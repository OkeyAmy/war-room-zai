"""
WAR ROOM — Voice Routes
API Section 12: Voice management endpoints.
  POST /voice/token     — ephemeral token for chairman audio WS
  GET  /voice/status    — voice session health for all agents
  PATCH /voice/chairman — mute/unmute chairman mic

API Section 11: Chairman command endpoint.
  POST /chairman/command — send text directive to agent(s)
"""

from __future__ import annotations

import uuid
import logging
from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field
from typing import Optional

from config.constants import (
    COLLECTION_CRISIS_SESSIONS,
)
from config.settings import get_settings
from gateway.chairman_handler import (
    get_agents,
    get_active_voice_agent_id,
    set_agent_voice_connected,
    select_voice_agent,
)
from utils.livekit_api import (
    build_livekit_participant_token,
    ensure_livekit_room,
    is_livekit_configured,
    ping_livekit,
)

logger = logging.getLogger(__name__)

router = APIRouter()


# ── Request / Response Models ────────────────────────────────────────────


class VoiceTokenResponse(BaseModel):
    token: str
    expires_at: str
    ws_audio_url: str
    transport: str = "websocket"  # websocket | livekit
    sample_rate: int = 16000
    channels: int = 1
    format: str = "pcm_16bit"
    livekit_room: Optional[str] = None
    livekit_identity: Optional[str] = None


class AgentVoiceStatus(BaseModel):
    agent_id: str
    voice_active: bool
    voice_name: str
    latency_ms: int = 0
    health: str = "good"


class VoiceStatusResponse(BaseModel):
    chairman_mic: str  # "active" | "muted" | "inactive"
    agent_sessions: list[AgentVoiceStatus]
    all_healthy: bool
    active_agent_id: Optional[str] = None


class ChairmanMicRequest(BaseModel):
    muted: bool


class ChairmanMicResponse(BaseModel):
    chairman_mic: str
    applied_at: str


class ChairmanCommandRequest(BaseModel):
    text: str
    target_agent_id: Optional[str] = None
    command_type: str = "question"  # question | directive | vote_call | inject_intel


class ChairmanCommandResponse(BaseModel):
    command_id: str
    text: str
    target_agent_id: Optional[str] = None
    routed_to: list[str]
    issued_at: str


class ActiveVoiceAgentRequest(BaseModel):
    agent_id: Optional[str] = None


class ActiveVoiceAgentResponse(BaseModel):
    active_agent_id: Optional[str] = None
    updated_at: str


class VoiceAgentTarget(BaseModel):
    agent_id: str
    character_name: str
    role_title: str
    status: str
    pod_id: Optional[str] = None
    pod_connected: bool = False
    livekit_room: Optional[str] = None
    livekit_identity: Optional[str] = None
    is_active: bool = False


class VoiceAgentTargetsResponse(BaseModel):
    session_id: str
    active_agent_id: Optional[str] = None
    agents: list[VoiceAgentTarget]
    updated_at: str


class LiveKitPingResponse(BaseModel):
    ok: bool
    message: str


class VoicePodState(BaseModel):
    pod_id: str
    agent_id: Optional[str] = None
    connected: bool
    livekit_room: Optional[str] = None
    livekit_identity: Optional[str] = None


class VoicePodsResponse(BaseModel):
    session_id: str
    pods: list[VoicePodState]
    updated_at: str


class VoicePodPatchRequest(BaseModel):
    connected: bool


class AgentPodTokenResponse(BaseModel):
    agent_id: str
    token: str
    expires_at: str
    ws_audio_url: str
    livekit_room: str
    livekit_identity: str
    transport: str = "livekit"
    sample_rate: int = 48000
    channels: int = 1
    format: str = "webrtc_opus"


class AgentSessionConfigResponse(BaseModel):
    session_id: str
    agent_id: str
    livekit_agent_session: dict
    updated_at: str


# ── Helpers ──────────────────────────────────────────────────────────────

# Track chairman mic state per session
_chairman_mic: dict[str, str] = {}  # session_id -> "active" | "muted"


async def _extract_session_and_token(
    session_id: str,
    authorization: str,
):
    """Extract and validate the chairman token from the Authorization header."""
    from utils.firestore_helpers import _get_db

    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid Authorization header")
    token = authorization[7:]
    db = _get_db()
    # Validate token against session.
    doc = await db.collection(COLLECTION_CRISIS_SESSIONS).document(session_id).get()
    if not doc.exists:
        raise HTTPException(status_code=404, detail="Session not found")
    if doc.to_dict().get("chairman_token") != token:
        raise HTTPException(status_code=403, detail="Invalid chairman token")
    return session_id, token


# ── Voice Endpoints ─────────────────────────────────────────────────────


@router.post(
    "/api/sessions/{session_id}/voice/token",
    response_model=VoiceTokenResponse,
)
async def get_voice_token(
    session_id: str,
    authorization: str = Header(None),
):
    """
    Get an ephemeral token for the Chairman's audio WebSocket.
    The token lets the chairman stream mic audio to agents.
    """
    sid, token = await _extract_session_and_token(session_id, authorization)

    # Validate session exists
    from utils.firestore_helpers import _get_db
    db = _get_db()
    doc = await db.collection(COLLECTION_CRISIS_SESSIONS).document(sid).get()
    if not doc.exists:
        raise HTTPException(status_code=404, detail="Session not found")

    session_data = doc.to_dict()
    if session_data.get("chairman_token") != token:
        raise HTTPException(status_code=403, detail="Invalid chairman token")

    expires_at = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()

    # Preferred transport: LiveKit (backend-managed).
    if is_livekit_configured():
        settings = get_settings()
        room_name = f"war-room-{sid.lower()}"
        identity = f"chairman-{sid.lower()}"
        ensure_livekit_room(
            room_name=room_name,
            metadata={"session_id": sid, "chairman_name": session_data.get("chairman_name", "DIRECTOR")},
        )
        lk_token = build_livekit_participant_token(
            room_name=room_name,
            identity=identity,
            name=session_data.get("chairman_name", "DIRECTOR"),
            metadata={"session_id": sid, "role": "chairman"},
            ttl_seconds=3600,
        )
        await db.collection(COLLECTION_CRISIS_SESSIONS).document(sid).update({
            "livekit_room": room_name,
            "livekit_identity": identity,
            "voice_transport": "livekit",
        })
        return VoiceTokenResponse(
            token=lk_token,
            expires_at=expires_at,
            ws_audio_url=settings.livekit_url,
            transport="livekit",
            sample_rate=48000,
            channels=1,
            format="webrtc_opus",
            livekit_room=room_name,
            livekit_identity=identity,
        )

    # Fallback transport: existing chairman audio websocket.
    audio_token = str(uuid.uuid4())
    await db.collection(COLLECTION_CRISIS_SESSIONS).document(sid).update({
        "audio_token": audio_token,
        "audio_token_expires": expires_at,
        "voice_transport": "websocket",
    })
    ws_url = f"ws://localhost:8000/ws/{session_id}/audio"
    return VoiceTokenResponse(
        token=audio_token,
        expires_at=expires_at,
        ws_audio_url=ws_url,
        transport="websocket",
        sample_rate=16000,
        channels=1,
        format="pcm_16bit",
    )


@router.get(
    "/api/sessions/{session_id}/voice/status",
    response_model=VoiceStatusResponse,
)
async def get_voice_status(
    session_id: str,
    authorization: str = Header(None),
):
    """
    Check voice session health for all agents.
    Returns whether each agent's Gemini Live session is active.
    """
    sid, token = await _extract_session_and_token(session_id, authorization)

    # Get registered agents
    agents = get_agents(sid)
    agent_statuses = []

    for role_key, agent in agents.items():
        agent_statuses.append(AgentVoiceStatus(
            agent_id=agent.agent_id,
            voice_active=agent.live_session is not None,
            voice_name=agent.assigned_voice,
            latency_ms=0,
            health="good" if agent.live_session else "unavailable",
        ))

    # If no registered agents, check Firestore roster
    if not agent_statuses:
        from utils.firestore_helpers import _get_db
        db = _get_db()
        doc = await db.collection(COLLECTION_CRISIS_SESSIONS).document(sid).get()
        if doc.exists:
            roster = doc.to_dict().get("agent_roster", [])
            for entry in roster:
                agent_statuses.append(AgentVoiceStatus(
                    agent_id=entry.get("agent_id", ""),
                    voice_active=False,
                    voice_name=entry.get("voice_name", "Unknown"),
                    latency_ms=0,
                    health="not_initialized",
                ))

    mic_state = _chairman_mic.get(sid, "muted")
    all_healthy = all(s.health == "good" for s in agent_statuses) if agent_statuses else False

    return VoiceStatusResponse(
        chairman_mic=mic_state,
        agent_sessions=agent_statuses,
        all_healthy=all_healthy,
        active_agent_id=get_active_voice_agent_id(sid),
    )


@router.patch(
    "/api/sessions/{session_id}/voice/chairman",
    response_model=ChairmanMicResponse,
)
async def patch_chairman_mic(
    session_id: str,
    body: ChairmanMicRequest,
    authorization: str = Header(None),
):
    """Mute/unmute chairman mic."""
    sid, token = await _extract_session_and_token(session_id, authorization)

    from utils.events import push_event

    new_state = "muted" if body.muted else "active"
    _chairman_mic[sid] = new_state

    await push_event(sid, "chairman_mic_status", {
        "chairman_mic": new_state,
    })

    return ChairmanMicResponse(
        chairman_mic=new_state,
        applied_at=datetime.now(timezone.utc).isoformat(),
    )


# ── Chairman Command Endpoint ───────────────────────────────────────────


@router.post(
    "/api/sessions/{session_id}/chairman/command",
    response_model=ChairmanCommandResponse,
)
async def post_chairman_command(
    session_id: str,
    body: ChairmanCommandRequest,
    authorization: str = Header(None),
):
    """
    Chairman sends a text directive to the room or a specific agent.
    The text is injected into the target agent's Gemini Live session
    so they respond to it with voice.
    """
    from utils.events import push_event
    from utils.turn_manager import get_turn_manager

    sid, token = await _extract_session_and_token(session_id, authorization)
    agents = get_agents(sid)

    if not agents:
        raise HTTPException(status_code=404, detail="No agents active in this session")

    command_id = str(uuid.uuid4())
    routed_to = []

    # Push chairman_spoke event
    tm = get_turn_manager(sid)
    if not tm.is_floor_free():
        await tm.chairman_interrupt()

    await push_event(sid, "chairman_taking_floor", {
        "target_agent_id": body.target_agent_id,
    })

    await push_event(sid, "chairman_spoke", {
        "text": body.text,
        "target_agent_id": body.target_agent_id,
        "command_type": body.command_type,
    })

    agent = select_voice_agent(sid, body.target_agent_id)
    if not agent:
        raise HTTPException(
            status_code=404,
            detail="No live voice agent available for this session",
        )

    if body.target_agent_id:
        await agent.send_text(
            f"The Chairman says to you: \"{body.text}\"\n\n"
            f"Respond directly and concisely."
        )
    else:
        await agent.send_text(
            f"The Chairman addresses the room: \"{body.text}\"\n\n"
            f"As the active responder, give your assessment."
        )
    routed_to.append(agent.agent_id)

    return ChairmanCommandResponse(
        command_id=command_id,
        text=body.text,
        target_agent_id=body.target_agent_id,
        routed_to=routed_to,
        issued_at=datetime.now(timezone.utc).isoformat(),
    )


@router.patch(
    "/api/sessions/{session_id}/voice/active-agent",
    response_model=ActiveVoiceAgentResponse,
)
async def patch_active_voice_agent(
    session_id: str,
    body: ActiveVoiceAgentRequest,
    authorization: str = Header(None),
):
    """
    Set or clear the active voice target agent for the session.
    Frontend calls this when chairman explicitly addresses an agent.
    """
    sid, _token = await _extract_session_and_token(session_id, authorization)

    if body.agent_id:
        agent = select_voice_agent(sid, body.agent_id)
        if not agent:
            raise HTTPException(status_code=404, detail="Target agent not found")
    active = get_active_voice_agent_id(sid)
    return ActiveVoiceAgentResponse(
        active_agent_id=active,
        updated_at=datetime.now(timezone.utc).isoformat(),
    )


@router.get(
    "/api/sessions/{session_id}/voice/agents",
    response_model=VoiceAgentTargetsResponse,
)
async def get_voice_agents(
    session_id: str,
    authorization: str = Header(None),
):
    """
    List agents available for voice routing/directing.
    """
    sid, _token = await _extract_session_and_token(session_id, authorization)
    from utils.firestore_helpers import _get_db

    db = _get_db()
    doc = await db.collection(COLLECTION_CRISIS_SESSIONS).document(sid).get()
    if not doc.exists:
        raise HTTPException(status_code=404, detail="Session not found")
    data = doc.to_dict() or {}
    roster = data.get("agent_roster", [])
    active = get_active_voice_agent_id(sid)
    agents = []
    for r in roster:
        agents.append(
            VoiceAgentTarget(
                agent_id=r.get("agent_id", ""),
                character_name=r.get("character_name", ""),
                role_title=r.get("role_title", ""),
                status=r.get("status", "idle"),
                pod_id=r.get("pod_id"),
                pod_connected=bool(r.get("pod_connected", False)),
                livekit_room=r.get("livekit_room"),
                livekit_identity=r.get("livekit_identity"),
                is_active=r.get("agent_id") == active,
            )
        )
    return VoiceAgentTargetsResponse(
        session_id=sid,
        active_agent_id=active,
        agents=agents,
        updated_at=datetime.now(timezone.utc).isoformat(),
    )


@router.get(
    "/api/sessions/{session_id}/voice/agent-session",
    response_model=AgentSessionConfigResponse,
)
async def get_livekit_agent_session_config(
    session_id: str,
    agent_id: Optional[str] = None,
    authorization: str = Header(None),
):
    """
    Return the generated LiveKit AgentSession parameters for the active voice agent.
    Useful for frontend/worker runtime parity and debugging.
    """
    sid, _token = await _extract_session_and_token(session_id, authorization)
    selected_agent = select_voice_agent(sid, agent_id)

    if not selected_agent:
        raise HTTPException(status_code=404, detail="No live voice agent available")

    config = getattr(selected_agent, "livekit_session_config", None) or {}
    if not config:
        from utils.firestore_helpers import _get_db

        db = _get_db()
        doc = await db.collection(COLLECTION_CRISIS_SESSIONS).document(sid).get()
        if doc.exists:
            roster = (doc.to_dict() or {}).get("agent_roster", [])
            entry = next(
                (
                    r
                    for r in roster
                    if r.get("agent_id") == getattr(selected_agent, "agent_id", "")
                ),
                None,
            )
            if entry:
                config = entry.get("livekit_agent_session", {}) or {}

    if not config:
        raise HTTPException(
            status_code=404,
            detail="LiveKit agent session config not found for selected agent",
        )

    return AgentSessionConfigResponse(
        session_id=sid,
        agent_id=getattr(selected_agent, "agent_id", ""),
        livekit_agent_session=config,
        updated_at=datetime.now(timezone.utc).isoformat(),
    )


@router.get(
    "/api/livekit/ping",
    response_model=LiveKitPingResponse,
)
async def get_livekit_ping():
    """
    Backend health check to LiveKit RoomService.
    """
    ok, message = ping_livekit()
    return LiveKitPingResponse(ok=ok, message=message)


@router.post(
    "/api/sessions/{session_id}/voice/pods/{agent_id}/token",
    response_model=AgentPodTokenResponse,
)
async def get_agent_pod_token(
    session_id: str,
    agent_id: str,
    authorization: str = Header(None),
):
    """
    Build a LiveKit token for a specific agent's dedicated voice pod room.
    This follows LiveKit room/participant isolation: one pod room per agent.
    """
    sid, _ = await _extract_session_and_token(session_id, authorization)
    if not is_livekit_configured():
        raise HTTPException(status_code=503, detail="LiveKit is not configured")

    from utils.firestore_helpers import _get_db

    db = _get_db()
    doc = await db.collection(COLLECTION_CRISIS_SESSIONS).document(sid).get()
    if not doc.exists:
        raise HTTPException(status_code=404, detail="Session not found")
    session_data = doc.to_dict() or {}
    roster = session_data.get("agent_roster", [])
    entry = next((a for a in roster if a.get("agent_id") == agent_id), None)
    if not entry:
        raise HTTPException(status_code=404, detail="Agent not found")

    room_name = (
        entry.get("livekit_room")
        or f"war-room-{sid.lower()}-{agent_id.rsplit('_', 1)[0]}"
    )
    identity = entry.get("livekit_identity") or f"{agent_id}-participant"
    ensure_livekit_room(
        room_name=room_name,
        metadata={"session_id": sid, "agent_id": agent_id, "pod_type": "agent_voice"},
    )
    settings = get_settings()
    expires_at = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
    token = build_livekit_participant_token(
        room_name=room_name,
        identity=identity,
        name=entry.get("character_name", agent_id),
        metadata={"session_id": sid, "agent_id": agent_id, "role": "agent_pod"},
        ttl_seconds=3600,
    )

    return AgentPodTokenResponse(
        agent_id=agent_id,
        token=token,
        expires_at=expires_at,
        ws_audio_url=settings.livekit_url,
        livekit_room=room_name,
        livekit_identity=identity,
    )


@router.get(
    "/api/sessions/{session_id}/voice/pods",
    response_model=VoicePodsResponse,
)
async def get_voice_pods(
    session_id: str,
    authorization: str = Header(None),
):
    sid, _ = await _extract_session_and_token(session_id, authorization)
    from utils.firestore_helpers import _get_db

    db = _get_db()
    doc = await db.collection(COLLECTION_CRISIS_SESSIONS).document(sid).get()
    if not doc.exists:
        raise HTTPException(status_code=404, detail="Session not found")
    data = doc.to_dict() or {}
    pods = data.get("voice_pods", [])
    return VoicePodsResponse(
        session_id=sid,
        pods=[VoicePodState(**p) for p in pods],
        updated_at=datetime.now(timezone.utc).isoformat(),
    )


@router.patch(
    "/api/sessions/{session_id}/voice/pods/{pod_id}",
    response_model=VoicePodsResponse,
)
async def patch_voice_pod(
    session_id: str,
    pod_id: str,
    body: VoicePodPatchRequest,
    authorization: str = Header(None),
):
    """
    Connect/disconnect a specific voice pod.
    Disconnected pods are removed from backend turn routing immediately.
    """
    sid, _ = await _extract_session_and_token(session_id, authorization)
    from utils.firestore_helpers import _get_db

    db = _get_db()
    doc_ref = db.collection(COLLECTION_CRISIS_SESSIONS).document(sid)
    doc = await doc_ref.get()
    if not doc.exists:
        raise HTTPException(status_code=404, detail="Session not found")
    data = doc.to_dict() or {}
    pods = data.get("voice_pods", [])
    target = next((p for p in pods if p.get("pod_id") == pod_id), None)
    if not target:
        raise HTTPException(status_code=404, detail="Pod not found")

    target["connected"] = bool(body.connected)
    roster = data.get("agent_roster", [])
    if target.get("agent_id"):
        for r in roster:
            if r.get("agent_id") == target.get("agent_id"):
                r["pod_connected"] = bool(body.connected)
                if not body.connected:
                    r["status"] = "silent"
                elif r.get("status") == "silent":
                    r["status"] = "listening"
                break
    await doc_ref.update({
        "voice_pods": pods,
        "agent_roster": roster,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    })

    agent_id = target.get("agent_id")
    if agent_id:
        set_agent_voice_connected(sid, agent_id, bool(body.connected))
        # Stop turn immediately if disconnecting a current speaker.
        from utils.turn_manager import get_turn_manager
        tm = get_turn_manager(sid)
        if not body.connected and tm.current_speaker == agent_id:
            await tm.chairman_interrupt()

        # Optional runtime re-enable for a previously muted agent.
        agents = get_agents(sid)
        agent_obj = None
        for _, a in agents.items():
            if getattr(a, "agent_id", None) == agent_id:
                agent_obj = a
                break
        if agent_obj and body.connected and not getattr(agent_obj, "live_session", None):
            try:
                await agent_obj.initialize_live_session()
                await agent_obj.start_background_tasks()
            except Exception as e:
                logger.warning(f"Pod reconnect failed for {agent_id}: {e}")

    return VoicePodsResponse(
        session_id=sid,
        pods=[VoicePodState(**p) for p in pods],
        updated_at=datetime.now(timezone.utc).isoformat(),
    )
