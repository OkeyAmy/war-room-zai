# ⚔️ WAR ROOM — Gemini Live Voice Pipeline
## Complete Guide: Getting Agent Voices Into the Browser

> **Goal:** Every agent has a unique voice. The browser plays it live.
> Chairman speaks into mic. Agents hear it and respond.
> Zero cross-agent memory. Zero audio bleed between sessions.

---

## THE CORE PROBLEM

The reference script (`AudioLoop`) runs everything in **one Python process**
with **one Gemini Live session**. It plays audio directly through `pyaudio`
on the server machine.

Your War Room needs:
- **N separate Gemini Live sessions** (one per agent, fully isolated)
- Audio sent **over the network** to the browser, not played locally
- Browser playing **multiple agents** through a single audio output
- Chairman mic captured in the **browser** and routed to the right agent
- **No session state crossing** between agents

This guide solves all of that.

---

## ARCHITECTURE OVERVIEW

```
BROWSER                        GATEWAY (FastAPI)              GEMINI
───────────────────────────    ────────────────────────────   ────────────────

[Chairman Mic]                 
  └─ PCM 16kHz chunks ──────→  /ws/{session_id}/audio
                                  │
                                  ├─ routes to target agent
                                  │   └─────────────────────────────────────→ Agent Live Session
                                  │                                                │
                                  │         ←── PCM 24kHz audio chunks ───────────┘
                                  │         ←── transcript text ────────────────────
                                  │
                                  ├─ audio_chunk WS event ──────────────────→ [Browser AudioContext]
                                  └─ agent_speaking_chunk WS event ────────→ [Transcript display]

[AudioContext.decodeAudioData()]
  └─ PCM → AudioBuffer → play()
      └─ User hears agent voice ✓
```

---

## PART 1 — BACKEND: ONE LIVE SESSION PER AGENT

### 1.1 — The CrisisAgent Class (Isolated Voice Session)

Each agent runs this class. The critical design decision:
**one `client.aio.live.connect()` per agent, never shared.**

```python
# war_room/agents/crisis_agent.py

import asyncio
import json
from google import genai
from google.genai import types

class CrisisAgent:
    """
    One agent = one Gemini Live session = one Firestore collection.

    MEMORY ISOLATION RULES (enforced here):
      - self.session: belongs to THIS agent only
      - self.agent_id: used as Firestore collection prefix
      - We NEVER pass another agent's session or memory here
      - We NEVER read from agent_memory/{other_agent}
      - We ONLY read from crisis_sessions (shared board) via tools
    """

    def __init__(
        self,
        agent_id: str,          # e.g. "atlas_A3F9B2C1"
        session_id: str,        # e.g. "A3F9B2C1"
        character_name: str,    # e.g. "ATLAS"
        role_title: str,        # e.g. "Strategic Analyst"
        voice_name: str,        # e.g. "Orus"  — unique per agent
        skill_md: str,          # 300-600 word generated instruction doc
        db,                     # get_db() — LocalDevDB or Firestore
        event_publisher,        # function to push WS events
    ):
        self.agent_id       = agent_id
        self.session_id     = session_id
        self.character_name = character_name
        self.role_title     = role_title
        self.voice_name     = voice_name
        self.skill_md       = skill_md
        self.db             = db
        self.publish        = event_publisher

        # THIS IS THE ISOLATED SESSION — only this agent uses it
        self.live_session   = None
        self.audio_out_queue = asyncio.Queue()   # PCM chunks going TO browser
        self.text_in_queue   = asyncio.Queue()   # chairman text commands
        self.audio_in_queue  = asyncio.Queue()   # chairman audio chunks

        self._running = False
        self._tasks   = []
```

---

### 1.2 — The Live Config (Per Agent, Never Shared)

```python
    def _build_config(self) -> types.LiveConnectConfig:
        """
        Each agent gets its own config with its own voice.
        This is called once at boot, never shared between agents.
        """
        return types.LiveConnectConfig(
            response_modalities=["AUDIO"],   # Audio out + text transcript

            # ── VOICE: unique per agent ─────────────────────────────────
            speech_config=types.SpeechConfig(
                voice_config=types.VoiceConfig(
                    prebuilt_voice_config=types.PrebuiltVoiceConfig(
                        voice_name=self.voice_name  # e.g. "Fenrir", "Kore", "Orus"
                    )
                )
            ),

            # ── SYSTEM INSTRUCTION: the SKILL.md ─────────────────────────
            # This is where the agent's identity lives.
            # Generated fresh per session by Scenario Analyst.
            system_instruction=types.Content(
                parts=[types.Part(text=self.skill_md)],
                role="user"
            ),

            # ── CONTEXT WINDOW COMPRESSION ───────────────────────────────
            # Critical for long sessions — prevents token overflow
            context_window_compression=types.ContextWindowCompressionConfig(
                trigger_tokens=104857,
                sliding_window=types.SlidingWindow(target_tokens=52428),
            ),

            # ── ENABLE TRANSCRIPTION (so we get text + audio) ────────────
            # Without this, we only get audio bytes — no transcript text.
            # We need the transcript for the Observer Agent and UI display.
            output_audio_transcription=types.AudioTranscriptionConfig(),
        )
```

---

### 1.3 — Starting the Live Session

```python
    async def start(self):
        """
        Opens the Gemini Live WebSocket for THIS agent.
        Must be called before any audio flows.
        """
        self._running = True
        config = self._build_config()

        # ─── THIS IS THE ISOLATED CONNECTION ────────────────────────────
        # Each agent calls this independently.
        # client is the shared genai.Client (safe — stateless),
        # but the SESSION object returned is fully isolated per agent.
        async with client.aio.live.connect(
            model="models/gemini-2.5-flash-native-audio-preview-12-2025",
            config=config
        ) as session:
            self.live_session = session

            # Update Firestore: this agent is now voice-active
            await self.db.collection("agent_memory").document(
                f"{self.agent_id}_{self.session_id}"
            ).update({"voice_session_active": True})

            # Push WS event: frontend pod goes from IDLE to LISTENING
            await self.publish({
                "event_type": "agent_status_change",
                "payload": {
                    "agent_id":   self.agent_id,
                    "status":     "listening",
                    "voice_name": self.voice_name,
                }
            })

            # Run all pipelines concurrently
            async with asyncio.TaskGroup() as tg:
                tg.create_task(self._receive_from_gemini())
                tg.create_task(self._send_audio_to_gemini())
                tg.create_task(self._send_text_to_gemini())
                tg.create_task(self._autonomous_turn_trigger())
```

---

### 1.4 — Receiving Audio FROM Gemini (The Voice Output)

```python
    async def _receive_from_gemini(self):
        """
        Reads audio chunks and transcript from Gemini Live.
        Audio chunks → audio_out_queue → WebSocket → Browser.
        Transcript  → WS event → UI transcript display + Observer.

        THIS IS WHERE THE VOICE COMES FROM.
        """
        while self._running:
            turn = self.live_session.receive()

            # Signal speaking start
            await self.publish({
                "event_type": "agent_speaking_start",
                "payload": {"agent_id": self.agent_id, "character_name": self.character_name}
            })
            await self._set_status("speaking")

            full_transcript = ""

            async for response in turn:

                # ── AUDIO CHUNK ──────────────────────────────────────────
                # This is raw PCM 24kHz 16-bit mono audio.
                # We forward it to the browser via WebSocket.
                if response.data:
                    await self.publish({
                        "event_type": "agent_audio_chunk",
                        "payload": {
                            "agent_id":   self.agent_id,
                            "audio_b64":  response.data,  # bytes → b64 in publisher
                            "sample_rate": 24000,
                            "channels":   1,
                            "bit_depth":  16,
                        }
                    })

                # ── TRANSCRIPT CHUNK ─────────────────────────────────────
                # Text of what the agent just said (from transcription).
                # Stream this to the UI word by word.
                if response.text:
                    full_transcript += response.text
                    await self.publish({
                        "event_type": "agent_speaking_chunk",
                        "payload": {
                            "agent_id":        self.agent_id,
                            "transcript_chunk": response.text,
                        }
                    })

            # ── TURN COMPLETE ────────────────────────────────────────────
            # Gemini finished speaking. Now process the full turn.
            if full_transcript:
                await self._on_turn_complete(full_transcript)

            # If interrupted (Chairman barged in), clear everything
            await self._clear_queues_on_interrupt()
```

---

### 1.5 — What Happens After Each Turn (No Memory Leakage)

```python
    async def _on_turn_complete(self, transcript: str):
        """
        Called after agent finishes speaking.
        Updates ONLY this agent's own data — never touches others.
        """

        # 1. Update THIS agent's last_statement in SHARED state
        #    (only this one field is readable by other agents)
        await self.db.collection("crisis_sessions").document(
            self.session_id
        ).update({
            f"agent_roster_last_statement_{self.agent_id}": transcript[:200]
        })

        # 2. Append to THIS agent's private memory
        #    (ONLY this agent ever reads/writes this collection)
        await self.db.collection("agent_memory").document(
            f"{self.agent_id}_{self.session_id}"  # ← prefixed by agent_id
        ).update({
            "previous_statements": LocalArrayUnion([{
                "text":      transcript,
                "spoken_at": now_iso(),
            }])
        })

        # 3. Write to session_events (append-only log)
        #    Observer reads this to detect contradictions/alliances
        event_id = f"evt_{uuid4().hex[:8]}"
        await self.db.collection("session_events").document(
            self.session_id
        ).collection("events").document(event_id).set({
            "event_id":     event_id,
            "event_type":   "agent_speaking_end",
            "session_id":   self.session_id,
            "source_agent_id": self.agent_id,
            "timestamp":    now_iso(),
            "payload": {
                "agent_id":        self.agent_id,
                "character_name":  self.character_name,
                "full_transcript": transcript,
                "duration_seconds": 0,  # calculated from audio chunks
            }
        })

        # 4. Push WS event: speaking_end (stops waveform on frontend)
        await self.publish({
            "event_type": "agent_speaking_end",
            "payload": {
                "agent_id":        self.agent_id,
                "full_transcript": transcript,
            }
        })

        # 5. Observer Agent picks up the session_events write above
        #    and runs its analysis asynchronously — we don't call it here.
        #    Zero coupling between CrisisAgent and Observer.

        await self._set_status("listening")

    async def _clear_queues_on_interrupt(self):
        """
        Gemini sends turn_complete when interrupted.
        Clear pending audio — matches behavior from reference script.
        """
        while not self.audio_out_queue.empty():
            self.audio_out_queue.get_nowait()
        await self.publish({
            "event_type": "agent_interrupted",
            "payload": {"agent_id": self.agent_id}
        })
```

---

### 1.6 — Sending Chairman Audio TO an Agent

```python
    async def _send_audio_to_gemini(self):
        """
        Forwards chairman PCM audio chunks to THIS agent's session.
        Chairman audio only arrives here if this agent is targeted.
        Gateway ensures routing — we never see other agents' audio.
        """
        while self._running:
            chunk = await self.audio_in_queue.get()
            if self.live_session and chunk:
                await self.live_session.send(
                    input={"data": chunk, "mime_type": "audio/pcm"},
                )

    async def receive_chairman_audio(self, pcm_bytes: bytes):
        """
        Called by Gateway when Chairman targets this agent (or full room).
        Puts audio into THIS agent's queue only.

        ISOLATION: Gateway calls agent.receive_chairman_audio(chunk)
        only for the targeted agent. Other agents never get this chunk.
        """
        await self.audio_in_queue.put(pcm_bytes)

    async def receive_text_command(self, text: str):
        """
        Called by Gateway to inject Chairman text commands.
        Sends as a turn to Gemini Live — agent will respond in voice.
        """
        if self.live_session:
            await self.live_session.send(input=text, end_of_turn=True)
            await self._set_status("thinking")

    async def _autonomous_turn_trigger(self):
        """
        If no one speaks for 10 seconds, agents start talking on their own.
        This is what makes the room feel alive without the Chairman.
        Each agent has its own timer — they don't coordinate this.
        """
        while self._running:
            await asyncio.sleep(10)
            # Read shared board state
            board = await self._read_shared_board()
            # Ask Gemini to decide whether to speak
            prompt = f"""
[BOARD STATE: {board}]
[YOUR ROLE: {self.role_title}]
It has been 10 seconds of silence in the room.
Based on your SKILL.md and the current board state,
decide whether to speak. If yes, make your point.
If no, stay silent.
"""
            if self.live_session:
                await self.live_session.send(input=prompt, end_of_turn=True)
```

---

### 1.7 — The Gateway: Routing Audio Between Agents

```python
# war_room/gateway/voice_router.py

class VoiceRouter:
    """
    Manages ALL CrisisAgent instances for a session.
    Handles chairman audio routing — the only place agents
    could theoretically cross-contaminate audio.

    ISOLATION RULE: each agent's audio_in_queue is PRIVATE.
    VoiceRouter calls agent.receive_chairman_audio() only for the target.
    """

    def __init__(self, session_id: str):
        self.session_id = session_id
        self.agents: dict[str, CrisisAgent] = {}  # agent_id → CrisisAgent

    def register_agent(self, agent: CrisisAgent):
        # Each agent registered under its own agent_id
        self.agents[agent.agent_id] = agent

    async def route_chairman_audio(
        self,
        pcm_chunk: bytes,
        target_agent_id: str | None  # None = full room
    ):
        """
        Routes chairman audio to the correct agent(s).

        If target_agent_id is set:   only that agent gets the audio
        If target_agent_id is None:  all agents get it (full room address)

        CRITICAL: We loop over agents and call each one's method.
        We NEVER pass one agent's queue reference to another agent.
        """
        if target_agent_id:
            agent = self.agents.get(target_agent_id)
            if agent:
                await agent.receive_chairman_audio(pcm_chunk)
        else:
            # Full room — each agent gets it independently
            await asyncio.gather(*[
                agent.receive_chairman_audio(pcm_chunk)
                for agent in self.agents.values()
            ])

    async def broadcast_text(self, text: str, target_agent_id: str | None = None):
        """Inject text into one or all agent Live sessions."""
        if target_agent_id:
            agent = self.agents.get(target_agent_id)
            if agent:
                await agent.receive_text_command(text)
        else:
            await asyncio.gather(*[
                a.receive_text_command(text) for a in self.agents.values()
            ])

    async def dismiss_agent(self, agent_id: str):
        """Stop an agent's Live session cleanly."""
        agent = self.agents.get(agent_id)
        if agent:
            agent._running = False
            for task in agent._tasks:
                task.cancel()
            del self.agents[agent_id]
```

---

## PART 2 — WEBSOCKET: STREAMING AUDIO TO THE BROWSER

### 2.1 — The Gateway WebSocket Handlers

```python
# war_room/gateway/ws_handler.py

from fastapi import WebSocket, WebSocketDisconnect
import asyncio
import base64
import json

@app.websocket("/ws/{session_id}")
async def ws_event_stream(websocket: WebSocket, session_id: str, token: str):
    """
    Main event stream WebSocket.
    Sends ALL events including agent_audio_chunk.
    Frontend handles audio playback from here.
    """
    await websocket.accept()

    # Validate chairman_token
    if not await validate_token(session_id, token):
        await websocket.close(code=4001)
        return

    # Register this connection as the event listener for this session
    connection_registry[session_id] = websocket

    try:
        while True:
            # Receive messages from frontend (keepalive, commands)
            data = await websocket.receive_json()
            await handle_frontend_message(session_id, data)

    except WebSocketDisconnect:
        del connection_registry[session_id]


@app.websocket("/ws/{session_id}/audio")
async def ws_audio_stream(websocket: WebSocket, session_id: str, token: str):
    """
    Dedicated audio WebSocket for Chairman mic input.
    Receives raw PCM bytes from browser microphone.
    Routes to target agent via VoiceRouter.
    """
    await websocket.accept()

    if not await validate_audio_token(session_id, token):
        await websocket.close(code=4001)
        return

    router = get_voice_router(session_id)
    target_agent_id = None  # Will be updated by frontend messages

    try:
        while True:
            message = await websocket.receive()

            if message["type"] == "websocket.receive":

                # ── TEXT: control messages ────────────────────────────
                if "text" in message:
                    control = json.loads(message["text"])
                    if control.get("type") == "set_target":
                        target_agent_id = control.get("agent_id")  # None = full room
                    elif control.get("type") == "stop":
                        break

                # ── BYTES: raw PCM audio from chairman mic ────────────
                elif "bytes" in message:
                    pcm_chunk = message["bytes"]
                    # Route to the correct agent(s) — the only place
                    # audio routing logic lives. Isolated per agent.
                    await router.route_chairman_audio(pcm_chunk, target_agent_id)

    except WebSocketDisconnect:
        pass


async def publish_event(session_id: str, event: dict):
    """
    Called by all agents to push events to the frontend.
    Adds session context and serializes audio as base64.

    IMPORTANT: audio_b64 field is raw PCM bytes encoded as base64.
    Browser will decode this back to PCM for Web Audio API.
    """
    ws = connection_registry.get(session_id)
    if not ws:
        return

    # Encode audio bytes as base64 if present
    if "audio_b64" in event.get("payload", {}):
        raw_bytes = event["payload"]["audio_b64"]
        if isinstance(raw_bytes, bytes):
            event["payload"]["audio_b64"] = base64.b64encode(raw_bytes).decode()

    await ws.send_json({
        "event_id":   f"evt_{uuid4().hex[:6]}",
        "session_id": session_id,
        "event_type": event["event_type"],
        "timestamp":  now_iso(),
        "payload":    event["payload"],
    })
```

---

## PART 3 — FRONTEND: PLAYING AGENT VOICES IN THE BROWSER

This is the most important part. The browser receives raw PCM bytes
encoded as base64 strings. You must decode and play them using the
**Web Audio API** — NOT the `<audio>` element (which needs a file format).

### 3.1 — Understanding the Audio Format

```
What Gemini Live sends:    PCM 24kHz, 16-bit, mono (signed integers)
What your WS delivers:     Base64-encoded string of those raw bytes
What the browser needs:    AudioBuffer via AudioContext

The chain:
  base64 string
    → atob() → Uint8Array (raw bytes)
    → Int16Array (interpret as 16-bit signed integers)
    → Float32Array (convert to -1.0 to 1.0 range for Web Audio)
    → AudioContext.createBuffer()
    → AudioBufferSourceNode.start()
    → 🔊 Sound from speakers
```

### 3.2 — The AudioManager Class (JavaScript)

Create this once and reuse it for all agents.

```javascript
// lib/AudioManager.js

export class AudioManager {
  constructor() {
    // ONE AudioContext for the entire page.
    // Web Audio API requires user gesture to start — see Section 3.5.
    this.context       = null;
    this.nextPlayTime  = {};  // agent_id → next scheduled play time
    this.isInitialized = false;
  }

  /**
   * MUST be called from a user gesture (button click, etc.)
   * before any audio can play. Browser security requirement.
   */
  async initialize() {
    if (this.isInitialized) return;
    this.context = new (window.AudioContext || window.webkitAudioContext)({
      sampleRate: 24000   // Match Gemini's output rate exactly
    });
    this.isInitialized = true;
    console.log('[AudioManager] Initialized. Sample rate:', this.context.sampleRate);
  }

  /**
   * Called for every agent_audio_chunk WS event.
   * Decodes the base64 PCM and schedules it for seamless playback.
   *
   * @param {string} agentId    - e.g. "atlas_A3F9B2C1"
   * @param {string} audioB64   - base64-encoded raw PCM bytes from Gemini
   */
  async playChunk(agentId, audioB64) {
    if (!this.isInitialized || !this.context) {
      console.warn('[AudioManager] Not initialized. Call initialize() first.');
      return;
    }

    // ── STEP 1: Base64 → raw bytes ──────────────────────────────────────
    const binaryString = atob(audioB64);
    const rawBytes     = new Uint8Array(binaryString.length);
    for (let i = 0; i < binaryString.length; i++) {
      rawBytes[i] = binaryString.charCodeAt(i);
    }

    // ── STEP 2: Raw bytes → Int16Array (PCM 16-bit signed) ──────────────
    // PCM 16-bit = every 2 bytes is one sample, little-endian
    const pcm16 = new Int16Array(rawBytes.buffer);

    // ── STEP 3: Int16Array → Float32Array (-1.0 to 1.0) ─────────────────
    // Web Audio API uses float32. Divide by 32768 to normalize.
    const float32 = new Float32Array(pcm16.length);
    for (let i = 0; i < pcm16.length; i++) {
      float32[i] = pcm16[i] / 32768.0;
    }

    // ── STEP 4: Create AudioBuffer ───────────────────────────────────────
    const buffer = this.context.createBuffer(
      1,                    // channels: mono
      float32.length,       // number of samples
      24000                 // sample rate: must match Gemini (24kHz)
    );
    buffer.copyToChannel(float32, 0);  // copy samples into channel 0

    // ── STEP 5: Create source node and connect to output ─────────────────
    const source      = this.context.createBufferSource();
    source.buffer     = buffer;
    source.connect(this.context.destination);  // → speakers

    // ── STEP 6: Schedule seamless playback ───────────────────────────────
    // This is the key to smooth audio without gaps or glitches.
    // We schedule each chunk to start exactly where the previous one ended.
    const now          = this.context.currentTime;
    const lastEnd      = this.nextPlayTime[agentId] || now;
    const startTime    = Math.max(now, lastEnd);  // don't schedule in the past

    source.start(startTime);

    // Update the next available start time for this agent
    this.nextPlayTime[agentId] = startTime + buffer.duration;
  }

  /**
   * Called when agent_interrupted event arrives.
   * Stops playback immediately and resets the schedule for this agent.
   */
  stopAgent(agentId) {
    // Reset the schedule so next chunk plays immediately
    this.nextPlayTime[agentId] = this.context?.currentTime || 0;
    // Note: chunks already scheduled via source.start() will play out.
    // For immediate stop: you'd need to track source nodes — see Section 3.6.
  }

  /**
   * Called when session ends. Clean up AudioContext.
   */
  async destroy() {
    if (this.context) {
      await this.context.close();
      this.context       = null;
      this.nextPlayTime  = {};
      this.isInitialized = false;
    }
  }
}
```

---

### 3.3 — The WebSocket Handler (React / JavaScript)

```javascript
// lib/useWarRoomSocket.js

import { useEffect, useRef, useCallback } from 'react';
import { AudioManager } from './AudioManager';
import { useSessionStore } from './store';  // your Zustand store

export function useWarRoomSocket(sessionId, chairmanToken) {
  const wsRef           = useRef(null);
  const audioManagerRef = useRef(new AudioManager());
  const updateStore     = useSessionStore(s => s.handleEvent);

  const connect = useCallback(async () => {
    const ws = new WebSocket(
      `wss://your-api/ws/${sessionId}?token=${chairmanToken}`
    );
    wsRef.current = ws;

    ws.onopen = () => {
      console.log('[WS] Connected to event stream');
      // Send keepalive every 25 seconds
      setInterval(() => ws.send(JSON.stringify({ type: 'ping' })), 25000);
    };

    ws.onmessage = async (event) => {
      const msg = JSON.parse(event.data);

      // ── AUDIO EVENT: play the chunk ─────────────────────────────────
      // This is the money line. Every time an agent speaks,
      // you get one of these events with audio_b64 in the payload.
      if (msg.event_type === 'agent_audio_chunk') {
        await audioManagerRef.current.playChunk(
          msg.payload.agent_id,
          msg.payload.audio_b64  // base64 PCM 24kHz 16-bit mono
        );
        return;  // Don't also process in store — audio-only event
      }

      // ── INTERRUPTED: stop audio ──────────────────────────────────────
      if (msg.event_type === 'agent_interrupted') {
        audioManagerRef.current.stopAgent(msg.payload.agent_id);
      }

      // ── ALL OTHER EVENTS: update UI state ────────────────────────────
      updateStore(msg);
    };

    ws.onerror = (err) => console.error('[WS] Error:', err);

    ws.onclose = () => {
      console.log('[WS] Disconnected — attempting reconnect in 2s');
      setTimeout(connect, 2000);
    };
  }, [sessionId, chairmanToken]);

  useEffect(() => {
    connect();
    return () => {
      wsRef.current?.close();
      audioManagerRef.current.destroy();
    };
  }, [connect]);

  return wsRef;
}
```

---

### 3.4 — Zustand Store: Handling Every Event Type

```javascript
// lib/store.js

import { create } from 'zustand';

export const useSessionStore = create((set, get) => ({
  // ── State ────────────────────────────────────────────────────────────
  agents:          {},   // agent_id → { status, trustScore, lastStatement, ... }
  boardDecisions:  [],
  boardConflicts:  [],
  boardIntel:      [],
  insights:        [],
  trustScores:     {},
  posture:         { publicExposure: 0, legalExposure: 0, internalStability: 100 },
  score:           { value: 50, label: 'RECOVERING', trend: 'stable' },
  feedItems:       [],
  threatLevel:     'contained',
  transcripts:     {},   // agent_id → current transcript being typed

  // ── Master event handler ──────────────────────────────────────────────
  handleEvent: (event) => {
    const { event_type, payload } = event;

    switch (event_type) {

      // ── AGENT STATUS ────────────────────────────────────────────────
      case 'agent_status_change':
        set(s => ({
          agents: {
            ...s.agents,
            [payload.agent_id]: {
              ...s.agents[payload.agent_id],
              status: payload.status,
            }
          }
        }));
        break;

      case 'agent_speaking_start':
        set(s => ({
          agents: {
            ...s.agents,
            [payload.agent_id]: { ...s.agents[payload.agent_id], status: 'speaking' }
          },
          transcripts: { ...s.transcripts, [payload.agent_id]: '' }
        }));
        break;

      // ── STREAMING TRANSCRIPT (word by word) ─────────────────────────
      case 'agent_speaking_chunk':
        set(s => ({
          transcripts: {
            ...s.transcripts,
            [payload.agent_id]: (s.transcripts[payload.agent_id] || '') + payload.transcript_chunk
          }
        }));
        break;

      case 'agent_speaking_end':
        set(s => ({
          agents: {
            ...s.agents,
            [payload.agent_id]: {
              ...s.agents[payload.agent_id],
              status:        'listening',
              lastStatement: payload.full_transcript,
            }
          },
          transcripts: { ...s.transcripts, [payload.agent_id]: '' }
        }));
        break;

      case 'agent_thinking':
        set(s => ({
          agents: {
            ...s.agents,
            [payload.agent_id]: { ...s.agents[payload.agent_id], status: 'thinking' }
          }
        }));
        break;

      case 'agent_interrupted':
        set(s => ({
          agents: {
            ...s.agents,
            [payload.agent_id]: { ...s.agents[payload.agent_id], status: 'listening' }
          },
          transcripts: { ...s.transcripts, [payload.agent_id]: '' }
        }));
        break;

      // ── CRISIS BOARD ─────────────────────────────────────────────────
      case 'decision_agreed':
        set(s => ({ boardDecisions: [payload, ...s.boardDecisions] }));
        break;

      case 'conflict_opened':
        set(s => ({ boardConflicts: [payload, ...s.boardConflicts] }));
        break;

      case 'conflict_resolved':
        set(s => ({
          boardConflicts: s.boardConflicts.map(c =>
            c.conflict_id === payload.conflict_id ? { ...c, resolution: payload.resolution } : c
          )
        }));
        break;

      case 'intel_dropped':
        set(s => ({ boardIntel: [payload, ...s.boardIntel] }));
        break;

      // ── ROOM INTELLIGENCE ────────────────────────────────────────────
      case 'observer_insight':
        set(s => ({ insights: [payload, ...s.insights].slice(0, 20) }));
        break;

      case 'trust_score_update':
        set(s => ({
          trustScores: { ...s.trustScores, [payload.agent_id]: payload.score },
          agents: {
            ...s.agents,
            [payload.agent_id]: {
              ...s.agents[payload.agent_id],
              trustScore: payload.score,
              trustDelta: payload.delta,
              trustReason: payload.reason,
            }
          }
        }));
        break;

      // ── POSTURE + SCORE ──────────────────────────────────────────────
      case 'posture_update':
        set({ posture: payload });
        break;

      case 'score_update':
        set({ score: { value: payload.score, label: payload.label, trend: payload.trend } });
        break;

      case 'threat_level_change':
        set({ threatLevel: payload.current });
        break;

      // ── FEED ─────────────────────────────────────────────────────────
      case 'feed_item':
        set(s => ({ feedItems: [payload, ...s.feedItems].slice(0, 100) }));
        break;

      default:
        // Unknown events ignored — future-safe
        break;
    }
  }
}));
```

---

### 3.5 — The Chairman Microphone (Sending Voice TO Agents)

```javascript
// components/ChairmanMic.jsx

import { useRef, useState, useCallback } from 'react';

const SAMPLE_RATE = 16000;   // Must match backend SEND_SAMPLE_RATE
const CHUNK_SIZE  = 1024;    // Matches reference script CHUNK_SIZE

export function ChairmanMic({ sessionId, audioToken, targetAgentId }) {
  const wsRef          = useRef(null);
  const processorRef   = useRef(null);
  const audioCtxRef    = useRef(null);
  const [recording, setRecording] = useState(false);

  const startRecording = useCallback(async () => {
    // ── STEP 1: Initialize AudioContext (user gesture = this click) ───
    // This is also the moment you should call audioManager.initialize()
    // for playback. Both need a user gesture to unlock.
    audioCtxRef.current = new AudioContext({ sampleRate: SAMPLE_RATE });

    // ── STEP 2: Get microphone access ─────────────────────────────────
    const stream = await navigator.mediaDevices.getUserMedia({
      audio: {
        sampleRate: SAMPLE_RATE,
        channelCount: 1,
        echoCancellation: true,   // Important: prevents feedback loops
        noiseSuppression: true,
        autoGainControl: true,
      }
    });

    // ── STEP 3: Open the audio WebSocket ──────────────────────────────
    wsRef.current = new WebSocket(
      `wss://your-api/ws/${sessionId}/audio?token=${audioToken}`
    );
    await new Promise(r => wsRef.current.onopen = r);

    // Tell the server who to route this audio to
    wsRef.current.send(JSON.stringify({
      type:     'set_target',
      agent_id: targetAgentId  // null = full room
    }));

    // ── STEP 4: Process mic audio with ScriptProcessor ────────────────
    // ScriptProcessorNode is deprecated but still the most compatible.
    // For modern browsers you can use AudioWorklet instead.
    const source    = audioCtxRef.current.createMediaStreamSource(stream);
    const processor = audioCtxRef.current.createScriptProcessor(CHUNK_SIZE, 1, 1);
    processorRef.current = processor;

    processor.onaudioprocess = (e) => {
      if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) return;

      // ── STEP 5: Convert Float32 mic audio to Int16 PCM ───────────────
      // Browser gives us float32 (-1.0 to 1.0)
      // Gemini wants int16 PCM 16kHz
      const float32 = e.inputBuffer.getChannelData(0);
      const int16   = new Int16Array(float32.length);
      for (let i = 0; i < float32.length; i++) {
        const s    = Math.max(-1, Math.min(1, float32[i]));
        int16[i]   = s < 0 ? s * 32768 : s * 32767;
      }

      // ── STEP 6: Send raw bytes to backend ───────────────────────────
      wsRef.current.send(int16.buffer);
    };

    source.connect(processor);
    processor.connect(audioCtxRef.current.destination);

    setRecording(true);
  }, [sessionId, audioToken, targetAgentId]);

  const stopRecording = useCallback(() => {
    processorRef.current?.disconnect();
    wsRef.current?.close();
    audioCtxRef.current?.close();
    setRecording(false);
  }, []);

  // Hold-to-talk: matches the design spec
  return (
    <button
      onMouseDown={startRecording}
      onMouseUp={stopRecording}
      onTouchStart={startRecording}
      onTouchEnd={stopRecording}
      style={{ /* your mic button styles */ }}
    >
      {recording ? '🔴 RECORDING' : '🎙 HOLD TO SPEAK'}
    </button>
  );
}
```

---

### 3.6 — Immediate Interrupt (Advanced)

When the Chairman interrupts an agent mid-sentence, you need to stop
the audio immediately — not just reset the schedule.

```javascript
// Add this to AudioManager class

constructor() {
  // ... existing code ...
  this.activeSources = {};  // agent_id → AudioBufferSourceNode[]
}

async playChunk(agentId, audioB64) {
  // ... decoding code (same as before) ...

  const source = this.context.createBufferSource();
  source.buffer = buffer;
  source.connect(this.context.destination);
  source.start(startTime);

  // ── TRACK THE SOURCE NODE ────────────────────────────────────────────
  if (!this.activeSources[agentId]) this.activeSources[agentId] = [];
  this.activeSources[agentId].push(source);

  // Clean up when it finishes playing naturally
  source.onended = () => {
    this.activeSources[agentId] = this.activeSources[agentId].filter(s => s !== source);
  };

  this.nextPlayTime[agentId] = startTime + buffer.duration;
}

stopAgent(agentId) {
  // ── STOP ALL PENDING AUDIO FOR THIS AGENT ────────────────────────────
  const sources = this.activeSources[agentId] || [];
  sources.forEach(source => {
    try { source.stop(); } catch(e) { /* already stopped */ }
  });
  this.activeSources[agentId] = [];
  this.nextPlayTime[agentId]  = this.context?.currentTime || 0;
}
```

---

## PART 4 — WIRING IT ALL TOGETHER

### 4.1 — Session Boot Sequence (Backend)

```python
# war_room/session_bootstrapper.py

async def bootstrap_session(session_id: str, scenario: dict, db, event_publisher):
    """
    Called once after Scenario Analyst generates the scenario.
    Boots all agents in parallel. Each gets isolated resources.
    """
    agents     = {}
    router     = VoiceRouter(session_id)

    # ── Boot all agents SIMULTANEOUSLY ───────────────────────────────────
    async def boot_single_agent(agent_config: dict) -> CrisisAgent:
        agent_id = agent_config["agent_id"]

        # Read the pre-generated SKILL.md from Firestore
        skill_doc = await db.collection("agent_skills").document(
            f"{session_id}_{agent_id}"
        ).get()
        skill_md = skill_doc.to_dict()["skill_md"]

        # Create the agent instance
        # ISOLATION CHECK: each instance has its own queues and session
        agent = CrisisAgent(
            agent_id       = agent_id,
            session_id     = session_id,
            character_name = agent_config["character_name"],
            role_title     = agent_config["role_title"],
            voice_name     = agent_config["voice_name"],  # unique per agent
            skill_md       = skill_md,
            db             = db,
            event_publisher= lambda evt: event_publisher(session_id, evt),
        )

        router.register_agent(agent)

        # Signal frontend: this agent is assembling
        await event_publisher(session_id, {
            "event_type": "agent_assembling",
            "payload": {
                "agent_id":       agent_id,
                "character_name": agent_config["character_name"],
                "role_title":     agent_config["role_title"],
                "voice_name":     agent_config["voice_name"],
                "identity_color": agent_config["identity_color"],
                "defining_line":  agent_config["defining_line"],
            }
        })

        return agent

    # Boot all agents in parallel (5 simultaneous Live connections)
    agent_instances = await asyncio.gather(*[
        boot_single_agent(cfg)
        for cfg in scenario["agents"]
    ])

    # Start all agent Live sessions (opens Gemini WebSocket per agent)
    # These run as background tasks — they don't block
    for agent in agent_instances:
        agents[agent.agent_id] = agent
        asyncio.create_task(agent.start())

    # Wait for all voice sessions to confirm active
    await asyncio.gather(*[
        wait_for_voice_active(agent, db) for agent in agent_instances
    ])

    # Signal frontend: war room is ready
    await event_publisher(session_id, {
        "event_type": "session_ready",
        "payload": {
            "crisis_title": scenario["crisis_title"],
            "agent_count":  len(agent_instances),
        }
    })

    return agents, router
```

---

### 4.2 — Frontend Startup Sequence

```javascript
// pages/WarRoom.jsx

import { useEffect, useRef } from 'react';
import { AudioManager } from '../lib/AudioManager';
import { useWarRoomSocket } from '../lib/useWarRoomSocket';

export function WarRoom({ sessionId, chairmanToken }) {
  const audioManagerRef = useRef(new AudioManager());
  const hasInitAudio    = useRef(false);

  // ── 1. Connect WebSocket BEFORE any REST calls ────────────────────────
  const wsRef = useWarRoomSocket(sessionId, chairmanToken);

  // ── 2. Initial panel data loads (REST) ───────────────────────────────
  useEffect(() => {
    async function loadInitialData() {
      const [session, agents, board, pods, feed, intel, posture, score] =
        await Promise.all([
          fetch(`/api/sessions/${sessionId}`,          { headers: authHeaders }),
          fetch(`/api/sessions/${sessionId}/agents`,   { headers: authHeaders }),
          fetch(`/api/sessions/${sessionId}/board`,    { headers: authHeaders }),
          fetch(`/api/sessions/${sessionId}/pods`,     { headers: authHeaders }),
          fetch(`/api/sessions/${sessionId}/feed`,     { headers: authHeaders }),
          fetch(`/api/sessions/${sessionId}/intel`,    { headers: authHeaders }),
          fetch(`/api/sessions/${sessionId}/posture`,  { headers: authHeaders }),
          fetch(`/api/sessions/${sessionId}/score`,    { headers: authHeaders }),
        ]);
      // Hydrate store with initial data...
    }
    loadInitialData();
  }, [sessionId]);

  // ── 3. CRITICAL: Initialize AudioContext on first user gesture ────────
  // Browser blocks AudioContext creation until the user interacts.
  // The mic button's first press triggers this.
  const handleFirstInteraction = async () => {
    if (!hasInitAudio.current) {
      await audioManagerRef.current.initialize();
      hasInitAudio.current = true;
    }
  };

  return (
    <div onPointerDown={handleFirstInteraction}>
      {/* Your War Room UI */}
    </div>
  );
}
```

---

## PART 5 — VOICE NAMES REFERENCE

Assign voices based on each agent's `voice_style` from the Scenario Analyst.
No two agents in a session should share a voice.

```python
# war_room/agents/voice_assignment.py

VOICE_POOL = {
  "authoritative": ["Orus", "Schedar", "Charon"],
  "aggressive":    ["Fenrir", "Gacrux", "Rasalgethi"],
  "warm":          ["Aoede", "Leda", "Callirrhoe"],
  "analytical":    ["Algenib", "Alnilam", "Algieba"],
  "measured":      ["Kore", "Achird", "Iapetus"],
  "urgent":        ["Auva", "Erinome", "Enceladus"],
  "calm":          ["Despina", "Laomedeia", "Umbriel"],
  "intel":         ["Cipher", "Sadachbia", "Sadaltager"],
  "persuasive":    ["Puck", "Pulcherrima", "Vindemiatrix"],
  "neutral":       ["Zephyr", "Sulafat", "Zubenelgenubi"],
}

def assign_voices(agent_configs: list[dict]) -> dict:
    """
    Assigns a unique voice to each agent.
    No two agents get the same voice in a session.
    """
    used_voices = set()
    assignments = {}

    for agent in agent_configs:
        style  = agent.get("voice_style", "neutral")
        pool   = VOICE_POOL.get(style, VOICE_POOL["neutral"])
        # Find first available voice in this style's pool
        voice  = next((v for v in pool if v not in used_voices), None)
        # Fallback: any unused voice
        if not voice:
            all_voices = [v for vs in VOICE_POOL.values() for v in vs]
            voice = next((v for v in all_voices if v not in used_voices), "Zephyr")

        used_voices.add(voice)
        assignments[agent["agent_id"]] = voice

    return assignments  # { "atlas_A3F9B2C1": "Orus", "felix_A3F9B2C1": "Fenrir", ... }
```

---

## PART 6 — COMMON FAILURES AND FIXES

### Problem 1: No audio plays — complete silence

```
Cause:   AudioContext not initialized before first playChunk() call.
         Browser blocks it until a user gesture.

Fix:     Call audioManager.initialize() inside a button's onClick.
         The ChairmanMic startRecording() function does this.
         Add a "ENTER WAR ROOM" button that user must click first.
```

### Problem 2: Audio plays but it's choppy / has gaps

```
Cause:   Using audio.play() instead of scheduled AudioBufferSourceNode.
         Each chunk plays from context.currentTime, causing overlaps
         and gaps.

Fix:     The nextPlayTime[agentId] scheduling in Section 3.2 fixes this.
         Chunks chain together seamlessly: each one starts exactly
         when the previous one ends.

Check:   context.currentTime vs nextPlayTime difference.
         If nextPlayTime >> currentTime, you have a buffer build-up.
         Add: if (nextPlayTime[agentId] - now > 2.0) nextPlayTime[agentId] = now;
```

### Problem 3: Audio sample rate mismatch (chipmunk or slow voices)

```
Cause:   AudioContext created at default 44100Hz but playing
         Gemini's 24000Hz audio without resampling.

Fix:     Always create AudioContext with { sampleRate: 24000 }.
         See Section 3.2.
         Or: use createBuffer(1, length, 24000) — the sample rate
         argument in createBuffer overrides the context rate for that buffer.
```

### Problem 4: Agents hear each other (memory/audio leakage)

```
Cause A: VoiceRouter passing wrong agent's queue reference.
Fix A:   Log agentId in route_chairman_audio() and confirm
         only the intended agent's receive_chairman_audio() is called.

Cause B: All agents sharing one Gemini Live session.
Fix B:   Each CrisisAgent must call client.aio.live.connect() independently.
         Check: each agent has its own `self.live_session` object.
         They should never be the same object.

Cause C: Firestore writes going to wrong document.
Fix C:   All agent_memory writes use f"{self.agent_id}_{self.session_id}"
         as the document ID. Never just session_id.
```

### Problem 5: Echo feedback (chairman hears themselves)

```
Cause:   Browser microphone picks up speaker output from agents.

Fix:     Use { echoCancellation: true } in getUserMedia constraints.
         See Section 3.5 — it's already in the code.
         On mobile: use headphones.
```

### Problem 6: AudioContext suspended (iOS/Safari)

```
Cause:   iOS aggressively suspends AudioContext after creation.

Fix:     Add context.resume() call inside the gesture handler.
         
         async initialize() {
           this.context = new AudioContext({ sampleRate: 24000 });
           if (this.context.state === 'suspended') {
             await this.context.resume();
           }
         }
         
         Also add context.resume() at the start of playChunk()
         in case iOS suspended it between calls.
```

### Problem 7: Gemini Live session drops mid-session

```
Cause:   Long sessions can have the WebSocket connection reset.
         The asyncio context manager in agent.start() will exit.

Fix:     Wrap agent.start() in a retry loop:
         
         async def start_with_retry(self, max_retries=3):
             for attempt in range(max_retries):
                 try:
                     await self.start()
                 except Exception as e:
                     print(f"Agent {self.agent_id} session dropped: {e}")
                     if attempt < max_retries - 1:
                         await asyncio.sleep(2 ** attempt)  # backoff
                     else:
                         raise
```

---

## SUMMARY: THE EXACT ORDER TO BUILD THIS

```
BACKEND — do in this order:

  1. crisis_agent.py        — CrisisAgent class with _build_config()
                              Make sure voice_name is per-instance, not global
  2. voice_router.py        — VoiceRouter with route_chairman_audio()
                              Test: log which agent gets which audio chunk
  3. ws_handler.py          — WebSocket endpoints + publish_event()
                              Test: can you receive a ping from browser?
  4. session_bootstrapper   — Boot N agents in parallel
                              Test: all agents show "voice_session_active: true"

FRONTEND — do in this order:

  1. AudioManager.js        — The PCM decoder and scheduler
                              Test: call playChunk() with a hardcoded b64 PCM
  2. useWarRoomSocket.js    — WS connection + event routing
                              Test: log every event_type you receive
  3. Zustand store          — handleEvent() switch statement
                              Test: agent status changes update UI
  4. ChairmanMic.jsx        — Mic capture + PCM conversion + WS send
                              Test: speak and verify pcm bytes arrive at backend
  5. Wire AudioManager into
     useWarRoomSocket        — Call playChunk on agent_audio_chunk events
                              Test: speak to an agent, hear it respond

THE MOMENT IT WORKS:
  You speak → bytes flow → Gemini processes → audio returns →
  base64 arrives in browser → AudioManager plays it → you hear the agent.
  That loop should complete in 400–800ms from your last word.
```

---

*War Room Voice Pipeline Guide v1.0*
*Based on: google-genai Gemini Live API + Web Audio API*
*Memory isolation enforced at: VoiceRouter, CrisisAgent, Firestore doc IDs*