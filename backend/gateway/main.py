"""
WAR ROOM — Gateway WebSocket Service
The single entry point. Frontend connects here via WebSocket.
Streams ALL events for a session to the frontend via direct queue.
Receives chairman audio/commands from the frontend.

Works in BOTH local dev and production:
- Events come from the shared asyncio.Queue (push_event / push_event_direct)
- No dependency on Firestore on_snapshot listeners
"""

from __future__ import annotations

import asyncio
import json
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from gateway.connection_manager import manager
from utils.events import get_event_queue, remove_event_queue

logger = logging.getLogger(__name__)

router = APIRouter()


@router.websocket("/ws/{session_id}")
async def war_room_websocket(websocket: WebSocket, session_id: str):
    """
    Frontend connects here once per session.
    Streams ALL events via the direct event queue (works in dev + prod).

    Two concurrent tasks:
    1. Forward events from the queue to WebSocket
    2. Receive chairman input from WebSocket (audio/commands)
    """
    await manager.connect(session_id, websocket)

    # Ensure the event queue exists for this session
    event_queue = get_event_queue(session_id)

    try:
        async def forward_events():
            """Read from the direct event queue and forward to WebSocket."""
            while True:
                event = await event_queue.get()
                try:
                    await websocket.send_json(event)
                except Exception as e:
                    logger.error(f"Failed to forward event: {e}")
                    break

        async def receive_chairman():
            """Receive and route chairman input from the WebSocket."""
            while True:
                try:
                    raw = await websocket.receive_text()
                    msg = json.loads(raw)

                    msg_type = msg.get("type", "")

                    if msg_type == "auth":
                        # Frontend sends auth token on connect
                        logger.info(
                            f"Chairman authenticated for session {session_id}"
                        )
                        # Send connection confirmation
                        await websocket.send_json({
                            "event_type": "connection_ready",
                            "session_id": session_id,
                            "payload": {"status": "connected"},
                        })

                    elif msg_type == "chairman_audio":
                        from gateway.chairman_handler import (
                            handle_chairman_audio,
                        )
                        await handle_chairman_audio(
                            session_id=session_id,
                            audio_b64=msg.get("audio", ""),
                            target_agent_id=msg.get("target_agent_id"),
                            transcript=msg.get("transcript", ""),
                        )

                    elif msg_type == "chairman_command" or msg_type == "command":
                        from gateway.chairman_handler import (
                            handle_chairman_command,
                        )
                        await handle_chairman_command(
                            session_id=session_id,
                            command=msg.get("command", ""),
                            params=msg.get("params", {}),
                        )

                    elif msg_type in {"chairman_speech", "lk_chat"}:
                        # Free-text from chairman or LiveKit chat topic payload
                        # -> route to active agent's voice/text pipeline.
                        from voice.pipeline import handle_chairman_text
                        text = msg.get("text", "")
                        if not text:
                            text = (msg.get("payload") or {}).get("text", "")
                        await handle_chairman_text(
                            session_id=session_id,
                            text=text,
                            target_agent_id=msg.get("target_agent_id"),
                        )

                    elif msg_type == "ping":
                        await websocket.send_json({"type": "pong"})

                    else:
                        logger.warning(f"Unknown message type: {msg_type}")

                except WebSocketDisconnect:
                    raise
                except json.JSONDecodeError as e:
                    logger.warning(f"Invalid JSON from chairman: {e}")
                except Exception as e:
                    logger.error(f"Error receiving chairman input: {e}")
                    break

        # Run both tasks concurrently
        await asyncio.gather(forward_events(), receive_chairman())

    except WebSocketDisconnect:
        logger.info(f"Chairman disconnected from session {session_id}")
    except Exception as e:
        logger.error(f"WebSocket error for session {session_id}: {e}")
    finally:
        manager.disconnect(session_id)
