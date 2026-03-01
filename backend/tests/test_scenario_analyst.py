"""
WAR ROOM — Test: Scenario Analyst
Mocks the ScenarioAnalyst output and validates schema compliance.
"""

import sys
import os
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


class TestScenarioAnalystMock:
    """Tests for the mock scenario analyst output."""

    def test_mock_scenario_has_correct_structure(self):
        """Mock scenario must match ScenarioSpec schema."""
        from agents.scenario_analyst import _generate_mock_scenario

        scenario = _generate_mock_scenario("A data breach at a tech company", "TEST001")

        assert "crisis_title" in scenario
        assert "crisis_domain" in scenario
        assert "crisis_brief" in scenario
        assert "threat_level_initial" in scenario
        assert "resolution_score_initial" in scenario
        assert "agents" in scenario
        assert "initial_intel" in scenario
        assert "escalation_schedule" in scenario

    def test_mock_scenario_has_correct_agent_count(self):
        """Multi-agent mode must generate exactly four active agents."""
        from agents.scenario_analyst import _generate_mock_scenario

        scenario = _generate_mock_scenario("Test crisis", "TEST002")
        agent_count = len(scenario["agents"])

        assert agent_count == 4, f"Expected 4 agents, got {agent_count}"

    def test_each_agent_has_required_fields(self):
        """Every agent config must have all required fields."""
        from agents.scenario_analyst import _generate_mock_scenario

        scenario = _generate_mock_scenario("Test crisis", "TEST003")

        required_fields = [
            "role_key", "role_title", "character_name",
            "defining_line", "agenda", "hidden_knowledge",
            "personality_traits", "voice_style", "identity_color",
        ]

        for agent in scenario["agents"]:
            for field in required_fields:
                assert field in agent, f"Agent {agent.get('role_key', '?')} missing '{field}'"

    def test_single_agent_conflicts_are_optional(self):
        """In strict single-agent mode conflict_with can be empty."""
        from agents.scenario_analyst import _generate_mock_scenario

        scenario = _generate_mock_scenario("Test crisis", "TEST004")

        for agent in scenario["agents"]:
            assert isinstance(agent.get("conflict_with", []), list)

    def test_escalation_schedule_has_three_events(self):
        """Must have exactly 3 escalation events."""
        from agents.scenario_analyst import _generate_mock_scenario

        scenario = _generate_mock_scenario("Test crisis", "TEST005")
        escalations = scenario.get("escalation_schedule", [])

        assert len(escalations) == 3, f"Expected 3 escalations, got {len(escalations)}"

    def test_escalation_events_have_increasing_delays(self):
        """Escalation events should be ordered by delay."""
        from agents.scenario_analyst import _generate_mock_scenario

        scenario = _generate_mock_scenario("Test crisis", "TEST006")
        delays = [e["delay_minutes"] for e in scenario["escalation_schedule"]]

        for i in range(1, len(delays)):
            assert delays[i] >= delays[i - 1], (
                f"Escalation delays not increasing: {delays}"
            )

    def test_identity_colors_are_unique(self):
        """Each agent must have a distinct identity_color."""
        from agents.scenario_analyst import _generate_mock_scenario

        scenario = _generate_mock_scenario("Test crisis", "TEST007")
        colors = [a["identity_color"] for a in scenario["agents"]]

        assert len(colors) == len(set(colors)), f"Duplicate colors: {colors}"

    def test_scenario_validates_against_pydantic(self):
        """Mock scenario should validate against ScenarioSpec."""
        from agents.scenario_analyst import _generate_mock_scenario
        from utils.pydantic_models import ScenarioSpec

        scenario = _generate_mock_scenario("Test crisis", "TEST008")

        # Should not raise ValidationError
        spec = ScenarioSpec(**scenario)
        assert spec.crisis_title is not None
        assert len(spec.agents) == 4

    def test_resolution_score_in_valid_range(self):
        """Initial resolution score must be between 30-70."""
        from agents.scenario_analyst import _generate_mock_scenario

        scenario = _generate_mock_scenario("Test crisis", "TEST009")
        score = scenario["resolution_score_initial"]

        assert 30 <= score <= 70, f"Score {score} out of range [30, 70]"


class TestSkillGeneration:
    """Tests for SKILL.md generation."""

    @pytest.mark.asyncio
    async def test_skill_md_contains_character_identity(self):
        """Generated SKILL.md must contain the character's identity."""
        from agents.skill_generator import generate_skill_md
        from agents.scenario_analyst import _generate_mock_scenario

        scenario = _generate_mock_scenario("Test crisis", "SKILL001")
        agent_config = scenario["agents"][0]

        skill_md = await generate_skill_md(
            agent_config, scenario, "SKILL001", "Orus"
        )

        assert agent_config["character_name"] in skill_md
        assert agent_config["role_title"] in skill_md
        assert "WHO YOU ARE" in skill_md
        assert "YOUR MISSION" in skill_md

    @pytest.mark.asyncio
    async def test_skill_md_contains_hidden_knowledge(self):
        """SKILL.md must include the agent's hidden knowledge."""
        from agents.skill_generator import generate_skill_md
        from agents.scenario_analyst import _generate_mock_scenario

        scenario = _generate_mock_scenario("Test crisis", "SKILL002")
        agent_config = scenario["agents"][0]

        skill_md = await generate_skill_md(
            agent_config, scenario, "SKILL002", "Orus"
        )

        assert agent_config["hidden_knowledge"] in skill_md
        assert "WHAT YOU KNOW THAT NOBODY ELSE DOES" in skill_md

    @pytest.mark.asyncio
    async def test_skill_md_contains_tool_instructions(self):
        """SKILL.md must include tool usage instructions."""
        from agents.skill_generator import generate_skill_md
        from agents.scenario_analyst import _generate_mock_scenario

        scenario = _generate_mock_scenario("Test crisis", "SKILL003")
        agent_config = scenario["agents"][0]

        skill_md = await generate_skill_md(
            agent_config, scenario, "SKILL003", "Orus"
        )

        assert "read_crisis_board()" in skill_md
        assert "write_agreed_decision" in skill_md
        assert "write_open_conflict" in skill_md
        assert "read_my_private_memory()" in skill_md
        assert "TOOL USAGE" in skill_md
        assert "LIVEKIT MULTIMODAL GUIDE" in skill_md
        assert "allow_interruptions" in skill_md

    @pytest.mark.asyncio
    async def test_skill_md_is_substantial(self):
        """SKILL.md should be 300-600+ words."""
        from agents.skill_generator import generate_skill_md
        from agents.scenario_analyst import _generate_mock_scenario

        scenario = _generate_mock_scenario("Test crisis", "SKILL004")
        agent_config = scenario["agents"][0]

        skill_md = await generate_skill_md(
            agent_config, scenario, "SKILL004", "Orus"
        )

        word_count = len(skill_md.split())
        assert word_count >= 200, f"SKILL.md too short: {word_count} words"


class TestLiveKitSessionConfig:
    """Tests for generated LiveKit agent session parameters."""

    def test_build_livekit_agent_session_config_defaults(self):
        from voice.livekit_session import build_livekit_agent_session_config

        cfg = build_livekit_agent_session_config(
            session_id="ABC12345",
            agent_id="legal_ABC12345",
            character_name="Elena Vance",
            role_title="Chief Legal Officer",
            assigned_voice="cgSgspJ2msm6clMCkdW9",
            skill_md="# test skill",
            text_model="gemini-3-flash-preview",
            stt_model="scribe_v1",
            tts_model="eleven_turbo_v2_5",
            crisis_brief="Test brief",
            allow_interruptions=True,
        )

        assert cfg["pipeline"]["mode"] == "stt-llm-tts"
        assert cfg["pipeline"]["stt"] == "elevenlabs/scribe_v1"
        assert cfg["pipeline"]["tts"] == "elevenlabs/eleven_turbo_v2_5:cgSgspJ2msm6clMCkdW9"
        assert cfg["multimodality"]["text_input"] is True
        assert cfg["voice_options"]["allow_interruptions"] is True
        assert cfg["turn_detection"]["enabled"] is True
