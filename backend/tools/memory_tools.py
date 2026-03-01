"""
WAR ROOM — Private Memory Tools
ADK function tools for agents to read/write their OWN private Firestore memory.
Each agent can ONLY access its own memory document — strict isolation.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


async def read_my_private_memory(
    session_id: str,
    agent_id: str,
) -> dict:
    """
    Read your private memory. Use this to check:
    - What you've publicly committed to (for consistency)
    - Your hidden agenda
    - Previous statements you've made
    - Private facts only you know

    Args:
        session_id: The current crisis session ID.
        agent_id: YOUR agent ID. You can only read your own memory.

    Returns:
        dict with: private_facts, hidden_agenda, private_commitments,
        previous_statements, public_positions, contradictions_detected
    """
    from utils.firestore_helpers import _get_db
    from config.constants import COLLECTION_AGENT_MEMORY

    db = _get_db()
    doc_id = f"{agent_id}_{session_id}"
    doc = await db.collection(COLLECTION_AGENT_MEMORY).document(doc_id).get()

    if not doc.exists:
        return {
            "private_facts": [],
            "hidden_agenda": "",
            "private_commitments": [],
            "previous_statements": [],
            "public_positions": {},
            "contradictions_detected": 0,
        }

    data = doc.to_dict()

    # Return ONLY private fields — never leak to other agents
    return {
        "private_facts": data.get("private_facts", []),
        "hidden_agenda": data.get("hidden_agenda", ""),
        "private_commitments": data.get("private_commitments", []),
        "previous_statements": data.get("previous_statements", []),
        "public_positions": data.get("public_positions", {}),
        "contradictions_detected": data.get("contradictions_detected", 0),
    }


async def write_my_private_memory(
    session_id: str,
    agent_id: str,
    key: str,
    value: str,
) -> dict:
    """
    Write to your private memory. Use this to record:
    - Public commitments you've made (so you stay consistent)
    - Private decisions you've made
    - New facts you've learned

    Args:
        session_id: The current crisis session ID.
        agent_id: YOUR agent ID. You can only write to your own memory.
        key: The memory key to update. One of:
            - "public_position": Record a public stance on a topic.
              Value format: "topic::position" (e.g., "timeline::We should delay 48h")
            - "private_commitment": Record a private decision.
            - "private_fact": Record a fact only you know.
        value: The value to store.

    Returns:
        dict confirming the write.
    """
    from utils.firestore_helpers import _get_db
    from config.constants import COLLECTION_AGENT_MEMORY

    db = _get_db()
    doc_id = f"{agent_id}_{session_id}"
    timestamp = datetime.now(timezone.utc).isoformat()

    update_data = {}

    if key == "public_position":
        # Format: "topic::position"
        parts = value.split("::", 1)
        topic = parts[0].strip() if len(parts) > 0 else "general"
        position = parts[1].strip() if len(parts) > 1 else value

        # Can't use Firestore nested field updates in mock, so do read-modify-write
        doc = await db.collection(COLLECTION_AGENT_MEMORY).document(doc_id).get()
        if doc.exists:
            data = doc.to_dict()
            positions = data.get("public_positions", {})
            positions[topic] = {
                "position": position,
                "stated_at": timestamp,
            }
            update_data["public_positions"] = positions

    elif key == "private_commitment":
        try:
            from google.cloud import firestore as fs
            update_data["private_commitments"] = fs.ArrayUnion([value])
        except ImportError:
            doc = await db.collection(COLLECTION_AGENT_MEMORY).document(doc_id).get()
            if doc.exists:
                data = doc.to_dict()
                commitments = data.get("private_commitments", [])
                commitments.append(value)
                update_data["private_commitments"] = commitments

    elif key == "private_fact":
        try:
            from google.cloud import firestore as fs
            update_data["private_facts"] = fs.ArrayUnion([value])
        except ImportError:
            doc = await db.collection(COLLECTION_AGENT_MEMORY).document(doc_id).get()
            if doc.exists:
                data = doc.to_dict()
                facts = data.get("private_facts", [])
                facts.append(value)
                update_data["private_facts"] = facts
    else:
        return {"error": f"Unknown memory key: {key}"}

    if update_data:
        await db.collection(COLLECTION_AGENT_MEMORY) \
                .document(doc_id) \
                .update(update_data)

    logger.debug(f"Agent {agent_id} wrote to memory: {key}")
    return {"status": "written", "key": key}
