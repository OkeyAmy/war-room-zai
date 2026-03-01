"""
WAR ROOM — World Agent (Escalation Engine)
Timer-based. Fires escalation events at scheduled intervals.
Also generates reactive feed items in response to crisis progression.
"""

from __future__ import annotations

import asyncio
import uuid
import logging
from datetime import datetime, timezone

from config.constants import (
    COLLECTION_CRISIS_SESSIONS,
    EVENT_CRISIS_ESCALATION,
    EVENT_FEED_ITEM,
)
from config.settings import get_settings

logger = logging.getLogger(__name__)

# ── SYSTEM INSTRUCTION ───────────────────────────────────────────────────

WORLD_AGENT_INSTRUCTION = """
You are the World Agent in WAR ROOM. You represent external forces.
You have NO memory of agent statements. You only know the crisis scenario.

Your job: generate realistic world events that escalate the crisis.
These are external pressures — media, legal, social, operational.

You fire events on a schedule. Each event should:
1. Increase pressure on the team
2. Be specific and realistic
3. Reference real-world mechanisms (lawsuits, press conferences, stock drops)
4. Force agents to react and potentially change their positions

You do NOT participate in discussions. You are the environment.
"""


class WorldAgent:
    """
    Timer-based escalation engine. Fires scheduled crisis events
    that create external pressure on the agent team.
    NO memory of agent statements — only reads crisis scenario.
    """

    def __init__(
        self,
        session_id: str,
        escalation_schedule: list[dict],
    ):
        self.session_id = session_id
        self.escalation_schedule = escalation_schedule
        self._tasks: list[asyncio.Task] = []

        # Firestore client
        self._db = None

        # Optional LLM for dynamic event generation
        self.llm = None

    @property
    def db(self):
        if self._db is None:
            from utils.firestore_helpers import _get_db
            self._db = _get_db()
        return self._db

    async def start_timer(self):
        """Schedule escalation events as asyncio tasks."""
        for event in self.escalation_schedule:
            delay = event["delay_minutes"] * 60
            task = asyncio.create_task(
                self._fire_escalation(delay, event)
            )
            self._tasks.append(task)

        logger.info(
            f"World Agent scheduled {len(self.escalation_schedule)} "
            f"escalations for session {self.session_id}"
        )

    async def _fire_escalation(self, delay_seconds: float, event: dict):
        """Fire a single escalation event after a delay."""
        from utils.events import push_event
        from utils.firestore_helpers import (
            update_resolution_score,
            check_threat_level,
            broadcast_to_agents,
        )

        await asyncio.sleep(delay_seconds)

        event_id = str(uuid.uuid4())
        timestamp = datetime.now(timezone.utc).isoformat()

        # Write to crisis board intel
        try:
            from google.cloud import firestore as fs
            await self.db.collection(COLLECTION_CRISIS_SESSIONS) \
                         .document(self.session_id) \
                         .update({
                             "critical_intel": fs.ArrayUnion([{
                                 "intel_id": event_id,
                                 "text": event["event_text"],
                                 "source": event["type"].upper(),
                                 "timestamp": timestamp,
                                 "is_escalation": True,
                             }])
                         })
        except ImportError:
            logger.debug("Firestore ArrayUnion unavailable — skipping intel write")

        # Push escalation event (triggers full-screen flash on frontend)
        await push_event(self.session_id, EVENT_CRISIS_ESCALATION, {
            "event_id": event_id,
            "text": event["event_text"],
            "type": event["type"],
            "next_escalation_in_seconds": 0,
        }, source_agent_id="world")

        # Push as feed item
        await push_event(self.session_id, EVENT_FEED_ITEM, {
            "feed_id": str(uuid.uuid4()),
            "text": event["event_text"],
            "source_name": "📡 WORLD FEED",
            "source_type": event["type"].upper(),
            "metric": "⚡ CRISIS ESCALATION · just now",
            "is_hot": True,
        }, source_agent_id="world")

        # Update resolution score negatively
        settings = get_settings()
        await update_resolution_score(
            self.session_id,
            settings.escalation_score_penalty,
            f"Escalation: {event['event_text'][:40]}...",
        )

        # Check if threat level changed
        await check_threat_level(self.session_id)

        # Notify all agents so they react
        await broadcast_to_agents(self.session_id, {
            "type": "world_escalation",
            "event_text": event["event_text"],
            "event_type": event["type"],
        })

        logger.info(
            f"Escalation fired for session {self.session_id}: "
            f"{event['event_text'][:50]}..."
        )

    async def cancel(self):
        """Cancel all pending escalation tasks."""
        for task in self._tasks:
            if not task.done():
                task.cancel()
        self._tasks.clear()
        logger.info(f"World Agent cancelled for session {self.session_id}")
