"""Tests para scripts/llama_boot — autostart multiplataforma (win32/darwin/linux).

Verifican que los builders PUROS producen el path y el contenido correctos para
cada plataforma (sin tocar el home real ni instalar servicios), que el dispatch
por ``sys.platform`` elige el artefacto adecuado, que ``status`` devuelve los
exit codes correctos con health mockeado, y que install/uninstall escriben el
artefacto y ejecutan el comando del SO con ``subprocess.run`` mockeado.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from harness.model_router.backend_config import BackendConfig
from scripts import llama_boot as lb

#: Ejecutable y config de prueba (SSOT inyectado, sin rutas de maquina real).
EXE = Path("/opt/swarmind/llama-swap")
CFG_FILE = Path("/opt/swarmind/llama-swap.yaml")


@pytest.fixture
def cfg() -> BackendConfig:
    """BackendConfig de prueba con rutas neutras y listen por defecto.

    Returns:
        BackendConfig con executable/config_file de prueba.
    """
    return BackendConfig(executable=EXE, config_file=CFG_FILE, base_url="http://127.0.0.1:11434")


def test_macos_plist_builder(cfg: BackendConfig, tmp_path: Path) -> None:
    """El plist de macOS trae Label, ProgramArguments, RunAtLoad/KeepAlive y logs."""
    path, content = lb._macos_plist(cfg, home=tmp_path)
    assert path == tmp_path / "Library" / "LaunchAgents" / "com.swarmind.llamaswap.plist"
    assert "<key>Label</key>" in content
    assert "<string>com.swarmind.llamaswap</string>" in content
    assert "<key>ProgramArguments</key>" in content
    assert str(EXE) in content
    assert "<key>RunAtLoad</key>" in content and "<true/>" in content
    assert "<key>KeepAlive</key>" in content and "<false/>" in content
    assert "<key>StandardOutPath</key>" in content
    assert "<key>StandardErrorPath</key>" in content
    assert not path.exists()


def test_linux_unit_builder(cfg: BackendConfig, tmp_path: Path) -> None:
    """La unidad systemd es simple y con ExecStart + Restart=on-failure."""
    path, content = lb._linux_unit(cfg, home=tmp_path)
    assert path == tmp_path / ".config" / "systemd" / "user" / "swarmind-llamaswap.service"
    assert "Type=simple" in content
    assert "ExecStart=" in content
    assert str(EXE) in content
    assert "Restart=on-failure" in content
    assert "WantedBy=default.target" in content


def test_linux_desktop_builder(cfg: BackendConfig, tmp_path: Path) -> None:
    """El .desktop XDG declara el Exec del arranque como fallback."""
    path, content = lb._linux_desktop(cfg, home=tmp_path)
    assert path == tmp_path / ".config" / "autostart" / "swarmind-llamaswap.desktop"
    assert "[Desktop Entry]" in content
    assert "Exec=" in content
    assert str(EXE) in content


def test_windows_vbs_builder(cfg: BackendConfig, tmp_path: Path) -> None:
    """El VBS de Windows arranca oculto y sin espera (', 0, False')."""
    path, content = lb._windows_artifact(cfg, home=tmp_path)
    startup = tmp_path / "AppData" / "Roaming" / "Microsoft" / "Windows"
    assert path == startup / "Start Menu" / "Programs" / "Startup" / "SwarmindLlamaSwap.vbs"
    assert ", 0, False" in content
    assert "WScript.Shell" in content
    assert str(EXE) in content


@pytest.mark.parametrize(
    ("platform", "expected"),
    [("win32", "SwarmindLlamaSwap.vbs"), ("darwin", "com.swarmind.llamaswap.plist")],
)
def test_artifacts_dispatch_single(
    monkeypatch: pytest.MonkeyPatch,
    cfg: BackendConfig,
    tmp_path: Path,
    platform: str,
    expected: str,
) -> None:
    """Windows y macOS despachan un solo artefacto con el nombre esperado."""
    monkeypatch.setattr(lb.sys, "platform", platform)
    artifacts = lb._artifacts(cfg, home=tmp_path)
    assert len(artifacts) == 1
    assert artifacts[0][0].name == expected


def test_artifacts_dispatch_linux(
    monkeypatch: pytest.MonkeyPatch, cfg: BackendConfig, tmp_path: Path
) -> None:
    """Linux despacha unidad systemd + entry .desktop XDG."""
    monkeypatch.setattr(lb.sys, "platform", "linux")
    names = {path.name for path, _ in lb._artifacts(cfg, home=tmp_path)}
    assert names == {"swarmind-llamaswap.service", "swarmind-llamaswap.desktop"}


def test_status_ok_when_artifact_and_health(
    monkeypatch: pytest.MonkeyPatch, cfg: BackendConfig, tmp_path: Path
) -> None:
    """status devuelve 0 si el artefacto existe y el backend responde."""
    artifact = tmp_path / "swarmind-llamaswap.service"
    artifact.write_text("x", encoding="utf-8")
    monkeypatch.setattr(lb, "_artifacts", lambda cfg, home=None: [(artifact, "x")])
    monkeypatch.setattr(lb, "_health_up", lambda cfg: True)
    assert lb.status() == 0


def test_status_fails_when_health_down(
    monkeypatch: pytest.MonkeyPatch, cfg: BackendConfig, tmp_path: Path
) -> None:
    """status devuelve 1 si hay artefacto pero el backend no responde."""
    artifact = tmp_path / "swarmind-llamaswap.service"
    artifact.write_text("x", encoding="utf-8")
    monkeypatch.setattr(lb, "_artifacts", lambda cfg, home=None: [(artifact, "x")])
    monkeypatch.setattr(lb, "_health_up", lambda cfg: False)
    assert lb.status() == 1


def test_status_fails_when_artifact_missing(
    monkeypatch: pytest.MonkeyPatch, cfg: BackendConfig, tmp_path: Path
) -> None:
    """status devuelve 1 si no hay artefacto aunque el backend responda."""
    missing = tmp_path / "ausente.service"
    monkeypatch.setattr(lb, "_artifacts", lambda cfg, home=None: [(missing, "x")])
    monkeypatch.setattr(lb, "_health_up", lambda cfg: True)
    assert lb.status() == 1


def _fake_run(calls: list[list[str]], returncode: int = 0):
    """Crea un reemplazo de ``subprocess.run`` que registra llamadas.

    Args:
        calls: Lista donde se acumulan los comandos ejecutados.
        returncode: Codigo de salida simulado.

    Returns:
        Funcion compatible con ``subprocess.run``.
    """

    def run(args, **_kwargs: object) -> subprocess.CompletedProcess:
        """Registra el comando y devuelve un CompletedProcess simulado."""
        calls.append(list(args))
        return subprocess.CompletedProcess(args, returncode, "", "")

    return run


def test_install_writes_artifact_and_calls_service(
    monkeypatch: pytest.MonkeyPatch, cfg: BackendConfig, tmp_path: Path
) -> None:
    """install escribe el artefacto y ejecuta el gestor de servicios (mocked)."""
    artifact = tmp_path / "autostart" / "swarmind-llamaswap.service"
    monkeypatch.setattr(lb, "_artifacts", lambda cfg, home=None: [(artifact, "content")])
    monkeypatch.setattr(lb.sys, "platform", "linux")
    calls: list[list[str]] = []
    monkeypatch.setattr(lb.subprocess, "run", _fake_run(calls))
    assert lb.install() is True
    assert artifact.read_text(encoding="utf-8") == "content"
    assert any(call[0] == "systemctl" for call in calls)


def test_uninstall_removes_artifact_and_calls_service(
    monkeypatch: pytest.MonkeyPatch, cfg: BackendConfig, tmp_path: Path
) -> None:
    """uninstall elimina el artefacto y ejecuta el gestor de servicios (mocked)."""
    artifact = tmp_path / "autostart" / "swarmind-llamaswap.service"
    artifact.parent.mkdir(parents=True)
    artifact.write_text("x", encoding="utf-8")
    monkeypatch.setattr(lb, "_artifacts", lambda cfg, home=None: [(artifact, "x")])
    monkeypatch.setattr(lb.sys, "platform", "linux")
    calls: list[list[str]] = []
    monkeypatch.setattr(lb.subprocess, "run", _fake_run(calls))
    assert lb.uninstall() is True
    assert not artifact.exists()
    assert any(call[0] == "systemctl" for call in calls)


def test_run_cmd_tolerates_missing_binary(monkeypatch: pytest.MonkeyPatch) -> None:
    """_run_cmd no lanza si el binario del servicio no existe (best-effort)."""
    def boom(_args, **_kwargs: object) -> subprocess.CompletedProcess:
        """Simula un binario ausente."""
        raise OSError("not found")

    monkeypatch.setattr(lb.subprocess, "run", boom)
    result = lb._run_cmd(["systemctl", "--user", "status"])
    assert result.returncode == 1


def test_windows_schtasks_args(cfg: BackendConfig) -> None:
    """Los args de schtasks registran la tarea ONLOGON con el comando de arranque."""
    args = lb._windows_schtasks_args(cfg)
    assert args[:2] == ["schtasks", "/Create"]
    assert "/SC" in args and "ONLOGON" in args
    assert args[args.index("/TN") + 1] == "SwarmindLlamaSwap"
    assert str(EXE) in args[args.index("/TR") + 1]
