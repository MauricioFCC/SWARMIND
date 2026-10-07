"""sandbox_executor.py — Sandbox efimero: Docker si existe, subprocess si no (ADR-0081).

WHAT: Ejecuta comandos y scripts aislados; backend docker (contenedor efimero
endurecido, env inyectado en runtime) o subprocess con entorno limpio
(allowlist) y rlimits best-effort cuando docker no esta disponible. Nunca
crashea el harness: devuelve `SandboxResult` con returncode != 0 en vez de
propagar excepciones.
WHY: Frontera (OpenSandbox/Alibaba): credenciales y entorno inyectados en
runtime, no expuestos al agente; aislamiento ante codigo generado por LLM
(CWE-94) ejecutado por los stages PBT/mutation.
WHERE: `pbt_stage`/`mutation_stage` (via `run_script`) y tool calls con efectos
(via `run`).

Nota de seguridad (importante): el backend `subprocess` NO es aislamiento de
OS fuerte. Solo limpia el entorno (allowlist `SAFE_ENV_KEYS`) y aplica rlimits
POSIX best-effort (CPU/memoria/procesos/archivo). Para aislamiento real se
requiere el backend docker (o microVM); en Windows `start_new_session` y los
rlimits no existen y se degrada con `logger.debug` sin abortar.

Uso:
    ex = SandboxExecutor()
    out = ex.run(["python", "-c", "print(1+1)"])  # backend auto
    out = ex.run_script(Path("gen.py"))           # script de LLM
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger("harness.validation.sandbox_executor")

#: Timeout default de ejecucion (segundos).
DEFAULT_TIMEOUT_S = 120.0

# ---------------------------------------------------------------------------
# Endurecimiento docker (CWE-94: aislamiento de codigo no confiable)
# ---------------------------------------------------------------------------

#: Limite de memoria del contenedor.
SANDBOX_MEMORY = "256m"
#: Limite de procesos del contenedor (anti fork-bomb).
SANDBOX_PIDS = "128"
#: Tmpfs efimero: read-write, sin exec, sin suid, con tamano acotado.
SANDBOX_TMPFS = "/tmp:rw,noexec,nosuid,size=64m"
#: Usuario sin privilegios (nobody:nogroup).
SANDBOX_USER = "65534:65534"
#: Punto de montaje read-only del workdir dentro del contenedor.
SANDBOX_WORKDIR = "/work"
#: Interprete Python disponible en la imagen docker por defecto.
PYTHON_IN_CONTAINER = "python"

#: Flags de endurecimiento aplicados SIEMPRE al `docker run`.
DOCKER_HARDENING: tuple[str, ...] = (
    "--network", "none",
    "--read-only",
    "--cap-drop", "ALL",
    "--security-opt", "no-new-privileges",
    "--pids-limit", SANDBOX_PIDS,
    "--memory", SANDBOX_MEMORY,
    "--tmpfs", SANDBOX_TMPFS,
    "--user", SANDBOX_USER,
)

# ---------------------------------------------------------------------------
# Allowlist de entorno para el backend subprocess
# ---------------------------------------------------------------------------

#: Claves de entorno permitidas (minimo funcional del interprete/venv).
SAFE_ENV_KEYS: tuple[str, ...] = (
    "PATH",
    "SYSTEMROOT",
    "TEMP",
    "TMP",
    "PATHEXT",
    "COMSPEC",
    "NUMBER_OF_PROCESSORS",
    "LANG",
    "VIRTUAL_ENV",
    "APPDATA",
    "LOCALAPPDATA",
)

#: Variables Python forzadas en el subproceso aislado.
SAFE_PYTHON_ENV: dict[str, str] = {
    "PYTHONDONTWRITEBYTECODE": "1",
    "PYTHONNOUSERSITE": "1",
    "PYTHONIOENCODING": "utf-8",
}

# ---------------------------------------------------------------------------
# Limites de recursos (rlimits POSIX, best-effort)
# ---------------------------------------------------------------------------

#: Limite de memoria virtual del subproceso (bytes).
SANDBOX_RLIMIT_AS_BYTES: int = 2 * 1024 * 1024 * 1024
#: Limite de tamano de archivo escrito por el subproceso (bytes).
SANDBOX_RLIMIT_FSIZE_BYTES: int = 64 * 1024 * 1024


@dataclass(frozen=True)
class SandboxResult:
    """Resultado de una ejecucion aislada.

    Attributes:
        stdout: Salida estandar (recortada por el caller si hace falta).
        stderr: Salida de error.
        returncode: Codigo de salida del proceso (124 = timeout).
        backend: Backend usado ("docker" o "subprocess").
    """

    stdout: str
    stderr: str
    returncode: int
    backend: str


def _build_safe_env(env: dict[str, str] | None) -> dict[str, str]:
    """Construye un entorno minimo (allowlist) sin secretos del proceso padre.

    Args:
        env: Variables inyectadas explicitamente en runtime (no van al contexto).

    Returns:
        Entorno con solo `SAFE_ENV_KEYS` presentes + flags Python + `env` inyectado.
    """
    safe: dict[str, str] = {
        key: os.environ[key] for key in SAFE_ENV_KEYS if key in os.environ
    }
    safe.update(SAFE_PYTHON_ENV)
    if env:
        safe.update(env)
    return safe


def _decode_partial(value: object) -> str:
    """Decodifica salida parcial de un timeout (puede ser bytes o str).

    Args:
        value: Salida cruda expuesta por `subprocess.TimeoutExpired`.

    Returns:
        Texto decodificado (vacio si no hay salida).
    """
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return str(value or "")


def _build_rlimit_preexec(timeout_s: float) -> Callable[[], None]:
    """Construye un `preexec_fn` POSIX que aplica rlimits best-effort.

    Args:
        timeout_s: Timeout de ejecucion; acota `RLIMIT_CPU`.

    Returns:
        Callable para `preexec_fn` que ignora (no aborta) los rlimits no
        soportados por la plataforma.
    """
    import resource

    cpu_seconds = max(1, int(timeout_s) + 2)
    limits: list[tuple[int, int]] = []
    for attr, value in (
        ("RLIMIT_CPU", cpu_seconds),
        ("RLIMIT_AS", SANDBOX_RLIMIT_AS_BYTES),
        ("RLIMIT_NPROC", int(SANDBOX_PIDS)),
        ("RLIMIT_FSIZE", SANDBOX_RLIMIT_FSIZE_BYTES),
    ):
        resource_id = getattr(resource, attr, None)
        if resource_id is not None:
            limits.append((resource_id, value))

    def _apply_limits() -> None:
        for resource_id, value in limits:
            try:
                resource.setrlimit(resource_id, (value, value))
            except (ValueError, OSError):
                continue

    return _apply_limits


class SandboxExecutor:
    """Ejecutor aislado con deteccion de backend (docker > subprocess).

    Args:
        image: Imagen docker para el backend docker (default python slim).
    """

    def __init__(self, image: str = "python:3.12-slim") -> None:
        """Detecta el backend disponible al construir.

        Args:
            image: Imagen del contenedor efimero (solo backend docker).
        """
        self._image = image
        self._backend = "docker" if shutil.which("docker") is not None else "subprocess"

    @property
    def backend(self) -> str:
        """Backend activo ("docker" o "subprocess")."""
        return self._backend

    def run(
        self,
        cmd: list[str],
        timeout_s: float = DEFAULT_TIMEOUT_S,
        env: dict[str, str] | None = None,
    ) -> SandboxResult:
        """Ejecuta el comando aislado con timeout (nunca lanza).

        Args:
            cmd: Comando y argumentos (lista no vacia).
            timeout_s: Timeout en segundos (> 0).
            env: Variables inyectadas SOLO en runtime (nunca al contexto).

        Returns:
            SandboxResult (returncode != 0 o timeout se reportan, no lanzan).

        Raises:
            ValueError: Si cmd vacio o timeout invalido (WHAT+WHY+WHERE).
        """
        self._validate_request(cmd, timeout_s)
        return self._execute(cmd, timeout_s, env or {}, workdir=None)

    def run_script(
        self,
        script_path: str | Path,
        *,
        timeout_s: float = DEFAULT_TIMEOUT_S,
        env: dict[str, str] | None = None,
        image: str | None = None,
    ) -> SandboxResult:
        """Ejecuta un script Python (codigo no confiable) de forma aislada.

        Backend docker: monta el directorio padre en `/work` (read-only) y
        ejecuta `python /work/<name>`. Backend subprocess: ejecuta
        `sys.executable <script_path>` con `cwd` = directorio padre.

        Args:
            script_path: Ruta del script a ejecutar.
            timeout_s: Timeout en segundos (> 0).
            env: Variables inyectadas en runtime (nunca al contexto).
            image: Imagen docker a usar (default: la del constructor).

        Returns:
            SandboxResult (timeout -> returncode 124; nunca lanza excepcion
            de ejecucion).

        Raises:
            ValueError: Si `script_path` es vacio o `timeout_s` no es positivo.
        """
        script = Path(script_path)
        self._validate_request([str(script)], timeout_s)
        parent = script.parent
        if self._backend == "docker":
            cmd = [PYTHON_IN_CONTAINER, f"{SANDBOX_WORKDIR}/{script.name}"]
            return self._execute(
                cmd, timeout_s, env or {}, parent, image or self._image
            )
        cmd = [sys.executable, str(script)]
        return self._execute(cmd, timeout_s, env or {}, parent)

    @staticmethod
    def _validate_request(cmd: list[str], timeout_s: float) -> None:
        """Valida el comando y el timeout (WHAT+WHY+WHERE).

        Args:
            cmd: Comando a ejecutar.
            timeout_s: Timeout en segundos.

        Raises:
            ValueError: Si cmd vacio o timeout no positivo.
        """
        if not cmd:
            raise ValueError(
                "WHAT: comando vacio. "
                "WHY: no hay nada que aislar. "
                "WHERE: SandboxExecutor.run/run_script"
            )
        if timeout_s <= 0:
            raise ValueError(
                f"WHAT: timeout invalido: {timeout_s}. "
                "WHY: debe ser positivo para acotar la ejecucion. "
                "WHERE: SandboxExecutor.run/run_script"
            )

    def _execute(
        self,
        cmd: list[str],
        timeout_s: float,
        env: dict[str, str],
        workdir: Path | None,
        image: str | None = None,
    ) -> SandboxResult:
        """Despacha al backend activo con los parametros de aislamiento.

        Args:
            cmd: Comando y argumentos.
            timeout_s: Timeout en segundos.
            env: Variables inyectadas en runtime.
            workdir: Directorio de trabajo (montado read-only en docker).
            image: Imagen docker (solo backend docker).

        Returns:
            SandboxResult del backend ejecutado.
        """
        if self._backend == "docker":
            return self._run_docker(cmd, timeout_s, env, workdir, image or self._image)
        return self._run_subprocess(cmd, timeout_s, env, workdir)

    def _run_subprocess(
        self,
        cmd: list[str],
        timeout_s: float,
        env: dict[str, str] | None,
        workdir: Path | None = None,
    ) -> SandboxResult:
        """Ejecuta en subproceso con env limpio, cwd y rlimits best-effort.

        NO es aislamiento de OS fuerte: solo aplica `SAFE_ENV_KEYS` (sin
        secretos heredados), `cwd` acotado y rlimits POSIX best-effort. En
        Windows los rlimits y `start_new_session` no existen: se degrada con
        `logger.debug` y continua.

        Args:
            cmd: Comando.
            timeout_s: Timeout.
            env: Variables extra inyectadas (allowlist + estas).
            workdir: Directorio de trabajo del subproceso (opcional).

        Returns:
            SandboxResult (timeout -> returncode 124, sin lanzar).
        """
        kwargs: dict[str, object] = {
            "capture_output": True,
            "text": True,
            "timeout": timeout_s,
            "env": _build_safe_env(env),
        }
        if workdir is not None:
            kwargs["cwd"] = str(workdir)
        if os.name == "posix":
            kwargs["start_new_session"] = True
            kwargs["preexec_fn"] = _build_rlimit_preexec(timeout_s)
        else:
            logger.debug(
                "sandbox_executor: rlimits/start_new_session no disponibles en %s",
                os.name,
            )
        try:
            proc = subprocess.run(cmd, check=False, **kwargs)  # type: ignore[arg-type]
            return SandboxResult(
                stdout=proc.stdout or "",
                stderr=proc.stderr or "",
                returncode=proc.returncode,
                backend="subprocess",
            )
        except subprocess.TimeoutExpired as exc:
            logger.warning("sandbox_executor: timeout tras %.0fs (%s)", timeout_s, cmd[0])
            return SandboxResult(
                stdout=_decode_partial(exc.stdout),
                stderr=f"timeout tras {timeout_s}s",
                returncode=124,
                backend="subprocess",
            )

    def _run_docker(
        self,
        cmd: list[str],
        timeout_s: float,
        env: dict[str, str],
        workdir: Path | None = None,
        image: str | None = None,
    ) -> SandboxResult:
        """Ejecuta en contenedor efimero (--rm) endurecido con env inyectado.

        Aplica SIEMPRE `DOCKER_HARDENING` (sin red, read-only, sin capabilities,
        sin privilegios, con limites de memoria/procesos/tmpfs). Si se pasa
        `workdir`, lo monta read-only en `/work`.

        Args:
            cmd: Comando dentro del contenedor.
            timeout_s: Timeout.
            env: Variables inyectadas con -e (nunca en el contexto).
            workdir: Directorio a montar read-only en /work (opcional).
            image: Imagen docker (default: la del constructor).

        Returns:
            SandboxResult del contenedor (timeout -> returncode 124).
        """
        docker_cmd = ["docker", "run", "--rm", *DOCKER_HARDENING]
        for key, value in env.items():
            docker_cmd += ["-e", f"{key}={value}"]
        if workdir is not None:
            docker_cmd += [
                "-v", f"{workdir}:{SANDBOX_WORKDIR}:ro",
                "--workdir", SANDBOX_WORKDIR,
            ]
        docker_cmd += [image or self._image, *cmd]
        try:
            proc = subprocess.run(
                docker_cmd, capture_output=True, text=True,
                timeout=timeout_s, check=False,
            )
            return SandboxResult(
                stdout=proc.stdout or "",
                stderr=proc.stderr or "",
                returncode=proc.returncode,
                backend="docker",
            )
        except subprocess.TimeoutExpired:
            logger.warning("sandbox_executor: timeout docker tras %.0fs", timeout_s)
            return SandboxResult(
                stdout="", stderr=f"timeout tras {timeout_s}s",
                returncode=124, backend="docker",
            )
