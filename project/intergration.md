# ⚔️ WAR ROOM — Frontend ↔ Backend Integration Guide

## The Complete Flow: How Every Panel Gets Its Data

> **How to read this:** Each section = one screen or panel.
> For each panel: what to call, when to call it, what you get back,
> what WS events keep it alive, and what the user action triggers.

---

## THE GOLDEN RULE (READ THIS FIRST)

```
1. Open WebSocket BEFORE calling POST /api/sessions
2. REST calls = initial hydration only (one-time on load)
3. WebSocket = everything that moves after that
4. Never re-fetch a panel after initial load — WS keeps it current
5. chairman_token lives in memory/localStorage — send it with EVERY request
```

---

## SCREEN 0 — LANDING / INPUT

**File you're building:** `pages/Landing.jsx`

### What happens when user types their crisis

```
USER ACTION:   Types crisis description → clicks "ASSEMBLE THE ROOM"

STEP 1 — Open WebSocket FIRST (before any API call)
  const ws = new WebSocket(`wss://api/ws/PENDING?token=PENDING`)
  // You don't have session_id yet. Use a pre-session channel or
  // open AFTER POST returns. The key: catch events from the first second.
  
  Recommended approach:
  - Call POST /api/sessions
  - Response gives you session_id + chairman_token + ws_url
  - IMMEDIATELY open WS with those values
  - Backend buffers early events so you don't miss them

STEP 2 — Call POST /api/sessions
  METHOD: POST
  URL:    /api/sessions
  BODY:   {
    "crisis_input":            "My hospital AI misdiagnosed 200 patients...",
    "chairman_name":           "DIRECTOR",         // optional
    "session_duration_minutes": 30                 // optional, default 30
  }

  RESPONSE 201:
  {
    "session_id":      "A3F9B2C1",
    "chairman_token":  "uuid4-string",
    "status":          "assembling",
    "ws_url":          "wss://api/ws/A3F9B2C1",
    "created_at":      "2026-02-26T14:30:00Z",
    "message":         "Crisis received. Assembling your team."
  }

STEP 3 — Store credentials
  localStorage.setItem('session_id',      data.session_id)
  localStorage.setItem('chairman_token',  data.chairman_token)

STEP 4 — Open WebSocket
  const ws = new WebSocket(`${data.ws_url}?token=${data.chairman_token}`)

STEP 5 — Navigate to Briefing Room
  router.push(`/session/${data.session_id}/briefing`)
```

### Error handling

```
422 → { "error": "crisis_input_too_short" }
  Show: "Min 10 characters required" under input field

500 → Server error
  Show: "Something went wrong. Try again." — do NOT retry automatically
```

---

## SCREEN 1 — BRIEFING ROOM (ASSEMBLING)

**File you're building:** `pages/Briefing.jsx`
**This screen shows while agents are being generated**

### Initial state check

```
On mount: check WebSocket is open (from Landing screen).
If not connected (e.g. user refreshed):
  - Re-open WebSocket with stored session_id + chairman_token
  - Call GET /api/sessions/{session_id} to check status
  - If status === "active" → skip briefing, go directly to WarRoom
  - If status === "assembling" → show briefing screen, poll scenario
```

### Polling for scenario readiness

```
POLL:  GET /api/sessions/{session_id}/scenario
  HEADERS: Authorization: Bearer {chairman_token}
  INTERVAL: every 1 second

RESPONSE 202 (still building):
  {
    "scenario_ready": false,
    "assembly_log": [
      { "line": "Extracting crisis domain:", "value": "ANALYZING...", "status": "in_progress" }
    ],
    "message": "Retry in 1 second."
  }
  → Render assembly_log lines into the terminal-style loading UI
  → Keep polling

RESPONSE 200 (ready):
  {
    "scenario_ready": true,
    "crisis_title": "OPERATION BLACKSITE",
    "agents": [...],
    "assembly_log": [
      { "line": "Extracting crisis domain:", "value": "CORPORATE",     "status": "complete" },
      { "line": "Generating tactical cast:", "value": "5 AGENTS",      "status": "complete" },
      { "line": "Formulating opening brief:", "value": "COMPLETED",    "status": "complete" },
      { "line": "Establishing secure connection:", "value": "ACTIVE",  "status": "complete" }
    ]
  }
  → STOP polling
  → Display complete assembly_log
  → Wait for session_ready WS event before navigating
```

### WebSocket events to handle on this screen

```
EVENT: "session_status"
  payload: { status: "assembling", message: "Generating crisis team..." }
  → Update loading message in top bar

EVENT: "agent_assembling"
  payload: {
    character_name: "ATLAS",
    role_title:     "Strategic Analyst",
    identity_color: "#4A9EFF",
    defining_line:  "Containment is possible. But not if we wait.",
    voice_name:     "Orus"
  }
  → Reveal one agent card (staggered, slide-in animation)
  → Show defining_line as the agent's first visible text

EVENT: "session_ready"
  payload: { session_id: "A3F9B2C1", crisis_title: "OPERATION BLACKSITE", agent_count: 5 }
  → Delay 800ms (let animations settle)
  → Navigate to: /session/{session_id}/warroom
  → This is the ONLY trigger for navigation — don't navigate on polling alone
```

---

## SCREEN 2 — WAR ROOM (MAIN DASHBOARD)

**File you're building:** `pages/WarRoom.jsx`

### Mount sequence (STRICT ORDER — do not change)

```
Step 1:  Open WebSocket (if not already open)
         const ws = new WebSocket(`wss://api/ws/${sessionId}?token=${token}`)

Step 2:  Initialize AudioManager (needs user gesture — handled by "ENTER" button)
         await audioManager.initialize()    ← call this inside onPointerDown on root div

Step 3:  Parallel REST calls — hydrate ALL panels at once
         const results = await Promise.all([
           fetch(`/api/sessions/${id}`),           // → top bar
           fetch(`/api/sessions/${id}/agents`),    // → agent roster
           fetch(`/api/sessions/${id}/board`),     // → crisis board
           fetch(`/api/sessions/${id}/pods`),      // → agent pods
           fetch(`/api/sessions/${id}/feed`),      // → crisis feed
           fetch(`/api/sessions/${id}/intel`),     // → room intelligence
           fetch(`/api/sessions/${id}/intel/trust`), // → trust bars
           fetch(`/api/sessions/${id}/posture`),   // → crisis posture
           fetch(`/api/sessions/${id}/score`),     // → resolution score
           fetch(`/api/sessions/${id}/voice/status`), // → voice health
           fetch(`/api/sessions/${id}/world`),     // → next escalation timer
         ])

Step 4:  Hydrate Zustand store with all results
Step 5:  Subscribe to WS events (already flowing — process them now)
Step 6:  Get voice token (for mic)
         const voiceResp = await fetch(`/api/sessions/${id}/voice/token`, { method: 'POST' })
         store.setAudioToken(voiceResp.token)
```

---

## PANEL A — TOP COMMAND BAR

**Component:** `components/TopBar.jsx`
**Data source:** `useSessionStore(s => s.session)`

### Initial load

```
REST: GET /api/sessions/{session_id}
  Headers: Authorization: Bearer {chairman_token}

STORE as: store.session = {
  crisis_title:     "OPERATION BLACKSITE",
  threat_level:     "critical",
  resolution_score: 44,
  status:           "active",
  chairman_name:    "DIRECTOR",
  timer: {
    session_duration_seconds: 5400,
    elapsed_seconds:          3622,
    remaining_seconds:        1778,
    formatted:                "00:29:38"
  }
}

RENDER:
  - Crisis title in top left
  - Threat level badge (color-coded, see Design Spec Section 6.1)
  - Countdown timer (start local JS countdown from remaining_seconds)
  - Chairman name
  - MIC STATUS (from GET /voice/status → chairman_mic field)
```

### Live updates (WebSocket)

```
EVENT: "timer_tick"
  payload: { seconds_remaining: 1777, formatted: "00:29:37" }
  → Update countdown display (DON'T use this for a local timer — use it to SYNC)
  → Keep a local setInterval(1000) but sync to WS value when received

EVENT: "threat_level_change"
  payload: { previous: "elevated", current: "critical" }
  → Animate badge color change (flash white → settle to new color)
  → Trigger full-UI color shift (change CSS variable --ui-accent-current)

EVENT: "session_paused"
  payload: {}
  → Show "⏸ PAUSED" overlay on all agent pods
  → Grey out countdown timer
  → Change "PAUSE" button to "RESUME"

EVENT: "session_resumed"
  payload: {}
  → Remove PAUSED overlay
  → Resume timer

EVENT: "chairman_mic_status"
  payload: { chairman_mic: "active" }
  → Update MIC indicator dot (pulsing green vs grey)
```

### Chairman actions from top bar

```
PAUSE / RESUME button:
  CALL:  PATCH /api/sessions/{session_id}
  BODY:  { "paused": true }   or   { "paused": false }
  RESP:  { updated_fields: ["paused"], current_state: {...} }
  → WS event "session_paused" or "session_resumed" handles UI update

MANUAL THREAT OVERRIDE (settings menu):
  CALL:  PATCH /api/sessions/{session_id}
  BODY:  { "threat_level": "critical" }
  RESP:  { updated_fields: ["threat_level"], current_state: {...} }
  → WS event "threat_level_change" handles UI update
```

---

## PANEL B — AGENT ROSTER (LEFT)

**Component:** `components/AgentRoster.jsx`
**Data source:** `useSessionStore(s => s.agents)`

### Initial load

```
REST: GET /api/sessions/{session_id}/agents
  Headers: Authorization: Bearer {chairman_token}

STORE as: store.agents = {
  "atlas_A3F9B2C1": {
    character_name: "ATLAS",
    role_title:     "Strategic Analyst",
    identity_color: "#4A9EFF",
    status:         "speaking",
    trust_score:    72,
    last_statement: "Containment window is closing...",
    conflict_with:  ["felix_A3F9B2C1"],
    last_spoke_at:  "2026-02-26T14:32:01Z"
  },
  ...
}

RENDER: One AgentRow per agent
  - Status dot color from agent.status
  - Trust score (shown on hover tooltip)
  - Conflict indicator if conflict_with.length > 0
```

### Live updates (WebSocket)

```
EVENT: "agent_status_change"
  payload: { agent_id: "atlas_A3F9B2C1", status: "thinking", previous_status: "speaking" }
  → Update store.agents[agent_id].status
  → Re-render status dot + status line

EVENT: "trust_score_update"
  payload: { agent_id: "felix_A3F9B2C1", score: 51, delta: -7, reason: "Contradicted timeline" }
  → Update store.agents[agent_id].trust_score
  → Animate trust bar (flash color on change)
  → Show delta briefly (+7 or -7 in tooltip)

EVENT: "agent_speaking_end"
  payload: { agent_id: "atlas_A3F9B2C1", full_transcript: "Containment window..." }
  → Update store.agents[agent_id].last_statement = full_transcript.slice(0, 80)
  → Update last_spoke_at to now

EVENT: "agent_dismissed"
  payload: { agent_id: "felix_A3F9B2C1" }
  → Remove from store.agents
  → Animate row out (opacity 0, height collapse, 300ms)

EVENT: "agent_assembling"  (mid-session summon)
  payload: { agent_id: "vanguard_A3F9B2C1", character_name: "VANGUARD", ... }
  → Add to store.agents with status: "idle"
  → Animate new row in (translateY(8px) → 0, opacity 0 → 1)
```

### Chairman actions

```
CLICK agent row → SELECT agent (local state, no API call)
  → Highlights the row
  → Sets store.selectedAgentId = agent_id
  → Target Selector in Command Bar updates to this agent

CLICK "DISMISS" with agent selected:
  CALL:  PATCH /api/sessions/{session_id}/agents/{agent_id}
  BODY:  { "action": "dismiss" }
  RESP:  { agent_id, action_applied: "dismiss", effect: "Agent FELIX has left..." }
  → WS event "agent_dismissed" handles UI update

CLICK "SILENCE [N]s" with agent selected:
  CALL:  PATCH /api/sessions/{session_id}/agents/{agent_id}
  BODY:  { "action": "silence", "duration_seconds": 30 }
  → WS event "agent_status_change" (status: "silent") handles UI

CLICK "SUMMON AGENT":
  CALL:  POST /api/sessions/{session_id}/agents/summon
  BODY:  { "role_description": "I need a board representative" }
  RESP 202: { request_id, status: "generating", estimated_seconds: 8 }
  → Show spinner on summon button
  → Wait for WS "agent_assembling" + "agent_ready" events
```

---

## PANEL C — CRISIS BOARD (CENTER)

**Component:** `components/CrisisBoard.jsx`
**Data source:** `useSessionStore(s => s.board)`

### Initial load

```
REST: GET /api/sessions/{session_id}/board
  Headers: Authorization: Bearer {chairman_token}

STORE as: store.board = {
  agreed_decisions: [...],
  open_conflicts:   [...],
  critical_intel:   [...]
}

RENDER: Three columns populated from store
```

### Live updates (WebSocket)

```
EVENT: "decision_agreed"
  payload: {
    decision_id:     "uuid4",
    text:            "Activate secondary containment protocol immediately.",
    agreed_at:       "2026-02-26T14:32:01Z",
    proposed_by:     "atlas_A3F9B2C1",
    agents_agreed:   ["atlas_A3F9B2C1", "nova_A3F9B2C1"],
    agents_dissented: ["felix_A3F9B2C1"]
  }
  → Prepend to store.board.agreed_decisions
  → Animate new card: opacity 0 → 1 + left border flash green (600ms)

EVENT: "conflict_opened"
  payload: {
    conflict_id:     "uuid4",
    description:     "FELIX insists on immediate deployment...",
    agents_involved: ["felix_A3F9B2C1", "nova_A3F9B2C1"],
    severity:        "high"
  }
  → Prepend to store.board.open_conflicts
  → Animate: double red flash (rgba(255,45,45,0.2) × 2, 300ms each)

EVENT: "conflict_resolved"
  payload: { conflict_id: "uuid4", resolution: "Chairman ruling: deployment approved." }
  → Update store.board.open_conflicts item: resolved = true
  → Animate: opacity 0.4, cross out with CSS text-decoration: line-through
  → Move to bottom of column after 1.5s

EVENT: "intel_dropped"
  payload: {
    intel_id:       "uuid4",
    text:           "Dark web chatter references operation codename...",
    source:         "CIPHER / OSINT",
    source_type:    "INTERNAL",
    is_escalation:  false
  }
  → Prepend to store.board.critical_intel
  → Animate: opacity 0 → 1 + left border flash blue (600ms)

EVENT: "crisis_escalation"
  payload: { event_id, text: "External breach...", type: "INTERNAL" }
  → Show escalation banner (slide down, 300ms spring-in)
  → intel_dropped event will also fire → adds to column
  → Auto-dismiss banner after 8 seconds
```

### Chairman actions

```
PIN A DECISION (lock it):
  CALL:  PATCH /api/sessions/{session_id}/board/decisions/{decision_id}
  BODY:  { "locked": true }
  RESP:  { decision_id, locked: true, locked_at: "..." }
  → Locally update: show 📌 pin icon on that card
  → No WS event for this — update locally from response

ADD DECISION MANUALLY:
  CALL:  POST /api/sessions/{session_id}/board/decisions
  BODY:  { "text": "No public statement before 18:00 UTC.", "source": "chairman", "lock": true }
  RESP 201: { decision_id, text, agreed_at, proposed_by: "chairman", locked: true }
  → WS event "decision_agreed" will also fire and handle the UI

RESOLVE CONFLICT:
  CALL:  PATCH /api/sessions/{session_id}/board/conflicts/{conflict_id}
  BODY:  {
    "resolution":   "Chairman ruling: deployment approved with oversight.",
    "decision_text": "NOVA to monitor compliance."  // optional: auto-creates decision
  }
  RESP:  { conflict_id, resolved_at, auto_created_decision_id }
  → WS "conflict_resolved" fires → handles UI
  → If decision_text was provided: WS "decision_agreed" also fires

ADD INTEL (inject information):
  CALL:  POST /api/sessions/{session_id}/board/intel
  BODY:  {
    "text":        "I just confirmed: journalist has the documents.",
    "source_type": "INTERNAL",
    "source":      "CHAIRMAN / DIRECT",
    "broadcast":   true    // sends to ALL agents' Gemini Live sessions
  }
  RESP 201: { intel_id, text, broadcast_to_agents: 5 }
  → WS "intel_dropped" fires → handles UI
  → If broadcast=true: all agents receive this in their next turn context

TIMELINE REPLAY (tab buttons: NOW / -5m / -10m / -20m):
  CALL:  GET /api/sessions/{session_id}/board/timeline?at={ISO_timestamp}
  RESP:  { at, agreed_decisions, open_conflicts, critical_intel, resolution_score_at_time, threat_level_at_time }
  → Replace board columns with historical data
  → Show "REPLAY MODE — {timestamp}" banner
  → Clicking "NOW" tab: restore from store.board (live state)
```

---

## PANEL D — CRISIS FEED (BOTTOM LEFT)

**Component:** `components/CrisisFeed.jsx`
**Data source:** `useSessionStore(s => s.feedItems)`

### Initial load

```
REST: GET /api/sessions/{session_id}/feed
  Headers: Authorization: Bearer {chairman_token}
  Query:   ?limit=30

STORE as: store.feedItems = [...items]
          store.feedTabCounts = { WORLD: 3, LEGAL: 2, MEDIA: 5, INTERNAL: 4, SOCIAL: 7 }
          store.feedUnread = { WORLD: 1, LEGAL: 0, MEDIA: 2, INTERNAL: 0, SOCIAL: 3 }

ALSO CALL (to populate World tab and get next escalation timer):
  REST: GET /api/sessions/{session_id}/feed/world
  STORE as: store.worldEvents = [...world_events]
            store.nextEscalation = { at, in_seconds, formatted }

RENDER:
  - 5 tabs with badge counts from store.feedTabCounts
  - Unread count badges from store.feedUnread
  - Feed items filtered by active tab
  - "WORLD" tab also shows next escalation timer
```

### Live updates (WebSocket)

```
EVENT: "feed_item"
  payload: {
    feed_id:       "uuid4",
    text:          "Anonymous source contacts Reuters...",
    source_name:   "📰 REUTERS",
    source_type:   "MEDIA",
    is_hot:        true,
    is_breaking:   true,
    metric:        "↗️ 82K impressions · 3 min ago"
  }
  → Prepend to store.feedItems
  → Increment store.feedTabCounts[source_type]
  → Increment store.feedUnread[source_type] (if tab not currently active)
  → Animate: standard = blue flash; breaking = red flash + header flashes

EVENT: "feed_unread_count"
  payload: { WORLD: 1, LEGAL: 0, MEDIA: 3, INTERNAL: 0, SOCIAL: 5 }
  → Update all tab badge counts at once

EVENT: "next_escalation_timer"
  payload: { in_seconds: 298, formatted: "4:58" }
  → Update escalation countdown in WORLD tab header
  → When in_seconds < 60: start blinking
```

### Chairman actions

```
MARK ITEM AS READ:
  CALL:  PATCH /api/sessions/{session_id}/feed/{feed_id}
  BODY:  { "read": true }
  RESP:  { feed_id, read: true }
  → Decrement unread badge for that tab
  → No WS event — update locally

TAB SWITCH (local only, no API call):
  → Filter store.feedItems by source_type
  → Mark that tab's unread count as 0 in store (visual clear)
  → Items fetched on initial load already include all types
```

---

## PANEL E — AGENT VOICE PODS (BOTTOM CENTER)

**Component:** `components/AgentPods.jsx`
**Data source:** `useSessionStore(s => s.pods)` + `audioManager`

### Initial load

```
REST: GET /api/sessions/{session_id}/pods
  Headers: Authorization: Bearer {chairman_token}

STORE as: store.pods = {
  "atlas_A3F9B2C1": {
    character_name:     "ATLAS",
    role_title:         "Strategic Analyst",
    identity_color:     "#4A9EFF",
    status:             "thinking",
    transcript_snippet: "Containment window is cl...",
    conflict_with_name: null,
    waveform_active:    false,
  },
  ...
}

RENDER: One AgentPod card per agent
  - Status state (IDLE/SPEAKING/THINKING/CONFLICTED — see Design Spec 6.5)
  - Flat waveform bars (will animate on SPEAKING)
  - Transcript snippet
```

### Live updates (WebSocket)

```
EVENT: "agent_speaking_start"
  payload: { agent_id: "atlas_A3F9B2C1", character_name: "ATLAS" }
  → store.pods[agent_id].status = "speaking"
  → store.pods[agent_id].waveform_active = true
  → Animate waveform bars (CSS animation starts)
  → Clear transcript_snippet to ""

EVENT: "agent_audio_chunk"    ← THIS IS THE VOICE
  payload: {
    agent_id:    "atlas_A3F9B2C1",
    audio_b64:   "base64-encoded-PCM-string",
    sample_rate: 24000,
    channels:    1,
    bit_depth:   16
  }
  → Call audioManager.playChunk(agent_id, audio_b64)
  → DO NOT update store — this is audio only
  → See WARROOM_VOICE_PIPELINE.md Section 3.2 for AudioManager

EVENT: "agent_speaking_chunk"
  payload: { agent_id: "atlas_A3F9B2C1", transcript_chunk: " containment" }
  → Append to store.transcripts[agent_id]
  → Renders in pod as live typewriter text

EVENT: "agent_speaking_end"
  payload: { agent_id: "atlas_A3F9B2C1", full_transcript: "Containment window is closing..." }
  → store.pods[agent_id].status = "listening"
  → store.pods[agent_id].waveform_active = false
  → store.pods[agent_id].transcript_snippet = full_transcript.slice(0, 60) + "..."
  → Stop waveform animation
  → Finalize transcript display

EVENT: "agent_thinking"
  payload: { agent_id: "felix_A3F9B2C1" }
  → store.pods[agent_id].status = "thinking"
  → Show animated "· · · processing" text

EVENT: "agent_interrupted"
  payload: { agent_id: "atlas_A3F9B2C1" }
  → audioManager.stopAgent("atlas_A3F9B2C1")  ← stop audio immediately
  → store.pods[agent_id].status = "listening"
  → Flash interrupt indicator on pod (brief red flash)

EVENT: "agent_status_change"
  payload: { agent_id, status, previous_status }
  → update store.pods[agent_id].status
  → re-render pod state

EVENT: "agent_dismissed"
  payload: { agent_id: "felix_A3F9B2C1" }
  → Remove from store.pods
  → Animate pod out (scale 0.8, opacity 0, 300ms)
  → Shift remaining pods to fill space
```

### Clicking a pod (detail view)

```
CLICK on agent pod → show expanded view
  CALL:  GET /api/sessions/{session_id}/pods/{agent_id}
  RESP: {
    recent_transcript: [
      "Field deployment cannot wait...",
      "NOVA's legal position is theoretical...",
      "I need authorization now or I go without it."
    ],
    conflict_with:     [{ agent_id: "nova_A3F9B2C1", name: "NOVA" }],
    trust_score:       51,
    interrupted_count: 2
  }
  → Show overlay/drawer on pod with full recent_transcript
  → Show conflict targets with links to other pods
```

---

## PANEL F — ROOM INTELLIGENCE (BOTTOM RIGHT TOP)

**Component:** `components/RoomIntelligence.jsx`
**Data source:** `useSessionStore(s => s.insights)` + `store.trustScores`

### Initial load

```
REST CALL 1: GET /api/sessions/{session_id}/intel
  STORE as: store.insights = [
    {
      insight_id:        "uuid4",
      type:              "contradiction",
      title:             "CONTRADICTION",
      body:              "ATLAS claims containment stable but CIPHER reports breach.",
      agents_referenced: ["atlas_A3F9B2C1", "cipher_A3F9B2C1"],
      severity:          "high"
    },
    ...
  ]

REST CALL 2: GET /api/sessions/{session_id}/intel/trust
  STORE as: store.trustScores = {
    "atlas_A3F9B2C1":  { score: 72, trend: "stable",  delta_last_turn: 0,  reason: "Consistent stance" },
    "nova_A3F9B2C1":   { score: 85, trend: "rising",  delta_last_turn: +3, reason: "↑ Cited precedent" },
    "felix_A3F9B2C1":  { score: 51, trend: "falling", delta_last_turn: -7, reason: "↓ Contradicted timeline" }
  }

RENDER:
  - Insight cards (color-coded by type)
  - Trust score bars at bottom (live bars)
```

### Live updates (WebSocket)

```
EVENT: "observer_insight"
  payload: {
    insight_id:        "uuid4",
    type:              "alliance",
    title:             "ALLIANCE FORMING",
    body:              "NOVA and CIPHER aligning on legal-intel protocol.",
    agents_referenced: ["nova_A3F9B2C1", "cipher_A3F9B2C1"],
    severity:          "medium"
  }
  → Prepend to store.insights (max 20 items)
  → Animate: slide in from top, brief glow matching insight type color
  → "ALLIANCE" card: blue glow
  → "CONTRADICTION" card: orange glow
  → "BLIND SPOT" card: purple glow

EVENT: "trust_score_update"
  payload: { agent_id: "felix_A3F9B2C1", score: 51, delta: -7, reason: "↓ Contradicted timeline" }
  → Update store.trustScores[agent_id]
  → Animate trust bar: if delta < 0 → flash red → settle; if delta > 0 → flash green
  → Show delta briefly: "-7" floats up and fades (CSS animation)
```

### Trust score sparkline (on hover)

```
HOVER trust bar row → show sparkline
  CALL:  GET /api/sessions/{session_id}/intel/trust/{agent_id}/history
  RESP: {
    history: [
      { score: 70, at: "2026-02-26T14:28:00Z", reason: "Initial" },
      { score: 68, at: "...", reason: "↓ Inconsistency" }
    ],
    current_score: 51,
    starting_score: 70
  }
  → Render sparkline SVG from history data
  → Show tooltip with latest reason
  → Dismiss on mouseout
```

---

## PANEL G — CRISIS POSTURE (BOTTOM RIGHT MID)

**Component:** `components/CrisisPosture.jsx`
**Data source:** `useSessionStore(s => s.posture)`

### Initial load

```
REST: GET /api/sessions/{session_id}/posture
  STORE as: store.posture = {
    axes: {
      public_exposure:     { value: 78, status: "high",      trend: "rising",  trend_arrow: "↑", sub_metric: "Viral velocity: RISING", driver: "Media coverage escalating" },
      legal_exposure:      { value: 62, status: "elevated",  trend: "stable",  trend_arrow: "→", sub_metric: "Liability scan active",   driver: "Class action risk" },
      internal_stability:  { value: 71, status: "contained", trend: "falling", trend_arrow: "↓", sub_metric: "Team alignment nominal",  driver: "FELIX/NOVA conflict" }
    }
  }

RENDER: 3 axis bars with values, trend arrows, sub-metrics
  NOTE: public_exposure and legal_exposure: higher = WORSE (red)
        internal_stability: higher = BETTER (green) — inverted color scale
```

### Live updates (WebSocket)

```
EVENT: "posture_update"
  payload: {
    public_exposure:    { value: 82, status: "high",      trend: "rising",  trend_arrow: "↑", sub_metric: "...", driver: "..." },
    legal_exposure:     { value: 62, status: "elevated",  trend: "stable",  trend_arrow: "→", sub_metric: "...", driver: "..." },
    internal_stability: { value: 68, status: "contained", trend: "falling", trend_arrow: "↓", sub_metric: "...", driver: "..." }
  }
  → Update store.posture.axes
  → Animate bars: CSS transition width 800ms ease
  → Show "1 NEW UPDATE" badge in header → auto-dismiss after 3s
```

### Posture history (optional trend view)

```
ON HOVER any axis bar:
  CALL:  GET /api/sessions/{session_id}/posture/history?axis=public_exposure&limit=20
  RESP:  { axis: "public_exposure", history: [{ value: 55, at: "..." }, ...] }
  → Render sparkline in tooltip
```

---

## PANEL H — RESOLUTION SCORE (BOTTOM RIGHT BOTTOM)

**Component:** `components/ResolutionScore.jsx`
**Data source:** `useSessionStore(s => s.score)`

### Initial load

```
REST CALL 1: GET /api/sessions/{session_id}/score
  STORE as: store.score = {
    score:              44,
    label:              "RECOVERING",
    trend:              "improving",
    trend_arrow:        "↑",
    delta_last_change:  +3,
    score_history:      [58, 55, 50, 46, 44, 44, 47],
    driver:             "Containment decision reduced legal exposure",
    target:             70,
    target_label:       "Target: 70+ to stabilize outcome",
    next_escalation: { in_seconds: 298, formatted: "4:58", blinking: false },
    threat_level:       "critical"
  }

REST CALL 2: GET /api/sessions/{session_id}/score/history?limit=30
  STORE as: store.scoreHistory = [
    { score: 58, at: "...", event: "Session started" },
    { score: 52, at: "...", event: "First escalation: Media leak" },
    ...
  ]

RENDER:
  - Big number (animated, see Design Spec 6.8)
  - State label ("RECOVERING")
  - Trend arrow
  - Mini sparkline from score_history
  - Next escalation countdown (ticks every second locally, syncs from WS)
  - Driver text
```

### Live updates (WebSocket)

```
EVENT: "score_update"
  payload: {
    score:        52,
    delta:        +8,
    score_history: [58, 55, 50, 46, 44, 44, 47, 52],
    threat_level: "elevated",
    driver:       "Conflict resolved: FELIX/NOVA"
  }
  → Animate counter from old to new value (JS requestAnimationFrame, 600ms)
  → On RISE: brief green flash on number
  → On DROP: brief red flash on number
  → Update store.score.score_history → re-render sparkline
  → Update driver text below score
  → Check label mapping:
      70–100 → "RESOLVED"     (green)
      50–69  → "RECOVERING"   (amber)
      30–49  → "CRITICAL"     (orange)
      0–29   → "MELTDOWN"     (red)

EVENT: "next_escalation_timer"
  payload: { in_seconds: 297, formatted: "4:57" }
  → Sync local countdown to this value
  → Run local setInterval(1000) between events
  → When in_seconds < 60: add blinking class to countdown text

EVENT: "threat_level_change"
  payload: { previous: "elevated", current: "critical" }
  → Update score panel accent color (matches threat)
  → Top bar badge already handled globally
```

---

## PANEL I — CHAIRMAN COMMAND BAR (FOOTER)

**Component:** `components/CommandBar.jsx`
**Always visible, fixed footer**

### Initialization

```
ON MOUNT:
  CALL:  GET /api/sessions/{session_id}/voice/status
  RESP: {
    chairman_mic:    "muted",
    agent_sessions:  [...],
    all_healthy:     true
  }
  → Set MIC indicator initial state
  → Log agent session health (debug)

ALSO LOAD (done in WarRoom mount):
  CALL:  POST /api/sessions/{session_id}/voice/token
  STORE: store.audioToken = token
         store.audioWsUrl  = ws_audio_url
  → Used when chairman holds the mic button
```

### MIC BUTTON — Hold to speak

```
HOLD DOWN:
  1. audioManager.initialize()  ← if not already done (user gesture)
  2. const stream = navigator.mediaDevices.getUserMedia({ audio: {...} })
  3. Open audio WebSocket: new WebSocket(`${store.audioWsUrl}?token=${store.audioToken}`)
  4. Send target: ws.send(JSON.stringify({ type: "set_target", agent_id: store.selectedAgentId }))
     // store.selectedAgentId = null means full room
  5. Process mic audio → ScriptProcessor → Int16PCM → ws.send(pcm.buffer)
  6. CALL PATCH /api/sessions/{session_id}/voice/chairman  BODY: { "muted": false }

RELEASE:
  1. Disconnect ScriptProcessor
  2. Close audio WebSocket
  3. CALL PATCH /api/sessions/{session_id}/voice/chairman  BODY: { "muted": true }
  → WS event "chairman_mic_status" confirms update in top bar
```

### WebSocket events for command bar audio feedback

```
From /ws/{session_id}/audio (separate audio WS):
  { "type": "vad_speech_start" }   → show "● RECORDING" indicator
  { "type": "vad_speech_end" }     → show processing indicator
  { "type": "transcript", "text": "NOVA, what is..." } → display in command bar
  { "type": "routed_to", "agent_id": "nova_A3F9B2C1" } → highlight NOVA pod briefly

From main WS /ws/{session_id}:
  EVENT: "chairman_spoke"
    payload: { transcript: "NOVA, answer the question.", target_agent_id: "nova_A3F9B2C1" }
    → Show in command bar transcript strip: "CHAIRMAN: NOVA, answer the question."
    → Highlight targeted agent's pod border briefly
```

### TEXT COMMAND (type instead of speak)

```
User types in command input → presses Enter:
  CALL:  POST /api/sessions/{session_id}/chairman/command
  BODY:  {
    "text":            "NOVA, what is the legal minimum disclosure window?",
    "target_agent_id": store.selectedAgentId,  // null = full room
    "command_type":    "question"
  }
  RESP:  { command_id, text, routed_to: ["nova_A3F9B2C1"], issued_at }
  → WS "chairman_spoke" fires → shows in command bar
  → Target agent's Gemini Live session receives the text → they respond in voice
```

### FORCE VOTE button

```
CLICK "FORCE VOTE" → show vote modal:
  User types: "Do we issue a public statement before 15:00 UTC?"

CALL:  POST /api/sessions/{session_id}/chairman/vote
BODY:  {
  "question":           "Do we issue a public statement before 15:00 UTC?",
  "time_limit_seconds": 120
}
RESP 202: {
  vote_id:       "uuid4",
  started_at:    "...",
  ends_at:       "...",
  agents_voting: ["atlas_...", "nova_...", ...]
}
→ Show vote progress overlay (shows each agent responding)
→ Watch for WS event "vote_result"

EVENT: "vote_result"
  payload: {
    results: [
      { agent_id: "atlas_A3F9B2C1", name: "ATLAS", vote: "YES", reasoning: "..." },
      ...
    ],
    majority:       "YES",
    vote_count:     { YES: 4, NO: 1 },
    decision_text:  "Majority voted: Issue public statement before 15:00 UTC."
  }
  → Show vote result overlay (full screen)
  → If auto_create_decision=true: WS "decision_agreed" also fires
  → Dismiss overlay after 5 seconds
```

### MANUAL ESCALATION (Chairman power)

```
From settings / overflow menu:
  CALL:  POST /api/sessions/{session_id}/world/escalate
  BODY:  {
    "event_text":   "The board has called an emergency session in 30 minutes.",
    "event_type":   "INTERNAL",
    "score_impact": -5
  }
  RESP 201: { event_id, fired_at, score_impact: -5, broadcast_to_agents: 5 }
  → WS "crisis_escalation" fires (full-screen flash)
  → WS "score_update" fires (score drops -5)
  → WS "feed_item" fires (appears in WORLD tab)
  → All agents receive context for next turn
```

---

## SCREEN 3 — RESOLUTION MODE

**Component:** `components/ResolutionOverlay.jsx`
**Triggered by:** Chairman action OR timer reaching 0

### Triggering resolution

```
Chairman clicks "CALL RESOLUTION":
  CALL:  POST /api/sessions/{session_id}/resolution
  BODY:  {
    "final_decision": "Issue limited statement at 17:00 UTC concurrent with deployment."
  }
  RESP 200: {
    resolution_id:  "uuid4",
    final_decision: "...",
    resolved_at:    "...",
    processing:     true,
    message:        "Generating agent final positions..."
  }

Or triggered via PATCH:
  CALL:  PATCH /api/sessions/{session_id}
  BODY:  { "status": "resolution" }
  → WS "resolution_mode_start" fires → show resolution overlay
```

### WebSocket events during resolution

```
EVENT: "resolution_mode_start"
  payload: {}
  → Show full-screen resolution overlay
  → Dim all panels
  → Lock Crisis Board (disable interactions)
  → Show "Agents generating final positions..." spinner

EVENT: "agent_final_position"   ← fires N times (once per agent)
  payload: {
    agent_id:       "atlas_A3F9B2C1",
    character_name: "ATLAS",
    verdict:        "Statement approved. Containment first, disclosure second.",
    alignment:      "agreed"  // "agreed" | "dissented" | "neutral"
  }
  → Reveal agent verdict card one by one (staggered, 500ms apart)
  → "agreed": green border
  → "dissented": red border
  → "neutral": grey border

EVENT: "session_resolved"
  payload: {
    session_id:       "A3F9B2C1",
    final_decision:   "We issue a limited statement...",
    projected_futures: [
      { scenario: "best",     probability: "35%", description: "..." },
      { scenario: "expected", probability: "50%", description: "..." },
      { scenario: "worst",    probability: "15%", description: "..." }
    ]
  }
  → Wait 2 seconds after all verdict cards revealed
  → Show final decision statement
  → Show projected futures
  → Show [ VIEW FULL REPORT ] button
  → Navigate to /session/{session_id}/report after 3 more seconds OR on button click
```

---

## SCREEN 4 — AFTER-ACTION REPORT

**Component:** `pages/AfterAction.jsx`

### Load

```
CALL:  GET /api/sessions/{session_id}/report
  Headers: Authorization: Bearer {chairman_token}

RESP 200: {
  crisis_title:   "OPERATION BLACKSITE",
  duration:       { started_at, ended_at, total_minutes: 32 },
  final_decision: "We issue a limited statement...",
  final_score:    61,
  final_threat_level: "elevated",
  agent_positions: [...],
  projected_futures: [...],
  key_moments:    [...],
  statistics:     { total_statements: 42, total_conflicts: 3, ... },
  replay_available: true,
  replay_start_url: "/api/sessions/A3F9B2C1/board/timeline?at=..."
}

RENDER: Full after-action screen (different page, no dashboard UI)
  - Final score with animation on mount
  - Timeline of key moments (horizontal scroll)
  - Agent verdict cards (all N agents)
  - Projected futures (3 scenarios)
  - Statistics grid
  - [ REPLAY ] button → uses board timeline API
  - [ NEW CRISIS ] button → navigate to Landing, clear session storage
```

### Replay

```
CLICK [ REPLAY ]:
  Navigate back to: /session/{session_id}/warroom?replay=true
  
  On WarRoom mount in replay mode:
  - Connect WS (read-only mode)
  - Show time scrubber at bottom
  - On scrub to T: CALL GET /api/sessions/{session_id}/board/timeline?at={T}
  - Populate all board columns with historical state
  - Score/posture show values "at that moment"
  - No live updates in replay mode
```

---

## SESSION CLEANUP

```
User closes browser / navigates away:
  - ws.close()  ← closes WS connection
  - audioManager.destroy()  ← closes AudioContext
  - clearInterval(all timers)
  
  Optionally (on explicit "END SESSION"):
  CALL:  DELETE /api/sessions/{session_id}
  RESP:  { closed_at, agents_released: 5, after_action_url: "..." }
  → Navigate to after-action report URL
  
  Note: Firestore data is preserved even after DELETE.
  DELETE only closes Gemini Live sessions and marks status="closed".
```

---

## RECONNECTION HANDLING

```
WebSocket drops → auto-reconnect:
  1. ws.onclose fires
  2. Wait 2 seconds
  3. Re-open: new WebSocket(ws_url + "?token=" + token)
  4. On reconnect → call GET /api/sessions/{id} to re-sync state
  5. Re-hydrate store (same as initial mount)
  6. WS events resume from current time (no replay of missed events)
  7. Show brief "RECONNECTING..." in top bar during gap
  
Page refresh:
  1. localStorage has session_id + chairman_token
  2. Open WS
  3. GET /api/sessions/{id} → if status=active → show WarRoom
  4. Re-hydrate all panels via REST
  5. WS events start flowing again
  
Token expiry (403 on REST call):
  - chairman_token doesn't expire (session-scoped)
  - Audio token from POST /voice/token expires in 1 hour
  - On 401 from /ws/audio: call POST /voice/token to refresh, reconnect audio WS
```

---

## ZUSTAND STORE SHAPE (COMPLETE)

```javascript
// lib/store.js — reference for what to store

{
  // Session
  session: {
    session_id, crisis_title, status, threat_level,
    resolution_score, chairman_name,
    timer: { remaining_seconds, formatted }
  },
  
  // Credentials
  chairmanToken: string,
  audioToken:    string,
  audioWsUrl:    string,
  
  // Agents (merged from /agents + /pods + WS updates)
  agents: {
    [agent_id]: {
      character_name, role_title, identity_color, voice_name,
      status, trust_score, last_statement, conflict_with,
      transcript_snippet, waveform_active, last_spoke_at
    }
  },
  selectedAgentId: string | null,   // for targeting chairman commands
  
  // Board
  board: {
    agreed_decisions: [...],
    open_conflicts:   [...],
    critical_intel:   [...]
  },
  boardReplayMode:  boolean,
  boardReplayAt:    string | null,
  
  // Feed
  feedItems:     [...],
  feedTabCounts: { WORLD, LEGAL, MEDIA, INTERNAL, SOCIAL },
  feedUnread:    { WORLD, LEGAL, MEDIA, INTERNAL, SOCIAL },
  activeTab:     "WORLD" | "LEGAL" | "MEDIA" | "INTERNAL" | "SOCIAL",
  nextEscalation: { in_seconds, formatted, blinking },
  
  // Live transcripts (streaming, per agent)
  transcripts:   { [agent_id]: string },
  
  // Room Intelligence
  insights:      [...],     // max 20, newest first
  trustScores:   { [agent_id]: { score, trend, delta_last_turn, reason } },
  
  // Posture
  posture: {
    axes: {
      public_exposure:    { value, status, trend, trend_arrow, sub_metric, driver },
      legal_exposure:     { value, status, trend, trend_arrow, sub_metric, driver },
      internal_stability: { value, status, trend, trend_arrow, sub_metric, driver }
    }
  },
  
  // Score
  score: {
    score, label, trend, trend_arrow,
    delta_last_change, score_history, driver, target, target_label,
    next_escalation: { in_seconds, formatted, blinking },
    threat_level
  },
  scoreHistory: [{ score, at, event }],
  
  // UI state
  micRecording:     boolean,
  resolutionMode:   boolean,
  voteInProgress:   boolean,
  currentVote:      object | null,
  
  // Actions
  handleEvent: (wsEvent) => void,    // master WS event handler
  setAudioToken: (token) => void,
  selectAgent: (agent_id) => void,
}
```

---

## CRITICAL TIMING RULES

```
NEVER do these:
  ✗ Poll any panel endpoint after initial load (WS handles updates)
  ✗ Call POST /sessions before opening WebSocket
  ✗ Create AudioContext outside a user gesture handler
  ✗ Call audioManager.playChunk before audioManager.initialize()
  ✗ Send chairman audio to multiple agents' queues (router handles this)
  ✗ Read agent_memory collection from any API call (doesn't exist in REST API)
  ✗ Refresh browser during active session without re-hydrating store

ALWAYS do these:
  ✓ Open WS immediately after POST /sessions returns session_id
  ✓ Use Promise.all() for all 10 initial panel REST calls (parallel)
  ✓ Handle ws.onclose with exponential backoff reconnect
  ✓ Keep a local timer (setInterval) but sync it to timer_tick WS events
  ✓ Send Authorization: Bearer {chairman_token} on EVERY REST request
  ✓ Store chairman_token in localStorage (survives refresh)
  ✓ Clear store on NEW CRISIS (navigate to Landing, localStorage.clear())
```

---

*War Room Integration Guide v1.0*
*Covers: 4 screens × 9 panels × 37 REST endpoints × 40+ WS events*
*Build order: Landing → Briefing → WarRoom panels → CommandBar → Resolution → Report*
