"""Tests para request_governor — serializacion, presupuesto y circuit breaker.

Hermeticos: sin GPU, sin red y sin backend real (semaforos frescos inyectados,
reloj falso para el breaker y backend mockeado en la integracion). Cubren el
contrato: ``estimate_prompt_tokens`` monotono, semaforo max-1 (2 hilos no
entran a la vez), ``admit`` fail-fast (prompt > ctx y VRAM sin margen) con
motivo accionable NO-reintentar, ``CircuitBreaker`` (abre tras 3 fallos, 1
probe tras el cooldown) y la integracion (``warm`` y ``execute_batch``
respetan el governor sin tocar el backend al rechazar).
"""

from __future__ import annotations

import threading

import pytest

from harness.model_router import request_governor as g


def _governor(**kw) -> g.RequestGovernor:
    """Governor hermetico: semaforo fresco (no toca el global del proceso)."""
    kw.setdefault("semaphore", threading.Semaphore(1))
    return g.RequestGovernor(**kw)


class _Clock:
    """Reloj monotono falso (el breaker avanza solo cuando el test lo dice)."""

    def __init__(self) -> None:
        """Arranca en t=1000.0."""
        self.now = 1000.0

    def __call__(self) -> float:
        """Devuelve el tiempo actual simulado."""
        return self.now


# ---------------------------------------------------------------------------
# estimate_prompt_tokens
# ---------------------------------------------------------------------------


def test_estimate_empty_is_zero() -> None:
    """Texto vacio estima 0 tokens."""
    assert g.estimate_prompt_tokens("") == 0


def test_estimate_monotonic_with_length() -> None:
    """A mas texto, nunca menos tokens (cota monotona)."""
    sizes = [0, 1, 4, 5, 100, 1000, 33451]
    estimates = [g.estimate_prompt_tokens("x" * size) for size in sizes]
    assert estimates == sorted(estimates)
    assert estimates[0] == 0
    assert g.estimate_prompt_tokens("x" * 100) == 25  # 100 bytes / 4


def test_estimate_counts_bytes_not_chars() -> None:
    """Multibyte cuenta por bytes UTF-8 (cota conservadora ante el backend)."""
    assert g.estimate_prompt_tokens("ñ") == 1  # 2 bytes -> ceil(2/4)


# ---------------------------------------------------------------------------
# Semaforo global (max-1 inferencia local a la vez)
# ---------------------------------------------------------------------------


def test_semaphore_serializes_two_threads() -> None:
    """Dos hilos no entran a la vez: pico de ocupacion == 1."""
    gov = _governor()
    active = 0
    peak = 0
    lock = threading.Lock()
    barrier = threading.Barrier(2)

    def worker() -> None:
        nonlocal active, peak
        barrier.wait(timeout=5)
        with gov.slot(timeout=5.0) as held:
            assert held
            with lock:
                active += 1
                peak = max(peak, active)
            threading.Event().wait(0.05)  # ensancha la ventana de carrera
            with lock:
                active -= 1

    threads = [threading.Thread(target=worker) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)
    assert peak == 1


def test_acquire_timeout_returns_false_when_busy() -> None:
    """Con el slot tomado, acquire(timeout corto) -> False (no bloquea)."""
    gov = _governor()
    assert gov.acquire(timeout=1.0) is True
    try:
        assert gov.acquire(timeout=0.05) is False
    finally:
        gov.release()
    assert gov.acquire(timeout=1.0) is True
    gov.release()


def test_slot_releases_on_exit() -> None:
    """El context manager libera el slot al salir (incluido con excepcion)."""
    gov = _governor()
    with gov.slot(timeout=1.0) as held:
        assert held is True
    assert gov.acquire(timeout=0.1) is True
    gov.release()
    with pytest.raises(RuntimeError, match="boom"), gov.slot(timeout=1.0):
        raise RuntimeError("boom")
    assert gov.acquire(timeout=0.1) is True
    gov.release()


# ---------------------------------------------------------------------------
# admit (fail-fast sin tocar el backend)
# ---------------------------------------------------------------------------


def test_admit_accepts_valid_request() -> None:
    """Prompt que cabe + VRAM con margen -> (True, ok)."""
    ok, reason = _governor().admit(1000, 8192, 6000, 3300)
    assert ok is True
    assert reason.startswith("OK")


def test_admit_rejects_prompt_over_ctx() -> None:
    """El caso tormenta (33451 tokens vs ctx 32768) se rechaza fail-fast."""
    ok, reason = _governor().admit(33451, 32768, 16000, 5000)
    assert ok is False
    assert "WHAT" in reason and "NO reintentar" in reason


def test_admit_rejects_insufficient_vram() -> None:
    """VRAM libre + liberable < footprint + margen -> (False, accionable)."""
    ok, reason = _governor().admit(500, 8192, 2000, 5800)
    assert ok is False
    assert "WHAT" in reason and "NO reintentar" in reason


def test_admit_counts_unloadable_vram() -> None:
    """La VRAM liberable (descargar residentes) suma al presupuesto."""
    gov = _governor()
    ok, _ = gov.admit(500, 8192, 1000, 5800, unloadable_mb=6000)
    assert ok is False  # 7000 < 5800 + 1500
    ok, _ = gov.admit(500, 8192, 1000, 5800, unloadable_mb=7000)
    assert ok is True  # 8000 >= 7300


def test_admit_allows_unknown_vram() -> None:
    """Sin dato de VRAM (None) se permite (ciego, como vram_guard)."""
    ok, _ = _governor().admit(500, 8192, None, 6600)
    assert ok is True


def test_admit_rejects_invalid_params() -> None:
    """Parametros fuera de rango -> (False, WHAT) en vez de excepcion."""
    gov = _governor()
    for args in [(-1, 8192, None, 1000), (10, 0, None, 1000), (10, 8192, None, 0)]:
        ok, reason = gov.admit(*args)
        assert ok is False
        assert "WHAT" in reason


def test_safety_margin_env_override(monkeypatch: pytest.MonkeyPatch) -> None:
    """SWARMIND_VRAM_SAFETY_MARGIN_MB endurece el gate de VRAM."""
    monkeypatch.setenv(g.ENV_SAFETY_MARGIN_MB, "4000")
    gov = _governor()
    assert gov._margin == 4000
    ok, _ = gov.admit(500, 8192, 6000, 3300)  # 6000 < 3300 + 4000
    assert ok is False


# ---------------------------------------------------------------------------
# CircuitBreaker
# ---------------------------------------------------------------------------


def test_breaker_closed_initially() -> None:
    """Sin fallos, el modelo pasa siempre."""
    clock = _Clock()
    breaker = g.CircuitBreaker(time_fn=clock)
    assert breaker.allow("m") is True
    assert breaker.is_open("m") is False


def test_breaker_opens_after_three_failures() -> None:
    """3 fallos consecutivos abren el circuito (fail-fast, sin backend)."""
    clock = _Clock()
    breaker = g.CircuitBreaker(time_fn=clock)
    breaker.record_failure("m")
    breaker.record_failure("m")
    assert breaker.allow("m") is True
    breaker.record_failure("m")
    assert breaker.allow("m") is False
    assert breaker.is_open("m") is True


def test_breaker_probe_after_cooldown() -> None:
    """Tras el cooldown pasa 1 probe; si triunfa, el circuito cierra."""
    clock = _Clock()
    breaker = g.CircuitBreaker(cooldown_s=60.0, time_fn=clock)
    for _ in range(3):
        breaker.record_failure("m")
    assert breaker.allow("m") is False
    clock.now += 61.0
    assert breaker.allow("m") is True  # el probe
    assert breaker.allow("m") is False  # solo 1 probe en vuelo
    breaker.record_success("m")
    assert breaker.allow("m") is True
    assert breaker.is_open("m") is False


def test_breaker_failed_probe_reopens() -> None:
    """Si el probe falla, el circuito reabre por otro cooldown completo."""
    clock = _Clock()
    breaker = g.CircuitBreaker(cooldown_s=60.0, time_fn=clock)
    for _ in range(3):
        breaker.record_failure("m")
    clock.now += 61.0
    assert breaker.allow("m") is True
    breaker.record_failure("m")
    assert breaker.allow("m") is False
    clock.now += 61.0
    assert breaker.allow("m") is True


def test_breaker_success_resets_count() -> None:
    """Un exito intermedio resetea la racha (2 fallos + exito + 2 fallos = pasa)."""
    clock = _Clock()
    breaker = g.CircuitBreaker(time_fn=clock)
    breaker.record_failure("m")
    breaker.record_failure("m")
    breaker.record_success("m")
    breaker.record_failure("m")
    breaker.record_failure("m")
    assert breaker.allow("m") is True


def test_breaker_is_per_model() -> None:
    """El circuito de un modelo roto no bloquea a los demas."""
    clock = _Clock()
    breaker = g.CircuitBreaker(time_fn=clock)
    for _ in range(3):
        breaker.record_failure("roto")
    assert breaker.allow("roto") is False
    assert breaker.allow("sano") is True


def test_breaker_env_overrides(monkeypatch: pytest.MonkeyPatch) -> None:
    """SWARMIND_CB_MAX_FAILURES / SWARMIND_CB_COOLDOWN_S reconfiguran el breaker."""
    monkeypatch.setenv(g.ENV_CB_MAX_FAILURES, "2")
    monkeypatch.setenv(g.ENV_CB_COOLDOWN_S, "5")
    clock = _Clock()
    breaker = g.CircuitBreaker(time_fn=clock)
    breaker.record_failure("m")
    assert breaker.allow("m") is True
    breaker.record_failure("m")
    assert breaker.allow("m") is False
    clock.now += 6.0
    assert breaker.allow("m") is True


def test_governor_delegates_breaker() -> None:
    """El governor expone el breaker (allow/record) por modelo."""
    gov = _governor()
    for _ in range(3):
        gov.record_failure("m")
    assert gov.allow("m") is False
    gov.record_success("m")
    assert gov.allow("m") is True


# ---------------------------------------------------------------------------
# Integracion: warm respeta admit + breaker sin tocar el backend
# ---------------------------------------------------------------------------


def test_warm_rejects_oversized_prompt_without_backend() -> None:
    """warm con prompt > ctx retorna False SIN llamar al backend (anti-tormenta)."""
    from harness.model_router import llama_swap_manager as m

    manager = m.LlamaSwapManager.__new__(m.LlamaSwapManager)
    manager._config = m.LlamaSwapConfig(base_url="http://127.0.0.1:11434")
    manager._governor = _governor()
    calls: list[str] = []
    manager._request_with_retry = lambda *a, **k: calls.append("backend") or None  # type: ignore[method-assign]
    ok = manager.warm(
        "algun-modelo", prompt_tokens=33451, model_ctx=32768,
        free_vram_mb=16000, footprint_mb=5000,
    )
    assert ok is False
    assert calls == []


def test_warm_skips_backend_when_circuit_open() -> None:
    """warm con circuito abierto retorna False SIN llamar al backend."""
    from harness.model_router import llama_swap_manager as m

    gov = _governor()
    for _ in range(3):
        gov.record_failure("roto")
    manager = m.LlamaSwapManager.__new__(m.LlamaSwapManager)
    manager._config = m.LlamaSwapConfig(base_url="http://127.0.0.1:11434")
    manager._governor = gov
    calls: list[str] = []
    manager._request_with_retry = lambda *a, **k: calls.append("backend") or None  # type: ignore[method-assign]
    assert manager.warm("roto") is False
    assert calls == []


# ---------------------------------------------------------------------------
# Integracion: execute_batch respeta el semaforo
# ---------------------------------------------------------------------------


def test_execute_batch_busy_governor_falls_back_to_cloud() -> None:
    """Con el slot tomado, execute_batch deriva todo a cloud (sin bloquear)."""
    from harness.model_router.local_executor import LocalExecutor

    class _Tiers:
        def tier_for_task(self, task: str) -> str:
            return "fast"

        def model_for(self, tier: object) -> str:
            return "fake-fast"

    class _Client:
        def is_available(self) -> bool:
            return True

        def generate(self, model: str, prompt: str, **kwargs) -> dict:
            raise AssertionError("no debe tocar el backend sin slot")

    gov = g.RequestGovernor(semaphore=threading.Semaphore(1), acquire_timeout_s=0.05)
    assert gov.acquire(timeout=1.0) is True  # el slot queda tomado
    try:
        executor = LocalExecutor(
            client=_Client(), tiers=_Tiers(), vram_check=lambda model: True,
            free_vram=lambda: None, governor=gov,
        )
        results = executor.execute_batch(["resume a", "resume b"])
    finally:
        gov.release()
    assert len(results) == 2
    assert all(result.executed_locally is False for result in results)
