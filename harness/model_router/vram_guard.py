"""vram_guard.py — Guard de VRAM anti-OOM (2 desbordamientos GPU + ruta Unsloth).

WHAT: `free_vram_mb()` (nvidia-smi, None si no hay GPU) + tabla de
footprints + `fits()` con margen de seguridad.
WHY: Causa de los OOMs: keep_alive 5m en todos los tiers mantenia
Qwen3.8 (5.8GB) + Qwopus (6.6GB) = 12.4GB residentes en 8GB, mas
Unsloth concurrente. Segundo vector: `LocalExecutor` intentaba Unsloth
PRIMERO sin gate — el llama-server cargaba modelos grandes (clase 26B)
con Ollama residente y reventaba (nvlddmkm 153). El guard + keep_alive
"0" en tiers grandes (descarga inmediata) lo impide por diseno.
WHERE: `LocalExecutor` antes de generar (Ollama y Unsloth);
diagnostico en `check_ollama.py` y `check_unsloth.py`.
"""

from __future__ import annotations

import logging
import shutil
import subprocess

logger = logging.getLogger("harness.model_router.vram_guard")

#: VRAM ocupada estimada por modelo (MB, pesos Q4/Q8 + KV tipica).
MODEL_FOOTPRINT_MB: dict[str, int] = {
    "qwen3.8": 5800,
    "qwen38": 5800,  # nombre corto con ctx horneado (mismos pesos 9B Q4)
    "qwopus": 6600,
    "glm": 6200,
    "minicpm5": 2700,
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

#: Margen de seguridad por defecto (15% headroom).
DEFAULT_SAFETY = 0.85


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

    Args:
        model: Nombre/tag.
        default: Valor si no hay match (peor caso 9B Q4).

    Returns:
        MB estimados.
    """
    key = _footprint_key(model)
    return MODEL_FOOTPRINT_MB.get(key, default)


def free_vram_mb() -> int | None:
    """VRAM libre via nvidia-smi (None si no hay GPU/driver).

    Returns:
        MB libres o None (graceful, nunca lanza).
    """
    if shutil.which("nvidia-smi") is None:
        return None
    try:
        proc = subprocess.run(
            ["nvidia-smi", "--query-gpu=memory.free",
             "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=10, check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        logger.debug("vram_guard: nvidia-smi fallo (%s)", exc)
        return None
    if proc.returncode != 0:
        return None
    try:
        values = [int(line.strip().split()[0])
                  for line in proc.stdout.splitlines() if line.strip()]
    except ValueError:
        return None
    return max(values) if values else None


def fits_in_vram(
    need_mb: int, free_mb: int | None, safety: float = DEFAULT_SAFETY
) -> bool:
    """True si cabe con margen (None = sin dato: permitir con advertencia).

    Args:
        need_mb: MB necesarios (> 0).
        free_mb: MB libres (None = desconocido -> True + warning).
        safety: Margen 0..1.

    Returns:
        True si need <= free*safety (o free desconocido).

    Raises:
        ValueError: Si need <= 0, free negativo o safety fuera de (0,1].
    """
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
    if not (0.0 < safety <= 1.0):
        raise ValueError(
            f"WHAT: safety invalido: {safety}. "
            "WHY: debe estar en (0, 1]. "
            "WHERE: fits_in_vram"
        )
    if free_mb is None:
        logger.warning("vram_guard: sin dato de VRAM, se permite (ciego)")
        return True
    return need_mb <= free_mb * safety
