"""
WAR ROOM — Resolution & After-Action Routes (API spec §13)
POST  /resolution  — chairman calls resolution
GET   /report      — after-action report

Also includes remaining Chairman routes (vote, commands history).
POST  /chairman/vote     — force vote
GET   /chairman/commands — command history
"""

from __future__ import annotations

import uuid
import asyncio
import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from utils.auth import get_chairman_token, validate_chairman_token
from utils.firestore_helpers import _get_db
from utils.events import push_event
from config.constants import COLLECTION_CRISIS_SESSIONS

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/sessions", tags=["Resolution & Chairman"])


# ── Request Models ──────────────────────────────────────────────────────

class ResolutionRequest(BaseModel):
    final_decision: str

class VoteRequest(BaseModel):
    question: str
    time_limit_seconds: int = 120


# ── POST /resolution ───────────────────────────────────────────────────

@router.post("/{session_id}/resolution")
async def call_resolution(
    session_id: str,
    body: ResolutionRequest,
    token: str = Depends(get_chairman_token),
):
    session_data = await validate_chairman_token(session_id, token)
    db = _get_db()
    now = datetime.now(timezone.utc).isoformat()
    resolution_id = str(uuid.uuid4())

    await push_event(session_id, "resolution_mode_start", {
        "final_decision": body.final_decision,
    })

    # Get agent final positions (ask each for verdict)
    from gateway.chairman_handler import get_agents
    agents = get_agents(session_id)
    positions = []

    for key, agent in agents.items():
        if agent.live_session:
            try:
                await agent.send_text(
                    f"The Chairman has made the final decision: \"{body.final_decision}\"\n"
                    f"State your final position: do you AGREE, DISSENT, or remain NEUTRAL? "
                    f"Give a one-sentence verdict."
                )
            except Exception:
                pass

    # Update session
    await db.collection(COLLECTION_CRISIS_SESSIONS).document(session_id).update({
        "status": "resolving",
        "final_decision": body.final_decision,
        "resolved_at": now,
        "updated_at": now,
    })

    return {
        "resolution_id": resolution_id,
        "final_decision": body.final_decision,
        "resolved_at": now,
        "processing": True,
        "message": "Generating agent final positions and projected futures...",
    }


# ── GET /report ────────────────────────────────────────────────────────

@router.get("/{session_id}/report")
async def get_report(
    session_id: str,
    token: str = Depends(get_chairman_token),
):
    session_data = await validate_chairman_token(session_id, token)

    roster = session_data.get("agent_roster", [])
    agent_positions = []
    for entry in roster:
        if entry.get("status") != "dismissed":
            agent_positions.append({
                "agent_id": entry.get("agent_id", ""),
                "name": entry.get("character_name", ""),
                "verdict": entry.get("final_verdict", "No verdict recorded"),
                "alignment": entry.get("final_alignment", "neutral"),
                "final_trust": entry.get("trust_score", 70),
            })

    world_events = session_data.get("world_events", [])
    conflicts = session_data.get("open_conflicts", [])
    decisions = session_data.get("agreed_decisions", [])

    return {
        "session_id": session_id,
        "crisis_title": session_data.get("crisis_title", ""),
        "duration": {
            "started_at": session_data.get("created_at", ""),
            "ended_at": session_data.get("resolved_at", ""),
            "total_minutes": 0,
        },
        "final_decision": session_data.get("final_decision", ""),
        "final_score": session_data.get("resolution_score", 50),
        "final_threat_level": session_data.get("threat_level", "elevated"),
        "agent_positions": agent_positions,
        "projected_futures": session_data.get("projected_futures", []),
        "key_moments": session_data.get("key_moments", []),
        "statistics": {
            "total_statements": 0,
            "total_conflicts": len(conflicts),
            "conflicts_resolved": sum(1 for c in conflicts if c.get("resolution")),
            "decisions_made": len(decisions),
            "escalations": len(world_events),
            "chairman_commands": 0,
            "votes_called": 0,
        },
        "replay_available": True,
        "replay_start_url": f"/api/sessions/{session_id}/board/timeline?at={session_data.get('created_at', '')}",
    }


# ── POST /chairman/vote ───────────────────────────────────────────────

@router.post("/{session_id}/chairman/vote", status_code=202)
async def call_vote(
    session_id: str,
    body: VoteRequest,
    token: str = Depends(get_chairman_token),
):
    await validate_chairman_token(session_id, token)
    now = datetime.now(timezone.utc).isoformat()
    vote_id = str(uuid.uuid4())

    from gateway.chairman_handler import get_agents
    agents = get_agents(session_id)
    voting_agents = []

    for key, agent in agents.items():
        if agent.live_session:
            voting_agents.append(agent.agent_id)
            try:
                await agent.send_text(
                    f"VOTE CALLED by Chairman: \"{body.question}\"\n"
                    f"You must respond with YES or NO and a brief reason. "
                    f"Time limit: {body.time_limit_seconds} seconds."
                )
            except Exception:
                pass

    await push_event(session_id, "vote_called", {
        "vote_id": vote_id,
        "question": body.question,
        "agents_voting": voting_agents,
    })

    return {
        "vote_id": vote_id,
        "question": body.question,
        "started_at": now,
        "agents_voting": voting_agents,
    }


# ── GET /chairman/commands ─────────────────────────────────────────────

@router.get("/{session_id}/chairman/commands")
async def get_commands(
    session_id: str,
    limit: int = Query(default=20, ge=1, le=100),
    token: str = Depends(get_chairman_token),
):
    session_data = await validate_chairman_token(session_id, token)
    commands = session_data.get("chairman_commands", [])
    commands.sort(key=lambda x: x.get("issued_at", ""), reverse=True)

    return {
        "commands": commands[:limit],
        "count": len(commands),
    }
