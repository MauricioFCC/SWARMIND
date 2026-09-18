"""Tests para _try_local_execution — wiring del loop local en run.py (ADR-0078).

Cierra el loop: tras `_apply_model_routing` == "local" y HITL aprobado,
las tareas cerradas se ejecutan en Ollama (0 tokens cloud) en vez de
solo registrar telemetria. Cualquier condicion no cumplida -> None (el
flujo cloud sigue intacto).
"""


from harness.run import _try_local_execution


class _FakeTiers:
    """Router de tiers fake."""

    def __init__(self, tier) -> None:
        self._tier = tier

    def tier_for_task(self, task: str):
        return self._tier

    def model_for(self, tier) -> str:
        return f"m-{tier.value}"


class _FakeClient:
    """Cliente Ollama fake."""

    def __init__(self, available: bool = True) -> None:
        self._available = available

    def is_available(self) -> bool:
        return self._available

    def generate(self, model: str, prompt: str, **kwargs) -> dict:
        return {"response": f"local:{prompt[:20]}", "model": model}


def test_closed_task_local_source_executes() -> None:
    """source local + tarea cerrada + Ollama arriba -> respuesta local."""
    from harness.model_router.ollama_tiers import CapabilityTier

    out = _try_local_execution(
        "resume esto en 2 lineas", "local",
        client=_FakeClient(), tiers=_FakeTiers(CapabilityTier.FAST),
    )
    assert out is not None
    assert out.startswith("local:")


def test_cloud_source_skips() -> None:
    """source cloud nunca ejecuta local (flujo cloud intacto)."""
    from harness.model_router.ollama_tiers import CapabilityTier

    out = _try_local_execution(
        "resume esto", "cloud",
        client=_FakeClient(), tiers=_FakeTiers(CapabilityTier.FAST),
    )
    assert out is None


def test_open_task_skips() -> None:
    """Tarea abierta no se ejecuta local aunque el source sea local."""
    from harness.model_router.ollama_tiers import CapabilityTier

    out = _try_local_execution(
        "investiga el mercado de stablecoins", "local",
        client=_FakeClient(), tiers=_FakeTiers(CapabilityTier.FAST),
    )
    assert out is None


def test_ollama_down_returns_none() -> None:
    """Ollama caido -> None (el flujo cloud sigue)."""
    from harness.model_router.ollama_tiers import CapabilityTier

    out = _try_local_execution(
        "resume esto", "local",
        client=_FakeClient(available=False),
        tiers=_FakeTiers(CapabilityTier.FAST),
    )
    assert out is None


def test_frontier_tier_returns_none() -> None:
    """Tier None (frontier-only) -> None."""
    out = _try_local_execution(
        "resume esto", "local",
        client=_FakeClient(), tiers=_FakeTiers(None),
    )
    assert out is None
