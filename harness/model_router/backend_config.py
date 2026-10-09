"""backend_config.py — SSOT de configuracion del backend local y presupuesto GPU.

WHAT: un solo lugar (frozen dataclasses) para (1) ``GpuBudget`` — techo de
contexto, reserva de VRAM y margen anti-TDR (antes constantes sueltas en
``gpu_guard``/``vram_guard``/``model_windows``) y (2) ``BackendConfig`` — URL
OpenAI-compatible, launcher, timeouts y politica de retry del backend local
(antes duplicados en ``ollama_client``, ``llama_swap_manager`` y
``llama_boot``). Ambos se resuelven de variables de entorno (12-Factor) para
cambiar de GPU/sistema sin tocar codigo.
WHY: el anti-TDR estaba clavado a 8GB en 4 modulos y la URL/puerto 11434
triplicada; migrar de GPU o de host exigia editar codigo. Centralizar elimina
la deriva (SSOT) y hace testeable el presupuesto con otros valores.
WHERE: ``gpu_guard``, ``vram_guard``, ``model_windows``, ``fleet_manifest``,
``llama_swap_manager``, ``local_executor`` y ``scripts/llama_boot``.
"""

from __future__ import annotations

import logging
import os
import shutil
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger("harness.model_router.backend_config")

# --- Defaults de ESTA maquina (RTX 4060 8GB). Override por entorno (UPG). ---
DEFAULT_SAFE_CTX_MAX = 8192
DEFAULT_MIN_FREE_VRAM_MB = 3000
DEFAULT_MIN_SAFE_CTX = 2048
DEFAULT_CTX_STEP = 1024
DEFAULT_VRAM_SAFETY = 0.85
DEFAULT_GPU_BUDGET_MB = 7000
DEFAULT_BASE_URL = "http://127.0.0.1:11434"
#: Binario de llama-swap. Default None: se DESCUBRE en runtime por entorno,
#: ``shutil.which`` o candidatos por plataforma (NUNCA rutas de usuario fijas).
DEFAULT_EXECUTABLE: Path | None = None
#: Config de modelos de llama-swap. Default None: se descubre en runtime.
DEFAULT_CONFIG_FILE: Path | None = None
#: Launcher de arranque (fallback si no hay binario). Default None: solo env.
DEFAULT_LAUNCHER: Path | None = None
DEFAULT_START_TIMEOUT_S = 90.0
DEFAULT_POLL_INTERVAL_S = 0.5
DEFAULT_RETRY_ATTEMPTS = 3
DEFAULT_RETRY_BACKOFF_S = 0.5

# --- Nombres de variables de entorno (nuevo + alias legacy soportado). ---
ENV_GPU_BUDGET_MB = "SWARMIND_GPU_BUDGET_MB"
ENV_SAFE_CTX_MAX = "SWARMIND_SAFE_CTX_MAX"
ENV_MIN_FREE_VRAM_MB = "SWARMIND_MIN_FREE_VRAM_MB"
ENV_MIN_SAFE_CTX = "SWARMIND_MIN_SAFE_CTX"
ENV_CTX_STEP = "SWARMIND_CTX_STEP"
ENV_VRAM_SAFETY = "SWARMIND_VRAM_SAFETY"
ENV_BASE_URL = "SWARMIND_LOCAL_BASE_URL"
ENV_BASE_URL_LEGACY = "SWARMIND_LLAMA_BASE_URL"
ENV_EXECUTABLE = "SWARMIND_LLAMA_EXECUTABLE"
ENV_CONFIG_FILE = "SWARMIND_LLAMA_CONFIG"
ENV_LAUNCHER = "SWARMIND_LLAMA_LAUNCHER"
ENV_START_TIMEOUT_S = "SWARMIND_LLAMA_START_TIMEOUT_S"
ENV_POLL_INTERVAL_S = "SWARMIND_LLAMA_POLL_INTERVAL_S"
ENV_RETRY_ATTEMPTS = "SWARMIND_LOCAL_RETRY_ATTEMPTS"
ENV_RETRY_BACKOFF_S = "SWARMIND_LOCAL_RETRY_BACKOFF_S"


def _env_int(name: str, default: int) -> int:
    """Lee un entero de entorno (default si ausente o invalido).

    Args:
        name: Nombre de la variable.
        default: Valor si no existe o no parsea.

    Returns:
        Entero leido o default.
    """
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return int(raw)
    except ValueError:
        logger.warning("backend_config: %s=%r no es entero; uso %s", name, raw, default)
        return default


def _env_float(name: str, default: float) -> float:
    """Lee un float de entorno (default si ausente o invalido).

    Args:
        name: Nombre de la variable.
        default: Valor si no existe o no parsea.

    Returns:
        Float leido o default.
    """
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return float(raw)
    except ValueError:
        logger.warning("backend_config: %s=%r no es float; uso %s", name, raw, default)
        return default


def _env_path(name: str) -> Path | None:
    """Lee una ruta opcional de entorno (None si ausente o vacia).

    Args:
        name: Nombre de la variable de entorno.

    Returns:
        ``Path`` del valor o ``None`` si no esta definido o es blanco.
    """
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return None
    return Path(raw)


def _is_windows() -> bool:
    """True si el sistema operativo es Windows (elige candidatos por plataforma).

    Returns:
        True en Windows; False en macOS/Linux.
    """
    return os.name == "nt"


def _windows_executable_candidates() -> tuple[Path, ...]:
    """Rutas tipicas del binario llama-swap en Windows (sin usuario fijo).

    Returns:
        Candidatos en orden de preferencia.
    """
    return (
        Path.home() / "llama" / "swap" / "llama-swap.exe",
        Path("C:/llama-swap/llama-swap.exe"),
    )


def _posix_executable_candidates() -> tuple[Path, ...]:
    """Rutas tipicas del binario llama-swap en macOS/Linux.

    Returns:
        Candidatos en orden de preferencia.
    """
    return (
        Path.home() / "llama" / "swap" / "llama-swap",
        Path("/usr/local/bin/llama-swap"),
        Path("/opt/homebrew/bin/llama-swap"),
    )


def _config_candidates() -> tuple[Path, ...]:
    """Rutas tipicas del YAML de modelos de llama-swap (multiplataforma).

    Returns:
        Candidatos en orden de preferencia.
    """
    return (
        Path.home() / "llama" / "llama-swap.yaml",
        Path.home() / ".config" / "llama-swap" / "config.yaml",
        Path("/etc/llama-swap/config.yaml"),
    )


def _first_existing(candidates: tuple[Path, ...]) -> Path | None:
    """Primer candidato que existe en disco.

    Args:
        candidates: Rutas candidatas en orden de preferencia.

    Returns:
        La primera ``Path`` existente o ``None`` si ninguna existe.
    """
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def discover_executable() -> Path | None:
    """Descubre el binario de llama-swap (env -> which -> candidatos del SO).

    Orden: ``SWARMIND_LLAMA_EXECUTABLE`` (si apunta a un archivo existente) ->
    ``shutil.which("llama-swap")`` -> candidatos por plataforma (Windows:
    ``~/llama/swap/llama-swap.exe`` y ``C:\\llama-swap\\llama-swap.exe``; POSIX:
    ``~/llama/swap/llama-swap``, ``/usr/local/bin`` y ``/opt/homebrew``).

    Returns:
        Ruta al ejecutable o ``None`` si no se encontro en ningun lugar.
    """
    env_path = _env_path(ENV_EXECUTABLE)
    if env_path is not None and env_path.exists():
        return env_path
    which_path = shutil.which("llama-swap")
    if which_path:
        return Path(which_path)
    candidates = (
        _windows_executable_candidates() if _is_windows() else _posix_executable_candidates()
    )
    return _first_existing(candidates)


def discover_config_file() -> Path | None:
    """Descubre el YAML de modelos (env -> rutas tipicas multiplataforma).

    Orden: ``SWARMIND_LLAMA_CONFIG`` (si apunta a un archivo existente) ->
    ``~/llama/llama-swap.yaml`` -> ``~/.config/llama-swap/config.yaml`` ->
    ``/etc/llama-swap/config.yaml``.

    Returns:
        Ruta al config o ``None`` si no se encontro.
    """
    env_path = _env_path(ENV_CONFIG_FILE)
    if env_path is not None and env_path.exists():
        return env_path
    return _first_existing(_config_candidates())


@dataclass(frozen=True)
class GpuBudget:
    """Presupuesto GPU y techo de contexto anti-TDR (configurable por entorno).

    Attributes:
        budget_mb: VRAM total utilizable para un modelo (pesos + KV).
        safe_ctx_max: Techo de contexto (anti-TDR en 8GB; subir en GPU mayor).
        min_free_vram_mb: VRAM que debe quedar libre tras cargar (headroom WDDM).
        min_safe_ctx: Piso de contexto funcional.
        ctx_step: Granularidad de la ventana reducida.
        vram_safety: Margen 0..1 sobre VRAM libre (anti-OOM).
    """

    budget_mb: int = DEFAULT_GPU_BUDGET_MB
    safe_ctx_max: int = DEFAULT_SAFE_CTX_MAX
    min_free_vram_mb: int = DEFAULT_MIN_FREE_VRAM_MB
    min_safe_ctx: int = DEFAULT_MIN_SAFE_CTX
    ctx_step: int = DEFAULT_CTX_STEP
    vram_safety: float = DEFAULT_VRAM_SAFETY

    def __post_init__(self) -> None:
        """Valida invariantes del presupuesto (WHAT+WHY+WHERE si viola)."""
        if self.safe_ctx_max <= 0 or self.min_safe_ctx <= 0:
            raise ValueError(
                f"WHAT: contextos no positivos (max={self.safe_ctx_max}, min={self.min_safe_ctx}). "
                "WHY: una ventana <= 0 no es funcional. "
                "WHERE: GpuBudget.__post_init__"
            )
        if self.min_safe_ctx > self.safe_ctx_max:
            raise ValueError(
                f"WHAT: min_safe_ctx({self.min_safe_ctx}) > safe_ctx_max({self.safe_ctx_max}). "
                "WHY: el piso no puede superar el techo. "
                "WHERE: GpuBudget.__post_init__"
            )
        if self.ctx_step <= 0:
            raise ValueError(
                f"WHAT: ctx_step invalido ({self.ctx_step}). "
                "WHY: la granularidad debe ser positiva. "
                "WHERE: GpuBudget.__post_init__"
            )
        if not (0.0 < self.vram_safety <= 1.0):
            raise ValueError(
                f"WHAT: vram_safety invalido ({self.vram_safety}). "
                "WHY: debe estar en (0, 1]. "
                "WHERE: GpuBudget.__post_init__"
            )
        if self.budget_mb <= 0 or self.min_free_vram_mb < 0:
            raise ValueError(
                f"WHAT: budget_mb({self.budget_mb})/min_free_vram_mb({self.min_free_vram_mb}) invalidos. "
                "WHY: el presupuesto debe ser positivo y la reserva no negativa. "
                "WHERE: GpuBudget.__post_init__"
            )

    @classmethod
    def from_env(cls) -> GpuBudget:
        """Construye el presupuesto desde el entorno (defaults de 8GB).

        Returns:
            GpuBudget con los overrides presentes.

        Raises:
            ValueError: Si una combinacion de env viola las invariantes.
        """
        return cls(
            budget_mb=_env_int(ENV_GPU_BUDGET_MB, DEFAULT_GPU_BUDGET_MB),
            safe_ctx_max=_env_int(ENV_SAFE_CTX_MAX, DEFAULT_SAFE_CTX_MAX),
            min_free_vram_mb=_env_int(ENV_MIN_FREE_VRAM_MB, DEFAULT_MIN_FREE_VRAM_MB),
            min_safe_ctx=_env_int(ENV_MIN_SAFE_CTX, DEFAULT_MIN_SAFE_CTX),
            ctx_step=_env_int(ENV_CTX_STEP, DEFAULT_CTX_STEP),
            vram_safety=_env_float(ENV_VRAM_SAFETY, DEFAULT_VRAM_SAFETY),
        )


@dataclass(frozen=True)
class BackendConfig:
    """Configuracion del backend local OpenAI-compatible (override por entorno).

    Attributes:
        base_url: Base del proxy (llama-swap/Ollama), protocolo OpenAI.
        executable: Binario de llama-swap (None si no se descubrio).
        config_file: YAML de modelos de llama-swap (None si no se descubrio).
        launcher: Script de arranque de fallback (None si no hay).
        start_timeout_s: Margen para que el backend quede listo al arrancar.
        poll_interval_s: Intervalo de sondeo del health durante el arranque.
        retry_attempts: Intentos de request/warm con backoff.
        retry_backoff_s: Base del backoff exponencial (segundos).
    """

    base_url: str = DEFAULT_BASE_URL
    executable: Path | None = DEFAULT_EXECUTABLE
    config_file: Path | None = DEFAULT_CONFIG_FILE
    launcher: Path | None = DEFAULT_LAUNCHER
    start_timeout_s: float = DEFAULT_START_TIMEOUT_S
    poll_interval_s: float = DEFAULT_POLL_INTERVAL_S
    retry_attempts: int = DEFAULT_RETRY_ATTEMPTS
    retry_backoff_s: float = DEFAULT_RETRY_BACKOFF_S

    @property
    def listen_address(self) -> str:
        """Direccion ``host:puerto`` para ``llama-swap -listen`` (derivada).

        Returns:
            host:puerto de ``base_url`` (ej. ``127.0.0.1:11434``).
        """
        from urllib.parse import urlsplit

        parts = urlsplit(self.base_url)
        host = parts.hostname or "127.0.0.1"
        port = parts.port or 11434
        return f"{host}:{port}"

    def __post_init__(self) -> None:
        """Valida la config del backend (WHAT+WHY+WHERE si viola)."""
        if not self.base_url.strip():
            raise ValueError(
                "WHAT: base_url vacia. WHY: sin endpoint no hay backend. "
                "WHERE: BackendConfig.__post_init__"
            )
        if self.start_timeout_s <= 0 or self.poll_interval_s <= 0:
            raise ValueError(
                f"WHAT: timeouts no positivos (start={self.start_timeout_s}, poll={self.poll_interval_s}). "
                "WHY: no se puede esperar sin un margen positivo. "
                "WHERE: BackendConfig.__post_init__"
            )
        if self.retry_attempts < 1:
            raise ValueError(
                f"WHAT: retry_attempts invalid ({self.retry_attempts}). "
                "WHY: debe haber al menos un intento. "
                "WHERE: BackendConfig.__post_init__"
            )
        if self.retry_backoff_s < 0:
            raise ValueError(
                f"WHAT: retry_backoff_s negativo ({self.retry_backoff_s}). "
                "WHY: el backoff no puede ser negativo. "
                "WHERE: BackendConfig.__post_init__"
            )

    @classmethod
    def from_env(cls) -> BackendConfig:
        """Construye la config desde el entorno (alias legacy soportado).

        Lee ``SWARMIND_LOCAL_BASE_URL`` con fallback al legacy
        ``SWARMIND_LLAMA_BASE_URL``.

        Returns:
            BackendConfig con los overrides presentes.

        Raises:
            ValueError: Si una combinacion de env viola las invariantes.
        """
        legacy_url = os.getenv(ENV_BASE_URL_LEGACY)
        base_url = os.getenv(ENV_BASE_URL) or legacy_url or DEFAULT_BASE_URL
        return cls(
            base_url=base_url.rstrip("/"),
            executable=discover_executable(),
            config_file=discover_config_file(),
            launcher=_env_path(ENV_LAUNCHER),
            start_timeout_s=_env_float(ENV_START_TIMEOUT_S, DEFAULT_START_TIMEOUT_S),
            poll_interval_s=_env_float(ENV_POLL_INTERVAL_S, DEFAULT_POLL_INTERVAL_S),
            retry_attempts=_env_int(ENV_RETRY_ATTEMPTS, DEFAULT_RETRY_ATTEMPTS),
            retry_backoff_s=_env_float(ENV_RETRY_BACKOFF_S, DEFAULT_RETRY_BACKOFF_S),
        )
