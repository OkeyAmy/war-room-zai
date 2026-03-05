"""
WAR ROOM — FastAPI Application Entry Point
Mounts the gateway WebSocket router, REST session endpoints,
and scenario routes.
"""

from __future__ import annotations

import uuid
import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import FastAPI, HTTPException, Depends, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware

from config.settings import get_settings
from gateway.main import router as gateway_router
from gateway.scenario_routes import router as scenario_router
from gateway.agent_routes import router as agent_router
from gateway.pod_routes import router as pod_router
from gateway.voice_routes import router as voice_router
from gateway.chairman_audio_ws import router as audio_ws_router
from gateway.board_routes import router as board_router
from gateway.feed_routes import router as feed_router
from gateway.intel_routes import router as intel_router
from gateway.posture_routes import router as posture_router
from gateway.score_routes import router as score_router
from gateway.world_routes import router as world_router
from gateway.resolution_routes import router as resolution_router
from gateway.document_routes import router as document_router
from utils.auth import get_chairman_token, validate_chairman_token
from utils.pydantic_models import (
    CreateSessionRequest,
    CreateSessionResponse,
    SessionStateResponse,
    TimerInfo,
    PatchSessionRequest,
    PatchSessionResponse,
    DeleteSessionResponse,
)
from config.constants import (
    COLLECTION_CRISIS_SESSIONS,
    SESSION_ASSEMBLING,
    SESSION_ACTIVE,
    SESSION_RESOLUTION,
    SESSION_CLOSED,
    EVENT_SESSION_STATUS,
    EVENT_RESOLUTION_MODE_START,
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("warroom")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan — startup and shutdown hooks."""
    settings = get_settings()
    logger.info(f"WAR ROOM Backend starting (debug={settings.debug})")
    logger.info(f"LLM: Z.AI agent_model={settings.zai_agent_model}, scenario_model={settings.zai_scenario_model}")
    logger.info(f"Z.AI base_url={settings.zai_base_url}, api_key={'set' if settings.zai_api_key else 'missing'}")
    logger.info(
        "Voice runtime config: "
        f"voice_backend={settings.voice_backend}, "
        f"elevenlabs_stt={settings.elevenlabs_stt_model}, "
        f"elevenlabs_tts={settings.elevenlabs_tts_model}, "
        f"elevenlabs_key={'set' if bool(settings.elevenlabs_api_key) else 'missing'}, "
        f"livekit={'configured' if bool(settings.livekit_url and settings.livekit_api_key and settings.livekit_api_secret) else 'not_configured'}"
    )
    yield
    logger.info("WAR ROOM Backend shutting down")


# ── APP ──────────────────────────────────────────────────────────────────

app = FastAPI(
    title="⚔️ WAR ROOM — Backend API",
    description=(
        "Multi-agent AI crisis simulation platform. "
        "Powered by Z.AI GLM, LiveKit ElevenLabs, and Firestore."
    ),
    version="2.0.0",
    lifespan=lifespan,
)

# CORS for Next.js frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Restrict in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount routers — all 35 endpoints + 2 WebSockets
app.include_router(gateway_router, tags=["WebSocket Gateway"])
app.include_router(scenario_router)
app.include_router(agent_router)
app.include_router(pod_router)
app.include_router(voice_router, tags=["Voice"])
app.include_router(audio_ws_router, tags=["Chairman Audio WS"])
app.include_router(board_router)
app.include_router(feed_router)
app.include_router(intel_router)
app.include_router(posture_router)
app.include_router(score_router)
app.include_router(world_router)
app.include_router(resolution_router)
app.include_router(document_router)


# ── HELPER: compute timer ────────────────────────────────────────────────


def _compute_timer(
    created_at: str | None,
    duration_minutes: int,
) -> TimerInfo | None:
    """Build a timer dict from session created_at and duration."""
    if not created_at:
        return None

    try:
        start = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None

    now = datetime.now(timezone.utc)
    duration_seconds = duration_minutes * 60
    elapsed = int((now - start).total_seconds())
    remaining = max(0, duration_seconds - elapsed)
    mins, secs = divmod(remaining, 60)
    hrs, mins = divmod(mins, 60)

    return TimerInfo(
        session_duration_seconds=duration_seconds,
        elapsed_seconds=elapsed,
        remaining_seconds=remaining,
        formatted=f"{hrs:02d}:{mins:02d}:{secs:02d}",
    )


# ── REST ENDPOINTS ───────────────────────────────────────────────────────


# ── POST /api/sessions ───────────────────────────────────────────────────


@app.post(
    "/api/sessions",
    response_model=CreateSessionResponse,
    status_code=201,
    tags=["Sessions"],
    summary="Create a new crisis session",
)
async def create_session(
    request: CreateSessionRequest,
    background_tasks: BackgroundTasks,
):
    """
    User submits crisis input. Triggers full bootstrap sequence.

    Returns immediately with session identifiers; the bootstrap
    runs asynchronously in the background.
    """
    session_id = str(uuid.uuid4())[:8].upper()
    chairman_token = str(uuid.uuid4())
    created_at = datetime.now(timezone.utc).isoformat()

    settings = get_settings()
    ws_url = f"wss://api.warroom.app/ws/{session_id}"
    if settings.debug:
        ws_url = f"ws://localhost:{settings.port}/ws/{session_id}"

    # Write the initial session document with assembling status
    from utils.firestore_helpers import _get_db

    db = _get_db()
    initial_doc = {
        "session_id": session_id,
        "chairman_token": chairman_token,
        "chairman_name": request.chairman_name or "DIRECTOR",
        "chairman_id": "chairman_default",
        "session_duration_minutes": request.session_duration_minutes,
        "created_at": created_at,
        "status": SESSION_ASSEMBLING,
        "crisis_input": request.crisis_input,
        "crisis_title": "",
        "crisis_domain": "",
        "crisis_brief": "",
        "threat_level": "elevated",
        "resolution_score": 50,
        "score_history": [50],
        "posture": {
            "public_exposure": 60,
            "legal_exposure": 45,
            "internal_stability": 50,
            "public_trend": "rising",
            "legal_trend": "stable",
            "internal_trend": "stable",
        },
        "agent_roster": [],
        "agreed_decisions": [],
        "open_conflicts": [],
        "critical_intel": [],
        "escalation_events": [],
        "next_escalation_at": None,
        "final_decision": None,
        "paused": False,
        "scenario_spec": {},
        "scenario_instruction_guide": "",
        "voice_runtime": {},
        "assembly_log": [],
        "scenario_ready": False,
    }

    await db.collection(COLLECTION_CRISIS_SESSIONS) \
            .document(session_id).set(initial_doc)

    # Launch bootstrap in the background (non-blocking)
    from session_bootstrapper import bootstrap_session

    background_tasks.add_task(
        bootstrap_session,
        crisis_input=request.crisis_input,
        chairman_id="chairman_default",
        session_id=session_id,
        chairman_token=chairman_token,
        chairman_name=request.chairman_name or "DIRECTOR",
        session_duration_minutes=request.session_duration_minutes,
    )

    return CreateSessionResponse(
        session_id=session_id,
        chairman_token=chairman_token,
        status=SESSION_ASSEMBLING,
        ws_url=ws_url,
        created_at=created_at,
        message="Crisis received. Assembling your team.",
    )


# ── GET /api/sessions/{session_id} ──────────────────────────────────────


@app.get(
    "/api/sessions/{session_id}",
    response_model=SessionStateResponse,
    tags=["Sessions"],
    summary="Get crisis session state",
)
async def get_session(
    session_id: str,
    token: str = Depends(get_chairman_token),
):
    """
    Poll full session state. Used on reconnect or page refresh.
    Returns the full merged state including timer.
    """
    session_data = await validate_chairman_token(session_id, token)

    duration_mins = session_data.get("session_duration_minutes", 30)
    timer = _compute_timer(session_data.get("created_at"), duration_mins)

    return SessionStateResponse(
        session_id=session_id,
        status=session_data.get("status", SESSION_ASSEMBLING),
        crisis_title=session_data.get("crisis_title", ""),
        crisis_domain=session_data.get("crisis_domain", ""),
        crisis_brief=session_data.get("crisis_brief", ""),
        threat_level=session_data.get("threat_level", "elevated"),
        resolution_score=session_data.get("resolution_score", 50),
        created_at=session_data.get("created_at"),
        timer=timer,
        chairman_name=session_data.get("chairman_name", "DIRECTOR"),
        agent_count=len(session_data.get("agent_roster", [])),
    )


# ── PATCH /api/sessions/{session_id} ────────────────────────────────────


@app.patch(
    "/api/sessions/{session_id}",
    response_model=PatchSessionResponse,
    tags=["Sessions"],
    summary="Update session-level settings",
)
async def patch_session(
    session_id: str,
    body: PatchSessionRequest,
    token: str = Depends(get_chairman_token),
):
    """
    Update session-level settings mid-session.
    Supports: status change, pause/resume, threat level override.
    """
    session_data = await validate_chairman_token(session_id, token)

    from utils.firestore_helpers import _get_db
    from utils.events import push_event

    db = _get_db()
    updates: dict = {}
    updated_fields: list[str] = []

    # Status change
    if body.status is not None:
        allowed = {SESSION_ACTIVE, SESSION_RESOLUTION}
        if body.status not in allowed:
            raise HTTPException(
                status_code=422,
                detail=f"Status must be one of: {allowed}",
            )
        updates["status"] = body.status
        updated_fields.append("status")

        if body.status == SESSION_RESOLUTION:
            await push_event(session_id, EVENT_RESOLUTION_MODE_START, {})

    # Pause / resume
    if body.paused is not None:
        updates["paused"] = body.paused
        updated_fields.append("paused")

        event_type = "session_paused" if body.paused else "session_resumed"
        await push_event(session_id, EVENT_SESSION_STATUS, {
            "status": session_data.get("status", SESSION_ACTIVE),
            "message": "Session paused." if body.paused else "Session resumed.",
            "paused": body.paused,
        })

    # Threat level override
    if body.threat_level is not None:
        valid = {"contained", "elevated", "critical", "meltdown"}
        if body.threat_level not in valid:
            raise HTTPException(
                status_code=422,
                detail=f"Threat level must be one of: {valid}",
            )
        updates["threat_level"] = body.threat_level
        updated_fields.append("threat_level")

    if not updates:
        raise HTTPException(status_code=422, detail="No valid fields to update")

    await db.collection(COLLECTION_CRISIS_SESSIONS) \
            .document(session_id).update(updates)

    # Re-fetch the updated state
    updated_doc = await db.collection(COLLECTION_CRISIS_SESSIONS) \
                          .document(session_id).get()
    current_state = updated_doc.to_dict() if updated_doc.exists else {}

    # Strip sensitive fields
    current_state.pop("chairman_token", None)

    return PatchSessionResponse(
        session_id=session_id,
        updated_fields=updated_fields,
        current_state=current_state,
    )


# ── DELETE /api/sessions/{session_id} ───────────────────────────────────


@app.delete(
    "/api/sessions/{session_id}",
    response_model=DeleteSessionResponse,
    tags=["Sessions"],
    summary="End session and release all resources",
)
async def delete_session(
    session_id: str,
    token: str = Depends(get_chairman_token),
):
    """
    End session, release all Gemini Live connections, clean Firestore.
    Does NOT delete Firestore data (preserved for after-action report).
    """
    session_data = await validate_chairman_token(session_id, token)

    from utils.firestore_helpers import _get_db
    from utils.events import push_event
    from gateway.chairman_handler import get_agents

    db = _get_db()
    agents = get_agents(session_id)
    agents_released = 0

    # Close all agent Live sessions
    for role_key, agent in agents.items():
        try:
            await agent.close()
            agents_released += 1
        except Exception as e:
            logger.warning(f"Error closing agent {role_key}: {e}")

    # Update session status and mark all agents inactive
    closed_at = datetime.now(timezone.utc).isoformat()
    roster = session_data.get("agent_roster", [])
    for entry in roster:
        entry["status"] = "idle"

    await db.collection(COLLECTION_CRISIS_SESSIONS) \
            .document(session_id).update({
                "status": SESSION_CLOSED,
                "agent_roster": roster,
            })

    await push_event(session_id, EVENT_SESSION_STATUS, {
        "status": SESSION_CLOSED,
        "message": "Session closed.",
    })

    # Cleanup agent registry
    from gateway.chairman_handler import _active_agents, _observer_agents, _world_agents
    _active_agents.pop(session_id, None)
    _observer_agents.pop(session_id, None)
    _world_agents.pop(session_id, None)

    # Finalize documents before closing
    try:
        from agents.document_engine import finalize_all_documents
        finalized = await finalize_all_documents(session_id)
        logger.info(f"Finalized {len(finalized)} documents for session {session_id}")
    except Exception as e:
        logger.warning(f"Document finalization skipped for {session_id}: {e}")

    return DeleteSessionResponse(
        session_id=session_id,
        closed_at=closed_at,
        agents_released=agents_released,
        after_action_url=f"/api/sessions/{session_id}/report",
    )


# ── HEALTH CHECK ────────────────────────────────────────────────────────

@app.get(
    "/api/health",
    tags=["System"],
    summary="Comprehensive health check",
)
async def health_check():
    """
    Comprehensive health check — validates every subsystem in the
    WAR ROOM architecture. Environment-aware: dev uses local/mock
    storage, production checks real Firestore/Firebase.
    """
    import asyncio

    settings = get_settings()
    env = settings.environment
    checks: dict[str, dict] = {}

    async def check_zai_text():
        try:
            from openai import OpenAI
            client = OpenAI(
                api_key=settings.zai_api_key,
                base_url=settings.zai_base_url,
            )
            if not settings.zai_api_key:
                return {"status": "warn", "message": "ZAI_API_KEY not set — LLM calls will be skipped"}
            response = client.chat.completions.create(
                model=settings.zai_agent_model,
                messages=[{"role": "user", "content": "Respond with exactly: PING_OK"}],
                max_tokens=10,
            )
            reply = (response.choices[0].message.content or "").strip()
            return {
                "status": "pass",
                "message": f"Z.AI GLM reachable ({settings.zai_agent_model}), reply: {reply[:30]}",
            }
        except ImportError:
            return {"status": "warn", "message": "openai SDK not installed"}
        except Exception as e:
            status = "warn" if env == "development" else "fail"
            return {"status": status, "message": str(e)}

    async def check_database():
        try:
            if env == "production":
                from google.cloud import firestore
                db = firestore.AsyncClient()
                doc = await db.collection("crisis_sessions").document("__health_check__").get()
                return {
                    "status": "pass",
                    "message": f"Firestore connected (production, project={settings.gcp_project_id})",
                }
            else:
                from utils.firestore_helpers import _get_db
                db = _get_db()
                if hasattr(db, "collection"):
                    return {
                        "status": "pass",
                        "message": "Local storage (in-memory mock) active — development mode",
                        "storage_type": "in-memory" if not settings.firestore_emulator_host else "emulator",
                    }
                return {"status": "fail", "message": "Local DB missing 'collection' method"}
        except ImportError:
            if env == "production":
                return {"status": "fail", "message": "google-cloud-firestore not installed (required for production)"}
            return {"status": "pass", "message": "Running in dev without Firestore — using mock store"}
        except Exception as e:
            return {"status": "fail", "message": str(e)}

    async def check_event_system():
        try:
            from utils.events import _get_db as get_events_db
            events_db = get_events_db()
            if hasattr(events_db, "collection"):
                return {
                    "status": "pass",
                    "message": f"Event store operational ({type(events_db).__name__})",
                }
            return {"status": "fail", "message": "Event store missing 'collection' method"}
        except Exception as e:
            return {"status": "fail", "message": str(e)}

    async def check_agent_memory():
        try:
            from utils.firestore_helpers import _get_db
            from config.constants import COLLECTION_AGENT_MEMORY
            db = _get_db()
            ref = db.collection(COLLECTION_AGENT_MEMORY).document("__health_check__")
            if ref:
                return {
                    "status": "pass",
                    "message": f"Agent memory store reachable ({COLLECTION_AGENT_MEMORY})",
                }
            return {"status": "fail", "message": "Could not create memory reference"}
        except Exception as e:
            return {"status": "fail", "message": str(e)}

    async def check_scenario_analyst():
        try:
            from agents.scenario_analyst import _generate_mock_scenario
            mock = _generate_mock_scenario("health check", "HEALTH")
            if mock and "crisis_title" in mock and "agents" in mock:
                agent_count = len(mock.get("agents", []))
                return {
                    "status": "pass",
                    "message": f"Scenario Analyst ready ({agent_count} agents in mock)",
                }
            return {"status": "fail", "message": "Mock scenario missing required fields"}
        except Exception as e:
            return {"status": "fail", "message": str(e)}

    async def check_observer():
        try:
            from agents.observer_agent import ObserverAgent
            observer = ObserverAgent(session_id="__health_check__")
            analysis = observer._generate_default_analysis("test", "test_agent")
            if analysis and "trust_delta" in analysis:
                return {"status": "pass", "message": "Observer Agent initializable and analysis working"}
            return {"status": "fail", "message": "Observer default analysis malformed"}
        except Exception as e:
            return {"status": "fail", "message": str(e)}

    async def check_world_agent():
        try:
            from agents.world_agent import WorldAgent
            world = WorldAgent(
                session_id="__health_check__",
                escalation_schedule=[{"delay_minutes": 5, "event_text": "test", "type": "media"}],
            )
            if world.escalation_schedule and len(world.escalation_schedule) == 1:
                return {"status": "pass", "message": "World Agent initializable with escalation schedule"}
            return {"status": "fail", "message": "World Agent schedule not set"}
        except Exception as e:
            return {"status": "fail", "message": str(e)}

    async def check_skill_generator():
        try:
            from agents.skill_generator import generate_skill_md, _get_primary_risk_axis
            axis = _get_primary_risk_axis("legal")
            if axis == "legal_exposure":
                return {"status": "pass", "message": "Skill generator module loaded, risk axis mapping correct"}
            return {"status": "fail", "message": f"Unexpected risk axis: {axis}"}
        except Exception as e:
            return {"status": "fail", "message": str(e)}

    async def check_voice():
        try:
            from utils.voice_discovery import check_voice_health
            return await check_voice_health()
        except Exception as e:
            return {"status": "fail", "message": str(e)}

    async def check_gateway():
        try:
            ws_routes = [
                r for r in app.routes
                if hasattr(r, "path") and "/ws/" in getattr(r, "path", "")
            ]
            if ws_routes:
                return {"status": "pass", "message": f"Gateway WebSocket route mounted ({len(ws_routes)} routes)"}
            return {"status": "fail", "message": "No WebSocket routes found"}
        except Exception as e:
            return {"status": "fail", "message": str(e)}

    async def check_document_engine():
        try:
            from agents.document_engine import finalize_document
            from agents.intake import process_uploaded_documents
            return {
                "status": "pass",
                "message": "Document engine and intake modules loaded",
            }
        except Exception as e:
            return {"status": "fail", "message": str(e)}

    results = await asyncio.gather(
        check_zai_text(),
        check_database(),
        check_event_system(),
        check_agent_memory(),
        check_scenario_analyst(),
        check_observer(),
        check_world_agent(),
        check_skill_generator(),
        check_voice(),
        check_gateway(),
        check_document_engine(),
        return_exceptions=True,
    )

    check_names = [
        "zai_text_model",
        "database",
        "event_system",
        "agent_memory",
        "scenario_analyst",
        "observer_agent",
        "world_agent",
        "skill_generator",
        "voice_system",
        "gateway_websocket",
        "document_engine",
    ]

    for name, result in zip(check_names, results):
        if isinstance(result, Exception):
            checks[name] = {"status": "fail", "message": str(result)}
        else:
            checks[name] = result

    statuses = [c.get("status", "fail") for c in checks.values()]
    if all(s == "pass" for s in statuses):
        overall = "healthy"
    elif any(s == "fail" for s in statuses):
        overall = "degraded"
    else:
        overall = "healthy"

    failed = [k for k, v in checks.items() if v.get("status") == "fail"]
    passed = [k for k, v in checks.items() if v.get("status") == "pass"]

    return {
        "status": overall,
        "service": "war-room-backend",
        "version": "2.0.0",
        "environment": env,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "summary": {
            "total": len(checks),
            "passed": len(passed),
            "failed": len(failed),
            "warnings": len([k for k, v in checks.items() if v.get("status") == "warn"]),
        },
        "checks": checks,
    }


@app.get(
    "/api/voices",
    tags=["System"],
    summary="List available ElevenLabs voices",
)
async def list_voices():
    """List available ElevenLabs voices with fallback."""
    from utils.voice_discovery import discover_voices, get_voice_style_map

    voices = await discover_voices()
    style_map = await get_voice_style_map()

    return {
        "total": len(voices),
        "voices": voices,
        "by_style": style_map,
        "source": "sdk" if voices else "hardcoded",
    }


# ── UVICORN ENTRYPOINT ──────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn

    settings = get_settings()
    reload_enabled = settings.debug and not settings.single_agent_voice_mode
    uvicorn.run(
        "main:app",
        host=settings.host,
        port=settings.port,
        reload=reload_enabled,
        # Prevent runtime data writes (skills/sessions/logs) from restarting
        # the backend mid-conversation while --reload is enabled.
        reload_includes=["*.py", "*.env"],
        reload_excludes=[
            "data/*",
            "backend/data/*",
            "data/_dev_log/*",
            "backend/data/_dev_log/*",
            "backend/__pycache__/*",
            "backend/.pytest_cache/*",
            "backend/tests/*",
            ".git/*",
            "test/*",
        ],
    )
