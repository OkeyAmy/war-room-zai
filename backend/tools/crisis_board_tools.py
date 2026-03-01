"""
WAR ROOM — Crisis Board Tools
ADK function tools for agents to read/write the shared Crisis Board.
These are the ONLY way agents interact with shared state.
"""

from __future__ import annotations

import uuid
import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


# ── TOOL CONTEXT ─────────────────────────────────────────────────────────
# These tools receive agent context via closure when bound in CrisisAgent.
# For ADK, they are plain async functions that the LLM can call.


async def read_crisis_board(
    session_id: str,
    agent_id: str,
) -> dict:
    """
    Read the current state of the Crisis Board.
    Returns: agreed decisions, open conflicts, critical intel, posture, and score.
    Call this at the START of every turn to understand the current room state.

    Args:
        session_id: The current crisis session ID.
        agent_id: Your agent ID (for audit logging).

    Returns:
        dict with keys: agreed_decisions, open_conflicts, critical_intel,
        posture, resolution_score, threat_level
    """
    from utils.firestore_helpers import _get_db
    from config.constants import COLLECTION_CRISIS_SESSIONS

    db = _get_db()
    doc = await db.collection(COLLECTION_CRISIS_SESSIONS) \
                  .document(session_id).get()

    if not doc.exists:
        return {"error": "Session not found"}

    crisis = doc.to_dict()

    # Return only the public Crisis Board data — NO private agent info
    return {
        "crisis_title": crisis.get("crisis_title", ""),
        "crisis_brief": crisis.get("crisis_brief", ""),
        "status": crisis.get("status", ""),
        "agreed_decisions": crisis.get("agreed_decisions", []),
        "open_conflicts": crisis.get("open_conflicts", []),
        "critical_intel": crisis.get("critical_intel", []),
        "posture": crisis.get("posture", {}),
        "resolution_score": crisis.get("resolution_score", 50),
        "threat_level": crisis.get("threat_level", "elevated"),
        "escalation_events": crisis.get("escalation_events", []),
    }


async def write_agreed_decision(
    session_id: str,
    agent_id: str,
    text: str,
    agents_agreed: list[str],
) -> dict:
    """
    Record a decision that has been agreed upon in the room.
    Call this when consensus is reached on a specific action.

    Args:
        session_id: The current crisis session ID.
        agent_id: Your agent ID (the proposer).
        text: The decision text (what was agreed).
        agents_agreed: List of agent_ids who agreed to this decision.

    Returns:
        dict with the decision_id of the newly created decision.
    """
    from utils.firestore_helpers import _get_db
    from utils.events import push_event
    from config.constants import (
        COLLECTION_CRISIS_SESSIONS,
        EVENT_DECISION_AGREED,
    )

    db = _get_db()
    decision_id = str(uuid.uuid4())[:8]
    timestamp = datetime.now(timezone.utc).isoformat()

    decision = {
        "decision_id": decision_id,
        "text": text,
        "agreed_at": timestamp,
        "agents_agreed": agents_agreed,
        "proposed_by": agent_id,
    }

    # Append to crisis session document
    try:
        from google.cloud import firestore as fs
        await db.collection(COLLECTION_CRISIS_SESSIONS) \
                .document(session_id) \
                .update({"agreed_decisions": fs.ArrayUnion([decision])})
    except ImportError:
        # Local dev fallback
        doc = await db.collection(COLLECTION_CRISIS_SESSIONS) \
                      .document(session_id).get()
        if doc.exists:
            data = doc.to_dict()
            decisions = data.get("agreed_decisions", [])
            decisions.append(decision)
            await db.collection(COLLECTION_CRISIS_SESSIONS) \
                    .document(session_id) \
                    .update({"agreed_decisions": decisions})

    # Push event to frontend
    await push_event(session_id, EVENT_DECISION_AGREED, decision, agent_id)

    logger.info(f"Decision agreed: {text[:50]}... by {agent_id}")
    return {"decision_id": decision_id, "status": "recorded"}


async def write_open_conflict(
    session_id: str,
    agent_id: str,
    description: str,
    agents_involved: list[str],
    severity: str = "medium",
) -> dict:
    """
    Register a conflict in the Crisis Board.
    Call this when you fundamentally disagree with another agent's position.

    Args:
        session_id: The current crisis session ID.
        agent_id: Your agent ID (the reporter).
        description: What the conflict is about.
        agents_involved: List of agent_ids in this conflict.
        severity: "low" | "medium" | "high" | "critical"

    Returns:
        dict with the conflict_id of the newly created conflict.
    """
    from utils.firestore_helpers import _get_db
    from utils.events import push_event
    from config.constants import (
        COLLECTION_CRISIS_SESSIONS,
        EVENT_CONFLICT_OPENED,
    )

    db = _get_db()
    conflict_id = str(uuid.uuid4())[:8]
    timestamp = datetime.now(timezone.utc).isoformat()

    conflict = {
        "conflict_id": conflict_id,
        "description": description,
        "agents_involved": agents_involved,
        "opened_at": timestamp,
        "severity": severity,
    }

    try:
        from google.cloud import firestore as fs
        await db.collection(COLLECTION_CRISIS_SESSIONS) \
                .document(session_id) \
                .update({"open_conflicts": fs.ArrayUnion([conflict])})
    except ImportError:
        doc = await db.collection(COLLECTION_CRISIS_SESSIONS) \
                      .document(session_id).get()
        if doc.exists:
            data = doc.to_dict()
            conflicts = data.get("open_conflicts", [])
            conflicts.append(conflict)
            await db.collection(COLLECTION_CRISIS_SESSIONS) \
                    .document(session_id) \
                    .update({"open_conflicts": conflicts})

    await push_event(session_id, EVENT_CONFLICT_OPENED, conflict, agent_id)

    logger.info(f"Conflict opened: {description[:50]}... involving {agents_involved}")
    return {"conflict_id": conflict_id, "status": "recorded"}


async def write_critical_intel(
    session_id: str,
    agent_id: str,
    text: str,
    source: str,
    is_escalation: bool = False,
) -> dict:
    """
    Drop critical intelligence into the Crisis Board.
    Call this when you have room-critical information to share.

    Args:
        session_id: The current crisis session ID.
        agent_id: Your agent ID (the source).
        text: The intel text.
        source: "WORLD" | "MEDIA" | "LEGAL" | "INTERNAL" | "SOCIAL"
        is_escalation: Whether this is an escalation event.

    Returns:
        dict with the intel_id.
    """
    from utils.firestore_helpers import _get_db
    from utils.events import push_event
    from config.constants import (
        COLLECTION_CRISIS_SESSIONS,
        EVENT_INTEL_DROPPED,
    )

    db = _get_db()
    intel_id = str(uuid.uuid4())[:8]
    timestamp = datetime.now(timezone.utc).isoformat()

    intel = {
        "intel_id": intel_id,
        "text": text,
        "source": source.upper(),
        "timestamp": timestamp,
        "is_escalation": is_escalation,
    }

    try:
        from google.cloud import firestore as fs
        await db.collection(COLLECTION_CRISIS_SESSIONS) \
                .document(session_id) \
                .update({"critical_intel": fs.ArrayUnion([intel])})
    except ImportError:
        doc = await db.collection(COLLECTION_CRISIS_SESSIONS) \
                      .document(session_id).get()
        if doc.exists:
            data = doc.to_dict()
            intels = data.get("critical_intel", [])
            intels.append(intel)
            await db.collection(COLLECTION_CRISIS_SESSIONS) \
                    .document(session_id) \
                    .update({"critical_intel": intels})

    await push_event(session_id, EVENT_INTEL_DROPPED, intel, agent_id)

    logger.info(f"Intel dropped: {text[:50]}... from {source}")
    return {"intel_id": intel_id, "status": "recorded"}
