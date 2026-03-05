"""
WAR ROOM — Base Crisis Agent
Per voice.md: ONE agent = ONE LiveKit session = ONE Firestore collection.

Each agent runs a PERSISTENT background loop:
  _livekit_voice_loop() → ElevenLabs STT → Z.AI GLM LLM → ElevenLabs TTS → audio events
  _introduce_on_join()  → opening character line on session start

MEMORY ISOLATION:
  - self.live_session belongs to THIS agent only, NEVER shared
  - Firestore writes use agent_id_{session_id} as doc key
  - Agent tools can ONLY read shared board state (via tools)
"""

from __future__ import annotations

import asyncio
import base64
import uuid
import logging
import re
import time
import random
from datetime import datetime, timezone
from typing import Optional

from config.constants import ALLOWED_VOICE_POOL
from config.settings import get_settings

logger = logging.getLogger(__name__)


class CrisisAgent:
    """
    One CrisisAgent = one LiveKit session = one Firestore collection.

    AUDIO PIPELINE (livekit_elevenlabs mode):
      chairman mic PCM → audio_in_queue → ElevenLabs STT
              → Z.AI GLM text LLM → ElevenLabs TTS
              → push_event_direct(agent_audio_chunk) → browser speakers
    """

    ALLOWED_VOICE_POOL = ALLOWED_VOICE_POOL

    def __init__(
        self,
        session_id: str,
        agent_id: str,
        role_config: dict,
        skill_md: str,
        assigned_voice: str,
        turn_manager=None,
        livekit_session_config: Optional[dict] = None,
    ):
        self.session_id = session_id
        self.agent_id = agent_id
        self.role_config = role_config
        self.assigned_voice = assigned_voice
        self.skill_md = skill_md

        # Turn manager — session-level coordination so only one agent speaks
        self.turn_manager = turn_manager
        self.livekit_session_config = livekit_session_config or {}

        # Live session presence marker
        self.live_session = None

        settings = get_settings()
        self.voice_backend = settings.voice_backend
        self.elevenlabs_stt_model = settings.elevenlabs_stt_model
        self.elevenlabs_tts_model = settings.elevenlabs_tts_model

        # LiveKit ElevenLabs stack (optional backend mode)
        self._lk_stt = None
        self._lk_tts = None
        self._lk_http_session = None
        self._lk_available_voice_ids: set[str] = set()

        # Firestore refs (lazy-initialized)
        self._db = None
        self._memory_ref = None
        self._crisis_ref = None

        # ── QUEUES: chairman → agent ─────────────────────────────────
        # ISOLATION: these queues are PRIVATE to this agent instance.
        # The VoiceRouter is the ONLY thing that puts into these queues.
        self.audio_in_queue: asyncio.Queue = asyncio.Queue()   # PCM bytes from chairman mic
        self.text_in_queue: asyncio.Queue = asyncio.Queue()    # text commands from chairman

        # Background tasks
        self._running = False
        self._tasks: list[asyncio.Task] = []
        # Hard serialization for one-agent mode:
        # prevent overlapping TTS generations from the same agent.
        self._speak_lock = asyncio.Lock()
        self._introduced = False
        self._conversation_history: list[dict[str, str]] = []
        self._last_user_input: str = ""
        self._last_user_input_at: float = 0.0
        self._last_agent_utterance: str = ""
        self._last_agent_utterance_at: float = 0.0

    def voice_runtime_summary(self) -> str:
        """
        Human-readable runtime stack marker for backend logs.
        """
        if self._lk_stt and self._lk_tts:
            allow_interruptions = self.livekit_session_config.get(
                "voice_options", {}
            ).get("allow_interruptions", True)
            settings = get_settings()
            return (
                f"backend={self.voice_backend} "
                f"stt=elevenlabs:{self.elevenlabs_stt_model} "
                f"tts=elevenlabs:{self.elevenlabs_tts_model} "
                f"voice_id={self.assigned_voice} "
                f"llm=zai:{settings.zai_agent_model} "
                f"allow_interruptions={str(bool(allow_interruptions)).lower()}"
            )
        return f"backend=unavailable requested_backend={self.voice_backend}"

    # ── Lazy Firestore ────────────────────────────────────────────────

    @property
    def db(self):
        if self._db is None:
            from utils.firestore_helpers import _get_db
            self._db = _get_db()
        return self._db

    @property
    def memory_ref(self):
        """Scoped to THIS agent's memory document ONLY."""
        if self._memory_ref is None:
            from config.constants import COLLECTION_AGENT_MEMORY
            self._memory_ref = self.db.collection(COLLECTION_AGENT_MEMORY).document(
                f"{self.agent_id}_{self.session_id}"
            )
        return self._memory_ref

    @property
    def crisis_ref(self):
        """Shared crisis session document (read-mostly)."""
        if self._crisis_ref is None:
            from config.constants import COLLECTION_CRISIS_SESSIONS
            self._crisis_ref = self.db.collection(COLLECTION_CRISIS_SESSIONS).document(
                self.session_id
            )
        return self._crisis_ref

    # ── Z.AI Client ───────────────────────────────────────────────────

    def _get_zai_client(self):
        """Return a configured OpenAI client pointing at Z.AI."""
        from openai import OpenAI
        settings = get_settings()
        return OpenAI(
            api_key=settings.zai_api_key,
            base_url=settings.zai_base_url,
        )

    def _build_tools(self) -> list:
        """Build the tool list. Tools are the ONLY way agents touch shared state."""
        from tools.crisis_board_tools import (
            read_crisis_board, write_agreed_decision,
            write_open_conflict, write_critical_intel,
            update_document_draft, flag_deadline_risk,
        )
        from tools.memory_tools import read_my_private_memory, write_my_private_memory
        from tools.event_tools import publish_room_event
        from tools.agent_tools import read_other_agent_last_statement, update_my_trust_score

        sid = self.session_id
        aid = self.agent_id

        async def _read_crisis_board() -> dict:
            """Read the current Crisis Board state."""
            return await read_crisis_board(sid, aid)

        async def _write_agreed_decision(text: str, agents_agreed: list[str]) -> dict:
            """Record an agreed decision on the Crisis Board."""
            return await write_agreed_decision(sid, aid, text, agents_agreed)

        async def _write_open_conflict(
            description: str, agents_involved: list[str], severity: str = "medium",
        ) -> dict:
            """Register a conflict on the Crisis Board."""
            return await write_open_conflict(sid, aid, description, agents_involved, severity)

        async def _write_critical_intel(text: str, source: str, is_escalation: bool = False) -> dict:
            """Drop critical intelligence onto the Crisis Board."""
            return await write_critical_intel(sid, aid, text, source, is_escalation)

        async def _read_my_private_memory() -> dict:
            """Read your private memory for consistency."""
            return await read_my_private_memory(sid, aid)

        async def _write_my_private_memory(key: str, value: str) -> dict:
            """Write to your private memory."""
            return await write_my_private_memory(sid, aid, key, value)

        async def _read_other_agent_last_statement(target_agent_id: str) -> dict:
            """Read another agent's last public statement."""
            return await read_other_agent_last_statement(sid, aid, target_agent_id)

        async def _update_my_trust_score(delta: int, reason: str) -> dict:
            """Update trust score."""
            return await update_my_trust_score(sid, aid, delta, reason)

        async def _publish_room_event(event_type: str, payload: dict) -> dict:
            """Publish an event to the room."""
            return await publish_room_event(sid, aid, event_type, payload)

        async def _update_document_draft(doc_id: str, section: str, content: str, status: str = "draft") -> dict:
            """Draft or update a section of an assigned response document."""
            return await update_document_draft(sid, aid, doc_id, section, content, status)

        async def _flag_deadline_risk(deadline_label: str, risk_note: str, hours_remaining: float = None) -> dict:
            """Escalate when a critical deadline is at risk."""
            return await flag_deadline_risk(sid, aid, deadline_label, risk_note, hours_remaining)

        return [
            _read_crisis_board, _write_agreed_decision, _write_open_conflict,
            _write_critical_intel, _read_other_agent_last_statement,
            _update_my_trust_score, _publish_room_event,
            _read_my_private_memory, _write_my_private_memory,
            _update_document_draft, _flag_deadline_risk,
        ]

    # ── Voice Session Setup ───────────────────────────────────────────

    async def initialize_live_session(self):
        """
        Initialize per-agent voice runtime.
        Only supported runtime:
          - LiveKit ElevenLabs STT/TTS plugins + Z.AI GLM text LLM
        """
        if self.voice_backend != "livekit_elevenlabs":
            logger.warning(
                f"[VOICE] Unsupported voice_backend={self.voice_backend} for {self.agent_id}. "
                "Only livekit_elevenlabs is enabled."
            )
            self.live_session = None
            return

        if self.voice_backend == "livekit_elevenlabs":
            try:
                import aiohttp
                from livekit.plugins import elevenlabs
                settings = get_settings()
                if not settings.elevenlabs_api_key:
                    raise RuntimeError("ELEVENLABS_API_KEY missing")
                self._lk_http_session = aiohttp.ClientSession(
                    timeout=aiohttp.ClientTimeout(total=45, sock_connect=10),
                )
                self._lk_stt = elevenlabs.STT(
                    api_key=settings.elevenlabs_api_key or None,
                    model_id=self.elevenlabs_stt_model,
                    http_session=self._lk_http_session,
                )
                self._lk_tts = elevenlabs.TTS(
                    api_key=settings.elevenlabs_api_key or None,
                    voice_id=self.assigned_voice,
                    model=self.elevenlabs_tts_model,
                    http_session=self._lk_http_session,
                )
                # Ensure assigned voice is valid for this ElevenLabs account.
                await self._ensure_livekit_voice_selection()
                # Presence marker for existing health checks.
                self.live_session = object()

                try:
                    await self.memory_ref.update({
                        "voice_session_active": True,
                        "voice_name": self.assigned_voice,
                        "voice_backend": self.voice_backend,
                    })
                except Exception:
                    logger.debug(
                        f"[VOICE] memory_ref not ready for {self.agent_id} "
                        "(will be created by bootstrapper)"
                    )

                settings = get_settings()
                logger.info(
                    f"[VOICE] livekit_elevenlabs ready for {self.agent_id} "
                    f"(stt={self.elevenlabs_stt_model}, "
                    f"tts={self.elevenlabs_tts_model}, llm=zai:{settings.zai_agent_model})"
                )
                return
            except Exception as e:
                logger.warning(
                    f"[VOICE] livekit_elevenlabs init failed for {self.agent_id}: {e}. "
                    "Voice disabled for this agent."
                )
                self.live_session = None
                return

    async def _ensure_livekit_voice_selection(self) -> None:
        """Validate current voice_id against ElevenLabs account voices and fallback safely."""
        if not self._lk_tts:
            return
        try:
            voices = await self._lk_tts.list_voices()
            ids = set()
            for v in voices or []:
                vid = getattr(v, "id", None) or getattr(v, "voice_id", None)
                if isinstance(vid, str) and vid:
                    ids.add(vid)
            self._lk_available_voice_ids = ids
            if ids and self.assigned_voice not in ids:
                fallback = next(iter(ids))
                logger.warning(
                    f"[VOICE] {self.agent_id} assigned_voice={self.assigned_voice} "
                    f"not available in ElevenLabs account. Falling back to {fallback}."
                )
                self.assigned_voice = fallback
                self._lk_tts.update_options(voice_id=fallback)
        except Exception as e:
            logger.warning(
                f"[VOICE] {self.agent_id} failed to validate ElevenLabs voice list: {e}"
            )

    async def _rebuild_livekit_tts(self) -> bool:
        """Recreate ElevenLabs TTS client after connection failures."""
        if not self._lk_http_session:
            return False
        try:
            from livekit.plugins import elevenlabs
            settings = get_settings()
            if self._lk_tts:
                try:
                    await self._lk_tts.aclose()
                except Exception:
                    pass
            self._lk_tts = elevenlabs.TTS(
                api_key=settings.elevenlabs_api_key or None,
                voice_id=self.assigned_voice,
                model=self.elevenlabs_tts_model,
                http_session=self._lk_http_session,
            )
            await self._ensure_livekit_voice_selection()
            return True
        except Exception as e:
            logger.warning(f"[VOICE] {self.agent_id} failed to rebuild ElevenLabs TTS: {e}")
            return False

    def _build_live_system_prompt(self) -> str:
        """System instruction for the LLM."""
        role = self.role_config
        char = role.get("character_name", "Agent")
        title = role.get("role_title", "Advisor")
        traits = ", ".join(role.get("personality_traits", []))
        style = role.get("voice_style", "measured")

        prompt = (
            f"{self.skill_md}\n\n"
            f"---\n"
            f"VOICE PERSONA: You are {char}, the {title}.\n"
            f"Voice style: {style}. Personality: {traits}.\n\n"
            f"RULES:\n"
            f"- Speak naturally and in character at all times.\n"
            f"- Keep responses concise: 2-3 sentences unless elaborating on a key point.\n"
            f"- If interrupted, stop immediately and listen.\n"
            f"- React to what other agents say — agree, push back, add nuance.\n"
            f"- You are in a live crisis simulation. The stakes are real to you.\n"
        )
        return prompt

    # ── Persistent Background Tasks (voice.md §1.3) ───────────────────

    async def start_background_tasks(self):
        """
        Launch the three persistent background tasks per voice.md §1.3.
        These run for the lifetime of the session.
        Call this AFTER initialize_live_session().
        """
        if not self.live_session:
            logger.warning(
                f"[{self.agent_id}] No live session — background tasks not started"
            )
            return

        self._running = True
        if self._lk_stt and self._lk_tts:
            self._tasks = [
                asyncio.create_task(self._livekit_voice_loop(), name=f"{self.agent_id}_lk_voice"),
                asyncio.create_task(self._introduce_on_join(), name=f"{self.agent_id}_intro"),
            ]
            logger.info(
                f"[{self.agent_id}] Background tasks started "
                "(livekit_elevenlabs voice)"
            )
        else:
            # No supported runtime available — log warning and skip
            logger.warning(
                f"[{self.agent_id}] No supported voice runtime. "
                "Live session unavailable."
            )

    async def _introduce_on_join(self):
        """
        LiveKit-mode opening line so the active agent announces itself on entry.
        """
        startup = self.livekit_session_config.get("startup", {})
        if not startup.get("introduce_on_join", True):
            return
        if self._introduced:
            return
        delay = float(startup.get("intro_delay_seconds", 1.0))
        intro_message = startup.get("intro_message", "")
        if not intro_message:
            char = self.role_config.get("character_name", "Agent")
            title = self.role_config.get("role_title", "Advisor")
            intro_message = (
                f"I am {char}, {title}. I am online and ready. "
                "Share the immediate crisis objective."
            )
        await asyncio.sleep(max(0.2, delay))
        if self._running and self.live_session and not self._introduced:
            await self.send_text(intro_message)
            self._introduced = True

    async def _kickoff_opening_turn(self):
        """
        Seed one initial turn quickly after startup so agents begin speaking
        without waiting for chairman input.
        """
        try:
            # Small jitter based on agent id to reduce same-time collisions.
            jitter = (abs(hash(self.agent_id)) % 5) * 0.4
            await asyncio.sleep(2.0 + jitter)
            if self._running and self.live_session:
                await self.send_text(
                    "Opening turn: introduce your immediate assessment and top priority "
                    "for this crisis in 2 concise sentences."
                )
        except Exception as e:
            logger.debug(f"[{self.agent_id}] kickoff turn skipped: {e}")

    async def _livekit_voice_loop(self):
        """
        Voice loop for:
          STT: LiveKit ElevenLabs STT
          LLM: Z.AI GLM via OpenAI SDK
          TTS: LiveKit ElevenLabs TTS
        """
        logger.info(f"[{self.agent_id}] Starting livekit_elevenlabs voice loop")
        while self._running and self.live_session:
            try:
                if not self.text_in_queue.empty():
                    text = await self.text_in_queue.get()
                    if text:
                        await self._generate_and_speak_reply(text, is_directive=True)
                    continue

                try:
                    first_chunk = await asyncio.wait_for(self.audio_in_queue.get(), timeout=0.5)
                except asyncio.TimeoutError:
                    continue

                chunks = [first_chunk]
                while True:
                    try:
                        nxt = await asyncio.wait_for(self.audio_in_queue.get(), timeout=0.35)
                        chunks.append(nxt)
                    except asyncio.TimeoutError:
                        break

                transcript = await self._transcribe_pcm(b"".join(chunks))
                if transcript:
                    await self._generate_and_speak_reply(transcript, is_directive=False)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.warning(f"[{self.agent_id}] livekit_elevenlabs loop error: {e}")
                await asyncio.sleep(0.5)

    async def _transcribe_pcm(self, pcm_bytes: bytes) -> str:
        if not self._lk_stt or not pcm_bytes:
            return ""
        try:
            from livekit import rtc
            samples_per_channel = len(pcm_bytes) // 2
            if samples_per_channel <= 0:
                return ""
            frame = rtc.AudioFrame(
                data=pcm_bytes,
                sample_rate=16000,
                num_channels=1,
                samples_per_channel=samples_per_channel,
            )
            event = await self._lk_stt.recognize(frame)
            if event.alternatives:
                text = (event.alternatives[0].text or "").strip()
                if len(text) < 2:
                    return ""
                if self._is_probable_echo(text):
                    logger.info(f"[{self.agent_id}] Ignoring probable echo transcript")
                    return ""
                return text
        except Exception as e:
            logger.warning(f"[{self.agent_id}] STT failed: {e}")
        return ""

    async def _generate_llm_reply(self, user_text: str) -> str:
        settings = get_settings()
        if not settings.zai_api_key:
            return "[LLM unavailable — ZAI_API_KEY not configured]"

        crisis_brief = await self._read_crisis_brief()
        history = self._render_conversation_history()
        intro_rule = (
            "You already introduced yourself earlier. Do NOT re-introduce your name/title."
            if self._introduced else
            "If this is your first speaking turn, introduce yourself once in one sentence."
        )
        system_prompt = (
            f"{self.skill_md}\n\n"
            f"VOICE PERSONA: You are {self.role_config.get('character_name', 'Agent')}, "
            f"the {self.role_config.get('role_title', 'Advisor')}.\n"
            f"CRISIS BRIEF:\n{crisis_brief}\n\n"
            "Respond in character as spoken dialogue only. "
            "Do NOT print JSON, markdown code fences, tool call lists, or function-call arguments. "
            f"{intro_rule} "
            "Continue the current conversation; do not reset context. "
            "Use 2-4 sentences. "
            "In single-agent mode, do not fabricate debate with other agents unless explicitly asked."
        )

        messages = [
            {"role": "system", "content": system_prompt},
        ]
        # Include recent history as alternating user/assistant turns
        for item in self._conversation_history[-8:]:
            role = item.get("role", "user")
            turn_role = "user" if role == "chairman" else "assistant"
            messages.append({"role": turn_role, "content": item.get("text", "")})
        messages.append({"role": "user", "content": user_text})

        try:
            client = self._get_zai_client()
            response = await asyncio.to_thread(
                client.chat.completions.create,
                model=settings.zai_agent_model,
                messages=messages,
                temperature=0.88,
                max_tokens=600,
            )
            text = self._sanitize_agent_reply(
                (response.choices[0].message.content or "").strip()
            )
            if text:
                return text
        except Exception as e:
            logger.warning(f"[{self.agent_id}] Z.AI LLM generation failed: {e}")

        return "We are out of alignment. I need one concrete proposal from the room right now."

    def _sanitize_agent_reply(self, text: str) -> str:
        """
        Strip tool-call JSON/code-fence noise so only spoken dialogue reaches TTS/feed.
        """
        if not text:
            return ""

        # Remove fenced code blocks (often tool-call JSON dumps).
        text = re.sub(r"```[\s\S]*?```", " ", text)
        # Remove leading JSON array/object blobs if model emits tool traces.
        text = re.sub(r"^\s*(\{[\s\S]*?\}|\[[\s\S]*?\])\s*", " ", text)
        # Collapse whitespace.
        text = re.sub(r"\s+", " ", text).strip()
        return text

    async def _read_crisis_brief(self) -> str:
        try:
            doc = await self.crisis_ref.get()
            if doc.exists:
                return (doc.to_dict() or {}).get("crisis_brief", "")
        except Exception:
            pass
        return ""

    def _normalize_text(self, text: str) -> str:
        return re.sub(r"\s+", " ", (text or "").strip().lower())

    def _append_conversation(self, role: str, text: str) -> None:
        if not text:
            return
        self._conversation_history.append({"role": role, "text": text.strip()})
        if len(self._conversation_history) > 14:
            self._conversation_history = self._conversation_history[-14:]

    def _render_conversation_history(self) -> str:
        if not self._conversation_history:
            return "No prior turns."
        rendered = []
        for item in self._conversation_history[-10:]:
            role = item.get("role", "unknown").upper()
            text = item.get("text", "")
            rendered.append(f"{role}: {text}")
        return "\n".join(rendered)

    def _is_probable_echo(self, transcript: str) -> bool:
        now = time.monotonic()
        if now - self._last_agent_utterance_at > 8.0:
            return False
        t = self._normalize_text(transcript)
        a = self._normalize_text(self._last_agent_utterance)
        if not t or not a:
            return False
        return t in a or a.startswith(t)

    async def _generate_and_speak_reply(self, user_text: str, is_directive: bool = False) -> None:
        from utils.events import push_event, push_event_direct
        from config.constants import (
            EVENT_AGENT_THINKING,
            EVENT_AGENT_SPEAKING_START,
            EVENT_AGENT_SPEAKING_CHUNK,
            EVENT_AGENT_SPEAKING_END,
            EVENT_AGENT_INTERRUPTED,
            EVENT_AGENT_STATUS_CHANGE,
        )

        async with self._speak_lock:
            normalized_user = self._normalize_text(user_text)
            now = time.monotonic()
            if (
                normalized_user
                and normalized_user == self._last_user_input
                and (now - self._last_user_input_at) < 3.0
            ):
                logger.info(f"[{self.agent_id}] Dropping duplicate user input")
                return
            self._last_user_input = normalized_user
            self._last_user_input_at = now
            self._append_conversation("chairman", user_text)

            await push_event(self.session_id, EVENT_AGENT_THINKING, {"agent_id": self.agent_id})
            logger.info(
                f"[VOICE_RUNTIME] session={self.session_id} agent={self.agent_id} "
                f"{self.voice_runtime_summary()}"
            )
            reply_text = await self._generate_llm_reply(user_text)
            if not reply_text:
                return
            if not self._introduced:
                self._introduced = True
            self._append_conversation("agent", reply_text)
            self._last_agent_utterance = reply_text
            self._last_agent_utterance_at = time.monotonic()

            holding_turn = False
            allow_interruptions = bool(
                self.livekit_session_config.get("voice_options", {}).get(
                    "allow_interruptions", True
                )
            )
            try:
                if self.turn_manager:
                    if is_directive:
                        wait_start = time.monotonic()
                        while True:
                            acquired = await self.turn_manager.try_acquire_turn(self.agent_id)
                            if acquired or time.monotonic() - wait_start > 45.0:
                                break
                            await asyncio.sleep(0.5)
                    else:
                        acquired = await self.turn_manager.try_acquire_turn(self.agent_id)
                        
                    if not acquired:
                        return
                    holding_turn = True

                first_chunk = True
                synthesis_ok = False
                for attempt in range(1, 4):
                    try:
                        tts_stream = self._lk_tts.synthesize(reply_text) if self._lk_tts else None
                        if not tts_stream:
                            break
                        async for ev in tts_stream:
                            if first_chunk:
                                await push_event(self.session_id, EVENT_AGENT_SPEAKING_START, {
                                    "agent_id": self.agent_id,
                                    "character_name": self.role_config.get("character_name", "Agent"),
                                    "voice_name": self.assigned_voice,
                                })
                                await push_event(self.session_id, EVENT_AGENT_STATUS_CHANGE, {
                                    "agent_id": self.agent_id,
                                    "status": "speaking",
                                    "previous_status": "thinking",
                                })
                                await self._update_roster_status("speaking", "thinking")
                                await push_event_direct(
                                    self.session_id,
                                    EVENT_AGENT_SPEAKING_CHUNK,
                                    {"agent_id": self.agent_id, "transcript_chunk": reply_text},
                                    source_agent_id=self.agent_id,
                                )
                                first_chunk = False

                            if (
                                allow_interruptions
                                and self.turn_manager
                                and self.turn_manager.should_yield(self.agent_id)
                            ):
                                await push_event(self.session_id, EVENT_AGENT_INTERRUPTED, {
                                    "agent_id": self.agent_id,
                                })
                                await self._update_roster_status("listening", "speaking")
                                break
                            audio_b64 = base64.b64encode(ev.frame.data).decode()
                            await push_event_direct(
                                self.session_id,
                                "agent_audio_chunk",
                                {
                                    "agent_id": self.agent_id,
                                    "audio_b64": audio_b64,
                                    "sample_rate": ev.frame.sample_rate,
                                    "channels": ev.frame.num_channels,
                                    "bit_depth": 16,
                                },
                                source_agent_id=self.agent_id,
                            )
                        synthesis_ok = True
                        break
                    except Exception as e:
                        logger.warning(
                            f"[{self.agent_id}] ElevenLabs synth attempt {attempt}/3 failed: {e}"
                        )
                        await self._rebuild_livekit_tts()
                        await asyncio.sleep(min(1.0 * attempt, 2.5))
                if not synthesis_ok:
                    logger.warning(f"[{self.agent_id}] ElevenLabs synthesis failed after retries")

                await push_event(self.session_id, EVENT_AGENT_SPEAKING_END, {
                    "agent_id": self.agent_id,
                    "full_transcript": reply_text,
                })
                await push_event(self.session_id, EVENT_AGENT_STATUS_CHANGE, {
                    "agent_id": self.agent_id,
                    "status": "listening",
                    "previous_status": "speaking",
                })
                await self._update_roster_status("listening", "speaking")
                await self._on_turn_complete(reply_text)
            finally:
                if holding_turn and self.turn_manager:
                    self.turn_manager.release_turn(self.agent_id)



    async def _autonomous_turn_trigger(self):
        """
        PERSISTENT LOOP: Per voice.md §1.6 — if no one speaks for N seconds,
        agent considers speaking based on board state.
        This keeps the room alive without the Chairman driving everything.

        TURN MANAGEMENT: Uses try_acquire (non-blocking) so agents don't
        pile up waiting.  If the floor is occupied, this cycle is skipped.
        """
        char = self.role_config.get("character_name", "Agent")
        title = self.role_config.get("role_title", "Advisor")

        # Warm up briefly, then keep room active.
        await asyncio.sleep(4)

        while self._running and self.live_session:
            try:
                # Poll frequently to accurately hit the 5-8s silence window
                await asyncio.sleep(1.0)

                if not self._running or not self.live_session:
                    break

                # ── Turn gating: skip if someone else is speaking ─────
                if self.turn_manager and not self.turn_manager.is_floor_free():
                    continue

                if self.turn_manager:
                    # Each agent picks a random silence target for their next autonomous turn
                    target_silence = getattr(self, '_current_target_silence', 0)
                    if not target_silence:
                        self._current_target_silence = random.uniform(5.5, 8.0)
                        target_silence = self._current_target_silence

                    silent_duration = time.monotonic() - self.turn_manager.last_turn_end_time
                    if silent_duration < target_silence:
                        continue
                        
                    # Target reached! Try to trigger, and pick a new target for next time
                    self._current_target_silence = random.uniform(5.5, 8.0)
                    
                    # Prevent multiple agents from triggering simultaneously (due to same polling cycle)
                    last_trigger = getattr(self.turn_manager, 'last_autonomous_trigger', 0)
                    if time.monotonic() - last_trigger < 6.0:
                        continue
                    self.turn_manager.last_autonomous_trigger = time.monotonic()

                # Read shared board state
                try:
                    doc = await self.crisis_ref.get()
                    board_data = doc.to_dict() if doc.exists else {}
                except Exception:
                    board_data = {}

                threat = board_data.get("threat_level", "elevated")
                score = board_data.get("resolution_score", 50)
                decisions = len(board_data.get("agreed_decisions", []))
                conflicts = len(board_data.get("open_conflicts", []))

                prompt = (
                    f"[BOARD STATE] Threat: {threat} | Score: {score}/100 | "
                    f"Decisions: {decisions} | Open conflicts: {conflicts}\n\n"
                    f"You are {char}, the {title}. "
                    f"Based on the current board state and your expertise, "
                    f"decide whether to speak now. If yes, make your point "
                    f"(2-3 sentences). If the situation doesn't warrant it, "
                    f"stay silent by saying nothing."
                )

                await self.send_text(prompt)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.warning(f"[{self.agent_id}] Auto-trigger error: {e}")
                await asyncio.sleep(5)

    # ── Chairman Input Handlers ───────────────────────────────────────

    async def receive_chairman_audio(self, pcm_bytes: bytes) -> None:
        """
        Called by VoiceRouter when Chairman targets this agent (or full room).
        Per voice.md §1.6 — puts into audio_in_queue, consumed by _send_audio_to_gemini.

        ISOLATION: Only called for the intended agent. VoiceRouter enforces this.
        """
        await self.audio_in_queue.put(pcm_bytes)

    async def receive_text_command(self, text: str) -> None:
        """
        Chairman text command → agent responds in voice.
        Per voice.md §1.6.
        """
        await self.send_text(text)

    async def send_text(self, text: str) -> None:
        """
        Send text to the agent's voice loop queue.
        For livekit_elevenlabs mode this queues to text_in_queue.
        """
        await self.text_in_queue.put(text)

    async def send_audio(self, audio_data: bytes) -> None:
        """Send raw PCM audio to the agent's Live session."""
        await self.audio_in_queue.put(audio_data)

    async def _update_roster_status(self, status: str, previous_status: str = "") -> None:
        """
        Keep crisis_sessions.agent_roster status in sync with live speaking state
        so REST APIs reflect the same state as websocket events.
        """
        try:
            doc = await self.crisis_ref.get()
            if not doc.exists:
                return
            crisis = doc.to_dict() or {}
            roster = crisis.get("agent_roster", [])
            changed = False
            now = datetime.now(timezone.utc).isoformat()
            for entry in roster:
                if entry.get("agent_id") == self.agent_id:
                    if entry.get("status") != status:
                        entry["status"] = status
                        if status == "speaking":
                            entry["last_spoke_at"] = now
                        changed = True
                    break
            if changed:
                await self.crisis_ref.update({"agent_roster": roster, "updated_at": now})
        except Exception as e:
            logger.debug(f"[{self.agent_id}] roster status sync skipped: {e}")

    # ── Turn Complete Handler ─────────────────────────────────────────

    async def _on_turn_complete(self, transcript: str) -> None:
        """
        Per voice.md §1.5 — processes what agent said after each turn.
        Writes ONLY to this agent's own data. Never touches other agents.
        """
        now = datetime.now(timezone.utc).isoformat()

        # 1. Update last_statement in shared session (the ONE shared field)
        try:
            await self.crisis_ref.update({
                f"agent_last_statement_{self.agent_id}": transcript[:200],
                "last_speaker_agent_id": self.agent_id,
                "last_speaker_excerpt": transcript[:240],
                "updated_at": now,
            })
        except Exception as e:
            logger.warning(f"[{self.agent_id}] Failed to update last_statement: {e}")

        # 2. Append to THIS agent's private memory
        try:
            statement = {"text": transcript, "spoken_at": now}
            try:
                from google.cloud import firestore as fs
                await self.memory_ref.update({
                    "previous_statements": fs.ArrayUnion([statement]),
                    "last_spoke_at": now,
                })
            except Exception:
                doc = await self.memory_ref.get()
                data = doc.to_dict() if doc.exists else {}
                prev = data.get("previous_statements", [])
                if not isinstance(prev, list):
                    prev = []
                prev.append(statement)
                await self.memory_ref.set({
                    **data,
                    "previous_statements": prev[-20:],
                    "last_spoke_at": now,
                }, merge=True)
        except Exception as e:
            logger.warning(f"[{self.agent_id}] Failed to update private memory: {e}")

        # 3. Trigger Observer analysis so board/conflicts/intel keep evolving.
        try:
            from gateway.chairman_handler import get_observer_agent
            observer = get_observer_agent(self.session_id)
            if observer:
                await observer.analyze_statement(
                    session_id=self.session_id,
                    agent_id=self.agent_id,
                    transcript=transcript,
                )
        except Exception as e:
            logger.warning(f"[{self.agent_id}] Observer analysis failed: {e}")

    async def _clear_audio_buffer(self) -> None:
        """Clear pending audio chunks when interrupted."""
        while not self.audio_in_queue.empty():
            try:
                self.audio_in_queue.get_nowait()
            except asyncio.QueueEmpty:
                break

    # ── Lifecycle ────────────────────────────────────────────────────

    async def close(self) -> None:
        """Clean up: cancel background tasks and close voice session."""
        self._running = False

        # Cancel all background tasks
        for task in self._tasks:
            task.cancel()
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks = []

        # Mark live session as closed
        self.live_session = None

        if self._lk_stt:
            try:
                await self._lk_stt.aclose()
            except Exception:
                pass
            self._lk_stt = None

        if self._lk_tts:
            try:
                await self._lk_tts.aclose()
            except Exception:
                pass
            self._lk_tts = None
        if self._lk_http_session and not self._lk_http_session.closed:
            try:
                await self._lk_http_session.close()
            except Exception:
                pass
            self._lk_http_session = None

        try:
            await self.memory_ref.update({"voice_session_active": False})
        except Exception:
            pass

        logger.info(f"[{self.agent_id}] Closed cleanly")
