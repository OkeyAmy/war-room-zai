"""
WAR ROOM — Resolution Score Routes (API spec §9)
GET  /score          — current score + next escalation timer
GET  /score/history  — full score history for sparkline
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Query

from utils.auth import get_chairman_token, validate_chairman_token

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/sessions", tags=["Resolution Score"])


def _score_label(score: int) -> str:
    if score >= 70:
        return "RESOLVED"
    elif score >= 50:
        return "RECOVERING"
    elif score >= 30:
        return "CRITICAL"
    return "MELTDOWN"


@router.get("/{session_id}/score")
async def get_score(
    session_id: str,
    token: str = Depends(get_chairman_token),
):
    session_data = await validate_chairman_token(session_id, token)

    score = session_data.get("resolution_score", 50)
    history = session_data.get("score_history", [score])
    delta = 0
    if len(history) >= 2:
        delta = history[-1] - history[-2]

    next_esc = session_data.get("next_escalation", {})

    trend = "stable"
    if delta > 0:
        trend = "improving"
    elif delta < 0:
        trend = "declining"

    return {
        "session_id": session_id,
        "score": score,
        "label": _score_label(score),
        "trend": trend,
        "trend_arrow": "↑" if delta > 0 else ("↓" if delta < 0 else "→"),
        "delta_last_change": delta,
        "score_history": history[-20:],
        "driver": session_data.get("score_driver", ""),
        "target": 70,
        "target_label": "Target: 70+ to stabilize outcome",
        "next_escalation": {
            "at": next_esc.get("at", ""),
            "in_seconds": next_esc.get("in_seconds", 0),
            "formatted": next_esc.get("formatted", ""),
            "blinking": next_esc.get("in_seconds", 999) < 60,
        },
        "threat_level": session_data.get("threat_level", "elevated"),
        "last_updated": session_data.get("updated_at", ""),
    }


@router.get("/{session_id}/score/history")
async def get_score_history(
    session_id: str,
    limit: int = Query(default=30, ge=1, le=100),
    token: str = Depends(get_chairman_token),
):
    session_data = await validate_chairman_token(session_id, token)
    history = session_data.get("score_history_detailed", [])
    score = session_data.get("resolution_score", 50)

    if not history:
        history = [{"score": score, "at": session_data.get("created_at", ""), "event": "Session started"}]

    return {
        "history": history[-limit:],
        "current_score": score,
        "starting_score": history[0].get("score", score) if history else score,
        "net_change": score - (history[0].get("score", score) if history else score),
    }
