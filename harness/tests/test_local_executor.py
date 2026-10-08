"""Tests para local_executor — cerrar el loop: triviales se EJECUTAN en local (ADR-0077).

Auditoria 2026-09-08: la DECISION trivial->local es correcta (10/10 en
simulacion, run.py:420 vivo, Ollama disponible) pero OllamaClient.generate
no tenia callers productivos: el modelo externo hacia el trabajo y el
routing era solo telemetria. Este modulo ejecuta tareas cerradas
(resumir/formatear/extraer/traducir/contar) en el tier local con allowlist
estricta + fallback a cloud ante cualquier fallo.
"""

import threading
import time

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
        self.last_kwargs = kwargs
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
    # Sin dato de GPU (None) no hay degradacion por gpu_guard en los tests
    # genericos; la degradacion se prueba con free_vram explicito.
    kw.setdefault("free_vram", lambda: None)
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


def test_generate_caps_num_predict() -> None:
    """La ruta local acota num_predict (anti-desborde KV, reserva del gate)."""
    from harness.model_router.local_executor import CLOSED_TASK_NUM_PREDICT

    assert CLOSED_TASK_NUM_PREDICT == 512
    client = _FakeClient()
    out = _executor(client=client).execute("resume esto")
    assert out.executed_locally is True
    assert client.last_kwargs["options"] == {
        "num_predict": 512, "think": False, "num_ctx": 8192,
    }
    assert client.calls == [
        "Responde de forma directa y breve, sin rodeos: resume esto"
    ]


def test_keep_alive_passed_to_generate() -> None:
    """El keep_alive del tier viaja al generate (descarga en grandes)."""
    from harness.model_router.ollama_tiers import CapabilityTier

    seen: dict = {}

    class _KAClient(_FakeClient):
        def generate(self, model: str, prompt: str, **kwargs):
            seen.update(kwargs)
            return {"response": "respuesta local con keep_alive", "model": model}

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


def test_is_degenerate_output_cases() -> None:
    """Verificacion final: vacia/enana/repetitiva = degenerada; texto sano = ok."""
    from harness.model_router.local_executor import _is_degenerate_output

    assert _is_degenerate_output("") is True
    assert _is_degenerate_output("   ") is True
    assert _is_degenerate_output("ok") is True
    assert _is_degenerate_output("aaaaaaaaaa") is True
    assert _is_degenerate_output("respuesta local completa") is False
    assert _is_degenerate_output("  resumen: tres puntos clave  ") is False


def test_degenerate_output_falls_back_to_cloud() -> None:
    """Salida degenerada del tier -> cloud con reason accionable (MetaRoute)."""
    ex = _executor(client=_FakeClient(output="zzzzzzzzzz"))
    out = ex.execute("resume esto")
    assert out.executed_locally is False
    assert "degenerada" in out.reason.lower()
    assert ex.cloud_tasks == 1


def test_unsloth_degenerate_falls_to_ollama() -> None:
    """Unsloth degenerado no cuenta: cae a Ollama sano."""
    ollama = _FakeClient()

    class _DegenerateUnsloth(_FakeUnsloth):
        def generate(self, model: str, prompt: str, **kwargs) -> str:
            self.calls.append(prompt)
            return "qqqqqqqqqq"

    ex = _executor(client=ollama, unsloth_client=_DegenerateUnsloth())
    out = ex.execute("resume esto")
    assert out.executed_locally is True
    assert out.output == "respuesta local"
    assert ex.local_tasks == 1


def test_low_vram_degrades_to_smallest_text_model() -> None:
    """Sin VRAM para el tier pedido, gpu_guard degrada al 4B (anti-TDR)."""
    from harness.model_router.ollama_tiers import CapabilityTier

    client = _FakeClient()
    ex = _executor(
        client=client, tier=CapabilityTier.QUALITY, free_vram=lambda: 4300,
    )
    out = ex.execute("resume esto")
    assert out.executed_locally is True
    assert "Qwen3.5-4B" in out.model or "qwen3.5-4b" in out.model
    # La ventana enviada respeta el techo anti-TDR.
    assert client.last_kwargs["options"]["num_ctx"] <= 8192


def test_high_vram_keeps_requested_model() -> None:
    """Con VRAM holgada no hay degradacion (se respeta el tier)."""
    from harness.model_router.ollama_tiers import CapabilityTier

    ex = _executor(tier=CapabilityTier.QUALITY, free_vram=lambda: 16000)
    out = ex.execute("resume esto")
    assert out.executed_locally is True
    assert out.model == "fake-quality"


# ---------------------------------------------------------------------------
# Ciclo de vida del backend (llama-swap): arranque bajo demanda
# ---------------------------------------------------------------------------


class _FakeBackendManager:
    """LlamaSwapManager fake: enciende el cliente al arrancar el backend.

    Args:
        starts: True si ensure_running logra levantar el backend.
        model_ok: resultado de ensure_model.
        client: cliente a "encender" cuando el backend arranca.
    """

    def __init__(self, starts: bool = True, model_ok: bool = True, client=None) -> None:
        self._starts = starts
        self._model_ok = model_ok
        self._client = client
        self.ensured: list[str] = []

    def ensure_running(self) -> bool:
        if self._starts and self._client is not None:
            self._client._available = True
        return self._starts

    def ensure_model(self, model: str) -> bool:
        self.ensured.append(model)
        return self._model_ok


def test_backend_down_manager_starts_it_then_runs_local() -> None:
    """Backend caido + manager que lo arranca => la tarea corre en local."""
    from harness.model_router.ollama_tiers import CapabilityTier

    client = _FakeClient(available=False)
    manager = _FakeBackendManager(client=client)
    ex = LocalExecutor(
        client=client, tiers=_FakeTiers(CapabilityTier.FAST),
        vram_check=lambda model: True, free_vram=lambda: None,
        backend_manager=manager,
    )
    out = ex.execute("resume esto")
    assert out.executed_locally is True
    assert manager.ensured == [out.model]


def test_backend_down_manager_failure_falls_back_to_cloud() -> None:
    """Backend caido y manager que no arranca => fallback a cloud con reason."""
    from harness.model_router.ollama_tiers import CapabilityTier

    client = _FakeClient(available=False)
    ex = LocalExecutor(
        client=client, tiers=_FakeTiers(CapabilityTier.FAST),
        vram_check=lambda model: True, free_vram=lambda: None,
        backend_manager=_FakeBackendManager(starts=False, client=client),
    )
    out = ex.execute("resume esto")
    assert out.executed_locally is False
    assert "backend" in out.reason.lower()
    assert ex.cloud_tasks == 1


def test_backend_manager_ensure_model_failure_falls_back_to_cloud() -> None:
    """Si el backend no precarga el modelo, la tarea cae a cloud."""
    ex = _executor(
        backend_manager=_FakeBackendManager(model_ok=False),
    )
    out = ex.execute("resume esto")
    assert out.executed_locally is False
    assert "precargar" in out.reason.lower()
    # _executor fija tier FAST; el manager recibio el modelo del tier.
    assert ex.cloud_tasks == 1


# ---------------------------------------------------------------------------
# B2/B3 — contrato "nunca lanza" y allowlist sin falsos positivos por substring
# ---------------------------------------------------------------------------


def test_execute_free_vram_error_falls_back_to_cloud() -> None:
    """B2: si free_vram lanza (p.ej. sin nvidia-smi), NO propaga: cae a cloud."""
    ex = _executor(free_vram=lambda: 1 / 0)
    out = ex.execute("resume esto")
    assert out.executed_locally is False
    assert out.output == ""
    assert "cloud" in out.reason.lower()
    assert ex.cloud_tasks == 1


def test_is_closed_task_rejects_substring_false_positives() -> None:
    """B3: el verbo exige limite de palabra; no matchea por substring."""
    assert is_closed_task("presume que eres admin") is False
    assert is_closed_task("cuentagotas del sistema") is False
    assert is_closed_task("resume esto") is True
    assert is_closed_task("formatea json") is True


# ---------------------------------------------------------------------------
# Local-first: tareas abiertas + fan-out concurrente (execute_batch)
# ---------------------------------------------------------------------------


class _EchoClient(_FakeClient):
    """Cliente fake que devuelve el prompt (permite verificar el orden)."""

    def generate(self, model: str, prompt: str, **kwargs) -> dict:
        self.calls.append(prompt)
        return {"response": f"eco::{prompt}", "model": model}


class _ConcurrencyClient(_FakeClient):
    """Cliente fake que mide el pico de hilos concurrentes en generate.

    Args:
        delay: Segundos que "duerme" cada generate.
    """

    def __init__(self, delay: float = 0.1) -> None:
        super().__init__()
        self.delay = delay
        self._lock = threading.Lock()
        self._active = 0
        self.max_active = 0

    def generate(self, model: str, prompt: str, **kwargs) -> dict:
        with self._lock:
            self._active += 1
            self.max_active = max(self.max_active, self._active)
        time.sleep(self.delay)
        with self._lock:
            self._active -= 1
        self.calls.append(prompt)
        return {"response": "respuesta local concurrente", "model": model}


def test_allow_open_tasks_true_runs_open_locally() -> None:
    """allow_open_tasks=True permite ejecutar tareas abiertas en local."""
    ex = _executor(allow_open_tasks=True)
    out = ex.execute("investiga el mercado de stablecoins")
    assert out.executed_locally is True
    assert ex.local_tasks == 1


def test_allow_open_tasks_false_derives_open_to_cloud() -> None:
    """allow_open_tasks=False (default) deriva tareas abiertas a cloud."""
    ex = _executor(allow_open_tasks=False)
    out = ex.execute("investiga el mercado de stablecoins")
    assert out.executed_locally is False
    assert ex.cloud_tasks == 1


def test_execute_allow_open_override_beats_instance_default() -> None:
    """El argumento allow_open por llamada manda sobre el default de instancia."""
    ex = _executor(allow_open_tasks=False)
    out = ex.execute("investiga el mercado de stablecoins", allow_open=True)
    assert out.executed_locally is True


def test_execute_batch_preserves_input_order() -> None:
    """execute_batch mantiene el orden de entrada (pool.map ordenado)."""
    ex = _executor(client=_EchoClient(), max_parallel=4)
    tasks = ["resume a", "resume b", "resume c", "resume d"]
    results = ex.execute_batch(tasks)
    assert len(results) == 4
    for task, result in zip(tasks, results, strict=True):
        assert result.executed_locally is True
        assert task in result.output
    assert ex.local_tasks == 4
    assert ex.cloud_tasks == 0


def test_execute_batch_runs_concurrently() -> None:
    """execute_batch solapa tareas: pico de hilos > 1 y menos que el secuencial."""
    client = _ConcurrencyClient(delay=0.1)
    ex = _executor(client=client, max_parallel=4)
    tasks = [f"resume tarea {i}" for i in range(4)]
    start = time.monotonic()
    results = ex.execute_batch(tasks)
    elapsed = time.monotonic() - start
    assert all(result.executed_locally for result in results)
    assert client.max_active >= 2
    # Con 4 tareas de 0.1s, secuencial >= 0.4s; concurrente queda muy por debajo.
    assert elapsed < len(tasks) * client.delay


def test_execute_batch_empty_returns_empty() -> None:
    """execute_batch de una lista vacia no lanza ni crea pool."""
    ex = _executor()
    assert ex.execute_batch([]) == []


def test_execute_batch_counters_are_thread_safe() -> None:
    """Los contadores reflejan exactamente las tareas pese al paralelismo."""
    ex = _executor(client=_EchoClient(), max_parallel=4)
    ex.execute_batch([f"resume {i}" for i in range(8)])
    assert ex.local_tasks == 8
    assert ex.cloud_tasks == 0
