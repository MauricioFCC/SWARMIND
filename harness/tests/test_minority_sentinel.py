"""Tests para MinoritySentinel — mayoria revertible (ACL 2026).

Frontera: el debate vanilla pierde frente a majority-vote; el
meta-clasificador que revierte la mayoria ~1/4 de las veces mejora el
resultado. Estos tests cubren el contrato del sentinel (determinista, DI del
``override_fn``) y su integracion opcional con ``DebateOrchestrator`` sin
LLM real (dispatch mockeado).

Casos:
    (a) mayoria con acuerdo alto -> NO revierte (keep majority).
    (b) mayoria con acuerdo bajo + minoria con apoyo suficiente -> revierte.
    (c) ``override_signal=True`` -> revierte aunque el acuerdo sea alto.
    (d) sin minoria (todas iguales) -> nunca revierte.
    (e) ``agreement`` calcula la fraccion correcta del grupo mayoritario.
    (f) sentinela de mutacion: quitar la condicion de acuerdo minimo rompe
        el test (2 asserts observables).
    (g) DI: el ``override_fn`` inyectado se usa (spy).
"""

from __future__ import annotations

from typing import Any

import pytest

from harness.orchestrator.debate_orchestrator import (
    DebateOrchestrator,
    DebateStrategy,
)
from harness.orchestrator.minority_sentinel import (
    DEFAULT_MIN_AGREEMENT,
    DEFAULT_OVERRIDE_THRESHOLD,
    MinoritySentinel,
    SentinelVerdict,
)


class _SpyOverride:
    """Spy de ``override_fn`` que registra cada invocacion (DI observable)."""

    def __init__(self, result: bool) -> None:
        """Inicializa el spy con el veredicto a devolver.

        Args:
            result: Valor booleano que retorna cada llamada.
        """
        self.result = result
        self.calls: list[tuple[str, list[str]]] = []

    def __call__(self, majority_answer: str, all_answers: list[str]) -> bool:
        """Registra la llamada y devuelve ``result``.

        Args:
            majority_answer: Respuesta mayoritaria recibida.
            all_answers: Respuestas individuales recibidas.

        Returns:
            El valor ``result`` configurado en el constructor.
        """
        self.calls.append((majority_answer, list(all_answers)))
        return self.result


# ---------------------------------------------------------------------------
# (e) agreement
# ---------------------------------------------------------------------------


class TestAgreement:
    """Verifica el calculo de la fraccion del grupo mayoritario."""

    def test_agreement_fraction(self) -> None:
        """La fraccion es el conteo del grupo mayoritario sobre el total."""
        assert MinoritySentinel.agreement(["a", "a", "b"]) == pytest.approx(2 / 3)
        assert MinoritySentinel.agreement(["a", "b", "b", "b"]) == pytest.approx(0.75)
        assert MinoritySentinel.agreement(["x"]) == pytest.approx(1.0)

    def test_agreement_empty_is_zero(self) -> None:
        """Sin respuestas la fraccion es 0.0 (no explota)."""
        assert MinoritySentinel.agreement([]) == pytest.approx(0.0)

    def test_agreement_tie_uses_largest_group(self) -> None:
        """En empate usa el grupo mas grande como mayoria (determinista)."""
        assert MinoritySentinel.agreement(["a", "b"]) == pytest.approx(0.5)


# ---------------------------------------------------------------------------
# (a)-(d) heuristicas de review
# ---------------------------------------------------------------------------


class TestReviewHeuristics:
    """Verifica las decisiones heuristicas y por senal explicita."""

    def test_high_agreement_keeps_majority(self) -> None:
        """(a) Acuerdo alto (0.9) -> NO revierte; conserva la mayoria."""
        sentinel = MinoritySentinel()
        answers = ["A"] * 9 + ["B"]
        verdict = sentinel.review("A", answers)
        assert verdict.reverted is False
        assert verdict.final_answer == "A"
        assert verdict.majority_answer == "A"
        assert verdict.minority_answer == "B"

    def test_low_agreement_reverts_to_minority(self) -> None:
        """(b) Acuerdo bajo (0.5) + minoria 0.3 -> revierte a la minoria."""
        sentinel = MinoritySentinel()
        answers = ["A"] * 5 + ["B"] * 3 + ["C"] * 2
        verdict = sentinel.review("A", answers)
        assert verdict.reverted is True
        assert verdict.final_answer == "B"
        assert verdict.minority_answer == "B"
        assert verdict.confidence == pytest.approx(0.3)

    def test_override_signal_true_forces_revert(self) -> None:
        """(c) override_signal=True revierte aun con acuerdo alto (0.9)."""
        sentinel = MinoritySentinel()
        answers = ["A"] * 9 + ["B"]
        verdict = sentinel.review("A", answers, override_signal=True)
        assert verdict.reverted is True
        assert verdict.final_answer == "B"
        assert "override" in verdict.reason

    def test_override_signal_false_keeps_majority(self) -> None:
        """override_signal=False conserva la mayoria aunque el acuerdo sea bajo."""
        sentinel = MinoritySentinel()
        answers = ["A"] * 5 + ["B"] * 3 + ["C"] * 2
        verdict = sentinel.review("A", answers, override_signal=False)
        assert verdict.reverted is False
        assert verdict.final_answer == "A"

    def test_no_minority_never_reverts(self) -> None:
        """(d) Sin minoria (todas iguales) -> nunca revierte, ni con override."""
        sentinel = MinoritySentinel()
        answers = ["A"] * 5
        verdict = sentinel.review("A", answers, override_signal=True)
        assert verdict.reverted is False
        assert verdict.final_answer == "A"
        assert verdict.minority_answer is None

    def test_strongest_minority_tie_is_deterministic(self) -> None:
        """Empate de minoria -> la respuesta mas larga (determinista)."""
        sentinel = MinoritySentinel()
        answers = ["A"] * 5 + ["Bee"] * 2 + ["C"] * 2
        verdict = sentinel.review("A", answers, override_signal=True)
        assert verdict.minority_answer == "Bee"

    def test_verdict_is_frozen(self) -> None:
        """SentinelVerdict es inmutable (frozen dataclass)."""
        sentinel = MinoritySentinel()
        verdict = sentinel.review("A", ["A", "A", "B"])
        with pytest.raises(AttributeError):
            verdict.reverted = True  # type: ignore[misc]


# ---------------------------------------------------------------------------
# (f) sentinela de mutacion
# ---------------------------------------------------------------------------


class TestMutationSentinel:
    """Sentinela de mutacion: la condicion de acuerdo minimo es observable."""

    def test_min_agreement_blocks_revert_even_with_strong_minority(self) -> None:
        """(f) Acuerdo 0.7 >= 0.66 con minoria 0.3 -> NO revierte.

        Mutacion: si se elimina la condicion ``majority_agreement <
        min_agreement`` de la heuristica, el sentinel revertiria (la minoria
        supera el override_threshold) y los DOS asserts fallarian.
        """
        sentinel = MinoritySentinel()
        answers = ["A"] * 7 + ["B"] * 3  # agreement=0.7, minoria=0.3
        verdict = sentinel.review("A", answers)
        # Si se muta la heuristica quitando el acuerdo minimo, ambos fallan:
        assert verdict.reverted is False
        assert verdict.final_answer == "A"


# ---------------------------------------------------------------------------
# (g) DI del meta-clasificador
# ---------------------------------------------------------------------------


class TestOverrideFnDI:
    """Verifica la inyeccion del meta-clasificador ``override_fn``."""

    def test_injected_override_fn_is_used(self) -> None:
        """(g) override_fn=True se invoca (spy) y revierte a la minoria."""
        spy = _SpyOverride(result=True)
        sentinel = MinoritySentinel(override_fn=spy)
        answers = ["A"] * 9 + ["B"]
        verdict = sentinel.review("A", answers)
        assert verdict.reverted is True
        assert verdict.final_answer == "B"
        assert len(spy.calls) == 1
        assert spy.calls[0] == ("A", answers)

    def test_injected_override_fn_false_keeps(self) -> None:
        """override_fn=False conserva la mayoria (DI se respeta)."""
        spy = _SpyOverride(result=False)
        sentinel = MinoritySentinel(override_fn=spy)
        verdict = sentinel.review("A", ["A"] * 5 + ["B"] * 3 + ["C"] * 2)
        assert verdict.reverted is False
        assert verdict.final_answer == "A"
        assert len(spy.calls) == 1

    def test_explicit_signal_has_precedence_over_override_fn(self) -> None:
        """override_signal explicito gana; no se consulta el override_fn."""
        spy = _SpyOverride(result=True)
        sentinel = MinoritySentinel(override_fn=spy)
        verdict = sentinel.review("A", ["A"] * 9 + ["B"], override_signal=False)
        assert verdict.reverted is False
        assert spy.calls == []


# ---------------------------------------------------------------------------
# Constantes y validacion (fail-fast)
# ---------------------------------------------------------------------------


class TestConfiguration:
    """Verifica constantes con nombre y validacion fail-fast."""

    def test_default_constants(self) -> None:
        """Las constantes por defecto reflejan ~1/4 y 0.66 (ACL 2026)."""
        assert DEFAULT_OVERRIDE_THRESHOLD == pytest.approx(0.25)
        assert DEFAULT_MIN_AGREEMENT == pytest.approx(0.66)

    def test_invalid_threshold_raises(self) -> None:
        """Umbrales fuera de [0, 1] fallan con ValueError accionable."""
        with pytest.raises(ValueError, match="WHAT"):
            MinoritySentinel(override_threshold=1.5)
        with pytest.raises(ValueError, match="WHAT"):
            MinoritySentinel(min_agreement=-0.1)

    def test_non_callable_override_fn_raises(self) -> None:
        """Un override_fn no invocable falla con ValueError accionable."""
        with pytest.raises(ValueError, match="WHAT"):
            MinoritySentinel(override_fn="no-soy-callable")  # type: ignore[arg-type]

    def test_review_validates_input(self) -> None:
        """Entradas invalidas de review fallan con ValueError accionable."""
        sentinel = MinoritySentinel()
        with pytest.raises(ValueError, match="WHAT"):
            sentinel.review("A", [])
        with pytest.raises(ValueError, match="WHAT"):
            sentinel.review("", ["A", "B"])
        with pytest.raises(ValueError, match="WHAT"):
            sentinel.review("Z", ["A", "B"])


# ---------------------------------------------------------------------------
# Integracion opcional (DI) con DebateOrchestrator — backward-compat
# ---------------------------------------------------------------------------


def _four_agent_dispatch() -> Any:
    """Dispatch determinista: 2 'Rust', 1 'Go', 1 'Python' (sin overlap)."""

    def _dispatch(agent: str, task: str, context: dict[str, Any]) -> str:
        mapping = {"a": "Rust", "b": "Rust", "c": "Go", "d": "Python"}
        return mapping[agent]

    return _dispatch


class TestDebateIntegration:
    """Integracion opcional: sin sentinel = comportamiento actual."""

    def test_backward_compat_without_sentinel(self) -> None:
        """Sin sentinel inyectado la mayoria no se revierte (backward-compat)."""
        orch = DebateOrchestrator(vector_store=None)
        result = orch.debate(
            task="Pick language",
            agents=["a", "b", "c", "d"],
            strategy=DebateStrategy.CONSENSUS,
            max_rounds=1,
            dispatch_fn=_four_agent_dispatch(),
        )
        assert result.final_answer == "Rust"

    def test_sentinel_injected_reverts_majority(self) -> None:
        """Con sentinel inyectado la mayoria debil se revierte a la minoria."""
        sentinel = MinoritySentinel()
        orch = DebateOrchestrator(vector_store=None, sentinel=sentinel)
        result = orch.debate(
            task="Pick language",
            agents=["a", "b", "c", "d"],
            strategy=DebateStrategy.CONSENSUS,
            max_rounds=1,
            dispatch_fn=_four_agent_dispatch(),
        )
        assert result.final_answer == "Python"


class TestSentinelVerdictShape:
    """Verifica la forma del dataclass de veredicto."""

    def test_fields_present(self) -> None:
        """SentinelVerdict expone todos los campos del contrato."""
        sentinel = MinoritySentinel()
        verdict = sentinel.review("A", ["A", "A", "B"])
        assert isinstance(verdict, SentinelVerdict)
        assert verdict.majority_answer == "A"
        assert verdict.minority_answer == "B"
        assert isinstance(verdict.reason, str)
        assert 0.0 <= verdict.confidence <= 1.0
