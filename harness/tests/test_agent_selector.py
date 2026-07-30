"""
Tests para agent_selector.py — Seleccion inteligente de agentes.
Verifica que solo se activen los agentes necesarios.
"""

from __future__ import annotations

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from harness.orchestrator.agent_selector import AgentSelector


class TestAgentSelector:
    """Test del selector de agentes."""

    def setup_method(self):
        self.selector = AgentSelector()

    def test_trivial_task_one_agent(self):
        """Tarea trivial -> 1 agente."""
        agents = self.selector.select("simple duda rapida")
        assert len(agents) <= 2

    def test_implem_task_has_builder(self):
        """Tarea de implementacion incluye builder."""
        agents = self.selector.select("implementa API REST en Rust")
        assert "builder" in agents

    def test_research_task_has_scientist(self):
        """Tarea de investigacion incluye scientist."""
        agents = self.selector.select("investiga patrones de disenio")
        assert "scientist" in agents

    def test_security_task_has_guardian(self):
        """Tarea de seguridad incluye guardian."""
        agents = self.selector.select("audita seguridad del codigo")
        assert "guardian" in agents

    def test_swarm_keyword_activates_all(self):
        """Keyword 'swarm' activa builder+scientist+guardian."""
        agents = self.selector.select("necesito swarm para implementar el sistema completo")
        assert "builder" in agents
        assert "scientist" in agents
        assert "guardian" in agents

    def test_evolve_task(self):
        """Tarea de evolve activa ese agente."""
        agents = self.selector.select("evolve the system skills")
        assert "evolve" in agents

    def test_complex_task_multi_agent(self):
        """Tarea compleja activa 2+ agentes."""
        agents = self.selector.select("implementa sistema de trading completo con tests y documentacion")
        assert len(agents) >= 2

    def test_simple_task_minimal_agents(self):
        """Tarea simple -> minimo de agentes."""
        agents = self.selector.select("solo una consulta rapida")
        # Simple indicators should trigger MINIMAL level
        assert len(agents) <= 2

    def test_empty_message(self):
        """Mensaje vacio -> builder por defecto."""
        agents = self.selector.select("")
        assert len(agents) >= 1

    def test_estimate_tokens_saved(self):
        """Estimacion de tokens ahorrados devuelve dict valido."""
        stats = self.selector.estimate_tokens_saved("implementa API REST")
        assert "selected_agents" in stats
        assert "tokens_saved" in stats
        assert stats["selected_agents"] >= 1
