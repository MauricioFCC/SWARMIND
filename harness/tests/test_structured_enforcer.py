"""Tests para structured_enforcer — salida con schema y retry con feedback (ADR-0073).

Frontera: JSON schema obligatorio da 99.9% adherencia vs <70% sin
constraint (30x menos fallos de parse); sin schema, 300K+ respuestas
malformadas por 1M requests. Verifica: validacion de schema, re-ask con
feedback del error, presupuesto de retries y fail-fast accionable.
"""


import pytest

from harness.orchestrator.structured_enforcer import (
    StructuredEnforcementError,
    enforce_schema,
)

_PERSON_SCHEMA = {
    "type": "object",
    "required": ["name", "age"],
    "properties": {
        "name": {"type": "string"},
        "age": {"type": "integer", "minimum": 0},
    },
}


def _raw_fn(bad: list[str], good: str):
    """Fabrica retry_fn: retorna los bad en orden, luego el good."""
    calls: list[str] = []

    def _fn(feedback: str) -> str:
        calls.append(feedback)
        return bad[len(calls) - 1] if len(calls) <= len(bad) else good

    _fn.calls = calls  # type: ignore[attr-defined]
    return _fn


def test_valid_first_shot_no_retry() -> None:
    """JSON valido de primera: solo la llamada inicial, 0 retries extra."""
    fn = _raw_fn([], '{"name": "ana", "age": 30}')
    out = enforce_schema(fn, _PERSON_SCHEMA, max_retries=2)
    assert out == {"name": "ana", "age": 30}
    assert len(fn.calls) == 1


def test_invalid_json_triggers_retry_with_feedback() -> None:
    """JSON malformado re-ask con feedback que menciona el error."""
    fn = _raw_fn(["no es json"], '{"name": "b", "age": 1}')
    out = enforce_schema(fn, _PERSON_SCHEMA, max_retries=2)
    assert out["name"] == "b"
    assert len(fn.calls) == 2
    assert "json" in fn.calls[1].lower()


def test_schema_violation_retry_names_field() -> None:
    """Violacion de schema nombra el campo faltante en el feedback."""
    fn = _raw_fn(['{"name": "x"}'], '{"name": "x", "age": 5}')
    out = enforce_schema(fn, _PERSON_SCHEMA, max_retries=1)
    assert out["age"] == 5
    assert "age" in fn.calls[1]


def test_exhausted_retries_raises_actionable() -> None:
    """Agotar retries lanza StructuredEnforcementError con WHAT+WHY+WHERE."""
    fn = _raw_fn(["malo", "tambien malo", "mas malo"], "")
    with pytest.raises(StructuredEnforcementError) as exc:
        enforce_schema(fn, _PERSON_SCHEMA, max_retries=2)
    assert "WHAT" in str(exc.value)


def test_wrapped_markdown_json_is_extracted() -> None:
    """JSON envuelto en fences markdown se extrae antes de validar."""
    fn = _raw_fn([], '```json\n{"name": "z", "age": 4}\n```')
    out = enforce_schema(fn, _PERSON_SCHEMA, max_retries=1)
    assert out["age"] == 4


def test_min_constraint_enforced() -> None:
    """Restricciones de schema (minimum) se validan."""
    fn = _raw_fn(['{"name": "n", "age": -5}'], '{"name": "n", "age": 0}')
    out = enforce_schema(fn, _PERSON_SCHEMA, max_retries=1)
    assert out["age"] == 0


def test_no_schema_raises() -> None:
    """Schema vacio falla accionable."""
    with pytest.raises(ValueError, match="WHAT"):
        enforce_schema(lambda fb: "{}", {})
