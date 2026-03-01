"""
WAR ROOM — Constants
Voice pool, event types, Firestore collection names, and static config.
"""

# ── FIRESTORE COLLECTIONS ────────────────────────────────────────────────
COLLECTION_CRISIS_SESSIONS = "crisis_sessions"
COLLECTION_AGENT_MEMORY = "agent_memory"
COLLECTION_AGENT_SKILLS = "agent_skills"
COLLECTION_SESSION_EVENTS = "session_events"
SUBCOLLECTION_EVENTS = "events"

# ── SESSION STATUSES ─────────────────────────────────────────────────────
SESSION_ASSEMBLING = "assembling"
SESSION_BRIEFING = "briefing"
SESSION_ACTIVE = "active"
SESSION_ESCALATION = "escalation"
SESSION_RESOLUTION = "resolution"
SESSION_CLOSED = "closed"

# ── AGENT STATUSES ───────────────────────────────────────────────────────
AGENT_IDLE = "idle"
AGENT_THINKING = "thinking"
AGENT_SPEAKING = "speaking"
AGENT_CONFLICTED = "conflicted"
AGENT_SILENT = "silent"

# ── THREAT LEVELS ────────────────────────────────────────────────────────
THREAT_CONTAINED = "contained"
THREAT_ELEVATED = "elevated"
THREAT_CRITICAL = "critical"
THREAT_MELTDOWN = "meltdown"

THREAT_LEVEL_THRESHOLDS = {
    THREAT_MELTDOWN: 20,    # score < 20
    THREAT_CRITICAL: 35,    # score < 35
    THREAT_ELEVATED: 55,    # score < 55
    THREAT_CONTAINED: 100,  # score >= 55
}

# ── INTEL SOURCES ────────────────────────────────────────────────────────
INTEL_WORLD = "WORLD"
INTEL_MEDIA = "MEDIA"
INTEL_LEGAL = "LEGAL"
INTEL_INTERNAL = "INTERNAL"
INTEL_SOCIAL = "SOCIAL"

# ── CRISIS DOMAINS ───────────────────────────────────────────────────────
DOMAIN_CORPORATE = "corporate"
DOMAIN_MILITARY = "military"
DOMAIN_MEDICAL = "medical"
DOMAIN_POLITICAL = "political"
DOMAIN_FANTASY = "fantasy"
DOMAIN_OTHER = "other"

# ── EVENT TYPES ──────────────────────────────────────────────────────────
EVENT_SESSION_STATUS = "session_status"
EVENT_AGENT_ASSEMBLING = "agent_assembling"
EVENT_SESSION_READY = "session_ready"
EVENT_AGENT_STATUS_CHANGE = "agent_status_change"
EVENT_AGENT_SPEAKING_START = "agent_speaking_start"
EVENT_AGENT_SPEAKING_CHUNK = "agent_speaking_chunk"
EVENT_AGENT_SPEAKING_END = "agent_speaking_end"
EVENT_AGENT_INTERRUPTED = "agent_interrupted"
EVENT_AGENT_THINKING = "agent_thinking"
EVENT_DECISION_AGREED = "decision_agreed"
EVENT_CONFLICT_OPENED = "conflict_opened"
EVENT_CONFLICT_RESOLVED = "conflict_resolved"
EVENT_INTEL_DROPPED = "intel_dropped"
EVENT_FEED_ITEM = "feed_item"
EVENT_OBSERVER_INSIGHT = "observer_insight"
EVENT_TRUST_SCORE_UPDATE = "trust_score_update"
EVENT_POSTURE_UPDATE = "posture_update"
EVENT_SCORE_UPDATE = "score_update"
EVENT_CRISIS_ESCALATION = "crisis_escalation"
EVENT_THREAT_LEVEL_CHANGE = "threat_level_change"
EVENT_TIMER_TICK = "timer_tick"
EVENT_CHAIRMAN_SPOKE = "chairman_spoke"
EVENT_RESOLUTION_MODE_START = "resolution_mode_start"
EVENT_AGENT_FINAL_POSITION = "agent_final_position"
EVENT_SESSION_RESOLVED = "session_resolved"

# ── VOICE POOL (ElevenLabs voice IDs) ───────────────────────────────────
# These IDs map to default/public voices and are used as stable fallbacks.
ALLOWED_VOICE_POOL = [
    "EXAVITQu4vr4xnSDxMaL",  # Sarah
    "nPczCjzI2devNBz1zQrb",  # Brian
    "cgSgspJ2msm6clMCkdW9",  # Jessica
    "cjVigY5qzO86Huf0OWal",  # Eric
    "SOYHLrjzK2X1ezoPC6cr",  # Harry
    "pNInz6obpgDQGcFmaJgB",  # Adam
    "CwhRBWXzGAHq8TQ4Fs17",  # Roger
    "onwK4e9ZLuTAKqWW03F9",  # Daniel
    "pFZP5JQG7iQjIQuC4Bku",  # Lily
    "Xb7hH8MSUJpSbSDYk0k2",  # Alice,
    "tnSpp4vdxKPjI9w0GnoV"
]

VOICE_STYLE_MAP = {
    "authoritative": ["nPczCjzI2devNBz1zQrb", "SOYHLrjzK2X1ezoPC6cr", "pNInz6obpgDQGcFmaJgB"],
    "warm":          ["EXAVITQu4vr4xnSDxMaL", "pFZP5JQG7iQjIQuC4Bku", "Xb7hH8MSUJpSbSDYk0k2", "tnSpp4vdxKPjI9w0GnoV"],
    "clipped":       ["CwhRBWXzGAHq8TQ4Fs17", "cjVigY5qzO86Huf0OWal", "onwK4e9ZLuTAKqWW03F9"],
    "measured":      ["cgSgspJ2msm6clMCkdW9", "pFZP5JQG7iQjIQuC4Bku", "cjVigY5qzO86Huf0OWal"],
    "urgent":        ["SOYHLrjzK2X1ezoPC6cr", "nPczCjzI2devNBz1zQrb", "onwK4e9ZLuTAKqWW03F9"],
    "calm":          ["Xb7hH8MSUJpSbSDYk0k2", "EXAVITQu4vr4xnSDxMaL", "cgSgspJ2msm6clMCkdW9"],
    "aggressive":    ["pNInz6obpgDQGcFmaJgB", "SOYHLrjzK2X1ezoPC6cr", "nPczCjzI2devNBz1zQrb"],
}

# Legacy Gemini Live voices for fallback mode when ElevenLabs is unavailable.
GEMINI_FALLBACK_VOICES = [
    "Aoede", "Charon", "Fenrir", "Kore", "Puck",
    "Achird", "Algenib", "Algieba", "Alnilam",
    "Auva", "Callirrhoe", "Despina", "Enceladus", "Erinome",
    "Gacrux", "Iapetus", "Laomedeia", "Leda", "Orus",
    "Pulcherrima", "Rasalgethi", "Sadachbia", "Sadaltager",
    "Schedar", "Sulafat", "Umbriel", "Vindemiatrix",
    "Zephyr", "Zubenelgenubi",
]

# ── POSTURE DEFAULTS ─────────────────────────────────────────────────────
DEFAULT_POSTURE = {
    "public_exposure": 60,
    "legal_exposure": 45,
    "internal_stability": 50,
    "public_trend": "rising",
    "legal_trend": "stable",
    "internal_trend": "stable",
}

# ── ESCALATION EVENT TYPES ───────────────────────────────────────────────
ESCALATION_TYPES = ["media", "legal", "internal", "social", "operational"]

# ── RISK AXES BY ROLE ────────────────────────────────────────────────────
ROLE_RISK_AXES = {
    "legal":    "legal_exposure",
    "pr":       "public_exposure",
    "engineer": "internal_stability",
    "finance":  "legal_exposure",
    "ops":      "internal_stability",
    "comms":    "public_exposure",
    "strategy": "resolution_score",
}
