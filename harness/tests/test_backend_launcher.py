"""Tests para backend_launcher — arranque DETACHED/multiplataforma del backend.

Hermeticos: NO se lanzan procesos reales (``subprocess.Popen`` se mockea) y las
plataformas se simulan con monkeypatch de ``os.name``/``sys.platform``. Cubren
``detached_kwargs`` (flags por SO), ``build_launch_command`` (binario / launcher
bat-cmd-sh / ninguno -> excepcion) y ``spawn_detached`` (DEVNULL o log append).
"""

from __future__ import annotations

from pathlib import Path

import pytest
from pytest_mock import MockerFixture

from harness.model_router import backend_launcher as bl
from harness.model_router.backend_config import BackendConfig


def _config(**kw) -> BackendConfig:
    """Config de backend hermética con base_url local fija.

    Returns:
        BackendConfig lista para construir comandos de arranque.
    """
    kw.setdefault("base_url", "http://127.0.0.1:11434")
    return BackendConfig(**kw)


# ---------------------------------------------------------------------------
# detached_kwargs (flags por plataforma)
# ---------------------------------------------------------------------------


def test_detached_kwargs_windows_uses_creationflags(monkeypatch) -> None:
    """En Windows, detached_kwargs devuelve creationflags sin consola."""
    monkeypatch.setattr(bl.os, "name", "nt")
    kwargs = bl.detached_kwargs()
    assert kwargs == {
        "creationflags": (
            bl._WINDOWS_CREATE_NO_WINDOW
            | bl._WINDOWS_DETACHED_PROCESS
            | bl._WINDOWS_CREATE_NEW_PROCESS_GROUP
        )
    }


def test_detached_kwargs_posix_uses_new_session(monkeypatch) -> None:
    """En POSIX, detached_kwargs usa start_new_session (setsid)."""
    monkeypatch.setattr(bl.os, "name", "posix")
    monkeypatch.setattr(bl.sys, "platform", "linux")
    assert bl.detached_kwargs() == {"start_new_session": True}


@pytest.mark.parametrize(
    "os_name,platform",
    [("nt", "linux"), ("posix", "win32")],
)
def test_detached_kwargs_detects_windows_by_either_signal(
    monkeypatch, os_name: str, platform: str
) -> None:
    """Basta os.name='nt' o sys.platform='win*' para elegir la ruta Windows."""
    monkeypatch.setattr(bl.os, "name", os_name)
    monkeypatch.setattr(bl.sys, "platform", platform)
    assert "creationflags" in bl.detached_kwargs()


# ---------------------------------------------------------------------------
# build_launch_command
# ---------------------------------------------------------------------------


def test_build_launch_command_prefers_executable(tmp_path: Path) -> None:
    """Con binario existente, el comando es exe + -config + -listen."""
    exe = tmp_path / "llama-swap.exe"
    exe.write_text("x", encoding="utf-8")
    cfg_file = tmp_path / "llama-swap.yaml"
    cfg_file.write_text("models: []", encoding="utf-8")
    config = _config(executable=exe, config_file=cfg_file)
    assert bl.build_launch_command(config) == [
        str(exe),
        "-config",
        str(cfg_file),
        "-listen",
        "127.0.0.1:11434",
    ]


def test_build_launch_command_bat_launcher_uses_cmd(tmp_path: Path) -> None:
    """Un launcher .bat se ejecuta via ``cmd /c`` (binario ausente)."""
    bat = tmp_path / "start_llama.bat"
    bat.write_text("@echo off", encoding="utf-8")
    assert bl.build_launch_command(_config(launcher=bat)) == ["cmd", "/c", str(bat)]


def test_build_launch_command_cmd_launcher_uses_cmd(tmp_path: Path) -> None:
    """Un launcher .cmd se ejecuta via ``cmd /c`` (binario ausente)."""
    cmd = tmp_path / "start_llama.cmd"
    cmd.write_text("@echo off", encoding="utf-8")
    assert bl.build_launch_command(_config(launcher=cmd)) == ["cmd", "/c", str(cmd)]


def test_build_launch_command_sh_launcher_uses_sh(tmp_path: Path) -> None:
    """Un launcher .sh se ejecuta via ``sh`` (binario ausente)."""
    sh = tmp_path / "start_llama.sh"
    sh.write_text("#!/bin/sh\n", encoding="utf-8")
    assert bl.build_launch_command(_config(launcher=sh)) == ["sh", str(sh)]


def test_build_launch_command_plain_launcher_is_direct(tmp_path: Path) -> None:
    """Un launcher sin sufijo de script se ejecuta directo."""
    other = tmp_path / "start_llama"
    other.write_text("x", encoding="utf-8")
    assert bl.build_launch_command(_config(launcher=other)) == [str(other)]


def test_build_launch_command_raises_when_nothing_exists(tmp_path: Path) -> None:
    """Sin binario ni launcher existentes, lanza BackendLaunchError (WHAT+WHY+WHERE)."""
    config = _config(
        executable=tmp_path / "missing.exe",
        launcher=tmp_path / "missing.bat",
    )
    with pytest.raises(bl.BackendLaunchError, match="WHAT"):
        bl.build_launch_command(config)


# ---------------------------------------------------------------------------
# spawn_detached
# ---------------------------------------------------------------------------


def test_spawn_detached_devnull_and_detached_flags(mocker: MockerFixture, monkeypatch) -> None:
    """spawn_detached usa DEVNULL, close_fds y flags detached (sin shell)."""
    popen = mocker.patch.object(bl.subprocess, "Popen")
    monkeypatch.setattr(bl.os, "name", "posix")
    monkeypatch.setattr(bl.sys, "platform", "linux")
    bl.spawn_detached(["llama-swap", "-listen", "127.0.0.1:11434"])
    popen.assert_called_once()
    _, kwargs = popen.call_args
    assert kwargs["stdin"] is bl.subprocess.DEVNULL
    assert kwargs["stdout"] is bl.subprocess.DEVNULL
    assert kwargs["stderr"] is bl.subprocess.DEVNULL
    assert kwargs["close_fds"] is True
    assert kwargs["shell"] is False
    assert kwargs["start_new_session"] is True


def test_spawn_detached_appends_to_log(mocker: MockerFixture, tmp_path: Path) -> None:
    """Con log_path, stdout/stderr apuntan al archivo append y se crea su carpeta."""
    popen = mocker.patch.object(bl.subprocess, "Popen")
    log_path = tmp_path / "logs" / "backend.log"
    bl.spawn_detached(["llama-swap"], log_path=log_path)
    _, kwargs = popen.call_args
    assert kwargs["stdout"] is not bl.subprocess.DEVNULL
    assert kwargs["stderr"] is kwargs["stdout"]
    assert log_path.exists()


def test_spawn_detached_passes_cwd(mocker: MockerFixture, tmp_path: Path) -> None:
    """spawn_detached propaga el cwd al proceso lanzado."""
    popen = mocker.patch.object(bl.subprocess, "Popen")
    bl.spawn_detached(["llama-swap"], cwd=str(tmp_path))
    _, kwargs = popen.call_args
    assert kwargs["cwd"] == str(tmp_path)


def test_spawn_detached_translates_oserror(mocker: MockerFixture, tmp_path: Path) -> None:
    """Un OSError de Popen se traduce a BackendLaunchError (WHAT+WHY+WHERE)."""
    mocker.patch.object(bl.subprocess, "Popen", side_effect=OSError("boom"))
    with pytest.raises(bl.BackendLaunchError, match="WHAT"):
        bl.spawn_detached(["nope"], cwd=str(tmp_path))
