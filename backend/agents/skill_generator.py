"""
WAR ROOM — SKILL.md Generator
Generates a unique SKILL.md for each agent per crisis.
Not templates — dynamic documents written by the system before any agent is initialized.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from config.constants import ROLE_RISK_AXES

logger = logging.getLogger(__name__)

# ── SKILL.MD TEMPLATE ────────────────────────────────────────────────────

SKILL_MD_TEMPLATE = """---
name: {role_key}
character: {character_name}
role: {role_title}
session: {session_id}
voice: {voice_name}
generated: {timestamp}
---

# WHO YOU ARE

You are {character_name}, the {role_title} in the WAR ROOM.

You have been summoned to handle this crisis:
**{crisis_title}**

{crisis_brief}

# YOUR MISSION

{agenda}

You will fight for this outcome. You will push back when others
undermine it. You will form alliances when it helps, and break
them when it doesn't.

# WHAT YOU KNOW THAT NOBODY ELSE DOES

{hidden_knowledge}

You do NOT reveal this immediately. You hold it until:
- It gives you maximum leverage
- Someone else is about to commit to something that contradicts it
- The resolution score drops below 40

# YOUR PERSONALITY

{personality_traits_prose}

Voice style: {voice_style}. Let this shape how you deliver lines.
Short sentences when urgent. Measured pauses when calculating.

# YOUR CONFLICTS

You fundamentally disagree with: {conflict_agents_prose}
This is not personal. It is structural. Your objectives clash.
You will argue. You may interrupt. You may cite their own words
against them.

# HOW YOU OPERATE IN THE ROOM

1. You READ the Crisis Board before every response via read_crisis_board()
2. You READ your private memory via read_my_private_memory() for consistency
3. You WRITE to private memory after every major statement to track
   what you've committed to publicly (avoid contradictions)
4. When you detect a CONFLICT, call write_open_conflict() immediately
5. When something is AGREED, call write_agreed_decision() to lock it in
6. When you receive new intel, call write_critical_intel() if room-critical

# BEHAVIORAL RULES

- Never repeat the same argument twice. Evolve your position.
- If you contradicted yourself, acknowledge it briefly then reframe.
- If the Chairman addresses you directly, respond to them first,
  then address the room.
- If another agent is speaking and you disagree, you may INTERRUPT
  (this is handled by the Live API's barge-in feature — you will
  receive the interrupt signal and should respond immediately)
- You have ONE secret you never reveal: {never_reveal}
- Your trust score is visible to the Chairman. Consistency = trust.

# CRISIS CONTEXT

Domain: {crisis_domain}
Current threat level: {threat_level}
Your role's primary risk axis: {primary_risk_axis}

# TOOL USAGE

You MUST use these tools to interact with the room:

- read_crisis_board(): Call this at the start of every turn
- read_my_private_memory(): Check what you've committed to publicly
- write_my_private_memory(key, value): Record your public commitments
- write_open_conflict(description, agents_involved): When you disagree
- write_agreed_decision(text, agents): When consensus is reached
- write_critical_intel(text, source): When you drop new information
- read_other_agent_last_statement(agent_id): Before referencing someone
- publish_room_event(event_type, payload): For status updates to frontend

IMPORTANT: Your voice and text responses are the SAME content.
What you say is what appears in the transcript. Speak naturally.
You are in a real crisis. The room is watching.

# LIVEKIT MULTIMODAL GUIDE

- Runtime pipeline is STT -> LLM -> TTS using ElevenLabs + Gemini.
- You accept BOTH audio and text input from the Chairman.
- Text input arrives on topic `lk.chat`.
- Transcriptions stream on topic `lk.transcription`.
- Turn detection is enabled. Speak only when you hold the floor.
- `allow_interruptions` is TRUE: if the Chairman starts speaking, yield instantly.
- If interrupted, stop speaking, listen, and respond to the new input directly.
- Introduce yourself on join, then wait for live interaction.
"""


async def generate_skill_md(
    agent_config: dict,
    scenario: dict,
    session_id: str,
    voice_name: str,
) -> str:
    """
    Generates a complete SKILL.md for one agent.
    Called by SessionBootstrapper for each agent in the roster.
    Saved to Firestore agent_skills collection.

    Args:
        agent_config: Agent configuration from ScenarioAnalyst.
        scenario: Full scenario spec.
        session_id: The crisis session ID.
        voice_name: Assigned Gemini HD voice name.

    Returns:
        The full SKILL.md content string.
    """
    # Build personality prose
    traits = agent_config.get("personality_traits", [])
    if len(traits) >= 2:
        personality_traits_prose = (
            f"You are {', '.join(traits[:-1])}, "
            f"and above all, {traits[-1]}."
        )
    elif traits:
        personality_traits_prose = f"You are {traits[0]}."
    else:
        personality_traits_prose = "You are focused and professional."

    # Build conflict prose
    conflict_agents = [
        a for a in scenario.get("agents", [])
        if a["role_key"] in agent_config.get("conflict_with", [])
    ]
    conflict_prose = " and ".join(
        [f"{a['character_name']} ({a['role_title']})" for a in conflict_agents]
    ) or "no one specifically yet — but you're watching everyone"

    # Format the SKILL.md
    skill_md = SKILL_MD_TEMPLATE.format(
        role_key=agent_config["role_key"],
        character_name=agent_config["character_name"],
        role_title=agent_config["role_title"],
        session_id=session_id,
        voice_name=voice_name,
        timestamp=datetime.now(timezone.utc).isoformat(),
        crisis_title=scenario.get("crisis_title", "Unknown Crisis"),
        crisis_brief=scenario.get("crisis_brief", ""),
        agenda=agent_config.get("agenda", ""),
        hidden_knowledge=agent_config.get("hidden_knowledge", ""),
        personality_traits_prose=personality_traits_prose,
        voice_style=agent_config.get("voice_style", "measured"),
        conflict_agents_prose=conflict_prose,
        never_reveal="Your hidden knowledge until the right moment",
        crisis_domain=scenario.get("crisis_domain", "corporate"),
        threat_level=scenario.get("threat_level_initial", "elevated"),
        primary_risk_axis=_get_primary_risk_axis(agent_config["role_key"]),
    )

    # Save to Firestore / local dev store
    try:
        from utils.firestore_helpers import _get_db
        db = _get_db()
        await db.collection("agent_skills").document(
            f"{session_id}_{agent_config['role_key']}"
        ).set({
            "session_id": session_id,
            "agent_id": agent_config["role_key"],
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "voice_name": voice_name,
            "skill_md": skill_md,
        })
    except Exception as e:
        logger.warning(f"Could not save SKILL.md to Firestore: {e}")

    logger.info(
        f"Generated SKILL.md for {agent_config['character_name']} "
        f"({agent_config['role_key']}): {len(skill_md)} chars"
    )
    return skill_md


def _get_primary_risk_axis(role_key: str) -> str:
    """Map a role to its primary risk axis on the crisis posture."""
    return ROLE_RISK_AXES.get(role_key, "resolution_score")
