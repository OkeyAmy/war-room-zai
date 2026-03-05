"""
WAR ROOM — Scenario Analyst Agent
Runs ONCE at session start. Analyzes the crisis input and outputs
a complete ScenarioSpec JSON that initializes the entire crisis team.

Uses Z.AI GLM-5 via OpenAI-compatible SDK.
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

{uploaded_context_section}

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
      "identity_color": "#hexcode that fits their personality",
      "expertise_domains": ["domain1", "domain2"],
      "communication_style": "How this person speaks — cadence, vocabulary, mannerisms",
      "hidden_tension": "Internal conflict that shapes their reasoning without them saying it",
      "emotional_temperature": "Their urgency level and emotional tone",
      "initial_position": "Their opening stance on the crisis",
      "blind_spot": "What they consistently underweight or miss",
      "documents_responsible": ["Document Name they should own"]
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
  ],
  "required_documents": [
    {{
      "doc_id": "snake_case_identifier",
      "title": "Document Title",
      "owner_agent_id": "role_key of responsible agent",
      "deadline_hours": 72,
      "template_type": "regulatory_notification|executive_briefing|technical_report|customer_notification|insurance_report",
      "legal_framework": "specific regulation or standard (if applicable)"
    }}
  ]
}}

Rules:
- Generate exactly 4 agents, each with a distinct role, personality, and agenda.
- Each agent will run in its own independent LiveKit pod with a unique room.
- The hidden_knowledge for each agent must eventually become relevant.
- At least 2 agents must have conflict_with entries pointing at each other.
- escalation_schedule must have exactly 3 events spaced across the session.
- voice_style guides which ElevenLabs voices to assign. Each agent MUST have a different voice_style.
- Each agent must have expertise_domains, communication_style, hidden_tension,
  emotional_temperature, initial_position, and blind_spot filled in.
- Generate 2-4 required_documents — real deliverables that must be drafted during the session.
  Each document should be owned by the agent with the most relevant expertise.
- Each agent must be suitable for LiveKit multimodal runtime:
  - accepts both spoken and typed chairman input
  - handles interruptions naturally
  - can introduce itself in one short opening turn
- Output ONLY the JSON object. No explanatory text.
"""


def _get_zai_client():
    """Return a configured OpenAI client pointing at Z.AI."""
    from openai import OpenAI
    settings = get_settings()
    return OpenAI(
        api_key=settings.zai_api_key,
        base_url=settings.zai_base_url,
    )


async def run_scenario_analyst(
    crisis_input: str,
    session_id: str,
    uploaded_context: str = "",
) -> dict:
    """
    Runs the Scenario Analyst agent ONCE.
    Returns the full scenario spec as a Python dict.

    Args:
        crisis_input: The raw crisis description from the chairman.
        session_id: The session being bootstrapped.
        uploaded_context: Optional extracted text from uploaded documents.

    Returns:
        dict matching the ScenarioSpec schema.
    """
    import asyncio
    settings = get_settings()

    # Build uploaded context section for the prompt
    uploaded_section = ""
    if uploaded_context:
        uploaded_section = f"UPLOADED DOCUMENT CONTEXT:\n{uploaded_context}"

    if not settings.zai_api_key:
        logger.warning("ZAI_API_KEY not set — returning mock scenario")
        return _generate_mock_scenario(crisis_input, session_id)

    try:
        client = _get_zai_client()

        system_prompt = SCENARIO_ANALYST_INSTRUCTION.format(
            crisis_input=crisis_input,
            uploaded_context_section=uploaded_section,
        )

        response = await asyncio.to_thread(
            client.chat.completions.create,
            model=settings.zai_scenario_model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"Analyze this crisis and return the full scenario JSON: {crisis_input}"},
            ],
            temperature=0.85,
            max_tokens=4000,
            response_format={"type": "json_object"},
        )

        content = response.choices[0].message.content
        if not content:
            logger.warning("Scenario Analyst returned empty response — using mock")
            return _generate_mock_scenario(crisis_input, session_id)

        scenario = json.loads(content)
        logger.info(f"Scenario Analyst produced: {scenario.get('crisis_title', 'Unknown')}")
        return scenario

    except Exception as e:
        logger.warning(f"Scenario Analyst failed ({e}) — returning mock scenario")
        return _generate_mock_scenario(crisis_input, session_id)


def _generate_mock_scenario(crisis_input: str, session_id: str) -> dict:
    """
    Generate a mock scenario for local development/testing
    when Z.AI is not available.
    MULTI-AGENT: expanded from 1 agent to 4 independent agents.
    v2.0: enriched agent profiles + required_documents.
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
                "expertise_domains": ["corporate law", "regulatory compliance", "data protection"],
                "communication_style": "Precise, measured, references statutes and precedents. Speaks in structured arguments.",
                "hidden_tension": "Knows the compliance warning she flagged was dismissed by leadership. Feels partly responsible.",
                "emotional_temperature": "Controlled urgency — maintains composure but pushes hard on deadlines.",
                "initial_position": "Full disclosure within 72 hours per regulatory requirements.",
                "blind_spot": "Underestimates the speed of media escalation. Focuses on legal timelines, ignores PR timelines.",
                "documents_responsible": ["Regulatory Notification"],
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
                "expertise_domains": ["crisis communications", "media relations", "reputation management"],
                "communication_style": "Fast, narrative-driven, uses metaphors and media framing language.",
                "hidden_tension": "Has a personal relationship with the Reuters reporter. Conflicted about using or containing it.",
                "emotional_temperature": "High urgency — sees every minute without a statement as damage done.",
                "initial_position": "Issue proactive holding statement within 2 hours.",
                "blind_spot": "Prioritizes narrative speed over factual verification. May over-promise commitments.",
                "documents_responsible": ["Customer Notification"],
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
                "expertise_domains": ["systems architecture", "incident response", "infrastructure engineering"],
                "communication_style": "Technical, data-driven, uses precise terminology. Avoids ambiguity.",
                "hidden_tension": "The cost-cutting decision she approved directly caused this. Wrestling with disclosure.",
                "emotional_temperature": "Measured on the surface, high internal stress about accountability.",
                "initial_position": "Root cause must be identified before any public communication.",
                "blind_spot": "Focuses on technical fix, underestimates human and organizational factors.",
                "documents_responsible": ["Technical Incident Report"],
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
                "expertise_domains": ["operations management", "supply chain", "business continuity"],
                "communication_style": "Direct, action-oriented, uses military-style brevity. No padding.",
                "hidden_tension": "Backup testing was his responsibility. Knows the gap but won't admit it unprompted.",
                "emotional_temperature": "High — driven by operational losses mounting every minute.",
                "initial_position": "Immediate failover to backup systems regardless of risk.",
                "blind_spot": "Prioritizes speed over due process. Dismisses legal and PR concerns as bureaucracy.",
                "documents_responsible": ["Executive Briefing"],
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
        "required_documents": [
            {
                "doc_id": "regulatory_notification",
                "title": "Regulatory Notification",
                "owner_agent_id": "legal",
                "deadline_hours": 72,
                "template_type": "regulatory_notification",
                "legal_framework": "SEC Regulation FD / State Data Breach Notification Laws",
            },
            {
                "doc_id": "customer_notification",
                "title": "Customer Notification",
                "owner_agent_id": "pr",
                "deadline_hours": 24,
                "template_type": "customer_notification",
                "legal_framework": "",
            },
            {
                "doc_id": "technical_incident_report",
                "title": "Technical Incident Report",
                "owner_agent_id": "engineer",
                "deadline_hours": 48,
                "template_type": "technical_report",
                "legal_framework": "ISO 27001 Incident Reporting",
            },
            {
                "doc_id": "executive_briefing",
                "title": "Executive Briefing",
                "owner_agent_id": "ops",
                "deadline_hours": 12,
                "template_type": "executive_briefing",
                "legal_framework": "",
            },
        ],
    }
