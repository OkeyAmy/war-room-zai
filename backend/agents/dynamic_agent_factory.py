"""
WAR ROOM — Dynamic Agent Factory
Summons new agents on chairman request during an active session.
Generates a new SKILL.md and initializes a new CrisisAgent on-the-fly.
"""

from __future__ import annotations

import uuid
import logging
from datetime import datetime, timezone

from agents.base_crisis_agent import CrisisAgent
from agents.skill_generator import generate_skill_md
from agents.voice_assignment import VOICE_STYLE_MAP
from config.constants import (
    ALLOWED_VOICE_POOL,
    COLLECTION_CRISIS_SESSIONS,
    EVENT_AGENT_ASSEMBLING,
)

logger = logging.getLogger(__name__)


async def summon_agent(
    session_id: str,
    role_key: str,
    role_title: str,
    character_name: str,
    agenda: str,
    personality_traits: list[str] = None,
    voice_style: str = "measured",
    identity_color: str = "#888888",
    active_agents: dict[str, CrisisAgent] = None,
) -> CrisisAgent:
    """
    Dynamically summon a new agent into an active crisis session.
    Called when the Chairman requests additional expertise.

    Args:
        session_id: Active crisis session ID.
        role_key: The role identifier (e.g., "strategy", "medical").
        role_title: Full job title.
        character_name: The character's full name.
        agenda: What they want to achieve.
        personality_traits: List of personality traits.
        voice_style: Voice delivery style.
        identity_color: Hex color for UI.
        active_agents: Dict of currently active agents (to avoid voice conflicts).

    Returns:
        The newly created CrisisAgent.
    """
    from utils.events import push_event

    agent_id = f"{role_key}_{session_id}"
    personality_traits = personality_traits or ["focused", "professional", "adaptable"]

    # Find an unused voice
    used_voices = set()
    if active_agents:
        for agent in active_agents.values():
            used_voices.add(agent.assigned_voice)

    # Try preferred style voices first
    assigned_voice = None
    candidates = VOICE_STYLE_MAP.get(voice_style, VOICE_STYLE_MAP["measured"])
    for voice in candidates:
        if voice not in used_voices:
            assigned_voice = voice
            break

    if not assigned_voice:
        # Fallback to any unused voice
        all_voices = set(ALLOWED_VOICE_POOL)
        remaining = list(all_voices - used_voices)
        assigned_voice = remaining[0] if remaining else "Kore"

    # Build agent config compatible with ScenarioAnalyst output
    agent_config = {
        "role_key": role_key,
        "role_title": role_title,
        "character_name": character_name,
        "defining_line": f"I've just been briefed. Let me assess the situation.",
        "agenda": agenda,
        "hidden_knowledge": "Freshly summoned — no hidden knowledge yet.",
        "personality_traits": personality_traits,
        "conflict_with": [],
        "voice_style": voice_style,
        "identity_color": identity_color,
    }

    # Get current scenario from Firestore
    try:
        from utils.firestore_helpers import _get_db
        db = _get_db()
        doc = await db.collection(COLLECTION_CRISIS_SESSIONS) \
                      .document(session_id).get()
        scenario = doc.to_dict() if doc.exists else {}
    except Exception:
        scenario = {"crisis_title": "Active Crisis", "crisis_brief": "", "agents": []}

    # Push assembling event
    await push_event(session_id, EVENT_AGENT_ASSEMBLING, {
        "character_name": character_name,
        "role_title": role_title,
        "identity_color": identity_color,
        "defining_line": agent_config["defining_line"],
        "voice_name": assigned_voice,
    })

    # Generate SKILL.md
    skill_md = await generate_skill_md(
        agent_config, scenario, session_id, assigned_voice
    )

    # Create the agent
    agent = CrisisAgent(
        session_id=session_id,
        agent_id=agent_id,
        role_config=agent_config,
        skill_md=skill_md,
        assigned_voice=assigned_voice,
    )

    # Initialize Live voice session
    await agent.initialize_live_session()

    # Initialize memory
    await agent.memory_ref.set({
        "agent_id": agent_id,
        "session_id": session_id,
        "character_name": character_name,
        "private_facts": [],
        "hidden_agenda": "",
        "private_commitments": [],
        "previous_statements": [],
        "public_positions": {},
        "contradictions_detected": 0,
        "adk_session_id": str(uuid.uuid4()),
        "voice_name": assigned_voice,
        "voice_session_active": True,
    })

    logger.info(
        f"Dynamically summoned agent: {character_name} ({role_title}) "
        f"as {agent_id} with voice {assigned_voice}"
    )

    return agent
