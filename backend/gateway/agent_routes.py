"""
WAR ROOM — Agent Routes (API spec §3)
REST endpoints for the Left Panel Agent Roster.
GET    /api/sessions/{sid}/agents             — list all agents
GET    /api/sessions/{sid}/agents/{aid}       — single agent detail
PATCH  /api/sessions/{sid}/agents/{aid}       — dismiss / silence / address
POST   /api/sessions/{sid}/agents/summon      — summon new agent mid-session
GET    /api/sessions/{sid}/agents/{aid}/transcript — agent statement history
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
from config.constants import (
    COLLECTION_CRISIS_SESSIONS,
    COLLECTION_SESSION_EVENTS,
    SUBCOLLECTION_EVENTS,
    EVENT_AGENT_ASSEMBLING,
    EVENT_AGENT_STATUS_CHANGE,
)
from config.settings import get_settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/sessions", tags=["Agents"])


# ── REQUEST / RESPONSE MODELS ──────────────────────────────────────────


class AgentActionRequest(BaseModel):
    """Body for PATCH /agents/{agent_id}."""
    action: str = Field(
        ..., description="dismiss | silence | address",
    )
    duration_seconds: Optional[int] = Field(
        default=None, description="For silence action only",
    )


class SummonAgentRequest(BaseModel):
    """Body for POST /agents/summon."""
    role_description: str = Field(
        ..., min_length=3, max_length=500,
        description="Chairman describes the role to generate",
    )


# ── HELPERS ─────────────────────────────────────────────────────────────


def _silence_duration(agent_roster: list, agent_id: str) -> int:
    """Compute silence duration in seconds from last_spoke_at."""
    for a in agent_roster:
        if a.get("agent_id") == agent_id:
            last = a.get("last_spoke_at")
            if last:
                try:
                    spoke = datetime.fromisoformat(
                        last.replace("Z", "+00:00")
                    )
                    return int(
                        (datetime.now(timezone.utc) - spoke).total_seconds()
                    )
                except Exception:
                    pass
    return 0


def _extract_conflict_agents(conflict_item: object) -> list[str]:
    """
    Backward-compatible parser for open_conflicts entries.
    Some legacy rows may be plain strings instead of dict objects.
    """
    if isinstance(conflict_item, dict):
        involved = conflict_item.get("agents_involved", [])
        if isinstance(involved, list):
            return [str(a) for a in involved if isinstance(a, (str, int))]
    return []


# ── GET /api/sessions/{sid}/agents ──────────────────────────────────────


@router.get("/{session_id}/agents")
async def list_agents(
    session_id: str,
    status_filter: Optional[str] = Query(
        default=None, description="Filter by agent status"
    ),
    token: str = Depends(get_chairman_token),
):
    """
    Get all agents with their current public state.
    Used on initial load and reconnect.
    MEMORY ISOLATION: never reads agent_memory. last_statement from events only.
    """
    session_data = await validate_chairman_token(session_id, token)
    roster = session_data.get("agent_roster", [])

    agents = []
    active_count = 0
    silent_count = 0
    conflict_count = 0

    for entry in roster:
        status = entry.get("status", "idle")

        if status_filter and status != status_filter:
            continue

        if status in ("speaking", "thinking", "listening"):
            active_count += 1
        if status == "silent":
            silent_count += 1
        if status == "conflicted":
            conflict_count += 1

        # Build conflict_with list from open_conflicts
        conflicts = session_data.get("open_conflicts", [])
        agent_id = entry.get("agent_id", "")
        conflict_with = []
        for c in conflicts:
            involved = _extract_conflict_agents(c)
            if agent_id in involved:
                conflict_with.extend(
                    [a for a in involved if a != agent_id]
                )

        agents.append({
            "agent_id": agent_id,
            "character_name": entry.get("character_name", ""),
            "role_title": entry.get("role_title", ""),
            "identity_color": entry.get("identity_color", "#666"),
            "voice_name": entry.get("voice_name", ""),
            "livekit_room": entry.get("livekit_room"),
            "livekit_identity": entry.get("livekit_identity"),
            "status": status,
            "trust_score": entry.get("trust_score", 70),
            "last_spoke_at": entry.get("last_spoke_at"),
            "last_statement": entry.get("last_statement", ""),
            "conflict_with": conflict_with,
            "silence_duration_seconds": _silence_duration(roster, agent_id),
        })

    return {
        "session_id": session_id,
        "agents": agents,
        "active_count": active_count,
        "silent_count": silent_count,
        "conflict_count": conflict_count,
    }


# ── GET /api/sessions/{sid}/agents/{agent_id} ──────────────────────────


@router.get("/{session_id}/agents/{agent_id}")
async def get_agent(
    session_id: str,
    agent_id: str,
    token: str = Depends(get_chairman_token),
):
    """
    Get one agent's full public state.
    MEMORY ISOLATION: public_positions extracted from transcripts only.
    NEVER reads agent_memory Firestore collection.
    """
    session_data = await validate_chairman_token(session_id, token)
    roster = session_data.get("agent_roster", [])

    agent_entry = None
    for entry in roster:
        if entry.get("agent_id") == agent_id:
            agent_entry = entry
            break

    if not agent_entry:
        raise HTTPException(status_code=404, detail="Agent not found")

    # Build conflict_with from open_conflicts
    conflicts = session_data.get("open_conflicts", [])
    conflict_with = []
    for c in conflicts:
        involved = _extract_conflict_agents(c)
        if agent_id in involved:
            conflict_with.extend([a for a in involved if a != agent_id])

    # Count statements from session_events
    db = _get_db()
    statement_count = 0
    try:
        events_ref = db.collection(COLLECTION_SESSION_EVENTS) \
                       .document(session_id) \
                       .collection(SUBCOLLECTION_EVENTS)
        all_events = await events_ref.get()
        for ev in all_events:
            ev_data = ev.to_dict() if hasattr(ev, 'to_dict') else ev
            if (ev_data.get("event_type") == "agent_speaking_end"
                    and ev_data.get("payload", {}).get("agent_id") == agent_id):
                statement_count += 1
    except Exception:
        pass

    return {
        "agent_id": agent_id,
        "character_name": agent_entry.get("character_name", ""),
        "role_title": agent_entry.get("role_title", ""),
        "identity_color": agent_entry.get("identity_color", "#666"),
        "voice_name": agent_entry.get("voice_name", ""),
        "livekit_room": agent_entry.get("livekit_room"),
        "livekit_identity": agent_entry.get("livekit_identity"),
        "status": agent_entry.get("status", "idle"),
        "trust_score": agent_entry.get("trust_score", 70),
        "last_spoke_at": agent_entry.get("last_spoke_at"),
        "silence_duration_seconds": _silence_duration(roster, agent_id),
        "conflict_with": conflict_with,
        "public_positions": {},  # Extracted from transcripts by Observer
        "statement_count": statement_count,
        "contradiction_count": 0,
        "defining_line": agent_entry.get("defining_line", ""),
        "agenda": agent_entry.get("agenda", ""),
    }


# ── PATCH /api/sessions/{sid}/agents/{agent_id} ────────────────────────


@router.patch("/{session_id}/agents/{agent_id}")
async def patch_agent(
    session_id: str,
    agent_id: str,
    body: AgentActionRequest,
    token: str = Depends(get_chairman_token),
):
    """
    Chairman actions on a specific agent: dismiss, silence, or address.
    """
    session_data = await validate_chairman_token(session_id, token)
    roster = session_data.get("agent_roster", [])

    agent_entry = None
    for entry in roster:
        if entry.get("agent_id") == agent_id:
            agent_entry = entry
            break

    if not agent_entry:
        raise HTTPException(status_code=404, detail="Agent not found")

    db = _get_db()
    now = datetime.now(timezone.utc).isoformat()
    character_name = agent_entry.get("character_name", "Agent")
    remaining = len([a for a in roster if a.get("status") != "dismissed"])

    if body.action == "dismiss":
        # Close the agent's live session
        from gateway.chairman_handler import get_agents
        agents = get_agents(session_id)

        # Find by role_key (agent_id minus session suffix)
        role_key = agent_id.rsplit("_", 1)[0] if "_" in agent_id else agent_id
        agent_instance = agents.get(role_key)
        if agent_instance:
            await agent_instance.close()
            del agents[role_key]

        # Update roster status
        for entry in roster:
            if entry.get("agent_id") == agent_id:
                entry["status"] = "dismissed"
                break
        await db.collection(COLLECTION_CRISIS_SESSIONS) \
                .document(session_id).update({"agent_roster": roster})

        await push_event(session_id, EVENT_AGENT_STATUS_CHANGE, {
            "agent_id": agent_id,
            "status": "dismissed",
            "previous_status": agent_entry.get("status", "idle"),
        })

        return {
            "agent_id": agent_id,
            "action_applied": "dismiss",
            "applied_at": now,
            "effect": (
                f"Agent {character_name} has left the room. "
                f"{remaining - 1} agents remain."
            ),
        }

    elif body.action == "silence":
        duration = body.duration_seconds or 60
        for entry in roster:
            if entry.get("agent_id") == agent_id:
                entry["status"] = "silent"
                break
        await db.collection(COLLECTION_CRISIS_SESSIONS) \
                .document(session_id).update({"agent_roster": roster})

        await push_event(session_id, EVENT_AGENT_STATUS_CHANGE, {
            "agent_id": agent_id,
            "status": "silent",
            "previous_status": agent_entry.get("status", "idle"),
        })

        # Schedule restoration to idle after duration
        async def _restore_idle():
            await asyncio.sleep(duration)
            try:
                doc = await db.collection(COLLECTION_CRISIS_SESSIONS) \
                              .document(session_id).get()
                if doc.exists:
                    r = doc.to_dict().get("agent_roster", [])
                    for e in r:
                        if e.get("agent_id") == agent_id and e.get("status") == "silent":
                            e["status"] = "idle"
                            await db.collection(COLLECTION_CRISIS_SESSIONS) \
                                    .document(session_id).update({"agent_roster": r})
                            await push_event(session_id, EVENT_AGENT_STATUS_CHANGE, {
                                "agent_id": agent_id,
                                "status": "idle",
                                "previous_status": "silent",
                            })
                            break
            except Exception as e:
                logger.warning(f"Failed to restore agent {agent_id} from silence: {e}")

        asyncio.create_task(_restore_idle())

        return {
            "agent_id": agent_id,
            "action_applied": "silence",
            "applied_at": now,
            "effect": (
                f"Agent {character_name} silenced for {duration} seconds."
            ),
        }

    elif body.action == "address":
        # Mark agent as addressed — switch to listening
        for entry in roster:
            if entry.get("agent_id") == agent_id:
                entry["status"] = "listening"
                break
        await db.collection(COLLECTION_CRISIS_SESSIONS) \
                .document(session_id).update({"agent_roster": roster})

        # Backend-owned handoff: make this the active voice responder.
        try:
            from gateway.chairman_handler import select_voice_agent
            select_voice_agent(session_id, agent_id)
        except Exception as e:
            logger.warning(f"Failed to set active voice agent {agent_id}: {e}")

        await push_event(session_id, EVENT_AGENT_STATUS_CHANGE, {
            "agent_id": agent_id,
            "status": "listening",
            "previous_status": agent_entry.get("status", "idle"),
        })

        return {
            "agent_id": agent_id,
            "action_applied": "address",
            "applied_at": now,
            "effect": f"Agent {character_name} is now listening.",
        }

    else:
        raise HTTPException(
            status_code=422,
            detail=f"Unknown action: {body.action}. Use dismiss|silence|address",
        )


# ── POST /api/sessions/{sid}/agents/summon ──────────────────────────────


@router.post("/{session_id}/agents/summon", status_code=202)
async def summon_agent_endpoint(
    session_id: str,
    body: SummonAgentRequest,
    token: str = Depends(get_chairman_token),
):
    """
    Chairman requests a new agent mid-session.
    Runs ScenarioAnalyst mini-call, generates SKILL.md, initializes agent.
    Returns 202 immediately; agent creation runs in background.
    """
    await validate_chairman_token(session_id, token)
    # MULTI-AGENT: commented out single-agent summon guard
    # settings = get_settings()
    # if settings.single_agent_voice_mode:
    #     raise HTTPException(
    #         status_code=409,
    #         detail="Summon disabled while single_agent_voice_mode=true",
    #     )

    request_id = str(uuid.uuid4())

    async def _do_summon():
        from agents.dynamic_agent_factory import summon_agent
        from gateway.chairman_handler import get_agents, register_agents, _active_agents

        try:
            # Generate a role_key from the description
            words = body.role_description.lower().split()
            role_key = "_".join(words[:2]) if len(words) >= 2 else words[0]
            role_key = "".join(c for c in role_key if c.isalnum() or c == "_")

            agents = get_agents(session_id)
            agent = await summon_agent(
                session_id=session_id,
                role_key=role_key,
                role_title=body.role_description,
                character_name=body.role_description.split()[0].upper(),
                agenda=f"Provide expert analysis on: {body.role_description}",
                active_agents=agents,
            )

            # Register the new agent
            if session_id in _active_agents:
                _active_agents[session_id][role_key] = agent
            else:
                _active_agents[session_id] = {role_key: agent}

            # Update roster in Firestore
            db = _get_db()
            doc = await db.collection(COLLECTION_CRISIS_SESSIONS) \
                          .document(session_id).get()
            if doc.exists:
                data = doc.to_dict()
                roster = data.get("agent_roster", [])
                roster.append({
                    "agent_id": agent.agent_id,
                    "role_key": role_key,
                    "role_title": body.role_description,
                    "character_name": agent.role_config.get("character_name", ""),
                    "voice_name": agent.assigned_voice,
                    "identity_color": agent.role_config.get("identity_color", "#888"),
                    "defining_line": agent.role_config.get("defining_line", ""),
                    "agenda": agent.role_config.get("agenda", ""),
                    "status": "idle",
                    "trust_score": 70,
                    "last_spoke_at": None,
                })
                await db.collection(COLLECTION_CRISIS_SESSIONS) \
                        .document(session_id).update({"agent_roster": roster})

            # Push ready event
            await push_event(session_id, "agent_ready", {
                "agent_id": agent.agent_id,
                "character_name": agent.role_config.get("character_name", ""),
                "role_title": body.role_description,
                "voice_name": agent.assigned_voice,
            })

            logger.info(f"Summoned agent {agent.agent_id} for session {session_id}")

        except Exception as e:
            logger.error(f"Failed to summon agent: {e}")

    asyncio.create_task(_do_summon())

    return {
        "request_id": request_id,
        "status": "generating",
        "message": "Generating new agent from role description...",
        "estimated_seconds": 8,
    }


# ── GET /api/sessions/{sid}/agents/{agent_id}/transcript ────────────────


@router.get("/{session_id}/agents/{agent_id}/transcript")
async def get_agent_transcript(
    session_id: str,
    agent_id: str,
    limit: int = Query(default=20, ge=1, le=100),
    before: Optional[str] = Query(default=None),
    token: str = Depends(get_chairman_token),
):
    """
    Get full statement history for one agent from session_events.
    MEMORY ISOLATION: reads ONLY from session_events (public transcript).
    Does NOT touch agent_memory collection.
    """
    await validate_chairman_token(session_id, token)

    db = _get_db()
    statements = []
    total_words = 0

    # Find character_name from roster
    doc = await db.collection(COLLECTION_CRISIS_SESSIONS) \
                  .document(session_id).get()
    character_name = ""
    if doc.exists:
        roster = doc.to_dict().get("agent_roster", [])
        for a in roster:
            if a.get("agent_id") == agent_id:
                character_name = a.get("character_name", "")
                break

    try:
        events_ref = db.collection(COLLECTION_SESSION_EVENTS) \
                       .document(session_id) \
                       .collection(SUBCOLLECTION_EVENTS)
        all_events = await events_ref.get()

        for ev in all_events:
            ev_data = ev.to_dict() if hasattr(ev, 'to_dict') else ev
            if ev_data.get("event_type") != "agent_speaking_end":
                continue
            payload = ev_data.get("payload", {})
            if payload.get("agent_id") != agent_id:
                continue

            text = payload.get("full_transcript", "")
            spoken_at = ev_data.get("timestamp", "")

            if before and spoken_at >= before:
                continue

            total_words += len(text.split())
            statements.append({
                "statement_id": ev_data.get("event_id", str(uuid.uuid4())),
                "text": text,
                "spoken_at": spoken_at,
                "duration_seconds": 0,
                "was_interrupted": False,
                "interrupted_by": None,
                "triggered_conflict": None,
                "triggered_decision": None,
            })

        # Sort by timestamp descending, apply limit
        statements.sort(key=lambda s: s["spoken_at"], reverse=True)
        statements = statements[:limit]

    except Exception as e:
        logger.warning(f"Failed to fetch transcript for {agent_id}: {e}")

    return {
        "agent_id": agent_id,
        "character_name": character_name,
        "statements": statements,
        "total_statements": len(statements),
        "total_words": total_words,
    }
