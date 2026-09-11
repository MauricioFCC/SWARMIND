"""Tests para local_executor — cerrar el loop: triviales se EJECUTAN en local (ADR-0077).

Auditoria 2026-09-08: la DECISION trivial->local es correcta (10/10 en
simulacion, run.py:420 vivo, Ollama disponible) pero OllamaClient.generate
no tenia callers productivos: el modelo externo hacia el trabajo y el
routing era solo telemetria. Este modulo ejecuta tareas cerradas
(resumir/formatear/extraer/traducir/contar) en el tier local con allowlist
estricta + fallback a cloud ante cualquier fallo.
"""

import pytest

from harness.model_router.local_executor import (
    CLOSED_TASK_PATTERNS,
    LocalExecutor,
    is_closed_task,
)


class _FakeTiers:
    """OllamaTierRouter fake: tier fijo por constructor."""

    def __init__(self, tier) -> None:
        self._tier = tier

    def tier_for_task(self, task: str):
        return self._tier

    def model_for(self, tier) -> str:
        return f"fake-{tier.value}"


class _FakeClient:
    """OllamaClient fake con generate programable."""

    def __init__(self, available: bool = True, output: str = "respuesta local") -> None:
        self._available = available
        self._output = output
        self.calls: list[str] = []

    def is_available(self) -> bool:
        return self._available

    def generate(self, model: str, prompt: str, **kwargs) -> dict:
        self.calls.append(prompt)
        return {"response": self._output, "model": model}


def _executor(**kw):
    from harness.model_router.ollama_tiers import CapabilityTier

    tiers = _FakeTiers(kw.pop("tier", CapabilityTier.FAST))
    return LocalExecutor(client=kw.pop("client", _FakeClient()), tiers=tiers, **kw)


def test_closed_task_patterns_documented() -> None:
    """La allowlist cubre resumir/formatear/extraer/traducir/contar."""
    joined = " ".join(CLOSED_TASK_PATTERNS)
    for kw in ("resum", "formatea", "extrae", "traduce", "cuenta", "convierte", "lista"):
        assert kw in joined


def test_is_closed_task_matches_trivial() -> None:
    """Tareas triviales matchean; diseno y codigo abierto no."""
    assert is_closed_task("resume esto en 2 lineas") is True
    assert is_closed_task("formatea este json") is True
    assert is_closed_task("disena la arquitectura hexagonal") is False
    assert is_closed_task("implementa el modulo de pagos") is False


def test_trivial_executes_locally_zero_cloud() -> None:
    """Tarea cerrada + tier FAST => se ejecuta en local, cloud_tokens=0."""
    ex = _executor()
    out = ex.execute("resume esto en 2 lineas")
    assert out.executed_locally is True
    assert out.cloud_tokens == 0
    assert out.model.startswith("fake-")
    assert "respuesta local" in out.output


def test_frontier_only_never_local() -> None:
    """Tier None (frontier-only) nunca ejecuta local."""
    ex = _executor(tier=None)
    out = ex.execute("disena la arquitectura hexagonal")
    assert out.executed_locally is False
    assert out.output == ""


def test_non_closed_task_never_local() -> None:
    """Tarea abierta aunque el tier sea FAST no se ejecuta local."""
    ex = _executor()
    out = ex.execute("investiga el mercado de stablecoins")
    assert out.executed_locally is False


def test_ollama_down_falls_back() -> None:
    """Ollama caido => fallback a cloud (sin excepcion)."""
    ex = _executor(client=_FakeClient(available=False))
    out = ex.execute("resume esto")
    assert out.executed_locally is False
    assert "cloud" in out.reason.lower() or "ollama" in out.reason.lower()


def test_execute_error_falls_back() -> None:
    """Error del modelo local => fallback con reason accionable."""
    class _Boom(_FakeClient):
        def generate(self, model: str, prompt: str, **kwargs):
            raise RuntimeError("gpu fuera de memoria")

    ex = _executor(client=_Boom())
    out = ex.execute("resume esto")
    assert out.executed_locally is False
    assert "gpu" in out.reason.lower()


def test_result_is_frozen() -> None:
    """LocalExecutionResult es inmutable."""
    ex = _executor()
    out = ex.execute("resume esto")
    with pytest.raises(AttributeError):
        out.output = "x"  # type: ignore[misc]


def test_savings_metric() -> None:
    """Contadores de ahorro auditables (tareas y tokens cloud evitados)."""
    ex = _executor()
    ex.execute("resume esto")
    ex.execute("disena la arquitectura")
    assert ex.local_tasks == 1
    assert ex.cloud_tasks == 1
