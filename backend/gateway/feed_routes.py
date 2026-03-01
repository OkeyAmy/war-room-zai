"""
WAR ROOM — Crisis Feed Routes (API spec §5)
GET    /feed            — all feed items
GET    /feed/world      — world agent events
PATCH  /feed/{feed_id}  — mark read
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from utils.auth import get_chairman_token, validate_chairman_token
from utils.firestore_helpers import _get_db
from config.constants import COLLECTION_CRISIS_SESSIONS

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/sessions", tags=["Crisis Feed"])


class MarkReadRequest(BaseModel):
    read: bool = True


@router.get("/{session_id}/feed")
async def get_feed(
    session_id: str,
    source_type: Optional[str] = Query(default=None),
    limit: int = Query(default=30, ge=1, le=100),
    before: Optional[str] = Query(default=None),
    hot_only: bool = Query(default=False),
    token: str = Depends(get_chairman_token),
):
    session_data = await validate_chairman_token(session_id, token)
    items = session_data.get("crisis_feed", [])

    if source_type:
        items = [i for i in items if i.get("source_type") == source_type]
    if hot_only:
        items = [i for i in items if i.get("is_hot") or i.get("is_breaking")]
    if before:
        items = [i for i in items if i.get("timestamp", "") < before]

    items.sort(key=lambda x: x.get("timestamp", ""), reverse=True)

    tab_counts = {}
    unread_counts = {}
    for item in session_data.get("crisis_feed", []):
        st = item.get("source_type", "INTERNAL")
        tab_counts[st] = tab_counts.get(st, 0) + 1
        if not item.get("read"):
            unread_counts[st] = unread_counts.get(st, 0) + 1

    return {
        "session_id": session_id,
        "items": items[:limit],
        "tab_counts": tab_counts,
        "unread_counts": unread_counts,
        "has_more": len(items) > limit,
        "next_cursor": items[limit - 1].get("timestamp") if len(items) > limit else None,
    }


@router.get("/{session_id}/feed/world")
async def get_feed_world(
    session_id: str,
    limit: int = Query(default=10, ge=1, le=50),
    token: str = Depends(get_chairman_token),
):
    session_data = await validate_chairman_token(session_id, token)
    escalations = session_data.get("world_events", [])
    escalations.sort(key=lambda x: x.get("fired_at", ""), reverse=True)

    next_esc = session_data.get("next_escalation", {})

    return {
        "world_events": escalations[:limit],
        "next_escalation_at": next_esc.get("at"),
        "next_escalation_in_seconds": next_esc.get("in_seconds", 0),
    }


@router.patch("/{session_id}/feed/{feed_id}")
async def mark_feed_read(
    session_id: str,
    feed_id: str,
    body: MarkReadRequest,
    token: str = Depends(get_chairman_token),
):
    await validate_chairman_token(session_id, token)
    db = _get_db()
    doc_ref = db.collection(COLLECTION_CRISIS_SESSIONS).document(session_id)
    doc = await doc_ref.get()
    data = doc.to_dict() if doc.exists else {}
    feed = data.get("crisis_feed", [])

    for item in feed:
        if item.get("feed_id") == feed_id:
            item["read"] = body.read
            break

    await doc_ref.update({"crisis_feed": feed})

    return {"feed_id": feed_id, "read": body.read}
