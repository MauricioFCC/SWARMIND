"""Tests para llama_swap_manager — ciclo de vida del backend llama.cpp/llama-swap.

Hermeticos: ``requests.get``/``requests.post`` y ``subprocess.Popen`` se
mockean (cero red, cero procesos reales). Cubren el contrato publico:
``resolve_config``, ``is_up``, ``is_ready``, ``list_models``, ``loaded_models``,
``ensure_running`` (idempotente + single-flight), ``warm`` (retry/backoff),
``ensure_model`` (swap robusto), ``verify_swap`` y ``unload_all``. Toda la
suite corre rapida (backoff 0 y timeouts cortos por defecto).
"""

from __future__ import annotations

import threading
import time
from pathlib import Path

import pytest
import requests
from pytest_mock import MockerFixture

from harness.model_router import llama_swap_manager as m


class _Resp:
    """Respuesta HTTP simulada (status + payload JSON)."""

    def __init__(self, status_code: int = 200, payload: dict | None = None) -> None:
        self.status_code = status_code
        self._payload = payload if payload is not None else {}

    def json(self) -> dict:
        """Devuelve el payload JSON simulado."""
        return self._payload


def _manager(tmp_path: Path | None = None, **cfg_kw) -> m.LlamaSwapManager:
    """Construye un manager hermetico y rapido (launcher temporal si se da).

    Por defecto usa ``retry_backoff_s=0`` y ``retry_attempts=2`` para que la
    suite no duerma; los tests de backoff los sobreescriben.
    """
    default_launcher = (tmp_path / "start_llama.bat") if tmp_path else Path(r"C:\nope\start_llama.bat")
    if tmp_path is not None:
        default_launcher.write_text("@echo off", encoding="utf-8")
    cfg_kw.setdefault("launcher", default_launcher)
    cfg_kw.setdefault("base_url", "http://127.0.0.1:11434")
    cfg_kw.setdefault("retry_attempts", 2)
    cfg_kw.setdefault("retry_backoff_s", 0.0)
    return m.LlamaSwapManager(m.LlamaSwapConfig(**cfg_kw))


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------


def test_resolve_config_uses_env_overrides(monkeypatch: pytest.MonkeyPatch) -> None:
    """SWARMIND_LOCAL_BASE_URL / SWARMIND_LLAMA_LAUNCHER sobreescriben defaults."""
    monkeypatch.setenv(m.ENV_BASE_URL, "http://127.0.0.1:9999/")
    monkeypatch.setenv(m.ENV_LAUNCHER, r"C:\custom\start_llama.bat")
    cfg = m.resolve_config()
    assert cfg.base_url == "http://127.0.0.1:9999"
    assert cfg.launcher == Path(r"C:\custom\start_llama.bat")


def test_resolve_config_defaults_to_11434(monkeypatch: pytest.MonkeyPatch) -> None:
    """Sin entorno, la base por defecto es el puerto 11434."""
    monkeypatch.delenv(m.ENV_BASE_URL, raising=False)
    monkeypatch.delenv(m.ENV_BASE_URL_LEGACY, raising=False)
    monkeypatch.delenv(m.ENV_LAUNCHER, raising=False)
    cfg = m.resolve_config()
    assert cfg.base_url == m.DEFAULT_BASE_URL
    assert cfg.base_url.endswith(":11434")


def test_llama_swap_config_alias_is_backend_config() -> None:
    """``LlamaSwapConfig`` es un alias retrocompatible de ``BackendConfig``."""
    assert m.LlamaSwapConfig is m.BackendConfig


def test_launch_command_delegates_to_backend_launcher(tmp_path: Path) -> None:
    """``_launch_command`` delega: binario existente + -config + -listen."""
    exe = tmp_path / "llama-swap.exe"
    exe.write_text("x", encoding="utf-8")
    cfg_file = tmp_path / "llama-swap.yaml"
    cfg_file.write_text("models: []", encoding="utf-8")
    manager = _manager(executable=exe, config_file=cfg_file, launcher=None)
    assert manager._launch_command() == [
        str(exe),
        "-config",
        str(cfg_file),
        "-listen",
        "127.0.0.1:11434",
    ]


def test_spawn_translates_missing_launcher_to_llama_error() -> None:
    """Sin binario ni launcher, ``_spawn`` traduce el error a ``LlamaSwapError``."""
    manager = _manager()  # launcher inexistente + executable None
    with pytest.raises(m.LlamaSwapError, match="WHAT"):
        manager._spawn()


# ---------------------------------------------------------------------------
# is_up / is_ready / list_models / loaded_models
# ---------------------------------------------------------------------------


def test_is_up_true_when_models_ok(mocker: MockerFixture) -> None:
    """is_up → True cuando /v1/models responde 200."""
    mocker.patch.object(m.requests, "get", return_value=_Resp(200, {"data": []}))
    assert _manager().is_up() is True


def test_is_up_false_on_connection_error(mocker: MockerFixture) -> None:
    """is_up → False cuando la conexion falla (backend caido)."""
    mocker.patch.object(m.requests, "get", side_effect=requests.ConnectionError("down"))
    assert _manager().is_up() is False


def test_is_up_false_on_non_200(mocker: MockerFixture) -> None:
    """is_up → False cuando el status no es 200."""
    mocker.patch.object(m.requests, "get", return_value=_Resp(503))
    assert _manager().is_up() is False


def test_is_ready_true_when_health_ok(mocker: MockerFixture) -> None:
    """is_ready → True cuando /v1/models y /health responden."""
    manager = _manager()
    mocker.patch.object(manager, "is_up", return_value=True)
    probe = mocker.patch.object(manager, "_probe", side_effect=[True])
    assert manager.is_ready() is True
    assert probe.call_count == 1


def test_is_ready_false_when_backend_down(mocker: MockerFixture) -> None:
    """is_ready → False si el backend ni siquiera esta vivo."""
    manager = _manager()
    mocker.patch.object(manager, "is_up", return_value=False)
    probe = mocker.patch.object(manager, "_probe")
    assert manager.is_ready() is False
    probe.assert_not_called()


def test_is_ready_falls_back_to_running(mocker: MockerFixture) -> None:
    """is_ready usa /running cuando /health no esta disponible."""
    manager = _manager()
    mocker.patch.object(manager, "is_up", return_value=True)
    mocker.patch.object(manager, "_probe", side_effect=[False, True])
    assert manager.is_ready() is True


def test_is_ready_false_without_diagnostics(mocker: MockerFixture) -> None:
    """is_ready → False si vivo pero sin /health ni /running."""
    manager = _manager()
    mocker.patch.object(manager, "is_up", return_value=True)
    mocker.patch.object(manager, "_probe", side_effect=[False, False])
    assert manager.is_ready() is False


def test_list_models_extracts_ids(mocker: MockerFixture) -> None:
    """list_models extrae data[].id de /v1/models."""
    mocker.patch.object(
        m.requests, "get",
        return_value=_Resp(200, {"data": [{"id": "a"}, {"id": "b"}]}),
    )
    assert _manager().list_models() == ["a", "b"]


def test_loaded_models_parses_running_and_never_raises(mocker: MockerFixture) -> None:
    """loaded_models normaliza /running y devuelve [] si el endpoint falla."""
    mocker.patch.object(
        m.requests, "get",
        return_value=_Resp(200, {"running": [{"model": "m1"}, "m2"]}),
    )
    assert _manager().loaded_models() == ["m1", "m2"]
    mocker.patch.object(m.requests, "get", side_effect=requests.ConnectionError("x"))
    assert _manager().loaded_models() == []


# ---------------------------------------------------------------------------
# ensure_running (single-flight)
# ---------------------------------------------------------------------------


def test_ensure_running_noop_when_already_up(mocker: MockerFixture) -> None:
    """Si ya esta arriba, ensure_running no lanza ningun proceso (idempotente)."""
    manager = _manager()
    mocker.patch.object(manager, "is_up", return_value=True)
    spawn = mocker.patch.object(manager, "_spawn")
    assert manager.ensure_running() is True
    spawn.assert_not_called()


def test_ensure_running_spawns_and_waits_until_up(mocker: MockerFixture, tmp_path: Path) -> None:
    """Si cae, lanza el launcher y espera hasta que /v1/models responde."""
    manager = _manager(tmp_path)
    mocker.patch.object(manager, "is_up", side_effect=[False, True])
    spawn = mocker.patch.object(manager, "_spawn")
    assert manager.ensure_running() is True
    spawn.assert_called_once()


def test_ensure_running_false_when_launcher_missing(mocker: MockerFixture) -> None:
    """Sin launcher existente, ensure_running devuelve False rapido (no crashea)."""
    manager = _manager(start_timeout_s=0.1, poll_interval_s=0.01)
    mocker.patch.object(manager, "is_up", return_value=False)
    started = time.monotonic()
    assert manager.ensure_running() is False
    assert time.monotonic() - started < 1.0  # antes esperaba 90s: bug de lentitud


def test_ensure_running_false_on_timeout(mocker: MockerFixture, tmp_path: Path) -> None:
    """Si el backend nunca responde, ensure_running vence y devuelve False."""
    manager = _manager(tmp_path, start_timeout_s=0.05, poll_interval_s=0.01)
    mocker.patch.object(manager, "is_up", return_value=False)
    mocker.patch.object(manager, "_spawn")
    assert manager.ensure_running() is False


def test_ensure_running_single_flight_two_threads_one_spawn(
    mocker: MockerFixture, tmp_path: Path
) -> None:
    """Dos hilos concurrentes no lanzan dos llama-swap: un solo spawn (TOCTOU)."""
    manager = _manager(tmp_path, start_timeout_s=1.0, poll_interval_s=0.01)
    state = {"up": False}

    def fake_is_up() -> bool:
        return state["up"]

    def fake_spawn() -> None:
        time.sleep(0.05)  # ensancha la ventana de carrera
        state["up"] = True

    mocker.patch.object(manager, "is_up", side_effect=fake_is_up)
    spawn = mocker.patch.object(manager, "_spawn", side_effect=fake_spawn)
    results: list[bool] = []
    barrier = threading.Barrier(2)

    def worker() -> None:
        barrier.wait(timeout=5)
        results.append(manager.ensure_running())

    threads = [threading.Thread(target=worker) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=5)

    assert results == [True, True]
    assert spawn.call_count == 1


# ---------------------------------------------------------------------------
# warm (retry/backoff)
# ---------------------------------------------------------------------------


def test_warm_rejects_empty_model() -> None:
    """warm con id vacio lanza LlamaSwapError (WHAT+WHY+WHERE)."""
    with pytest.raises(m.LlamaSwapError):
        _manager().warm("   ")


def test_warm_true_on_200_false_after_retries(mocker: MockerFixture) -> None:
    """warm → True con 200; False tras agotar reintentos con HTTP != 200."""
    mocker.patch.object(m.requests, "post", return_value=_Resp(200))
    assert _manager().warm("jackod-9b-coder-iq4-xs") is True
    mocker.patch.object(m.requests, "post", return_value=_Resp(500))
    assert _manager(retry_attempts=2, retry_backoff_s=0.0).warm("jackod-9b-coder-iq4-xs") is False


def test_warm_retries_transient_failure(mocker: MockerFixture) -> None:
    """warm reintenta un fallo transitorio y triunfa al segundo intento."""
    post = mocker.patch.object(
        m.requests, "post",
        side_effect=[requests.ConnectionError("flaky"), _Resp(200)],
    )
    assert _manager(retry_attempts=2, retry_backoff_s=0.0).warm("m") is True
    assert post.call_count == 2


def test_warm_gives_up_after_exhausting_retries(mocker: MockerFixture) -> None:
    """warm → False cuando todos los intentos fallan por conexion."""
    post = mocker.patch.object(m.requests, "post", side_effect=requests.ConnectionError("down"))
    assert _manager(retry_attempts=3, retry_backoff_s=0.0).warm("m") is False
    assert post.call_count == 3


def test_request_with_retry_backoff_exponential_with_jitter(mocker: MockerFixture) -> None:
    """El backoff crece exponencialmente (base*2**n) con jitter uniforme (0, techo)."""
    manager = _manager(retry_attempts=3, retry_backoff_s=1.0)
    mocker.patch.object(m.requests, "post", side_effect=requests.ConnectionError("down"))
    sleeps: list[float] = []
    mocker.patch.object(m.time, "sleep", side_effect=lambda delay: sleeps.append(delay))
    mocker.patch.object(m.random, "uniform", side_effect=lambda low, high: high)
    assert manager.warm("m") is False
    assert sleeps == [1.0, 2.0]  # 1.0*2**0 y 1.0*2**1


# ---------------------------------------------------------------------------
# ensure_model (swap robusto) / verify_swap
# ---------------------------------------------------------------------------


def test_ensure_model_noop_when_already_loaded(mocker: MockerFixture) -> None:
    """Si el modelo ya esta cargado, ensure_model no recarga ni descarga."""
    manager = _manager()
    mocker.patch.object(manager, "ensure_running", return_value=True)
    mocker.patch.object(manager, "loaded_models", return_value=["m"])
    warm = mocker.patch.object(manager, "warm", return_value=True)
    unload = mocker.patch.object(manager, "unload_all", return_value=True)
    verify = mocker.patch.object(manager, "verify_swap", return_value=True)
    assert manager.ensure_model("m") is True
    warm.assert_not_called()
    unload.assert_not_called()
    verify.assert_not_called()


def test_ensure_model_unloads_resident_then_warms(mocker: MockerFixture) -> None:
    """Si hay otro modelo residente, lo descarga (best-effort) antes del warm."""
    manager = _manager()
    mocker.patch.object(manager, "ensure_running", return_value=True)
    mocker.patch.object(manager, "loaded_models", return_value=["otro-modelo"])
    unload = mocker.patch.object(manager, "unload_all", return_value=True)
    warm = mocker.patch.object(manager, "warm", return_value=True)
    verify = mocker.patch.object(manager, "verify_swap", return_value=True)
    assert manager.ensure_model("m") is True
    unload.assert_called_once()
    warm.assert_called_once_with("m")
    verify.assert_called_once_with("m")


def test_ensure_model_warms_without_unload_when_vram_free(mocker: MockerFixture) -> None:
    """Sin residentes, ensure_model precarga sin descargar nada."""
    manager = _manager()
    mocker.patch.object(manager, "ensure_running", return_value=True)
    mocker.patch.object(manager, "loaded_models", return_value=[])
    unload = mocker.patch.object(manager, "unload_all", return_value=True)
    mocker.patch.object(manager, "warm", return_value=True)
    mocker.patch.object(manager, "verify_swap", return_value=True)
    assert manager.ensure_model("m") is True
    unload.assert_not_called()


def test_ensure_model_warm_false_skips_load(mocker: MockerFixture) -> None:
    """ensure_model(warm=False) solo garantiza el backend (no carga modelo)."""
    manager = _manager()
    mocker.patch.object(manager, "ensure_running", return_value=True)
    loaded = mocker.patch.object(manager, "loaded_models", return_value=[])
    warm = mocker.patch.object(manager, "warm", return_value=True)
    assert manager.ensure_model("m", warm=False) is True
    warm.assert_not_called()
    loaded.assert_not_called()


def test_ensure_model_false_when_warms_fails(mocker: MockerFixture) -> None:
    """ensure_model → False si el warm final falla (no llama a verify)."""
    manager = _manager()
    mocker.patch.object(manager, "ensure_running", return_value=True)
    mocker.patch.object(manager, "loaded_models", return_value=[])
    mocker.patch.object(manager, "warm", return_value=False)
    verify = mocker.patch.object(manager, "verify_swap", return_value=True)
    assert manager.ensure_model("m") is False
    verify.assert_not_called()


def test_ensure_model_false_when_backend_down(mocker: MockerFixture) -> None:
    """ensure_model → False si el backend no puede arrancar."""
    manager = _manager()
    mocker.patch.object(manager, "ensure_running", return_value=False)
    warm = mocker.patch.object(manager, "warm")
    assert manager.ensure_model("m") is False
    warm.assert_not_called()


def test_verify_swap_true_when_model_resident(mocker: MockerFixture) -> None:
    """verify_swap → True si el modelo aparece en /running."""
    manager = _manager()
    mocker.patch.object(manager, "loaded_models", return_value=["m", "otro"])
    assert manager.verify_swap("m") is True


def test_verify_swap_best_effort_when_running_unavailable(mocker: MockerFixture) -> None:
    """verify_swap → True (no bloquea) si /running esta vacio o no existe."""
    manager = _manager()
    mocker.patch.object(manager, "loaded_models", return_value=[])
    assert manager.verify_swap("m") is True


def test_verify_swap_false_when_model_absent(mocker: MockerFixture) -> None:
    """verify_swap → False si /running responde pero el modelo no figura."""
    manager = _manager()
    mocker.patch.object(manager, "loaded_models", return_value=["otro"])
    assert manager.verify_swap("m") is False


# ---------------------------------------------------------------------------
# unload_all
# ---------------------------------------------------------------------------


def test_unload_all_true_on_200_false_on_error(mocker: MockerFixture) -> None:
    """unload_all → True con 200; False con fallo de red."""
    mocker.patch.object(m.requests, "post", return_value=_Resp(200))
    assert _manager().unload_all() is True
    mocker.patch.object(m.requests, "post", side_effect=requests.ConnectionError("x"))
    assert _manager().unload_all() is False
