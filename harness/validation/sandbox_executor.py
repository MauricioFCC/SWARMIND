"""sandbox_executor.py — Sandbox efimero: Docker si existe, subprocess si no (ADR-0081).

WHAT: Ejecuta comandos aislados; backend docker (contenedor efimero con
env inyectado en runtime, nunca en el contexto) o subprocess con timeout
cuando docker no esta disponible. Nunca crashea el harness.
WHY: Frontera (OpenSandbox/Alibaba): credenciales y entorno inyectados en
runtime, no expuestos al agente; aislamiento ante codigo no confiable.
WHERE: `pbt_stage`/`mutation_stage` y tool calls con efectos.

Uso:
    ex = SandboxExecutor()
    out = ex.run(["python", "-c", "print(1+1)"])  # backend auto
"""

from __future__ import annotations

import logging
import shutil
import subprocess
from dataclasses import dataclass

logger = logging.getLogger("harness.validation.sandbox_executor")

#: Timeout default de ejecucion (segundos).
DEFAULT_TIMEOUT_S = 120.0


@dataclass(frozen=True)
class SandboxResult:
    """Resultado de una ejecucion aislada.

    Attributes:
        stdout: Salida estandar (recortada por el caller si hace falta).
        stderr: Salida de error.
        returncode: Codigo de salida del proceso.
        backend: Backend usado ("docker" o "subprocess").
    """

    stdout: str
    stderr: str
    returncode: int
    backend: str


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
        if not cmd:
            raise ValueError(
                "WHAT: comando vacio. "
                "WHY: no hay nada que aislar. "
                "WHERE: SandboxExecutor.run"
            )
        if timeout_s <= 0:
            raise ValueError(
                f"WHAT: timeout invalido: {timeout_s}. "
                "WHY: debe ser positivo para acotar la ejecucion. "
                "WHERE: SandboxExecutor.run"
            )
        if self._backend == "docker":
            return self._run_docker(cmd, timeout_s, env or {})
        return self._run_subprocess(cmd, timeout_s, env)

    def _run_subprocess(
        self, cmd: list[str], timeout_s: float, env: dict[str, str] | None
    ) -> SandboxResult:
        """Ejecuta en subproceso con timeout y env inyectado.

        Args:
            cmd: Comando.
            timeout_s: Timeout.
            env: Variables extra (merge con el entorno actual).

        Returns:
            SandboxResult (timeout -> returncode 124, sin lanzar).
        """
        import os

        merged = dict(os.environ)
        if env:
            merged.update(env)
        try:
            proc = subprocess.run(
                cmd, capture_output=True, text=True,
                timeout=timeout_s, check=False, env=merged,
            )
            return SandboxResult(
                stdout=proc.stdout, stderr=proc.stderr,
                returncode=proc.returncode, backend="subprocess",
            )
        except subprocess.TimeoutExpired as exc:
            logger.warning("sandbox_executor: timeout tras %.0fs (%s)", timeout_s, cmd[0])
            return SandboxResult(
                stdout=exc.stdout.decode() if isinstance(exc.stdout, bytes) else str(exc.stdout or ""),
                stderr=f"timeout tras {timeout_s}s",
                returncode=124, backend="subprocess",
            )

    def _run_docker(
        self, cmd: list[str], timeout_s: float, env: dict[str, str]
    ) -> SandboxResult:
        """Ejecuta en contenedor efimero (--rm) con env inyectado.

        Args:
            cmd: Comando dentro del contenedor.
            timeout_s: Timeout.
            env: Variables inyectadas con -e (nunca en el contexto).

        Returns:
            SandboxResult del contenedor.
        """
        docker_cmd = ["docker", "run", "--rm"]
        for key, value in env.items():
            docker_cmd += ["-e", f"{key}={value}"]
        docker_cmd += [self._image, *cmd]
        try:
            proc = subprocess.run(
                docker_cmd, capture_output=True, text=True,
                timeout=timeout_s, check=False,
            )
            return SandboxResult(
                stdout=proc.stdout, stderr=proc.stderr,
                returncode=proc.returncode, backend="docker",
            )
        except subprocess.TimeoutExpired:
            logger.warning("sandbox_executor: timeout docker tras %.0fs", timeout_s)
            return SandboxResult(
                stdout="", stderr=f"timeout tras {timeout_s}s",
                returncode=124, backend="docker",
            )
