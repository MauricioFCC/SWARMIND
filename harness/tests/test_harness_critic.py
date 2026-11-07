"""Tests TDD de Harness Critic (marco de frontera Co-Harness, arXiv:2607.22688).

Contrato RED→GREEN del atribuidor de fallos a causas harness-level y del loop
de diffs locales validados con Pareto accuracy x wall-clock:

  (a) ``analyze`` clasifica 5+ mensajes de ejemplo en su categoria correcta.
  (b) ``propose`` agrupa por causa y devuelve 1 diff por causa con target/change.
  (c) ``validate`` acepta una mejora real y RECHAZA una regresion de held-out
      (rollback safety / Pareto-aware).
  (d) ``pareto_accept``: rechaza (peor accuracy, peor tiempo); acepta (mejor
      accuracy, mismo tiempo); acepta (misma accuracy, mejor tiempo).
  (e) oraculo de mutacion: quitar la condicion de held-out rompe el assert.
  (f) el classifier inyectado (spy) se usa para clasificar.

Aislamiento: todo es puro/determinista; el CLI se prueba con un registry
temporal en ``tmp_path`` (NUNCA toca ``harness/db/failures.jsonl`` real).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

#: ``scripts/`` esta fuera de ``harness/`` -> se agrega al path de import.
_SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"
sys.path.insert(1, str(_SCRIPTS))

import harness_critic as cli

from harness.evolve_loop.harness_critic import (
    HarnessCause,
    HarnessCritic,
    HarnessDiff,
)
from harness.failure_registry.registry import FailureRegistry, FailureType

#: Mensajes de ejemplo (deterministas) y su categoria esperada.
_EXAMPLES: tuple[tuple[str, str], ...] = (
    ("Tool schema validation failed: unexpected key 'foo'", "tool_schema_error"),
    ("Context window overflow: 9000 tokens exceed 8192", "context_overflow"),
    ("skill 'pdf-forms' not found in registry", "missing_skill"),
    ("request blocked by guardrail policy", "guardrail_gap"),
    ("middleware mismatch in router dispatch", "middleware_mismatch"),
    ("ambiguous objective: clarify the request", "prompt_ambiguity"),
)


def _sample_diff(critic: HarnessCritic | None = None) -> HarnessDiff:
    """Construye un ``HarnessDiff`` de ejemplo a partir de un fallo de schema.

    Args:
        critic: Critic opcional; si es None se usa uno por defecto.

    Returns:
        Diff no validado con causa ``tool_schema_error``.
    """
    critic = critic or HarnessCritic()
    cause = critic.analyze("Tool schema validation failed")
    return HarnessDiff(
        cause=cause,
        target="tool_schema",
        change=cause.proposal,
        validated=False,
        regression_risk=0.2,
    )


class TestAnalyze:
    """(a) clasificacion determinista de mensajes de fallo."""

    @pytest.mark.parametrize(("message", "expected"), _EXAMPLES)
    def test_clasifica_cada_ejemplo(self, message: str, expected: str) -> None:
        """Cada mensaje de ejemplo cae en su categoria harness-level."""
        cause = HarnessCritic().analyze(message)

        assert isinstance(cause, HarnessCause)
        assert cause.category == expected
        assert cause.evidence != ""
        assert cause.proposal != ""
        assert 0.0 < cause.confidence <= 1.0

    def test_default_es_prompt_ambiguity(self) -> None:
        """Un mensaje sin patron harness-level cae al default prompt_ambiguity."""
        cause = HarnessCritic().analyze("the objective was unclear")

        assert cause.category == "prompt_ambiguity"

    def test_evidence_es_el_fragmento_que_matcheo(self) -> None:
        """La evidencia reproduce el fragmento del mensaje que disparo la causa."""
        cause = HarnessCritic().analyze("Tool schema validation failed")

        assert cause.evidence.lower() in {"schema", "validation"}

    def test_componente_se_incluye_en_la_propuesta(self) -> None:
        """El componente opcional aparece en la propuesta de accion local."""
        cause = HarnessCritic().analyze(
            "Tool schema validation failed", component="mcp/filesystem"
        )

        assert "mcp/filesystem" in cause.proposal


class TestPropose:
    """(b) agrupacion por causa -> 1 diff local por causa."""

    def test_agrupa_por_causa_y_devuelve_un_diff_por_causa(self) -> None:
        """Tres mensajes, dos causas -> 2 diffs con target/change no vacios."""
        failures = [
            "Tool schema validation failed: field x",
            "Tool schema validation failed: field y",
            "Context window overflow: 9000 tokens",
        ]

        diffs = HarnessCritic().propose(failures)

        assert len(diffs) == 2
        categories = {diff.cause.category for diff in diffs}
        assert categories == {"tool_schema_error", "context_overflow"}
        for diff in diffs:
            assert diff.target != ""
            assert diff.change != ""
            assert diff.validated is False
            assert 0.0 <= diff.regression_risk <= 1.0

    def test_lista_vacia_no_propone_nada(self) -> None:
        """Sin fallos no se proponen diffs."""
        assert HarnessCritic().propose([]) == []


class TestValidate:
    """(c) validacion Pareto-aware con seguridad de rollback."""

    def test_acepta_mejora_real(self) -> None:
        """after > before y held-out sin regresion -> validated=True."""
        diff = _sample_diff()

        result = HarnessCritic().validate(
            diff, before_score=0.50, after_score=0.60, held_out_delta=0.0
        )

        assert result.validated is True

    def test_rechaza_regresion_de_held_out(self) -> None:
        """after > before pero held-out cae fuera de tolerancia -> False."""
        diff = _sample_diff()

        result = HarnessCritic().validate(
            diff,
            before_score=0.50,
            after_score=0.60,
            held_out_delta=-0.40,
            regression_tolerance=0.0,
        )

        assert result.validated is False

    def test_rechaza_sin_mejora(self) -> None:
        """Sin mejora (after <= before) -> validated=False."""
        diff = _sample_diff()

        result = HarnessCritic().validate(diff, before_score=0.60, after_score=0.60)

        assert result.validated is False

    def test_tolerancia_de_regresion_permite_caida_pequena(self) -> None:
        """Una caida de held-out dentro de la tolerancia no bloquea la mejora."""
        diff = _sample_diff()

        result = HarnessCritic().validate(
            diff,
            before_score=0.50,
            after_score=0.60,
            held_out_delta=-0.10,
            regression_tolerance=0.20,
        )

        assert result.validated is True


class TestParetoAccept:
    """(d) frontera accuracy x wall-clock."""

    def test_rechaza_peor_accuracy_peor_tiempo(self) -> None:
        """Degrada ambos ejes -> rechazado."""
        accepted, reason = HarnessCritic.pareto_accept(
            accuracy_before=0.80,
            accuracy_after=0.70,
            wall_clock_before=10.0,
            wall_clock_after=14.0,
        )

        assert accepted is False
        assert reason != ""

    def test_acepta_mejor_accuracy_mismo_tiempo(self) -> None:
        """Sube accuracy sin costo de tiempo -> aceptado."""
        accepted, _ = HarnessCritic.pareto_accept(
            accuracy_before=0.80,
            accuracy_after=0.90,
            wall_clock_before=10.0,
            wall_clock_after=10.0,
        )

        assert accepted is True

    def test_acepta_misma_accuracy_mejor_tiempo(self) -> None:
        """Mantiene accuracy y baja wall-clock -> aceptado."""
        accepted, _ = HarnessCritic.pareto_accept(
            accuracy_before=0.80,
            accuracy_after=0.80,
            wall_clock_before=10.0,
            wall_clock_after=7.0,
        )

        assert accepted is True


class TestMutationOracle:
    """(e) oraculo de mutacion: la condicion de held-out es discriminante."""

    def test_held_out_guard_es_discriminante(self) -> None:
        """Sin el guard de held-out, una mejora con regresion oculta pasaria.

        Escenario: before=0.50 -> after=0.60 (mejora) pero held_out_delta=-0.50
        (regresion grave). El mutante que elimina el termino
        ``held_out_delta >= -regression_tolerance`` marcaria ``validated=True``;
        este assert lo detecta.
        """
        diff = _sample_diff()

        result = HarnessCritic().validate(
            diff,
            before_score=0.50,
            after_score=0.60,
            held_out_delta=-0.50,
            regression_tolerance=0.0,
        )

        assert result.validated is False


class TestClassifierDI:
    """(f) inyeccion de dependencia del classifier."""

    def test_classifier_inyectado_se_usa(self) -> None:
        """Un classifier inyectado (spy) determina la categoria."""
        calls: list[str] = []

        def spy(message: str) -> str:
            calls.append(message)
            return "missing_skill"

        cause = HarnessCritic(classifier=spy).analyze("mensaje arbitrario")

        assert cause.category == "missing_skill"
        assert calls == ["mensaje arbitrario"]

    def test_classifier_mock_se_invoca(self) -> None:
        """El classifier inyectado recibe el mensaje del fallo (MagicMock)."""
        classifier = MagicMock(return_value="guardrail_gap")

        cause = HarnessCritic(classifier=classifier).analyze("cualquier cosa")

        classifier.assert_called_once_with("cualquier cosa")
        assert cause.category == "guardrail_gap"


class TestCli:
    """Integracion: el CLI lee el registry y emite diffs sugeridos (dry-run)."""

    def _registry(self, tmp_path: Path) -> FailureRegistry:
        """Crea un registry temporal con dos fallos de causas distintas."""
        registry = FailureRegistry(path=tmp_path / "failures.jsonl")
        registry.record(
            task="t1",
            failure_type=FailureType.RUNTIME,
            error_msg="Tool schema validation failed: field x",
            root_cause="schema drift",
            resolution="pending",
        )
        registry.record(
            task="t2",
            failure_type=FailureType.RUNTIME,
            error_msg="Context window overflow: 9000 tokens",
            root_cause="ctx too big",
            resolution="pending",
        )
        return registry

    def test_json_es_parseable(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """``--json`` emite JSON parseable con un diff por causa."""
        registry = self._registry(tmp_path)

        code = cli.main(["--json"], registry=registry)
        payload = json.loads(capsys.readouterr().out)

        assert code == 0
        assert payload["dry_run"] is True
        assert payload["count"] == 2

    def test_no_aplica_cambios(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """El CLI solo propone: no escribe archivos ni modifica el registry."""
        registry = self._registry(tmp_path)
        before = (tmp_path / "failures.jsonl").read_text(encoding="utf-8")

        cli.main(["--json"], registry=registry)
        capsys.readouterr()

        after = (tmp_path / "failures.jsonl").read_text(encoding="utf-8")
        assert before == after
