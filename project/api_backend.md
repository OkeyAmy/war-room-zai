# ⚔️ WAR ROOM — Complete API Specification
>
> Framework: FastAPI (Python 3.11+)
> Auth: Bearer token (chairman_token per session)
> Real-time: WebSocket at /ws/{session_id}
> Database: Firestore (per-agent isolated)
> Version: 1.0

---

## HOW THE API IS ORGANIZED

```
Every route group maps to EXACTLY ONE frontend panel or system:

/api/sessions/...           → SESSION LIFECYCLE (all screens)
/api/sessions/{id}/scenario → BRIEFING ROOM (assembling screen)
/api/sessions/{id}/agents   → LEFT PANEL: Agent Roster
/api/sessions/{id}/board    → CENTER PANEL: Crisis Board
/api/sessions/{id}/feed     → BOTTOM LEFT: Crisis Feed
/api/sessions/{id}/pods     → BOTTOM CENTER: Agent Voice Pods
/api/sessions/{id}/intel    → BOTTOM RIGHT TOP: Room Intelligence
/api/sessions/{id}/posture  → BOTTOM RIGHT MID: Crisis Posture
/api/sessions/{id}/score    → BOTTOM RIGHT BOT: Resolution Score
/api/sessions/{id}/world    → WORLD AGENT: Escalation Engine
/api/sessions/{id}/chairman → COMMAND BAR: Chairman Actions
/api/sessions/{id}/voice    → VOICE: Gemini Live Audio Bridge
/ws/{session_id}            → WEBSOCKET: All real-time events

Memory isolation rule:
  Every endpoint for a specific agent ONLY reads/writes
  that agent's Firestore collection. The shared crisis
  document is read-only for agents except via controlled
  write tools.
```

POD VOICE MODE (implemented)
  - Session bootstrap limits active roster to 4 generated agents.
  - Each agent is mapped to a fixed pod slot: pod_1..pod_4.
  - A fifth slot (pod_5_summon) is reserved for summon workflow.
  - Each pod stores:
      pod_id, agent_id, connected, livekit_room, livekit_identity
  - Only connected pods are eligible for backend turn routing and audio output.

---

## BASE MODELS (Shared Across All Endpoints)

```python
# All timestamps: ISO 8601 UTC string  "2026-02-26T14:32:01Z"
# All IDs: UUID4 string
# All scores: integer 0–100

class AgentStatus(str, Enum):
    IDLE        = "idle"
    THINKING    = "thinking"
    SPEAKING    = "speaking"
    CONFLICTED  = "conflicted"
    SILENT      = "silent"
    LISTENING   = "listening"

class ThreatLevel(str, Enum):
    CONTAINED = "contained"
    ELEVATED  = "elevated"
    CRITICAL  = "critical"
    MELTDOWN  = "meltdown"

class FeedSource(str, Enum):
    WORLD    = "WORLD"
    LEGAL    = "LEGAL"
    MEDIA    = "MEDIA"
    INTERNAL = "INTERNAL"
    SOCIAL   = "SOCIAL"

class InsightType(str, Enum):
    CONTRADICTION = "contradiction"
    ALLIANCE      = "alliance"
    BLIND_SPOT    = "blind_spot"
    MOOD_SHIFT    = "mood_shift"

class SessionStatus(str, Enum):
    ASSEMBLING  = "assembling"
    BRIEFING    = "briefing"
    ACTIVE      = "active"
    ESCALATION  = "escalation"
    RESOLUTION  = "resolution"
    CLOSED      = "closed"
```

---

## 1. SESSION ROUTES

### POST /api/sessions

**Panel:** Landing Screen (Image 2)
**Purpose:** User submits crisis input. Triggers full bootstrap sequence.

```
REQUEST:
  Content-Type: application/json
  Body:
    {
      "crisis_input": string,       // required, 10–2000 chars
                                    // "My hospital AI misdiagnosed 200 patients..."
      "chairman_name": string,      // optional, displayed in Command Bar
      "session_duration_minutes": int  // optional, default 30, min 5, max 120
    }

RESPONSE 201:
  {
    "session_id": "A3F9B2C1",        // 8-char uppercase ID
    "chairman_token": "uuid4",       // store in frontend, sent with every request
    "status": "assembling",
    "ws_url": "wss://api.warroom.app/ws/A3F9B2C1",
    "created_at": "2026-02-26T14:30:00Z",
    "message": "Crisis received. Assembling your team."
  }

RESPONSE 422:
  { "error": "crisis_input_too_short", "detail": "Min 10 characters required" }

SIDE EFFECTS:
  - Creates /crisis_sessions/{session_id} in Firestore
  - Triggers session_bootstrapper.py asynchronously
  - Immediately starts pushing events over WebSocket
  - Frontend should open WebSocket BEFORE calling this endpoint
    to catch the first assembling events

MEMORY ISOLATION:
  - Only creates the top-level session doc
  - No agent memory collections created yet (done in /scenario)
```

---

### GET /api/sessions/{session_id}

**Panel:** Top Command Bar (session state + timer)
**Purpose:** Poll full session state. Used on reconnect or page refresh.

```
REQUEST:
  Headers: Authorization: Bearer {chairman_token}

RESPONSE 200:
  {
    "session_id": "A3F9B2C1",
    "status": "active",
    "crisis_title": "OPERATION BLACKSITE",
    "crisis_domain": "corporate",
    "crisis_brief": "A classified AI-driven surveillance...",
    "threat_level": "critical",
    "resolution_score": 44,
    "created_at": "2026-02-26T14:30:00Z",
    "timer": {
      "session_duration_seconds": 5400,
      "elapsed_seconds": 3622,
      "remaining_seconds": 1778,
      "formatted": "00:29:38"
    },
    "chairman_name": "DIRECTOR",
    "agent_count": 5
  }

RESPONSE 404:
  { "error": "session_not_found" }

RESPONSE 403:
  { "error": "invalid_chairman_token" }

NOTE: This is the ONLY endpoint that returns the full
      merged session state. All other endpoints return
      data for their specific panel only.
```

---

### PATCH /api/sessions/{session_id}

**Panel:** Top Command Bar (pause/resume)
**Purpose:** Update session-level settings mid-session.

```
REQUEST:
  Headers: Authorization: Bearer {chairman_token}
  Body (all fields optional):
    {
      "status": "active" | "resolution",  // trigger resolution mode
      "paused": boolean,                  // pause/resume all agents
      "threat_level": ThreatLevel         // manual override (Chairman power)
    }

RESPONSE 200:
  {
    "session_id": "A3F9B2C1",
    "updated_fields": ["paused"],
    "current_state": { ...same as GET /api/sessions/{id} }
  }

SIDE EFFECTS:
  When paused=true:
    - All agent Live sessions receive pause signal
    - WebSocket pushes "session_paused" event
    - All agent pods show PAUSED state
  When status="resolution":
    - Triggers resolution sequence
    - Each agent generates their final_position
    - Pushes "resolution_mode_start" WS event
```

---

### DELETE /api/sessions/{session_id}

**Panel:** N/A (system cleanup)
**Purpose:** End session, release all Gemini Live connections, clean Firestore.

```
REQUEST:
  Headers: Authorization: Bearer {chairman_token}

RESPONSE 200:
  {
    "session_id": "A3F9B2C1",
    "closed_at": "2026-02-26T15:00:00Z",
    "agents_released": 5,
    "after_action_url": "/api/sessions/A3F9B2C1/report"
  }

SIDE EFFECTS:
  - Closes all Gemini Live WebSocket sessions (per agent)
  - Marks all agent Firestore docs voice_session_active=false
  - Sets session status="closed"
  - Generates after-action report async
  - Does NOT delete Firestore data (preserved for report)
```

---

## 2. SCENARIO ROUTES

### GET /api/sessions/{session_id}/scenario

**Panel:** Briefing Room (Image 3 — assembling screen)
**Purpose:** Get the full scenario spec generated by Scenario Analyst.
             Frontend polls this during assembling state.

```
REQUEST:
  Headers: Authorization: Bearer {chairman_token}

RESPONSE 200:
  {
    "session_id": "A3F9B2C1",
    "crisis_title": "OPERATION BLACKSITE",
    "crisis_domain": "corporate",
    "crisis_brief": "A classified AI-driven surveillance contract has been exposed...",
    "threat_level_initial": "critical",
    "resolution_score_initial": 44,
    "agents": [
      {
        "agent_id": "atlas_A3F9B2C1",
        "role_key": "strategic_analyst",
        "role_title": "Strategic Analyst",
        "character_name": "ATLAS",
        "defining_line": "Containment is possible. But not if we wait.",
        "identity_color": "#4A9EFF",
        "voice_name": "Orus",
        "status": "idle"
      },
      ...
    ],
    "initial_intel": [...],
    "initial_conflicts": [...],
    "escalation_schedule": [
      { "delay_minutes": 5,  "event_text": "...", "type": "MEDIA" },
      { "delay_minutes": 12, "event_text": "...", "type": "LEGAL" },
      { "delay_minutes": 20, "event_text": "...", "type": "INTERNAL" }
    ],
    "assembly_log": [
      // Streaming log lines shown on Image 3 screen
      { "line": "Extracting crisis domain:", "value": "ANALYZING...",   "status": "complete" },
      { "line": "Generating tactical cast:", "value": "SYNCING 6 AGENTS", "status": "complete" },
      { "line": "Formulating opening brief:", "value": "COMPLETED",     "status": "complete" },
      { "line": "Establishing secure connection:", "value": "ACTIVE",   "status": "complete" }
    ],
    "scenario_ready": true
  }

RESPONSE 202: (still assembling)
  {
    "scenario_ready": false,
    "assembly_log": [
      { "line": "Extracting crisis domain:", "value": "ANALYZING...", "status": "in_progress" }
    ],
    "message": "Scenario analyst still running. Retry in 1 second."
  }

NOTE: Frontend polls this at 1s intervals during assembling screen.
      Once scenario_ready=true AND status=active → navigate to War Room.
      The WS stream sends the same data as events — polling is a fallback.
```

---

### GET /api/sessions/{session_id}/scenario/skill/{agent_id}

**Panel:** Debug / Developer tools only
**Purpose:** Read the generated SKILL.md for any agent. Useful for
             transparency and debugging agent behavior.

```
REQUEST:
  Headers: Authorization: Bearer {chairman_token}

RESPONSE 200:
  {
    "agent_id": "atlas_A3F9B2C1",
    "character_name": "ATLAS",
    "role_title": "Strategic Analyst",
    "voice_name": "Orus",
    "skill_md": "---\nname: strategic_analyst\ncharacter: ATLAS\n...",
    "generated_at": "2026-02-26T14:30:15Z",
    "word_count": 487
  }

MEMORY ISOLATION:
  Returns ONLY skill_md (the instruction given to the agent).
  Does NOT return agent's private memory, hidden knowledge,
  or previous statements. Skill.md is the input, not the state.
```

---

## 3. AGENT ROUTES

### GET /api/sessions/{session_id}/agents

**Panel:** Left Panel — Agent Roster (full list)
**Purpose:** Get all agents with their current status.
             Used on initial load and reconnect.

```
REQUEST:
  Headers: Authorization: Bearer {chairman_token}
  Query params:
    status_filter: AgentStatus  // optional, e.g. ?status_filter=conflicted

RESPONSE 200:
  {
    "session_id": "A3F9B2C1",
    "agents": [
      {
        "agent_id":       "atlas_A3F9B2C1",
        "character_name": "ATLAS",
        "role_title":     "Strategic Analyst",
        "identity_color": "#4A9EFF",
        "voice_name":     "Orus",
        "status":         "speaking",
        "trust_score":    72,
        "last_spoke_at":  "2026-02-26T14:32:01Z",
        "last_statement": "Containment window is closing. We need a decision now.",
        "conflict_with":  ["felix_A3F9B2C1"],
        "silence_duration_seconds": 0
      },
      {
        "agent_id":       "nova_A3F9B2C1",
        "character_name": "NOVA",
        "role_title":     "Legal Counsel",
        "identity_color": "#C084FC",
        "voice_name":     "Kore",
        "status":         "thinking",
        "trust_score":    85,
        "last_spoke_at":  "2026-02-26T14:28:44Z",
        "last_statement": "We need legal sign-off before any field action.",
        "conflict_with":  ["felix_A3F9B2C1"],
        "silence_duration_seconds": 197
      }
    ],
    "active_count":    3,
    "silent_count":    2,
    "conflict_count":  1
  }

NOTE:
  'last_statement' = last PUBLIC statement only.
  Private memory, hidden_knowledge, private_commitments
  are NEVER returned by any API endpoint.
```

---

### GET /api/sessions/{session_id}/agents/{agent_id}

**Panel:** Left Panel — Agent Roster (single agent row)
           + Agent Voice Pod (single pod state)
**Purpose:** Get one agent's full public state. Called when
             an agent pod is clicked to see details.

```
REQUEST:
  Headers: Authorization: Bearer {chairman_token}

RESPONSE 200:
  {
    "agent_id":         "felix_A3F9B2C1",
    "character_name":   "FELIX",
    "role_title":       "Field Operations",
    "identity_color":   "#FF6B00",
    "voice_name":       "Fenrir",
    "status":           "conflicted",
    "trust_score":      51,
    "last_spoke_at":    "2026-02-26T14:31:44Z",
    "silence_duration_seconds": 18,
    "conflict_with":    ["nova_A3F9B2C1"],
    "public_positions": {
      // Topics this agent has taken a public stance on
      // (extracted from transcript history by Observer Agent)
      "field_deployment": {
        "position": "Immediate deployment is necessary",
        "stated_at": "2026-02-26T14:29:00Z"
      },
      "timeline": {
        "position": "48-hour window maximum",
        "stated_at": "2026-02-26T14:31:00Z"
      }
    },
    "statement_count":  8,
    "contradiction_count": 1
  }

MEMORY ISOLATION:
  public_positions = extracted from transcripts only.
  NEVER reads agent_memory Firestore collection.
  NEVER exposes hidden_agenda, private_facts,
  private_commitments.
```

---

### PATCH /api/sessions/{session_id}/agents/{agent_id}

**Panel:** Left Panel — Chairman dismisses or modifies an agent
**Purpose:** Chairman actions on a specific agent.

```
REQUEST:
  Headers: Authorization: Bearer {chairman_token}
  Body:
    {
      "action": "dismiss" | "silence" | "address",
      "duration_seconds": int   // for "silence" action only
    }

RESPONSE 200:
  {
    "agent_id": "felix_A3F9B2C1",
    "action_applied": "dismiss",
    "applied_at": "2026-02-26T14:35:00Z",
    "effect": "Agent FELIX has left the room. 4 agents remain."
  }

SIDE EFFECTS for dismiss:
  - Closes that agent's Gemini Live WebSocket
  - Sets agent status to "dismissed" in Firestore
  - Pushes "agent_dismissed" WS event to frontend
  - Agent pod shows empty/dismissed state
  - Agent row removed from roster

SIDE EFFECTS for silence:
  - Agent's Live session receives silence signal
  - Status set to "silent"
  - Restored to "idle" after duration_seconds
```

---

### POST /api/sessions/{session_id}/agents/summon

**Panel:** Left Panel — Summon Agent button
           + Agent Voice Pod — Summon pod slot
**Purpose:** Chairman requests a new agent mid-session.

```
REQUEST:
  Headers: Authorization: Bearer {chairman_token}
  Body:
    {
      "role_description": "I need a board representative",
      // Chairman speaks/types this — system generates the agent
    }

RESPONSE 202:
  {
    "request_id": "uuid4",
    "status": "generating",
    "message": "Generating new agent from role description...",
    "estimated_seconds": 8
  }

SIDE EFFECTS:
  - Runs ScenarioAnalyst mini-call with role_description
  - Generates new SKILL.md for the agent
  - Creates new CrisisAgent instance
  - Opens new Gemini Live session
  - Pushes "agent_assembling" then "agent_ready" WS events
  - Frontend shows summon pod animating → new pod appears

FOLLOW-UP: GET /api/sessions/{session_id}/agents/{new_agent_id}
           Returns the fully initialized agent once ready
```

---

### GET /api/sessions/{session_id}/agents/{agent_id}/transcript

**Panel:** Agent Voice Pod — transcript snippet below pod
**Purpose:** Get full statement history for one agent.
             Used for replay and after-action report.

```
REQUEST:
  Headers: Authorization: Bearer {chairman_token}
  Query params:
    limit: int   // default 20, max 100
    before: ISO  // pagination cursor

RESPONSE 200:
  {
    "agent_id": "felix_A3F9B2C1",
    "character_name": "FELIX",
    "statements": [
      {
        "statement_id": "uuid4",
        "text": "Immediate deployment is our only option. The window...",
        "spoken_at": "2026-02-26T14:29:00Z",
        "duration_seconds": 12,
        "was_interrupted": false,
        "interrupted_by": null,
        "triggered_conflict": "conflict_uuid",   // null if no conflict triggered
        "triggered_decision": null
      },
      ...
    ],
    "total_statements": 8,
    "total_words": 412
  }

MEMORY ISOLATION:
  Returns ONLY text from public transcript.
  Source: session_events collection (agent_speaking_end events)
  Does NOT touch agent_memory collection.
```

---

## 4. CRISIS BOARD ROUTES

### GET /api/sessions/{session_id}/board

**Panel:** Center Main Panel — Crisis Board (full state)
**Purpose:** Load full Crisis Board state on initial render.

```
REQUEST:
  Headers: Authorization: Bearer {chairman_token}
  Query params:
    replay_at: ISO  // optional — get board state at a specific past time

RESPONSE 200:
  {
    "session_id": "A3F9B2C1",
    "last_updated": "2026-02-26T14:32:01Z",
    "agreed_decisions": [
      {
        "decision_id": "uuid4",
        "text": "Activate secondary containment protocol and isolate affected nodes immediately.",
        "agreed_at": "2026-02-26T14:32:01Z",
        "proposed_by": "atlas_A3F9B2C1",
        "agents_agreed": ["atlas_A3F9B2C1", "nova_A3F9B2C1", "oracle_A3F9B2C1"],
        "agents_dissented": ["felix_A3F9B2C1"],
        "locked": false    // true = Chairman pinned it, cannot be undone
      }
    ],
    "open_conflicts": [
      {
        "conflict_id": "uuid4",
        "description": "FELIX insists on immediate field deployment; NOVA flags legal risk of unauthorized action in jurisdiction.",
        "agents_involved": ["felix_A3F9B2C1", "nova_A3F9B2C1"],
        "opened_at": "2026-02-26T14:28:00Z",
        "severity": "high",
        "duration_seconds": 241,
        "resolution": null
      }
    ],
    "critical_intel": [
      {
        "intel_id": "uuid4",
        "text": "Dark web chatter references operation codename matching our incident. Confidence: medium.",
        "source": "CIPHER / OSINT",
        "source_type": "INTERNAL",
        "received_at": "2026-02-26T14:25:00Z",
        "is_escalation": false,
        "pinned": false
      }
    ]
  }
```

---

### GET /api/sessions/{session_id}/board/decisions

**Panel:** Crisis Board — AGREED DECISIONS column only
**Purpose:** Lightweight poll for decision column only.

```
REQUEST:
  Headers: Authorization: Bearer {chairman_token}
  Query params:
    since: ISO   // only return decisions after this timestamp
    limit: int   // default 50

RESPONSE 200:
  {
    "decisions": [ ...array of decision objects... ],
    "count": 2,
    "last_updated": "2026-02-26T14:32:01Z"
  }
```

---

### POST /api/sessions/{session_id}/board/decisions

**Panel:** Crisis Board — Chairman pins a decision manually
**Purpose:** Chairman locks a decision onto the board
             (separate from agent-generated decisions).

```
REQUEST:
  Headers: Authorization: Bearer {chairman_token}
  Body:
    {
      "text": "We will not issue a public statement before 18:00 UTC.",
      "source": "chairman",
      "lock": true    // immediately lock — cannot be removed
    }

RESPONSE 201:
  {
    "decision_id": "uuid4",
    "text": "We will not issue a public statement before 18:00 UTC.",
    "agreed_at": "2026-02-26T14:35:00Z",
    "proposed_by": "chairman",
    "locked": true
  }

SIDE EFFECTS:
  - Writes to crisis_sessions.agreed_decisions array
  - Pushes "decision_agreed" WS event
  - Observer Agent runs analysis on the decision
```

---

### PATCH /api/sessions/{session_id}/board/decisions/{decision_id}

**Panel:** Crisis Board — lock/pin a decision
**Purpose:** Chairman pins (locks) an existing decision.

```
REQUEST:
  Headers: Authorization: Bearer {chairman_token}
  Body:
    {
      "locked": true
    }

RESPONSE 200:
  {
    "decision_id": "uuid4",
    "locked": true,
    "locked_at": "2026-02-26T14:36:00Z"
  }
```

---

### GET /api/sessions/{session_id}/board/conflicts

**Panel:** Crisis Board — OPEN CONFLICTS column only

```
REQUEST:
  Headers: Authorization: Bearer {chairman_token}
  Query params:
    status: "open" | "resolved" | "all"   // default "open"
    severity: "low" | "medium" | "high" | "critical"

RESPONSE 200:
  {
    "conflicts": [
      {
        "conflict_id":     "uuid4",
        "description":     "FELIX insists on immediate field deployment...",
        "agents_involved": ["felix_A3F9B2C1", "nova_A3F9B2C1"],
        "opened_at":       "2026-02-26T14:28:00Z",
        "severity":        "high",
        "duration_seconds": 241,
        "resolution":      null,
        "resolved_at":     null
      }
    ],
    "open_count":     1,
    "resolved_count": 0
  }
```

---

### PATCH /api/sessions/{session_id}/board/conflicts/{conflict_id}

**Panel:** Crisis Board — Chairman resolves a conflict
**Purpose:** Chairman forces a conflict closed.

```
REQUEST:
  Headers: Authorization: Bearer {chairman_token}
  Body:
    {
      "resolution": "Chairman ruling: field deployment approved with legal oversight.",
      "decision_text": "Field deployment approved. NOVA to monitor jurisdiction compliance."
      // If decision_text is provided, auto-creates a corresponding decision
    }

RESPONSE 200:
  {
    "conflict_id": "uuid4",
    "resolved_at": "2026-02-26T14:37:00Z",
    "resolution": "Chairman ruling: field deployment approved with legal oversight.",
    "auto_created_decision_id": "uuid4"
  }

SIDE EFFECTS:
  - Sets conflict.resolution in Firestore
  - If decision_text provided: calls POST /board/decisions internally
  - Pushes "conflict_resolved" WS event
  - Resolution Score increases
```

---

### GET /api/sessions/{session_id}/board/intel

**Panel:** Crisis Board — CRITICAL INTEL column only

```
REQUEST:
  Headers: Authorization: Bearer {chairman_token}
  Query params:
    source_type: FeedSource   // filter by source
    is_escalation: bool       // filter World Agent events only
    since: ISO

RESPONSE 200:
  {
    "intel": [
      {
        "intel_id":     "uuid4",
        "text":         "Dark web chatter references operation codename...",
        "source":       "CIPHER / OSINT",
        "source_type":  "INTERNAL",
        "received_at":  "2026-02-26T14:25:00Z",
        "is_escalation": false,
        "pinned":       false
      }
    ],
    "count": 4,
    "escalation_count": 1
  }
```

---

### POST /api/sessions/{session_id}/board/intel

**Panel:** Crisis Board — Chairman injects intel
**Purpose:** Chairman drops new information into the room.

```
REQUEST:
  Headers: Authorization: Bearer {chairman_token}
  Body:
    {
      "text": "I just received confirmation: the journalist has the documents.",
      "source_type": "INTERNAL",
      "source": "CHAIRMAN / DIRECT",
      "broadcast": true   // if true, all agents receive this in their context
    }

RESPONSE 201:
  {
    "intel_id": "uuid4",
    "text": "...",
    "broadcast_to_agents": 5,
    "received_at": "2026-02-26T14:38:00Z"
  }

SIDE EFFECTS:
  - Writes intel to crisis_sessions.critical_intel
  - If broadcast=true: sends intel text to all agent Live sessions
    as a system message (appears in their context for next turn)
  - Pushes "intel_dropped" WS event
  - Observer Agent re-runs analysis
```

---

### GET /api/sessions/{session_id}/board/timeline

**Panel:** Crisis Board — Replay tab group (NOW / -5m / -10m / -20m)
**Purpose:** Get board state at a specific past moment for replay.

```
REQUEST:
  Headers: Authorization: Bearer {chairman_token}
  Query params:
    at: ISO   // required — point-in-time to query

RESPONSE 200:
  {
    "at": "2026-02-26T14:20:00Z",
    "agreed_decisions": [...],   // only items existing at that timestamp
    "open_conflicts": [...],
    "critical_intel": [...],
    "resolution_score_at_time": 58,
    "threat_level_at_time": "elevated"
  }

NOTE: This is a pure READ of historical data.
      Computed by filtering Firestore events by timestamp.
      No AI processing — pure data replay.
```

---

## 5. CRISIS FEED ROUTES

### GET /api/sessions/{session_id}/feed

**Panel:** Bottom Left — Crisis Feed (full list)
**Purpose:** Load feed items. Called on initial load.

```
REQUEST:
  Headers: Authorization: Bearer {chairman_token}
  Query params:
    source_type: FeedSource   // filter by tab: WORLD, LEGAL, MEDIA, INTERNAL, SOCIAL
    limit: int                // default 30, max 100
    before: ISO               // pagination cursor
    hot_only: bool            // only breaking/critical items

RESPONSE 200:
  {
    "session_id": "A3F9B2C1",
    "items": [
      {
        "feed_id":      "uuid4",
        "text":         "// new intel received from CIPHER / OSINT",
        "source_name":  "SYSTEM",
        "source_type":  "INTERNAL",
        "category_icon": "💬",
        "timestamp":    "2026-02-26T18:30:00Z",
        "is_hot":       false,
        "is_breaking":  false,
        "metric":       null
      },
      {
        "feed_id":      "uuid4",
        "text":         "Anonymous source contacts Reuters: 'The AI knew. Management was warned 3 months ago.'",
        "source_name":  "📰 REUTERS",
        "source_type":  "MEDIA",
        "category_icon": "📰",
        "timestamp":    "2026-02-26T14:31:22Z",
        "is_hot":       true,
        "is_breaking":  true,
        "metric":       "↗️ 82K impressions · 3 min ago"
      }
    ],
    "tab_counts": {
      "WORLD":    3,
      "LEGAL":    2,
      "MEDIA":    5,
      "INTERNAL": 4,
      "SOCIAL":   7
    },
    "unread_counts": {
      "WORLD":    1,
      "LEGAL":    0,
      "MEDIA":    2,
      "INTERNAL": 0,
      "SOCIAL":   3
    },
    "has_more": true,
    "next_cursor": "2026-02-26T14:20:00Z"
  }
```

---

### GET /api/sessions/{session_id}/feed/world

**Panel:** Crisis Feed — WORLD tab specifically
**Purpose:** Get World Agent-generated events (crisis escalations).

```
REQUEST:
  Headers: Authorization: Bearer {chairman_token}
  Query params:
    limit: int   // default 10

RESPONSE 200:
  {
    "world_events": [
      {
        "event_id":          "uuid4",
        "text":              "External actor attempted perimeter breach at 14:29 UTC. Three vectors confirmed.",
        "type":              "INTERNAL",
        "fired_at":          "2026-02-26T14:29:00Z",
        "score_impact":      -8,
        "threat_level_after": "critical"
      }
    ],
    "next_escalation_at": "2026-02-26T18:35:00Z",
    "next_escalation_in_seconds": 298
  }
```

---

### PATCH /api/sessions/{session_id}/feed/{feed_id}

**Panel:** Crisis Feed — mark item as read
**Purpose:** Track which feed items have been read (for unread badge counts).

```
REQUEST:
  Headers: Authorization: Bearer {chairman_token}
  Body: { "read": true }

RESPONSE 200:
  { "feed_id": "uuid4", "read": true }

NOTE: Stored per session, not per user.
      Unread counts recalculated and pushed via WS.
```

---

## 6. AGENT VOICE PODS (AGENT FEEDS)

### GET /api/sessions/{session_id}/pods

**Panel:** Bottom Center — Agent Feeds (all pods state)
**Purpose:** Get current speaking/thinking/status state of all agent pods.
             Used for initial render and reconnect.

```
REQUEST:
  Headers: Authorization: Bearer {chairman_token}
  Query params:
    filter: "all" | "active" | "conflicted"   // matches tab bar in UI

RESPONSE 200:
  {
    "session_id": "A3F9B2C1",
    "filter_applied": "all",
    "pods": [
      {
        "agent_id":         "atlas_A3F9B2C1",
        "character_name":   "ATLAS",
        "role_title":       "Strategic Analyst",
        "identity_color":   "#4A9EFF",
        "status":           "thinking",
        "transcript_snippet": "Containment window is cl...",
        "conflict_with_name": null,
        "waveform_active":   false,
        "last_audio_at":     "2026-02-26T14:32:01Z"
      },
      {
        "agent_id":         "felix_A3F9B2C1",
        "character_name":   "FELIX",
        "role_title":       "Field Operations",
        "identity_color":   "#FF6B00",
        "status":           "conflicted",
        "transcript_snippet": "Field deployment cannot wait...",
        "conflict_with_name": "NOVA",
        "waveform_active":   false,
        "last_audio_at":     "2026-02-26T14:31:44Z"
      }
    ],
    "active_count":    2,
    "conflicted_count": 1,
    "thinking_count":  2,
    "silent_count":    0
  }
```

---

### GET /api/sessions/{session_id}/pods/{agent_id}

**Panel:** Bottom Center — Single agent pod (detailed view on click)
**Purpose:** Get full pod state + last N transcript lines for one agent.

```
REQUEST:
  Headers: Authorization: Bearer {chairman_token}

RESPONSE 200:
  {
    "agent_id":       "felix_A3F9B2C1",
    "character_name": "FELIX",
    "role_title":     "Field Operations",
    "identity_color": "#FF6B00",
    "voice_name":     "Fenrir",
    "status":         "conflicted",
    "conflict_with":  [{ "agent_id": "nova_A3F9B2C1", "name": "NOVA" }],
    "recent_transcript": [
      // Last 3 statements spoken by this agent
      "Field deployment cannot wait. Every hour we delay...",
      "NOVA's legal position is theoretical. The threat is real.",
      "I need authorization now or I go without it."
    ],
    "waveform_active":    false,
    "trust_score":        51,
    "statements_today":   8,
    "interrupted_count":  2,
    "interruption_count": 3
  }
```

---

## 7. ROOM INTELLIGENCE ROUTES

### GET /api/sessions/{session_id}/intel

**Panel:** Bottom Right Top — Room Intelligence panel
**Purpose:** Get all Observer Agent insights. Initial load + reconnect.

```
REQUEST:
  Headers: Authorization: Bearer {chairman_token}
  Query params:
    type: InsightType   // filter by contradiction|alliance|blind_spot|mood_shift
    limit: int          // default 10
    since: ISO

RESPONSE 200:
  {
    "session_id": "A3F9B2C1",
    "insights": [
      {
        "insight_id":         "uuid4",
        "type":               "contradiction",
        "title":              "CONTRADICTION",
        "body":               "ATLAS claims containment is stable, but CIPHER reports perimeter breach.",
        "agents_referenced":  ["atlas_A3F9B2C1", "cipher_A3F9B2C1"],
        "detected_at":        "2026-02-26T14:36:12Z",
        "severity":           "high",
        "resolved":           false
      },
      {
        "insight_id":         "uuid4",
        "type":               "alliance",
        "title":              "ALLIANCE FORMING",
        "body":               "NOVA and CIPHER are aligning on legal-intel data protocol.",
        "agents_referenced":  ["nova_A3F9B2C1", "cipher_A3F9B2C1"],
        "detected_at":        "2026-02-26T14:34:45Z",
        "severity":           "medium",
        "resolved":           false
      },
      {
        "insight_id":         "uuid4",
        "type":               "blind_spot",
        "title":              "CRITICAL UNASKED",
        "body":               "No response plan for public data leak in European markets.",
        "agents_referenced":  [],
        "detected_at":        "2026-02-26T14:33:28Z",
        "severity":           "critical",
        "resolved":           false
      }
    ],
    "insight_counts": {
      "contradiction": 1,
      "alliance":      1,
      "blind_spot":    1,
      "mood_shift":    0
    }
  }

MEMORY ISOLATION:
  Observer Agent computes insights from:
    - Public transcripts (session_events)
    - crisis_sessions shared state
  Observer NEVER reads agent_memory collections.
```

---

### GET /api/sessions/{session_id}/intel/trust

**Panel:** Bottom Right Top — Trust Score bars at bottom of Room Intelligence
**Purpose:** Get current trust scores for all agents.

```
REQUEST:
  Headers: Authorization: Bearer {chairman_token}

RESPONSE 200:
  {
    "session_id": "A3F9B2C1",
    "trust_scores": [
      {
        "agent_id":         "atlas_A3F9B2C1",
        "character_name":   "ATLAS",
        "score":            72,
        "trend":            "stable",
        "delta_last_turn":  0,
        "reason":           "Consistent on containment stance",
        "contradiction_count": 0
      },
      {
        "agent_id":         "nova_A3F9B2C1",
        "character_name":   "NOVA",
        "score":            85,
        "trend":            "rising",
        "delta_last_turn":  +3,
        "reason":           "↑ Legally consistent, cited precedent correctly",
        "contradiction_count": 0
      },
      {
        "agent_id":         "felix_A3F9B2C1",
        "character_name":   "FELIX",
        "score":            51,
        "trend":            "falling",
        "delta_last_turn":  -7,
        "reason":           "↓ Contradicted timeline commitment",
        "contradiction_count": 1
      }
    ],
    "last_updated": "2026-02-26T14:32:01Z"
  }

MEMORY ISOLATION:
  Trust scores computed by Observer Agent.
  Stored in crisis_sessions.agent_roster[].trust_score.
  Does NOT read agent_memory collections.
```

---

### GET /api/sessions/{session_id}/intel/trust/{agent_id}/history

**Panel:** Room Intelligence — trust score trend (hover/detail view)
**Purpose:** Get the trust score history for one agent (sparkline data).

```
REQUEST:
  Headers: Authorization: Bearer {chairman_token}

RESPONSE 200:
  {
    "agent_id": "felix_A3F9B2C1",
    "history": [
      { "score": 70, "at": "2026-02-26T14:28:00Z", "reason": "Initial" },
      { "score": 68, "at": "2026-02-26T14:29:00Z", "reason": "↓ Slight inconsistency" },
      { "score": 58, "at": "2026-02-26T14:31:00Z", "reason": "↓ Contradicted timeline" },
      { "score": 51, "at": "2026-02-26T14:32:00Z", "reason": "↓ Pushed back on board decision" }
    ],
    "current_score": 51,
    "starting_score": 70
  }
```

---

## 8. CRISIS POSTURE ROUTES

### GET /api/sessions/{session_id}/posture

**Panel:** Bottom Right Middle — Crisis Posture panel
**Purpose:** Get current posture values for all three axes.

```
REQUEST:
  Headers: Authorization: Bearer {chairman_token}

RESPONSE 200:
  {
    "session_id": "A3F9B2C1",
    "last_updated": "2026-02-26T14:32:01Z",
    "axes": {
      "public_exposure": {
        "value":     78,
        "status":    "high",
        "trend":     "rising",
        "trend_arrow": "↑",
        "sub_metric": "Viral velocity: RISING • ↑ RISING",
        "driver":    "Media coverage escalating post-leak"
      },
      "legal_exposure": {
        "value":     62,
        "status":    "elevated",
        "trend":     "stable",
        "trend_arrow": "→",
        "sub_metric": "Liability scan active • → STABLE",
        "driver":    "Class action risk if deployment proceeds"
      },
      "internal_stability": {
        "value":     71,
        "status":    "contained",
        "trend":     "falling",
        "trend_arrow": "↓",
        "sub_metric": "Team alignment nominal • ↓ FALLING",
        "driver":    "FELIX/NOVA conflict eroding cohesion"
      }
    }
  }

NOTE: public_exposure and legal_exposure: higher = worse.
      internal_stability: higher = better (inverted axis in UI).
```

---

### GET /api/sessions/{session_id}/posture/history

**Panel:** Crisis Posture — trend data
**Purpose:** Get posture value history for sparklines / trend arrows.

```
REQUEST:
  Headers: Authorization: Bearer {chairman_token}
  Query params:
    axis: "public_exposure" | "legal_exposure" | "internal_stability"
    limit: int   // default 20

RESPONSE 200:
  {
    "axis": "public_exposure",
    "history": [
      { "value": 55, "at": "2026-02-26T14:00:00Z" },
      { "value": 60, "at": "2026-02-26T14:10:00Z" },
      { "value": 68, "at": "2026-02-26T14:20:00Z" },
      { "value": 78, "at": "2026-02-26T14:32:00Z" }
    ]
  }
```

---

## 9. RESOLUTION SCORE ROUTES

### GET /api/sessions/{session_id}/score

**Panel:** Bottom Right Bottom — Resolution Score panel
**Purpose:** Get current resolution score, trend, driver, next escalation timer.

```
REQUEST:
  Headers: Authorization: Bearer {chairman_token}

RESPONSE 200:
  {
    "session_id":         "A3F9B2C1",
    "score":              44,
    "label":              "RECOVERING",
    "trend":              "improving",
    "trend_arrow":        "↑",
    "delta_last_change":  +3,
    "score_history":      [58, 55, 50, 46, 44, 44, 47],   // last 20 values for sparkline
    "driver":             "Containment decision reduced legal exposure",
    "target":             70,
    "target_label":       "Target: 70+ to stabilize outcome",
    "next_escalation": {
      "at":               "2026-02-26T18:35:00Z",
      "in_seconds":       298,
      "formatted":        "4:58",
      "blinking":         false    // true when < 60 seconds
    },
    "threat_level": "critical",
    "last_updated": "2026-02-26T14:32:01Z"
  }

Score label mapping:
  70–100: "RESOLVED"
  50–69:  "RECOVERING"
  30–49:  "CRITICAL"
  0–29:   "MELTDOWN"
```

---

### GET /api/sessions/{session_id}/score/history

**Panel:** Resolution Score — sparkline chart
**Purpose:** Full score history with timestamps for animated sparkline.

```
REQUEST:
  Headers: Authorization: Bearer {chairman_token}
  Query params:
    limit: int   // default 30

RESPONSE 200:
  {
    "history": [
      { "score": 58, "at": "2026-02-26T14:00:00Z", "event": "Session started" },
      { "score": 52, "at": "2026-02-26T14:05:00Z", "event": "First escalation: Media leak" },
      { "score": 48, "at": "2026-02-26T14:12:00Z", "event": "Conflict opened: FELIX vs NOVA" },
      { "score": 44, "at": "2026-02-26T14:32:00Z", "event": "Decision agreed: Containment" }
    ],
    "current_score": 44,
    "starting_score": 58,
    "net_change": -14
  }
```

---

## 10. WORLD AGENT ROUTES

### GET /api/sessions/{session_id}/world

**Panel:** Crisis Feed (WORLD tab) + Crisis Board escalation banner
**Purpose:** Get World Agent status and scheduled escalation events.

```
REQUEST:
  Headers: Authorization: Bearer {chairman_token}

RESPONSE 200:
  {
    "session_id": "A3F9B2C1",
    "world_agent_active": true,
    "escalations_fired": 1,
    "escalations_remaining": 2,
    "next_escalation": {
      "at":        "2026-02-26T18:35:00Z",
      "in_seconds": 298,
      "type":      "LEGAL",
      "preview":   null    // null — don't show the Chairman what's coming
    },
    "fired_events": [
      {
        "event_id":           "uuid4",
        "text":               "External actor attempted perimeter breach...",
        "type":               "INTERNAL",
        "fired_at":           "2026-02-26T14:29:00Z",
        "score_impact":       -8,
        "threat_level_after": "critical"
      }
    ]
  }
```

---

### POST /api/sessions/{session_id}/world/escalate

**Panel:** Chairman Command Bar — Chairman triggers manual escalation
**Purpose:** Chairman forces an unscheduled escalation event.
             Used for testing or dramatic effect.

```
REQUEST:
  Headers: Authorization: Bearer {chairman_token}
  Body:
    {
      "event_text": "The board has called an emergency session in 30 minutes.",
      "event_type": "INTERNAL",
      "score_impact": -5   // optional override, default -8
    }

RESPONSE 201:
  {
    "event_id":     "uuid4",
    "fired_at":     "2026-02-26T14:38:00Z",
    "score_impact": -5,
    "broadcast_to_agents": 5
  }

SIDE EFFECTS:
  - Pushes "crisis_escalation" WS event (triggers full-screen flash)
  - Adds to crisis_feed as WORLD item
  - All agents receive escalation context in their next turn
  - Resolution Score decreases
```

---

## 11. CHAIRMAN ROUTES

### POST /api/sessions/{session_id}/chairman/command

**Panel:** Chairman Command Bar — text/voice directive
**Purpose:** Chairman sends a text command to the room or a specific agent.
             (Voice is handled via WebSocket audio stream directly.)

```
REQUEST:
  Headers: Authorization: Bearer {chairman_token}
  Body:
    {
      "text": "NOVA, what is the legal minimum disclosure window?",
      "target_agent_id": "nova_A3F9B2C1",   // null = broadcast to full room
      "command_type": "question" | "directive" | "vote_call" | "inject_intel"
    }

RESPONSE 200:
  {
    "command_id": "uuid4",
    "text": "NOVA, what is the legal minimum disclosure window?",
    "target_agent_id": "nova_A3F9B2C1",
    "routed_to": ["nova_A3F9B2C1"],
    "issued_at": "2026-02-26T14:38:00Z"
  }

SIDE EFFECTS:
  - Text injected into target agent's Gemini Live session
    as a system turn so they respond to it
  - Pushes "chairman_spoke" WS event (shows in command bar transcript)
  - Observer Agent logs the command for consistency tracking
```

---

### POST /api/sessions/{session_id}/chairman/vote

**Panel:** Chairman Command Bar — FORCE VOTE button
**Purpose:** Chairman calls a vote on a specific question.
             All agents must respond with a position.

```
REQUEST:
  Headers: Authorization: Bearer {chairman_token}
  Body:
    {
      "question": "Do we issue a public statement before 15:00 UTC? YES or NO.",
      "time_limit_seconds": 120   // agents must respond within this window
    }

RESPONSE 202:
  {
    "vote_id":    "uuid4",
    "question":   "Do we issue a public statement before 15:00 UTC?",
    "started_at": "2026-02-26T14:39:00Z",
    "ends_at":    "2026-02-26T14:41:00Z",
    "agents_voting": ["atlas_A3F9B2C1", "nova_A3F9B2C1", "cipher_A3F9B2C1", "felix_A3F9B2C1", "oracle_A3F9B2C1"]
  }

VOTE RESULT (returned via WebSocket "vote_result" event):
  {
    "vote_id":  "uuid4",
    "question": "...",
    "results": [
      { "agent_id": "atlas_A3F9B2C1",  "name": "ATLAS", "vote": "YES", "reasoning": "..." },
      { "agent_id": "nova_A3F9B2C1",   "name": "NOVA",  "vote": "YES", "reasoning": "..." },
      { "agent_id": "felix_A3F9B2C1",  "name": "FELIX", "vote": "NO",  "reasoning": "..." },
      { "agent_id": "cipher_A3F9B2C1", "name": "CIPHER","vote": "YES", "reasoning": "..." },
      { "agent_id": "oracle_A3F9B2C1", "name": "ORACLE","vote": "YES", "reasoning": "..." }
    ],
    "majority": "YES",
    "vote_count": { "YES": 4, "NO": 1 },
    "auto_create_decision": true,
    "decision_text": "Majority voted: Issue public statement before 15:00 UTC."
  }
```

---

### GET /api/sessions/{session_id}/chairman/commands

**Panel:** Chairman Command Bar — command history
**Purpose:** Get history of chairman commands (for after-action report).

```
REQUEST:
  Headers: Authorization: Bearer {chairman_token}
  Query params:
    limit: int   // default 20

RESPONSE 200:
  {
    "commands": [
      {
        "command_id":     "uuid4",
        "text":           "NOVA, what is the legal minimum disclosure window?",
        "target_agent_id": "nova_A3F9B2C1",
        "command_type":   "question",
        "issued_at":      "2026-02-26T14:38:00Z"
      }
    ],
    "count": 5
  }
```

---

## 12. VOICE ROUTES

### POST /api/sessions/{session_id}/voice/token

**Panel:** Chairman Command Bar — mic button initialization
**Purpose:** Get an ephemeral token for the Chairman's own voice session.
             (Agent voice sessions are managed server-side.
              Chairman needs a client-side token to send audio.)

```
REQUEST:
  Headers: Authorization: Bearer {chairman_token}

RESPONSE 200:
  {
    "token":      "ephemeral_token_string",
    "expires_at": "2026-02-26T15:30:00Z",
    "ws_audio_url": "wss://api.warroom.app/ws/A3F9B2C1/audio",
    "sample_rate": 16000,
    "channels": 1,
    "format": "pcm_16bit"
  }

NOTE: Chairman audio goes to a separate WebSocket endpoint
      /ws/{session_id}/audio (not the main event stream).
      Gateway routes audio to target agent's Live session.
```

---

### GET /api/sessions/{session_id}/voice/status

**Panel:** Top Command Bar — MIC STATUS indicator
           + Agent Voice Pods — active/idle status
**Purpose:** Check voice session health for all agents.

```
REQUEST:
  Headers: Authorization: Bearer {chairman_token}

RESPONSE 200:
  {
    "chairman_mic":   "muted",   // "active" | "muted" | "inactive"
    "agent_sessions": [
      {
        "agent_id":      "atlas_A3F9B2C1",
        "voice_active":  true,
        "voice_name":    "Orus",
        "latency_ms":    120,
        "health":        "good"
      },
      {
        "agent_id":      "nova_A3F9B2C1",
        "voice_active":  true,
        "voice_name":    "Kore",
        "latency_ms":    98,
        "health":        "good"
      }
    ],
    "all_healthy": true
  }
```

---

### PATCH /api/sessions/{session_id}/voice/chairman

**Panel:** Top Command Bar — MIC MUTED / MIC ACTIVE toggle
**Purpose:** Mute/unmute chairman mic.

```
REQUEST:
  Headers: Authorization: Bearer {chairman_token}
  Body: { "muted": true | false }

RESPONSE 200:
  {
    "chairman_mic": "muted",   // updated state
    "applied_at": "2026-02-26T14:40:00Z"
  }

SIDE EFFECTS:
  - Pushes "chairman_mic_status" WS event
  - Frontend top bar updates immediately
```

---

## 13. RESOLUTION & AFTER-ACTION ROUTES

### POST /api/sessions/{session_id}/resolution

**Panel:** Resolution Mode overlay (full screen)
**Purpose:** Chairman calls resolution. Triggers final agent positions.

```
REQUEST:
  Headers: Authorization: Bearer {chairman_token}
  Body:
    {
      "final_decision": "We issue a limited public statement at 17:00 UTC, concurrent with field deployment under legal oversight."
    }

RESPONSE 200:
  {
    "resolution_id":    "uuid4",
    "final_decision":   "We issue a limited public statement...",
    "resolved_at":      "2026-02-26T14:42:00Z",
    "processing":       true,
    "message":          "Generating agent final positions and projected futures..."
  }

SIDE EFFECTS:
  - All agents generate final_position synchronously
  - Pushes "agent_final_position" WS event per agent
  - Pushes "session_resolved" WS event when all done
  - Generates after-action report async
  - Sets session.status = "closed"
```

---

### GET /api/sessions/{session_id}/report

**Panel:** After-Action Report screen (separate page)
**Purpose:** Get the complete after-action report for the session.

```
REQUEST:
  Headers: Authorization: Bearer {chairman_token}

RESPONSE 200:
  {
    "session_id":     "A3F9B2C1",
    "crisis_title":   "OPERATION BLACKSITE",
    "duration":       {
      "started_at": "2026-02-26T14:30:00Z",
      "ended_at":   "2026-02-26T15:02:00Z",
      "total_minutes": 32
    },
    "final_decision": "We issue a limited public statement at 17:00 UTC...",
    "final_score":    61,
    "final_threat_level": "elevated",

    "agent_positions": [
      {
        "agent_id":     "atlas_A3F9B2C1",
        "name":         "ATLAS",
        "verdict":      "Statement approved. Containment first, disclosure second.",
        "alignment":    "agreed",     // "agreed" | "dissented" | "neutral"
        "final_trust":  72
      },
      ...
    ],

    "projected_futures": [
      {
        "scenario": "best",
        "probability": "35%",
        "description": "Public statement lands without leak escalation. Legal exposure reduces over 72 hours."
      },
      {
        "scenario": "expected",
        "probability": "50%",
        "description": "Media picks up on the delay. Moderate reputational damage but legally defensible."
      },
      {
        "scenario": "worst",
        "probability": "15%",
        "description": "Journalist publishes before 17:00. Statement appears reactive. Full regulatory review."
      }
    ],

    "key_moments": [
      {
        "at":          "2026-02-26T14:28:00Z",
        "type":        "conflict_opened",
        "description": "FELIX vs NOVA conflict on field deployment changed room dynamic"
      },
      {
        "at":          "2026-02-26T14:29:00Z",
        "type":        "escalation",
        "description": "World Agent escalation dropped score from 52 to 44"
      }
    ],

    "statistics": {
      "total_statements":   42,
      "total_conflicts":    3,
      "conflicts_resolved": 2,
      "decisions_made":     4,
      "escalations":        1,
      "chairman_commands":  5,
      "votes_called":       1
    },

    "replay_available": true,
    "replay_start_url": "/api/sessions/A3F9B2C1/board/timeline?at=2026-02-26T14:30:00Z"
  }
```

---

## 14. WEBSOCKET SPECIFICATION

### WS /ws/{session_id}

**Purpose:** Primary real-time channel. Frontend opens this FIRST,
             before any REST calls. ALL live updates come through here.
             No polling needed once WS is established.

```
Connection:
  URL: wss://api.warroom.app/ws/{session_id}
  Query: ?token={chairman_token}

FRONTEND → SERVER messages:

  1. Ping (keepalive every 25s):
     { "type": "ping" }

  2. Chairman audio (PCM 16kHz base64):
     {
       "type":            "chairman_audio",
       "audio":           "base64_pcm_string",
       "target_agent_id": "nova_A3F9B2C1" | null,
       "transcript":      "NOVA, answer the question."
     }

  3. Chairman text command:
     {
       "type":            "chairman_command",
       "command":         "force_vote" | "dismiss_agent" | "pause" | "inject_intel",
       "params":          { ...command-specific params... }
     }

  4. Mark event consumed (for replay):
     { "type": "consumed", "event_id": "uuid4" }


SERVER → FRONTEND events (all follow this envelope):
  {
    "event_id":    "uuid4",
    "session_id":  "A3F9B2C1",
    "event_type":  "[see below]",
    "timestamp":   "ISO8601",
    "payload":     { ...event-specific... }
  }

COMPLETE EVENT TYPE LIST:

  ── SESSION ─────────────────────────────────────────────────
  session_status          → Briefing screen loading log update
  session_ready           → Navigate to War Room
  session_paused          → All pods show PAUSED
  session_resumed         → Restore from pause
  timer_tick              → Every second { seconds_remaining, formatted }

  ── AGENTS ──────────────────────────────────────────────────
  agent_assembling        → Briefing screen: reveal agent card
  agent_ready             → New summoned agent ready
  agent_dismissed         → Remove agent from roster + pods
  agent_status_change     → Update roster dot + pod border/state
  agent_speaking_start    → Activate waveform on pod
  agent_speaking_chunk    → Stream transcript + audio to pod
  agent_speaking_end      → Stop waveform, finalize transcript
  agent_thinking          → Show thinking dots on pod
  agent_interrupted       → Show interrupt flash on pod
  agent_final_position    → Resolution overlay: agent verdict card

  ── CRISIS BOARD ────────────────────────────────────────────
  decision_agreed         → Add card to AGREED DECISIONS column
  conflict_opened         → Add card to OPEN CONFLICTS column
  conflict_resolved       → Remove/grey-out conflict card
  intel_dropped           → Add card to CRITICAL INTEL column
  board_updated           → Generic board refresh signal

  ── CRISIS FEED ─────────────────────────────────────────────
  feed_item               → Add item to feed (specific source_type tab)
  feed_unread_count       → Update tab badge counts

  ── ROOM INTELLIGENCE ───────────────────────────────────────
  observer_insight        → New insight card in Room Intelligence
  trust_score_update      → Animate trust bar for one agent

  ── POSTURE & SCORE ─────────────────────────────────────────
  posture_update          → Update all three axis bars
  score_update            → Animate resolution score number + sparkline
  threat_level_change     → Update top bar threat badge + full UI color shift

  ── WORLD AGENT ─────────────────────────────────────────────
  crisis_escalation       → Full screen flash + all panels react
  next_escalation_timer   → Update "Next escalation in: X:XX" countdown

  ── CHAIRMAN ────────────────────────────────────────────────
  chairman_spoke          → Show transcript in command bar
  chairman_mic_status     → Update MIC ACTIVE/MUTED indicator
  vote_result             → Show vote result overlay

  ── RESOLUTION ──────────────────────────────────────────────
  resolution_mode_start   → Show resolution overlay
  session_resolved        → Navigate to after-action report
```

---

### WS /ws/{session_id}/audio

**Purpose:** Dedicated audio stream for Chairman voice input.
             Separate from main event stream to avoid
             audio data bloating event logs.

```
Connection:
  URL: wss://api.warroom.app/ws/{session_id}/audio
  Query: ?token={ephemeral_audio_token}   // from POST /voice/token

FRONTEND → SERVER:
  Raw PCM audio bytes (16kHz, 16-bit, mono)
  Server reads continuously, applies VAD,
  routes speech segments to target agent

SERVER → FRONTEND:
  { "type": "vad_speech_start" }     // you started speaking
  { "type": "vad_speech_end" }       // you stopped
  { "type": "transcript", "text": "NOVA, answer the question." }
  { "type": "routed_to", "agent_id": "nova_A3F9B2C1" }
```

---

## 15. COMPLETE ROUTE INDEX

```
SESSION
  POST   /api/sessions
  GET    /api/sessions/{session_id}
  PATCH  /api/sessions/{session_id}
  DELETE /api/sessions/{session_id}

SCENARIO
  GET    /api/sessions/{session_id}/scenario
  GET    /api/sessions/{session_id}/scenario/skill/{agent_id}

AGENTS
  GET    /api/sessions/{session_id}/agents
  GET    /api/sessions/{session_id}/agents/{agent_id}
  PATCH  /api/sessions/{session_id}/agents/{agent_id}
  POST   /api/sessions/{session_id}/agents/summon
  GET    /api/sessions/{session_id}/agents/{agent_id}/transcript

CRISIS BOARD
  GET    /api/sessions/{session_id}/board
  GET    /api/sessions/{session_id}/board/decisions
  POST   /api/sessions/{session_id}/board/decisions
  PATCH  /api/sessions/{session_id}/board/decisions/{decision_id}
  GET    /api/sessions/{session_id}/board/conflicts
  PATCH  /api/sessions/{session_id}/board/conflicts/{conflict_id}
  GET    /api/sessions/{session_id}/board/intel
  POST   /api/sessions/{session_id}/board/intel
  GET    /api/sessions/{session_id}/board/timeline

CRISIS FEED
  GET    /api/sessions/{session_id}/feed
  GET    /api/sessions/{session_id}/feed/world
  PATCH  /api/sessions/{session_id}/feed/{feed_id}

AGENT PODS
  GET    /api/sessions/{session_id}/pods
  GET    /api/sessions/{session_id}/pods/{agent_id}

ROOM INTELLIGENCE
  GET    /api/sessions/{session_id}/intel
  GET    /api/sessions/{session_id}/intel/trust
  GET    /api/sessions/{session_id}/intel/trust/{agent_id}/history

CRISIS POSTURE
  GET    /api/sessions/{session_id}/posture
  GET    /api/sessions/{session_id}/posture/history

RESOLUTION SCORE
  GET    /api/sessions/{session_id}/score
  GET    /api/sessions/{session_id}/score/history

WORLD AGENT
  GET    /api/sessions/{session_id}/world
  POST   /api/sessions/{session_id}/world/escalate

CHAIRMAN
  POST   /api/sessions/{session_id}/chairman/command
  POST   /api/sessions/{session_id}/chairman/vote
  GET    /api/sessions/{session_id}/chairman/commands

VOICE
  POST   /api/sessions/{session_id}/voice/token
  GET    /api/sessions/{session_id}/voice/status
  PATCH  /api/sessions/{session_id}/voice/chairman

RESOLUTION
  POST   /api/sessions/{session_id}/resolution
  GET    /api/sessions/{session_id}/report

WEBSOCKET
  WS     /ws/{session_id}            ← main event stream
  WS     /ws/{session_id}/audio      ← chairman audio stream

TOTAL: 35 REST endpoints + 2 WebSocket endpoints
```

---

## 16. FRONTEND ↔ API PANEL WIRING MAP

```
PANEL                    INITIAL LOAD              LIVE UPDATES (WS events)
──────────────────────── ──────────────────────    ─────────────────────────────────
Top Command Bar          GET /sessions/{id}        timer_tick
                                                   threat_level_change
                                                   chairman_mic_status
                                                   session_paused/resumed

Left: Agent Roster       GET /agents               agent_status_change
                                                   agent_assembling
                                                   agent_dismissed
                                                   trust_score_update

Center: Crisis Board     GET /board                decision_agreed
                                                   conflict_opened/resolved
                                                   intel_dropped
                                                   crisis_escalation (banner)

Bottom Left: Crisis Feed GET /feed                 feed_item
                         GET /feed/world           feed_unread_count

Bottom Center: Pods      GET /pods                 agent_speaking_start/chunk/end
                                                   agent_thinking
                                                   agent_interrupted
                                                   agent_status_change

Bottom Right Top:        GET /intel                observer_insight
Room Intelligence        GET /intel/trust          trust_score_update

Bottom Right Mid:        GET /posture              posture_update
Crisis Posture

Bottom Right Bot:        GET /score                score_update
Resolution Score                                   next_escalation_timer

Chairman Command Bar     GET /voice/status         chairman_spoke
                                                   vad_speech_start/end
                                                   (audio via /ws/{id}/audio)

Briefing Screen          GET /scenario             session_status
(assembling)                                       agent_assembling
                                                   session_ready
```

---

## 17. MEMORY LEAKAGE PREVENTION SUMMARY

```
API LEVEL RULES:
  ✅ No endpoint ever returns agent_memory Firestore documents
  ✅ /agents/{agent_id} returns only public state from crisis_sessions
  ✅ Trust scores stored in crisis_sessions, not agent_memory
  ✅ Transcripts come from session_events (append-only log)
  ✅ hidden_agenda, private_facts, private_commitments:
     NEVER appear in any API response
  ✅ /scenario/skill/{agent_id} returns skill_md (input to agent)
     but not agent's current memory state

AGENT ISOLATION RULES:
  ✅ Agent tools can only write to their OWN agent_memory doc
  ✅ read_other_agent_last_statement() = read ONE field from
     crisis_sessions.agent_roster[].last_statement (not memory)
  ✅ Observer Agent reads only transcripts + shared crisis state
  ✅ World Agent reads only crisis_sessions (no agent memory)
  ✅ Each agent has its own InMemorySessionService (ADK)
  ✅ Each agent has its own Gemini Live WebSocket connection

AUTH RULES:
  ✅ chairman_token required on every endpoint
  ✅ Token is session-scoped (not reusable across sessions)
  ✅ Ephemeral audio token expires in 1 hour
  ✅ No cross-session data access possible
```

---

*War Room API Specification v1.0*
*35 REST endpoints + 2 WebSocket streams*
*Maps 1:1 to frontend panels defined in Design Spec v1.0*
