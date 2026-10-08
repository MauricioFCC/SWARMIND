"""Tests de endurecimiento de la seleccion/descarte de agentes del coordinator.

Sonda adversarial (ADR-0077/ADR-0100) que fija el contrato CORREGIDO:

- matching por frontera de palabra: `"go"` no matchea `"good"`, `"ai"` no
  matchea `"email"`, `"test"` no matchea `"latest"`;
- abstention: fuera de dominio NO se fuerza `builder`;
- re-rank por competencia basado en observaciones reales (0 -> identidad) y
  calibrado por evidencia para no revertir un keyword fuerte con 1 dato.

Restricciones: 0 red, 0 LLM, determinista (SBX).
"""

from __future__ import annotations

from harness.orchestrator.agent_selector import AgentSelector
from harness.orchestrator.competence_model import CompetenceModel


class TestWordBoundaryMatching:
    """El matching de keywords usa frontera de palabra, no substring."""

    def setup_method(self) -> None:
        """Crea un selector sin evidencia de competencia (solo keywords)."""
        self.selector = AgentSelector()

    def test_go_no_matchea_good_practices(self) -> None:
        """'go' (builder) no debe matchear dentro de 'good'."""
        assert self.selector._score_agents("good practices")["builder"] == 0.0
        assert self.selector.select("good practices") == []

    def test_ai_no_matchea_email_marketing(self) -> None:
        """'ai' (scientist) no debe matchear dentro de 'email'."""
        assert self.selector._score_agents("email marketing")["scientist"] == 0.0
        assert self.selector.select("email marketing") == []

    def test_test_no_matchea_latest_build(self) -> None:
        """'test' (guardian) no debe matchear dentro de 'latest'."""
        scores = self.selector._score_agents("the latest build")
        assert scores["guardian"] == 0.0
        assert "guardian" not in self.selector.select("the latest build")

    def test_build_si_matchea_como_palabra(self) -> None:
        """La palabra real ('build') si debe asignar a builder."""
        assert "builder" in self.selector.select("the latest build")


class TestAbstention:
    """Fuera de dominio el selector se abstiene en vez de forzar builder."""

    def setup_method(self) -> None:
        """Crea un selector sin evidencia de competencia."""
        self.selector = AgentSelector()

    def test_out_of_domain_returns_empty(self) -> None:
        """'xyzzy plugh' (sin senal) devuelve lista vacia."""
        assert self.selector.select("xyzzy plugh") == []

    def test_out_of_domain_does_not_force_builder(self) -> None:
        """La abstention nunca debe caer al fallback hardcodeado 'builder'."""
        result = self.selector.select("xyzzy plugh quux blorf ambar")
        assert "builder" not in result
        assert result in ([], ["coordinator"])

    def test_empty_message_keeps_builder_contract(self) -> None:
        """Mensaje vacio conserva el contrato historico -> ['builder']."""
        assert self.selector.select("") == ["builder"]

    def test_abstain_false_restores_legacy_fallback(self) -> None:
        """Con abstain=False se conserva la retrocompatibilidad (builder)."""
        assert self.selector.select("xyzzy plugh", abstain=False) == ["builder"]


class TestCompetenceRerank:
    """El re-rank por competencia solo actua con evidencia real."""

    @staticmethod
    def _model() -> CompetenceModel:
        """Modelo Beta sin observaciones para (builder, guardian)."""
        return CompetenceModel(
            agents=("builder", "guardian"), skills=("general",)
        )

    def test_rerank_without_observations_is_identity(self) -> None:
        """0 observaciones => re-ordenacion identidad (mismo orden y valores)."""
        selector = AgentSelector(competence=self._model())
        base = selector._score_agents("implementa una api")
        adjusted = selector._rerank_with_competence(dict(base), "general")
        assert adjusted == base
        assert list(adjusted) == list(base)

    def test_one_observation_does_not_revert_strong_keyword(self) -> None:
        """1 sola observacion no revierte el keyword fuerte (builder primero)."""
        model = self._model()
        model.update("guardian", "general", success=True)
        selector = AgentSelector(competence=model)
        agents = selector.select("implementa una api", skill="general")
        assert agents[0] == "builder"

    def test_strong_evidence_can_boost_but_scaled(self) -> None:
        """Con evidencia fuerte, el bonus es positivo pero acotado por n/(n+k)."""
        model = self._model()
        for _ in range(20):
            model.update("guardian", "general", success=True)
        posterior = model.posterior("guardian", "general")
        assert 0.0 < posterior.evidence_weight() < 1.0


class TestDeterminism:
    """Misma entrada => mismo resultado (funcion pura y estable)."""

    def test_selection_is_deterministic(self) -> None:
        """Tres mensajes producen el mismo resultado en llamadas repetidas."""
        selector = AgentSelector()
        for message in (
            "implementa una api",
            "audita la seguridad",
            "xyzzy plugh",
        ):
            assert selector.select(message) == selector.select(message)
