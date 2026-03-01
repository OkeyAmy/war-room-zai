"""
WAR ROOM — Base Crisis Agent
Per voice.md: ONE agent = ONE Gemini Live session = ONE Firestore collection.

Each agent runs a PERSISTENT background loop:
  _receive_from_gemini() → streams audio chunks + transcripts to frontend
  _send_audio_to_gemini() → drains audio_in_queue from chairman mic
  _autonomous_turn_trigger() → keeps discussion alive without chairman

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
from datetime import datetime, timezone
from typing import Optional

from config.constants import ALLOWED_VOICE_POOL, GEMINI_FALLBACK_VOICES
from config.settings import get_settings

logger = logging.getLogger(__name__)


class CrisisAgent:
    """
    One CrisisAgent = one Gemini Live session = one Firestore collection.

    AUDIO PIPELINE:
      Gemini PCM → _receive_from_gemini() → push_event_direct(agent_audio_chunk)
              → WS queue → browser AudioManager.playChunk() → speakers

    CHAIRMAN AUDIO:
      browser mic → WS binary → audio_in_queue → _send_audio_to_gemini()
              → agent.live_session → Gemini processes → responds
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

        # ADK session ID — unique per agent instance
        self.adk_session_id = str(uuid.uuid4())

        # Gemini Live session (opened by initialize_live_session)
        self.live_session = None
        self._live_ctx = None

        settings = get_settings()
        self.live_model = settings.live_model
        self.text_model = settings.text_model
        self.voice_backend = settings.voice_backend
        self.elevenlabs_stt_model = settings.elevenlabs_stt_model
        self.elevenlabs_tts_model = settings.elevenlabs_tts_model

        # ADK (text mode — used for tool calls etc.)
        self.session_service = None
        self.llm_agent = None
        self.runner = None

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
            return (
                f"backend={self.voice_backend} "
                f"stt=elevenlabs:{self.elevenlabs_stt_model} "
                f"tts=elevenlabs:{self.elevenlabs_tts_model} "
                f"voice_id={self.assigned_voice} "
                f"llm={self.text_model} "
                f"allow_interruptions={str(bool(allow_interruptions)).lower()}"
            )
        if self.live_session:
            return (
                f"backend=gemini_live "
                f"realtime_model={self.live_model} "
                f"voice={self.assigned_voice} "
                f"llm={self.text_model}"
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

    # ── ADK Setup ─────────────────────────────────────────────────────

    def initialize_adk(self):
        """
        Initialize the ADK LlmAgent, Runner, and SessionService.
        Called during session bootstrapping.
        """
        try:
            from google.adk.agents import LlmAgent
            from google.adk.runners import Runner
            from google.adk.sessions import InMemorySessionService

            self.session_service = InMemorySessionService()
            self.llm_agent = LlmAgent(
                name=self.agent_id,
                model=self.text_model,
                instruction=self.skill_md,
                description=self.role_config.get("role_title", "Crisis Agent"),
                tools=self._build_tools(),
            )
            self.runner = Runner(
                agent=self.llm_agent,
                app_name=f"warroom_{self.session_id}",
                session_service=self.session_service,
            )
            logger.info(f"ADK initialized for agent {self.agent_id}")

        except ImportError:
            logger.warning(
                f"Google ADK not available — agent {self.agent_id} "
                "initialized in local-dev mode (no LLM)"
            )
            self.session_service = _MockSessionService()
            self.llm_agent = None
            self.runner = None

    def _build_tools(self) -> list:
        """Build the tool list. Tools are the ONLY way agents touch shared state."""
        from tools.crisis_board_tools import (
            read_crisis_board, write_agreed_decision,
            write_open_conflict, write_critical_intel,
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

        return [
            _read_crisis_board, _write_agreed_decision, _write_open_conflict,
            _write_critical_intel, _read_other_agent_last_statement,
            _update_my_trust_score, _publish_room_event,
            _read_my_private_memory, _write_my_private_memory,
        ]

    # ── Gemini Live Session Setup ─────────────────────────────────────

    async def initialize_live_session(self):
        """
        Initialize per-agent voice runtime.
        Only supported runtime:
          - LiveKit ElevenLabs STT/TTS plugins + Gemini text LLM
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

                logger.info(
                    f"[VOICE] livekit_elevenlabs ready for {self.agent_id} "
                    f"(stt={self.elevenlabs_stt_model}, "
                    f"tts={self.elevenlabs_tts_model}, llm={self.text_model})"
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

    def _build_live_config(self, types):
        """
        Per-agent Live config. voice.md §1.2.
        Each agent has its own unique voice — never shared.
        Context window compression prevents token overflow in long sessions.
        """
        voice_name = self.assigned_voice
        if voice_name not in GEMINI_FALLBACK_VOICES:
            voice_name = "Kore"
        return types.LiveConnectConfig(
            response_modalities=["AUDIO"],
            speech_config=types.SpeechConfig(
                voice_config=types.VoiceConfig(
                    prebuilt_voice_config=types.PrebuiltVoiceConfig(
                        voice_name=voice_name
                    )
                )
            ),
            system_instruction=types.Content(
                parts=[types.Part(text=self._build_live_system_prompt())],
                role="user"
            ),
            # Transcription: needed for Observer Agent + transcript display
            output_audio_transcription=types.AudioTranscriptionConfig(),
            # Context window compression: prevents token overflow in long sessions
            context_window_compression=types.ContextWindowCompressionConfig(
                trigger_tokens=104857,
                sliding_window=types.SlidingWindow(target_tokens=52428),
            ),
            # VAD: let Gemini detect natural speech endpoints
            realtime_input_config=types.RealtimeInputConfig(
                automatic_activity_detection=types.AutomaticActivityDetection(
                    disabled=False,
                )
            ),
        )

    def _build_live_system_prompt(self) -> str:
        """System instruction injected into the Live session."""
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
            self._tasks = [
                asyncio.create_task(self._receive_from_gemini(), name=f"{self.agent_id}_recv"),
                asyncio.create_task(self._send_audio_to_gemini(), name=f"{self.agent_id}_audio"),
                asyncio.create_task(self._autonomous_turn_trigger(), name=f"{self.agent_id}_auto"),
                asyncio.create_task(self._kickoff_opening_turn(), name=f"{self.agent_id}_kickoff"),
            ]
            logger.info(f"[{self.agent_id}] Background tasks started (recv + audio + auto)")

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
          LLM: Gemini text model (gemini-3-flash-preview)
          TTS: LiveKit ElevenLabs TTS
        """
        logger.info(f"[{self.agent_id}] Starting livekit_elevenlabs voice loop")
        while self._running and self.live_session:
            try:
                if not self.text_in_queue.empty():
                    text = await self.text_in_queue.get()
                    if text:
                        await self._generate_and_speak_reply(text)
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
                    await self._generate_and_speak_reply(transcript)

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
        from google import genai

        crisis_brief = await self._read_crisis_brief()
        history = self._render_conversation_history()
        intro_rule = (
            "You already introduced yourself earlier. Do NOT re-introduce your name/title."
            if self._introduced else
            "If this is your first speaking turn, introduce yourself once in one sentence."
        )
        prompt = (
            f"{self.skill_md}\n\n"
            f"[ROLE] {self.role_config.get('character_name', 'Agent')} "
            f"({self.role_config.get('role_title', 'Advisor')})\n"
            f"[CRISIS BRIEF]\n{crisis_brief}\n\n"
            f"[RECENT CONVERSATION]\n{history}\n\n"
            f"[INPUT]\n{user_text}\n\n"
            "Respond in character as spoken dialogue only.\n"
            "Do NOT print JSON, markdown code fences, tool call lists, or function-call arguments.\n"
            f"{intro_rule}\n"
            "Continue the current conversation; do not reset context.\n"
            "Use 2-4 sentences.\n"
            "In single-agent mode, do not fabricate debate with other agents unless explicitly asked."
        )

        models_to_try = [self.text_model, "gemini-2.5-flash", "gemini-2.0-flash"]
        for model_name in models_to_try:
            try:
                client = genai.Client()
                result = client.models.generate_content(
                    model=model_name,
                    contents=prompt,
                )
                text = self._sanitize_agent_reply(
                    (getattr(result, "text", None) or "").strip()
                )
                if text:
                    return text
            except Exception as e:
                logger.warning(
                    f"[{self.agent_id}] LLM generation failed model={model_name}: {e}"
                )

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

    async def _generate_and_speak_reply(self, user_text: str) -> None:
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
                    acquired = await self.turn_manager.try_acquire_turn(self.agent_id)
                    if not acquired:
                        return
                    holding_turn = True

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

                synthesis_ok = False
                for attempt in range(1, 4):
                    try:
                        tts_stream = self._lk_tts.synthesize(reply_text) if self._lk_tts else None
                        if not tts_stream:
                            break
                        async for ev in tts_stream:
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

    async def _receive_from_gemini(self):
        """
        PERSISTENT LOOP: Reads audio chunks + transcripts from Gemini Live.

        Per voice.md §1.4:
          response.data  → raw PCM bytes → base64 encode → WS event → browser plays
          response.text  → transcript chunk → WS event → UI display + Observer

        TURN MANAGEMENT:
          When the first audio chunk arrives, we acquire the turn from the
          TurnManager.  If another agent already holds the floor, we wait
          (with a timeout) before emitting audio.  The turn is released on
          turn_complete or interruption.

        AUDIO FIELD: We use 'audio_b64' in the event payload to match
        the frontend useWarRoomSocket handler.
        """
        from utils.events import push_event, push_event_direct
        from config.constants import (
            EVENT_AGENT_THINKING, EVENT_AGENT_SPEAKING_START,
            EVENT_AGENT_SPEAKING_CHUNK, EVENT_AGENT_SPEAKING_END,
            EVENT_AGENT_INTERRUPTED, EVENT_AGENT_STATUS_CHANGE,
        )

        logger.info(f"[{self.agent_id}] Starting receive loop")

        while self._running and self.live_session:
            # Session ended: stop all audio loops immediately
            if self.turn_manager and self.turn_manager.is_session_ended():
                break
            holding_turn = False
            try:
                # Signal: agent is thinking/ready
                await push_event(self.session_id, EVENT_AGENT_THINKING, {
                    "agent_id": self.agent_id,
                })

                full_transcript = ""
                audio_chunk_count = 0

                async for response in self.live_session.receive():

                    # ── CHECK YIELD (turn manager) ────────────────────
                    if (
                        holding_turn
                        and self.turn_manager
                        and self.turn_manager.should_yield(self.agent_id)
                    ):
                        # Chairman interrupted — stop speaking
                        logger.info(f"[{self.agent_id}] Yielding floor (chairman interrupt)")
                        self.turn_manager.release_turn(self.agent_id)
                        holding_turn = False
                        await push_event(self.session_id, EVENT_AGENT_INTERRUPTED, {
                            "agent_id": self.agent_id,
                        })
                        await push_event(self.session_id, EVENT_AGENT_STATUS_CHANGE, {
                            "agent_id": self.agent_id,
                            "status": "listening",
                        })
                        await self._clear_audio_buffer()
                        break

                    # ── INTERRUPTED ───────────────────────────────────
                    if (
                        response.server_content
                        and response.server_content.interrupted
                    ):
                        if holding_turn and self.turn_manager:
                            self.turn_manager.release_turn(self.agent_id)
                            holding_turn = False
                        await push_event(self.session_id, EVENT_AGENT_INTERRUPTED, {
                            "agent_id": self.agent_id,
                        })
                        await push_event(self.session_id, EVENT_AGENT_STATUS_CHANGE, {
                            "agent_id": self.agent_id,
                            "status": "listening",
                        })
                        logger.info(f"[{self.agent_id}] Interrupted")
                        # Clear any buffered audio
                        await self._clear_audio_buffer()
                        break

                    # ── AUDIO CHUNK ───────────────────────────────────
                    # response.data = raw PCM 24kHz 16-bit mono bytes
                    if response.data:
                        # Base64-encode for JSON WebSocket transport
                        audio_b64 = base64.b64encode(response.data).decode()
                        audio_chunk_count += 1

                        # First chunk → acquire turn + update UI to "speaking"
                        if audio_chunk_count == 1:
                            # IMMEDIATE-DROP: if someone else already holds the floor,
                            # discard this response rather than blocking for 15s.
                            # This prevents overlapping voices while keeping latency low.
                            if self.turn_manager:
                                # try_acquire_turn is now a proper coroutine that
                                # atomically checks + acquires the lock.
                                acquired = await self.turn_manager.try_acquire_turn(
                                    self.agent_id
                                )
                                if not acquired:
                                    logger.info(
                                        f"[{self.agent_id}] Could not acquire floor "
                                        "— dropping response"
                                    )
                                    break
                                holding_turn = True

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

                        # Direct push — skip Firestore (too slow for audio)
                        # FIELD NAME: 'audio_b64' matches frontend useWarRoomSocket
                        await push_event_direct(
                            self.session_id,
                            "agent_audio_chunk",
                            {
                                "agent_id": self.agent_id,
                                "audio_b64": audio_b64,
                                "sample_rate": 24000,
                                "channels": 1,
                                "bit_depth": 16,
                            },
                            source_agent_id=self.agent_id,
                        )

                    # ── TRANSCRIPT CHUNK ──────────────────────────────
                    # output_transcription gives us text of what agent said
                    if (
                        response.server_content
                        and response.server_content.output_transcription
                    ):
                        chunk = response.server_content.output_transcription.text
                        if chunk:
                            full_transcript += chunk
                            await push_event_direct(
                                self.session_id,
                                EVENT_AGENT_SPEAKING_CHUNK,
                                {
                                    "agent_id": self.agent_id,
                                    "transcript_chunk": chunk,
                                },
                                source_agent_id=self.agent_id,
                            )

                    # Also handle response.text (some SDK versions use this)
                    if response.text:
                        full_transcript += response.text
                        await push_event_direct(
                            self.session_id,
                            EVENT_AGENT_SPEAKING_CHUNK,
                            {
                                "agent_id": self.agent_id,
                                "transcript_chunk": response.text,
                            },
                            source_agent_id=self.agent_id,
                        )

                    # ── TURN COMPLETE ─────────────────────────────────
                    if (
                        response.server_content
                        and response.server_content.turn_complete
                    ):
                        # Release the speaking floor
                        if holding_turn and self.turn_manager:
                            self.turn_manager.release_turn(self.agent_id)
                            holding_turn = False

                        if audio_chunk_count > 0:
                            await push_event(self.session_id, EVENT_AGENT_SPEAKING_END, {
                                "agent_id": self.agent_id,
                                "full_transcript": full_transcript,
                                "audio_chunks": audio_chunk_count,
                            })
                            await push_event(self.session_id, EVENT_AGENT_STATUS_CHANGE, {
                                "agent_id": self.agent_id,
                                "status": "listening",
                                "previous_status": "speaking",
                            })

                            # Process turn completion
                            if full_transcript:
                                asyncio.create_task(
                                    self._on_turn_complete(full_transcript)
                                )

                        logger.info(
                            f"[{self.agent_id}] Turn complete: "
                            f"{audio_chunk_count} chunks, {len(full_transcript)} chars"
                        )
                        break

            except asyncio.CancelledError:
                if holding_turn and self.turn_manager:
                    self.turn_manager.release_turn(self.agent_id)
                break
            except Exception as e:
                if holding_turn and self.turn_manager:
                    self.turn_manager.release_turn(self.agent_id)
                    holding_turn = False
                logger.error(f"[{self.agent_id}] Receive loop error: {e}")
                await asyncio.sleep(1)  # Brief pause before retry

            # Post-turn cooldown: prevent the loop from immediately
            # restarting and picking up a new Gemini response before
            # other agents have a chance to acquire the floor.
            await asyncio.sleep(0.5)

        logger.info(f"[{self.agent_id}] Receive loop ended")

    async def _send_audio_to_gemini(self):
        """
        PERSISTENT LOOP: Drains audio_in_queue and sends PCM to agent's Live session.
        Per voice.md §1.6 — chairman mic goes into audio_in_queue, this drains it.

        ISOLATION: Only runs for THIS agent's queue. Other agents' queues are separate.
        """
        from google.genai import types

        logger.info(f"[{self.agent_id}] Starting audio send loop")

        while self._running and self.live_session:
            try:
                # Wait up to 1s for a chunk (allows _running check)
                try:
                    pcm_bytes = await asyncio.wait_for(
                        self.audio_in_queue.get(), timeout=1.0
                    )
                except asyncio.TimeoutError:
                    continue

                if pcm_bytes and self.live_session:
                    await self.live_session.send_realtime_input(
                        media=types.Blob(data=pcm_bytes, mime_type="audio/pcm;rate=16000")
                    )
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.warning(f"[{self.agent_id}] Audio send error: {e}")
                await asyncio.sleep(0.5)

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
                await asyncio.sleep(8)  # Check frequently to keep flow active

                if not self._running or not self.live_session:
                    break

                # ── Turn gating: skip if someone else is speaking ─────
                if self.turn_manager and not self.turn_manager.is_floor_free():
                    logger.debug(
                        f"[{self.agent_id}] Auto-trigger skipped — "
                        f"{self.turn_manager.current_speaker} holds the floor"
                    )
                    continue

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
        Send text to the agent's Live session.
        Uses send_realtime_input to avoid 1008 policy violations caused by interleaving 
        LiveClientContent with VAD-enabled audio sessions.
        """
        if self._lk_stt and self._lk_tts:
            await self.text_in_queue.put(text)
            return

        if self.live_session:
            import websockets
            try:
                await self.live_session.send_realtime_input(text=text)
            except websockets.exceptions.ConnectionClosed:
                logger.warning(f"Agent {self.agent_id} websocket closed, could not send text: {text[:20]}...")

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
        """Clean up: cancel background tasks and close Live session."""
        self._running = False

        # Cancel all background tasks
        for task in self._tasks:
            task.cancel()
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks = []

        # Close Live session
        if self._live_ctx:
            try:
                await self._live_ctx.__aexit__(None, None, None)
            except Exception:
                pass
            self._live_ctx = None
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
        if not self._live_ctx:
            self.live_session = None

        try:
            await self.memory_ref.update({"voice_session_active": False})
        except Exception:
            pass

        logger.info(f"[{self.agent_id}] Closed cleanly")


class _MockSessionService:
    """Minimal mock for when ADK is not installed."""
    pass
