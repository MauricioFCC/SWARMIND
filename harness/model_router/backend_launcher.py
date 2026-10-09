"""backend_launcher.py — arranque DETACHED y multiplataforma del backend local.

WHAT: centraliza (1) los flags de proceso desacoplado y sin ventana/consola por
plataforma (``detached_kwargs``), (2) el lanzamiento silencioso via
``subprocess.Popen`` (``spawn_detached``) y (3) la construccion del comando de
arranque de llama-swap desde ``BackendConfig`` (``build_launch_command``).
WHY: el arranque bajo demanda parpadeaba consolas en Windows y el comando estaba
acoplado a flags de Windows dentro de ``llama_swap_manager``; aislarlo lo hace
testeable y portable a macOS/Linux (SEG/SBX: sin shell, sin ventanas).
WHERE: ``llama_swap_manager._launch_command`` y ``llama_swap_manager._spawn``.
"""

from __future__ import annotations

import logging
import os
import subprocess
import sys
from pathlib import Path
from typing import IO

from harness.model_router.backend_config import BackendConfig

logger = logging.getLogger("harness.model_router.backend_launcher")

#: Flags de Windows para un proceso desacoplado, sin consola ni grupo heredado.
#: ``getattr`` mantiene el modulo importable en POSIX (donde no existen).
_WINDOWS_CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
_WINDOWS_DETACHED_PROCESS = getattr(subprocess, "DETACHED_PROCESS", 0x00000008)
_WINDOWS_CREATE_NEW_PROCESS_GROUP = getattr(
    subprocess, "CREATE_NEW_PROCESS_GROUP", 0x00000200
)

#: Sufijos de script que requieren interprete (Windows y POSIX).
_WINDOWS_SCRIPT_SUFFIXES = frozenset({".bat", ".cmd"})
_POSIX_SCRIPT_SUFFIX = ".sh"


class BackendLaunchError(RuntimeError):
    """Error de lanzamiento del backend local (WHAT+WHY+WHERE en el mensaje)."""


def _is_windows() -> bool:
    """True si el SO es Windows (por ``os.name`` o ``sys.platform``).

    Consulta ambas senales para ser robusto frente a monkeypatch en tests.

    Returns:
        True en Windows; False en macOS/Linux.
    """
    return os.name == "nt" or sys.platform.startswith("win")


def detached_kwargs() -> dict:
    """Argumentos de ``Popen`` para un proceso desacoplado y sin ventana.

    Windows: ``creationflags`` con ``CREATE_NO_WINDOW`` + ``DETACHED_PROCESS``
    + ``CREATE_NEW_PROCESS_GROUP`` (sin consola ni Ctrl+C heredado). POSIX:
    ``start_new_session=True`` (``setsid``, desacoplado de la terminal).

    Returns:
        Dict de kwargs listo para pasar a ``subprocess.Popen``.
    """
    if _is_windows():
        flags = (
            _WINDOWS_CREATE_NO_WINDOW
            | _WINDOWS_DETACHED_PROCESS
            | _WINDOWS_CREATE_NEW_PROCESS_GROUP
        )
        return {"creationflags": flags}
    return {"start_new_session": True}


def _open_log(log_path: Path) -> IO[str]:
    """Abre (append) el log de arranque creando su carpeta si falta.

    Args:
        log_path: Ruta del archivo de log.

    Returns:
        Handle de texto abierto en modo append.
    """
    log_path.parent.mkdir(parents=True, exist_ok=True)
    return log_path.open("a", encoding="utf-8")


def spawn_detached(
    command: list[str],
    cwd: str | None = None,
    log_path: Path | None = None,
) -> None:
    """Lanza ``command`` desacoplado y SILENCIOSO (sin ventanas ni consola).

    stdin se cierra (``DEVNULL``); stdout/stderr van a ``DEVNULL`` o, si se da
    ``log_path``, al archivo en modo append. Nunca usa shell (SEG: sin
    inyeccion de comandos).

    Args:
        command: Lista de argumentos (argv) a ejecutar.
        cwd: Directorio de trabajo del proceso (None = el actual).
        log_path: Archivo donde anexar stdout/stderr (None = descartar).

    Raises:
        BackendLaunchError: Si el SO impide lanzar el proceso (``OSError``).
    """
    log_handle = _open_log(log_path) if log_path is not None else None
    try:
        output = subprocess.DEVNULL if log_handle is None else log_handle
        subprocess.Popen(
            command,
            cwd=cwd,
            stdin=subprocess.DEVNULL,
            stdout=output,
            stderr=output,
            close_fds=True,
            shell=False,
            **detached_kwargs(),
        )
    except OSError as exc:
        raise BackendLaunchError(
            f"WHAT: no se pudo lanzar {command[0]} ({exc}). "
            "WHY: permisos, binario no ejecutable o ruta inexistente. "
            "WHERE: backend_launcher.spawn_detached"
        ) from exc
    finally:
        if log_handle is not None:
            log_handle.close()


def _launcher_command(launcher: Path) -> list[str]:
    """Comando para ejecutar un launcher segun su sufijo.

    Args:
        launcher: Ruta del script de arranque.

    Returns:
        argv con interprete en Windows (``cmd /c``) o POSIX (``sh``); directo si
        el sufijo no es de script conocido.
    """
    suffix = launcher.suffix.lower()
    if suffix in _WINDOWS_SCRIPT_SUFFIXES:
        return ["cmd", "/c", str(launcher)]
    if suffix == _POSIX_SCRIPT_SUFFIX:
        return ["sh", str(launcher)]
    return [str(launcher)]


def build_launch_command(config: BackendConfig) -> list[str]:
    """Comando de arranque del backend: binario directo o launcher (fallback).

    Prefiere el binario ``llama-swap`` (SILENCIOSO) con ``-config`` y ``-listen``;
    si no existe, usa el launcher (``.bat``/``.cmd`` via ``cmd /c``; ``.sh`` via
    ``sh``).

    Args:
        config: Configuracion resuelta del backend local.

    Returns:
        argv listo para ``subprocess.Popen``.

    Raises:
        BackendLaunchError: Si no existe ni el binario ni el launcher.
    """
    executable = config.executable
    if executable is not None and executable.exists():
        command = [str(executable)]
        if config.config_file is not None:
            command += ["-config", str(config.config_file)]
        command += ["-listen", config.listen_address]
        return command
    launcher = config.launcher
    if launcher is not None and launcher.exists():
        return _launcher_command(launcher)
    raise BackendLaunchError(
        f"WHAT: no existe ni el binario {executable} ni el launcher {launcher}. "
        "WHY: sin ejecutable ni script de arranque no hay backend que lanzar. "
        "WHERE: backend_launcher.build_launch_command"
    )
