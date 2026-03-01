"""
WAR ROOM — Event Publishing Tools
ADK function tools for agents to publish events to the frontend.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


async def publish_room_event(
    session_id: str,
    agent_id: str,
    event_type: str,
    payload: dict,
) -> dict:
    """
    Publish an event to the room that the frontend will display.
    Use this for status updates, feed items, or other notifications.

    Args:
        session_id: The current crisis session ID.
        agent_id: Your agent ID (event source).
        event_type: The type of event. One of:
            - "feed_item": Post to the Crisis Feed
            - "agent_status_change": Update your status in the roster
        payload: Event-specific data. See event type definitions.

    Returns:
        dict with the event_id.
    """
    from utils.events import push_event

    event_id = await push_event(
        session_id=session_id,
        event_type=event_type,
        payload=payload,
        source_agent_id=agent_id,
    )

    logger.info(f"Agent {agent_id} published {event_type}: {event_id}")
    return {"event_id": event_id, "status": "published"}
