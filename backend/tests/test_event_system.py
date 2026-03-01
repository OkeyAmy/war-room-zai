"""
WAR ROOM — Test: Event System
Validates that push_event() generates the exact JSON structure
required by the Next.js frontend (matching Section 6 of the spec).
"""

import sys
import os
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


class TestPushEvent:
    """Tests for the push_event utility."""

    @pytest.mark.asyncio
    async def test_push_event_returns_event_id(self):
        """push_event should return a valid UUID event_id."""
        from utils.events import push_event

        event_id = await push_event("TEST001", "session_status", {
            "status": "assembling",
            "message": "Test event",
        })

        assert event_id is not None
        assert isinstance(event_id, str)
        assert len(event_id) > 0

    @pytest.mark.asyncio
    async def test_event_has_required_fields(self):
        """Every event must have: event_id, session_id, event_type, timestamp, payload."""
        from utils.firestore_helpers import _get_db
        from utils.events import push_event, get_session_events

        session_id = "TEST002"
        await push_event(session_id, "agent_thinking", {
            "agent_id": "legal_TEST002",
        })

        events = get_session_events(session_id)
        assert len(events) >= 1

        event = events[-1]
        assert "event_id" in event
        assert "session_id" in event
        assert event["session_id"] == session_id
        assert "event_type" in event
        assert event["event_type"] == "agent_thinking"
        assert "timestamp" in event
        assert "payload" in event
        assert event["consumed_by_frontend"] is False

    @pytest.mark.asyncio
    async def test_session_status_event_schema(self):
        """session_status events must have status and message."""
        from utils.events import push_event, get_session_events

        session_id = "TEST003"
        await push_event(session_id, "session_status", {
            "status": "assembling",
            "message": "Analyzing crisis scenario...",
        })

        events = get_session_events(session_id)
        event = events[-1]

        payload = event["payload"]
        assert "status" in payload
        assert payload["status"] == "assembling"
        assert "message" in payload

    @pytest.mark.asyncio
    async def test_agent_speaking_chunk_event_schema(self):
        """agent_speaking_chunk must have agent_id, transcript_chunk, audio_chunk_b64, is_final."""
        from utils.events import push_event, get_session_events

        session_id = "TEST004"
        await push_event(session_id, "agent_speaking_chunk", {
            "agent_id": "legal_TEST004",
            "transcript_chunk": "We need to address liability.",
            "audio_chunk_b64": "dGVzdA==",
            "is_final": False,
        })

        events = get_session_events(session_id)
        event = events[-1]

        payload = event["payload"]
        assert payload["agent_id"] == "legal_TEST004"
        assert payload["transcript_chunk"] == "We need to address liability."
        assert payload["audio_chunk_b64"] == "dGVzdA=="
        assert payload["is_final"] is False

    @pytest.mark.asyncio
    async def test_decision_agreed_event_schema(self):
        """decision_agreed events must match the frontend schema."""
        from utils.events import push_event, get_session_events

        session_id = "TEST005"
        await push_event(session_id, "decision_agreed", {
            "decision_id": "d001",
            "text": "Issue public statement within 2 hours",
            "agents_agreed": ["legal_TEST005", "pr_TEST005"],
            "proposed_by": "pr_TEST005",
            "agreed_at": "2024-01-01T12:00:00Z",
        })

        events = get_session_events(session_id)
        event = events[-1]

        payload = event["payload"]
        assert payload["decision_id"] == "d001"
        assert "text" in payload
        assert isinstance(payload["agents_agreed"], list)
        assert "proposed_by" in payload
        assert "agreed_at" in payload

    @pytest.mark.asyncio
    async def test_crisis_escalation_event_schema(self):
        """crisis_escalation events must trigger full-screen flash."""
        from utils.events import push_event, get_session_events

        session_id = "TEST006"
        await push_event(session_id, "crisis_escalation", {
            "event_id": "esc001",
            "text": "CNN Breaking: Major company confirms outage",
            "type": "media",
            "next_escalation_in_seconds": 300,
        })

        events = get_session_events(session_id)
        event = events[-1]

        payload = event["payload"]
        assert payload["event_id"] == "esc001"
        assert "text" in payload
        assert payload["type"] == "media"
        assert "next_escalation_in_seconds" in payload

    @pytest.mark.asyncio
    async def test_score_update_event_schema(self):
        """score_update events must include score, delta, history, and threat level."""
        from utils.events import push_event, get_session_events

        session_id = "TEST007"
        await push_event(session_id, "score_update", {
            "score": 42,
            "delta": -8,
            "score_history": [55, 50, 48, 42],
            "threat_level": "critical",
            "driver": "Media escalation",
        })

        events = get_session_events(session_id)
        event = events[-1]

        payload = event["payload"]
        assert payload["score"] == 42
        assert payload["delta"] == -8
        assert isinstance(payload["score_history"], list)
        assert payload["threat_level"] == "critical"
        assert "driver" in payload

    @pytest.mark.asyncio
    async def test_source_agent_id_propagated(self):
        """Events should carry the source agent ID."""
        from utils.events import push_event, get_session_events

        session_id = "TEST008"
        await push_event(
            session_id, "intel_dropped",
            {"intel_id": "i001", "text": "Test intel", "source": "LEGAL", "is_escalation": False},
            source_agent_id="legal_TEST008",
        )

        events = get_session_events(session_id)
        event = events[-1]

        assert event["source_agent_id"] == "legal_TEST008"
