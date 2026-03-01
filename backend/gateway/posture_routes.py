"""
WAR ROOM — Crisis Posture Routes (API spec §8)
GET  /posture          — current posture values
GET  /posture/history  — trend data for sparklines
"""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, Query

from utils.auth import get_chairman_token, validate_chairman_token

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/sessions", tags=["Crisis Posture"])


@router.get("/{session_id}/posture")
async def get_posture(
    session_id: str,
    token: str = Depends(get_chairman_token),
):
    session_data = await validate_chairman_token(session_id, token)

    posture = session_data.get("posture", {})

    # Default posture if not set
    default_axes = {
        "public_exposure": {
            "value": 45, "status": "elevated", "trend": "stable",
            "trend_arrow": "→", "sub_metric": "Viral velocity: STABLE",
            "driver": "No media escalation yet",
        },
        "legal_exposure": {
            "value": 30, "status": "contained", "trend": "stable",
            "trend_arrow": "→", "sub_metric": "Liability scan active",
            "driver": "Legal counsel reviewing",
        },
        "internal_stability": {
            "value": 75, "status": "good", "trend": "stable",
            "trend_arrow": "→", "sub_metric": "Team alignment nominal",
            "driver": "Agents cooperating",
        },
    }

    return {
        "session_id": session_id,
        "last_updated": session_data.get("updated_at", ""),
        "axes": posture.get("axes", default_axes),
    }


@router.get("/{session_id}/posture/history")
async def get_posture_history(
    session_id: str,
    axis: str = Query(default="public_exposure"),
    limit: int = Query(default=20, ge=1, le=100),
    token: str = Depends(get_chairman_token),
):
    session_data = await validate_chairman_token(session_id, token)
    histories = session_data.get("posture_history", {})
    axis_history = histories.get(axis, [])

    return {
        "axis": axis,
        "history": axis_history[-limit:],
    }
