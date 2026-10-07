"""sandbox_executor.py — Sandbox efimero portable: Docker > Job Object > bwrap > subprocess.

WHAT: Ejecuta comandos y scripts aislados con deteccion automatica de backend
por prioridad: `docker` (contenedor efimero endurecido), `windows-jobobject`
(Job Object nativo de Windows via ctypes), `bwrap` (bubblewrap en Linux) o
`subprocess` (env limpio + rlimits POSIX best-effort). Nunca crashea el
harness: devuelve `SandboxResult` con returncode != 0 en vez de propagar
excepciones.
WHY: Frontera (OpenSandbox/Alibaba): credenciales y entorno inyectados en
runtime, no expuestos al agente; aislamiento ante codigo generado por LLM
(CWE-94) ejecutado por los stages PBT/mutation.
WHERE: `pbt_stage`/`mutation_stage` (via `run_script`) y tool calls con efectos
(via `run`).

Prioridad de backends (`_detect_backend`):
    1. `docker`            — si `shutil.which("docker")` existe.
    2. `windows-jobobject` — si `os.name == "nt"` y `kernel32` expone
       `CreateJobObjectW` (portable, sin deps, sin Docker).
    3. `bwrap`             — si `shutil.which("bwrap")` existe (Linux).
    4. `subprocess`        — fallback universal (deteccion debil).

Aislamiento por backend:
    - `docker`: red/FS/caps/privilegios/pids/memoria/tmpfs (fuerte).
    - `windows-jobobject`: recursos (memoria ~2 GiB, max 128 procesos), kill
      tree al cerrar el job (`KILL_ON_JOB_CLOSE`) y env limpio. NO aísla FS ni
      red: es una barrera de recursos + limpieza de arbol, no un sandbox de OS
      fuerte.
    - `bwrap`: namespaces (red/PID/FS) con binds read-only (fuerte, Linux).
    - `subprocess`: solo env limpio (allowlist `SAFE_ENV_KEYS`) y rlimits POSIX
      best-effort. NO es aislamiento de OS fuerte; en Windows cae aqui cuando
      el Job Object no esta disponible.

Nota de seguridad: en Windows `start_new_session` y los rlimits no existen; el
backend `windows-jobobject` cubre parcialmente ese hueco con un Job Object
nativo (recursos + kill-tree + env limpio), pero NO aísla filesystem ni red.

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
# Backends disponibles y prioridad (deteccion en `_detect_backend`)
# ---------------------------------------------------------------------------

#: Backend docker (contenedor efimero endurecido).
BACKEND_DOCKER = "docker"
#: Backend Windows Job Object (nativo, portable, sin Docker).
BACKEND_JOB_OBJECT = "windows-jobobject"
#: Backend bubblewrap (namespaces en Linux).
BACKEND_BWRAP = "bwrap"
#: Backend subprocess (fallback universal, deteccion debil).
BACKEND_SUBPROCESS = "subprocess"

# ---------------------------------------------------------------------------
# Windows Job Object (portable, sin deps: ctypes sobre kernel32)
# ---------------------------------------------------------------------------

#: Clase de informacion `JobObjectExtendedLimitInformation` de SetInformationJobObject.
JOB_OBJECT_EXTENDED_LIMIT_INFORMATION = 9
#: Maximo de procesos activos simultaneos en el job (anti fork-bomb).
JOB_OBJECT_ACTIVE_PROCESS = 128
#: Limite de memoria total del job (bytes).
JOB_OBJECT_MEMORY_BYTES = 2 * 1024**3
#: Flag de creacion de proceso: sin ventana de consola.
CREATE_NO_WINDOW = 0x08000000
#: `JOB_OBJECT_LIMIT_*`: mata el arbol al cerrar el ultimo handle del job.
JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x2000
#: `JOB_OBJECT_LIMIT_*`: aplica `ActiveProcessLimit`.
JOB_OBJECT_LIMIT_ACTIVE_PROCESS = 0x8
#: `JOB_OBJECT_LIMIT_*`: aplica `JobMemoryLimit`.
JOB_OBJECT_LIMIT_JOB_MEMORY = 0x200
#: `JOB_OBJECT_LIMIT_*`: mata el proceso ante excepcion no manejada.
JOB_OBJECT_LIMIT_DIE_ON_UNHANDLED_EXCEPTION = 0x400

#: Flags de limite combinados aplicados SIEMPRE al Job Object.
JOB_OBJECT_LIMIT_FLAGS = (
    JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
    | JOB_OBJECT_LIMIT_ACTIVE_PROCESS
    | JOB_OBJECT_LIMIT_JOB_MEMORY
    | JOB_OBJECT_LIMIT_DIE_ON_UNHANDLED_EXCEPTION
)

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


# ---------------------------------------------------------------------------
# Windows Job Object: carga perezosa de kernel32 y structs ctypes
# ---------------------------------------------------------------------------

#: Cache del modulo kernel32 (None si no aplica/falla); `_KERNEL32_LOADED`
#: evita reintentar la carga en cada llamada.
_KERNEL32: object | None = None
_KERNEL32_LOADED = False


def _load_kernel32() -> object | None:
    """Carga `kernel32` de forma perezosa SOLO en Windows.

    Returns:
        DLL `kernel32` si `os.name == "nt"` y expone `CreateJobObjectW`;
        `None` en Linux/macOS o si la carga falla (nunca lanza).
    """
    global _KERNEL32, _KERNEL32_LOADED
    if _KERNEL32_LOADED:
        return _KERNEL32
    _KERNEL32_LOADED = True
    if os.name != "nt":
        return None
    try:
        import ctypes

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    except (OSError, AttributeError, ImportError):
        logger.warning("sandbox_executor: kernel32 no disponible; sin Job Object")
        return None
    if not hasattr(kernel32, "CreateJobObjectW"):
        logger.warning("sandbox_executor: kernel32 sin CreateJobObjectW")
        return None
    _KERNEL32 = kernel32
    return kernel32


#: Cache de las structs ctypes del Job Object (definidas perezosamente).
_JOB_STRUCTS: dict[str, type] | None = None


def _jobobject_structs() -> dict[str, type]:
    """Define y cachea las structs ctypes del Job Object (Windows-only).

    Returns:
        Dict con `EXTENDED_LIMIT` (`JOBOBJECT_EXTENDED_LIMIT_INFORMATION`),
        `BASIC_LIMIT` y `IO_COUNTERS` mapeados 1:1 al layout C de Windows.
    """
    global _JOB_STRUCTS
    if _JOB_STRUCTS is not None:
        return _JOB_STRUCTS
    import ctypes
    from ctypes import wintypes

    class _IO_COUNTERS(ctypes.Structure):
        """Contadores de I/O del job (`IO_COUNTERS`)."""

        _fields_ = [
            ("ReadOperationCount", ctypes.c_ulonglong),
            ("WriteOperationCount", ctypes.c_ulonglong),
            ("OtherOperationCount", ctypes.c_ulonglong),
            ("ReadTransferCount", ctypes.c_ulonglong),
            ("WriteTransferCount", ctypes.c_ulonglong),
            ("OtherTransferCount", ctypes.c_ulonglong),
        ]

    class _JOBOBJECT_BASIC_LIMIT_INFORMATION(ctypes.Structure):
        """Limites basicos del job (`JOBOBJECT_BASIC_LIMIT_INFORMATION`)."""

        _fields_ = [
            ("PerProcessUserTimeLimit", ctypes.c_longlong),
            ("PerJobUserTimeLimit", ctypes.c_longlong),
            ("LimitFlags", wintypes.DWORD),
            ("MinimumWorkingSetSize", ctypes.c_size_t),
            ("MaximumWorkingSetSize", ctypes.c_size_t),
            ("ActiveProcessLimit", wintypes.DWORD),
            ("Affinity", ctypes.c_size_t),
            ("PriorityClass", wintypes.DWORD),
            ("SchedulingClass", wintypes.DWORD),
        ]

    class _JOBOBJECT_EXTENDED_LIMIT_INFORMATION(ctypes.Structure):
        """Limites extendidos del job (`JOBOBJECT_EXTENDED_LIMIT_INFORMATION`)."""

        _fields_ = [
            ("BasicLimitInformation", _JOBOBJECT_BASIC_LIMIT_INFORMATION),
            ("IoInfo", _IO_COUNTERS),
            ("ProcessMemoryLimit", ctypes.c_size_t),
            ("JobMemoryLimit", ctypes.c_size_t),
            ("PeakProcessMemoryUsed", ctypes.c_size_t),
            ("PeakJobMemoryUsed", ctypes.c_size_t),
        ]

    _JOB_STRUCTS = {
        "IO_COUNTERS": _IO_COUNTERS,
        "BASIC_LIMIT": _JOBOBJECT_BASIC_LIMIT_INFORMATION,
        "EXTENDED_LIMIT": _JOBOBJECT_EXTENDED_LIMIT_INFORMATION,
    }
    return _JOB_STRUCTS


def _configure_kernel32(kernel32: object) -> None:
    """Declara prototypes de kernel32 (evita truncar handles de 64 bits).

    Args:
        kernel32: DLL kernel32 (o fake compatible con atributos `argtypes`/
            `restype`).
    """
    import ctypes
    from ctypes import wintypes

    kernel32.CreateJobObjectW.restype = wintypes.HANDLE
    kernel32.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
    kernel32.SetInformationJobObject.restype = wintypes.BOOL
    kernel32.SetInformationJobObject.argtypes = [
        wintypes.HANDLE,
        ctypes.c_int,
        ctypes.c_void_p,
        wintypes.DWORD,
    ]
    kernel32.AssignProcessToJobObject.restype = wintypes.BOOL
    kernel32.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
    kernel32.CloseHandle.restype = wintypes.BOOL
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]


def _detect_backend() -> str:
    """Detecta el backend disponible por prioridad (nunca lanza).

    Returns:
        `BACKEND_DOCKER` > `BACKEND_JOB_OBJECT` (Windows) > `BACKEND_BWRAP`
        (Linux) > `BACKEND_SUBPROCESS`.
    """
    if shutil.which(BACKEND_DOCKER) is not None:
        return BACKEND_DOCKER
    if os.name == "nt" and _load_kernel32() is not None:
        return BACKEND_JOB_OBJECT
    if shutil.which(BACKEND_BWRAP) is not None:
        return BACKEND_BWRAP
    return BACKEND_SUBPROCESS


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
        self._backend = _detect_backend()

    @property
    def backend(self) -> str:
        """Backend activo (`docker`, `windows-jobobject`, `bwrap` o `subprocess`)."""
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
        if self._backend == BACKEND_DOCKER:
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
        if self._backend == BACKEND_DOCKER:
            return self._run_docker(cmd, timeout_s, env, workdir, image or self._image)
        if self._backend == BACKEND_JOB_OBJECT:
            return self._run_windows_jobobject(cmd, timeout_s, env, workdir)
        if self._backend == BACKEND_BWRAP:
            return self._run_bwrap(cmd, timeout_s, env, workdir)
        return self._run_subprocess(cmd, timeout_s, env, workdir)

    def _run_windows_jobobject(
        self,
        cmd: list[str],
        timeout_s: float,
        env: dict[str, str] | None,
        workdir: Path | None = None,
    ) -> SandboxResult:
        """Ejecuta el hijo dentro de un Windows Job Object (portable, sin Docker).

        Crea un Job Object, fija `JOBOBJECT_EXTENDED_LIMIT_INFORMATION` (kill
        on close, limite de procesos y memoria), lanza el hijo con env limpio y
        lo asigna al job. Al cerrar el handle del job, `KILL_ON_JOB_CLOSE` mata
        todo el arbol de procesos. NO aísla filesystem ni red. Si el Job Object
        no se puede crear/fijar/asignar (p. ej. el proceso ya vive en un job sin
        breakaway), degrada a `_run_subprocess` con `logger.warning` (nunca
        crashea).

        Args:
            cmd: Comando y argumentos.
            timeout_s: Timeout en segundos (> 0).
            env: Variables inyectadas en runtime (nunca al contexto).
            workdir: Directorio de trabajo del hijo (opcional).

        Returns:
            SandboxResult (timeout -> returncode 124, sin lanzar).
        """
        import ctypes

        kernel32 = _load_kernel32()
        if kernel32 is None:
            logger.warning(
                "sandbox_executor: Kernel32 sin Job Object; degrada a subprocess"
            )
            return self._run_subprocess(cmd, timeout_s, env, workdir)

        _configure_kernel32(kernel32)
        structs = _jobobject_structs()
        job = kernel32.CreateJobObjectW(None, None)
        if not job:
            logger.warning(
                "sandbox_executor: CreateJobObjectW fallo (errno=%s); degrada a subprocess",
                ctypes.get_last_error() if os.name == "nt" else "n/a",
            )
            return self._run_subprocess(cmd, timeout_s, env, workdir)

        try:
            self._apply_job_limits(kernel32, ctypes, structs, job)
            proc = self._spawn_job_child(cmd, env, workdir)
            if not kernel32.AssignProcessToJobObject(job, proc._handle):
                logger.warning(
                    "sandbox_executor: AssignProcessToJobObject fallo; "
                    "degrada a subprocess"
                )
                proc.kill()
                proc.communicate()
                return self._run_subprocess(cmd, timeout_s, env, workdir)
            return self._collect_job_result(proc, timeout_s)
        finally:
            kernel32.CloseHandle(job)

    @staticmethod
    def _apply_job_limits(
        kernel32: object,
        ctypes_module: object,
        structs: dict[str, type],
        job: object,
    ) -> None:
        """Fija los limites extendidos del Job Object (best-effort, no aborta).

        Args:
            kernel32: DLL kernel32 (o fake compatible).
            ctypes_module: Modulo `ctypes` (inyectado para monkeypatch/test).
            structs: Structs del Job Object (`EXTENDED_LIMIT`).
            job: Handle del Job Object.
        """
        extended = structs["EXTENDED_LIMIT"]()
        extended.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_FLAGS
        extended.BasicLimitInformation.ActiveProcessLimit = JOB_OBJECT_ACTIVE_PROCESS
        extended.JobMemoryLimit = JOB_OBJECT_MEMORY_BYTES
        ok = kernel32.SetInformationJobObject(
            job,
            JOB_OBJECT_EXTENDED_LIMIT_INFORMATION,
            ctypes_module.byref(extended),
            ctypes_module.sizeof(extended),
        )
        if not ok:
            logger.warning(
                "sandbox_executor: SetInformationJobObject fallo (errno=%s)",
                ctypes_module.get_last_error() if os.name == "nt" else "n/a",
            )

    @staticmethod
    def _spawn_job_child(
        cmd: list[str], env: dict[str, str] | None, workdir: Path | None
    ) -> subprocess.Popen:
        """Lanza el hijo sin ventana de consola, env limpio y cwd acotado.

        Args:
            cmd: Comando y argumentos.
            env: Variables extra inyectadas (allowlist + estas).
            workdir: Directorio de trabajo (opcional).

        Returns:
            Proceso hijo (`subprocess.Popen`) pendiente de asignar al job.
        """
        return subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=_build_safe_env(env),
            cwd=str(workdir) if workdir is not None else None,
            creationflags=CREATE_NO_WINDOW,
        )

    @staticmethod
    def _collect_job_result(
        proc: subprocess.Popen, timeout_s: float
    ) -> SandboxResult:
        """Espera al hijo del job y normaliza el resultado (timeout -> 124).

        Args:
            proc: Proceso hijo ya asignado al job.
            timeout_s: Timeout en segundos.

        Returns:
            SandboxResult con backend `windows-jobobject`.
        """
        try:
            stdout, stderr = proc.communicate(timeout=timeout_s)
        except subprocess.TimeoutExpired:
            logger.warning(
                "sandbox_executor: timeout jobobject tras %.0fs", timeout_s
            )
            proc.kill()
            proc.communicate()
            return SandboxResult(
                stdout="",
                stderr=f"timeout tras {timeout_s}s",
                returncode=124,
                backend=BACKEND_JOB_OBJECT,
            )
        return SandboxResult(
            stdout=stdout or "",
            stderr=stderr or "",
            returncode=proc.returncode,
            backend=BACKEND_JOB_OBJECT,
        )

    def _run_bwrap(
        self,
        cmd: list[str],
        timeout_s: float,
        env: dict[str, str] | None,
        workdir: Path | None = None,
    ) -> SandboxResult:
        """Ejecuta con bubblewrap (namespaces) en Linux; fallback si falta workdir.

        Args:
            cmd: Comando y argumentos.
            timeout_s: Timeout en segundos.
            env: Variables inyectadas en runtime.
            workdir: Directorio a montar read-only y usar como cwd; si es
                `None` no hay raiz que aislar y se degrada a `_run_subprocess`.

        Returns:
            SandboxResult con backend `bwrap` (timeout -> returncode 124).
        """
        if workdir is None:
            logger.warning(
                "sandbox_executor: backend bwrap requiere workdir; "
                "degrada a subprocess"
            )
            return self._run_subprocess(cmd, timeout_s, env, workdir)
        parent = str(workdir)
        bwrap_cmd = [
            BACKEND_BWRAP,
            "--unshare-all",
            "--die-with-parent",
            "--new-session",
            "--ro-bind", parent, parent,
            "--proc", "/proc",
            "--dev", "/dev",
            "--tmpfs", "/tmp",
            "--chdir", parent,
            "--",
            *cmd,
        ]
        try:
            proc = subprocess.run(
                bwrap_cmd,
                capture_output=True,
                text=True,
                timeout=timeout_s,
                check=False,
                env=_build_safe_env(env),
            )
            return SandboxResult(
                stdout=proc.stdout or "",
                stderr=proc.stderr or "",
                returncode=proc.returncode,
                backend=BACKEND_BWRAP,
            )
        except subprocess.TimeoutExpired:
            logger.warning("sandbox_executor: timeout bwrap tras %.0fs", timeout_s)
            return SandboxResult(
                stdout="",
                stderr=f"timeout tras {timeout_s}s",
                returncode=124,
                backend=BACKEND_BWRAP,
            )

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
