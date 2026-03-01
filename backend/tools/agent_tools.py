"""
WAR ROOM — Agent Interaction Tools
ADK function tools for reading other agents' public data and updating trust scores.
Strictly limited — agents can only read the LAST public statement, nothing else.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


async def read_other_agent_last_statement(
    session_id: str,
    my_agent_id: str,
    target_agent_id: str,
) -> dict:
    """
    Read another agent's last public statement.
    This is the ONLY cross-agent data access allowed.
    You can see what they said publicly — nothing else.

    Args:
        session_id: The current crisis session ID.
        my_agent_id: YOUR agent ID (for audit).
        target_agent_id: The agent whose statement you want to read.

    Returns:
        dict with: character_name, last_statement, stated_at
    """
    from utils.firestore_helpers import _get_db
    from config.constants import COLLECTION_AGENT_MEMORY, COLLECTION_CRISIS_SESSIONS

    db = _get_db()

    # Read the target agent's memory — but ONLY the last statement
    doc_id = f"{target_agent_id}_{session_id}"
    doc = await db.collection(COLLECTION_AGENT_MEMORY).document(doc_id).get()

    if not doc.exists:
        return {
            "error": f"Agent {target_agent_id} not found",
            "character_name": "Unknown",
            "last_statement": "",
        }

    data = doc.to_dict()
    statements = data.get("previous_statements", [])

    # SECURITY: Only return the LAST statement, nothing else from memory
    last_statement = ""
    stated_at = ""
    if statements:
        last = statements[-1]
        if isinstance(last, dict):
            last_statement = last.get("text", "")
            stated_at = last.get("spoken_at", "") or last.get("timestamp", "")
        else:
            last_statement = str(last)

    return {
        "character_name": data.get("character_name", "Unknown"),
        "last_statement": last_statement,
        "stated_at": stated_at,
    }


async def update_my_trust_score(
    session_id: str,
    agent_id: str,
    delta: int,
    reason: str,
) -> dict:
    """
    Update your own trust score in the roster.
    Typically called by the Observer Agent, but agents can self-report.

    Args:
        session_id: The current crisis session ID.
        agent_id: The agent whose trust score to update.
        delta: The change in trust score (-20 to +10).
        reason: One-line explanation (e.g., "Contradicted timeline commitment").

    Returns:
        dict with the new trust score.
    """
    from utils.firestore_helpers import _get_db
    from utils.events import push_event
    from config.constants import (
        COLLECTION_CRISIS_SESSIONS,
        EVENT_TRUST_SCORE_UPDATE,
    )

    db = _get_db()
    doc = await db.collection(COLLECTION_CRISIS_SESSIONS) \
                  .document(session_id).get()

    if not doc.exists:
        return {"error": "Session not found"}

    crisis = doc.to_dict()
    roster = crisis.get("agent_roster", [])

    new_score = 70  # default
    for agent in roster:
        if agent.get("agent_id") == agent_id:
            current_score = agent.get("trust_score", 70)
            new_score = max(0, min(100, current_score + delta))
            agent["trust_score"] = new_score
            break

    # Update the full roster (Firestore doesn't support array element updates)
    await db.collection(COLLECTION_CRISIS_SESSIONS) \
            .document(session_id) \
            .update({"agent_roster": roster})

    # Push event to frontend
    await push_event(session_id, EVENT_TRUST_SCORE_UPDATE, {
        "agent_id": agent_id,
        "score": new_score,
        "delta": delta,
        "reason": reason,
    })

    logger.info(f"Trust score update for {agent_id}: {delta:+d} → {new_score} ({reason})")
    return {"agent_id": agent_id, "new_score": new_score}
