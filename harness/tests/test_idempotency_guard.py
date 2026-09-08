"""Tests para idempotency_guard + boundary strict (ADR-0076).

Frontera (dump 9-8-2026, agentic=distributed systems): un retry sin
idempotency key deja el workflow en limbo (200 OK con JSON keys
inesperados). El guard deduplica efectos por (idempotency_key, hash del
payload): mismo key + mismo payload -> resultado cacheado sin re-ejecutar;
mismo key + payload distinto -> error accionable (proteccion contra
key-reuse). Y el structured_enforcer en modo strict rechaza keys
inesperadas fuera del schema.
"""

from __future__ import annotations

import pytest

from harness.orchestrator.idempotency_guard import (
    IdempotencyGuard,
    KeyPayloadMismatch,
)


def _exec_fn(counter: list[int]):
    """Fabrica execute_fn que cuenta ejecuciones."""

    def _fn(payload: str) -> str:
        counter.append(1)
        return f"resultado-{len(counter)}"

    return _fn


def test_first_call_executes_and_caches() -> None:
    """Primera llamada ejecuta y cachea por key."""
    counter: list[int] = []
    guard = IdempotencyGuard()
    out = guard.run("txn-1", "payload-a", _exec_fn(counter))
    assert out.output == "resultado-1"
    assert out.replayed is False
    assert len(counter) == 1


def test_retry_same_key_same_payload_replays() -> None:
    """Retry con mismo key y payload: replay cacheado, 0 re-ejecucion."""
    counter: list[int] = []
    guard = IdempotencyGuard()
    first = guard.run("txn-1", "payload-a", _exec_fn(counter))
    second = guard.run("txn-1", "payload-a", _exec_fn(counter))
    assert second.output == first.output
    assert second.replayed is True
    assert len(counter) == 1


def test_same_key_different_payload_raises() -> None:
    """Mismo key con payload distinto: KeyPayloadMismatch accionable."""
    guard = IdempotencyGuard()
    guard.run("txn-1", "payload-a", lambda p: "x")
    with pytest.raises(KeyPayloadMismatch, match="WHAT"):
        guard.run("txn-1", "payload-B", lambda p: "y")


def test_different_keys_execute_independently() -> None:
    """Keys distintos ejecutan (no hay cross-dedup)."""
    counter: list[int] = []
    guard = IdempotencyGuard()
    guard.run("txn-1", "p", _exec_fn(counter))
    guard.run("txn-2", "p", _exec_fn(counter))
    assert len(counter) == 2


def test_stats_replays() -> None:
    """Metrica de replays auditable."""
    guard = IdempotencyGuard()
    guard.run("t1", "p", lambda x: "a")
    guard.run("t1", "p", lambda x: "a")
    guard.run("t1", "p", lambda x: "a")
    assert guard.replays == 2


def test_empty_key_raises() -> None:
    """Key vacio falla accionable."""
    guard = IdempotencyGuard()
    with pytest.raises(ValueError, match="WHAT"):
        guard.run("", "p", lambda x: "x")


def test_strict_keys_rejects_unexpected() -> None:
    """Enforcer strict: keys inesperadas -> retry con feedback."""
    from harness.orchestrator.structured_enforcer import enforce_schema

    schema = {
        "type": "object",
        "required": ["name"],
        "properties": {"name": {"type": "string"}},
        "additionalProperties": False,
    }
    responses = ['{"name": "x", "trojan": "si"}', '{"name": "ok"}']
    calls: list[str] = []

    def retry_fn(feedback: str) -> str:
        calls.append(feedback)
        return responses[min(len(calls) - 1, len(responses) - 1)]

    out = enforce_schema(retry_fn, schema, max_retries=1)
    assert out == {"name": "ok"}
    assert "trojan" in calls[1]


def test_strict_keys_documented_default() -> None:
    """El default del enforcer sigue tolerante (strict solo opt-in)."""
    from harness.orchestrator.structured_enforcer import enforce_schema

    schema = {
        "type": "object",
        "required": ["name"],
        "properties": {"name": {"type": "string"}},
    }
    out = enforce_schema(lambda fb: '{"name": "x", "extra": 1}', schema, max_retries=0)
    assert out["name"] == "x"
