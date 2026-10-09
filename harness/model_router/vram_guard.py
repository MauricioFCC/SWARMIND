"""vram_guard.py — Guard de VRAM anti-OOM multi-vendor (NVIDIA/AMD/Metal).

WHAT: `free_vram_mb()` multi-vendor (`nvidia-smi` -> `rocm-smi` -> None en
macOS/Metal, override por `SWARMIND_VRAM_CMD`) + tabla de footprints +
`fits()` con margen de seguridad.
WHY: Causa de los OOMs: keep_alive 5m en todos los tiers mantenia
Qwen3.8 (5.8GB) + un 9B coding (6.6GB) = 12.4GB residentes en 8GB, mas
Unsloth concurrente. Segundo vector: `LocalExecutor` intentaba Unsloth
PRIMERO sin gate — el llama-server cargaba modelos grandes (clase 26B)
con Ollama residente y reventaba (nvlddmkm 153). El guard + keep_alive
"0" en tiers grandes (descarga inmediata) lo impide por diseno. Ademas, la
lectura de VRAM estaba clavada a NVIDIA (ciega en AMD/macOS); ahora se
descubre el SMI por vendor con `shutil.which`.
WHERE: `LocalExecutor` antes de generar (Ollama y Unsloth);
diagnostico en `check_ollama.py` y `check_unsloth.py`.
"""

from __future__ import annotations

import logging
import os
import shlex
import shutil
import subprocess

from harness.model_router.backend_config import GpuBudget
from harness.model_router.fleet_manifest import model_entry

logger = logging.getLogger("harness.model_router.vram_guard")

#: Presupuesto por defecto (RTX 4060 8GB): fuente del margen de seguridad.
_DEFAULT_BUDGET = GpuBudget()

#: VRAM ocupada estimada por modelo (MB, pesos Q4/Q8 + KV tipica). Claves de
#: las familias de la flota 2026-10-01 (el manifiesto GANA) + familias ajenas
#: que el usuario pudiera servir por Unsloth. Los retirados (minicpm5, qwen3.8)
#: se eliminan para que caigan al default conservador.
MODEL_FOOTPRINT_MB: dict[str, int] = {
    "qwen3.5-4b": 3600,
    "mimo": 6100,
    "jackod": 5800,
    "ornith": 6700,
    "glm": 6200,
    "lfm2.5": 2900,
    "llama3.2": 2000,
    "qwen3:4b": 2600,
    "deepseek-r1": 5200,
    "qwen2.5-coder": 4600,
    "olmoe": 3900,
    "qwen3-vl": 2600,
    "qwen3-embedding": 400,
    "gemma-4": 16000,  # clase 26B Q4 servida por Unsloth: nunca cabe en 8GB
    "gemma4": 16000,
    "26b": 16000,  # cualquier 26B Q4 (~15-16GB con KV)
    "bonsai": 6000,  # 27B ternario 5.54GB en disco + KV (standby, solo fork)
}

#: Margen de seguridad por defecto (15% headroom). Derivado de `GpuBudget`.
DEFAULT_SAFETY = _DEFAULT_BUDGET.vram_safety

#: Timeout de sondeo VRAM (segundos). Un SMI local responde en <1s; 10s corta
#: un driver colgado sin bloquear el arranque del backend.
_VRAM_TIMEOUT_S = 10

#: Bytes por mebibyte (rocm-smi reporta bytes; nvidia-smi ya da MiB).
_BYTES_PER_MIB = 1024 * 1024

#: Variable de entorno que fuerza el comando de lectura de VRAM (override).
ENV_VRAM_CMD = "SWARMIND_VRAM_CMD"

#: Sondeos por vendor en orden de prioridad: (binario, args).
#: macOS/Metal no expone CLI de VRAM -> ningun sondeo matchea -> None (graceful).
_VRAM_PROBES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("nvidia-smi", ("--query-gpu=memory.free", "--format=csv,noheader,nounits")),
    ("rocm-smi", ("--showmeminfo", "vram", "--csv")),
)


def _footprint_key(model: str) -> str:
    """Clave de footprint por substring (case-insensitive).

    Args:
        model: Nombre/tag del modelo.

    Returns:
        Clave o "" si no hay match (se usa default conservador).
    """
    lowered = model.lower()
    for key in MODEL_FOOTPRINT_MB:
        if key in lowered:
            return key
    return ""


def footprint_mb(model: str, default: int = 6600) -> int:
    """VRAM estimada del modelo (conservadora si desconocido).

    Prioridad: manifiesto de flota (SSOT medida, ADR-0101) -> tabla de
    footprints de fallback (modelos ajenos a la flota) -> default.

    Args:
        model: Nombre/tag.
        default: Valor si no hay match (peor caso 9B Q4).

    Returns:
        MB estimados.
    """
    entry = model_entry(model)
    if entry is not None:
        return entry.vram_mb
    key = _footprint_key(model)
    return MODEL_FOOTPRINT_MB.get(key, default)


def _to_int(token: str) -> int | None:
    """Convierte un token a entero (None si no es numerico).

    Args:
        token: Campo de texto (posible numero).

    Returns:
        Entero o None si el token no parsea.
    """
    try:
        return int(token)
    except ValueError:
        return None


def _parse_free_mb(stdout: str) -> int | None:
    """Extrae la VRAM libre (MB) del stdout de un SMI (puro, sin I/O).

    Soporta ambos formatos CSV:
    - NVIDIA (``memory.free``): un entero MiB por linea/GPU.
    - AMD (``--showmeminfo vram --csv``): filas ``device,total_b,used_b``
      (bytes) -> libre = total - usado, convertido a MiB.

    Args:
        stdout: Salida cruda del comando de VRAM.

    Returns:
        MB libres maximos entre GPUs o None si no hay dato parseable.
    """
    candidates: list[int] = []
    for line in stdout.splitlines():
        numbers = [
            value
            for token in line.split(",")
            if (value := _to_int(token.strip())) is not None
        ]
        if not numbers:
            continue
        if len(numbers) == 1:
            candidates.append(numbers[0])
        elif numbers[0] >= numbers[1]:
            candidates.append((numbers[0] - numbers[1]) // _BYTES_PER_MIB)
    return max(candidates) if candidates else None


def _run_cmd(cmd: list[str]) -> str | None:
    """Ejecuta un comando de VRAM y devuelve su stdout (None si falla).

    Args:
        cmd: Argumentos ya separados (sin shell).

    Returns:
        stdout crudo o None si el binario no existe, expira o retorna != 0.
    """
    try:
        proc = subprocess.run(
            cmd, capture_output=True, text=True,
            timeout=_VRAM_TIMEOUT_S, check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        logger.warning(
            "vram_guard: WHAT=%s no ejecuto; WHY=%s; WHERE=_run_cmd",
            cmd[0], exc,
        )
        return None
    if proc.returncode != 0:
        logger.warning(
            "vram_guard: WHAT=%s returncode=%s; WHY=driver/permiso; WHERE=_run_cmd",
            cmd[0], proc.returncode,
        )
        return None
    return proc.stdout


def _override_argv(override: str) -> list[str] | None:
    """Divide el comando de override en argumentos (shlex, sin shell).

    Args:
        override: Valor de ``SWARMIND_VRAM_CMD``.

    Returns:
        Lista de argumentos o None si el quoting es invalido/vacio.
    """
    try:
        argv = shlex.split(override, posix=os.name != "nt")
    except ValueError as exc:
        logger.warning(
            "vram_guard: WHAT=%r invalido; WHY=%s; WHERE=_override_argv",
            override, exc,
        )
        return None
    return argv or None


def free_vram_mb() -> int | None:
    """VRAM libre (MB) multi-vendor (None si no hay GPU/driver/comando).

    Orden: override ``SWARMIND_VRAM_CMD`` -> nvidia-smi (NVIDIA) ->
    rocm-smi (AMD) -> None (macOS/Metal sin CLI). Nunca lanza.

    Returns:
        MB libres maximos o None (graceful).
    """
    override = os.getenv(ENV_VRAM_CMD, "").strip()
    if override:
        argv = _override_argv(override)
        stdout = _run_cmd(argv) if argv else None
        return _parse_free_mb(stdout) if stdout else None
    for binary, args in _VRAM_PROBES:
        if shutil.which(binary) is None:
            continue
        stdout = _run_cmd([binary, *args])
        if stdout:
            parsed = _parse_free_mb(stdout)
            if parsed is not None:
                return parsed
    return None


def fits_in_vram(
    need_mb: int, free_mb: int | None, safety: float | None = None
) -> bool:
    """True si cabe con margen (None = sin dato: permitir con advertencia).

    Args:
        need_mb: MB necesarios (> 0).
        free_mb: MB libres (None = desconocido -> True + warning).
        safety: Margen 0..1; None usa ``GpuBudget.from_env().vram_safety``.

    Returns:
        True si need <= free*safety (o free desconocido).

    Raises:
        ValueError: Si need <= 0, free negativo o safety fuera de (0,1].
    """
    resolved_safety = safety if safety is not None else GpuBudget.from_env().vram_safety
    if need_mb <= 0:
        raise ValueError(
            f"WHAT: need_mb invalido: {need_mb}. "
            "WHY: debe ser positivo. "
            "WHERE: fits_in_vram"
        )
    if free_mb is not None and free_mb < 0:
        raise ValueError(
            f"WHAT: free_mb invalido: {free_mb}. "
            "WHY: no puede ser negativo. "
            "WHERE: fits_in_vram"
        )
    if not (0.0 < resolved_safety <= 1.0):
        raise ValueError(
            f"WHAT: safety invalido: {resolved_safety}. "
            "WHY: debe estar en (0, 1]. "
            "WHERE: fits_in_vram"
        )
    if free_mb is None:
        logger.warning("vram_guard: sin dato de VRAM, se permite (ciego)")
        return True
    return need_mb <= free_mb * resolved_safety
