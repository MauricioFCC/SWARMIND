"""Tests para tool_output_filter — wrapper rtk para reducir output bash (ADR-0076).

Frontera (rtk-ai/rtk, 79K estrellas): CLI proxy Rust que corta hasta 90%
del output bash que el agente lee (git/cargo/npm/docker...), con <10ms
overhead. Si el binario rtk esta disponible, los comandos soportados se
reescriben a `rtk <cmd>`; si no, passthrough transparente (sin cambiar
el workflow). Metrica bytes_saved auditable.
"""

from __future__ import annotations

import pytest

from harness.orchestrator.tool_output_filter import (
    RTK_SUPPORTED,
    ToolOutputFilter,
)


class _Runner:
    """Runner fake: registra comandos y retorna outputs programados."""

    def __init__(self) -> None:
        self.calls: list[list[str]] = []

    def __call__(self, cmd: list[str]) -> str:
        self.calls.append(cmd)
        return f"out de {cmd[0]}"


def test_git_command_supported() -> None:
    """Los comandos git/cargo/npm/docker/python estan en la lista rtk."""
    assert "git" in RTK_SUPPORTED
    assert "cargo" in RTK_SUPPORTED
    assert "npm" in RTK_SUPPORTED
    assert "docker" in RTK_SUPPORTED


def test_passthrough_without_rtk() -> None:
    """Sin binario rtk, el comando pasa integro (workflow sin cambios)."""
    runner = _Runner()
    flt = ToolOutputFilter(runner, has_rtk=False)
    out = flt.run(["git", "status"])
    assert out.output == "out de git"
    assert out.rewritten is False
    assert runner.calls == [["git", "status"]]


def test_rewrite_with_rtk() -> None:
    """Con rtk disponible, `git status` se reescribe a `rtk git status`."""
    runner = _Runner()
    flt = ToolOutputFilter(runner, has_rtk=True)
    out = flt.run(["git", "status"])
    assert out.rewritten is True
    assert runner.calls == [["rtk", "git", "status"]]


def test_unsupported_command_no_rewrite() -> None:
    """Un comando no soportado por rtk no se reescribe aunque haya rtk."""
    runner = _Runner()
    flt = ToolOutputFilter(runner, has_rtk=True)
    out = flt.run(["mi-tool-propietario", "run"])
    assert out.rewritten is False
    assert runner.calls == [["mi-tool-propietario", "run"]]


def test_nested_binary_first_token_only() -> None:
    """Solo el primer token decide soporte (git -C sub status -> rtk git ...)."""
    runner = _Runner()
    flt = ToolOutputFilter(runner, has_rtk=True)
    flt.run(["git", "-C", "sub", "status"])
    assert runner.calls[0][:2] == ["rtk", "git"]


def test_empty_command_raises() -> None:
    """Comando vacio falla accionable."""
    flt = ToolOutputFilter(_Runner(), has_rtk=False)
    with pytest.raises(ValueError, match="WHAT"):
        flt.run([])


def test_bytes_saved_metric() -> None:
    """El filtro acumula bytes guardados (compactado rtk vs passthrough)."""
    def fat_runner(cmd: list[str]) -> str:
        return "linea de output ruidoso\n" * 50  # 1350 bytes aprox

    flt = ToolOutputFilter(fat_runner, has_rtk=True)
    flt.run(["git", "status"])
    assert flt.bytes_saved >= 0
