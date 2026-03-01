"""
WAR ROOM — World Agent Routes (API spec §10)
GET   /world          — world agent status + escalation schedule
POST  /world/escalate — chairman triggers manual escalation
"""

from __future__ import annotations

import uuid
import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from utils.auth import get_chairman_token, validate_chairman_token
from utils.firestore_helpers import _get_db
from utils.events import push_event
from config.constants import COLLECTION_CRISIS_SESSIONS

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/sessions", tags=["World Agent"])


class EscalateRequest(BaseModel):
    event_text: str
    event_type: str = "INTERNAL"
    score_impact: int = -8


@router.get("/{session_id}/world")
async def get_world(
    session_id: str,
    token: str = Depends(get_chairman_token),
):
    session_data = await validate_chairman_token(session_id, token)

    world_events = session_data.get("world_events", [])
    next_esc = session_data.get("next_escalation", {})
    esc_schedule = session_data.get("escalation_schedule", [])
    fired_count = len(world_events)

    return {
        "session_id": session_id,
        "world_agent_active": True,
        "escalations_fired": fired_count,
        "escalations_remaining": max(0, len(esc_schedule) - fired_count),
        "next_escalation": {
            "at": next_esc.get("at", ""),
            "in_seconds": next_esc.get("in_seconds", 0),
            "type": next_esc.get("type", "INTERNAL"),
            "preview": None,
        },
        "fired_events": world_events,
    }


@router.post("/{session_id}/world/escalate", status_code=201)
async def trigger_escalation(
    session_id: str,
    body: EscalateRequest,
    token: str = Depends(get_chairman_token),
):
    session_data = await validate_chairman_token(session_id, token)
    db = _get_db()
    now = datetime.now(timezone.utc).isoformat()
    event_id = str(uuid.uuid4())

    # Create escalation event
    esc_event = {
        "event_id": event_id,
        "text": body.event_text,
        "type": body.event_type,
        "fired_at": now,
        "score_impact": body.score_impact,
        "threat_level_after": session_data.get("threat_level", "elevated"),
    }

    # Update session
    doc_ref = db.collection(COLLECTION_CRISIS_SESSIONS).document(session_id)
    doc = await doc_ref.get()
    data = doc.to_dict() if doc.exists else {}

    world_events = data.get("world_events", [])
    world_events.append(esc_event)

    score = data.get("resolution_score", 50)
    new_score = max(0, score + body.score_impact)

    feed = data.get("crisis_feed", [])
    feed.append({
        "feed_id": str(uuid.uuid4()),
        "text": body.event_text,
        "source_name": "🌐 WORLD AGENT",
        "source_type": body.event_type,
        "category_icon": "🌐",
        "timestamp": now,
        "is_hot": True,
        "is_breaking": True,
    })

    await doc_ref.update({
        "world_events": world_events,
        "resolution_score": new_score,
        "crisis_feed": feed,
        "updated_at": now,
    })

    # Push WS events
    await push_event(session_id, "crisis_escalation", esc_event)
    await push_event(session_id, "score_update", {
        "score": new_score,
        "label": "CRITICAL" if new_score < 50 else "RECOVERING",
        "trend": "declining",
    })
    await push_event(session_id, "feed_item", {
        "text": body.event_text,
        "source_name": "🌐 WORLD AGENT",
        "source_type": body.event_type,
        "timestamp": now,
        "is_breaking": True,
    })

    # Broadcast to all agents
    from gateway.chairman_handler import get_agents
    agents = get_agents(session_id)
    broadcast_count = 0
    for key, agent in agents.items():
        if agent.live_session:
            try:
                await agent.send_text(
                    f"[WORLD ESCALATION — {body.event_type}]: {body.event_text}\n"
                    f"The crisis has intensified. Adjust your assessment."
                )
                broadcast_count += 1
            except Exception as e:
                logger.warning(f"Failed to broadcast escalation to {key}: {e}")

    return {
        "event_id": event_id,
        "fired_at": now,
        "score_impact": body.score_impact,
        "broadcast_to_agents": broadcast_count,
    }
