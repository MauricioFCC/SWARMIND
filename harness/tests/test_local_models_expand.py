"""Tests de ``_expand_path`` — rutas portables via plantillas ``${VAR}``.

Supuestos de red: ninguno (unidad pura). Cada test mataria al mutante que
quitara la expansion por entorno o rompiera el fail-soft sin env.
"""

from __future__ import annotations

import pytest

from harness.model_router.local_models import _expand_path


def test_expand_resuelve_una_plantilla(monkeypatch: pytest.MonkeyPatch) -> None:
    """``${SWARMIND_LLAMA_DIR}/bin/x`` se resuelve con el env (portable)."""
    # Arrange
    monkeypatch.setenv("SWARMIND_LLAMA_DIR", "/home/u/llama")

    # Act / Assert
    assert _expand_path("${SWARMIND_LLAMA_DIR}/bin/llama-server", "backend") == (
        "/home/u/llama/bin/llama-server"
    )


def test_expand_resuelve_varias_plantillas(monkeypatch: pytest.MonkeyPatch) -> None:
    """Multiples ``${VAR}`` en la misma ruta se resuelven todas."""
    # Arrange
    monkeypatch.setenv("SWARMIND_ROOT", "/opt")
    monkeypatch.setenv("SWARMIND_LLAMA_DIR", "/opt/llama")

    # Act / Assert
    assert _expand_path("${SWARMIND_ROOT}/${SWARMIND_LLAMA_DIR}/models/x.gguf", "model m") == (
        "/opt//opt/llama/models/x.gguf"
    )


def test_expand_fail_soft_sin_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Variable ausente: se conserva la plantilla (no rompe carga sin env)."""
    # Arrange
    monkeypatch.delenv("SWARMIND_LLAMA_DIR", raising=False)

    # Act / Assert
    assert _expand_path("${SWARMIND_LLAMA_DIR}/bin/x", "backend") == (
        "${SWARMIND_LLAMA_DIR}/bin/x"
    )


def test_expand_sin_plantilla_queda_igual() -> None:
    """Ruta sin plantilla no se altera (idempotente)."""
    # Act / Assert
    assert _expand_path(r"C:\llama\llama-server.exe", "backend") == r"C:\llama\llama-server.exe"


def test_expand_con_env_windows(monkeypatch: pytest.MonkeyPatch) -> None:
    """Plantilla + separador Windows: se resuelve y conserva los backslashes."""
    # Arrange
    monkeypatch.setenv("SWARMIND_LLAMA_DIR", r"C:\Users\u\llama")

    # Act / Assert
    assert _expand_path(r"${SWARMIND_LLAMA_DIR}\bin\llama-server.exe", "backend") == (
        r"C:\Users\u\llama\bin\llama-server.exe"
    )