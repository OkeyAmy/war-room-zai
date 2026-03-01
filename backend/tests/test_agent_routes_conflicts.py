"""
WAR ROOM — Regression tests for agent conflict parsing in /agents routes.
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def test_extract_conflict_agents_handles_legacy_string_entries():
    from gateway.agent_routes import _extract_conflict_agents

    assert _extract_conflict_agents("legacy_conflict_text") == []


def test_extract_conflict_agents_reads_dict_entries():
    from gateway.agent_routes import _extract_conflict_agents

    conflict = {"agents_involved": ["legal_ABC", "ops_ABC"]}
    assert _extract_conflict_agents(conflict) == ["legal_ABC", "ops_ABC"]
