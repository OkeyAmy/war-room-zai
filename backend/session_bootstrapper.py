"""
WAR ROOM — Session Bootstrapper
Called as a background task after POST /api/sessions.
The initial Firestore document already exists; this function runs
the Scenario Analyst, assembles agents, and transitions the session
from "assembling" → "briefing" → ready.
"""

from __future__ import annotations

import uuid
import asyncio
import logging
from datetime import datetime, timezone

from agents.scenario_analyst import run_scenario_analyst
from agents.skill_generator import generate_skill_md
from agents.voice_assignment import assign_voices
from agents.base_crisis_agent import CrisisAgent
from agents.observer_agent import ObserverAgent
from agents.world_agent import WorldAgent
from voice.livekit_session import (
    build_livekit_agent_session_config,
    build_scenario_instruction_guide,
)
from gateway.chairman_handler import (
    register_agents,
    select_voice_agent,
    start_discussion_loop,
)
from utils.events import push_event, get_event_queue
from utils.turn_manager import get_turn_manager
from utils.livekit_api import ensure_livekit_room, is_livekit_configured
from utils.firestore_helpers import _get_db, compute_next_escalation
from config.settings import get_settings
from config.constants import (
    COLLECTION_CRISIS_SESSIONS,
    COLLECTION_AGENT_MEMORY,
    EVENT_SESSION_STATUS,
    EVENT_AGENT_ASSEMBLING,
    EVENT_SESSION_READY,
    SESSION_ASSEMBLING,
    SESSION_BRIEFING,
    DEFAULT_POSTURE,
)

logger = logging.getLogger(__name__)


# ── ASSEMBLY LOG HELPERS ────────────────────────────────────────────────


async def _update_assembly_log(
    session_id: str,
    line: str,
    value: str,
    status: str = "in_progress",
):
    """Append an assembly log entry and push it via WS."""
    db = _get_db()
    doc = await db.collection(COLLECTION_CRISIS_SESSIONS) \
                  .document(session_id).get()

    if doc.exists:
        data = doc.to_dict()
        log = data.get("assembly_log", [])
    else:
        log = []

    # If the last entry has the same line text, update it in place
    entry = {"line": line, "value": value, "status": status}
    updated = False
    for i, existing in enumerate(log):
        if existing.get("line") == line:
            log[i] = entry
            updated = True
            break
    if not updated:
        log.append(entry)

    await db.collection(COLLECTION_CRISIS_SESSIONS) \
            .document(session_id).update({"assembly_log": log})

    # Push event so WS clients get the update immediately
    await push_event(session_id, EVENT_SESSION_STATUS, {
        "status": SESSION_ASSEMBLING,
        "message": f"{line} {value}",
        "assembly_log": log,
    })


# ── BOOTSTRAP ENTRY POINT ──────────────────────────────────────────────


async def bootstrap_session(
    crisis_input: str,
    chairman_id: str,
    session_id: str,
    chairman_token: str = "",
    chairman_name: str = "DIRECTOR",
    session_duration_minutes: int = 30,
) -> str:
    """
    Full session initialization sequence.
    The Firestore document already exists (created by POST /api/sessions).
    This function updates it as the bootstrap progresses.

    SEQUENCE:
    1.  Push "assembling" event immediately
    2.  Run Scenario Analyst → get full scenario spec
    3.  Update crisis_sessions document with scenario data
    4.  Assign unique voices to each agent
    5.  Generate SKILL.md for each agent (parallel)
    6.  Initialize each CrisisAgent (parallel)
    7.  Open Gemini Live WebSocket for each agent (parallel)
    8.  Initialize Observer Agent (reads all public data)
    9.  Schedule World Agent escalation events
    10. Push "session_ready" event → frontend moves to War Room
    """
    logger.info(f"Bootstrapping session {session_id} for chairman {chairman_id}")
    db = _get_db()

    # Ensure event queue exists so all bootstrap events reach the WS
    get_event_queue(session_id)

    # Step 1: Push "assembling" event
    await push_event(session_id, EVENT_SESSION_STATUS, {
        "status": SESSION_ASSEMBLING,
        "message": "Analyzing crisis scenario...",
    })
    await _update_assembly_log(
        session_id,
        "Initializing scenario analysis:",
        "STARTING...",
        "in_progress",
    )

    # Optional LiveKit provisioning (backend-owned).
    if is_livekit_configured():
        try:
            ensure_livekit_room(
                room_name=f"war-room-{session_id.lower()}",
                metadata={"session_id": session_id},
            )
            await _update_assembly_log(
                session_id,
                "Provisioning voice transport:",
                "LIVEKIT ROOM READY",
                "complete",
            )
        except Exception as e:
            logger.warning(f"LiveKit room provisioning failed for {session_id}: {e}")

    # Step 2: Scenario Analyst
    await _update_assembly_log(
        session_id,
        "Extracting crisis domain:",
        "ANALYZING...",
        "in_progress",
    )

    scenario = await run_scenario_analyst(crisis_input, session_id)
    # MULTI-AGENT: commented out single-agent truncation — all agents are used
    # Product constraint: single active voice agent for stability.
    agents_cfg = scenario.get("agents", [])
    # scenario["agents"] = agents_cfg[:1]
    # if len(agents_cfg) > 1:
    #     logger.info(
    #         f"Scenario generated {len(agents_cfg)} agents; truncating to 1 active agent"
    #     )
    logger.info(f"Scenario: {scenario.get('crisis_title', 'Unknown')} — {len(agents_cfg)} agents")

    await _update_assembly_log(
        session_id,
        "Extracting crisis domain:",
        scenario.get("crisis_domain", "CORPORATE").upper(),
        "complete",
    )

    await push_event(session_id, EVENT_SESSION_STATUS, {
        "status": SESSION_ASSEMBLING,
        "message": "Assembling crisis team...",
    })

    # Step 3: Update Firestore with scenario data
    agent_count = len(scenario.get("agents", []))

    update_data = {
        "crisis_title": scenario.get("crisis_title", ""),
        "crisis_domain": scenario.get("crisis_domain", "corporate"),
        "crisis_brief": scenario.get("crisis_brief", ""),
        "threat_level": scenario.get("threat_level_initial", "elevated"),
        "resolution_score": scenario.get("resolution_score_initial", 55),
        "score_history": [scenario.get("resolution_score_initial", 55)],
        "scenario_spec": scenario,
        "scenario_instruction_guide": build_scenario_instruction_guide(
            crisis_input=crisis_input,
            crisis_title=scenario.get("crisis_title", ""),
            crisis_brief=scenario.get("crisis_brief", ""),
        ),
        "voice_runtime": {
            # MULTI-AGENT: changed mode from single_active_agent to multi_agent_pods
            "mode": "multi_agent_pods",
            "backend": "livekit_elevenlabs",
            "pipeline": "stt-llm-tts",
            "multimodality": {
                "audio_input": True,
                "audio_output": True,
                "text_input": True,
                "text_output": True,
                "transcriptions": True,
            },
            "providers": {
                "stt": "elevenlabs",
                "llm": "google_gemini",
                "tts": "elevenlabs",
            },
            "turn_detection": {
                "enabled": True,
                "allow_interruptions": True,
                "chairman_priority": True,
            },
        },
    }

    # Handle initial conflicts
    open_conflicts = []
    if scenario.get("initial_conflicts"):
        for conflict in scenario["initial_conflicts"]:
            open_conflicts.append({
                "conflict_id": str(uuid.uuid4())[:8],
                "description": conflict.get("description", ""),
                "agents_involved": conflict.get("agents_involved", []),
                "opened_at": datetime.now(timezone.utc).isoformat(),
                "severity": "medium",
            })
    update_data["open_conflicts"] = open_conflicts

    # Handle initial intel
    critical_intel = []
    if scenario.get("initial_intel"):
        for intel in scenario["initial_intel"]:
            critical_intel.append({
                "intel_id": str(uuid.uuid4())[:8],
                "text": intel.get("text", ""),
                "source": intel.get("source", "INTERNAL"),
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "is_escalation": False,
            })
    update_data["critical_intel"] = critical_intel

    await db.collection(COLLECTION_CRISIS_SESSIONS) \
            .document(session_id).update(update_data)

    await _update_assembly_log(
        session_id,
        "Generating tactical cast:",
        f"SYNCING {agent_count} AGENTS",
        "in_progress",
    )

    # Step 4: Voice assignment
    voice_assignments = assign_voices(scenario.get("agents", []))
    settings = get_settings()
    single_voice_mode = settings.single_agent_voice_mode
    single_voice_target = (settings.single_agent_voice_target or "").strip()
    default_first_role = (
        scenario.get("agents", [{}])[0].get("role_key", "")
        if scenario.get("agents")
        else ""
    )

    # Step 5+6+7: Generate SKILLs and init agents in parallel
    agent_instances: dict[str, CrisisAgent] = {}

    async def init_one_agent(agent_config: dict, pod_index: int) -> dict:
        role_key = agent_config["role_key"]
        voice = voice_assignments.get(role_key, "Kore")
        agent_id = f"{role_key}_{session_id}"

        # Push assembling event for this agent
        await push_event(session_id, EVENT_AGENT_ASSEMBLING, {
            "agent_id": agent_id,
            "character_name": agent_config["character_name"],
            "role_title": agent_config["role_title"],
            "identity_color": agent_config.get("identity_color", "#666"),
            "defining_line": agent_config.get("defining_line", ""),
            "voice_name": voice,
        })

        # Generate SKILL.md
        skill_md = await generate_skill_md(
            agent_config, scenario, session_id, voice
        )

        # Initialize agent
        # Get the session's TurnManager so agents coordinate turns
        tm = get_turn_manager(session_id)
        livekit_session_config = build_livekit_agent_session_config(
            session_id=session_id,
            agent_id=agent_id,
            character_name=agent_config["character_name"],
            role_title=agent_config["role_title"],
            assigned_voice=voice,
            skill_md=skill_md,
            text_model=settings.text_model,
            stt_model=settings.elevenlabs_stt_model,
            tts_model=settings.elevenlabs_tts_model,
            crisis_brief=scenario.get("crisis_brief", ""),
            allow_interruptions=True,
        )

        agent = CrisisAgent(
            session_id=session_id,
            agent_id=agent_id,
            role_config=agent_config,
            skill_md=skill_md,
            assigned_voice=voice,
            turn_manager=tm,
            livekit_session_config=livekit_session_config,
        )
        agent.initialize_adk()

        # Open Live voice session
        await agent.initialize_live_session()
        logger.info(
            f"[VOICE_RUNTIME] session={session_id} agent={agent.agent_id} "
            f"{agent.voice_runtime_summary()}"
        )

        # MULTI-AGENT: commented out single-voice muting — all agents start background tasks
        # Start persistent background tasks.
        # In single-agent voice mode, only one selected pod is allowed to speak.
        # agent_is_voice_active = True
        # if single_voice_mode:
        #     target_match = (
        #         single_voice_target == ""
        #         or single_voice_target == role_key
        #         or single_voice_target == agent_id
        #     )
        #     if single_voice_target:
        #         agent_is_voice_active = target_match
        #     else:
        #         agent_is_voice_active = role_key == default_first_role
        agent_is_voice_active = True

        # All agents always start their background voice tasks in multi-agent mode
        await agent.start_background_tasks()

        # Write agent memory (isolated — only this agent reads/writes)
        agent_livekit_room = None
        agent_livekit_identity = None
        if is_livekit_configured():
            try:
                agent_livekit_room = f"war-room-{session_id.lower()}-{role_key}"
                agent_livekit_identity = f"{agent_id}-participant"
                ensure_livekit_room(
                    room_name=agent_livekit_room,
                    metadata={
                        "session_id": session_id,
                        "agent_id": agent_id,
                        "role_key": role_key,
                        "pod_type": "agent_voice",
                    },
                )
            except Exception as e:
                logger.warning(
                    f"Failed provisioning LiveKit pod room for {agent_id}: {e}"
                )

        memory_data = {
            "agent_id": agent_id,
            "session_id": session_id,
            "character_name": agent_config["character_name"],
            "private_facts": [],
            "hidden_agenda": agent_config.get("hidden_knowledge", ""),
            "private_commitments": [],
            "previous_statements": [],
            "public_positions": {},
            "contradictions_detected": 0,
            "adk_session_id": agent.adk_session_id,
            "voice_name": voice,
            "voice_session_active": True,
            "livekit_agent_session": livekit_session_config,
            "livekit_room": agent_livekit_room,
            "livekit_identity": agent_livekit_identity,
        }
        await agent.memory_ref.set(memory_data)

        agent_instances[role_key] = agent

        # Return roster entry (for Firestore update)
        return {
            "agent_id": agent_id,
            "role_key": role_key,
            "role_title": agent_config["role_title"],
            "character_name": agent_config["character_name"],
            "voice_name": voice,
            "identity_color": agent_config.get("identity_color", "#666"),
            "defining_line": agent_config.get("defining_line", ""),
            "agenda": agent_config.get("agenda", ""),
            "status": "idle" if agent_is_voice_active else "silent",
            "trust_score": 70,
            "last_spoke_at": None,
            "livekit_room": agent_livekit_room,
            "livekit_identity": agent_livekit_identity,
            "pod_id": f"pod_{pod_index}",
            "pod_connected": bool(agent_is_voice_active),
            "livekit_agent_session": livekit_session_config,
        }

    # Run all agent inits concurrently
    roster_entries = await asyncio.gather(*[
        init_one_agent(a, idx + 1) for idx, a in enumerate(scenario.get("agents", []))
    ])

    await _update_assembly_log(
        session_id,
        "Generating tactical cast:",
        f"SYNCED {agent_count} AGENTS",
        "complete",
    )

    # Step 8: Observer Agent
    await _update_assembly_log(
        session_id,
        "Formulating opening brief:",
        "IN PROGRESS",
        "in_progress",
    )

    # Observer remains active in single-agent mode for board intelligence updates.
    observer = ObserverAgent(session_id=session_id)
    await observer.start_watching()

    await _update_assembly_log(
        session_id,
        "Formulating opening brief:",
        "COMPLETED",
        "complete",
    )

    # Step 9: World Agent
    await _update_assembly_log(
        session_id,
        "Establishing secure connection:",
        "CONNECTING...",
        "in_progress",
    )

    # World agent remains active in single-agent mode for timed escalations.
    world = WorldAgent(
        session_id=session_id,
        escalation_schedule=scenario.get("escalation_schedule", []),
    )
    await world.start_timer()

    await _update_assembly_log(
        session_id,
        "Establishing secure connection:",
        "ACTIVE",
        "complete",
    )

    # MULTI-AGENT: commented out single-voice-mode pin and conditional discussion loop
    # Register agents + turn manager in the chairman handler
    tm = get_turn_manager(session_id)
    register_agents(session_id, agent_instances, observer, world, tm)
    # Pin active voice agent in single-agent mode.
    # if single_voice_mode:
    #     selected_agent_id = ""
    #     if single_voice_target:
    #         if "_" in single_voice_target and single_voice_target.endswith(session_id):
    #             selected_agent_id = single_voice_target
    #         else:
    #             selected_agent_id = f"{single_voice_target}_{session_id}"
    #     else:
    #         selected_agent_id = f"{default_first_role}_{session_id}" if default_first_role else ""
    #     if selected_agent_id:
    #         selected = select_voice_agent(session_id, selected_agent_id)
    #         if selected:
    #             logger.info(
    #                 f"[VOICE_RUNTIME] single-agent mode active speaker "
    #                 f"session={session_id} agent={selected.agent_id}"
    #             )
    # Backend-owned autonomous loop is multi-agent behavior.
    # In single-agent mode we only speak on explicit chairman input.
    # if not single_voice_mode:
    #     start_discussion_loop(session_id)
    # else:
    #     logger.info(
    #         f"[VOICE_RUNTIME] single-agent mode: autonomous discussion loop disabled "
    #         f"for session {session_id}"
    #     )
    # MULTI-AGENT: always start the discussion loop for all 4 agents
    start_discussion_loop(session_id)

    # Update Firestore with full roster + transition to briefing
    fixed_pods = []
    for i in range(1, 5):
        pod_id = f"pod_{i}"
        entry = next((r for r in roster_entries if r.get("pod_id") == pod_id), None)
        fixed_pods.append({
            "pod_id": pod_id,
            "agent_id": entry.get("agent_id") if entry else None,
            "connected": bool(entry.get("pod_connected")) if entry else False,
            "livekit_room": entry.get("livekit_room") if entry else None,
            "livekit_identity": entry.get("livekit_identity") if entry else None,
            "livekit_agent_session": entry.get("livekit_agent_session") if entry else None,
        })
    fixed_pods.append({
        "pod_id": "pod_5_summon",
        "agent_id": None,
        "connected": False,
        "livekit_room": None,
        "livekit_identity": None,
    })

    await db.collection(COLLECTION_CRISIS_SESSIONS) \
            .document(session_id).update({
                "agent_roster": list(roster_entries),
                "voice_pods": fixed_pods,
                "status": SESSION_BRIEFING,
                "scenario_ready": True,
                "next_escalation_at": compute_next_escalation(
                    scenario.get("escalation_schedule", [])
                ),
            })

    # Step 10: Session ready
    await push_event(session_id, EVENT_SESSION_READY, {
        "session_id": session_id,
        "crisis_title": scenario.get("crisis_title", ""),
        "agent_count": len(roster_entries),
    })

    # Step 11: Kick-start the briefing round.
    # Each agent's persistent _receive_from_gemini loop is already running.
    # We just need to send them the initial crisis brief to trigger speech.
    crisis_brief = scenario.get(
        "crisis_brief",
        scenario.get("crisis_title", "Unknown crisis"),
    )

    async def _kick_start_briefing():
        """
        Send opening brief to each agent SEQUENTIALLY.
        Uses the TurnManager so each agent finishes speaking before the
        next one begins — no more overlapping opening briefs.
        """
        tm = get_turn_manager(session_id)
        await asyncio.sleep(2)  # Wait for WS connections to establish
        ordered = list(agent_instances.items())
        # MULTI-AGENT: commented out single-voice filter — all agents get the briefing
        # if single_voice_mode:
        #     # Only kick the selected active voice pod in single-agent mode.
        #     active_id = f"{single_voice_target}_{session_id}" if single_voice_target else f"{default_first_role}_{session_id}"
        #     ordered = [(k, a) for k, a in ordered if a.agent_id == active_id] or ordered[:1]

        for role_key, agent in ordered:
            char = agent.role_config.get("character_name", role_key)
            title = agent.role_config.get("role_title", "Advisor")
            briefing = (
                f"You are in a live crisis war room. The situation is:\n\n"
                f"{crisis_brief}\n\n"
                f"You are {char}, the {title}. "
                f"This is the opening round. Briefly introduce yourself and give "
                f"your immediate assessment of the crisis. "
                f"Keep it to 2-3 sentences. Speak naturally and in character."
            )
            try:
                await agent.send_text(briefing)
            except Exception as e:
                logger.warning(f"Failed to send briefing to {role_key}: {e}")

            # Wait for the agent to finish speaking before moving to the next.
            # The TurnManager lock will be acquired by _receive_from_gemini
            # when the agent starts speaking, and released when done.
            # We poll until the floor is free (max 20s per agent).
            for _ in range(40):
                await asyncio.sleep(0.5)
                if tm.is_floor_free():
                    break
            # Extra buffer between agents
            await asyncio.sleep(1)

    # MULTI-AGENT: always schedule the kick-start briefing for all agents
    # if not single_voice_mode:
    asyncio.create_task(_kick_start_briefing())
    logger.info(
        f"Session {session_id} ready: {len(roster_entries)} agents, "
        f"'{scenario.get('crisis_title', 'Unknown')}' — kick-start briefing scheduled"
    )
    # else:
    #     logger.info(
    #         f"Session {session_id} ready: {len(roster_entries)} agents, "
    #         f"'{scenario.get('crisis_title', 'Unknown')}' — waiting for chairman input"
    #     )

    return session_id
