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


class _FakeUnsloth:
    """UnslothClient fake (generate retorna str directo)."""

    def __init__(self, available: bool = True, models: list | None = None) -> None:
        self._available = available
        self._models = models if models is not None else ["unsloth/m1"]
        self.calls: list[str] = []

    def is_available(self) -> bool:
        return self._available

    def list_models(self) -> list[str]:
        return list(self._models)

    def generate(self, model: str, prompt: str, **kwargs) -> str:
        self.calls.append(prompt)
        return "respuesta unsloth"


def _executor(**kw):
    from harness.model_router.ollama_tiers import CapabilityTier

    tiers = _FakeTiers(kw.pop("tier", CapabilityTier.FAST))
    # VRAM hermetica por DI: sin GPU real en tests (inmune a purgas de
    # sys.modules como las de test_lazy_loading). El escenario sin-VRAM
    # se cubre con vram_check explicito en sus propios tests.
    kw.setdefault("vram_check", lambda model: True)
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


def test_oversized_task_falls_back_to_cloud() -> None:
    """Tarea que excede la ventana no va a local (anti-loop/OOM)."""
    ex = _executor()
    out = ex.execute("resume esto: " + "x" * 20000)
    assert out.executed_locally is False
    assert "ventana" in out.reason.lower()
    assert ex.cloud_tasks == 1


def test_savings_metric() -> None:
    """Contadores de ahorro auditables (tareas y tokens cloud evitados)."""
    ex = _executor()
    ex.execute("resume esto")
    ex.execute("disena la arquitectura")
    assert ex.local_tasks == 1
    assert ex.cloud_tasks == 1


def test_unsloth_preferred_over_ollama() -> None:
    """Unsloth disponible => se usa primero (0 tokens cloud)."""
    ollama = _FakeClient()
    unsloth = _FakeUnsloth()
    ex = _executor(client=ollama, unsloth_client=unsloth)
    out = ex.execute("resume esto")
    assert out.executed_locally is True
    assert out.output == "respuesta unsloth"
    assert len(unsloth.calls) == 1
    assert ollama.calls == []


def test_unsloth_down_falls_to_ollama() -> None:
    """Unsloth caido => fallback a Ollama (no a cloud directo)."""
    ollama = _FakeClient()
    ex = _executor(client=ollama, unsloth_client=_FakeUnsloth(available=False))
    out = ex.execute("resume esto")
    assert out.executed_locally is True
    assert out.output == "respuesta local"
    assert len(ollama.calls) == 1


def test_unsloth_explicit_model() -> None:
    """unsloth_model override usa ese modelo."""
    unsloth = _FakeUnsloth(models=["a", "b"])
    ex = _executor(client=_FakeClient(), unsloth_client=unsloth,
                   unsloth_model="b")
    out = ex.execute("resume esto")
    assert out.executed_locally is True
    assert "b" in out.model


def test_vram_guard_blocks_without_vram() -> None:
    """Sin VRAM para el modelo va a cloud (anti-OOM)."""
    ex = _executor(vram_check=lambda model: False)
    out = ex.execute("resume esto")
    assert out.executed_locally is False
    assert "vram" in out.reason.lower()


def test_unsloth_blocked_without_vram_falls_to_ollama() -> None:
    """Unsloth grande sin VRAM no genera: cae a Ollama (anti-OOM)."""
    ollama = _FakeClient()
    unsloth = _FakeUnsloth(models=["unsloth/gemma-4-26B"])
    ex = _executor(
        client=ollama, unsloth_client=unsloth,
        vram_check=lambda model: not str(model).startswith("unsloth:"),
    )
    out = ex.execute("resume esto")
    assert out.executed_locally is True
    assert out.output == "respuesta local"
    assert unsloth.calls == []
    assert len(ollama.calls) == 1


def test_keep_alive_passed_to_generate() -> None:
    """El keep_alive del tier viaja al generate (descarga en grandes)."""
    from harness.model_router.ollama_tiers import CapabilityTier

    seen: dict = {}

    class _KAClient(_FakeClient):
        def generate(self, model: str, prompt: str, **kwargs):
            seen.update(kwargs)
            return {"response": "ok", "model": model}

    class _KATiers(_FakeTiers):
        def keep_alive_for(self, tier) -> str:
            return "0"

    ex = LocalExecutor(
        client=_KAClient(), tiers=_KATiers(CapabilityTier.FAST),
        vram_check=lambda model: True,
    )
    out = ex.execute("resume esto")
    assert out.executed_locally is True
    assert seen.get("keep_alive") == "0"
