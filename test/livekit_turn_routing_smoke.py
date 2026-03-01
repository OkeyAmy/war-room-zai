#!/usr/bin/env python3
"""
LiveKit-style turn routing smoke test.

Validates that chairman input is routed to exactly one active agent target
and that explicit target selection updates the active speaker handoff state.
"""

from __future__ import annotations

import os
import sys


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BACKEND_DIR = os.path.join(ROOT, "backend")
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

from gateway.chairman_handler import (  # noqa: E402
    get_active_voice_agent_id,
    register_agents,
    select_voice_agent,
)


class _FakeAgent:
    def __init__(self, agent_id: str, has_live: bool = True):
        self.agent_id = agent_id
        self.live_session = object() if has_live else None


def run() -> int:
    session_id = "LIVEKIT_SMOKE"
    agents = {
        "atlas": _FakeAgent("atlas_TEST"),
        "nova": _FakeAgent("nova_TEST"),
        "cipher": _FakeAgent("cipher_TEST", has_live=False),
    }

    register_agents(session_id, agents)

    # 1) In single-agent mode, registry is hard-trimmed to one live agent.
    first = select_voice_agent(session_id)
    assert first is not None, "Expected a selected agent"
    assert first.agent_id == "atlas_TEST", f"Unexpected default agent: {first.agent_id}"
    assert get_active_voice_agent_id(session_id) == "atlas_TEST"

    # 2) Explicit target to another agent should NOT switch in single-agent guard mode.
    targeted = select_voice_agent(session_id, "nova_TEST")
    assert targeted is not None, "Expected targeted agent selection"
    assert targeted.agent_id == "atlas_TEST"
    assert get_active_voice_agent_id(session_id) == "atlas_TEST"

    # 3) Invalid target should preserve current active responder.
    fallback = select_voice_agent(session_id, "missing_agent")
    assert fallback is not None
    assert fallback.agent_id == "atlas_TEST", "Active responder should remain atlas"

    # 4) Non-live target should not steal routing.
    non_live = select_voice_agent(session_id, "cipher_TEST")
    assert non_live is not None
    assert non_live.agent_id == "atlas_TEST", "Non-live agent must not become active"

    print("PASS: livekit_turn_routing_smoke")
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
