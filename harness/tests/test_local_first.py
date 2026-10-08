"""Tests para local_first — politica local-first + concurrente del harness.

Cubre la resolucion por entorno (on/off, paralelismo, tolerancia a valores
invalidos) y la decision ``should_use_local`` en las combinaciones
backend/force_cloud. Valores invalidos de entorno NO rompen: caen al default
con warning; solo ``max_parallel < 1`` viola la invariante (ValueError).
"""

import pytest

from harness.model_router.local_first import (
    ENV_ALLOW_OPEN_TASKS,
    ENV_CLOUD_ORACLE,
    ENV_ENABLED,
    ENV_MAX_PARALLEL,
    LocalFirstPolicy,
)

_ENV_NAMES = (ENV_ENABLED, ENV_MAX_PARALLEL, ENV_ALLOW_OPEN_TASKS, ENV_CLOUD_ORACLE)


def _clear_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Elimina las variables de la politica para aislar cada test.

    Args:
        monkeypatch: Fixture de pytest para manipular el entorno.
    """
    for name in _ENV_NAMES:
        monkeypatch.delenv(name, raising=False)


def test_from_env_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    """Sin entorno, la politica queda local-first, concurrente y con oraculo."""
    _clear_env(monkeypatch)
    policy = LocalFirstPolicy.from_env()
    assert policy.enabled is True
    assert policy.max_parallel == 2
    assert policy.allow_open_tasks is True
    assert policy.cloud_oracle is True


def test_from_env_off_and_custom(monkeypatch: pytest.MonkeyPatch) -> None:
    """El entorno desactiva la politica y ajusta paralelismo y flags."""
    monkeypatch.setenv(ENV_ENABLED, "0")
    monkeypatch.setenv(ENV_MAX_PARALLEL, "8")
    monkeypatch.setenv(ENV_ALLOW_OPEN_TASKS, "0")
    monkeypatch.setenv(ENV_CLOUD_ORACLE, "0")
    policy = LocalFirstPolicy.from_env()
    assert policy.enabled is False
    assert policy.max_parallel == 8
    assert policy.allow_open_tasks is False
    assert policy.cloud_oracle is False


def test_from_env_on_with_truthy_tokens(monkeypatch: pytest.MonkeyPatch) -> None:
    """Valores truthy/falsy tolerantes (on/off, yes/no) se interpretan bien."""
    monkeypatch.setenv(ENV_ENABLED, "on")
    monkeypatch.setenv(ENV_ALLOW_OPEN_TASKS, "no")
    policy = LocalFirstPolicy.from_env()
    assert policy.enabled is True
    assert policy.allow_open_tasks is False


def test_from_env_unknown_bool_falls_back_to_default(monkeypatch: pytest.MonkeyPatch) -> None:
    """Un booleano desconocido cae al default (no lanza)."""
    _clear_env(monkeypatch)
    monkeypatch.setenv(ENV_ENABLED, "quizas")
    assert LocalFirstPolicy.from_env().enabled is True


@pytest.mark.parametrize("raw", ["0", "-2"])
def test_from_env_max_parallel_invalid_raises(monkeypatch: pytest.MonkeyPatch, raw: str) -> None:
    """max_parallel < 1 lanza ValueError accionable."""
    _clear_env(monkeypatch)
    monkeypatch.setenv(ENV_MAX_PARALLEL, raw)
    with pytest.raises(ValueError) as excinfo:
        LocalFirstPolicy.from_env()
    assert "max_parallel" in str(excinfo.value)


def test_from_env_max_parallel_non_int_falls_back(monkeypatch: pytest.MonkeyPatch) -> None:
    """max_parallel no entero cae al default (robustez de entorno)."""
    _clear_env(monkeypatch)
    monkeypatch.setenv(ENV_MAX_PARALLEL, "no-es-entero")
    assert LocalFirstPolicy.from_env().max_parallel == 2


def test_direct_construction_validates_max_parallel() -> None:
    """La invariante max_parallel >= 1 tambien se valida al construir directo."""
    with pytest.raises(ValueError):
        LocalFirstPolicy(max_parallel=0)


def test_should_use_local_matrix() -> None:
    """should_use_local cubre las 4 combinaciones backend/force_cloud."""
    policy = LocalFirstPolicy()
    assert policy.should_use_local(backend_available=True, force_cloud=False) is True
    assert policy.should_use_local(backend_available=False, force_cloud=False) is False
    assert policy.should_use_local(backend_available=True, force_cloud=True) is False
    assert policy.should_use_local(backend_available=False, force_cloud=True) is False


def test_should_use_local_disabled() -> None:
    """Politica deshabilitada nunca usa local aunque el backend este arriba."""
    policy = LocalFirstPolicy(enabled=False)
    assert policy.should_use_local(backend_available=True, force_cloud=False) is False
