"""
WAR ROOM — Scenario Analyst Agent
Runs ONCE at session start. Analyzes the crisis input and outputs
a complete ScenarioSpec JSON that initializes the entire crisis team.
"""

from __future__ import annotations

import json
import logging
from typing import Optional

from config.settings import get_settings
from utils.pydantic_models import ScenarioSpec

logger = logging.getLogger(__name__)

# ── SYSTEM INSTRUCTION ───────────────────────────────────────────────────

SCENARIO_ANALYST_INSTRUCTION = """
You are the Scenario Analyst for WAR ROOM. You run ONCE at session start.
Your job: analyze the crisis input and output a complete JSON specification
that will be used to initialize the entire crisis team.

CRISIS INPUT: {crisis_input}

You must output a valid JSON object with this exact structure:
{{
  "crisis_title": "Short dramatic title (max 8 words)",
  "crisis_domain": "corporate|military|medical|political|fantasy|other",
  "crisis_brief": "2-3 sentence classified-style intelligence brief",
  "threat_level_initial": "contained|elevated|critical",
  "resolution_score_initial": <number between 30-70>,
  "agents": [
    {{
      "role_key": "legal|pr|engineer|finance|ops|comms|strategy|[custom]",
      "role_title": "Exact job title",
      "character_name": "Full name (diverse, realistic)",
      "defining_line": "First thing they say when entering. Reveals agenda.",
      "agenda": "What they WANT to achieve in this crisis",
      "hidden_knowledge": "One fact they know that others don't.",
      "personality_traits": ["trait1", "trait2", "trait3"],
      "conflict_with": ["role_key_of_agent_they_clash_with"],
      "voice_style": "authoritative|warm|clipped|measured|urgent|calm|aggressive",
      "identity_color": "#hexcode that fits their personality"
    }}
  ],
  "initial_intel": [
    {{ "text": "Opening intel item", "source": "WORLD|MEDIA|LEGAL|INTERNAL|SOCIAL" }}
  ],
  "initial_conflicts": [
    {{ "description": "Conflict that exists from the start", "agents_involved": ["role_key1", "role_key2"] }}
  ],
  "escalation_schedule": [
    {{ "delay_minutes": 5, "event_text": "...", "type": "media|legal|internal|social|operational" }},
    {{ "delay_minutes": 10, "event_text": "...", "type": "..." }},
    {{ "delay_minutes": 18, "event_text": "...", "type": "..." }}
  ]
}}

Rules:
- Generate exactly 4 agents, each with a distinct role, personality, and agenda.
- Each agent will run in its own independent LiveKit pod with a unique room.
- The hidden_knowledge for each agent must eventually become relevant.
- At least 2 agents must have conflict_with entries pointing at each other.
- escalation_schedule must have exactly 3 events spaced across the session.
- voice_style guides which ElevenLabs voices to assign. Each agent MUST have a different voice_style.
- Each agent must be suitable for LiveKit multimodal runtime:
  - accepts both spoken and typed chairman input
  - handles interruptions naturally
  - can introduce itself in one short opening turn
- Output ONLY the JSON object. No explanatory text.
"""


async def run_scenario_analyst(
    crisis_input: str,
    session_id: str,
) -> dict:
    """
    Runs the Scenario Analyst agent ONCE.
    Returns the full scenario spec as a Python dict.

    Args:
        crisis_input: The raw crisis description from the chairman.
        session_id: The session being bootstrapped.

    Returns:
        dict matching the ScenarioSpec schema.
    """
    settings = get_settings()

    try:
        from google.adk.agents import LlmAgent
        from google.adk.runners import Runner
        from google.adk.sessions import InMemorySessionService
        from google.genai import types

        session_service = InMemorySessionService()

        analyst = LlmAgent(
            name="ScenarioAnalyst",
            model=settings.text_model,
            instruction=SCENARIO_ANALYST_INSTRUCTION.format(
                crisis_input=crisis_input
            ),
            output_schema=ScenarioSpec,
        )

        runner = Runner(
            agent=analyst,
            app_name=f"analyst_{session_id}",
            session_service=session_service,
        )

        # Create the session in the InMemorySessionService BEFORE calling run_async.
        # Without this, the runner raises "Session not found".
        analyst_session_id = f"analyst_{session_id}"
        await session_service.create_session(
            app_name=f"analyst_{session_id}",
            user_id="system",
            session_id=analyst_session_id,
        )

        # runner.run_async() returns an AsyncGenerator of events, NOT an awaitable.
        # We iterate to capture the final response text.
        final_response_text = ""
        async for event in runner.run_async(
            user_id="system",
            session_id=analyst_session_id,
            new_message=types.Content(
                role="user",
                parts=[types.Part(text=f"Analyze this crisis: {crisis_input}")]
            ),
        ):
            if event.is_final_response() and event.content and event.content.parts:
                final_response_text = event.content.parts[0].text

        if not final_response_text:
            logger.warning("Scenario Analyst returned no final response — using mock")
            return _generate_mock_scenario(crisis_input, session_id)

        scenario = json.loads(final_response_text)
        # MULTI-AGENT: commented out single-agent truncation — now supports 4 agents
        # Hard guarantee: scenario bootstrap currently supports strict single-agent voice.
        # agents = scenario.get("agents", [])
        # if isinstance(agents, list):
        #     scenario["agents"] = agents[:1]
        logger.info(f"Scenario Analyst produced: {scenario.get('crisis_title', 'Unknown')}")
        return scenario

    except ImportError:
        logger.warning("Google ADK not available — returning mock scenario")
        return _generate_mock_scenario(crisis_input, session_id)


def _generate_mock_scenario(crisis_input: str, session_id: str) -> dict:
    """
    Generate a mock scenario for local development/testing
    when ADK is not available.
    MULTI-AGENT: expanded from 1 agent to 4 independent agents.
    """
    return {
        "crisis_title": "Critical Systems Failure",
        "crisis_domain": "corporate",
        "crisis_brief": (
            "CLASSIFIED — A major systems failure has been detected. "
            "Multiple stakeholders are affected. Immediate action required "
            "to prevent cascading failures across the organization."
        ),
        "threat_level_initial": "elevated",
        "resolution_score_initial": 55,
        "agents": [
            {
                "role_key": "legal",
                "role_title": "Chief Legal Officer",
                "character_name": "Alexandra Chen",
                "defining_line": "Before anyone says another word — we need to talk about liability.",
                "agenda": "Minimize legal exposure and ensure regulatory compliance.",
                "hidden_knowledge": "There was a compliance warning issued 3 months ago that was ignored.",
                "personality_traits": ["cautious", "analytical", "persistent"],
                "conflict_with": ["ops"],
                "voice_style": "authoritative",
                "identity_color": "#3B82F6",
            },
            {
                "role_key": "pr",
                "role_title": "VP of Communications",
                "character_name": "Marcus Rivera",
                "defining_line": "The media cycle waits for no one — we control the narrative or it controls us.",
                "agenda": "Shape public perception and protect brand reputation.",
                "hidden_knowledge": "A reporter at Reuters already has a draft story with insider quotes.",
                "personality_traits": ["charismatic", "strategic", "impatient"],
                "conflict_with": ["legal"],
                "voice_style": "warm",
                "identity_color": "#F59E0B",
            },
            {
                "role_key": "engineer",
                "role_title": "Chief Technology Officer",
                "character_name": "Priya Sharma",
                "defining_line": "I have the root-cause analysis. You're not going to like it.",
                "agenda": "Fix the technical failure and prevent recurrence.",
                "hidden_knowledge": "The failure originated from a cost-cutting decision she approved last quarter.",
                "personality_traits": ["direct", "technical", "defensive"],
                "conflict_with": ["finance"],
                "voice_style": "clipped",
                "identity_color": "#10B981",
            },
            {
                "role_key": "ops",
                "role_title": "Head of Operations",
                "character_name": "James O'Sullivan",
                "defining_line": "We need boots on the ground now — every minute is costing us.",
                "agenda": "Restore operational continuity at any cost.",
                "hidden_knowledge": "The backup systems were last tested 8 months ago and may not hold.",
                "personality_traits": ["aggressive", "decisive", "blunt"],
                "conflict_with": ["legal"],
                "voice_style": "urgent",
                "identity_color": "#EF4444",
            },
        ],
        "initial_intel": [
            {"text": "Systems monitoring detected anomalous behavior 47 minutes ago.", "source": "INTERNAL"},
            {"text": "Social media chatter increasing. #SystemDown trending locally.", "source": "SOCIAL"},
        ],
        "initial_conflicts": [
            {
                "description": "O'Sullivan wants immediate field deployment; Chen flags legal risk of unauthorized action.",
                "agents_involved": ["ops", "legal"],
            },
        ],
        "escalation_schedule": [
            {"delay_minutes": 5, "event_text": "CNN Breaking: Major tech company confirms service outage.", "type": "media"},
            {"delay_minutes": 10, "event_text": "A class-action law firm issues a public statement of intent.", "type": "legal"},
            {"delay_minutes": 18, "event_text": "Internal whistleblower leaks email chain to The Verge.", "type": "internal"},
        ],
    }
