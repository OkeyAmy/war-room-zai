"""
WAR ROOM — WebSocket Connection Manager
Manages active WebSocket connections per session.
"""

from __future__ import annotations

import logging
from typing import Optional
from fastapi import WebSocket

logger = logging.getLogger(__name__)


class ConnectionManager:
    """
    Manages WebSocket connections for the Gateway.
    One WebSocket per session (frontend client).
    """

    def __init__(self):
        self._connections: dict[str, WebSocket] = {}

    async def connect(self, session_id: str, websocket: WebSocket) -> None:
        """Accept and register a WebSocket connection for a session."""
        existing = self._connections.get(session_id)
        if existing and existing is not websocket:
            try:
                await existing.close(code=1000)
            except Exception:
                pass
        await websocket.accept()
        self._connections[session_id] = websocket
        logger.info(f"WebSocket connected for session {session_id}")

    def disconnect(self, session_id: str) -> None:
        """Remove a WebSocket connection."""
        if session_id in self._connections:
            del self._connections[session_id]
            logger.info(f"WebSocket disconnected for session {session_id}")

    def get(self, session_id: str) -> Optional[WebSocket]:
        """Get the WebSocket for a session."""
        return self._connections.get(session_id)

    async def send_event(self, session_id: str, event: dict) -> bool:
        """
        Send an event to the frontend via WebSocket.
        Returns True if sent, False if no connection.
        """
        ws = self._connections.get(session_id)
        if ws:
            try:
                await ws.send_json(event)
                return True
            except Exception as e:
                logger.warning(f"Failed to send event to {session_id}: {e}")
                self.disconnect(session_id)
        return False

    @property
    def active_sessions(self) -> list[str]:
        """List all session IDs with active connections."""
        return list(self._connections.keys())


# Singleton instance
manager = ConnectionManager()
