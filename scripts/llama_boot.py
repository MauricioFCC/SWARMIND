"""
llama_boot.py — autostart multiplataforma del backend local (llama.cpp/llama-swap).

WHAT: registra, consulta o elimina el autostart del backend local llama-swap
(protocolo OpenAI en ``http://127.0.0.1:11434``) adaptandose al sistema
operativo:

* Windows: tarea del Task Scheduler (ONLOGON) y, como respaldo silencioso, un
  ``SwarmindLlamaSwap.vbs`` en la carpeta Startup per-user (sin admin).
* macOS: ``LaunchAgent`` (launchd) en ``~/Library/LaunchAgents``.
* Linux: unidad ``systemd --user`` y ``.desktop`` XDG en ``~/.config/autostart``.

WHY: el backend debe estar disponible apenas inicia sesion el equipo sin
arrancarlo a mano; y el harness lo sube bajo demanda si cae
(``harness/model_router/llama_swap_manager.py``). Separar autostart (boot) de
arranque bajo demanda evita que un fallo del backend bloquee el encendido. Los
builders de artefactos son funciones PURAS (sin I/O) para poder testear cada
plataforma sin instalar nada real.
WHERE: ``python scripts/llama_boot.py install|uninstall|status``. El binario, la
config y la direccion de escucha se leen de
``backend_config.BackendConfig`` (SSOT, override por entorno); nunca se
hardcodean rutas de una maquina concreta.

Uso:
    python scripts/llama_boot.py install     # registra autostart al iniciar sesion
    python scripts/llama_boot.py uninstall   # elimina el autostart
    python scripts/llama_boot.py status      # estado del autostart + health del backend
"""

from __future__ import annotations

import argparse
import logging
import os
import subprocess
import sys
from pathlib import Path
from xml.sax.saxutils import escape as _xml_escape

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)

#: Raiz del repo en sys.path[1] (SEG: nunca index 0) para importar el harness.
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(1, str(_ROOT))

from harness.model_router.backend_config import BackendConfig

#: Nombre de la tarea programada en Windows (y base del artefacto VBS).
TASK_NAME = "SwarmindLlamaSwap"
#: Nombre de la unidad systemd de usuario (Linux).
UNIT_NAME = "swarmind-llamaswap.service"
#: Nombre del entry .desktop XDG (Linux, fallback).
DESKTOP_NAME = "swarmind-llamaswap.desktop"
#: Label del LaunchAgent de macOS (tambien nombre del .plist).
MACOS_LABEL = "com.swarmind.llamaswap"
#: Timeout de los comandos de servicio (segundos).
CMD_TIMEOUT_S = 60
#: Retardo tras el logon en Windows: da margen al driver de GPU/escritorio.
LOGON_DELAY = "0000:15"
#: Ruta del endpoint de health (protocolo OpenAI).
MODELS_PATH = "/v1/models"
#: Timeout del health check (segundos).
HEALTH_TIMEOUT_S = 3


def _home(home: Path | None = None) -> Path:
    """Directorio home efectivo (inyectable para tests).

    Args:
        home: Home explicito; None = ``Path.home()``.

    Returns:
        El home a usar, sin rutas de maquina hardcodeadas.
    """
    return home if home is not None else Path.home()


def _config_dir(home: Path | None = None) -> Path:
    """Directorio de configuracion XDG (``$XDG_CONFIG_HOME`` o ``~/.config``).

    Args:
        home: Home explicito; si None se respeta ``XDG_CONFIG_HOME``.

    Returns:
        Directorio base de configuracion del usuario.
    """
    if home is not None:
        return home / ".config"
    xdg = os.environ.get("XDG_CONFIG_HOME")
    return Path(xdg) if xdg else Path.home() / ".config"


def _windows_startup_dir(home: Path | None = None) -> Path:
    """Carpeta Startup per-user de Windows (autostart sin admin).

    Args:
        home: Home explicito; si None se usa ``%APPDATA%``.

    Returns:
        Ruta a ``.../Start Menu/Programs/Startup``.
    """
    if home is not None:
        base = home / "AppData" / "Roaming"
    else:
        appdata = os.environ.get("APPDATA")
        base = Path(appdata) if appdata else Path.home() / "AppData" / "Roaming"
    return base / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"


def _macos_plist_path(home: Path | None = None) -> Path:
    """Ruta del LaunchAgent de macOS.

    Args:
        home: Home explicito; None = ``Path.home()``.

    Returns:
        ``~/Library/LaunchAgents/com.swarmind.llamaswap.plist``.
    """
    return _home(home) / "Library" / "LaunchAgents" / f"{MACOS_LABEL}.plist"


def _linux_unit_path(home: Path | None = None) -> Path:
    """Ruta de la unidad systemd de usuario.

    Args:
        home: Home explicito para tests.

    Returns:
        ``~/.config/systemd/user/swarmind-llamaswap.service``.
    """
    return _config_dir(home) / "systemd" / "user" / UNIT_NAME


def _linux_desktop_path(home: Path | None = None) -> Path:
    """Ruta del entry .desktop de autostart XDG.

    Args:
        home: Home explicito para tests.

    Returns:
        ``~/.config/autostart/swarmind-llamaswap.desktop``.
    """
    return _config_dir(home) / "autostart" / DESKTOP_NAME


def _launch_command(cfg: BackendConfig) -> str:
    """Linea de arranque SILENCIOSA del backend (binario directo).

    Args:
        cfg: Config del backend (SSOT).

    Returns:
        Comando ``"<exe>" -config "<cfg>" -listen <host:puerto>``.
    """
    return f'"{cfg.executable}" -config "{cfg.config_file}" -listen {cfg.listen_address}'


def _vbs_quote(text: str) -> str:
    """Escapa comillas para un literal de cadena en VBScript.

    Args:
        text: Texto a incrustar entre comillas VBS.

    Returns:
        El texto con cada comilla doblada (``"`` -> ``""``).
    """
    return text.replace('"', '""')


def _windows_artifact(cfg: BackendConfig, home: Path | None = None) -> tuple[Path, str]:
    """Artefacto de fallback de Windows: VBS silencioso en Startup.

    Args:
        cfg: Config del backend (SSOT).
        home: Home explicito para tests.

    Returns:
        ``(ruta_del_vbs, contenido)``. El ``Run ... , 0, False`` oculta la
        ventana (0) y no espera a que el backend termine (False).
    """
    path = _windows_startup_dir(home) / f"{TASK_NAME}.vbs"
    command = _vbs_quote(_launch_command(cfg))
    lines = [
        "' SwarmindLlamaSwap - arranca llama-swap (llama.cpp) al iniciar sesion.",
        "' Ventana oculta (0) y sin espera (False): arranque silencioso per-user.",
        'Set shell = CreateObject("WScript.Shell")',
        f'shell.Run "{command}", 0, False',
        "",
    ]
    return path, "\n".join(lines)


def _windows_schtasks_args(cfg: BackendConfig) -> list[str]:
    """Argumentos de ``schtasks`` para registrar la tarea ONLOGON.

    Args:
        cfg: Config del backend (SSOT).

    Returns:
        Lista de argumentos (sin el binario) para ``subprocess.run``.
    """
    return [
        "schtasks", "/Create", "/F", "/TN", TASK_NAME,
        "/SC", "ONLOGON", "/DELAY", LOGON_DELAY, "/TR", _launch_command(cfg),
    ]


def _macos_plist(cfg: BackendConfig, home: Path | None = None) -> tuple[Path, str]:
    """LaunchAgent de macOS que arranca el backend al iniciar sesion.

    Args:
        cfg: Config del backend (SSOT).
        home: Home explicito para tests.

    Returns:
        ``(ruta_del_plist, contenido)`` con ProgramArguments y logs a archivo.
    """
    path = _macos_plist_path(home)
    log = _home(home) / "Library" / "Logs" / "swarmind-llamaswap.log"
    args = (str(cfg.executable), "-config", str(cfg.config_file), "-listen", cfg.listen_address)
    arg_xml = "\n".join(f"        <string>{_xml_escape(arg)}</string>" for arg in args)
    content = "\n".join([
        '<?xml version="1.0" encoding="UTF-8"?>',
        (
            '<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" '
            '"http://www.apple.com/DTDs/PropertyList-1.0.dtd">'
        ),
        '<plist version="1.0">',
        "<dict>",
        "    <key>Label</key>",
        f"    <string>{MACOS_LABEL}</string>",
        "    <key>ProgramArguments</key>",
        "    <array>",
        arg_xml,
        "    </array>",
        "    <key>RunAtLoad</key>",
        "    <true/>",
        "    <key>KeepAlive</key>",
        "    <false/>",
        "    <key>StandardOutPath</key>",
        f"    <string>{_xml_escape(str(log))}</string>",
        "    <key>StandardErrorPath</key>",
        f"    <string>{_xml_escape(str(log))}</string>",
        "</dict>",
        "</plist>",
        "",
    ])
    return path, content


def _linux_unit(cfg: BackendConfig, home: Path | None = None) -> tuple[Path, str]:
    """Unidad systemd de usuario que arranca el backend al iniciar sesion.

    Args:
        cfg: Config del backend (SSOT).
        home: Home explicito para tests.

    Returns:
        ``(ruta_de_la_unit, contenido)`` con ExecStart y restart tolerante.
    """
    path = _linux_unit_path(home)
    content = "\n".join([
        "[Unit]",
        "Description=Swarmind llama-swap backend (llama.cpp)",
        "After=network-online.target",
        "",
        "[Service]",
        "Type=simple",
        f"ExecStart={_launch_command(cfg)}",
        "Restart=on-failure",
        "RestartSec=5",
        "",
        "[Install]",
        "WantedBy=default.target",
        "",
    ])
    return path, content


def _linux_desktop(cfg: BackendConfig, home: Path | None = None) -> tuple[Path, str]:
    """Entry .desktop de autostart XDG (fallback sin systemd).

    Args:
        cfg: Config del backend (SSOT).
        home: Home explicito para tests.

    Returns:
        ``(ruta_del_desktop, contenido)`` con la linea Exec del arranque.
    """
    path = _linux_desktop_path(home)
    content = "\n".join([
        "[Desktop Entry]",
        "Type=Application",
        "Name=Swarmind llama-swap",
        f"Exec={_launch_command(cfg)}",
        "Terminal=false",
        "X-GNOME-Autostart-enabled=true",
        "",
    ])
    return path, content


def _artifacts(cfg: BackendConfig, home: Path | None = None) -> list[tuple[Path, str]]:
    """Artefactos de autostart para la plataforma actual (dispatch puro).

    Args:
        cfg: Config del backend (SSOT).
        home: Home explicito para tests.

    Returns:
        Lista de ``(path, content)`` que corresponden a ``sys.platform``.
    """
    if sys.platform == "win32":
        return [_windows_artifact(cfg, home)]
    if sys.platform == "darwin":
        return [_macos_plist(cfg, home)]
    return [_linux_unit(cfg, home), _linux_desktop(cfg, home)]


def _backend() -> BackendConfig:
    """Config del backend local resuelta del entorno (SSOT).

    Returns:
        BackendConfig con base_url/executable/config/listen efectivos.
    """
    return BackendConfig.from_env()


def _health_url(cfg: BackendConfig) -> str:
    """URL de health del backend local (OpenAI-compatible).

    Args:
        cfg: Config del backend (SSOT).

    Returns:
        Base URL + ``/v1/models``.
    """
    return f"{cfg.base_url}{MODELS_PATH}"


def _run_cmd(args: list[str]) -> subprocess.CompletedProcess:
    """Ejecuta un comando con lista de args y timeout (sin shell).

    Best-effort: ante timeout u OSError devuelve un fallo sintetico, nunca lanza
    ni deja caer install/uninstall/status por un binario de servicio ausente.

    Args:
        args: Comando completo como lista (sin shell: evita CWE-78).

    Returns:
        Resultado del comando, o uno sintetico (returncode 1) ante fallo.
    """
    try:
        return subprocess.run(
            args, capture_output=True, text=True, check=False, timeout=CMD_TIMEOUT_S
        )
    except subprocess.TimeoutExpired:
        logger.warning("llama_boot: '%s' excedio %ss (%s)", args[0], CMD_TIMEOUT_S, args)
        return subprocess.CompletedProcess(args, 1, "", "timeout")
    except OSError as exc:
        logger.warning("llama_boot: no se pudo ejecutar '%s' (%s)", args[0], exc)
        return subprocess.CompletedProcess(args, 1, "", str(exc))


def _install_service(cfg: BackendConfig) -> bool:
    """Registra el servicio de autostart del SO (best-effort).

    Args:
        cfg: Config del backend (SSOT).

    Returns:
        True si el gestor de servicios acepto el alta; False si no esta
        disponible o rechazo la operacion (el artefacto de archivo ya cubre).
    """
    if sys.platform == "win32":
        return _run_cmd(_windows_schtasks_args(cfg)).returncode == 0
    if sys.platform == "darwin":
        plist_path, _ = _macos_plist(cfg)
        return _run_cmd(["launchctl", "load", "-w", str(plist_path)]).returncode == 0
    _run_cmd(["systemctl", "--user", "daemon-reload"])
    return _run_cmd(["systemctl", "--user", "enable", "--now", UNIT_NAME]).returncode == 0


def _uninstall_service(cfg: BackendConfig) -> bool:
    """Da de baja el servicio de autostart del SO (best-effort).

    Args:
        cfg: Config del backend (SSOT).

    Returns:
        True si el gestor de servicios acepto la baja; False en cualquier fallo.
    """
    if sys.platform == "win32":
        return _run_cmd(["schtasks", "/Delete", "/F", "/TN", TASK_NAME]).returncode == 0
    if sys.platform == "darwin":
        plist_path, _ = _macos_plist(cfg)
        return _run_cmd(["launchctl", "unload", "-w", str(plist_path)]).returncode == 0
    return _run_cmd(["systemctl", "--user", "disable", "--now", UNIT_NAME]).returncode == 0


def _health_up(cfg: BackendConfig) -> bool:
    """True si el backend local responde en ``/v1/models``.

    Args:
        cfg: Config del backend (SSOT).

    Returns:
        True si GET ``/v1/models`` responde 200; False en cualquier fallo.
    """
    url = _health_url(cfg)
    try:
        import requests

        return requests.get(url, timeout=HEALTH_TIMEOUT_S).status_code == 200
    except Exception as exc:  # noqa: BLE001 - diagnostico, no crash
        logger.warning("llama_boot: health fallo en %s (%s)", url, exc)
        return False


def _write_text(path: Path, content: str) -> bool:
    """Escribe un artefacto creando sus directorios padre.

    Args:
        path: Ruta destino del artefacto.
        content: Contenido a escribir (UTF-8, sin emojis).

    Returns:
        True si el artefacto quedo escrito; False si hubo OSError.
    """
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    except OSError as exc:
        logger.warning(
            "WHAT: no se pudo escribir %s. WHY: %s. WHERE: llama_boot._write_text", path, exc
        )
        return False
    logger.info("[OK] Autostart escrito: %s", path)
    return True


def _remove_file(path: Path) -> bool:
    """Elimina un artefacto si existe (idempotente).

    Args:
        path: Ruta del artefacto.

    Returns:
        True si el artefacto quedo ausente; False si no se pudo borrar.
    """
    if not path.exists():
        return True
    try:
        path.unlink()
    except OSError as exc:
        logger.warning(
            "WHAT: no se pudo eliminar %s. WHY: %s. WHERE: llama_boot._remove_file", path, exc
        )
        return False
    logger.info("[OK] Autostart eliminado: %s", path)
    return True


def install() -> bool:
    """Registra el autostart del backend para la plataforma actual (idempotente).

    Escribe siempre los artefactos de archivo (fallback garantizado) y ademas
    intenta dar de alta el gestor de servicios del SO. El binario es idempotente,
    asi que un reintento no duplica procesos.

    Returns:
        True si todos los artefactos de archivo quedaron escritos.
    """
    cfg = _backend()
    ok = True
    for path, content in _artifacts(cfg):
        ok = _write_text(path, content) and ok
    if _install_service(cfg):
        logger.info("[OK] Servicio de autostart registrado (%s)", sys.platform)
    else:
        logger.info("[INFO] Servicio no registrado; el artefacto de archivo cubre el arranque.")
    return ok


def uninstall() -> bool:
    """Elimina el autostart del backend para la plataforma actual.

    Remueve los artefactos de archivo y da de baja el servicio del SO
    (best-effort). No falla si el servicio no estaba registrado.

    Returns:
        True si no queda ningun artefacto de archivo del usuario.
    """
    cfg = _backend()
    ok = True
    for path, _ in _artifacts(cfg):
        ok = _remove_file(path) and ok
    if _uninstall_service(cfg):
        logger.info("[OK] Servicio de autostart retirado (%s)", sys.platform)
    return ok


def status() -> int:
    """Imprime el estado del autostart y del backend; retorna exit code.

    Returns:
        0 si hay autostart registrado y el backend responde; 1 en caso contrario.
    """
    cfg = _backend()
    artifacts = _artifacts(cfg)
    for path, _ in artifacts:
        logger.info("  Autostart %s: %s", path.name, "REGISTRADO" if path.exists() else "AUSENTE")
    registered = any(path.exists() for path, _ in artifacts)
    up = _health_up(cfg)
    logger.info("  Backend %s: %s", _health_url(cfg), "ACTIVO" if up else "CAIDO")
    return 0 if (registered and up) else 1


def main() -> int:
    """CLI entry point: install | uninstall | status.

    Returns:
        Exit code del comando (0 exito).
    """
    parser = argparse.ArgumentParser(description="Autostart multiplataforma de llama-swap")
    parser.add_argument("command", choices=["install", "uninstall", "status"])
    args = parser.parse_args()
    logger.info("")
    logger.info("=" * 56)
    logger.info("  llama-swap autostart (llama.cpp) [%s]", sys.platform)
    logger.info("=" * 56)
    if args.command == "install":
        return 0 if install() else 1
    if args.command == "uninstall":
        return 0 if uninstall() else 1
    return status()


if __name__ == "__main__":
    sys.exit(main())
