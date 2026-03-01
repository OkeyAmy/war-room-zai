"""
WAR ROOM — Voice Pipeline
Handles audio flow between chairman, agents, and the Gemini Live API.
Streams audio directly to frontend via WebSocket (bypasses Firestore).
Handles interruptions (barge-in), turn completion, and Observer feed.
"""

from __future__ import annotations

import asyncio
import base64
import logging
from datetime import datetime, timezone

from config.constants import (
    EVENT_AGENT_THINKING,
    EVENT_AGENT_SPEAKING_START,
    EVENT_AGENT_SPEAKING_CHUNK,
    EVENT_AGENT_SPEAKING_END,
    EVENT_AGENT_INTERRUPTED,
    EVENT_AGENT_STATUS_CHANGE,
)

logger = logging.getLogger(__name__)


async def handle_agent_live_response(
    agent,  # CrisisAgent instance
    session_id: str,
    observer_agent=None,  # ObserverAgent instance
) -> str:
    """
    Runs as a background task for each agent.
    Consumes the agent's Live API response stream.
    Forwards audio DIRECTLY via WS queue (no Firestore for audio).
    Pushes status events via push_event (persisted).
    Feeds transcript to Observer Agent.

    TURN MANAGEMENT: Acquires the floor from TurnManager before emitting
    the first audio chunk. Releases on turn_complete or interruption.
    This path was previously ungated — chairman responses went straight
    to the frontend, causing voice overlap.

    Returns the full transcript string.
    """
    from utils.events import push_event, push_event_direct
    from utils.turn_manager import get_turn_manager

    if not agent.live_session:
        logger.warning(f"No live session for agent {agent.agent_id} — skipping")
        return ""

    # Signal thinking state
    await push_event(session_id, EVENT_AGENT_THINKING, {
        "agent_id": agent.agent_id,
    })

    tm = get_turn_manager(session_id)
    holding_turn = False
    full_transcript = ""
    audio_chunk_count = 0

    try:
        async for response in agent.live_session.receive():

            # ── CHECK YIELD (turn manager) ────────────────────────────
            if (
                holding_turn
                and tm.should_yield(agent.agent_id)
            ):
                logger.info(f"Agent {agent.agent_id} yielding floor (pipeline)")
                tm.release_turn(agent.agent_id)
                holding_turn = False
                await push_event(session_id, EVENT_AGENT_INTERRUPTED, {
                    "agent_id": agent.agent_id,
                })
                await push_event(session_id, EVENT_AGENT_STATUS_CHANGE, {
                    "agent_id": agent.agent_id,
                    "status": "listening",
                })
                break

            # ── INTERRUPTED ──────────────────────────────────────────
            if (
                response.server_content
                and response.server_content.interrupted
            ):
                if holding_turn:
                    tm.release_turn(agent.agent_id)
                    holding_turn = False
                await push_event(session_id, EVENT_AGENT_INTERRUPTED, {
                    "agent_id": agent.agent_id,
                    "interrupted_by": "chairman",
                })
                await push_event(session_id, EVENT_AGENT_STATUS_CHANGE, {
                    "agent_id": agent.agent_id,
                    "status": "listening",
                    "previous_status": "speaking",
                })
                logger.info(f"Agent {agent.agent_id} interrupted")
                break

            # ── AUDIO CHUNK ──────────────────────────────────────────
            if response.data:
                audio_b64 = base64.b64encode(response.data).decode()
                audio_chunk_count += 1

                # First chunk → acquire the floor from TurnManager
                if audio_chunk_count == 1:
                    acquired = await tm.try_acquire_turn(agent.agent_id)
                    if not acquired:
                        logger.info(
                            f"Agent {agent.agent_id} could not acquire floor "
                            "(pipeline) — dropping response"
                        )
                        break
                    holding_turn = True

                    await push_event(session_id, EVENT_AGENT_SPEAKING_START, {
                        "agent_id": agent.agent_id,
                        "character_name": agent.role_config.get(
                            "character_name", "Agent"
                        ),
                    })
                    await push_event(session_id, EVENT_AGENT_STATUS_CHANGE, {
                        "agent_id": agent.agent_id,
                        "status": "speaking",
                        "previous_status": "thinking",
                    })

                # Push audio DIRECTLY — skip Firestore (too slow for audio)
                # FIELD NAME: 'audio_b64' matches frontend useWarRoomSocket
                await push_event_direct(
                    session_id,
                    "agent_audio_chunk",
                    {
                        "agent_id": agent.agent_id,
                        "audio_b64": audio_b64,
                        "sample_rate": 24000,
                        "channels": 1,
                        "bit_depth": 16,
                    },
                    source_agent_id=agent.agent_id,
                )

            # ── TEXT TRANSCRIPT (side channel) ────────────────────────
            if (
                response.server_content
                and response.server_content.output_transcription
            ):
                chunk = response.server_content.output_transcription.text
                full_transcript += chunk

                # Transcript chunks go via direct push (low latency)
                await push_event_direct(
                    session_id,
                    EVENT_AGENT_SPEAKING_CHUNK,
                    {
                        "agent_id": agent.agent_id,
                        "transcript_chunk": chunk,
                    },
                    source_agent_id=agent.agent_id,
                )

            # ── TURN COMPLETE ─────────────────────────────────────────
            if (
                response.server_content
                and response.server_content.turn_complete
            ):
                # Release the floor
                if holding_turn:
                    tm.release_turn(agent.agent_id)
                    holding_turn = False

                await push_event(session_id, EVENT_AGENT_SPEAKING_END, {
                    "agent_id": agent.agent_id,
                    "full_transcript": full_transcript,
                })
                await push_event(session_id, EVENT_AGENT_STATUS_CHANGE, {
                    "agent_id": agent.agent_id,
                    "status": "idle",
                    "previous_status": "speaking",
                })

                # Feed to Observer Agent for analysis
                if observer_agent and full_transcript:
                    try:
                        await observer_agent.analyze_statement(
                            session_id=session_id,
                            agent_id=agent.agent_id,
                            transcript=full_transcript,
                        )
                    except Exception as e:
                        logger.warning(
                            f"Observer analysis failed for {agent.agent_id}: {e}"
                        )

                # Store in agent's private memory
                try:
                    await agent.memory_ref.update({
                        "previous_statements": [{
                            "text": full_transcript,
                            "timestamp": datetime.now(timezone.utc).isoformat(),
                        }],
                    })
                except Exception as e:
                    logger.warning(
                        f"Failed to store transcript for {agent.agent_id}: {e}"
                    )

                break

    except Exception as e:
        if holding_turn:
            tm.release_turn(agent.agent_id)
        logger.error(f"Error in live response handler for {agent.agent_id}: {e}")
        await push_event(session_id, EVENT_AGENT_STATUS_CHANGE, {
            "agent_id": agent.agent_id,
            "status": "idle",
            "previous_status": "speaking",
        })

    logger.info(
        f"Agent {agent.agent_id} finished speaking: "
        f"{audio_chunk_count} audio chunks, "
        f"{len(full_transcript)} chars transcript"
    )
    return full_transcript


async def route_audio_to_agent(
    agent,  # CrisisAgent instance
    audio_data: bytes,
):
    """
    Route chairman audio to a specific agent's Live session.
    The Live API's VAD will detect speech start/end.
    """
    if agent.live_session:
        logger.info(
            f"[VOICE_ROUTE] session={agent.session_id} target={agent.agent_id} "
            f"{agent.voice_runtime_summary()}"
        )
        await agent.send_audio(audio_data)
    else:
        logger.warning(f"Cannot route audio — {agent.agent_id} has no live session")


async def route_text_to_agent(
    agent,  # CrisisAgent instance
    text: str,
):
    """
    Route text to a specific agent's Live session.
    Used for agent-to-agent discussion prompts.
    """
    if agent.live_session:
        await agent.send_text(text)
    else:
        logger.warning(f"Cannot route text — {agent.agent_id} has no live session")


async def handle_chairman_text(
    session_id: str,
    text: str,
    target_agent_id: str | None = None,
) -> None:
    """
    Route chairman free-text to agent(s) via their Gemini Live sessions.

    Per voice.md §1.6 and api_backend.md §11:
      Chairman text → agent.send_text() → Gemini processes → agent responds in voice.

    The agent's persistent _receive_from_gemini() loop handles the response.

    Args:
        session_id: The crisis session ID.
        text: Chairman's text message.
        target_agent_id: Specific agent to address, or None for broadcast.
    """
    from gateway.chairman_handler import get_agents, select_voice_agent
    from config.settings import get_settings
    from utils.events import push_event
    from utils.turn_manager import get_turn_manager

    agents = get_agents(session_id)
    if not agents:
        logger.warning(f"No agents registered for session {session_id}")
        return

    # Chairman has priority — interrupt current speaker
    tm = get_turn_manager(session_id)
    if not tm.is_floor_free():
        await tm.chairman_interrupt()

    # Push chairman_spoke event to frontend
    await push_event(session_id, "chairman_spoke", {
        "text": text,
        "target_agent_id": target_agent_id,
        "command_type": "question",
    })

    routed_to = []

    settings = get_settings()
    # MULTI-AGENT: commented out single_agent_voice_mode — route to target or broadcast
    if target_agent_id:  # or settings.single_agent_voice_mode:
        # Direct address: route to exactly one selected agent.
        agent = select_voice_agent(session_id, target_agent_id)
        if not agent:
            logger.warning(
                f"No live voice agent available for session {session_id} "
                f"(target={target_agent_id})"
            )
            return

        char = getattr(agent, "role_config", {}).get("character_name", "Agent")
        await agent.send_text(
            f'The Chairman says to you, {char}: "{text}"\n\n'
            "Respond directly and concisely, then challenge one relevant claim "
            "from another agent if needed."
        )
        routed_to.append(getattr(agent, "agent_id", target_agent_id))
    else:
        # Room-wide address: fan out to all live agents, one-by-one.
        # This preserves turn order while ensuring everyone receives the prompt.
        live_agents = [a for _, a in agents.items() if getattr(a, "live_session", None)]
        if not live_agents:
            logger.warning(f"No live agents available for room-wide routing in {session_id}")
            return

        for agent in live_agents:
            char = getattr(agent, "role_config", {}).get("character_name", "Agent")
            await agent.send_text(
                f'The Chairman addresses the room: "{text}"\n\n'
                f"As {char}, respond in 2-4 sentences. Reference another agent's "
                "position and either challenge it or reinforce it."
            )
            routed_to.append(getattr(agent, "agent_id", "unknown"))

            # Let the current response finish before prompting the next agent.
            for _ in range(80):
                await asyncio.sleep(0.25)
                if tm.is_floor_free():
                    break

    logger.info(
        f"Chairman text routed to {len(routed_to)} agent(s) in session {session_id}"
    )
