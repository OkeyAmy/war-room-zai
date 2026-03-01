"""
WAR ROOM — Chairman Handler
Routes chairman audio and commands to the appropriate agents.
"""

from __future__ import annotations

import asyncio
import base64
import logging
from datetime import datetime, timezone

from config.constants import (
    EVENT_CHAIRMAN_SPOKE,
    EVENT_RESOLUTION_MODE_START,
    EVENT_AGENT_FINAL_POSITION,
    EVENT_SESSION_RESOLVED,
    EVENT_AGENT_STATUS_CHANGE,
    COLLECTION_CRISIS_SESSIONS,
    SESSION_RESOLUTION,
    SESSION_CLOSED,
)

logger = logging.getLogger(__name__)

# ── AGENT REGISTRY (session_id → dict of role_key → CrisisAgent) ──────────
# In production, this would be managed by the session bootstrapper
# and stored in a distributed cache or service registry.
_active_agents: dict[str, dict] = {}
_observer_agents: dict[str, object] = {}
_world_agents: dict[str, object] = {}
_turn_managers: dict[str, object] = {}  # session_id → TurnManager
_active_voice_agents: dict[str, str] = {}  # session_id → agent_id
_discussion_tasks: dict[str, asyncio.Task] = {}  # session_id → background task
_discussion_cursor: dict[str, int] = {}  # session_id → next agent index
_discussion_last_agent: dict[str, str] = {}  # session_id → previous speaker
_discussion_phase: dict[str, str] = {}  # session_id → intro | debate
_introduced_agents: dict[str, set[str]] = {}  # session_id → introduced agent_ids
_voice_connected_agents: dict[str, set[str]] = {}  # session_id → connected agent_ids


def register_agents(
    session_id: str,
    agents: dict,
    observer=None,
    world=None,
    turn_manager=None,
):
    """Register agents for a session after bootstrapping."""
    # MULTI-AGENT: commented out single-agent guard — all agents are registered
    # settings = get_settings()
    # if settings.single_agent_voice_mode and len(agents) > 1:
    #     # Hard safety: never keep more than one active voice agent in single-agent mode.
    #     first_key = next(iter(agents.keys()))
    #     agents = {first_key: agents[first_key]}
    #     logger.warning(
    #         f"[VOICE_RUNTIME] single-agent guard trimmed registry to 1 agent "
    #         f"for session {session_id}"
    #     )

    _active_agents[session_id] = agents
    if observer:
        _observer_agents[session_id] = observer
    if world:
        _world_agents[session_id] = world
    if turn_manager:
        _turn_managers[session_id] = turn_manager
    _voice_connected_agents[session_id] = {
        getattr(a, "agent_id", "") for _, a in agents.items() if getattr(a, "agent_id", "")
    }
    # Default active voice target to the first agent with a live session.
    for _, agent in agents.items():
        if getattr(agent, "live_session", None):
            _active_voice_agents[session_id] = getattr(agent, "agent_id", "")
            break
    logger.info(
        f"[VOICE_RUNTIME] session={session_id} registered_agents={len(agents)} "
        f"active_voice_agent={_active_voice_agents.get(session_id)}"
    )


def start_discussion_loop(session_id: str) -> None:
    """
    Start a backend-owned round-robin discussion scheduler.
    Ensures agents take turns speaking without overlap.
    """
    if session_id in _discussion_tasks and not _discussion_tasks[session_id].done():
        return

    async def _loop() -> None:
        from config.settings import get_settings
        from utils.firestore_helpers import _get_db

        logger.info(f"[LIVEKIT_AGENT_LOOP] started for session {session_id}")
        _discussion_cursor.setdefault(session_id, 0)
        _discussion_phase.setdefault(session_id, "intro")
        _introduced_agents.setdefault(session_id, set())
        db = _get_db()
        settings = get_settings()
        while True:
            tm = _turn_managers.get(session_id)
            if not tm or tm.is_session_ended():
                break
            agents_map = get_agents(session_id)
            connected = _voice_connected_agents.get(session_id, set())
            agents = [
                a for _, a in agents_map.items()
                if getattr(a, "live_session", None)
                and getattr(a, "agent_id", "") in connected
            ]
            if not agents:
                await asyncio.sleep(1.0)
                continue

            # MULTI-AGENT: commented out single-voice filter — all connected agents participate
            # if settings.single_agent_voice_mode:
            #     active_id = _active_voice_agents.get(session_id)
            #     if active_id:
            #         only = _resolve_agent(session_id, active_id)
            #         agents = [only] if only and getattr(only, "live_session", None) else []
            #     else:
            #         agents = []
            #     if not agents:
            #         await asyncio.sleep(1.0)
            #         continue

            # If someone already has the floor, wait.
            if not tm.is_floor_free():
                await asyncio.sleep(0.6)
                continue

            # MULTI-AGENT: commented out single-voice agent selection — use round-robin for all
            # if settings.single_agent_voice_mode:
            #     agent = agents[0]
            # else:
            idx = _discussion_cursor.get(session_id, 0) % len(agents)
            agent = agents[idx]
            _discussion_cursor[session_id] = (idx + 1) % len(agents)
            previous_agent_id = _discussion_last_agent.get(session_id)
            _discussion_last_agent[session_id] = getattr(agent, "agent_id", "")

            # Pull fresh board context so autonomous rounds stay scenario-grounded.
            crisis = {}
            try:
                doc = await db.collection(COLLECTION_CRISIS_SESSIONS).document(session_id).get()
                if doc.exists:
                    crisis = doc.to_dict() or {}
            except Exception as e:
                logger.debug(f"[LIVEKIT_AGENT_LOOP] failed reading crisis doc: {e}")

            open_conflicts = crisis.get("open_conflicts", [])
            latest_conflict = open_conflicts[-1] if open_conflicts else {}
            critical_intel = crisis.get("critical_intel", [])
            latest_intel = critical_intel[-1] if critical_intel else {}
            previous_claim = ""
            if previous_agent_id:
                previous_claim = (crisis.get(f"agent_last_statement_{previous_agent_id}") or "").strip()

            char_name = getattr(agent, "role_config", {}).get("character_name", "Agent")
            target_hint = ""
            if previous_agent_id and previous_agent_id != getattr(agent, "agent_id", ""):
                target_hint = (
                    f"Address {previous_agent_id} directly and challenge or support their last claim. "
                )

            # Deterministic conversation phases:
            #   1) intro: each agent introduces themselves exactly once
            #   2) debate: structured pushback based on live board state
            agent_id = getattr(agent, "agent_id", "")
            introduced = _introduced_agents.get(session_id, set())
            if _discussion_phase.get(session_id) == "intro" and agent_id not in introduced:
                prompt = (
                    "INTRO ROUND.\n"
                    f"You are {char_name}. Introduce yourself in 2-3 sentences.\n"
                    "State your role priority and one immediate concern about this crisis.\n"
                    "Do not output JSON or tool-call traces."
                )
                introduced.add(agent_id)
                _introduced_agents[session_id] = introduced
                if len(introduced) >= len(agents):
                    _discussion_phase[session_id] = "debate"
            else:
                _discussion_phase[session_id] = "debate"
                prompt = (
                    "DEBATE ROUND.\n"
                    f"You are {char_name}. Keep the room moving without waiting for the Chairman.\n"
                    f"Crisis brief: {crisis.get('crisis_brief', '')}\n"
                    f"Threat={crisis.get('threat_level', 'elevated')} "
                    f"Score={crisis.get('resolution_score', 50)}\n"
                    f"Latest conflict: {latest_conflict.get('description', 'none')}\n"
                    f"Latest intel: {latest_intel.get('text', 'none')}\n"
                    f"Prior claim to react to: {previous_claim or 'none'}\n\n"
                    f"{target_hint}"
                    "Speak 3-5 sentences. Explicitly challenge or support one other agent. "
                    "If disagreement sharpens, call write_open_conflict(). "
                    "If consensus forms, call write_agreed_decision(). "
                    "Do not output JSON or tool-call traces."
                )

            # Rotate active responder target and prompt a concise turn.
            _active_voice_agents[session_id] = getattr(agent, "agent_id", "")
            try:
                await agent.send_text(prompt)
                logger.info(
                    f"[LIVEKIT_AGENT_LOOP] dispatched turn session={session_id} "
                    f"agent={getattr(agent, 'agent_id', 'unknown')} "
                    f"phase={_discussion_phase.get(session_id)}"
                )
            except Exception as e:
                logger.warning(f"[LIVEKIT_AGENT_LOOP] dispatch failed: {e}")

            await asyncio.sleep(10.0)

        logger.info(f"[LIVEKIT_AGENT_LOOP] stopped for session {session_id}")

    _discussion_tasks[session_id] = asyncio.create_task(
        _loop(),
        name=f"discussion_loop_{session_id}",
    )


def get_agents(session_id: str) -> dict:
    """Get active agents for a session."""
    return _active_agents.get(session_id, {})


def get_active_voice_agent_id(session_id: str) -> str | None:
    """Return the current voice-target agent for the session, if set."""
    return _active_voice_agents.get(session_id)


def get_observer_agent(session_id: str):
    """Return observer agent for session if registered."""
    return _observer_agents.get(session_id)


def _resolve_agent(session_id: str, agent_id: str | None):
    """Resolve agent by role key or canonical agent_id."""
    if not agent_id:
        return None
    agents = get_agents(session_id)
    agent = agents.get(agent_id)
    if agent:
        return agent
    for _, candidate in agents.items():
        if getattr(candidate, "agent_id", None) == agent_id:
            return candidate
    return None


def select_voice_agent(session_id: str, target_agent_id: str | None = None):
    """
    Pick the single agent that should receive chairman input.
    Priority:
      1) Explicit target from frontend/REST
      2) Session's currently active voice agent
      3) First live agent in roster
    """
    # Explicit target wins.
    agent = _resolve_agent(session_id, target_agent_id)
    connected = _voice_connected_agents.get(session_id, set())
    if (
        agent
        and getattr(agent, "live_session", None)
        and getattr(agent, "agent_id", "") in connected
    ):
        _active_voice_agents[session_id] = getattr(agent, "agent_id", target_agent_id)
        return agent

    # Reuse current active target.
    active_id = _active_voice_agents.get(session_id)
    agent = _resolve_agent(session_id, active_id)
    if (
        agent
        and getattr(agent, "live_session", None)
        and getattr(agent, "agent_id", "") in connected
    ):
        return agent

    # Fallback to first available live session.
    for _, fallback in get_agents(session_id).items():
        if (
            getattr(fallback, "live_session", None)
            and getattr(fallback, "agent_id", "") in connected
        ):
            _active_voice_agents[session_id] = getattr(fallback, "agent_id", "")
            return fallback
    return None


def set_agent_voice_connected(session_id: str, agent_id: str, connected: bool) -> None:
    """Mark an agent voice pod connected/disconnected for routing and turns."""
    current = _voice_connected_agents.setdefault(session_id, set())
    if connected:
        current.add(agent_id)
    else:
        current.discard(agent_id)
        if _active_voice_agents.get(session_id) == agent_id:
            _active_voice_agents.pop(session_id, None)


async def handle_chairman_audio(
    session_id: str,
    audio_b64: str,
    target_agent_id: str | None = None,
    transcript: str = "",
):
    """
    Handle chairman audio input.
    Routes audio to the target agent's Live session,
    or broadcasts to all agents if no target specified.

    Args:
        session_id: The crisis session ID.
        audio_b64: Base64-encoded PCM audio from the chairman's mic.
        target_agent_id: Specific agent to address, or None for broadcast.
        transcript: Optional transcript of what the chairman said.
    """
    from utils.events import push_event
    from voice.pipeline import route_audio_to_agent

    agents = get_agents(session_id)
    if not agents:
        logger.warning(f"No agents registered for session {session_id}")
        return

    # Decode audio
    try:
        audio_data = base64.b64decode(audio_b64)
    except Exception as e:
        logger.error(f"Failed to decode chairman audio: {e}")
        return

    # Chairman has priority — interrupt current speaker via TurnManager
    tm = _turn_managers.get(session_id)
    if tm:
        await tm.chairman_interrupt()

    # Notify all frontends immediately so they stop agent audio playback
    await push_event(session_id, "chairman_taking_floor", {
        "target_agent_id": target_agent_id,
    })

    # Push chairman_spoke event
    await push_event(session_id, EVENT_CHAIRMAN_SPOKE, {
        "transcript": transcript,
        "target_agent_id": target_agent_id,
    })

    # LiveKit-style turn routing: route chairman mic to exactly one active agent.
    agent = select_voice_agent(session_id, target_agent_id)
    if not agent:
        logger.warning(
            f"No live voice agent available for session {session_id} "
            f"(target={target_agent_id})"
        )
        return

    await route_audio_to_agent(agent, audio_data)


async def handle_chairman_command(
    session_id: str,
    command: str,
    params: dict = None,
):
    """
    Handle a chairman command (non-audio).
    Commands: FORCE_VOTE, DISMISS_AGENT, INJECT_INTEL, START_RESOLUTION, etc.

    Args:
        session_id: The crisis session ID.
        command: The command type.
        params: Command-specific parameters.
    """
    from utils.events import push_event
    from utils.firestore_helpers import _get_db
    from config.settings import get_settings

    params = params or {}
    agents = get_agents(session_id)
    settings = get_settings()

    logger.info(f"Chairman command: {command} for session {session_id}")

    if command == "FORCE_VOTE":
        # Force all agents to state their position
        topic = params.get("topic", "the current crisis")
        # MULTI-AGENT: commented out single-agent branch — all agents vote
        # if settings.single_agent_voice_mode:
        #     active = select_voice_agent(session_id, None)
        #     if active and active.live_session:
        #         await active.send_text(
        #             f"The Chairman has called for a VOTE on: {topic}. "
        #             "State your position clearly — FOR or AGAINST. "
        #             "You have 30 seconds."
        #         )
        # else:
        for role_key, agent in agents.items():
            if agent.live_session:
                await agent.send_text(
                    f"The Chairman has called for a VOTE on: {topic}. "
                    "State your position clearly — FOR or AGAINST. "
                    "You have 30 seconds."
                )

    elif command == "DISMISS_AGENT":
        # Remove an agent from the session
        target_id = params.get("agent_id")
        if target_id and target_id in agents:
            agent = agents[target_id]
            await agent.close()
            del agents[target_id]
            await push_event(session_id, EVENT_AGENT_STATUS_CHANGE, {
                "agent_id": target_id,
                "status": "dismissed",
                "previous_status": "idle",
            })
            logger.info(f"Agent {target_id} dismissed from session {session_id}")

    elif command == "INJECT_INTEL":
        # Chairman injects custom intelligence
        from tools.crisis_board_tools import write_critical_intel
        await write_critical_intel(
            session_id=session_id,
            agent_id="chairman",
            text=params.get("text", ""),
            source=params.get("source", "INTERNAL"),
            is_escalation=params.get("is_escalation", False),
        )

    elif command == "START_RESOLUTION":
        # Begin resolution phase
        await push_event(session_id, EVENT_RESOLUTION_MODE_START, {})

        db = _get_db()
        await db.collection(COLLECTION_CRISIS_SESSIONS) \
                .document(session_id) \
                .update({"status": SESSION_RESOLUTION})

        # Cancel world agent escalations
        world = _world_agents.get(session_id)
        if world:
            await world.cancel()

        # Ask each agent for their final position
        # MULTI-AGENT: commented out single-agent branch — all agents give final position
        # if settings.single_agent_voice_mode:
        #     active = select_voice_agent(session_id, None)
        #     if active and active.live_session:
        #         await active.send_text(
        #             "RESOLUTION MODE: The Chairman is closing this crisis. "
        #             "State your FINAL position and recommendation in one sentence."
        #         )
        # else:
        for role_key, agent in agents.items():
            if agent.live_session:
                await agent.send_text(
                    "RESOLUTION MODE: The Chairman is closing this crisis. "
                    "State your FINAL position and recommendation in one sentence."
                )

    elif command == "CLOSE_SESSION":
        # End the session
        final_decision = params.get("final_decision", "Session closed by Chairman.")
        db = _get_db()
        await db.collection(COLLECTION_CRISIS_SESSIONS) \
                .document(session_id) \
                .update({
                    "status": SESSION_CLOSED,
                    "final_decision": final_decision,
                    "resolution_at": datetime.now(timezone.utc).isoformat(),
                })

        await push_event(session_id, EVENT_SESSION_RESOLVED, {
            "session_id": session_id,
            "final_decision": final_decision,
            "projected_futures": [],
        })

        # Close all agents
        for role_key, agent in agents.items():
            await agent.close()

        # End turn manager — stops all speak loops immediately
        tm = _turn_managers.get(session_id)
        if tm:
            await tm.end_session()

        # Cleanup registries
        _active_agents.pop(session_id, None)
        _observer_agents.pop(session_id, None)
        _world_agents.pop(session_id, None)
        _turn_managers.pop(session_id, None)
        _active_voice_agents.pop(session_id, None)
        _discussion_cursor.pop(session_id, None)
        _discussion_last_agent.pop(session_id, None)
        _discussion_phase.pop(session_id, None)
        _introduced_agents.pop(session_id, None)
        _voice_connected_agents.pop(session_id, None)
        task = _discussion_tasks.pop(session_id, None)
        if task and not task.done():
            task.cancel()

    else:
        # Treat unrecognized commands as free-text directed at agents.
        # This handles cases where the frontend sends typed text via
        # the "command" WS message type instead of "chairman_speech".
        logger.info(f"Treating as free-text: {command[:80]}")

        # Chairman has priority — interrupt current speaker
        tm = _turn_managers.get(session_id)
        if tm:
            await tm.chairman_interrupt()

        from voice.pipeline import handle_chairman_text
        await handle_chairman_text(
            session_id=session_id,
            text=command,
            target_agent_id=params.get("target_agent_id") if params else None,
        )
