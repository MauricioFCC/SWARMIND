"""Tests para ScopeAnalyzer — analisis de alcance de tareas."""
from __future__ import annotations

from harness.orchestrator.scope_analyzer import ScopeAnalyzer, ScopeEstimate


class TestScopeAnalyzer:
    """Verifica el analisis de alcance de tareas."""

    def setup_method(self):
        self.analyzer = ScopeAnalyzer()

    def test_empty_message(self):
        """Mensaje vacio retorna ScopeEstimate default."""
        scope = self.analyzer.analyze("")
        assert scope.estimated_files == 1
        assert scope.estimated_modules == 1
        assert scope.builders_needed == 1
        assert scope.guardians_needed == 1
        assert scope.need_scientist is False
        assert scope.need_bugfix is False
        assert scope.level == "small"

    def test_none_message(self):
        """Mensaje None retorna ScopeEstimate default."""
        scope = self.analyzer.analyze(None)
        assert scope.estimated_files == 1
        assert scope.level == "small"

    def test_small_scope(self):
        """Tarea simple produce nivel small."""
        scope = self.analyzer.analyze("un archivo simple")
        assert scope.level == "small"
        assert scope.builders_needed == 1
        assert scope.guardians_needed == 1
        assert scope.need_scientist is False
        assert scope.need_bugfix is False

    def test_medium_scope(self):
        """Tarea normal produce nivel medium."""
        scope = self.analyzer.analyze("desarrolla un sistema backend completo con varios modulos")
        assert scope.level == "medium"
        assert scope.builders_needed == 2
        assert scope.guardians_needed == 1
        assert scope.need_scientist is True
        assert scope.need_bugfix is False

    def test_large_scope(self):
        """Tarea grande produce nivel large."""
        scope = self.analyzer.analyze("arquitectura de trading")
        assert scope.level == "large"
        assert scope.builders_needed == 3
        assert scope.guardians_needed == 2
        assert scope.need_scientist is True
        assert scope.need_bugfix is True

    def test_xlarge_scope(self):
        """Tarea de proyecto enorme produce nivel xlarge."""
        scope = self.analyzer.analyze(
            "monorepo enterprise microservicios aplicacion completa con cola de mensajes"
        )
        assert scope.level == "xlarge"
        assert scope.builders_needed >= 4
        assert scope.guardians_needed >= 2
        assert scope.need_scientist is True
        assert scope.need_bugfix is True

    def test_tech_stack_rust(self):
        """Tech stack Rust suma peso extra."""
        scope = self.analyzer.analyze("implementa un sistema en Rust")
        # Rust agrega 2 al total_work
        assert scope.estimated_files > 1

    def test_research_triggers_scientist(self):
        """Palabra 'investigar' activa scientist incluso en small."""
        scope = self.analyzer.analyze("investigar algoritmos")
        assert scope.need_scientist is True


class TestScopeEstimate:
    """Verifica el dataclass ScopeEstimate."""

    def test_total_agents_default(self):
        """total_agents por defecto incluye coordinator."""
        scope = ScopeEstimate()
        assert scope.total_agents == 3  # 1 builder + 1 guardian + 1 coordinator

    def test_total_agents_with_scientist(self):
        """total_agents suma scientist."""
        scope = ScopeEstimate(
            builders_needed=2, guardians_needed=1,
            need_scientist=True, need_bugfix=False,
        )
        assert scope.total_agents == 5  # 2+1+1(scientist)+1(coordinator)

    def test_total_agents_with_bugfix(self):
        """total_agents suma bugfix."""
        scope = ScopeEstimate(
            builders_needed=2, guardians_needed=1,
            need_scientist=False, need_bugfix=True,
        )
        assert scope.total_agents == 5  # 2+1+1(bugfix)+1(coordinator)

    def test_total_agents_with_both(self):
        """total_agents suma scientist y bugfix."""
        scope = ScopeEstimate(
            builders_needed=3, guardians_needed=2,
            need_scientist=True, need_bugfix=True,
        )
        assert scope.total_agents == 8  # 3+2+1+1+1

    def test_get_template_name(self):
        """get_template_name genera nombre descriptivo."""
        scope = ScopeEstimate(level="medium", builders_needed=2, guardians_needed=1)
        name = ScopeAnalyzer().get_template_name(scope)
        assert name == "dynamic_medium_2b_1g"

    def test_generate_subtasks_small(self):
        """generate_subtasks genera estructura correcta para small."""
        scope = ScopeEstimate(level="small", builders_needed=1, guardians_needed=1)
        analyzer = ScopeAnalyzer()
        subtasks = analyzer.generate_subtasks(scope)
        assert len(subtasks) >= 4  # plan + builder + guardian-tests + consolidar
        assert subtasks[0]["agent"] == "coordinator"
        assert subtasks[0]["description"].startswith("PLAN")

    def test_generate_subtasks_medium_with_scientist(self):
        """generate_subtasks incluye scientist cuando corresponde."""
        scope = ScopeEstimate(
            level="medium", builders_needed=2, guardians_needed=1,
            need_scientist=True,
        )
        analyzer = ScopeAnalyzer()
        subtasks = analyzer.generate_subtasks(scope)
        agentes = {s["agent"] for s in subtasks}
        assert "scientist" in agentes

    def test_generate_subtasks_xlarge(self):
        """generate_subtasks para xlarge incluye bugfix."""
        scope = ScopeEstimate(
            level="xlarge", builders_needed=4, guardians_needed=2,
            need_scientist=True, need_bugfix=True,
        )
        analyzer = ScopeAnalyzer()
        subtasks = analyzer.generate_subtasks(scope)
        descripciones = [s["description"] for s in subtasks]
        assert any("BUGFIX" in d for d in descripciones)
