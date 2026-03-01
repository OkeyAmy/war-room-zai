"""
WAR ROOM — Test: Crisis Board Tools
Tests the tool-calling logic for reading/writing the Crisis Board.
"""

import sys
import os
import pytest
import pytest_asyncio

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


@pytest_asyncio.fixture
async def setup_crisis_session():
    """Set up a mock crisis session in the in-memory store."""
    from utils.firestore_helpers import _get_db
    from config.constants import COLLECTION_CRISIS_SESSIONS

    db = _get_db()

    await db.collection(COLLECTION_CRISIS_SESSIONS).document("TEST_CB").set({
        "session_id": "TEST_CB",
        "crisis_title": "Test Crisis",
        "crisis_brief": "A test crisis for board tools.",
        "status": "active",
        "agreed_decisions": [],
        "open_conflicts": [],
        "critical_intel": [],
        "posture": {
            "public_exposure": 60,
            "legal_exposure": 45,
            "internal_stability": 50,
            "public_trend": "rising",
            "legal_trend": "stable",
            "internal_trend": "stable",
        },
        "resolution_score": 55,
        "threat_level": "elevated",
        "escalation_events": [],
        "agent_roster": [],
    })
    return db


class TestReadCrisisBoard:
    """Tests for read_crisis_board tool."""

    @pytest.mark.asyncio
    async def test_read_returns_public_data(self, setup_crisis_session):
        """read_crisis_board should return all public crisis board data."""
        from tools.crisis_board_tools import read_crisis_board

        result = await read_crisis_board("TEST_CB", "legal_TEST_CB")

        assert result.get("crisis_title") == "Test Crisis"
        assert "agreed_decisions" in result
        assert "open_conflicts" in result
        assert "critical_intel" in result
        assert "posture" in result
        assert "resolution_score" in result
        assert "threat_level" in result

    @pytest.mark.asyncio
    async def test_read_nonexistent_session(self):
        """read_crisis_board should return error for nonexistent sessions."""
        from tools.crisis_board_tools import read_crisis_board

        result = await read_crisis_board("NONEXISTENT", "agent_X")
        assert "error" in result


class TestWriteAgreedDecision:
    """Tests for write_agreed_decision tool."""

    @pytest.mark.asyncio
    async def test_write_decision_returns_id(self, setup_crisis_session):
        """write_agreed_decision should return a decision_id."""
        from tools.crisis_board_tools import write_agreed_decision

        result = await write_agreed_decision(
            session_id="TEST_CB",
            agent_id="pr_TEST_CB",
            text="Issue immediate public statement",
            agents_agreed=["pr_TEST_CB", "legal_TEST_CB"],
        )

        assert "decision_id" in result
        assert result["status"] == "recorded"


class TestWriteOpenConflict:
    """Tests for write_open_conflict tool."""

    @pytest.mark.asyncio
    async def test_write_conflict_returns_id(self, setup_crisis_session):
        """write_open_conflict should return a conflict_id."""
        from tools.crisis_board_tools import write_open_conflict

        result = await write_open_conflict(
            session_id="TEST_CB",
            agent_id="legal_TEST_CB",
            description="Disagree on timeline for public disclosure",
            agents_involved=["legal_TEST_CB", "pr_TEST_CB"],
            severity="high",
        )

        assert "conflict_id" in result
        assert result["status"] == "recorded"


class TestWriteCriticalIntel:
    """Tests for write_critical_intel tool."""

    @pytest.mark.asyncio
    async def test_write_intel_returns_id(self, setup_crisis_session):
        """write_critical_intel should return an intel_id."""
        from tools.crisis_board_tools import write_critical_intel

        result = await write_critical_intel(
            session_id="TEST_CB",
            agent_id="legal_TEST_CB",
            text="Compliance warning was issued 3 months ago",
            source="LEGAL",
            is_escalation=False,
        )

        assert "intel_id" in result
        assert result["status"] == "recorded"

    @pytest.mark.asyncio
    async def test_intel_source_uppercased(self, setup_crisis_session):
        """Intel source should be uppercased."""
        from tools.crisis_board_tools import write_critical_intel

        result = await write_critical_intel(
            session_id="TEST_CB",
            agent_id="legal_TEST_CB",
            text="Test intel",
            source="legal",
        )

        assert result["status"] == "recorded"
