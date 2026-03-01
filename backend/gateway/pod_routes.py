"""
WAR ROOM — Pod Routes (API spec §6)
REST endpoints for the Bottom Center Agent Voice Pods.
GET  /api/sessions/{sid}/pods            — all pod states
GET  /api/sessions/{sid}/pods/{aid}      — single pod detail
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from utils.auth import get_chairman_token, validate_chairman_token
from utils.firestore_helpers import _get_db
from config.constants import (
    COLLECTION_CRISIS_SESSIONS,
    COLLECTION_SESSION_EVENTS,
    SUBCOLLECTION_EVENTS,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/sessions", tags=["Agent Voice Pods"])


# ── GET /api/sessions/{sid}/pods ────────────────────────────────────────


@router.get("/{session_id}/pods")
async def list_pods(
    session_id: str,
    filter: str = Query(
        default="all", description="all | active | conflicted"
    ),
    token: str = Depends(get_chairman_token),
):
    """
    Get current speaking/thinking/status state of all agent pods.
    Used for initial render and reconnect.
    """
    session_data = await validate_chairman_token(session_id, token)
    roster = session_data.get("agent_roster", [])
    conflicts = session_data.get("open_conflicts", [])

    pods = []
    active_count = 0
    conflicted_count = 0
    thinking_count = 0
    silent_count = 0

    for entry in roster:
        status = entry.get("status", "idle")
        agent_id = entry.get("agent_id", "")

        # Skip dismissed agents
        if status == "dismissed":
            continue

        # Find conflict partner name
        conflict_with_name = None
        for c in conflicts:
            involved = c.get("agents_involved", [])
            if agent_id in involved:
                for partner_id in involved:
                    if partner_id != agent_id:
                        # Look up character name
                        for r in roster:
                            if r.get("agent_id") == partner_id:
                                conflict_with_name = r.get(
                                    "character_name", ""
                                )
                                break
                break

        # Count by status
        if status in ("speaking", "listening"):
            active_count += 1
        if status == "conflicted":
            conflicted_count += 1
        if status == "thinking":
            thinking_count += 1
        if status == "silent":
            silent_count += 1

        # Apply filter
        if filter == "active" and status not in (
            "speaking", "thinking", "listening"
        ):
            continue
        if filter == "conflicted" and status != "conflicted":
            continue

        # Build the last transcript snippet
        last_statement = entry.get("last_statement", "")
        snippet = last_statement[:40] + "..." if len(last_statement) > 40 else last_statement

        pods.append({
            "agent_id": agent_id,
            "character_name": entry.get("character_name", ""),
            "role_title": entry.get("role_title", ""),
            "identity_color": entry.get("identity_color", "#666"),
            "status": status,
            "transcript_snippet": snippet,
            "conflict_with_name": conflict_with_name,
            "waveform_active": status == "speaking",
            "last_audio_at": entry.get("last_spoke_at"),
        })

    return {
        "session_id": session_id,
        "filter_applied": filter,
        "pods": pods,
        "active_count": active_count,
        "conflicted_count": conflicted_count,
        "thinking_count": thinking_count,
        "silent_count": silent_count,
    }


# ── GET /api/sessions/{sid}/pods/{agent_id} ────────────────────────────


@router.get("/{session_id}/pods/{agent_id}")
async def get_pod(
    session_id: str,
    agent_id: str,
    token: str = Depends(get_chairman_token),
):
    """
    Get full pod state + last N transcript lines for one agent.
    Used when a specific pod is clicked for detail view.
    """
    session_data = await validate_chairman_token(session_id, token)
    roster = session_data.get("agent_roster", [])

    agent_entry = None
    for entry in roster:
        if entry.get("agent_id") == agent_id:
            agent_entry = entry
            break

    if not agent_entry:
        raise HTTPException(status_code=404, detail="Agent pod not found")

    # Build conflict_with list with names
    conflicts = session_data.get("open_conflicts", [])
    conflict_with = []
    for c in conflicts:
        involved = c.get("agents_involved", [])
        if agent_id in involved:
            for partner_id in involved:
                if partner_id != agent_id:
                    name = ""
                    for r in roster:
                        if r.get("agent_id") == partner_id:
                            name = r.get("character_name", "")
                            break
                    conflict_with.append({
                        "agent_id": partner_id,
                        "name": name,
                    })

    # Get recent transcript from session_events (last 3 statements)
    db = _get_db()
    recent_transcript = []
    interrupted_count = 0
    interruption_count = 0
    statements_today = 0

    try:
        events_ref = db.collection(COLLECTION_SESSION_EVENTS) \
                       .document(session_id) \
                       .collection(SUBCOLLECTION_EVENTS)
        all_events = await events_ref.get()

        speaking_events = []
        for ev in all_events:
            ev_data = ev.to_dict() if hasattr(ev, 'to_dict') else ev
            payload = ev_data.get("payload", {})

            if (ev_data.get("event_type") == "agent_speaking_end"
                    and payload.get("agent_id") == agent_id):
                text = payload.get("full_transcript", "")
                speaking_events.append({
                    "text": text,
                    "timestamp": ev_data.get("timestamp", ""),
                })
                statements_today += 1

            # Count interruptions involving this agent
            if ev_data.get("event_type") == "agent_interrupted":
                if payload.get("agent_id") == agent_id:
                    interrupted_count += 1
                if payload.get("interrupted_by") == agent_id:
                    interruption_count += 1

        # Sort by timestamp and take last 3
        speaking_events.sort(key=lambda s: s["timestamp"], reverse=True)
        recent_transcript = [e["text"] for e in speaking_events[:3]]

    except Exception as e:
        logger.warning(f"Failed to fetch pod transcript for {agent_id}: {e}")

    status = agent_entry.get("status", "idle")

    return {
        "agent_id": agent_id,
        "character_name": agent_entry.get("character_name", ""),
        "role_title": agent_entry.get("role_title", ""),
        "identity_color": agent_entry.get("identity_color", "#666"),
        "voice_name": agent_entry.get("voice_name", ""),
        "status": status,
        "conflict_with": conflict_with,
        "recent_transcript": recent_transcript,
        "waveform_active": status == "speaking",
        "trust_score": agent_entry.get("trust_score", 70),
        "statements_today": statements_today,
        "interrupted_count": interrupted_count,
        "interruption_count": interruption_count,
    }
