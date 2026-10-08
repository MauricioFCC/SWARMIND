"""Tests para backend_config — SSOT de GPU y backend local (anti-TDR).

`GpuBudget` centraliza el techo de contexto y la reserva de VRAM; `BackendConfig`
la URL/launcher/timeouts del backend local. Ambos se resuelven de entorno
(12-Factor) con alias legacy soportado. Cada test falla si se rompe el override
o una invariante deja de validarse (no son decorativos).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from harness.model_router import backend_config
from harness.model_router.backend_config import (
    DEFAULT_BASE_URL,
    DEFAULT_CTX_STEP,
    DEFAULT_GPU_BUDGET_MB,
    DEFAULT_MIN_FREE_VRAM_MB,
    DEFAULT_MIN_SAFE_CTX,
    DEFAULT_SAFE_CTX_MAX,
    DEFAULT_VRAM_SAFETY,
    BackendConfig,
    GpuBudget,
    discover_config_file,
    discover_executable,
)

#: Variables SWARMIND que afectan a estas dataclasses (limpiadas por test).
_ENV_KEYS = (
    "SWARMIND_GPU_BUDGET_MB",
    "SWARMIND_SAFE_CTX_MAX",
    "SWARMIND_MIN_FREE_VRAM_MB",
    "SWARMIND_MIN_SAFE_CTX",
    "SWARMIND_CTX_STEP",
    "SWARMIND_VRAM_SAFETY",
    "SWARMIND_LOCAL_BASE_URL",
    "SWARMIND_LLAMA_BASE_URL",
    "SWARMIND_LLAMA_EXECUTABLE",
    "SWARMIND_LLAMA_CONFIG",
    "SWARMIND_LLAMA_LAUNCHER",
    "SWARMIND_LLAMA_START_TIMEOUT_S",
    "SWARMIND_LLAMA_POLL_INTERVAL_S",
    "SWARMIND_LOCAL_RETRY_ATTEMPTS",
    "SWARMIND_LOCAL_RETRY_BACKOFF_S",
)


@pytest.fixture
def clean_env(monkeypatch):
    """Entorno SWARMIND limpio: borra las claves antes de cada test.

    Args:
        monkeypatch: Fixture de pytest.

    Returns:
        El monkeypatch para setear overrides puntuales en el test.
    """
    for key in _ENV_KEYS:
        monkeypatch.delenv(key, raising=False)
    return monkeypatch


def test_gpu_budget_defaults(clean_env) -> None:
    """Sin entorno, GpuBudget reproduce el contrato post-BSOD (8GB)."""
    budget = GpuBudget.from_env()
    assert budget.budget_mb == DEFAULT_GPU_BUDGET_MB == 7000
    assert budget.safe_ctx_max == DEFAULT_SAFE_CTX_MAX == 8192
    assert budget.min_free_vram_mb == DEFAULT_MIN_FREE_VRAM_MB == 3000
    assert budget.min_safe_ctx == DEFAULT_MIN_SAFE_CTX == 2048
    assert budget.ctx_step == DEFAULT_CTX_STEP == 1024
    assert budget.vram_safety == DEFAULT_VRAM_SAFETY == 0.85


def test_gpu_budget_env_overrides(clean_env) -> None:
    """Los overrides por entorno cambian el presupuesto (migrar de GPU)."""
    clean_env.setenv("SWARMIND_SAFE_CTX_MAX", "16384")
    clean_env.setenv("SWARMIND_GPU_BUDGET_MB", "24000")
    clean_env.setenv("SWARMIND_MIN_FREE_VRAM_MB", "4000")
    clean_env.setenv("SWARMIND_VRAM_SAFETY", "0.9")
    budget = GpuBudget.from_env()
    assert budget.safe_ctx_max == 16384
    assert budget.budget_mb == 24000
    assert budget.min_free_vram_mb == 4000
    assert budget.vram_safety == 0.9


@pytest.mark.parametrize(
    "env",
    [
        {"SWARMIND_SAFE_CTX_MAX": "0"},
        {"SWARMIND_SAFE_CTX_MAX": "1024", "SWARMIND_MIN_SAFE_CTX": "4096"},
        {"SWARMIND_CTX_STEP": "0"},
        {"SWARMIND_VRAM_SAFETY": "1.5"},
        {"SWARMIND_VRAM_SAFETY": "0"},
        {"SWARMIND_GPU_BUDGET_MB": "0"},
        {"SWARMIND_MIN_FREE_VRAM_MB": "-1"},
    ],
)
def test_gpu_budget_invalid_env_raises(clean_env, env) -> None:
    """Combinaciones de entorno que violan invariantes lanzan ValueError."""
    for key, value in env.items():
        clean_env.setenv(key, value)
    with pytest.raises(ValueError, match="WHAT"):
        GpuBudget.from_env()


def test_backend_config_defaults(clean_env) -> None:
    """Sin entorno, BackendConfig usa los defaults locales."""
    cfg = BackendConfig.from_env()
    assert cfg.base_url == DEFAULT_BASE_URL
    assert cfg.start_timeout_s > 0
    assert cfg.poll_interval_s > 0
    assert cfg.retry_attempts >= 1
    assert cfg.retry_backoff_s >= 0


def test_backend_config_base_url_override(clean_env) -> None:
    """SWARMIND_LOCAL_BASE_URL se aplica y se normaliza (sin slash final)."""
    clean_env.setenv("SWARMIND_LOCAL_BASE_URL", "http://127.0.0.1:9999/")
    assert BackendConfig.from_env().base_url == "http://127.0.0.1:9999"


def test_backend_config_legacy_url_alias(clean_env) -> None:
    """El alias legacy SWARMIND_LLAMA_BASE_URL sigue soportado."""
    clean_env.setenv("SWARMIND_LLAMA_BASE_URL", "http://127.0.0.1:8888")
    assert BackendConfig.from_env().base_url == "http://127.0.0.1:8888"


def test_backend_config_new_url_beats_legacy(clean_env) -> None:
    """Si ambos existen, gana SWARMIND_LOCAL_BASE_URL sobre el legacy."""
    clean_env.setenv("SWARMIND_LOCAL_BASE_URL", "http://127.0.0.1:7777")
    clean_env.setenv("SWARMIND_LLAMA_BASE_URL", "http://127.0.0.1:8888")
    assert BackendConfig.from_env().base_url == "http://127.0.0.1:7777"


def test_backend_config_paths_default_to_none(clean_env) -> None:
    """Sin entorno ni binario descubrible, las rutas opcionales son None."""
    clean_env.setenv("SWARMIND_LLAMA_LAUNCHER", "")
    cfg = BackendConfig.from_env()
    assert cfg.launcher is None


def test_backend_config_executable_from_env(clean_env, tmp_path: Path) -> None:
    """SWARMIND_LLAMA_EXECUTABLE (existente) se usa como binario efectivo."""
    exe = tmp_path / "llama-swap"
    exe.write_text("x", encoding="utf-8")
    clean_env.setenv("SWARMIND_LLAMA_EXECUTABLE", str(exe))
    assert BackendConfig.from_env().executable == exe


def test_backend_config_does_not_hardcode_user_path(clean_env, monkeypatch) -> None:
    """Sin entorno, el default de binario NO es una ruta de usuario fija."""
    monkeypatch.setattr(backend_config.shutil, "which", lambda name: None)
    monkeypatch.setattr(backend_config, "_windows_executable_candidates", lambda: ())
    monkeypatch.setattr(backend_config, "_posix_executable_candidates", lambda: ())
    assert BackendConfig.from_env().executable is None


# ---------------------------------------------------------------------------
# Descubrimiento multiplataforma (sin rutas de usuario hardcodeadas)
# ---------------------------------------------------------------------------


def test_discover_executable_prefers_valid_env(clean_env, tmp_path: Path) -> None:
    """discover_executable usa SWARMIND_LLAMA_EXECUTABLE si existe en disco."""
    exe = tmp_path / "llama-swap.exe"
    exe.write_text("x", encoding="utf-8")
    clean_env.setenv("SWARMIND_LLAMA_EXECUTABLE", str(exe))
    assert discover_executable() == exe


def test_discover_executable_ignores_missing_env(clean_env, monkeypatch) -> None:
    """Un env apuntando a un archivo inexistente se ignora (cae a which/candidatos)."""
    clean_env.setenv("SWARMIND_LLAMA_EXECUTABLE", "/nope/missing-llama-swap")
    monkeypatch.setattr(backend_config.shutil, "which", lambda name: None)
    monkeypatch.setattr(backend_config, "_windows_executable_candidates", lambda: ())
    monkeypatch.setattr(backend_config, "_posix_executable_candidates", lambda: ())
    assert discover_executable() is None


def test_discover_executable_falls_back_to_which(clean_env, monkeypatch, tmp_path: Path) -> None:
    """Sin env valido, discover_executable usa ``shutil.which``."""
    which_path = tmp_path / "llama-swap"
    which_path.write_text("x", encoding="utf-8")
    monkeypatch.setattr(backend_config.shutil, "which", lambda name: str(which_path))
    assert discover_executable() == which_path


def test_discover_executable_uses_platform_candidates(clean_env, monkeypatch, tmp_path: Path) -> None:
    """Sin env ni which, usa los candidatos por plataforma que existan."""
    candidate = tmp_path / "llama-swap.exe"
    candidate.write_text("x", encoding="utf-8")
    monkeypatch.setattr(backend_config.shutil, "which", lambda name: None)
    monkeypatch.setattr(backend_config, "_windows_executable_candidates", lambda: (candidate,))
    monkeypatch.setattr(backend_config, "_posix_executable_candidates", lambda: ())
    assert discover_executable() == candidate


def test_discover_executable_none_when_absent(clean_env, monkeypatch) -> None:
    """discover_executable devuelve None si no hay binario en ningun lado."""
    monkeypatch.setattr(backend_config.shutil, "which", lambda name: None)
    monkeypatch.setattr(backend_config, "_windows_executable_candidates", lambda: ())
    monkeypatch.setattr(backend_config, "_posix_executable_candidates", lambda: ())
    assert discover_executable() is None


def test_discover_config_file_prefers_valid_env(clean_env, tmp_path: Path) -> None:
    """discover_config_file usa SWARMIND_LLAMA_CONFIG si existe en disco."""
    cfg = tmp_path / "llama-swap.yaml"
    cfg.write_text("models: []", encoding="utf-8")
    clean_env.setenv("SWARMIND_LLAMA_CONFIG", str(cfg))
    assert discover_config_file() == cfg


def test_discover_config_file_uses_candidates(clean_env, monkeypatch, tmp_path: Path) -> None:
    """Sin env, discover_config_file usa los candidatos tipicos existentes."""
    cfg = tmp_path / "config.yaml"
    cfg.write_text("models: []", encoding="utf-8")
    monkeypatch.setattr(backend_config, "_config_candidates", lambda: (cfg,))
    assert discover_config_file() == cfg


def test_discover_config_file_none_when_absent(clean_env, monkeypatch) -> None:
    """discover_config_file devuelve None si no hay config en ningun lado."""
    monkeypatch.setattr(backend_config, "_config_candidates", lambda: ())
    assert discover_config_file() is None
