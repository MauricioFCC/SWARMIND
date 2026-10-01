"""gpu_guard.py — capa de seguridad de VRAM anti-TDR (BSOD 0x116, 2026-10-01).

WHAT: techo de contexto (`SAFE_CTX_MAX=8192`), reserva minima de VRAM libre
(`MIN_FREE_VRAM_MB=3000`), `safe_num_ctx()` que nunca pide mas ventana de la
segura y la reduce si la VRAM libre es baja, `should_degrade()` y
`pick_safe_model()` que degradan al modelo mas chico que quepa.
WHY: el 2026-10-01 un 9B Q4 + `num_ctx=16384` + Vulkan sobre 8GB agoto los
recursos de la GPU y provoco VIDEO_TDR_FAILURE (0x116) -> BSOD. El techo de
contexto y la reserva de VRAM impiden por diseno volver a ese escenario.
WHERE: `local_executor.execute` (options.num_ctx + degradacion); complementa
`vram_guard.footprint_mb` (presupuesto) y `model_windows.recommend_num_ctx`
(ventana declarada). Constantes en el modulo (MAG).
"""

from __future__ import annotations

import logging
from collections.abc import Iterable

from harness.model_router.model_windows import recommend_num_ctx
from harness.model_router.vram_guard import fits_in_vram, footprint_mb

logger = logging.getLogger("harness.model_router.gpu_guard")

#: Techo absoluto de contexto (anti-TDR). 16384 NO es seguro en 8GB.
SAFE_CTX_MAX = 8192
#: VRAM que debe quedar libre despues de cargar el modelo (headroom GPU/WDDM).
MIN_FREE_VRAM_MB = 3000
#: Piso de contexto: por debajo el modelo no es funcional (mejor degradar).
MIN_SAFE_CTX = 2048
#: Granularidad de la ventana reducida (multiplos de 1K).
CTX_STEP = 1024


def safe_num_ctx(model: str, free_vram_mb: int | None, requested: int | None = None) -> int:
    """Ventana segura anti-TDR: nunca > 8192 y se reduce si falta VRAM.

    Formula (documentada):
        cap     = min(requested o recommend_num_ctx(model), SAFE_CTX_MAX)
        budget  = free_vram_mb - MIN_FREE_VRAM_MB
        si budget <= 0            -> min(cap, MIN_SAFE_CTX)
        si footprint_mb <= budget -> cap
        si no                     -> max(MIN_SAFE_CTX,
                                         (cap * budget / footprint) // CTX_STEP * CTX_STEP)

    Es decir: se reserva `MIN_FREE_VRAM_MB` y se escala la ventana por la
    fraccion del footprint que el presupuesto permite cubrir (aproximacion
    lineal pesos+KV), redondeando a la baja a multiplos de 1K. Sin dato de
    GPU (None) solo aplica el techo.

    Args:
        model: Nombre/tag del modelo.
        free_vram_mb: MB libres (None = sin dato -> solo techo).
        requested: Ventana pedida; None usa la declarada del manifiesto.

    Returns:
        num_ctx en [MIN_SAFE_CTX, SAFE_CTX_MAX].
    """
    base = requested if requested is not None else recommend_num_ctx(model)
    cap = min(base, SAFE_CTX_MAX)
    if free_vram_mb is None:
        return cap
    budget = free_vram_mb - MIN_FREE_VRAM_MB
    if budget <= 0:
        logger.warning(
            "gpu_guard: VRAM libre baja (%s MB, reserva %s MB); ventana "
            "minima %s para %s (anti-TDR)",
            free_vram_mb, MIN_FREE_VRAM_MB, min(cap, MIN_SAFE_CTX), model,
        )
        return min(cap, MIN_SAFE_CTX)
    footprint = footprint_mb(model)
    if footprint <= budget:
        return cap
    scaled = int(cap * budget / footprint)
    stepped = (scaled // CTX_STEP) * CTX_STEP
    return max(MIN_SAFE_CTX, min(cap, stepped))


def should_degrade(model: str, free_vram_mb: int | None) -> bool:
    """True si el modelo no cabe con el margen de seguridad (anti-OOM/TDR).

    Usa `vram_guard.fits_in_vram` sobre `footprint_mb(model)`. Sin dato de
    GPU (None) no hay degradacion (ciego: `fits_in_vram` permite).

    Args:
        model: Nombre/tag del modelo.
        free_vram_mb: MB libres (None = sin dato).

    Returns:
        True si conviene cambiar a un modelo mas chico.
    """
    return not fits_in_vram(footprint_mb(model), free_vram_mb)


def pick_safe_model(requested: str, candidates: Iterable[str], free_vram_mb: int | None) -> str:
    """Degrada al candidato mas chico que quepa (o deja `requested` si cabe).

    Ordena los candidatos por footprint ascendente y devuelve el primero que
    no requiera degradacion. Si `requested` ya cabe, se devuelve sin cambios.
    Si ninguno cabe, devuelve `requested` (sin degradacion segura): el
    llamador debe derivar a cloud.

    Args:
        requested: Modelo pedido por el router.
        candidates: Modelos alternativos (misma capacidad generativa).
        free_vram_mb: MB libres (None = sin dato -> no degrada).

    Returns:
        El modelo elegido (nunca lanza).
    """
    if not should_degrade(requested, free_vram_mb):
        return requested
    ordered = sorted(set(candidates), key=lambda name: (footprint_mb(name), name))
    for candidate in ordered:
        if not should_degrade(candidate, free_vram_mb):
            logger.warning(
                "gpu_guard: %s no cabe en %s MB libres (anti-TDR); "
                "degrado a %s (%s MB)",
                requested, free_vram_mb, candidate, footprint_mb(candidate),
            )
            return candidate
    logger.warning(
        "gpu_guard: ningun candidato cabe en %s MB libres (anti-TDR); "
        "mantengo %s (derivar a cloud)",
        free_vram_mb, requested,
    )
    return requested
