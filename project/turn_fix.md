# ⚔️ WAR ROOM — Voice Isolation, Turn Management & Agent Memory

## Fixing Multi-Agent Voice Bleed: One Voice at a Time, Like a Real Room

> **The Problem:** Z is speaking. You hear Y and Z simultaneously.
> **Root Cause:** All Gemini Live sessions run in parallel with no speaking gate.
> **The Fix:** A global TurnManager mutex + frontend audio gate + rolling memory.

---

## WHY THIS IS HAPPENING (Root Cause)

```
CURRENT (BROKEN):

  Agent X: autonomous_turn_trigger fires → sends prompt → Gemini responds → streams audio
  Agent Y: autonomous_turn_trigger fires → sends prompt → Gemini responds → streams audio  ← SAME TIME
  Agent Z: autonomous_turn_trigger fires → sends prompt → Gemini responds → streams audio  ← SAME TIME

  All 4 asyncio.sleep(10) timers expire at roughly the same time.
  All 4 agents send to their Live sessions simultaneously.
  All 4 sessions stream audio back at the same time.
  Frontend receives agent_audio_chunk from X, Y, Z, A simultaneously.
  AudioManager plays all 4 → voice soup.

FIXED:

  Only ONE agent holds the speaking lock at any time.
  All other agents see: lock is held → stay silent → wait.
  When lock releases → next agent in queue acquires it.
  Frontend drops audio from any agent that isn't the active speaker.
```

---

## PART 1 — BACKEND: THE TURN MANAGER

### 1.1 — The TurnManager Class (Global Per Session)

```python
# war_room/agents/turn_manager.py

import asyncio
from datetime import datetime
from typing import Optional
import uuid

class TurnManager:
    """
    One TurnManager per session. Enforces exactly ONE speaker at a time.
    
    All agents share this instance. When an agent wants to speak,
    it calls acquire_turn(). If another agent is speaking, it waits.
    When done, it calls release_turn().
    
    This is the ONLY place that controls who speaks.
    No agent bypasses this.
    """

    def __init__(self, session_id: str, event_publisher):
        self.session_id      = session_id
        self.publish         = event_publisher
        
        # The core lock — only ONE agent holds this at a time
        self._speaking_lock  = asyncio.Lock()
        
        # Who is currently speaking (None if room is silent)
        self.active_speaker:  Optional[str] = None
        
        # Ordered queue of agents waiting to speak
        # Each entry: (agent_id, priority, queued_at)
        self._speaker_queue:  asyncio.Queue = asyncio.Queue()
        
        # Track last speaker to avoid same agent speaking twice in a row
        self._last_speaker:   Optional[str] = None
        
        # Conversation turn counter (for memory context)
        self.turn_count:      int = 0

    async def acquire_turn(self, agent_id: str, priority: int = 5) -> bool:
        """
        Called by an agent before it speaks.
        Blocks until the current speaker finishes.
        
        priority: 1=urgent (chairman directive), 5=normal, 10=low
        Returns True when the agent has the floor.
        Returns False if it should skip (e.g. was pre-empted).
        
        Usage in CrisisAgent:
          if await turn_manager.acquire_turn(self.agent_id):
              await self._speak()
              await turn_manager.release_turn(self.agent_id)
        """
        # Avoid same agent speaking twice in a row (feels unnatural)
        if agent_id == self._last_speaker:
            # Check if any other agent is waiting — if so, defer
            if not self._speaker_queue.empty():
                return False
        
        # Wait for the lock (blocks here until current speaker done)
        await self._speaking_lock.acquire()
        
        # Lock acquired — this agent has the floor
        self.active_speaker = agent_id
        self._last_speaker  = agent_id
        self.turn_count    += 1
        
        # Notify ALL agents that X now has the floor
        # This is what makes other agents hold their output
        await self.publish({
            "event_type": "turn_started",
            "payload": {
                "agent_id":  agent_id,
                "turn_count": self.turn_count,
                "acquired_at": datetime.utcnow().isoformat(),
            }
        })
        
        return True

    async def release_turn(self, agent_id: str):
        """
        Called by an agent when it finishes speaking.
        Releases the lock so the next agent can speak.
        """
        if self.active_speaker != agent_id:
            # Safety: only the active speaker can release
            return
        
        self.active_speaker = None
        
        # Notify all agents: floor is now free
        await self.publish({
            "event_type": "turn_ended",
            "payload": {
                "agent_id":    agent_id,
                "turn_count":  self.turn_count,
                "released_at": datetime.utcnow().isoformat(),
            }
        })
        
        # Brief pause between speakers (feels natural, ~0.8s)
        await asyncio.sleep(0.8)
        
        # Release the lock — next acquire_turn() call will proceed
        self._speaking_lock.release()

    async def interrupt_current_speaker(self, by_agent_id: str = "chairman"):
        """
        Called when Chairman interrupts.
        Immediately releases the lock.
        The active speaker's audio stream will be stopped.
        """
        if self.active_speaker and self._speaking_lock.locked():
            interrupted_agent = self.active_speaker
            self.active_speaker = None
            
            await self.publish({
                "event_type": "agent_interrupted",
                "payload": {
                    "agent_id":       interrupted_agent,
                    "interrupted_by": by_agent_id,
                }
            })
            
            # Force-release the lock
            try:
                self._speaking_lock.release()
            except RuntimeError:
                pass  # Already released

    @property
    def is_floor_free(self) -> bool:
        """Returns True if no one is currently speaking."""
        return not self._speaking_lock.locked()

    @property
    def current_speaker(self) -> Optional[str]:
        return self.active_speaker
```

---

### 1.2 — Updated CrisisAgent: Gated Speaking

```python
# war_room/agents/crisis_agent.py
# KEY CHANGES: All speaking goes through TurnManager

class CrisisAgent:
    def __init__(self, ..., turn_manager: TurnManager):
        # ... existing fields ...
        self.turn_manager = turn_manager   # ← SHARED across all agents
        self._wants_to_speak = False        # Flag: agent has something to say
        self._pending_prompt = None         # What it wants to say

    async def _autonomous_turn_trigger(self):
        """
        FIXED: Agents no longer fire simultaneously.
        
        Each agent checks if it WANTS to speak, then WAITS for the floor.
        The TurnManager ensures only one speaks at a time.
        """
        while self._running:
            # Stagger startup: each agent has a different initial delay
            # This prevents all agents from queueing at T=0
            await asyncio.sleep(self._get_initial_delay())
            
            while self._running:
                # Step 1: Wait for silence (floor must be free before we even try)
                await self._wait_for_silence()
                
                # Step 2: Decide if THIS agent wants to speak right now
                should_speak = await self._decide_to_speak()
                
                if not should_speak:
                    # This agent chose silence. Wait and check again.
                    await asyncio.sleep(3.0 + self._jitter())
                    continue
                
                # Step 3: Acquire the floor (blocks if another agent is speaking)
                got_floor = await self.turn_manager.acquire_turn(
                    self.agent_id, 
                    priority=5
                )
                
                if not got_floor:
                    # Was pre-empted or same agent spoke twice. Wait.
                    await asyncio.sleep(2.0 + self._jitter())
                    continue
                
                # Step 4: We have the floor. Speak.
                try:
                    await self._execute_turn()
                finally:
                    # ALWAYS release the turn, even if speech fails
                    await self.turn_manager.release_turn(self.agent_id)
                
                # Step 5: After speaking, wait a natural pause before next turn
                await asyncio.sleep(4.0 + self._jitter())

    def _get_initial_delay(self) -> float:
        """
        Each agent gets a unique starting delay so they don't all
        try to speak the moment the session starts.
        
        Agent 0: waits 2s
        Agent 1: waits 4s  
        Agent 2: waits 6s
        Agent 3: waits 8s
        """
        agent_index = int(self.agent_id.split("_")[0][-1], 36) % 4
        return 2.0 + (agent_index * 2.0)

    def _jitter(self) -> float:
        """Random 0-2s jitter to prevent agents from syncing up."""
        import random
        return random.uniform(0.0, 2.0)

    async def _wait_for_silence(self):
        """
        Block until the room is silent.
        Polls the TurnManager — does NOT try to acquire the lock here.
        """
        while not self.turn_manager.is_floor_free:
            await asyncio.sleep(0.2)

    async def _decide_to_speak(self) -> bool:
        """
        Ask the agent (via Gemini) whether it wants to speak now.
        This is a LIGHTWEIGHT call — text only, no audio.
        Returns True if the agent has something to say.
        """
        # Read current board state
        board = await self._read_shared_board()
        
        # Read last few statements from conversation memory
        recent_context = await self._read_recent_conversation(last_n=5)
        
        decision_prompt = f"""
[CONVERSATION SO FAR]:
{recent_context}

[CURRENT BOARD STATE]:
{board}

[YOUR ROLE]: {self.role_title}
[YOUR AGENDA]: (from your SKILL.md)

It is your opportunity to speak. The room is silent.

Should you speak right now? Consider:
- Do you have something NEW and RELEVANT to add?
- Has enough time passed since you last spoke?
- Is this the right moment given what was just said?

Reply with ONLY: YES or NO
"""
        
        # Quick Gemini call (text model, not Live — much faster)
        response = await self._quick_gemini_call(decision_prompt)
        return response.strip().upper().startswith("YES")

    async def _execute_turn(self):
        """
        The agent actually speaks. Called only when floor is acquired.
        Builds a full context prompt with conversation memory.
        """
        # Build prompt with memory
        full_context = await self._build_turn_prompt()
        
        # Send to the agent's Gemini Live session
        if self.live_session:
            await self.live_session.send(
                input=full_context,
                end_of_turn=True
            )
            # Audio response will flow through _receive_from_gemini()
            # which is already running as a background task

    async def _build_turn_prompt(self) -> str:
        """
        Builds a rich context prompt injected before each turn.
        This is how agents "remember" past conversation.
        """
        board      = await self._read_shared_board()
        memory     = await self._read_my_memory()
        recent     = await self._read_recent_conversation(last_n=10)
        
        return f"""
[TURN {self.turn_manager.turn_count}]

[RECENT CONVERSATION — last 10 statements]:
{recent}

[WHAT YOU KNOW PRIVATELY]:
{memory.get('private_facts', [])}
{memory.get('private_commitments', [])}

[CURRENT CRISIS BOARD]:
Agreed Decisions: {board.get('agreed_decisions', [])}
Open Conflicts:   {board.get('open_conflicts', [])}
Critical Intel:   {board.get('critical_intel', [])}

[YOUR TASK]:
Based on all of the above and your SKILL.md identity,
make your next statement. Be concise. Be specific.
Reference what was just said if relevant.
If you have a tool call to make (write_open_conflict, etc.),
make it AFTER your spoken statement.
"""
```

---

### 1.3 — Conversation Memory: Rolling Context Store

```python
# war_room/agents/conversation_memory.py

class ConversationMemory:
    """
    Maintains a rolling log of the full conversation.
    All agents read from this. No agent writes to another's memory.
    
    Stored in Firestore: crisis_sessions/{session_id}.conversation_log
    Capped at 50 statements. Older ones rolled into a summary.
    """

    def __init__(self, session_id: str, db):
        self.session_id = session_id
        self.db         = db
        self.MAX_FULL   = 50    # Keep last 50 statements in full
        self.MAX_RECENT = 10    # Default "recent" context window

    async def add_statement(
        self,
        agent_id:       str,
        character_name: str,
        role_title:     str,
        text:           str,
        turn_count:     int,
    ):
        """
        Called after every agent_speaking_end.
        Appends to the shared rolling log.
        """
        entry = {
            "turn":           turn_count,
            "agent_id":       agent_id,
            "character_name": character_name,
            "role_title":     role_title,
            "text":           text,
            "spoken_at":      datetime.utcnow().isoformat(),
        }

        # Read current log
        doc   = await self.db.collection("crisis_sessions") \
                             .document(self.session_id).get()
        log   = doc.to_dict().get("conversation_log", [])
        
        log.append(entry)

        # If log exceeds MAX_FULL, compress oldest half into a summary
        if len(log) > self.MAX_FULL:
            log = await self._compress_old_entries(log)

        await self.db.collection("crisis_sessions") \
                     .document(self.session_id) \
                     .update({"conversation_log": log})

    async def get_recent(self, last_n: int = 10) -> str:
        """
        Returns the last N statements as a formatted string.
        This is injected into every agent's turn prompt.
        """
        doc  = await self.db.collection("crisis_sessions") \
                            .document(self.session_id).get()
        log  = doc.to_dict().get("conversation_log", [])
        
        recent = log[-last_n:] if len(log) >= last_n else log
        
        if not recent:
            return "[No statements yet — session just started]"
        
        lines = []
        for entry in recent:
            # Check if it's a summary entry
            if entry.get("is_summary"):
                lines.append(f"[SUMMARY of turns {entry['covers_turns']}]:")
                lines.append(f"  {entry['text']}")
            else:
                lines.append(
                    f"Turn {entry['turn']} — {entry['character_name']} "
                    f"({entry['role_title']}):"
                )
                lines.append(f"  \"{entry['text']}\"")
        
        return "\n".join(lines)

    async def get_full_summary(self) -> str:
        """
        Returns a compressed summary of the entire conversation.
        Used for very long sessions.
        """
        doc  = await self.db.collection("crisis_sessions") \
                            .document(self.session_id).get()
        log  = doc.to_dict().get("conversation_log", [])
        summary = doc.to_dict().get("conversation_summary", "")
        
        if summary:
            return summary + "\n\n[RECENT]:\n" + await self.get_recent(5)
        return await self.get_recent(20)

    async def _compress_old_entries(self, log: list) -> list:
        """
        When log exceeds MAX_FULL entries, take the oldest half
        and compress them into a single summary using Gemini.
        Keep the newest half intact.
        """
        split_point = len(log) // 2
        old_entries = log[:split_point]
        new_entries = log[split_point:]
        
        # Format old entries for summarization
        old_text = "\n".join([
            f"{e['character_name']} ({e['role_title']}): \"{e['text']}\""
            for e in old_entries
            if not e.get("is_summary")
        ])
        
        # Call Gemini to summarize (text model, fast)
        summary_prompt = f"""
Summarize this crisis room conversation in 3-5 sentences.
Focus on: what was agreed, what conflicts exist, what intel was shared.
Be factual and specific. Preserve agent names and positions.

CONVERSATION:
{old_text}
"""
        from google import genai
        client  = genai.Client()
        model   = "gemini-2.5-flash"
        result  = await client.aio.models.generate_content(
            model=model,
            contents=summary_prompt
        )
        summary_text = result.text.strip()
        
        # Replace old entries with one summary entry
        covers_turns = f"{old_entries[0]['turn']}-{old_entries[-1]['turn']}"
        summary_entry = {
            "is_summary":    True,
            "covers_turns":  covers_turns,
            "text":          summary_text,
            "compressed_at": datetime.utcnow().isoformat(),
        }
        
        return [summary_entry] + new_entries
```

---

### 1.4 — Introduction Sequence (Structured Turn-by-Turn)

```python
# war_room/agents/introduction_sequence.py

async def run_introduction_sequence(
    agents:       list,       # list of CrisisAgent instances (in order)
    turn_manager: TurnManager,
    memory:       ConversationMemory,
    crisis_brief: str,
):
    """
    Runs ONCE at session start.
    Each agent introduces themselves in order, one at a time.
    
    This populates the conversation memory so all agents
    know who is in the room before the crisis discussion begins.
    
    Sequence:
      Turn 1: ATLAS introduces themselves
      Turn 2: NOVA introduces themselves
      Turn 3: FELIX introduces themselves
      Turn 4: CIPHER introduces themselves
      Turn 5: ORACLE introduces themselves
      Turn 6: ATLAS opens the crisis discussion
    """
    
    INTRO_PROMPT = """
[CRISIS BRIEF]:
{crisis_brief}

[YOUR TASK — INTRODUCTION]:
This is the start of the crisis session. You are entering the room.
Introduce yourself in 2-3 sentences:
  1. Your name and role
  2. Your immediate read on the crisis (one sentence)
  3. What you need from this room (one sentence)

Be in character. Be direct. This sets the tone.
Do NOT wait for others. You have the floor.
"""

    for i, agent in enumerate(agents):
        # Acquire the floor for this agent
        got_floor = await turn_manager.acquire_turn(agent.agent_id, priority=1)
        
        if not got_floor:
            continue
        
        try:
            # Get context of previous introductions for later agents
            previous_intros = await memory.get_recent(last_n=i)
            
            intro_prompt = INTRO_PROMPT.format(crisis_brief=crisis_brief)
            
            if i > 0:
                intro_prompt += f"\n\n[WHO IS ALREADY IN THE ROOM]:\n{previous_intros}"
            
            # Send intro prompt to agent's Live session
            if agent.live_session:
                await agent.live_session.send(
                    input=intro_prompt,
                    end_of_turn=True
                )
                
                # Wait for agent to finish speaking
                # The _receive_from_gemini() task will fire agent_speaking_end
                # We wait for it via an event or a reasonable timeout
                await _wait_for_agent_to_finish(agent, timeout=30.0)
        
        finally:
            await turn_manager.release_turn(agent.agent_id)
        
        # Brief pause between introductions (1.5s feels natural)
        await asyncio.sleep(1.5)
    
    # After all introductions, let ATLAS open the discussion
    # The autonomous turn triggers will take over from here


async def _wait_for_agent_to_finish(agent: CrisisAgent, timeout: float = 30.0):
    """
    Wait until agent.is_speaking becomes False.
    Uses an asyncio.Event set in _on_turn_complete().
    """
    deadline = asyncio.get_event_loop().time() + timeout
    
    while agent.is_speaking:
        if asyncio.get_event_loop().time() > deadline:
            break
        await asyncio.sleep(0.1)
```

---

### 1.5 — Updated _receive_from_gemini: Add Speaking State Flag

```python
# In CrisisAgent — add is_speaking flag

class CrisisAgent:
    def __init__(self, ...):
        # ... existing fields ...
        self.is_speaking  = False   # ← track speaking state
        self._speak_done  = asyncio.Event()  # ← signals turn complete

    async def _receive_from_gemini(self):
        """
        UPDATED: Sets is_speaking flag and fires _speak_done event.
        """
        while self._running:
            turn = self.live_session.receive()
            
            self.is_speaking = True
            self._speak_done.clear()
            
            full_transcript = ""

            async for response in turn:
                
                if response.data:
                    # Send audio to frontend
                    await self.publish({
                        "event_type": "agent_audio_chunk",
                        "payload": {
                            "agent_id":    self.agent_id,
                            "audio_b64":   response.data,
                            "sample_rate": 24000,
                            "channels":    1,
                            "bit_depth":   16,
                        }
                    })
                
                if response.text:
                    full_transcript += response.text
                    await self.publish({
                        "event_type": "agent_speaking_chunk",
                        "payload": {
                            "agent_id":        self.agent_id,
                            "transcript_chunk": response.text,
                        }
                    })
                
                # Handle interruption from chairman
                if (hasattr(response, "server_content") and
                    response.server_content and
                    response.server_content.interrupted):
                    break
            
            # Turn complete
            if full_transcript:
                await self._on_turn_complete(full_transcript)
            
            self.is_speaking = False
            self._speak_done.set()  # ← wake up _wait_for_agent_to_finish()
```

---

### 1.6 — Session Bootstrapper: Wire Everything Together

```python
# In session_bootstrapper.py — updated boot sequence

async def bootstrap_session(session_id, crisis_input, ...):
    # ... existing code to generate scenario and agents ...
    
    # Create ONE TurnManager for the session (shared by all agents)
    turn_manager  = TurnManager(
        session_id=session_id,
        event_publisher=lambda evt: publish_event(session_id, evt)
    )
    
    # Create conversation memory (shared, stored in Firestore)
    memory = ConversationMemory(session_id=session_id, db=db)
    
    # Initialize all agents with the SHARED turn_manager and memory
    agents = []
    for agent_config in scenario["agents"]:
        agent = CrisisAgent(
            ...,
            turn_manager = turn_manager,  # ← shared instance
            memory       = memory,        # ← shared instance
        )
        agents.append(agent)
    
    # Start all agent background tasks (Live sessions open)
    for agent in agents:
        asyncio.create_task(agent.start())
    
    # Wait for all voice sessions to be ready
    await wait_for_all_voices_active(agents, db)
    
    # Run structured introduction sequence BEFORE autonomous turns start
    asyncio.create_task(
        run_introduction_sequence(
            agents=agents,
            turn_manager=turn_manager,
            memory=memory,
            crisis_brief=scenario["crisis_brief"]
        )
    )
    
    # The autonomous_turn_trigger in each agent will start after
    # introductions complete (it waits for floor to be free)
    
    await publish_event(session_id, "session_ready", {
        "session_id":  session_id,
        "crisis_title": scenario["crisis_title"],
        "agent_count": len(agents),
    })
```

---

## PART 2 — FRONTEND: THE AUDIO GATE

### 2.1 — The Core Problem in the Frontend

```
CURRENT:
  ws.onmessage: agent_audio_chunk for X → AudioManager.playChunk(X)
  ws.onmessage: agent_audio_chunk for Y → AudioManager.playChunk(Y)  ← same time
  ws.onmessage: agent_audio_chunk for Z → AudioManager.playChunk(Z)  ← same time
  Result: 3 voices playing simultaneously ❌

FIXED:
  Track activeSpeaker in store.
  In ws.onmessage: ONLY play audio if agent_id === activeSpeaker.
  Drop all other audio chunks silently.
  Result: exactly 1 voice at a time ✓
```

### 2.2 — Updated Zustand Store: Active Speaker Gate

```javascript
// lib/store.js — add activeSpeaker tracking

export const useSessionStore = create((set, get) => ({
  // ── State ────────────────────────────────────────────────────────────
  agents:          {},
  activeSpeaker:   null,   // ← THE GATE: only this agent's audio plays
  speakingQueue:   [],     // agents waiting for the floor (for UI display)
  turnCount:       0,
  // ... rest of existing state ...

  handleEvent: (event) => {
    const { event_type, payload } = event;

    switch (event_type) {

      // ── TURN MANAGEMENT ─────────────────────────────────────────────
      
      case 'turn_started':
        // The TurnManager says THIS agent now has the floor.
        // ALL audio from other agents will be dropped.
        set(s => ({
          activeSpeaker: payload.agent_id,
          turnCount:     payload.turn_count,
          // Set all other agents to "listening"
          agents: Object.fromEntries(
            Object.entries(s.agents).map(([id, agent]) => [
              id,
              {
                ...agent,
                status: id === payload.agent_id ? 'speaking' : 'listening'
              }
            ])
          )
        }));
        break;

      case 'turn_ended':
        set(s => ({
          activeSpeaker: null,
          // Set the finished speaker back to "listening"
          agents: {
            ...s.agents,
            [payload.agent_id]: {
              ...s.agents[payload.agent_id],
              status: 'listening'
            }
          }
        }));
        break;

      // ── AGENT STATUS (still keep these for specific transitions) ────
      
      case 'agent_speaking_start':
        // Only update UI if this matches the active speaker
        set(s => {
          if (s.activeSpeaker !== payload.agent_id) return s;
          return {
            agents: {
              ...s.agents,
              [payload.agent_id]: {
                ...s.agents[payload.agent_id],
                status: 'speaking'
              }
            },
            transcripts: { ...s.transcripts, [payload.agent_id]: '' }
          };
        });
        break;

      case 'agent_speaking_chunk':
        // Only update transcript if this is the active speaker
        set(s => {
          if (s.activeSpeaker !== payload.agent_id) return s;
          return {
            transcripts: {
              ...s.transcripts,
              [payload.agent_id]: 
                (s.transcripts[payload.agent_id] || '') + 
                payload.transcript_chunk
            }
          };
        });
        break;

      case 'agent_speaking_end':
        // Clear transcript and set to listening
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

      // ... rest of existing switch cases unchanged ...
    }
  }
}));
```

### 2.3 — Updated WebSocket Handler: The Audio Gate

```javascript
// lib/useWarRoomSocket.js — the critical change

export function useWarRoomSocket(sessionId, chairmanToken) {
  const wsRef           = useRef(null);
  const audioManagerRef = useRef(new AudioManager());
  const updateStore     = useSessionStore(s => s.handleEvent);
  
  // ── GET THE ACTIVE SPEAKER FROM STORE ────────────────────────────────
  // We read this directly from the store ref to avoid stale closures
  const getActiveSpeaker = () => useSessionStore.getState().activeSpeaker;

  const connect = useCallback(async () => {
    const ws = new WebSocket(
      `wss://your-api/ws/${sessionId}?token=${chairmanToken}`
    );
    wsRef.current = ws;

    ws.onmessage = async (event) => {
      const msg = JSON.parse(event.data);

      // ── THE AUDIO GATE ────────────────────────────────────────────────
      if (msg.event_type === 'agent_audio_chunk') {
        const activeSpeaker = getActiveSpeaker();
        
        // CRITICAL: Only play audio from the active speaker.
        // All other chunks are silently dropped.
        if (msg.payload.agent_id === activeSpeaker) {
          await audioManagerRef.current.playChunk(
            msg.payload.agent_id,
            msg.payload.audio_b64
          );
        }
        // If agent_id !== activeSpeaker: drop the chunk. Don't play it.
        // No error, no logging needed — this is expected behavior.
        return;
      }

      // ── INTERRUPTED: stop audio immediately ───────────────────────────
      if (msg.event_type === 'agent_interrupted') {
        audioManagerRef.current.stopAgent(msg.payload.agent_id);
        // Update store
        updateStore(msg);
        return;
      }

      // ── ALL OTHER EVENTS → store ──────────────────────────────────────
      updateStore(msg);
    };

    ws.onopen  = () => {
      setInterval(() => ws.send(JSON.stringify({ type: 'ping' })), 25000);
    };
    ws.onerror = (err) => console.error('[WS] Error:', err);
    ws.onclose = () => setTimeout(connect, 2000);
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

### 2.4 — Updated AudioManager: Clear Queue on Speaker Change

```javascript
// lib/AudioManager.js — add clearAllExcept() method

export class AudioManager {
  constructor() {
    this.context        = null;
    this.nextPlayTime   = {};
    this.activeSources  = {};
    this.isInitialized  = false;
  }

  // ... existing initialize(), playChunk(), destroy() unchanged ...

  stopAgent(agentId) {
    const sources = this.activeSources[agentId] || [];
    sources.forEach(source => {
      try { source.stop(); } catch(e) {}
    });
    this.activeSources[agentId] = [];
    this.nextPlayTime[agentId]  = this.context?.currentTime || 0;
  }

  /**
   * Called when activeSpeaker changes.
   * Stops ALL audio from previous speakers.
   * Resets their playback schedules.
   * 
   * This prevents buffered chunks from a previous speaker
   * bleeding into the next speaker's turn.
   */
  stopAllExcept(activeAgentId) {
    const allAgents = Object.keys(this.activeSources);
    
    allAgents.forEach(agentId => {
      if (agentId !== activeAgentId) {
        this.stopAgent(agentId);
      }
    });
  }

  /**
   * Hard reset — stop everything, clear all schedules.
   * Called when a chairman interruption occurs.
   */
  stopAll() {
    const allAgents = Object.keys(this.activeSources);
    allAgents.forEach(agentId => this.stopAgent(agentId));
  }
}
```

### 2.5 — Wire stopAllExcept() to turn_started Event

```javascript
// In useWarRoomSocket.js — handle turn_started event specially

ws.onmessage = async (event) => {
  const msg = JSON.parse(event.data);

  // ── TURN STARTED: new speaker → stop all others ───────────────────
  if (msg.event_type === 'turn_started') {
    // Stop any buffered audio from previous speakers immediately
    audioManagerRef.current.stopAllExcept(msg.payload.agent_id);
    // Update store (sets activeSpeaker → enables audio gate)
    updateStore(msg);
    return;
  }

  // ── AUDIO GATE (same as before) ────────────────────────────────────
  if (msg.event_type === 'agent_audio_chunk') {
    const activeSpeaker = getActiveSpeaker();
    if (msg.payload.agent_id === activeSpeaker) {
      await audioManagerRef.current.playChunk(
        msg.payload.agent_id,
        msg.payload.audio_b64
      );
    }
    return;
  }

  // ── INTERRUPTED: stop all audio ────────────────────────────────────
  if (msg.event_type === 'agent_interrupted') {
    audioManagerRef.current.stopAll();
    updateStore(msg);
    return;
  }

  updateStore(msg);
};
```

---

## PART 3 — AGENT MEMORY: REMEMBER THE WHOLE CONVERSATION

### 3.1 — What Each Agent Remembers

```
Two types of memory:

SHARED (crisis_sessions.conversation_log):
  - What everyone said, in order
  - Compressed automatically when it gets long
  - Read by ALL agents before every turn
  - The "room transcript"

PRIVATE (agent_memory/{agent_id}_{session_id}):
  - This agent's own commitments
  - Hidden agenda (never shared)
  - What they plan to reveal and when
  - Their own contradiction tracking
  - Written/read by THIS agent only
```

### 3.2 — How Memory Is Injected Into Every Turn

```python
# In CrisisAgent._build_turn_prompt()

async def _build_turn_prompt(self) -> str:
    # 1. Get shared conversation memory (last 10 turns)
    recent_convo = await self.memory.get_recent(last_n=10)
    
    # 2. Get this agent's private memory
    my_memory_doc = await self.db.collection("agent_memory") \
                                 .document(f"{self.agent_id}_{self.session_id}") \
                                 .get()
    my_memory = my_memory_doc.to_dict() if my_memory_doc.exists else {}
    
    # 3. Get current board state
    board = await self._read_shared_board()
    
    # 4. Build full context prompt
    prompt = f"""
[TURN {self.turn_manager.turn_count} — YOUR TURN TO SPEAK]

━━━ CONVERSATION SO FAR ━━━
{recent_convo}

━━━ CURRENT BOARD ━━━
AGREED: {[d['text'] for d in board.get('agreed_decisions', [])]}
CONFLICTS: {[c['description'] for c in board.get('open_conflicts', [])]}
INTEL: {[i['text'] for i in board.get('critical_intel', [])]}

━━━ YOUR PRIVATE NOTES ━━━
Your commitments: {my_memory.get('private_commitments', [])}
What you know that others don't: {my_memory.get('private_facts', [])}

━━━ YOUR TASK ━━━
Based on everything above and your identity (from your SKILL.md):
Speak your next statement. Reference the conversation above.
Stay consistent with your past positions.
Advance your agenda.
"""
    return prompt
```

### 3.3 — Updating Memory After Each Turn

```python
# In CrisisAgent._on_turn_complete()

async def _on_turn_complete(self, transcript: str):
    # 1. Add to shared conversation memory
    await self.memory.add_statement(
        agent_id       = self.agent_id,
        character_name = self.character_name,
        role_title     = self.role_title,
        text           = transcript,
        turn_count     = self.turn_manager.turn_count,
    )
    
    # 2. Update this agent's private memory (what they committed to publicly)
    #    Ask Gemini to extract any commitments from the statement
    commitments = await self._extract_commitments(transcript)
    if commitments:
        await self.db.collection("agent_memory") \
                     .document(f"{self.agent_id}_{self.session_id}") \
                     .update({
                         "private_commitments": firestore.ArrayUnion(commitments),
                         "previous_statements": firestore.ArrayUnion([{
                             "text":      transcript,
                             "turn":      self.turn_manager.turn_count,
                             "spoken_at": datetime.utcnow().isoformat(),
                         }])
                     })
    
    # 3. Push events as normal
    await self.publish({
        "event_type": "agent_speaking_end",
        "payload": {
            "agent_id":        self.agent_id,
            "full_transcript": transcript,
        }
    })
    
    # 4. Observer Agent will pick this up and analyze
    # (via session_events subcollection — no direct coupling)

async def _extract_commitments(self, transcript: str) -> list[str]:
    """
    Quick Gemini call to extract explicit commitments from a statement.
    e.g. "I will prepare the legal brief by 15:00" → stored as commitment
    """
    if len(transcript) < 20:
        return []
    
    result = await self._quick_gemini_call(
        f"Extract any explicit commitments or positions from this statement. "
        f"Return as a JSON list of strings. Return [] if none.\n\n"
        f"Statement: \"{transcript}\""
    )
    
    import json
    try:
        return json.loads(result.strip())
    except:
        return []
```

---

## PART 4 — AGENT POD UI: SHOW LISTENING STATE

### 4.1 — Pod Status Rules (Strict)

```javascript
// components/AgentPod.jsx

export function AgentPod({ agentId }) {
  const agent        = useSessionStore(s => s.agents[agentId]);
  const activeSpeaker = useSessionStore(s => s.activeSpeaker);
  const transcript   = useSessionStore(s => s.transcripts[agentId]);
  
  // Derive display state from activeSpeaker (not just agent.status)
  const displayState = (() => {
    if (agentId === activeSpeaker) {
      return agent?.status || 'speaking';   // speaking / thinking
    }
    // If someone else is speaking, this agent is ALWAYS "listening"
    if (activeSpeaker && agentId !== activeSpeaker) {
      return 'listening';
    }
    // No one speaking — show agent's actual status
    return agent?.status || 'idle';
  })();
  
  const isActive = agentId === activeSpeaker;
  
  return (
    <div className={`pod pod--${displayState} ${isActive ? 'pod--active' : ''}`}>
      
      {/* Agent name + role */}
      <div className="pod__name">{agent?.character_name}</div>
      <div className="pod__role">{agent?.role_title}</div>
      
      {/* Waveform — only animate for active speaker */}
      <WaveformBars 
        active={displayState === 'speaking'}
        color={isActive ? 'var(--accent-voice)' : 'var(--bg-elevated)'}
      />
      
      {/* Status label */}
      <div className={`pod__status pod__status--${displayState}`}>
        {displayState === 'speaking'  && '🎙️ SPEAKING'}
        {displayState === 'thinking'  && '💭 PROCESSING'}
        {displayState === 'listening' && '👂 LISTENING'}
        {displayState === 'conflicted'&& '⚡ CONFLICTING'}
        {displayState === 'idle'      && '· · ·'}
      </div>
      
      {/* Live transcript — only for active speaker */}
      {isActive && transcript && (
        <div className="pod__transcript">{transcript}</div>
      )}
      
      {/* Last statement — for non-active agents */}
      {!isActive && agent?.lastStatement && (
        <div className="pod__last-statement">
          "{agent.lastStatement.slice(0, 60)}..."
        </div>
      )}
      
    </div>
  );
}
```

### 4.2 — Pod CSS States

```css
/* Listening state — when another agent has the floor */
.pod--listening {
  border: 1px solid var(--bg-border);
  background: var(--bg-surface);
  opacity: 0.75;   /* Slightly dimmed — they're not the focus */
  transition: opacity 300ms ease, border-color 300ms ease;
}

/* Active speaker state */
.pod--active.pod--speaking {
  border: 1px solid rgba(0, 229, 255, 0.6);
  box-shadow: 
    0 0 20px rgba(0, 229, 255, 0.2),
    inset 0 0 20px rgba(0, 229, 255, 0.03);
  background: var(--bg-elevated);
  opacity: 1.0;
  transition: all 300ms ease;
}

/* All non-active pods when someone is speaking */
.pod:not(.pod--active) {
  opacity: 0.6;
  transition: opacity 300ms ease;
}

/* Return to full opacity when no one is speaking */
.pod--idle, .pod--listening {
  opacity: 1.0;
}
```

---

## PART 5 — SUMMARY: WHAT YOU NEED TO ADD / CHANGE

### Backend Changes (4 files)

```
NEW FILE:  war_room/agents/turn_manager.py
  ✓ TurnManager class with asyncio.Lock()
  ✓ acquire_turn() / release_turn()
  ✓ interrupt_current_speaker()

NEW FILE:  war_room/agents/conversation_memory.py
  ✓ ConversationMemory class
  ✓ add_statement() → Firestore
  ✓ get_recent(last_n) → formatted string
  ✓ _compress_old_entries() → Gemini summarization

NEW FILE:  war_room/agents/introduction_sequence.py
  ✓ run_introduction_sequence()
  ✓ Structured turn-by-turn agent intros

MODIFY:    war_room/agents/crisis_agent.py
  ✓ Add: turn_manager and memory as __init__ params
  ✓ Fix:  _autonomous_turn_trigger() → uses TurnManager gate
  ✓ Add:  _decide_to_speak() → quick Gemini YES/NO check
  ✓ Add:  _execute_turn() → calls acquire, speaks, releases
  ✓ Add:  _build_turn_prompt() → injects conversation memory
  ✓ Fix:  _on_turn_complete() → writes to shared memory
  ✓ Add:  is_speaking flag + _speak_done Event

MODIFY:    war_room/session_bootstrapper.py
  ✓ Create TurnManager + ConversationMemory (shared)
  ✓ Pass both to every CrisisAgent
  ✓ Start introduction_sequence as background task
```

### Frontend Changes (3 files)

```
MODIFY:    lib/store.js
  ✓ Add: activeSpeaker field (null by default)
  ✓ Add: case 'turn_started' → sets activeSpeaker
  ✓ Add: case 'turn_ended'   → clears activeSpeaker
  ✓ Fix: agent_speaking_chunk → only update if activeSpeaker matches

MODIFY:    lib/useWarRoomSocket.js
  ✓ Add: getActiveSpeaker() helper (reads from store)
  ✓ Fix: agent_audio_chunk handler → ONLY plays if agent_id === activeSpeaker
  ✓ Add: turn_started handler → calls audioManager.stopAllExcept()

MODIFY:    lib/AudioManager.js
  ✓ Add: stopAllExcept(activeAgentId)
  ✓ Add: stopAll()

MODIFY:    components/AgentPod.jsx
  ✓ Fix: displayState derives from activeSpeaker, not just agent.status
  ✓ Fix: all non-active pods show "listening" when someone speaks
  ✓ Fix: waveform only animates for active speaker
  ✓ Fix: transcript only shows for active speaker
```

---

## BEFORE vs AFTER

```
BEFORE:
  T=0: Agents X, Y, Z, A all start 10s timers simultaneously
  T=10: All 4 fire, all 4 send to Gemini Live simultaneously
  T=11: All 4 receive audio responses simultaneously  
  T=11: Frontend plays all 4 → voice chaos

AFTER:
  T=0: Intro sequence starts
  T=0: ATLAS acquires lock → introduces self → releases lock
  T=8: NOVA acquires lock → introduces self → releases lock
  T=16: FELIX acquires lock → introduces self → releases lock
  T=24: CIPHER acquires lock → introduces self → releases lock
  T=32: Autonomous turns begin — ONE at a time
  T=32: ATLAS decides YES → acquires lock → speaks → releases lock
  T=43: NOVA decides YES → acquires lock → speaks → releases lock
  T=43: FELIX decides NO → stays silent → waits
  T=54: One voice. Always. No leakage.
```

---

*War Room Voice Isolation & Turn Management v1.0*
*One speaker. One voice. Every time.*
*The TurnManager lock is the single source of truth for who speaks.*
