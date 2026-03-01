# ⚔️ WAR ROOM — Official Architecture Decision

## Framework: LiveKit Agents + Gemini Live

### Based on: <https://docs.livekit.io/agents/>

---

## WHY LIVEKIT WINS OVER PIPECAT FOR WAR ROOM

Both frameworks were read fully. Here is what the docs actually say.

### Pipecat — What it does well

Pipecat's pipeline model (`transport.input() → STT → LLM → TTS → transport.output()`) is
excellent for **single-agent voice bots**. For multi-agent, it uses `ParallelPipeline` where
all branches feed into ONE `transport.output()`. You would have to build a custom
`AgentAudioGate` FrameProcessor yourself to route frames from the right agent.

Pipecat also offers Pipecat Flows for structured conversations, with context strategies
like `APPEND`, `RESET`, and `RESET_WITH_SUMMARY`. These are great for call center flows and
linear interview bots.

### LiveKit — Why it fits War Room exactly

LiveKit's `AgentSession` is designed from the ground up for **multi-persona, multi-handoff
voice workflows**. From their docs:

> "Agents are the core units of a voice AI workflow. They define the instructions, tools,
> and reasoning behavior that drive a conversation. An agent can transfer control to other
> agents when different logic or capabilities are required."

This is **exactly** War Room. Four agents. Different roles. Pass the floor. One speaker at a time.

| Feature                        | LiveKit                                  | Pipecat                              |
|-------------------------------|-------------------------------------------|--------------------------------------|
| Multi-agent handoffs          | ✅ Built-in (`session.update_agent()`)    | ❌ Manual (build yourself)           |
| One active speaker at a time  | ✅ By design (single AgentSession)        | ✅ Via single transport.output()     |
| Manual turn control           | ✅ `turn_detection="manual"`              | ❌ Not built-in                      |
| Different voice per agent     | ✅ Agent-level TTS plugin override        | ⚠️ Possible but complex              |
| Gemini Live support           | ✅ `google.beta.realtime.RealtimeModel`   | ✅ `GeminiMultimodalLiveLLMService`  |
| Conversation history          | ✅ `session.history` (automatic)          | ✅ Context aggregator                |
| Pass context between agents   | ✅ `chat_ctx` parameter in Agent()        | ✅ Context strategies                |
| Interruption API              | ✅ `session.interrupt()`                  | ✅ Via pipeline interruption         |
| `agent_state_changed` events  | ✅ listening/thinking/speaking/idle       | ❌ Must build manually               |
| Cloud deployment + observability | ✅ LiveKit Cloud (traces, transcripts)  | ✅ Pipecat Cloud                     |
| WebRTC transport              | ✅ Native (core of LiveKit)               | ✅ Via Daily.co                      |
| Chairman microphone input     | ✅ Room participant with mic track        | ✅ Via transport.input()             |

**LiveKit wins on the critical features:**

1. Manual turn control is a first-class API — the Orchestrator controls exactly when each agent speaks
2. Agent handoffs with `session.update_agent()` is the cleanest API for passing the floor
3. Different voice per agent via TTS plugin override is documented and simple
4. `session.history` contains the full shared conversation automatically
5. `chat_ctx` lets each new agent inherit the full conversation before speaking
6. `agent_state_changed` events map 1:1 to War Room UI pod states

---

## THE COMPLETE WAR ROOM ARCHITECTURE

### Core Concept: ONE AgentSession, N Agent Classes

```
War Room Session

  ONE AgentSession (the orchestrator/runtime)
    │
    ├── ActiveAgent: ATLAS     ← session controls this right now
    │     voice: "Charon"      ← Gemini Live voice
    │     instructions: ...    ← ATLAS persona + SKILL.md
    │
    │── (waiting): NOVA        ← not active, generates nothing
    │── (waiting): FELIX       ← not active, generates nothing
    │── (waiting): CIPHER      ← not active, generates nothing
    │
    └── session.history        ← all spoken turns, shared by all agents

  Chairman (human)
    └── Room participant with mic track
        └── session.commit_user_turn() to pass floor to Chairman
```

The `AgentSession` has ONE active agent. Other agents exist as Python class instances
but generate NO audio until `session.update_agent()` switches to them.
This is not a hack. This is exactly what LiveKit built it for.

---

## PART 1 — INSTALLATION & SETUP

```bash
# Core framework
pip install "livekit-agents[google,silero]>=1.0"

# Google plugin for Gemini Live
pip install "livekit-agents-plugin-google"

# VAD for interruption detection
pip install "livekit-agents-plugin-silero"

# Optional: turn detector model for natural endpointing
pip install "livekit-agents-plugin-turn-detector"
```

### Environment Variables

```bash
# .env
LIVEKIT_URL=wss://your-project.livekit.cloud
LIVEKIT_API_KEY=your_api_key
LIVEKIT_API_SECRET=your_api_secret
GOOGLE_API_KEY=your_gemini_api_key
```

---

## PART 2 — THE AGENT CLASSES

Each War Room agent is a subclass of `livekit.agents.Agent`.
They differ in: `instructions` (persona), `voice` (overridden TTS plugin).

```python
# war_room/agents/agent_personas.py

from livekit import agents
from livekit.agents import Agent, function_tool, RunContext
from livekit.plugins import google, silero
from dataclasses import dataclass, field
from typing import Optional
import json

# ─── SHARED SESSION STATE ────────────────────────────────────────────────────
# This is the "userdata" attached to AgentSession.
# All agents read and write to this. It IS the shared crisis board.

@dataclass
class WarRoomState:
    session_id:         str             = ""
    crisis_title:       str             = ""
    crisis_brief:       str             = ""
    turn_count:         int             = 0
    active_agent_id:    str             = ""
    
    # Crisis Board (shared)
    agreed_decisions:   list            = field(default_factory=list)
    open_conflicts:     list            = field(default_factory=list)
    critical_intel:     list            = field(default_factory=list)
    
    # All agents in the room (for prompt context)
    agents_roster:      list            = field(default_factory=list)
    
    # Event publisher (set at boot)
    publish_fn:         Optional[any]   = None

    def publish(self, event_type: str, payload: dict):
        if self.publish_fn:
            import asyncio
            asyncio.create_task(self.publish_fn(event_type, payload))

    def board_summary(self) -> str:
        return json.dumps({
            "agreed_decisions": self.agreed_decisions,
            "open_conflicts":   self.open_conflicts,
            "critical_intel":   self.critical_intel,
        }, indent=2)


# ─── BASE WAR ROOM AGENT ─────────────────────────────────────────────────────

class WarRoomAgent(Agent):
    """
    Base class for all War Room agents.
    Each agent overrides: character_name, role_title, voice_name, base_persona.
    """
    
    character_name: str = "Agent"
    role_title:     str = "Analyst"
    voice_name:     str = "Charon"      # Gemini Live voice
    agent_id:       str = "base"
    
    def __init__(self, state: WarRoomState, chat_ctx=None):
        """
        chat_ctx: pass the accumulated conversation history from the previous
        agent so this agent inherits all context before speaking.
        """
        super().__init__(
            instructions = self._build_instructions(state),
            chat_ctx     = chat_ctx,   # ← Full conversation memory passed in
        )
        self.state = state
    
    def _build_instructions(self, state: WarRoomState) -> str:
        """
        Full persona injected before every agent turn.
        Includes the entire crisis context.
        """
        return f"""
You are {self.character_name}, {self.role_title} in an AI crisis management room.

[CRISIS]: {state.crisis_title}
[BRIEF]: {state.crisis_brief}

[AGENTS IN THIS ROOM]:
{chr(10).join([f"- {a['name']} ({a['role']})" for a in state.agents_roster])}

[CURRENT BOARD STATE]:
{state.board_summary()}

[YOUR PERSONA]:
{self.base_persona}

[SPEAKING RULES]:
- You speak in character as {self.character_name} at all times.
- You are aware of the full conversation history above.
- When you finish speaking, end your statement naturally.
  The room will know you are done when you stop talking.
- Use your tools (write_decision, write_conflict, drop_intel) during your turn
  to record important points on the board.
- Do NOT pretend other agents are speaking. Only speak as yourself.
- Be direct, specific, and in character.
"""
    
    # ─── SHARED TOOLS (available to all agents) ────────────────────────────
    
    @function_tool
    async def write_agreed_decision(
        self,
        context: RunContext,
        decision_text: str,
        confidence: str = "high"
    ) -> str:
        """Record an agreed decision on the crisis board."""
        entry = {
            "text":      decision_text,
            "by":        self.character_name,
            "turn":      self.state.turn_count,
            "confidence": confidence,
        }
        self.state.agreed_decisions.append(entry)
        self.state.publish("decision_agreed", {"decision": entry})
        return f"Decision recorded: {decision_text}"
    
    @function_tool
    async def write_open_conflict(
        self,
        context: RunContext,
        description:    str,
        agent_a:        str,
        agent_b:        str,
    ) -> str:
        """Record an open conflict between agents on the crisis board."""
        entry = {
            "description": description,
            "agent_a":     agent_a,
            "agent_b":     agent_b,
            "opened_by":   self.character_name,
            "turn":        self.state.turn_count,
        }
        self.state.open_conflicts.append(entry)
        self.state.publish("conflict_opened", {"conflict": entry})
        return f"Conflict recorded between {agent_a} and {agent_b}"
    
    @function_tool
    async def drop_intel(
        self,
        context: RunContext,
        intel_text: str,
        urgency: str = "medium"
    ) -> str:
        """Drop critical intelligence on the crisis board."""
        entry = {
            "text":    intel_text,
            "by":      self.character_name,
            "turn":    self.state.turn_count,
            "urgency": urgency,
        }
        self.state.critical_intel.append(entry)
        self.state.publish("intel_dropped", {"intel": entry})
        return f"Intel recorded: {intel_text}"

    async def on_enter(self):
        """
        Called by LiveKit when this agent becomes active.
        Triggers the first speech for this agent's turn.
        """
        self.state.active_agent_id = self.agent_id
        self.state.turn_count     += 1
        
        # Notify frontend: this agent has the floor
        self.state.publish("turn_started", {
            "agent_id":   self.agent_id,
            "turn_count": self.state.turn_count,
        })
        
        # Generate this agent's reply (this is where the voice comes out)
        await self.session.generate_reply(
            allow_interruptions = False   # Other agents don't interrupt mid-turn
        )
    
    async def on_exit(self):
        """Called by LiveKit when this agent hands off to another."""
        self.state.publish("turn_ended", {
            "agent_id": self.agent_id,
        })
    
    @property
    def base_persona(self) -> str:
        """Override in subclasses."""
        return "You are a crisis analyst."


# ─── CONCRETE AGENT CLASSES ──────────────────────────────────────────────────
# These are generated dynamically by the ScenarioAnalyst.
# For now, here are example fixed personas.
# In production, these are created at runtime with AI-generated personas.

class AtlasAgent(WarRoomAgent):
    character_name = "ATLAS"
    role_title     = "Strategic Operations Lead"
    voice_name     = "Charon"
    agent_id       = "atlas"
    
    @property
    def base_persona(self):
        return """
You are ATLAS. You think in systems and second-order effects.
Your job: ensure the group doesn't commit to a path without pressure-testing it.
You are skeptical of consensus, demand evidence, and push for actionable plans.
You often challenge other agents when their reasoning is sloppy.
"""


class NovaAgent(WarRoomAgent):
    character_name = "NOVA"
    role_title     = "Intelligence & Threat Assessment"
    voice_name     = "Fenrir"
    agent_id       = "nova"
    
    @property
    def base_persona(self):
        return """
You are NOVA. You live in the data. You read threat patterns others miss.
Your job: surface intel, quantify risk, flag what the group is ignoring.
You are precise, slightly clinical, and interrupt when you see a threat being dismissed.
"""


class FelixAgent(WarRoomAgent):
    character_name = "FELIX"
    role_title     = "Political & Legal Liaison"
    voice_name     = "Aoede"
    agent_id       = "felix"
    
    @property
    def base_persona(self):
        return """
You are FELIX. You understand what's politically possible vs legally dangerous.
Your job: identify the downstream consequences of every proposed action.
You are pragmatic, occasionally frustrated by idealism, and always aware of optics.
"""


class CipherAgent(WarRoomAgent):
    character_name = "CIPHER"
    role_title     = "Cyber & Technical Operations"
    voice_name     = "Kore"
    agent_id       = "cipher"
    
    @property
    def base_persona(self):
        return """
You are CIPHER. You operate in technical reality, not theory.
Your job: validate what's technically feasible, identify attack vectors, recommend countermeasures.
You are blunt, unimpressed by non-technical hand-waving, and speak in specifics.
"""
```

---

## PART 3 — THE ORCHESTRATOR

This is the brain. It controls who speaks and when.
It runs the introduction sequence, then drives autonomous turns.

```python
# war_room/orchestrator.py

import asyncio
from livekit import agents, rtc
from livekit.agents import AgentSession, JobContext
from livekit.plugins import google, silero

from .agents.agent_personas import (
    WarRoomAgent, WarRoomState,
    AtlasAgent, NovaAgent, FelixAgent, CipherAgent
)

class WarRoomOrchestrator:
    """
    Controls the War Room conversation flow.
    
    ONE AgentSession. N Agent class instances.
    Only the ACTIVE agent speaks. The session has exactly one active agent
    at any moment. Others generate nothing — they don't even have a session.
    
    This is the correct architecture per LiveKit docs:
    https://docs.livekit.io/agents/logic/agents-handoffs/
    """
    
    def __init__(
        self,
        session:    AgentSession,
        state:      WarRoomState,
        agents:     list[WarRoomAgent],
        ctx:        JobContext,
    ):
        self.session    = session
        self.state      = state
        self.agents     = agents         # List of agent instances (in intro order)
        self.ctx        = ctx
        self._running   = False
        self._agent_map = {a.agent_id: a for a in agents}
    
    async def run(self):
        """
        Entry point. Called after session is started.
        Runs introductions → autonomous turns.
        """
        self._running = True
        
        # 1. Introduction sequence
        await self._run_introductions()
        
        # 2. Autonomous crisis discussion
        await self._run_crisis_discussion()
    
    async def _run_introductions(self):
        """
        Each agent introduces themselves, one at a time, in order.
        Uses session.update_agent() to hand control to each agent.
        Each agent's on_enter() fires generate_reply() automatically.
        """
        for agent in self.agents:
            # Pass cumulative conversation history to this agent
            # so they know what previous agents said before them
            agent_with_context = type(agent)(
                state    = self.state,
                chat_ctx = self.session.history.copy()  # ← LiveKit built-in history
            )
            
            # Give this agent the floor
            # LiveKit: only ONE agent is active. Others generate nothing.
            await self.session.update_agent(agent_with_context)
            
            # Wait for this agent to finish speaking
            # listen for agent_state_changed → "listening" (done speaking)
            await self._wait_for_agent_done()
            
            # Natural pause between speakers
            await asyncio.sleep(1.0)
    
    async def _run_crisis_discussion(self):
        """
        Autonomous turns. Orchestrator picks the next speaker.
        Each agent speaks once per turn, then the next is selected.
        """
        while self._running:
            # Pick next speaker
            next_agent_id = await self._pick_next_speaker()
            next_agent    = self._agent_map.get(next_agent_id)
            
            if not next_agent:
                # Fallback: round-robin
                next_agent = self.agents[self.state.turn_count % len(self.agents)]
            
            # Rebuild agent with full current conversation context
            agent_with_context = type(next_agent)(
                state    = self.state,
                chat_ctx = self.session.history.copy()  # Full history injected
            )
            
            # Hand the floor to this agent
            await self.session.update_agent(agent_with_context)
            
            # Wait for turn to complete
            await self._wait_for_agent_done()
            
            # Pause between turns
            await asyncio.sleep(1.2)
    
    async def _wait_for_agent_done(self, timeout: float = 45.0):
        """
        Wait until the active agent transitions from 'speaking' to 'listening'.
        LiveKit fires agent_state_changed events automatically.
        
        States: initializing → listening → thinking → speaking → listening
        We wait for the full cycle to complete (back to 'listening').
        """
        # Track state transitions
        done = asyncio.Event()
        
        @self.session.on("agent_state_changed")
        def on_state_change(ev):
            # Agent finished speaking when it returns to 'listening'
            if ev.new_state == "listening":
                done.set()
        
        try:
            await asyncio.wait_for(done.wait(), timeout=timeout)
        except asyncio.TimeoutError:
            pass
        finally:
            # Cleanup listener
            self.session.off("agent_state_changed", on_state_change)
    
    async def _pick_next_speaker(self) -> str:
        """
        Ask Gemini (text, not voice) who should speak next.
        Falls back to round-robin if it fails.
        """
        from google import genai
        
        # Get last 5 turns from session history
        recent = self._format_recent_history(last_n=5)
        
        agent_options = "\n".join([
            f"- {a.agent_id}: {a.character_name} ({a.role_title})"
            for a in self.agents
        ])
        
        prompt = f"""
You are managing a crisis room debate.

Recent conversation:
{recent}

Available agents:
{agent_options}

Who should speak NEXT for the most natural, productive conversation?
Consider: who hasn't spoken recently, who has the most relevant perspective.

Reply with ONLY the agent_id. One word. Nothing else.
"""
        try:
            client = genai.Client()
            result = await client.aio.models.generate_content(
                model    = "gemini-2.0-flash",
                contents = prompt
            )
            return result.text.strip()
        except Exception:
            return self.agents[self.state.turn_count % len(self.agents)].agent_id
    
    def _format_recent_history(self, last_n: int = 5) -> str:
        """Format the last N messages from session.history for the prompt."""
        history = self.session.history
        recent  = list(history.messages)[-last_n*2:]  # *2 for user+assistant pairs
        lines   = []
        for msg in recent:
            role    = "AGENT" if msg.role == "assistant" else "USER"
            content = msg.content if isinstance(msg.content, str) else str(msg.content)
            lines.append(f"{role}: {content[:200]}")
        return "\n".join(lines)
    
    # ─── CHAIRMAN CONTROLS ────────────────────────────────────────────────────
    
    async def chairman_interrupt(self):
        """
        Chairman interrupts the current speaker.
        LiveKit docs: session.interrupt() stops current speech.
        """
        self.session.interrupt()
        self.state.publish("agent_interrupted", {
            "agent_id":       self.state.active_agent_id,
            "interrupted_by": "chairman",
        })
    
    async def chairman_direct_to_agent(self, agent_id: str, message: str):
        """
        Chairman addresses a specific agent.
        That agent becomes active and responds.
        """
        target = self._agent_map.get(agent_id)
        if not target:
            return
        
        # Build agent with context
        agent_with_context = type(target)(
            state    = self.state,
            chat_ctx = self.session.history.copy()
        )
        
        # Update the session to use this agent
        await self.session.update_agent(agent_with_context)
        
        # Commit the chairman's message as user input
        # This triggers the agent to respond to it specifically
        await self.session.generate_reply(
            instructions = f"Respond to this direct message from the Chairman: '{message}'"
        )
    
    async def force_vote(self, question: str):
        """
        Each agent votes YES/NO sequentially.
        Results published to frontend.
        """
        results = []
        
        for agent in self.agents:
            vote_agent = type(agent)(
                state    = self.state,
                chat_ctx = self.session.history.copy()
            )
            
            await self.session.update_agent(vote_agent)
            
            await self.session.generate_reply(
                instructions = f"""
The Chairman calls for a vote: "{question}"

State your position clearly:
1. YES or NO (your vote)
2. One sentence: why

Be definitive. Be brief.
""",
                allow_interruptions = False
            )
            
            await self._wait_for_agent_done()
            
            # Extract vote from last message in history
            last_msg = list(self.session.history.messages)[-1]
            results.append({
                "agent_id":         agent.agent_id,
                "character_name":   agent.character_name,
                "response":         str(last_msg.content)[:200],
            })
        
        self.state.publish("vote_result", {"results": results})
```

---

## PART 4 — SESSION ENTRYPOINT

This is the FastAPI + LiveKit entry point.
One room = one war room session.

```python
# war_room/entrypoint.py

import asyncio
from livekit import agents, rtc
from livekit.agents import AgentSession, JobContext, AgentServer, cli
from livekit.plugins import google, silero

from .agents.agent_personas import WarRoomState, AtlasAgent, NovaAgent, FelixAgent, CipherAgent
from .orchestrator import WarRoomOrchestrator

# ─── PREWARM ──────────────────────────────────────────────────────────────────
# Load VAD once at process start (reused across all sessions)

async def prewarm(proc: agents.JobProcess):
    proc.userdata["vad"] = await silero.VAD.load()


# ─── MAIN ENTRYPOINT ──────────────────────────────────────────────────────────

async def entrypoint(ctx: JobContext):
    """
    Called once per War Room session.
    A "room" in LiveKit = one War Room session.
    """
    # 1. Get crisis context from room metadata
    #    (sent by your FastAPI when creating the room)
    room_metadata  = ctx.room.metadata or "{}"
    crisis_data    = json.loads(room_metadata)
    
    crisis_title   = crisis_data.get("crisis_title", "Unknown Crisis")
    crisis_brief   = crisis_data.get("crisis_brief", "")
    scenario       = crisis_data.get("scenario", {})  # from ScenarioAnalyst
    
    # 2. Build shared state
    state = WarRoomState(
        session_id   = ctx.room.name,
        crisis_title = crisis_title,
        crisis_brief = crisis_brief,
        agents_roster = [
            {"name": "ATLAS",  "role": "Strategic Operations Lead"},
            {"name": "NOVA",   "role": "Intelligence & Threat Assessment"},
            {"name": "FELIX",  "role": "Political & Legal Liaison"},
            {"name": "CIPHER", "role": "Cyber & Technical Operations"},
        ]
    )
    
    # 3. Wire up Firestore event publisher
    # state.publish_fn = your_publish_function
    
    # 4. Build agent instances
    #    In production: these are generated from ScenarioAnalyst output
    agents_list = [
        AtlasAgent(state=state),
        NovaAgent(state=state),
        FelixAgent(state=state),
        CipherAgent(state=state),
    ]
    
    # 5. Build session with MANUAL turn detection
    #    manual = orchestrator controls exactly when each agent speaks
    #    No VAD triggers (agents don't respond to each other's voices)
    session = AgentSession[WarRoomState](
        llm = google.beta.realtime.RealtimeModel(
            model = "gemini-2.0-flash-exp",
            voice = agents_list[0].voice_name,  # Will be overridden per agent
        ),
        vad             = ctx.proc.userdata["vad"],
        turn_detection  = "manual",          # ← Orchestrator controls turns
        userdata        = state,
    )
    
    # 6. Connect to the room
    await ctx.connect()
    
    # 7. Start the session with the first agent
    await session.start(
        room  = ctx.room,
        agent = agents_list[0],
    )
    
    # 8. Create orchestrator and run the War Room
    orchestrator = WarRoomOrchestrator(
        session = session,
        state   = state,
        agents  = agents_list,
        ctx     = ctx,
    )
    
    # 9. Run intro sequence + autonomous turns
    #    This runs the entire war room conversation
    asyncio.create_task(orchestrator.run())
    
    # 10. Listen for chairman RPC calls from frontend
    await _register_chairman_rpc(ctx, orchestrator, session)


async def _register_chairman_rpc(
    ctx:          JobContext,
    orchestrator: WarRoomOrchestrator,
    session:      AgentSession
):
    """
    Register RPC methods that the Next.js frontend can call.
    These replace the HTTP endpoints for real-time chairman actions.
    """
    
    @ctx.room.local_participant.register_rpc_method("chairman.interrupt")
    async def rpc_interrupt(data: rtc.RpcInvocationData):
        await orchestrator.chairman_interrupt()
        return "ok"
    
    @ctx.room.local_participant.register_rpc_method("chairman.address_agent")
    async def rpc_address_agent(data: rtc.RpcInvocationData):
        payload   = json.loads(data.payload)
        agent_id  = payload["agent_id"]
        message   = payload["message"]
        await orchestrator.chairman_direct_to_agent(agent_id, message)
        return "ok"
    
    @ctx.room.local_participant.register_rpc_method("chairman.force_vote")
    async def rpc_vote(data: rtc.RpcInvocationData):
        payload   = json.loads(data.payload)
        question  = payload["question"]
        await orchestrator.force_vote(question)
        return "ok"
    
    @ctx.room.local_participant.register_rpc_method("chairman.hold_to_talk_start")
    async def rpc_hold_start(data: rtc.RpcInvocationData):
        # Stop current agent, enable chairman mic
        session.interrupt()
        session.input.set_audio_enabled(True)
        return "ok"
    
    @ctx.room.local_participant.register_rpc_method("chairman.hold_to_talk_end")
    async def rpc_hold_end(data: rtc.RpcInvocationData):
        # Commit chairman's spoken input → active agent responds
        session.input.set_audio_enabled(False)
        session.commit_user_turn()
        return "ok"


# ─── SERVER ENTRY ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import json
    
    server = AgentServer(
        entrypoint_fnc = entrypoint,
        prewarm_fnc    = prewarm,
    )
    cli.run_app(server)
```

---

## PART 5 — DIFFERENT VOICES PER AGENT

LiveKit's agent handoff system allows overriding the TTS/LLM plugin per agent.
For Gemini Live, the voice is a model parameter.

```python
# Each agent overrides the LLM plugin with their voice

class AtlasAgent(WarRoomAgent):
    voice_name = "Charon"
    
    async def on_enter(self):
        # Override the session's LLM with this agent's specific voice
        # LiveKit docs: override plugins in Agent constructor or on_enter
        self.session._llm = google.beta.realtime.RealtimeModel(
            model = "gemini-2.0-flash-exp",
            voice = self.voice_name,
        )
        await super().on_enter()


class NovaAgent(WarRoomAgent):
    voice_name = "Fenrir"
    
    async def on_enter(self):
        self.session._llm = google.beta.realtime.RealtimeModel(
            model = "gemini-2.0-flash-exp",
            voice = self.voice_name,
        )
        await super().on_enter()

# Gemini Live available voices (as of 2025):
# Charon, Puck, Kore, Fenrir, Aoede, Leda, Orus, Zephyr, Umbriel
```

---

## PART 6 — VOICE ISOLATION: WHY IT'S SOLVED BY DESIGN

With LiveKit's architecture:

```
Old broken approach:
  4 Gemini Live sessions open → all generate audio simultaneously

LiveKit approach:
  1 AgentSession → 1 active agent → 1 Gemini Live connection active
  session.update_agent(nova) → ATLAS connection goes idle → NOVA connection activates
  
  There is no "4 sessions running in parallel" to suppress.
  There is ONE session. ONE active model connection. ONE audio output.
  Voice isolation is architectural. Not a lock. Not a gate. Just design.
```

The `session.history` that is passed via `chat_ctx` is how agents remember everything.
NOVA reads everything ATLAS said before responding. This is memory. Built-in.

---

## PART 7 — FRONTEND: USING LIVEKIT CLIENT SDK

Replace raw WebSocket with LiveKit's official React SDK.

```bash
npm install @livekit/components-react livekit-client
```

```javascript
// components/WarRoom.jsx

import { LiveKitRoom, RoomAudioRenderer, useRoomContext } from '@livekit/components-react';

export function WarRoom({ livekitToken, livekitUrl }) {
  return (
    <LiveKitRoom
      token      = {livekitToken}
      serverUrl  = {livekitUrl}
      connect    = {true}
      audio      = {true}     // Enable chairman mic
      video      = {false}
    >
      <RoomAudioRenderer />   {/* Renders agent audio automatically */}
      <WarRoomInterface />
    </LiveKitRoom>
  );
}
```

```javascript
// hooks/useWarRoomEvents.js
// Listen to agent state changes from the LiveKit room

import { useRoomContext } from '@livekit/components-react';
import { useEffect } from 'react';
import { useSessionStore } from '../lib/store';

export function useWarRoomEvents() {
  const room        = useRoomContext();
  const handleEvent = useSessionStore(s => s.handleEvent);
  
  useEffect(() => {
    if (!room) return;
    
    // Agent state events come via LiveKit Data API / RPC
    const handleData = (payload, participant) => {
      const event = JSON.parse(new TextDecoder().decode(payload));
      handleEvent(event);
    };
    
    room.on('dataReceived', handleData);
    return () => room.off('dataReceived', handleData);
  }, [room]);
}
```

```javascript
// hooks/useChairmanControls.js
// Chairman RPC calls to the agent server

import { useRoomContext } from '@livekit/components-react';

export function useChairmanControls() {
  const room = useRoomContext();
  
  const interrupt = async () => {
    await room.localParticipant.performRpc({
      destinationIdentity: 'war-room-agent',
      method:              'chairman.interrupt',
      payload:             '{}',
    });
  };
  
  const holdToTalkStart = async () => {
    await room.localParticipant.performRpc({
      destinationIdentity: 'war-room-agent',
      method:              'chairman.hold_to_talk_start',
      payload:             '{}',
    });
  };
  
  const holdToTalkEnd = async () => {
    await room.localParticipant.performRpc({
      destinationIdentity: 'war-room-agent',
      method:              'chairman.hold_to_talk_end',
      payload:             '{}',
    });
  };
  
  const forceVote = async (question) => {
    await room.localParticipant.performRpc({
      destinationIdentity: 'war-room-agent',
      method:              'chairman.force_vote',
      payload:             JSON.stringify({ question }),
    });
  };
  
  const addressAgent = async (agentId, message) => {
    await room.localParticipant.performRpc({
      destinationIdentity: 'war-room-agent',
      method:              'chairman.address_agent',
      payload:             JSON.stringify({ agent_id: agentId, message }),
    });
  };
  
  return { interrupt, holdToTalkStart, holdToTalkEnd, forceVote, addressAgent };
}
```

---

## PART 8 — FASTAPI INTEGRATION

Your existing FastAPI backend creates LiveKit rooms and tokens.
The LiveKit Agent Server runs as a SEPARATE process.

```
Architecture:

  Next.js Frontend
       ↕ REST (session create, scenario fetch)
  FastAPI Backend
       ↕ LiveKit Server API (create rooms, generate tokens)
  LiveKit Cloud
       ↕ Agent dispatch (auto when room created)
  War Room Agent Server (war_room/entrypoint.py)
```

```python
# In your existing FastAPI backend

from livekit import api as livekit_api

@app.post("/api/sessions")
async def create_session(body: SessionCreate):
    lk = livekit_api.LiveKitAPI(
        url    = settings.LIVEKIT_URL,
        api_key    = settings.LIVEKIT_API_KEY,
        api_secret = settings.LIVEKIT_API_SECRET,
    )
    
    # 1. Generate scenario (your existing ScenarioAnalyst)
    scenario = await scenario_analyst.generate(body.crisis_input)
    
    # 2. Create LiveKit room with scenario embedded in metadata
    room = await lk.room.create_room(
        api.CreateRoomRequest(
            name     = f"war-room-{uuid4().hex[:8]}",
            metadata = json.dumps({
                "crisis_title": scenario["crisis_title"],
                "crisis_brief": scenario["crisis_brief"],
                "scenario":     scenario,
            })
        )
    )
    
    # 3. Generate a token for the Chairman (human user)
    token = (
        livekit_api.AccessToken(settings.LIVEKIT_API_KEY, settings.LIVEKIT_API_SECRET)
        .with_identity("chairman")
        .with_name("Chairman")
        .with_grants(livekit_api.VideoGrants(
            room_join  = True,
            room       = room.name,
            can_publish = True,    # Chairman can speak
        ))
        .to_jwt()
    )
    
    # 4. The LiveKit Agent Server auto-dispatches to the room
    #    (configured via LIVEKIT_DISPATCH_RULES in your agent server settings)
    
    return {
        "session_id":    room.name,
        "livekit_url":   settings.LIVEKIT_URL,
        "livekit_token": token,  # ← Frontend uses this to join the room
        "scenario":      scenario,
    }
```

---

## PART 9 — COMPLETE FILE STRUCTURE

```
war_room/
├── entrypoint.py              ← LiveKit agent entrypoint (run this separately)
├── orchestrator.py            ← WarRoomOrchestrator (controls turn flow)
├── agents/
│   ├── agent_personas.py      ← WarRoomAgent base + concrete personas + WarRoomState
│   └── dynamic_agent.py       ← Factory: creates Agent class from ScenarioAnalyst JSON
├── scenario/
│   └── analyst.py             ← ScenarioAnalyst (unchanged from your current code)
└── requirements.txt

fastapi_backend/               ← Your existing FastAPI (just adds LiveKit room creation)
├── main.py
├── routes/sessions.py         ← POST /api/sessions (creates room + token)
└── ...

frontend/                      ← Next.js (replaces raw WebSocket with LiveKit SDK)
├── components/
│   ├── WarRoom.jsx             ← LiveKitRoom wrapper
│   ├── AgentPod.jsx            ← Unchanged UI, wired to LiveKit events
│   └── ChairmanMic.jsx        ← hold-to-talk using RPC
├── hooks/
│   ├── useWarRoomEvents.js    ← LiveKit data events → Zustand store
│   └── useChairmanControls.js ← RPC calls to agent server
└── lib/store.js               ← Zustand (mostly unchanged)
```

---

## PART 10 — START RUNNING IT

### Step 1: Run the agent server

```bash
# Terminal 1
python war_room/entrypoint.py start \
  --url $LIVEKIT_URL \
  --api-key $LIVEKIT_API_KEY \
  --api-secret $LIVEKIT_API_SECRET
```

### Step 2: Run FastAPI

```bash
# Terminal 2
uvicorn fastapi_backend.main:app --reload
```

### Step 3: Run Next.js

```bash
# Terminal 3
cd frontend && npm run dev
```

### Step 4: Test locally (agent console mode)

```bash
# Test a single agent without a browser
python war_room/entrypoint.py console
```

---

## SUMMARY

```
WHAT LIVEKIT GIVES WAR ROOM FOR FREE:

  ✅ ONE active agent at a time                → voice isolation solved by design
  ✅ session.update_agent()                    → clean handoff, one line of code
  ✅ turn_detection="manual"                   → orchestrator controls turns
  ✅ session.history / chat_ctx               → conversation memory built-in
  ✅ session.interrupt()                       → chairman interrupt
  ✅ session.generate_reply()                 → trigger agent speech on demand
  ✅ agent_state_changed events               → listening / thinking / speaking → UI
  ✅ Voice override per agent                 → each persona has unique voice
  ✅ RPC methods                              → chairman actions from frontend
  ✅ LiveKit React SDK                        → audio rendering handled by SDK
  ✅ LiveKit Cloud observability              → full transcripts, traces, recordings
  ✅ WebRTC (not raw WebSocket)               → better audio quality + latency

  WHAT YOU BUILD ON TOP:

  ✓ WarRoomOrchestrator (controls turn order)
  ✓ WarRoomState dataclass (shared crisis board)
  ✓ Agent persona classes (instructions + voice)
  ✓ ScenarioAnalyst (generate crisis scenario)
  ✓ War Room UI (unchanged, wire to LiveKit events)
```

---

*War Room Architecture v3.0 — LiveKit Agents*
*Sources: docs.livekit.io/agents/, docs.livekit.io/agents/logic/turns/, docs.livekit.io/agents/logic/agents-handoffs/*
