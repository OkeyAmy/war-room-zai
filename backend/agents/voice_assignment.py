"""
WAR ROOM — Voice Assignment
Maps agent voice_style preferences to the ElevenLabs voice pool.
Guarantees no two agents share a voice within a session.
"""

from __future__ import annotations

import logging
from config.constants import VOICE_STYLE_MAP

logger = logging.getLogger(__name__)


def assign_voices(agents: list[dict]) -> dict[str, str]:
    """
    Takes the agent list from Scenario Analyst output.
    Returns a dict of { role_key: voice_name }.
    Guarantees no two agents share a voice.

    Args:
        agents: List of agent config dicts with 'role_key' and 'voice_style'.

    Returns:
        Dict mapping role_key → voice_name.
    """
    assigned: dict[str, str] = {}
    used_voices: set[str] = set()

    for agent in agents:
        style = agent.get("voice_style", "measured")
        candidates = VOICE_STYLE_MAP.get(style, VOICE_STYLE_MAP["measured"])

        voice_found = False
        for voice in candidates:
            if voice not in used_voices:
                assigned[agent["role_key"]] = voice
                used_voices.add(voice)
                voice_found = True
                break

        if not voice_found:
            # Fallback: pick any unused voice from the full pool
            all_voices = set()
            for voices in VOICE_STYLE_MAP.values():
                all_voices.update(voices)
            remaining = list(all_voices - used_voices)
            if remaining:
                assigned[agent["role_key"]] = remaining[0]
                used_voices.add(remaining[0])
                logger.warning(
                    f"Fallback voice for {agent['role_key']}: {remaining[0]} "
                    f"(preferred style '{style}' exhausted)"
                )
            else:
                logger.error(f"No voices available for {agent['role_key']}")

    logger.info(f"Voice assignments: {assigned}")
    return assigned
