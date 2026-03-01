"""
WAR ROOM — Event Push Utility
Writes events to the session_events sub-collection AND pushes them
directly to a shared asyncio.Queue for instant WebSocket forwarding.

In development:  data/session_events/{session_id}/events/{event_id}.json
In production:   Firestore session_events/{session_id}/events/{event_id}

Audio chunks use push_event_direct() to skip Firestore entirely
(too large + too slow for real-time streaming).
"""

from __future__ import annotations

import asyncio
import uuid
import logging
from datetime import datetime, timezone
from typing import Optional

from config.constants import (
    COLLECTION_SESSION_EVENTS,
    SUBCOLLECTION_EVENTS,
)

logger = logging.getLogger(__name__)


# ── DIRECT PUSH QUEUES ──────────────────────────────────────────────────
# One queue per session. The gateway WS handler reads from these
# instead of relying on Firestore snapshots.

_ws_queues: dict[str, asyncio.Queue] = {}


def get_event_queue(session_id: str) -> asyncio.Queue:
    """Get (or create) the direct-push queue for a session."""
    if session_id not in _ws_queues:
        _ws_queues[session_id] = asyncio.Queue()
    return _ws_queues[session_id]


def remove_event_queue(session_id: str) -> None:
    """Clean up when session closes."""
    _ws_queues.pop(session_id, None)


# ── PUBLIC API ───────────────────────────────────────────────────────────


async def push_event(
    session_id: str,
    event_type: str,
    payload: dict,
    source_agent_id: str = "system",
) -> str:
    """
    Writes an event to the session_events sub-collection AND
    pushes it directly to the WS queue for instant frontend delivery.
    """
    from utils.firestore_helpers import _get_db

    db = _get_db()
    event_id = str(uuid.uuid4())
    timestamp = datetime.now(timezone.utc).isoformat()

    event_data = {
        "event_id": event_id,
        "session_id": session_id,
        "event_type": event_type,
        "source_agent_id": source_agent_id,
        "timestamp": timestamp,
        "payload": payload,
        "consumed_by_frontend": False,
    }

    # Persist to Firestore / local storage
    await (
        db.collection(COLLECTION_SESSION_EVENTS)
          .document(session_id)
          .collection(SUBCOLLECTION_EVENTS)
          .document(event_id)
          .set(event_data)
    )

    # Direct push to WS queue (instant delivery)
    q = _ws_queues.get(session_id)
    if q:
        await q.put(event_data)

    logger.debug(f"[EVENT] {event_type} → session {session_id} ({event_id[:8]})")
    return event_id


async def push_event_direct(
    session_id: str,
    event_type: str,
    payload: dict,
    source_agent_id: str = "system",
) -> None:
    """
    Push an event ONLY to the WS queue — skip Firestore persistence.
    Used for high-frequency events like audio chunks that would
    overwhelm storage and add unacceptable latency.
    """
    event_data = {
        "event_id": str(uuid.uuid4()),
        "session_id": session_id,
        "event_type": event_type,
        "source_agent_id": source_agent_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "payload": payload,
    }

    q = _ws_queues.get(session_id)
    if q:
        await q.put(event_data)


def get_session_events(session_id: str) -> list[dict]:
    """
    Read all events for a session from the local dev store (testing/debug only).
    Returns [] when running against real Firestore (use a query instead).
    """
    from utils.firestore_helpers import _get_db
    from utils.local_storage import LocalDevDB

    db = _get_db()
    if not isinstance(db, LocalDevDB):
        logger.warning("get_session_events() is only available with LocalDevDB")
        return []

    sub = (
        db.collection(COLLECTION_SESSION_EVENTS)
          .document(session_id)
          .collection(SUBCOLLECTION_EVENTS)
    )
    return sub.get_all_events()
