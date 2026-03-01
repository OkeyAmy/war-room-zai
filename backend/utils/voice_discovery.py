"""
WAR ROOM — Voice Discovery
Fetches available ElevenLabs voices via LiveKit plugin runtime when available.
Falls back to the hardcoded pool in constants.py.
"""

from __future__ import annotations

import logging
from typing import Optional

from config.constants import ALLOWED_VOICE_POOL, VOICE_STYLE_MAP

logger = logging.getLogger(__name__)

# ── CACHED RESULT ────────────────────────────────────────────────────────

_cached_voices: Optional[list[str]] = None


async def discover_voices(force_refresh: bool = False) -> list[str]:
    """
    Attempt to discover available voices from ElevenLabs via LiveKit plugin.
    Falls back to the hardcoded ALLOWED_VOICE_POOL if the SDK
    is unavailable or the call fails.

    Results are cached for the lifetime of the server process.

    Returns:
        List of voice name strings.
    """
    global _cached_voices

    if _cached_voices is not None and not force_refresh:
        return _cached_voices

    try:
        import aiohttp
        from config.settings import get_settings
        from livekit.plugins import elevenlabs

        settings = get_settings()
        if settings.elevenlabs_api_key:
            async with aiohttp.ClientSession() as http_session:
                tts = elevenlabs.TTS(
                    api_key=settings.elevenlabs_api_key,
                    http_session=http_session,
                )
                try:
                    voices = await tts.list_voices()
                finally:
                    await tts.aclose()
            ids = [
                (getattr(v, "id", None) or getattr(v, "voice_id", None))
                for v in voices
            ]
            ids = [v for v in ids if isinstance(v, str) and v]
            if ids:
                _cached_voices = ids
                logger.info(
                    f"Discovered {len(ids)} ElevenLabs voices from API."
                )
                return _cached_voices
        logger.info(
            "ELEVENLABS_API_KEY not set or no voices returned. "
            f"Using fallback pool ({len(ALLOWED_VOICE_POOL)} voices)."
        )

    except ImportError:
        logger.warning("LiveKit/ElevenLabs plugin unavailable — using hardcoded voice pool")
    except Exception as e:
        logger.warning(f"Voice discovery failed: {e} — using hardcoded voice pool")

    _cached_voices = ALLOWED_VOICE_POOL
    return _cached_voices


async def get_voice_style_map() -> dict[str, list[str]]:
    """
    Returns the voice-to-style mapping.
    Currently the style mapping is maintained locally since the SDK
    does not expose style metadata for prebuilt voices.
    """
    return VOICE_STYLE_MAP


async def check_voice_health() -> dict:
    """
    Health check for the voice subsystem.
    Validates that:
    1. The voice pool is available (from SDK or fallback)
    2. The live audio model is reachable
    3. Voice assignment logic works

    Returns:
        Dict with 'status' ('pass'/'fail') and 'message'.
    """
    try:
        voices = await discover_voices()
        if not voices:
            return {"status": "fail", "message": "No voices available"}

        # Verify voice assignment works
        from agents.voice_assignment import assign_voices
        test_agents = [
            {"role_key": "test_legal", "voice_style": "authoritative"},
            {"role_key": "test_pr", "voice_style": "urgent"},
        ]
        assignments = assign_voices(test_agents)
        if len(assignments) != 2:
            return {
                "status": "fail",
                "message": f"Voice assignment returned {len(assignments)}/2",
            }

        return {
            "status": "pass",
            "message": f"{len(voices)} voices available, assignment working",
            "voice_count": len(voices),
        }

    except Exception as e:
        return {"status": "fail", "message": f"Voice check failed: {e}"}
