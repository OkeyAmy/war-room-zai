#!/usr/bin/env python3
"""
End-to-end backend structure check for LiveKit + agent turn handling.

Checks:
  1) Required env keys are present in backend/.env
  2) LiveKit ping through backend utility succeeds (when configured)
  3) Active-agent routing semantics are correct
"""

from __future__ import annotations

import os
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
BACKEND_DIR = ROOT / "backend"
os.chdir(BACKEND_DIR)
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from utils.livekit_api import is_livekit_configured, ping_livekit  # noqa: E402
from config.settings import get_settings  # noqa: E402
from gateway.chairman_handler import (  # noqa: E402
    get_active_voice_agent_id,
    register_agents,
    select_voice_agent,
)


def _parse_env(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    if not path.exists():
        return out
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        out[k.strip()] = v.strip().strip('"').strip("'")
    return out


def _print_env_status(env: dict[str, str]) -> bool:
    required = [
        "ZAI_API_KEY",
        "LIVEKIT_URL",
        "LIVEKIT_API_KEY",
        "LIVEKIT_API_SECRET",
        "ELEVENLABS_API_KEY",
        "VOICE_BACKEND",
    ]
    ok = True
    for key in required:
        present = bool(env.get(key))
        print(f"ENV {key}: {'SET' if present else 'MISSING'}")
        ok = ok and present
    return ok


class _FakeAgent:
    def __init__(self, agent_id: str, has_live: bool = True):
        self.agent_id = agent_id
        self.live_session = object() if has_live else None


def test_active_agent_routing():
    sid = "LIVEKIT_SYSTEM_CHECK"
    agents = {
        "atlas": _FakeAgent("atlas_CHECK"),
        "nova": _FakeAgent("nova_CHECK"),
        "cipher": _FakeAgent("cipher_CHECK", has_live=False),
    }
    register_agents(sid, agents)

    first = select_voice_agent(sid)
    assert first is not None and first.agent_id == "atlas_CHECK", "ROUTING FAIL: default active agent mismatch"

    targeted = select_voice_agent(sid, "nova_CHECK")
    assert targeted is not None and targeted.agent_id == "nova_CHECK", "ROUTING FAIL: target handoff mismatch"

    assert get_active_voice_agent_id(sid) == "nova_CHECK", "ROUTING FAIL: active agent state not persisted"


def test_livekit_environment():
    env = _parse_env(BACKEND_DIR / ".env")
    env_ok = _print_env_status(env)
    assert env_ok, "Missing required environment variables"

    settings = get_settings()
    model_ok = bool(settings.zai_agent_model)
    backend_ok = settings.voice_backend == "livekit_elevenlabs"

    eleven_ok = False
    if settings.elevenlabs_api_key:
        try:
            from livekit.plugins import elevenlabs
            import asyncio
            import aiohttp

            async def _check():
                async with aiohttp.ClientSession() as http_session:
                    tts = elevenlabs.TTS(
                        api_key=settings.elevenlabs_api_key,
                        http_session=http_session,
                    )
                    try:
                        voices = await tts.list_voices()
                    finally:
                        await tts.aclose()
                    return len(voices)

            count = asyncio.run(_check())
            eleven_ok = count > 0
        except Exception as e:
            pass

    ping_ok = False
    if is_livekit_configured():
        ping_ok, ping_msg = ping_livekit()

    assert model_ok, "Model check failed"
    assert backend_ok, "Voice backend check failed"
    assert eleven_ok, "Elevenlabs API check failed"
    if is_livekit_configured():
        assert ping_ok, "LiveKit ping failed"
