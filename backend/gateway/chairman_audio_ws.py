"""
WAR ROOM — Chairman Audio WebSocket
API Section 14: WS /ws/{session_id}/audio

Dedicated WebSocket for streaming chairman microphone audio to agents.
Separate from the main event WebSocket to keep audio data out of event logs.

Flow:
  Frontend captures mic → PCM 16kHz 16-bit mono → base64 encode → send on WS
  Backend decodes → routes to target agent's Gemini Live session
  Agent responds → audio streamed via main event WS
"""

from __future__ import annotations

import json
import logging
import time

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from gateway.chairman_handler import get_agents, select_voice_agent

logger = logging.getLogger(__name__)

router = APIRouter()

# Track which agent the chairman is addressing per session
_audio_targets: dict[str, str | None] = {}


def set_audio_target(session_id: str, agent_id: str | None):
    """Set the target agent for chairman audio (called from command bar)."""
    _audio_targets[session_id] = agent_id


@router.websocket("/ws/{session_id}/audio")
async def chairman_audio_ws(websocket: WebSocket, session_id: str):
    """
    Chairman audio stream WebSocket.

    Frontend sends:
      - Binary frames: raw PCM audio bytes (16kHz, 16-bit, mono)
      - Text frames:   JSON control messages
        { "type": "set_target", "agent_id": "nova_A3F9B2C1" }
        { "type": "clear_target" }

    Server sends back:
      { "type": "vad_speech_start" }
      { "type": "vad_speech_end" }
      { "type": "transcript", "text": "..." }
      { "type": "routed_to", "agent_id": "..." }
    """
    await websocket.accept()
    logger.info(f"Chairman audio WS connected for session {session_id}")

    target_agent_id: str | None = None
    last_interrupt_at = 0.0
    try:
        while True:
            # Check if WebSocket is still connected before trying to receive
            if websocket.client_state.name != "CONNECTED":
                logger.info(
                    f"Chairman audio WS no longer connected for session {session_id}"
                )
                break

            try:
                msg = await websocket.receive()
            except RuntimeError as e:
                # "Cannot call receive once a disconnect message has been received"
                logger.debug(f"Chairman audio WS receive ended: {e}")
                break

            # Handle disconnect message type from ASGI
            if msg.get("type") == "websocket.disconnect":
                break

            if "text" in msg:
                # Control message
                try:
                    data = json.loads(msg["text"])
                    msg_type = data.get("type", "")

                    if msg_type == "set_target":
                        target_agent_id = data.get("agent_id")
                        _audio_targets[session_id] = target_agent_id
                        await websocket.send_json({
                            "type": "routed_to",
                            "agent_id": target_agent_id,
                        })
                        logger.info(
                            f"Chairman audio target set to: {target_agent_id}"
                        )

                    elif msg_type == "clear_target":
                        target_agent_id = None
                        _audio_targets[session_id] = None

                    elif msg_type == "ping":
                        await websocket.send_json({"type": "pong"})

                except json.JSONDecodeError:
                    continue

            elif "bytes" in msg:
                # Raw PCM audio data from chairman mic
                audio_bytes = msg["bytes"]

                agents = get_agents(session_id)
                if not agents:
                    continue

                # Chairman must be able to interrupt any active speaker mid-sentence.
                # Throttle interrupt signals to avoid flooding.
                now = time.monotonic()
                if now - last_interrupt_at > 0.25:
                    try:
                        from utils.turn_manager import get_turn_manager
                        from utils.events import push_event

                        tm = get_turn_manager(session_id)
                        await tm.chairman_interrupt()
                        await push_event(session_id, "chairman_taking_floor", {
                            "target_agent_id": target_agent_id,
                        })
                    except Exception as e:
                        logger.debug(f"Chairman interrupt signal failed: {e}")
                    last_interrupt_at = now

                # Use set target, otherwise route to session active speaker.
                effective_target = target_agent_id or _audio_targets.get(session_id)
                agent = select_voice_agent(session_id, effective_target)
                if agent and agent.live_session:
                    await agent.send_audio(audio_bytes)

    except WebSocketDisconnect:
        logger.info(f"Chairman audio WS disconnected for session {session_id}")
    except Exception as e:
        logger.error(f"Chairman audio WS error: {e}")
    finally:
        _audio_targets.pop(session_id, None)
