"""
WAR ROOM — Pydantic Models
Schemas for ScenarioSpec, AgentConfig, ObserverOutput, and Firestore documents.
"""

from __future__ import annotations

from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


# ── SCENARIO ANALYST OUTPUT ──────────────────────────────────────────────


class IntelItem(BaseModel):
    """A single intelligence item."""
    text: str
    source: str = Field(description="WORLD | MEDIA | LEGAL | INTERNAL | SOCIAL")


class ConflictItem(BaseModel):
    """An initial conflict between agents."""
    description: str
    agents_involved: list[str]


class EscalationEvent(BaseModel):
    """A scheduled escalation event."""
    delay_minutes: int
    event_text: str
    type: str = Field(description="media | legal | internal | social | operational")


class AgentConfig(BaseModel):
    """Configuration for a single crisis agent, output by Scenario Analyst."""
    role_key: str
    role_title: str
    character_name: str
    defining_line: str
    agenda: str
    hidden_knowledge: str
    personality_traits: list[str]
    conflict_with: list[str] = Field(default_factory=list)
    voice_style: str = "measured"
    identity_color: str = "#666666"


class ScenarioSpec(BaseModel):
    """Full output schema from the Scenario Analyst agent."""
    crisis_title: str = Field(max_length=80)
    crisis_domain: str
    crisis_brief: str
    threat_level_initial: str = "elevated"
    resolution_score_initial: int = Field(ge=0, le=100, default=50)
    agents: list[AgentConfig]
    initial_intel: list[IntelItem] = Field(default_factory=list)
    initial_conflicts: list[ConflictItem] = Field(default_factory=list)
    escalation_schedule: list[EscalationEvent] = Field(default_factory=list)


# ── OBSERVER AGENT OUTPUT ────────────────────────────────────────────────


class PostureImpact(BaseModel):
    """Impact on crisis posture metrics, produced by Observer."""
    public_exposure_delta: int = Field(ge=-10, le=10, default=0)
    legal_exposure_delta: int = Field(ge=-10, le=10, default=0)
    internal_stability_delta: int = Field(ge=-10, le=10, default=0)


class ObserverOutput(BaseModel):
    """Structured output from the Observer Agent."""
    trust_delta: int = Field(ge=-20, le=10, default=0)
    trust_reason: str = ""
    insight_type: Optional[str] = Field(
        default=None,
        description="contradiction | alliance | blind_spot | mood_shift | null",
    )
    insight_title: Optional[str] = None
    insight_body: Optional[str] = None
    agents_referenced: list[str] = Field(default_factory=list)
    posture_impact: PostureImpact = Field(default_factory=PostureImpact)
    resolution_score_delta: int = Field(ge=-5, le=5, default=0)


# ── FIRESTORE DOCUMENT MODELS ───────────────────────────────────────────


class PostureModel(BaseModel):
    """Crisis posture metrics for the session."""
    public_exposure: int = 60
    legal_exposure: int = 45
    internal_stability: int = 50
    public_trend: str = "rising"
    legal_trend: str = "stable"
    internal_trend: str = "stable"


class AgentRosterEntry(BaseModel):
    """An agent entry in the crisis session roster."""
    agent_id: str
    role_title: str
    character_name: str
    voice_name: str
    identity_color: str
    defining_line: str
    agenda: str
    hidden_knowledge: str = ""  # NEVER exposed in shared state reads
    status: str = "idle"
    trust_score: int = 70
    last_spoke_at: Optional[str] = None


class AgreedDecision(BaseModel):
    """A decision agreed upon by agents."""
    decision_id: str
    text: str
    agreed_at: str
    agents_agreed: list[str]
    proposed_by: str


class OpenConflict(BaseModel):
    """An active conflict between agents."""
    conflict_id: str
    description: str
    agents_involved: list[str]
    opened_at: str
    severity: str = "medium"


class CriticalIntel(BaseModel):
    """A piece of critical intelligence."""
    intel_id: str
    text: str
    source: str
    timestamp: str
    is_escalation: bool = False


class CrisisSessionModel(BaseModel):
    """Full Firestore document model for /crisis_sessions/{session_id}."""
    session_id: str
    chairman_id: str
    created_at: Optional[str] = None
    status: str = "assembling"
    crisis_input: str = ""
    crisis_title: str = ""
    crisis_domain: str = ""
    crisis_brief: str = ""
    agent_roster: list[AgentRosterEntry] = Field(default_factory=list)
    agreed_decisions: list[AgreedDecision] = Field(default_factory=list)
    open_conflicts: list[OpenConflict] = Field(default_factory=list)
    critical_intel: list[CriticalIntel] = Field(default_factory=list)
    posture: PostureModel = Field(default_factory=PostureModel)
    resolution_score: int = 50
    score_history: list[int] = Field(default_factory=lambda: [50])
    threat_level: str = "elevated"
    next_escalation_at: Optional[str] = None
    escalation_events: list[dict] = Field(default_factory=list)
    final_decision: Optional[str] = None
    resolution_at: Optional[str] = None
    projected_futures: list[dict] = Field(default_factory=list)


# ── AGENT MEMORY MODEL ──────────────────────────────────────────────────


class AgentMemoryModel(BaseModel):
    """Firestore document model for /agent_memory/{agent_id}_{session_id}."""
    agent_id: str
    session_id: str
    character_name: str
    private_facts: list[str] = Field(default_factory=list)
    hidden_agenda: str = ""
    private_commitments: list[str] = Field(default_factory=list)
    previous_statements: list[dict] = Field(default_factory=list)
    public_positions: dict = Field(default_factory=dict)
    contradictions_detected: int = 0
    adk_session_id: str = ""
    adk_last_event: Optional[str] = None
    live_session_token: str = ""
    voice_name: str = ""
    voice_session_active: bool = False
    livekit_agent_session: dict = Field(default_factory=dict)


# ── SESSION EVENT MODEL ──────────────────────────────────────────────────


class SessionEvent(BaseModel):
    """Firestore document model for session_events subcollection."""
    event_id: str
    session_id: str
    event_type: str
    source_agent_id: str = "system"
    timestamp: str
    payload: dict
    consumed_by_frontend: bool = False


# ── API REQUEST / RESPONSE MODELS ───────────────────────────────────────


class CreateSessionRequest(BaseModel):
    """Request body for POST /api/sessions."""
    crisis_input: str = Field(
        ..., min_length=10, max_length=2000,
        description="Raw crisis description, 10–2000 characters",
    )
    chairman_name: Optional[str] = Field(
        default="DIRECTOR",
        description="Display name for the Chairman in the Command Bar",
    )
    session_duration_minutes: int = Field(
        default=30, ge=5, le=120,
        description="Session length in minutes",
    )


class CreateSessionResponse(BaseModel):
    """Response body for POST /api/sessions (201)."""
    session_id: str
    chairman_token: str
    status: str = "assembling"
    ws_url: str
    created_at: str
    message: str = "Crisis received. Assembling your team."


class TimerInfo(BaseModel):
    """Timer state returned by GET /api/sessions/{session_id}."""
    session_duration_seconds: int
    elapsed_seconds: int
    remaining_seconds: int
    formatted: str


class SessionStateResponse(BaseModel):
    """Full merged session state for GET /api/sessions/{session_id}."""
    session_id: str
    status: str
    crisis_title: str = ""
    crisis_domain: str = ""
    crisis_brief: str = ""
    threat_level: str = "elevated"
    resolution_score: int = 50
    created_at: Optional[str] = None
    timer: Optional[TimerInfo] = None
    chairman_name: str = "DIRECTOR"
    agent_count: int = 0


class PatchSessionRequest(BaseModel):
    """Request body for PATCH /api/sessions/{session_id}."""
    status: Optional[str] = Field(
        default=None,
        description="Set to 'active' or 'resolution' to change session state",
    )
    paused: Optional[bool] = Field(
        default=None,
        description="Pause or resume all agents",
    )
    threat_level: Optional[str] = Field(
        default=None,
        description="Manual Chairman override of threat level",
    )


class PatchSessionResponse(BaseModel):
    """Response body for PATCH /api/sessions/{session_id}."""
    session_id: str
    updated_fields: list[str]
    current_state: dict


class DeleteSessionResponse(BaseModel):
    """Response body for DELETE /api/sessions/{session_id}."""
    session_id: str
    closed_at: str
    agents_released: int
    after_action_url: str


# ── SCENARIO RESPONSE MODELS ────────────────────────────────────────────


class AssemblyLogEntry(BaseModel):
    """A single line in the assembling-screen log."""
    line: str
    value: str
    status: str = "in_progress"  # "in_progress" | "complete"


class ScenarioAgentEntry(BaseModel):
    """Agent entry in the scenario response."""
    agent_id: str
    role_key: str
    role_title: str
    character_name: str
    defining_line: str = ""
    identity_color: str = "#666666"
    voice_name: str = ""
    status: str = "idle"


class ScenarioResponse(BaseModel):
    """Full scenario spec for GET /api/sessions/{session_id}/scenario (200)."""
    session_id: str
    crisis_title: str = ""
    crisis_domain: str = ""
    crisis_brief: str = ""
    scenario_instruction_guide: str = ""
    voice_runtime: dict = Field(default_factory=dict)
    threat_level_initial: str = "elevated"
    resolution_score_initial: int = 50
    agents: list[ScenarioAgentEntry] = Field(default_factory=list)
    initial_intel: list[dict] = Field(default_factory=list)
    initial_conflicts: list[dict] = Field(default_factory=list)
    escalation_schedule: list[dict] = Field(default_factory=list)
    assembly_log: list[AssemblyLogEntry] = Field(default_factory=list)
    scenario_ready: bool = False


class ScenarioPollingResponse(BaseModel):
    """Partial response for GET /api/sessions/{session_id}/scenario (202)."""
    scenario_ready: bool = False
    assembly_log: list[AssemblyLogEntry] = Field(default_factory=list)
    message: str = "Scenario analyst still running. Retry in 1 second."


class SkillResponse(BaseModel):
    """Response for GET /api/sessions/{session_id}/scenario/skill/{agent_id}."""
    agent_id: str
    character_name: str = ""
    role_title: str = ""
    voice_name: str = ""
    skill_md: str = ""
    generated_at: Optional[str] = None
    word_count: int = 0
