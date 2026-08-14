"""
Tests del PBT Stage reescrito (oraculo mecanico REAL, ADR-0041 H3).

Verifica que el stage de Property-Based Testing:
  - Extrae invariantes de docstrings (AST).
  - Genera hypotheses dirigidas por anotaciones (tipos correctos).
  - EJECUTA hypothesis de verdad en subprocess aislado (sin exec en proceso).
  - Detecta bugs aritmeticos reales (conmutatividad).
  - No genera falsos positivos con funciones correctas.
  - Maneja errores: codigo vacio, sintaxis invalida, timeout.

Regla: un oraculo mecanico honesto nunca usa exec()/eval() en el proceso
principal ni juzga con un LLM; ejecuta la libreria Hypothesis real.
"""
from __future__ import annotations

import time

import pytest

from harness.validation.pbt_stage import (
    _build_script_with_present_tests,
    _extract_docstring_invariants,
    _infer_pbt_hypotheses,
    _strategy_for_annotation,
    run_pbt_stage,
)

# ============================================================================
# Fixtures
# ============================================================================

GOOD_SUM_SOURCE = (
    "def add(a, b):\n"
    '    """Suma dos numeros y devuelve el resultado."""\n'
    "    return a + b\n"
)

BUGGY_SUB_SOURCE = (
    "def add(a, b):\n"
    '    """Suma dos numeros y devuelve el resultado."""\n'
    "    return a - b\n"
)

LIST_SOURCE = (
    "def get_items(n):\n"
    '    """Devuelve una lista de n elementos."""\n'
    "    return list(range(max(n, 0)))\n"
)

EMPTY_SOURCE = ""
INVALID_SOURCE = "def broken(:\n"

# ============================================================================
# Extraccion de invariantes
# ============================================================================


class TestExtractDocstringInvariants:
    """Invariantes extraidas del docstring via AST."""

    def test_detects_return_invariant(self) -> None:
        """Docstring con 'devuelve' produce al menos una invariante."""
        invariants = _extract_docstring_invariants(GOOD_SUM_SOURCE)
        assert len(invariants) >= 1
        assert any("devuelve" in inv.lower() for inv in invariants)

    def test_empty_source_returns_empty(self) -> None:
        """Source vacio no produce invariantes ni excepcion."""
        assert _extract_docstring_invariants(EMPTY_SOURCE) == []

    def test_invalid_syntax_returns_empty(self) -> None:
        """SyntaxError no rompe la extraccion; devuelve lista vacia."""
        assert _extract_docstring_invariants(INVALID_SOURCE) == []


# ============================================================================
# Estrategias por anotacion
# ============================================================================


class TestStrategyForAnnotation:
    """Mapeo de anotaciones a estrategias Hypothesis."""

    def test_none_uses_homogeneous_ints(self) -> None:
        """Sin anotacion: ints homogeneos (evita falsos positivos de tipo)."""
        strategy = _strategy_for_annotation(None)
        assert "st.integers" in strategy
        assert "st.text" not in strategy

    def test_int_annotation(self) -> None:
        """Anotacion int produce estrategia de enteros."""
        strategy = _strategy_for_annotation(_parse_annotation("int"))
        assert "st.integers" in strategy

    def test_str_annotation(self) -> None:
        """Anotacion str produce estrategia de texto."""
        strategy = _strategy_for_annotation(_parse_annotation("str"))
        assert "st.text" in strategy

    def test_list_annotation(self) -> None:
        """Anotacion list produce estrategia de listas."""
        strategy = _strategy_for_annotation(_parse_annotation("list[int]"))
        assert "st.lists" in strategy


def _parse_annotation(name: str) -> object:
    """Convierte texto de anotacion en nodo AST (helper del test)."""
    import ast

    return ast.parse(f"def f(x: {name}) -> None: ...").body[0].args.args[0].annotation


# ============================================================================
# Generacion de hypotheses
# ============================================================================


class TestInferPbtHypotheses:
    """Hypotheses generadas segun firma + invariantes."""

    def test_no_crash_generated_for_params(self) -> None:
        """Funcion con parametros genera hypothesis de no-crash."""
        hyps = _infer_pbt_hypotheses(GOOD_SUM_SOURCE, ["devuelve"], max_examples=10)
        joined = "\n".join(hyps)
        assert "no_crash" in joined

    def test_commutative_generated_for_sum(self) -> None:
        """Docstring de suma genera invariante conmutativa."""
        hyps = _infer_pbt_hypotheses(
            GOOD_SUM_SOURCE, ["suma dos numeros"], max_examples=10
        )
        joined = "\n".join(hyps)
        assert "commutative" in joined

    def test_no_hypotheses_for_invalid_source(self) -> None:
        """Source con sintaxis invalida no genera hypotheses."""
        assert _infer_pbt_hypotheses(INVALID_SOURCE, [], max_examples=10) == []

    def test_list_invariant_only_when_suggested(self) -> None:
        """Hypothesis de lista solo con evidencia de retorno lista."""
        hyps = _infer_pbt_hypotheses(
            LIST_SOURCE, ["devuelve una lista"], max_examples=10
        )
        scalar_hyps = _infer_pbt_hypotheses(
            GOOD_SUM_SOURCE, ["devuelve"], max_examples=10
        )
        assert any("output_list" in h for h in hyps)
        assert not any("output_list" in h for h in scalar_hyps)


# ============================================================================
# Script builder
# ============================================================================


class TestBuildScriptWithPresentTests:
    """Script de subprocess invoca solo los tests definidos."""

    def test_calls_only_defined_tests(self) -> None:
        """Solo se invocan los test_* presentes en el codigo hypothesis."""
        hypothesis_code = (
            "def test_add_no_crash(a, b):\n"
            "    add(a, b)\n"
        )
        script = _build_script_with_present_tests(GOOD_SUM_SOURCE, hypothesis_code)
        assert "test_add_no_crash()" in script
        assert "test_add_returns_value()" not in script

    def test_script_contains_function_source(self) -> None:
        """El script incluye el source de la funcion (sin exec de fuente)."""
        script = _build_script_with_present_tests(GOOD_SUM_SOURCE, "def t(): pass")
        assert "def add(a, b):" in script


# ============================================================================
# Orquestacion del stage (oraculo mecanico real)
# ============================================================================


class TestRunPbtStage:
    """Validacion end-to-end con hypothesis ejecutada de verdad."""

    def test_good_function_passes(self) -> None:
        """Funcion correcta pasa todas las hypotheses (0 bugs)."""
        report = run_pbt_stage(GOOD_SUM_SOURCE, "good-agent", max_examples=10)
        assert report["passed"] is True
        assert report["bugs_found"] == 0
        assert report["hypotheses_generated"] >= 2

    def test_buggy_function_detected(self) -> None:
        """Bug aritmetico (a - b) detectado por invariante conmutativa."""
        report = run_pbt_stage(BUGGY_SUB_SOURCE, "buggy-agent", max_examples=10)
        assert report["passed"] is False
        assert report["bugs_found"] >= 1
        failed = [d for d in report["execution_details"] if not d["passed"]]
        assert any("commutative" in d["hypothesis_name"] for d in failed)

    def test_empty_source_raises_value_error(self) -> None:
        """Source vacio lanza ValueError accionable."""
        with pytest.raises(ValueError, match="func_source"):
            run_pbt_stage(EMPTY_SOURCE, "empty-agent")

    def test_invalid_source_skips_gracefully(self) -> None:
        """Source con sintaxis invalida: reporte con 0 hypotheses, sin crash."""
        report = run_pbt_stage(INVALID_SOURCE, "broken-agent")
        assert report["passed"] is True
        assert report["hypotheses_generated"] == 0

    def test_timeout_reports_bug(self) -> None:
        """Hypothesis que cuelga (sleep) se aborta por timeout y reporta bug."""
        slow_source = (
            "def slow(x):\n"
            '    """Devuelve el valor de entrada."""\n'
            "    import time\n"
            "    time.sleep(5)\n"
            "    return x\n"
        )
        start = time.monotonic()
        report = run_pbt_stage(slow_source, "slow-agent", timeout_per_example=1.0)
        elapsed = time.monotonic() - start
        assert report["passed"] is False
        assert elapsed < 10  # no se deja correr el sleep completo
