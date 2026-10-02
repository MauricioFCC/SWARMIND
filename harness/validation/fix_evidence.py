"""fix_evidence.py — Gate de evidencia de fix (SpecBench / anti-pintar-verde).

WHAT: verifica que un fix de agente traiga evidencia real: spec existente,
test de reproduccion que FALLABA antes y PASA despues, y cero debilitamiento
de tests (SpecBench arXiv:2605.21384: sin esto un agente "resuelve" editando
el test).
WHY: `cp_spec_gate` valida el spec ANTES de codear y `tdd_strict` define las
fases, pero nada verifica DESPUES que el repro fallaba ni que los tests no
se tocaron para pasar. Este gate T1 determinista (sin LLM, sin red) cierra
ese hueco para el merge.
WHERE: guardian/CI antes de aceptar un fix; `specs/fix-evidence-gate.md`.

Uso:
    report = verify_fix_evidence(spec_path="specs/x.md", repro_test="...::test",
                                 failed_before=True, passed_after=True,
                                 old_test_text=old, new_test_text=new)
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

#: Operadores de comparacion que `new` no puede relajar respecto a `old`.
_RELAXATIONS: tuple[tuple[str, str], ...] = (
    ("==", "in"),
    ("==", "not in"),
    (">", ">="),
    ("<", "<="),
)

_ASSERT_RE = re.compile(
    r"^\s*assert\s+(?P<lhs>.+?)\s*(?P<op>==|!=|\bnot in\b|\bin\b|>=|<=|>|<|\bis\b)\s*(?P<rhs>.+?)\s*$"
)


@dataclass(frozen=True)
class FixEvidenceReport:
    """Veredicto del gate de evidencia.

    Attributes:
        passed: True solo con spec + repro fail->pass + cero debilitamientos.
        reasons: Tupla vacia si paso; motivos WHAT+WHERE si fallo.
    """

    passed: bool
    reasons: tuple[str, ...] = ()


def _assert_lines(text: str) -> list[str]:
    """Lineas `assert` normalizadas (sin indentacion ni espacios extra)."""
    return [
        re.sub(r"\s+", " ", line.strip())
        for line in (text or "").splitlines()
        if line.strip().startswith("assert ")
    ]


def _parse_assert(line: str) -> tuple[str, str, str] | None:
    """Descompone `assert LHS OP RHS`; None si no es una comparacion."""
    match = _ASSERT_RE.match(line)
    if match is None:
        return None
    return (
        re.sub(r"\s+", " ", match.group("lhs").strip()),
        match.group("op").strip(),
        re.sub(r"\s+", " ", match.group("rhs").strip()),
    )


def _findings_for_old(old: str, new_parsed: list[tuple[str, str, str] | None]) -> list[str]:
    """Debilitamientos para un assert viejo contra los nuevos parseados."""
    parsed = _parse_assert(old)
    if parsed is None:
        return []
    lhs, op, rhs = parsed
    same_lhs = [p for p in new_parsed if p is not None and p[0] == lhs]
    if not same_lhs:
        return [f"assert eliminado (LHS `{lhs}` ya no se verifica)"]
    for _, new_op, new_rhs in same_lhs:
        if (op, new_op) in _RELAXATIONS:
            return [f"comparacion relajada `{op}` -> `{new_op}` en `{lhs}`"]
        if new_op == op and new_rhs != rhs:
            return [f"literal esperado cambiado en `{lhs}` (`{rhs}` -> `{new_rhs}`)"]
    return []


def check_test_weakening(old_test_text: str, new_test_text: str) -> list[str]:
    """Detecta si el diff de tests debilita aserciones (pintar verde).

    Anadir asserts nuevos esta permitido (endurece). Quitar, relajar el
    operador (`==`->`in`, `>`->`>=`) o cambiar el literal esperado es
    debilitamiento.

    Args:
        old_test_text: Contenido del test antes del fix.
        new_test_text: Contenido del test despues del fix.

    Returns:
        Lista de hallazgos (vacia = sin debilitamiento).
    """
    old_lines = _assert_lines(old_test_text)
    new_lines = _assert_lines(new_test_text)
    new_set = set(new_lines)
    new_parsed = [_parse_assert(line) for line in new_lines]
    findings: list[str] = []
    for line in old_lines:
        if line in new_set:
            continue
        findings.extend(_findings_for_old(line, new_parsed))
    return findings


def _check_spec(spec_path: str) -> str | None:
    """Razon de fallo si la spec no existe o esta vacia; None si vale."""
    path = Path(spec_path)
    if not path.is_file():
        return f"sin-spec: no existe {spec_path} (WHERE: spec_path)"
    if not path.read_text(encoding="utf-8").strip():
        return f"sin-spec: vacia {spec_path} (WHERE: spec_path)"
    return None


def verify_fix_evidence(
    spec_path: str,
    repro_test: str,
    failed_before: bool,
    passed_after: bool,
    old_test_text: str,
    new_test_text: str,
) -> FixEvidenceReport:
    """Gate: spec + repro que fallaba y ahora pasa + tests sin debilitar.

    Args:
        spec_path: Ruta a la spec del fix.
        repro_test: Nodo del test de reproduccion (`path::test`).
        failed_before: True si el repro fallaba antes del fix.
        passed_after: True si el repro pasa despues del fix.
        old_test_text: Contenido del test antes del fix.
        new_test_text: Contenido del test despues del fix.

    Returns:
        FixEvidenceReport con passed y razones accionables (WHAT+WHERE).
    """
    reasons: list[str] = []
    spec_reason = _check_spec(spec_path)
    if spec_reason is not None:
        reasons.append(spec_reason)
    if not failed_before:
        reasons.append(
            f"sin-fallo-previo: {repro_test} no fallaba antes "
            f"(WHERE: repro_test, sin evidencia de que el fix arregle)"
        )
    if not passed_after:
        reasons.append(
            f"sigue-fallando: {repro_test} no pasa despues "
            "(WHERE: repro_test)"
        )
    for finding in check_test_weakening(old_test_text, new_test_text):
        reasons.append(f"debilitamiento de test: {finding} (WHERE: diff de tests)")
    return FixEvidenceReport(passed=not reasons, reasons=tuple(reasons))
