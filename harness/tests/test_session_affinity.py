"""Tests para session_affinity — routing sticky por sesion (ADR-0073).

Frontera (vLLM SAAR): memoria de sesion owned por el router evita
switches de modelo en deployments multi-agente (-79% switches, -78.7%
costo). Verifica: tier sticky por session_id con TTL, switches evitados
contabilizados, expiracion y fail-fast.
"""

import pytest

from harness.model_router.session_affinity import (
    AffinityConfig,
    SessionAffinityRouter,
)


def test_sticky_tier_reuses_route() -> None:
    """Segunda tarea de la misma sesion reutiliza el tier sin re-decidir."""
    decides: list[str] = []

    def decide_fn(task: str) -> str:
        decides.append(task)
        return "small"

    router = SessionAffinityRouter(decide_fn, AffinityConfig())
    r1 = router.route("s1", "tarea uno")
    r2 = router.route("s1", "tarea dos")
    assert r1.tier == "small"
    assert r2.tier == "small"
    assert len(decides) == 1  # segunda decision servida por afinidad
    assert r2.from_cache is True


def test_different_sessions_independent() -> None:
    """Sesiones distintas deciden de forma independiente."""
    router = SessionAffinityRouter(lambda t: "small", AffinityConfig())
    router.route("a", "t1")
    r = router.route("b", "t2")
    assert r.from_cache is False


def test_affinity_expired_after_ttl() -> None:
    """Tras expirar el TTL, la sesion re-decide."""
    now = [1000.0]

    def decide_fn(task: str) -> str:
        return "frontier"

    router = SessionAffinityRouter(decide_fn, AffinityConfig(ttl_s=60.0), clock=lambda: now[0])
    router.route("s", "t1")
    now[0] += 120.0
    r2 = router.route("s", "t2")
    assert r2.from_cache is False


def test_switches_avoided_metric() -> None:
    """El contador de switches evitados crece con reusos de afinidad."""
    router = SessionAffinityRouter(lambda t: "small", AffinityConfig())
    router.route("s", "t1")
    router.route("s", "t2")
    router.route("s", "t3")
    assert router.switches_avoided == 2


def test_invalid_session_raises() -> None:
    """session_id vacio falla con ValueError accionable."""
    router = SessionAffinityRouter(lambda t: "small")
    with pytest.raises(ValueError, match="WHAT"):
        router.route("", "tarea")


def test_invalid_tier_raises() -> None:
    """Tier desconocido del decide_fn falla accionable."""
    router = SessionAffinityRouter(lambda t: "mega")
    with pytest.raises(ValueError, match="WHAT"):
        router.route("s", "t")
