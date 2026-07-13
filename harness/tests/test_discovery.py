"""Tests para agent discovery."""
from __future__ import annotations


class TestDiscovery:
    def test_discover_count(self, agent_discovery):
        assert len(agent_discovery) >= 5

    def test_has_universal_roles(self, agent_discovery):
        for role in ["coordinator", "builder", "scientist", "guardian"]:
            assert role in agent_discovery

    def test_agents_have_triggers_key(self, agent_discovery):
        for name, info in agent_discovery.items():
            assert "triggers" in info, f"{name} debe tener campo triggers"

    def test_agents_have_capabilities(self, agent_discovery):
        for name, info in agent_discovery.items():
            assert "capabilities" in info
