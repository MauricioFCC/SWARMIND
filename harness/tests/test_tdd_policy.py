"""
test_tdd_policy.py - Tests para TDDPolicyEngine (H1, arXiv 2604.26615).

El motor de politicas TDD es la autoridad que GARANTIZA que SWARMIND use TDD
estricto (test primero) bajo el patron "model proposes, engine disposes".
Cubre: gate por fase (RED/GREEN/REFACTOR), test-first real, anti-gaming por
hash de tests, completitud 100%, umbrales de mutation y branch, validacion de
PolicyContext, hash_tests y la API corta can_emit_done.
"""

from __future__ import annotations

from typing import Any

import pytest

from harness.orchestrator.workflows.tdd_policy import (
    PolicyContext,
    PolicyVerdict,
    TDDPolicyEngine,
)
from harness.orchestrator.workflows.tdd_strict import TDDPhase

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _green_ctx(**overrides: Any) -> PolicyContext:
    """Contexto GREEN valido por defecto: solo implementacion en src/."""
    defaults: dict[str, Any] = {
        "task_id": "task-1",
        "phase": TDDPhase.GREEN,
        "test_files_modified": False,
        "src_files_modified": True,
        "tests_passed": 0,
        "tests_total": 0,
        "mutation_score": 0.0,
        "branch_coverage": 0.0,
        "red_evidence": True,
        "tests_hash_red": None,
        "tests_hash_now": None,
    }
    defaults.update(overrides)
    return PolicyContext(**defaults)


# ---------------------------------------------------------------------------
# Gate por fase
# ---------------------------------------------------------------------------


def test_gate_blocks_red_when_src_modified() -> None:
    """En RED el gate bloquea si se modifico src/ (prohibido implementar)."""
    verdict = TDDPolicyEngine().evaluate(
        _green_ctx(phase=TDDPhase.RED, test_files_modified=True, src_files_modified=True)
    )

    assert verdict.allowed is False
    assert any("RED" in reason and "src/" in reason for reason in verdict.reasons)


def test_gate_allows_red_with_only_tests_modified() -> None:
    """En RED escribir solo tests es la tarea correcta y el gate lo permite."""
    verdict = TDDPolicyEngine().evaluate(
        _green_ctx(phase=TDDPhase.RED, test_files_modified=True, src_files_modified=False)
    )

    assert verdict.allowed is True


def test_gate_blocks_green_when_tests_modified() -> None:
    """En GREEN tocar tests esta prohibido: el gate bloquea."""
    verdict = TDDPolicyEngine().evaluate(_green_ctx(test_files_modified=True, src_files_modified=True))

    assert verdict.allowed is False
    assert any("GREEN" in reason for reason in verdict.reasons)


def test_gate_allows_green_with_src_modified_and_red_evidence() -> None:
    """En GREEN implementar en src/ con evidencia RED es correcto y pasa."""
    verdict = TDDPolicyEngine().evaluate(_green_ctx(test_files_modified=False, src_files_modified=True))

    assert verdict.allowed is True


def test_gate_blocks_refactor_when_tests_modified() -> None:
    """En REFACTOR tocar tests es una violacion y el gate bloquea."""
    verdict = TDDPolicyEngine().evaluate(
        _green_ctx(phase=TDDPhase.REFACTOR, test_files_modified=True, src_files_modified=False)
    )

    assert verdict.allowed is False
    assert any("REFACTOR" in reason for reason in verdict.reasons)


# ---------------------------------------------------------------------------
# Test-first real (evidencia de RED)
# ---------------------------------------------------------------------------


def test_test_first_blocks_green_without_red_evidence() -> None:
    """En GREEN sin red_evidence el gate bloquea con 'sin_evidencia_red'."""
    verdict = TDDPolicyEngine().evaluate(_green_ctx(red_evidence=False))

    assert verdict.allowed is False
    assert any("sin_evidencia_red" in reason for reason in verdict.reasons)


def test_test_first_blocks_refactor_without_red_evidence() -> None:
    """En REFACTOR sin red_evidence el gate bloquea con 'sin_evidencia_red'."""
    verdict = TDDPolicyEngine().evaluate(_green_ctx(phase=TDDPhase.REFACTOR, red_evidence=False))

    assert verdict.allowed is False
    assert any("sin_evidencia_red" in reason for reason in verdict.reasons)


def test_test_first_not_required_in_red() -> None:
    """En RED no se exige red_evidence (aun no hay implementacion que probar)."""
    verdict = TDDPolicyEngine().evaluate(
        _green_ctx(phase=TDDPhase.RED, test_files_modified=True, src_files_modified=False, red_evidence=False)
    )

    assert verdict.allowed is True


# ---------------------------------------------------------------------------
# Anti-gaming: los tests no pueden cambiar entre RED y DONE
# ---------------------------------------------------------------------------


def test_anti_gaming_blocks_when_hashes_differ() -> None:
    """Si el hash actual de tests difiere del de RED se bloquea."""
    verdict = TDDPolicyEngine().evaluate(_green_ctx(tests_hash_red="aaa", tests_hash_now="bbb"))

    assert verdict.allowed is False
    assert any("tests_modificados_entre_fases" in reason for reason in verdict.reasons)


def test_anti_gaming_allows_when_hashes_match() -> None:
    """Si los hashes coinciden (mismos tests) el gate lo permite."""
    verdict = TDDPolicyEngine().evaluate(_green_ctx(tests_hash_red="abc123", tests_hash_now="abc123"))

    assert verdict.allowed is True


def test_anti_gaming_skipped_when_no_hashes() -> None:
    """Sin hashes registrados el check anti-gaming no bloquea."""
    verdict = TDDPolicyEngine().evaluate(_green_ctx(tests_hash_red=None, tests_hash_now=None))

    assert verdict.allowed is True


# ---------------------------------------------------------------------------
# Completitud: 100% de tests verdes
# ---------------------------------------------------------------------------


def test_completitud_blocks_when_tests_fail() -> None:
    """Si tests_passed < tests_total el gate bloquea con 'tests_no_verdes'."""
    verdict = TDDPolicyEngine().evaluate(_green_ctx(tests_passed=3, tests_total=5))

    assert verdict.allowed is False
    assert any("tests_no_verdes" in reason for reason in verdict.reasons)


def test_completitud_allows_when_100_percent() -> None:
    """Con el 100% de tests aprobados el gate lo permite."""
    verdict = TDDPolicyEngine().evaluate(_green_ctx(tests_passed=5, tests_total=5))

    assert verdict.allowed is True


def test_completitud_skipped_when_no_tests() -> None:
    """Con tests_total=0 el check de completitud no bloquea."""
    verdict = TDDPolicyEngine().evaluate(_green_ctx(tests_passed=0, tests_total=0))

    assert verdict.allowed is True


# ---------------------------------------------------------------------------
# Mutation score
# ---------------------------------------------------------------------------


def test_mutation_blocks_below_threshold() -> None:
    """Mutation score < 85 bloquea con 'mutation_bajo_umbral'."""
    verdict = TDDPolicyEngine().evaluate(_green_ctx(mutation_score=70.0))

    assert verdict.allowed is False
    assert any("mutation_bajo_umbral" in reason for reason in verdict.reasons)


def test_mutation_allows_at_threshold() -> None:
    """Mutation score = 85.0 (umbral) es suficiente y pasa."""
    verdict = TDDPolicyEngine().evaluate(_green_ctx(mutation_score=85.0))

    assert verdict.allowed is True


def test_mutation_above_threshold_allowed() -> None:
    """Mutation score >= 85 pasa el gate."""
    verdict = TDDPolicyEngine().evaluate(_green_ctx(mutation_score=92.4))

    assert verdict.allowed is True


def test_mutation_zero_does_not_block() -> None:
    """Mutation score 0 (no evaluado) no bloquea."""
    verdict = TDDPolicyEngine().evaluate(_green_ctx(mutation_score=0.0))

    assert verdict.allowed is True


# ---------------------------------------------------------------------------
# Branch coverage
# ---------------------------------------------------------------------------


def test_branch_blocks_below_threshold() -> None:
    """Branch coverage < 80 bloquea con 'branch_bajo_umbral'."""
    verdict = TDDPolicyEngine().evaluate(_green_ctx(branch_coverage=55.0))

    assert verdict.allowed is False
    assert any("branch_bajo_umbral" in reason for reason in verdict.reasons)


def test_branch_allows_at_threshold() -> None:
    """Branch coverage = 80.0 (umbral) es suficiente y pasa."""
    verdict = TDDPolicyEngine().evaluate(_green_ctx(branch_coverage=80.0))

    assert verdict.allowed is True


def test_branch_above_threshold_allowed() -> None:
    """Branch coverage >= 80 pasa el gate."""
    verdict = TDDPolicyEngine().evaluate(_green_ctx(branch_coverage=95.0))

    assert verdict.allowed is True


def test_branch_zero_does_not_block() -> None:
    """Branch coverage 0 (no evaluado) no bloquea."""
    verdict = TDDPolicyEngine().evaluate(_green_ctx(branch_coverage=0.0))

    assert verdict.allowed is True


# ---------------------------------------------------------------------------
# Veredicto global: trazabilidad y acumulacion
# ---------------------------------------------------------------------------


def test_full_green_verdict_allowed_with_summary() -> None:
    """Un contexto completamente verde produce allowed=True y summary legible."""
    engine = TDDPolicyEngine()
    verdict = engine.evaluate(_green_ctx())

    assert verdict.allowed is True
    assert isinstance(verdict, PolicyVerdict)
    assert verdict.summary()
    assert "APROBADO" in verdict.summary()


def test_multiple_blocks_accumulate_reasons() -> None:
    """Un contexto con 2+ violaciones reporta todas las razones acumuladas."""
    verdict = TDDPolicyEngine().evaluate(
        _green_ctx(
            red_evidence=False,
            tests_passed=1,
            tests_total=2,
            mutation_score=40.0,
            branch_coverage=30.0,
        )
    )

    assert verdict.allowed is False
    assert len(verdict.reasons) >= 2
    assert any("sin_evidencia_red" in reason for reason in verdict.reasons)
    assert any("tests_no_verdes" in reason for reason in verdict.reasons)


def test_gate_checks_record_all_checks_executed() -> None:
    """El veredicto registra todos los checks ejecutados para trazabilidad."""
    checks = TDDPolicyEngine().evaluate(_green_ctx()).gate_checks

    assert "fase" in checks
    assert "test_first" in checks
    assert "anti_gaming" in checks
    assert "completitud" in checks
    assert "mutation" in checks
    assert "branch" in checks


# ---------------------------------------------------------------------------
# PolicyContext: validacion de invariantes
# ---------------------------------------------------------------------------


def test_context_rejects_empty_task_id() -> None:
    """task_id vacio invalida el contexto."""
    with pytest.raises(ValueError):
        _green_ctx(task_id="")


def test_context_rejects_mutation_above_100() -> None:
    """mutation_score > 100 invalida el contexto."""
    with pytest.raises(ValueError):
        _green_ctx(mutation_score=101.0)


def test_context_rejects_negative_mutation() -> None:
    """mutation_score < 0 invalida el contexto."""
    with pytest.raises(ValueError):
        _green_ctx(mutation_score=-1.0)


def test_context_rejects_negative_tests_total() -> None:
    """tests_total < 0 invalida el contexto."""
    with pytest.raises(ValueError):
        _green_ctx(tests_total=-1)


def test_context_rejects_negative_branch_coverage() -> None:
    """branch_coverage < 0 invalida el contexto."""
    with pytest.raises(ValueError):
        _green_ctx(branch_coverage=-0.5)


def test_context_accepts_boundary_values() -> None:
    """Los valores limite 0 y 100 son validos en el contexto."""
    ctx = _green_ctx(mutation_score=100.0, branch_coverage=100.0)

    assert ctx.mutation_score == 100.0
    assert ctx.branch_coverage == 100.0


# ---------------------------------------------------------------------------
# hash_tests: firma sha256 del contenido
# ---------------------------------------------------------------------------


def test_hash_tests_stable_for_same_content(tmp_path: Any) -> None:
    """El mismo contenido produce el mismo hash aunque sea otro archivo."""
    first = tmp_path / "test_a.py"
    first.write_text("def test_x(): pass\n", encoding="utf-8")
    second = tmp_path / "test_b.py"
    second.write_text("def test_x(): pass\n", encoding="utf-8")
    engine = TDDPolicyEngine()

    assert engine.hash_tests((str(first),)) == engine.hash_tests((str(second),))


def test_hash_tests_changes_with_content(tmp_path: Any) -> None:
    """Contenido distinto produce hash distinto."""
    first = tmp_path / "test_a.py"
    first.write_text("def test_x(): pass\n", encoding="utf-8")
    second = tmp_path / "test_b.py"
    second.write_text("def test_y(): pass\n", encoding="utf-8")

    assert TDDPolicyEngine.hash_tests((str(first),)) != TDDPolicyEngine.hash_tests((str(second),))


def test_hash_tests_missing_file_raises_clear_error(tmp_path: Any) -> None:
    """Un archivo inexistente falla con mensaje WHAT+WHY+WHERE."""
    missing = tmp_path / "no_existe.py"

    with pytest.raises(FileNotFoundError) as exc_info:
        TDDPolicyEngine.hash_tests((str(missing),))

    message = str(exc_info.value)
    assert "WHAT" in message
    assert "WHY" in message
    assert "WHERE" in message
    assert "no_existe.py" in message


def test_hash_tests_empty_sources_is_sha256_of_empty() -> None:
    """Con cero fuentes se firma el hash de contenido vacio."""
    digest = TDDPolicyEngine.hash_tests(())

    assert digest == "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"


def test_hash_tests_is_hex_sha256(tmp_path: Any) -> None:
    """El hash producido es un hex sha256 de 64 caracteres."""
    source = tmp_path / "test.py"
    source.write_text("assert True\n", encoding="utf-8")

    digest = TDDPolicyEngine.hash_tests((str(source),))

    assert len(digest) == 64
    assert all(char in "0123456789abcdef" for char in digest)


# ---------------------------------------------------------------------------
# can_emit_done: API corta para el orchestrator
# ---------------------------------------------------------------------------


def test_can_emit_done_true_when_green() -> None:
    """can_emit_done devuelve True solo con un contexto completamente verde."""
    ok, message = TDDPolicyEngine().can_emit_done(_green_ctx())

    assert ok is True
    assert "APROBADO" in message


def test_can_emit_done_false_when_blocked() -> None:
    """can_emit_done devuelve False con cualquier bloqueo y su razon."""
    ok, message = TDDPolicyEngine().can_emit_done(_green_ctx(red_evidence=False))

    assert ok is False
    assert "BLOQUEADO" in message
    assert "sin_evidencia_red" in message
