"""Tests de wiring ADR-0075: composition en skills reales + selector con
competencia + fanout_gate en executor/planner.

Piloto real: swarm-release-ops delega a security-audit (calls:), el
AgentSelector re-rankea con CompetenceModel cuando hay evidencia, y el
fanout_gate degrada voting/estrategia multi cuando el baseline >= 80%.
"""

from __future__ import annotations

from pathlib import Path

from harness.context.skill_composition import resolve_composition
from harness.model_router.multi_provider_types import ExecutionResult
from harness.orchestrator.agent_selector import AgentSelector
from harness.orchestrator.competence_model import CompetenceModel


class _FakeProvider:
    """MultiAPIProvider fake: respuesta exitosa determinista (patron test PE)."""

    def execute(self, model: str, prompt: str, **kwargs: object) -> ExecutionResult:
        """Retorna resultado exitoso con tokens 100 (determinista)."""
        return ExecutionResult(
            success=True, output=f"out:{prompt[:10]}", source="cloud",
            model=model, duration_ms=1.0, tokens_used=100,
        )


REPO = Path(__file__).resolve().parents[2]
SKILLS_DIR = REPO / ".opencode" / "skills"


class TestPilotComposition:
    """Wiring 1: calls: en skills reales (SSOT del repo)."""

    def test_swarm_release_ops_delegates_security_audit(self) -> None:
        """El piloto real: swarm-release-ops -> security-audit (sin ciclo)."""
        resolved = resolve_composition("swarm-release-ops", SKILLS_DIR)
        assert "security-audit" in resolved.invoked
        assert resolved.invocation_tiers["swarm-release-ops"] == "user"
        assert resolved.invocation_tiers["security-audit"] == "skill"

    def test_all_declared_calls_resolve(self) -> None:
        """Toda skill con calls: resuelve (sin romper el SSOT de 34)."""
        from harness.context.skill_composition import parse_calls

        for skill_md in SKILLS_DIR.glob("*/SKILL.md"):
            calls = parse_calls(skill_md)
            if not calls:
                continue
            resolved = resolve_composition(skill_md.parent.name, SKILLS_DIR)
            assert all(c in resolved.invoked or c == skill_md.parent.name for c in calls)


class TestSelectorCompetence:
    """Wiring 2: AgentSelector re-rankea con CompetenceModel inyectado."""

    def _model(self) -> CompetenceModel:
        """Modelo con guardian fuertemente dominante en 'security'."""
        model = CompetenceModel(
            agents=("builder", "guardian", "scientist"),
            skills=("security",),
        )
        for _ in range(6):
            model.update("guardian", "security", success=True)
        for _ in range(2):
            model.update("guardian", "security", success=False)
        for _ in range(1):
            model.update("builder", "security", success=True)
        for _ in range(4):
            model.update("builder", "security", success=False)
        return model

    def test_selector_accepts_competence(self) -> None:
        """AgentSelector acepta el modelo inyectado (DI)."""
        selector = AgentSelector(competence=self._model())
        agents = selector.select("auditar la seguridad del endpoint", skill="security")
        assert agents  # no vacio

    def test_competence_boosts_evidence_based_ranking(self) -> None:
        """Con evidencia fuerte, guardian domina la seleccion de security."""
        selector = AgentSelector(competence=self._model())
        agents = selector.select("auditar la seguridad del endpoint", skill="security")
        assert agents[0] == "guardian"

    def test_selector_without_competence_unchanged(self) -> None:
        """Sin modelo inyectado, el comportamiento keyword no cambia."""
        selector = AgentSelector()
        agents = selector.select("auditar la seguridad del endpoint")
        assert "guardian" in agents


class _FakeRouter:
    """Router fake con score/confidence fijos (mismo contrato que el test PE)."""

    def __init__(self, score: float = 30.0, confidence: float = 0.9) -> None:
        self.score = score
        self.confidence = confidence

    def route(self, task_text: str, **kwargs: object) -> object:
        """Retorna un route con model_route de score/confidence fijos."""
        return type(
            "R", (),
            {
                "model_route": type(
                    "MR", (),
                    {"route": "frontier" if self.score >= 50 else "small",
                     "score": self.score, "confidence": self.confidence},
                )(),
            },
        )()


class TestFanoutGateWiring:
    """Wiring 3: fanout_gate en executor (voting) y planner (estrategia)."""

    def test_vote_on_task_respects_baseline_probe(self) -> None:
        """Baseline >= 0.8 degrada el voting a 1 sola pasada (sin gate)."""
        from harness.orchestrator.parallel_executor import (
            ParallelExecutor,
            ParallelTask,
        )

        ex = ParallelExecutor(provider=_FakeProvider(), router=_FakeRouter(score=80.0, confidence=0.6))
        outcome = ex.vote_on_task(
            ParallelTask(id="t1", prompt="ambigua"),
            baseline_success=0.85,
        )
        assert outcome.gate_applied is False  # sin voting (anti-fanout)
        assert outcome.winner is not None     # 1 pasada responde
        assert outcome.total_tokens < 500     # costo de UNA llamada, no N

    def test_planner_boundary_exact_threshold(self, monkeypatch) -> None:
        """_degrade_if_strong con rate == threshold EXACTO degrada (gate >=).

        Test unitario del metodo (sin depender del learned path): con >=
        degrada a SINGLE; con > (mutante) no degrada y retorna la multi.
        """
        from harness.orchestrator import adaptive_planner as ap_pkg
        from harness.orchestrator.adaptive_planner.core import (
            AdaptivePlanner,
            PlanStrategy,
        )
        from harness.orchestrator.adaptive_planner.models import PlanFeedback

        planner = AdaptivePlanner()
        for i in range(8):
            planner.record_feedback(PlanFeedback(
                session_id="s", task_hash=f"b{i}", task_type="implement",
                strategy_used=PlanStrategy.SINGLE_AGENT,
                subtask_count=1, level_count=1,
                success_count=1, failure_count=0,
                total_duration_ms=50.0, success_rate=1.0,
            ))
        for i in range(2):
            planner.record_feedback(PlanFeedback(
                session_id="s", task_hash=f"bf{i}", task_type="implement",
                strategy_used=PlanStrategy.SINGLE_AGENT,
                subtask_count=1, level_count=1,
                success_count=0, failure_count=1,
                total_duration_ms=50.0, success_rate=0.0,
            ))
        real_rate = planner._strategy_stats["single_agent"].avg_success_rate
        assert 0.79 <= real_rate <= 0.81
        monkeypatch.setattr(ap_pkg.core, "SINGLE_AGENT_THRESHOLD", real_rate)
        result = planner._degrade_if_strong(PlanStrategy.HYBRID)
        assert result is PlanStrategy.SINGLE_AGENT
        # y el caso trivial: SINGLE se mantiene SINGLE
        assert planner._degrade_if_strong(PlanStrategy.SINGLE_AGENT) is PlanStrategy.SINGLE_AGENT

    def test_vote_on_task_without_probe_unchanged(self) -> None:
        """Sin probe, el gate score/confidence decide como siempre."""
        from harness.orchestrator.parallel_executor import (
            ParallelExecutor,
            ParallelTask,
        )

        ex = ParallelExecutor(provider=_FakeProvider(), router=_FakeRouter(score=80.0, confidence=0.6))
        outcome = ex.vote_on_task(ParallelTask(id="t1", prompt="ambigua"))
        assert outcome.gate_applied is True

    def test_planner_degrades_strong_multi(self) -> None:
        """Planner: baseline SINGLE >= 0.8 degrada la multi a SINGLE_AGENT."""
        from harness.orchestrator.adaptive_planner.core import (
            AdaptivePlanner,
            PlanStrategy,
        )
        from harness.orchestrator.adaptive_planner.models import PlanFeedback

        planner = AdaptivePlanner()
        # Baseline single-agent fuerte (probe con exito) + multi con exito:
        # el gate compara contra el BASELINE single (no contra el multi).
        for i in range(10):
            planner.record_feedback(PlanFeedback(
                session_id="s", task_hash=f"h{i}", task_type="implement",
                strategy_used=PlanStrategy.SINGLE_AGENT,
                subtask_count=1, level_count=1,
                success_count=1, failure_count=0,
                total_duration_ms=50.0, success_rate=1.0,
            ))
        for i in range(10):
            planner.record_feedback(PlanFeedback(
                session_id="s", task_hash=f"m{i}", task_type="implement",
                strategy_used=PlanStrategy.HYBRID,
                subtask_count=2, level_count=1,
                success_count=1, failure_count=0,
                total_duration_ms=100.0, success_rate=1.0,
            ))
        strategy = planner.choose_strategy(
            "implementa el modulo completo con arquitectura", task_type="implement"
        )
        assert strategy is PlanStrategy.SINGLE_AGENT
