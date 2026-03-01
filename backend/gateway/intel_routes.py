"""
WAR ROOM — Room Intelligence Routes (API spec §7)
GET  /intel                              — observer insights
GET  /intel/trust                        — all trust scores
GET  /intel/trust/{agent_id}/history     — trust history for one agent
"""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, Query

from utils.auth import get_chairman_token, validate_chairman_token
from utils.firestore_helpers import _get_db
from config.constants import COLLECTION_CRISIS_SESSIONS

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/sessions", tags=["Room Intelligence"])


@router.get("/{session_id}/intel")
async def get_intel(
    session_id: str,
    type: Optional[str] = Query(default=None, alias="type"),
    limit: int = Query(default=10, ge=1, le=50),
    since: Optional[str] = Query(default=None),
    token: str = Depends(get_chairman_token),
):
    session_data = await validate_chairman_token(session_id, token)
    insights = session_data.get("observer_insights", [])

    if type:
        insights = [i for i in insights if i.get("type") == type]
    if since:
        insights = [i for i in insights if i.get("detected_at", "") > since]

    counts = {}
    for i in session_data.get("observer_insights", []):
        t = i.get("type", "other")
        counts[t] = counts.get(t, 0) + 1

    return {
        "session_id": session_id,
        "insights": insights[:limit],
        "insight_counts": counts,
    }


@router.get("/{session_id}/intel/trust")
async def get_trust_scores(
    session_id: str,
    token: str = Depends(get_chairman_token),
):
    session_data = await validate_chairman_token(session_id, token)
    roster = session_data.get("agent_roster", [])

    scores = []
    for entry in roster:
        if entry.get("status") == "dismissed":
            continue
        scores.append({
            "agent_id": entry.get("agent_id", ""),
            "character_name": entry.get("character_name", ""),
            "score": entry.get("trust_score", 70),
            "trend": entry.get("trust_trend", "stable"),
            "delta_last_turn": entry.get("trust_delta", 0),
            "reason": entry.get("trust_reason", ""),
            "contradiction_count": entry.get("contradiction_count", 0),
        })

    return {
        "session_id": session_id,
        "trust_scores": scores,
        "last_updated": session_data.get("updated_at", ""),
    }


@router.get("/{session_id}/intel/trust/{agent_id}/history")
async def get_trust_history(
    session_id: str,
    agent_id: str,
    token: str = Depends(get_chairman_token),
):
    session_data = await validate_chairman_token(session_id, token)

    # Trust history stored in session events
    db = _get_db()
    history = []
    current_score = 70

    roster = session_data.get("agent_roster", [])
    for entry in roster:
        if entry.get("agent_id") == agent_id:
            current_score = entry.get("trust_score", 70)
            break

    # Try to get from trust_history array on session
    trust_histories = session_data.get("trust_histories", {})
    if agent_id in trust_histories:
        history = trust_histories[agent_id]
    else:
        history = [{"score": current_score, "at": session_data.get("created_at", ""), "reason": "Initial"}]

    return {
        "agent_id": agent_id,
        "history": history,
        "current_score": current_score,
        "starting_score": history[0].get("score", 70) if history else 70,
    }
