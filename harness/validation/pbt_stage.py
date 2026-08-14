"""
PBT Validation Stage — Property-Based Testing for LLM-generated code (ADR-0041 H3).

Integra Hypothesis-style property-based testing como stage posterior a la generación
de código por agentes Swarmind. El objetivo es validar invariantes semanticas
y detectar regresiones invisibles a tests unitarios tradicionales.

Flujo (oraculo mecanico, nunca un LLM juzgando a otro):
  1. Agent genera código (fuente Python).
  2. PBT stage extrae invariantes de docstrings + firma (AST).
  3. Genera @given strategies (Hypothesis) dirigidas por anotaciones.
  4. Ejecuta las hypotheses REALMENTE en subprocess aislado (hypothesis 6.x).
  5. Reporta: pass/fail, bugs descubiertos, invariantes rotas.

Seguridad (SEG): NUNCA se usa exec()/eval() en el proceso principal; cada
hypothesis se ejecuta en subprocess desde archivo temporal (tempfile), nunca
/tmp hardcodeado (ADR-0035 paths portables).

Inspirado en:
  - PBT‑Bench (arXiv 2605.15229, 2026‑05‑13): bug‑recall 31.4%–76.7% open‑ended;
    Hypothesis scaffolding lifts mid‑capability models >20pp.
  - ACL 2026 PROBE: +9.79% mutation score via property‑based refinement.
"""

from __future__ import annotations

import ast
import logging
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constantes (sin magic numbers)
# ---------------------------------------------------------------------------

DEFAULT_MAX_EXAMPLES: int = 50  # máximo de casos @given (Hypothesis)
DEFAULT_MIN_EXAMPLES: int = 10  # mínimo para considerar validación
TIMEOUT_PER_EXAMPLE: float = 30.0  # segundos por hypothesis antes de abortar

# Palabras clave en docstrings que señalan invariantes candidatas
INVARIANT_KEYWORDS: frozenset[str] = frozenset({
    "devuelve", "resultado", "mismo", "identico", "tipo", "lista",
    "ordena", "filtra", "valida", "lanza", "excepcion",
})

# Estrategias Hypothesis por tipo de anotación (progressive, sin mágicos)
# Orden IMPORTANTE: tipos contenedores ("list") ANTES que sus elementos ("int").
_HYPOTHESIS_STRATEGIES: dict[str, str] = {
    "list": "st.lists(st.integers(min_value=-100, max_value=100), max_size=20)",
    "int": "st.integers(min_value=-1000, max_value=1000)",
    "float": "st.floats(min_value=-1000.0, max_value=1000.0, allow_nan=False)",
    "str": "st.text(max_size=50)",
    "bool": "st.booleans()",
    "None": "st.none()",
}


# ---------------------------------------------------------------------------
# Helpers: extracción de invariantes del docstring / AST
# ---------------------------------------------------------------------------

def _extract_docstring_invariants(source: str) -> list[str]:
    """Extrae invariantes candidatas del docstring de funciones/módulo.

    Args:
        source: Código fuente Python.

    Returns:
        Lista de frases del docstring que contienen keywords de invariante.
    """
    invariants: list[str] = []
    try:
        tree = ast.parse(source)
    except SyntaxError as e:
        logger.warning(
            "Could not parse AST for invariants (WHAT=parse_error WHY=%s "
            "WHERE=_extract_docstring_invariants)", e,
        )
        return invariants
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Module)):
            doc = ast.get_docstring(node)
            if doc:
                for sentence in doc.split("."):
                    sentence = sentence.strip()
                    if any(kw in sentence.lower() for kw in INVARIANT_KEYWORDS):
                        invariants.append(sentence.strip())
    return invariants


def _strategy_for_annotation(annotation: ast.expr | None) -> str:
    """Devuelve estrategia Hypothesis para una anotación de tipo.

    Args:
        annotation: Nodo AST de anotación (o None).

    Returns:
        Expresión de estrategia st.* (default: ints homogéneos, evita
        falsos positivos por mezcla de tipos).
    """
    if annotation is None:
        return "st.integers(min_value=-100, max_value=100)"
    ann_name = ast.unparse(annotation).lower().replace("optional[", "").replace("]", "")
    ann_name = ann_name.replace("typing.", "").split("|")[0].strip()
    for key, strategy in _HYPOTHESIS_STRATEGIES.items():
        if key in ann_name:
            return strategy
    return "st.integers(min_value=-100, max_value=100)"


def _infer_pbt_hypotheses(
    func_source: str,
    invariants: list[str],
    max_examples: int = DEFAULT_MAX_EXAMPLES,
) -> list[str]:
    """Genera plantillas @given Hypothesis dirigidas por firma e invariantes.

    Args:
        func_source: Código fuente de la función.
        invariants: Invariantes extraídas del docstring.
        max_examples: Máximo de casos por hypothesis (settings).

    Returns:
        Lista de códigos de test Hypothesis (def test_...).
    """
    hypotheses: list[str] = []
    try:
        tree = ast.parse(func_source)
    except SyntaxError:
        return hypotheses

    func_def = next(
        (node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)),
        None,
    )
    if func_def is None:
        return hypotheses

    func_name = func_def.name
    params = [arg.arg for arg in func_def.args.args if arg.arg != "self"]
    annotations = {
        arg.arg: arg.annotation for arg in func_def.args.args if arg.arg != "self"
    }
    returns = func_def.returns
    returns_name = ast.unparse(returns).lower() if returns else ""
    settings = (
        f"@settings(max_examples={max_examples}, deadline=None, "
        f"derandomize=True)"
    )

    # 1. Invariante "no crash": la función no lanza con entradas válidas
    if params:
        args = ", ".join(params)
        given_args = ", ".join(
            f"{p}=_strat_{i}" for i, p in enumerate(params)
        )
        strat_lines = "\n".join(
            f"_strat_{i} = {_strategy_for_annotation(annotations.get(p))}"
            for i, p in enumerate(params)
        )
        hyp = (
            f"{strat_lines}\n"
            f"@given({given_args})\n"
            f"{settings}\n"
            f"def test_{func_name}_no_crash({args}):\n"
            f"    '''Invariante: la función no lanza excepción inesperada.'''\n"
            f"    {func_name}({args})\n"
        )
        hypotheses.append(hyp)

    # 2. Invariante de resultado no-None (si el docstring sugiere retorno)
    has_return_invariant = any(
        kw in inv.lower() for inv in invariants
        for kw in ("devuelve", "resultado", "retorna", "mismo", "identico")
    )
    if params and has_return_invariant:
        args = ", ".join(params)
        given_args = ", ".join(f"{p}=_strat_{i}" for i, p in enumerate(params))
        strat_lines = "\n".join(
            f"_strat_{i} = {_strategy_for_annotation(annotations.get(p))}"
            for i, p in enumerate(params)
        )
        hyp = (
            f"{strat_lines}\n"
            f"@given({given_args})\n"
            f"{settings}\n"
            f"def test_{func_name}_returns_value({args}):\n"
            f"    '''Invariante: la función devuelve un resultado (no None).'''\n"
            f"    result = {func_name}({args})\n"
            f"    assert result is not None, 'Function returned None'\n"
        )
        hypotheses.append(hyp)

    # 3. Invariante de lista (solo si el retorno anotado o nombre sugiere lista)
    if params and (
        "list" in returns_name
        or "lista" in " ".join(invariants).lower()
        or any(word in func_name.lower() for word in ("list", "filter", "sort", "get_"))
    ):
        args = ", ".join(params)
        given_args = ", ".join(f"{p}=_strat_{i}" for i, p in enumerate(params))
        strat_lines = "\n".join(
            f"_strat_{i} = {_strategy_for_annotation(annotations.get(p))}"
            for i, p in enumerate(params)
        )
        hyp = (
            f"{strat_lines}\n"
            f"@given({given_args})\n"
            f"{settings}\n"
            f"def test_{func_name}_output_list({args}):\n"
            f"    '''Invariante: el resultado es una lista acotada.'''\n"
            f"    result = {func_name}({args})\n"
            f"    assert isinstance(result, list), 'Result is not a list'\n"
            f"    assert len(result) <= 50, 'List too large'\n"
        )
        hypotheses.append(hyp)

    # 4. Invariante "mismo/identico": consistencia para la misma entrada
    if params and any(
        kw in " ".join(invariants).lower() for kw in ("mismo", "identico", "consistente")
    ):
        args = ", ".join(params)
        given_args = ", ".join(f"{p}=_strat_{i}" for i, p in enumerate(params))
        strat_lines = "\n".join(
            f"_strat_{i} = {_strategy_for_annotation(annotations.get(p))}"
            for i, p in enumerate(params)
        )
        hyp = (
            f"{strat_lines}\n"
            f"@given({given_args})\n"
            f"{settings}\n"
            f"def test_{func_name}_deterministic({args}):\n"
            f"    '''Invariante: mismo resultado para la misma entrada.'''\n"
            f"    first = {func_name}({args})\n"
            f"    second = {func_name}({args})\n"
            f"    assert first == second, 'Non-deterministic result'\n"
        )
        hypotheses.append(hyp)

    # 5. Invariante conmutativa (PBT template commutative): detecta bugs
    #    aritmeticos como a - b en funciones de suma (conmuta el resultado).
    commutative_kw = ("suma", "sumar", "multiplica", "multiplicar", "conmuta")
    if len(params) == 2 and any(kw in " ".join(invariants).lower() for kw in commutative_kw):
        a, b = params[0], params[1]
        strat_lines = "\n".join(
            f"_strat_{i} = {_strategy_for_annotation(annotations.get(p))}"
            for i, p in enumerate(params)
        )
        hyp = (
            f"{strat_lines}\n"
            f"@given(a=_strat_0, b=_strat_1)\n"
            f"{settings}\n"
            f"def test_{func_name}_commutative({a}, {b}):\n"
            f"    '''Invariante: {func_name}(a, b) == {func_name}(b, a).'''\n"
            f"    assert {func_name}({a}, {b}) == {func_name}({b}, {a}), \\\n"
            f"        'Non-commutative result'\n"
        )
        hypotheses.append(hyp)

    return hypotheses


# ---------------------------------------------------------------------------
# Ejecución de PBT stage (oráculo mecánico real)
# ---------------------------------------------------------------------------

def _run_hypothesis_in_subprocess(
    func_source: str,
    hypothesis_code: str,
    timeout: float,
) -> tuple[bool, str]:
    """Ejecuta una hypothesis REAL contra la función en subprocess aislado.

    Escribe un script temporal (tempfile, nunca /tmp hardcodeado) que importa
    hypothesis, define la función y el test @given, y llama al test. Si
    hypothesis encuentra un ejemplo falsificador, el subprocess sale con
    error y el mensaje contiene el contraejemplo.

    Args:
        func_source: Código fuente de la función.
        hypothesis_code: Código del test @given.
        timeout: Timeout de ejecución en segundos.

    Returns:
        (passed, mensaje). passed=True si la hypothesis se validó.
    """
    script = _build_script_with_present_tests(func_source, hypothesis_code)

    with tempfile.TemporaryDirectory() as tmp_dir:
        script_path = Path(tmp_dir) / "pbt_check.py"
        script_path.write_text(script, encoding="utf-8")
        try:
            result = subprocess.run(
                [sys.executable, str(script_path)],
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False,
            )
        except subprocess.TimeoutExpired:
            return False, f"Timeout after {timeout}s"
        except Exception as e:  # noqa: BLE001
            return False, f"{type(e).__name__}: {e}"

    if result.returncode == 0:
        return True, ""
    return False, (result.stdout + result.stderr)[:300]


def _build_script_with_present_tests(
    func_source: str, hypothesis_code: str
) -> str:
    """Construye el script de ejecución invocando solo los tests definidos.

    Args:
        func_source: Código fuente de la función.
        hypothesis_code: Código del test @given generado.

    Returns:
        Script Python completo listo para subprocess.
    """
    defined_tests = re.findall(r"def (test_\w+)", hypothesis_code)
    calls = "\n".join(f"        {name}()" for name in defined_tests)
    return (
        "import sys\n"
        "from hypothesis import given, settings, strategies as st\n"
        "import traceback\n"
        f"{func_source}\n"
        f"{hypothesis_code}\n"
        "def _main():\n"
        "    try:\n"
        f"{calls}\n"
        "    except Exception as e:\n"
        "        print(f'FALSIFYING: {e}')\n"
        "        traceback.print_exc()\n"
        "        sys.exit(1)\n"
        "    sys.exit(0)\n"
        "if __name__ == '__main__':\n"
        "    _main()\n"
    )


def run_pbt_stage(
    func_source: str,
    agent_name: str,
    max_examples: int = DEFAULT_MAX_EXAMPLES,
    timeout_per_example: float = TIMEOUT_PER_EXAMPLE,
) -> dict[str, Any]:
    """
    Ejecuta el stage de Property-Based Testing sobre el código generado.

    Oráculo mecánico REAL: cada hypothesis se ejecuta con hypothesis 6.x en
    subprocess aislado; si encuentra un contraejemplo, se reporta como bug.

    Args:
        func_source: Código fuente Python (definicion de función) a validar.
        agent_name: Nombre del agente que genero el código (para logging).
        max_examples: Número máximo de casos @given (default 50).
        timeout_per_example: Timeout por hypothesis en segundos (default 30).

    Returns:
        Dict con reporte de validacion:
        {
            "passed": bool,
            "bugs_found": int,
            "invariants_detected": int,
            "hypotheses_generated": int,
            "execution_details": [
                {"hypothesis": "...", "passed": bool, "error": "..."}
            ]
        }

    Raises:
        ValueError: Si func_source está vacío.
    """
    if not isinstance(func_source, str) or not func_source.strip():
        raise ValueError(
            "func_source must be a non-empty string. "
            "WHY: Sin codigo fuente no hay invariantes que validar. "
            "WHERE: pbt_stage.run_pbt_stage"
        )

    logger.info(
        "Running PBT stage for agent=%s (max_examples=%d)", agent_name, max_examples
    )

    invariants = _extract_docstring_invariants(func_source)
    logger.info("Agent %s: %d invariants detected", agent_name, len(invariants))

    hypotheses = _infer_pbt_hypotheses(func_source, invariants, max_examples)
    logger.info("Agent %s: %d hypotheses generated", agent_name, len(hypotheses))

    if not hypotheses:
        return {
            "passed": True,
            "bugs_found": 0,
            "invariants_detected": len(invariants),
            "hypotheses_generated": 0,
            "execution_details": [],
            "note": "No PBT hypotheses generated; skipping validation.",
        }

    execution_details: list[dict[str, Any]] = []
    bugs_found = 0

    for hyp in hypotheses[:max_examples]:
        passed, error = _run_hypothesis_in_subprocess(
            func_source, hyp, timeout_per_example
        )
        if not passed:
            bugs_found += 1
        name_match = re.search(r"def (test_\w+)", hyp)
        execution_details.append(
            {
                "hypothesis_name": name_match.group(1) if name_match else "unknown",
                "hypothesis": hyp[:80] + ("..." if len(hyp) > 80 else ""),
                "passed": passed,
                "error": error,
            }
        )

    all_passed = bugs_found == 0 and all(d["passed"] for d in execution_details)

    report: dict[str, Any] = {
        "passed": all_passed,
        "bugs_found": bugs_found,
        "invariants_detected": len(invariants),
        "hypotheses_generated": len(hypotheses),
        "execution_details": execution_details,
    }

    logger.info(
        "Agent %s PBT stage complete: passed=%s, bugs_found=%d",
        agent_name,
        all_passed,
        bugs_found,
    )

    return report
