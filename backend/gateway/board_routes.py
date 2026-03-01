"""
WAR ROOM — Crisis Board Routes (API spec §4)
GET    /board              — full board state
GET    /board/decisions    — decisions column
POST   /board/decisions    — chairman pins decision
PATCH  /board/decisions/{id} — lock/pin decision
GET    /board/conflicts    — conflicts column
PATCH  /board/conflicts/{id} — resolve conflict
GET    /board/intel        — intel column
POST   /board/intel        — chairman injects intel
GET    /board/timeline     — board at past timestamp
"""

from __future__ import annotations

import uuid
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

router = APIRouter(prefix="/api/sessions", tags=["Crisis Board"])


# ── Request Models ──────────────────────────────────────────────────────

class CreateDecisionRequest(BaseModel):
    text: str
    source: str = "chairman"
    lock: bool = False

class LockDecisionRequest(BaseModel):
    locked: bool

class ResolveConflictRequest(BaseModel):
    resolution: str
    decision_text: Optional[str] = None

class InjectIntelRequest(BaseModel):
    text: str
    source_type: str = "INTERNAL"
    source: str = "CHAIRMAN / DIRECT"
    broadcast: bool = True


# ── GET /board — full board state ───────────────────────────────────────

@router.get("/{session_id}/board")
async def get_board(
    session_id: str,
    token: str = Depends(get_chairman_token),
):
    session_data = await validate_chairman_token(session_id, token)
    return {
        "session_id": session_id,
        "last_updated": session_data.get("updated_at", datetime.now(timezone.utc).isoformat()),
        "agreed_decisions": session_data.get("agreed_decisions", []),
        "open_conflicts": session_data.get("open_conflicts", []),
        "critical_intel": session_data.get("critical_intel", []),
    }


# ── GET /board/decisions ────────────────────────────────────────────────

@router.get("/{session_id}/board/decisions")
async def get_decisions(
    session_id: str,
    since: Optional[str] = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    token: str = Depends(get_chairman_token),
):
    session_data = await validate_chairman_token(session_id, token)
    decisions = session_data.get("agreed_decisions", [])

    if since:
        decisions = [d for d in decisions if d.get("agreed_at", "") > since]

    return {
        "decisions": decisions[:limit],
        "count": len(decisions),
        "last_updated": session_data.get("updated_at", ""),
    }


# ── POST /board/decisions — chairman pins decision ──────────────────────

@router.post("/{session_id}/board/decisions", status_code=201)
async def create_decision(
    session_id: str,
    body: CreateDecisionRequest,
    token: str = Depends(get_chairman_token),
):
    await validate_chairman_token(session_id, token)
    db = _get_db()
    now = datetime.now(timezone.utc).isoformat()
    decision_id = str(uuid.uuid4())

    decision = {
        "decision_id": decision_id,
        "text": body.text,
        "agreed_at": now,
        "proposed_by": body.source,
        "agents_agreed": [],
        "agents_dissented": [],
        "locked": body.lock,
    }

    doc_ref = db.collection(COLLECTION_CRISIS_SESSIONS).document(session_id)
    doc = await doc_ref.get()
    data = doc.to_dict() if doc.exists else {}
    decisions = data.get("agreed_decisions", [])
    decisions.append(decision)
    await doc_ref.update({"agreed_decisions": decisions, "updated_at": now})

    await push_event(session_id, "decision_agreed", decision)

    return decision


# ── PATCH /board/decisions/{decision_id} — lock/pin ─────────────────────

@router.patch("/{session_id}/board/decisions/{decision_id}")
async def lock_decision(
    session_id: str,
    decision_id: str,
    body: LockDecisionRequest,
    token: str = Depends(get_chairman_token),
):
    await validate_chairman_token(session_id, token)
    db = _get_db()
    now = datetime.now(timezone.utc).isoformat()

    doc_ref = db.collection(COLLECTION_CRISIS_SESSIONS).document(session_id)
    doc = await doc_ref.get()
    data = doc.to_dict() if doc.exists else {}
    decisions = data.get("agreed_decisions", [])

    for d in decisions:
        if d.get("decision_id") == decision_id:
            d["locked"] = body.locked
            break
    else:
        raise HTTPException(status_code=404, detail="Decision not found")

    await doc_ref.update({"agreed_decisions": decisions, "updated_at": now})

    return {"decision_id": decision_id, "locked": body.locked, "locked_at": now}


# ── GET /board/conflicts ────────────────────────────────────────────────

@router.get("/{session_id}/board/conflicts")
async def get_conflicts(
    session_id: str,
    status: str = Query(default="open"),
    severity: Optional[str] = Query(default=None),
    token: str = Depends(get_chairman_token),
):
    session_data = await validate_chairman_token(session_id, token)
    conflicts = session_data.get("open_conflicts", [])

    if status == "open":
        filtered = [c for c in conflicts if not c.get("resolution")]
    elif status == "resolved":
        filtered = [c for c in conflicts if c.get("resolution")]
    else:
        filtered = conflicts

    if severity:
        filtered = [c for c in filtered if c.get("severity") == severity]

    return {
        "conflicts": filtered,
        "open_count": sum(1 for c in conflicts if not c.get("resolution")),
        "resolved_count": sum(1 for c in conflicts if c.get("resolution")),
    }


# ── PATCH /board/conflicts/{conflict_id} — resolve ─────────────────────

@router.patch("/{session_id}/board/conflicts/{conflict_id}")
async def resolve_conflict(
    session_id: str,
    conflict_id: str,
    body: ResolveConflictRequest,
    token: str = Depends(get_chairman_token),
):
    await validate_chairman_token(session_id, token)
    db = _get_db()
    now = datetime.now(timezone.utc).isoformat()

    doc_ref = db.collection(COLLECTION_CRISIS_SESSIONS).document(session_id)
    doc = await doc_ref.get()
    data = doc.to_dict() if doc.exists else {}
    conflicts = data.get("open_conflicts", [])

    for c in conflicts:
        if c.get("conflict_id") == conflict_id:
            c["resolution"] = body.resolution
            c["resolved_at"] = now
            break
    else:
        raise HTTPException(status_code=404, detail="Conflict not found")

    updates = {"open_conflicts": conflicts, "updated_at": now}

    # Auto-create decision if decision_text provided
    auto_decision_id = None
    if body.decision_text:
        auto_decision_id = str(uuid.uuid4())
        decision = {
            "decision_id": auto_decision_id,
            "text": body.decision_text,
            "agreed_at": now,
            "proposed_by": "chairman",
            "locked": True,
        }
        decisions = data.get("agreed_decisions", [])
        decisions.append(decision)
        updates["agreed_decisions"] = decisions
        await push_event(session_id, "decision_agreed", decision)

    await doc_ref.update(updates)
    await push_event(session_id, "conflict_resolved", {
        "conflict_id": conflict_id, "resolution": body.resolution,
    })

    return {
        "conflict_id": conflict_id,
        "resolved_at": now,
        "resolution": body.resolution,
        "auto_created_decision_id": auto_decision_id,
    }


# ── GET /board/intel ────────────────────────────────────────────────────

@router.get("/{session_id}/board/intel")
async def get_intel(
    session_id: str,
    source_type: Optional[str] = Query(default=None),
    is_escalation: Optional[bool] = Query(default=None),
    since: Optional[str] = Query(default=None),
    token: str = Depends(get_chairman_token),
):
    session_data = await validate_chairman_token(session_id, token)
    intel = session_data.get("critical_intel", [])

    if source_type:
        intel = [i for i in intel if i.get("source_type") == source_type]
    if is_escalation is not None:
        intel = [i for i in intel if i.get("is_escalation") == is_escalation]
    if since:
        intel = [i for i in intel if i.get("received_at", "") > since]

    return {
        "intel": intel,
        "count": len(intel),
        "escalation_count": sum(1 for i in intel if i.get("is_escalation")),
    }


# ── POST /board/intel — chairman injects intel ──────────────────────────

@router.post("/{session_id}/board/intel", status_code=201)
async def inject_intel(
    session_id: str,
    body: InjectIntelRequest,
    token: str = Depends(get_chairman_token),
):
    await validate_chairman_token(session_id, token)
    db = _get_db()
    now = datetime.now(timezone.utc).isoformat()
    intel_id = str(uuid.uuid4())

    intel_item = {
        "intel_id": intel_id,
        "text": body.text,
        "source": body.source,
        "source_type": body.source_type,
        "received_at": now,
        "is_escalation": False,
        "pinned": False,
    }

    doc_ref = db.collection(COLLECTION_CRISIS_SESSIONS).document(session_id)
    doc = await doc_ref.get()
    data = doc.to_dict() if doc.exists else {}
    intel_list = data.get("critical_intel", [])
    intel_list.append(intel_item)

    roster = data.get("agent_roster", [])
    broadcast_count = len(roster) if body.broadcast else 0

    await doc_ref.update({"critical_intel": intel_list, "updated_at": now})
    await push_event(session_id, "intel_dropped", intel_item)

    # Broadcast to agents if requested
    if body.broadcast:
        from gateway.chairman_handler import get_agents
        agents = get_agents(session_id)
        for key, agent in agents.items():
            if agent.live_session:
                try:
                    await agent.send_text(
                        f"[BREAKING INTEL from Chairman]: {body.text}"
                    )
                except Exception as e:
                    logger.warning(f"Failed to broadcast intel to {key}: {e}")

    return {
        "intel_id": intel_id,
        "text": body.text,
        "broadcast_to_agents": broadcast_count,
        "received_at": now,
    }


# ── GET /board/timeline — board at past timestamp ───────────────────────

@router.get("/{session_id}/board/timeline")
async def get_timeline(
    session_id: str,
    at: str = Query(..., description="ISO timestamp to query"),
    token: str = Depends(get_chairman_token),
):
    session_data = await validate_chairman_token(session_id, token)

    # Filter all board items to before the given timestamp
    decisions = [
        d for d in session_data.get("agreed_decisions", [])
        if d.get("agreed_at", "") <= at
    ]
    conflicts = [
        c for c in session_data.get("open_conflicts", [])
        if c.get("opened_at", "") <= at
    ]
    intel = [
        i for i in session_data.get("critical_intel", [])
        if i.get("received_at", "") <= at
    ]

    return {
        "at": at,
        "agreed_decisions": decisions,
        "open_conflicts": conflicts,
        "critical_intel": intel,
        "resolution_score_at_time": session_data.get("resolution_score", 50),
        "threat_level_at_time": session_data.get("threat_level", "elevated"),
    }
