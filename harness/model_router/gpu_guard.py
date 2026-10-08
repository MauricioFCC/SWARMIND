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
(ventana declarada). Las constantes del modulo se DERIVAN de un `GpuBudget()`
por defecto y las funciones aceptan un `budget` inyectable (SSOT, anti-TDR
configurable): `SWARMIND_*` en entorno o un `GpuBudget` explicito.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable

from harness.model_router.backend_config import GpuBudget
from harness.model_router.model_windows import recommend_num_ctx
from harness.model_router.vram_guard import fits_in_vram, footprint_mb

logger = logging.getLogger("harness.model_router.gpu_guard")

#: Presupuesto por defecto (RTX 4060 8GB). Los overrides por entorno se
#: resuelven en cada llamada via ``GpuBudget.from_env()`` (12-Factor).
_DEFAULT_BUDGET = GpuBudget()

#: Techo absoluto de contexto (anti-TDR). 16384 NO es seguro en 8GB.
SAFE_CTX_MAX = _DEFAULT_BUDGET.safe_ctx_max
#: VRAM que debe quedar libre despues de cargar el modelo (headroom GPU/WDDM).
MIN_FREE_VRAM_MB = _DEFAULT_BUDGET.min_free_vram_mb
#: Piso de contexto: por debajo el modelo no es funcional (mejor degradar).
MIN_SAFE_CTX = _DEFAULT_BUDGET.min_safe_ctx
#: Granularidad de la ventana reducida (multiplos de 1K).
CTX_STEP = _DEFAULT_BUDGET.ctx_step


def _resolve_budget(budget: GpuBudget | None) -> GpuBudget:
    """Resuelve el presupuesto GPU (entorno si no se inyecta uno explicito).

    Args:
        budget: Presupuesto explicito o None para leer el entorno.

    Returns:
        El presupuesto a usar (nunca None). Puede lanzar ValueError si el
        entorno define combinaciones que violan las invariantes de GpuBudget.
    """
    return budget if budget is not None else GpuBudget.from_env()


def safe_num_ctx(
    model: str,
    free_vram_mb: int | None,
    requested: int | None = None,
    budget: GpuBudget | None = None,
) -> int:
    """Ventana segura anti-TDR: nunca > techo y se reduce si falta VRAM.

    Formula (documentada, campos de `GpuBudget`):
        cap        = min(requested o recommend_num_ctx(model), safe_ctx_max)
        headroom   = free_vram_mb - min_free_vram_mb
        si headroom <= 0            -> min(cap, min_safe_ctx)
        si footprint_mb <= headroom -> cap
        si no                       -> max(min_safe_ctx,
                                           (cap * headroom / footprint)
                                           // ctx_step * ctx_step)

    Es decir: se reserva `min_free_vram_mb` y se escala la ventana por la
    fraccion del footprint que el presupuesto permite cubrir (aproximacion
    lineal pesos+KV), redondeando a la baja a multiplos de `ctx_step`. Sin
    dato de GPU (None) solo aplica el techo.

    Args:
        model: Nombre/tag del modelo.
        free_vram_mb: MB libres (None = sin dato -> solo techo).
        requested: Ventana pedida; None usa la declarada del manifiesto.
        budget: Presupuesto GPU; None usa ``GpuBudget.from_env()``.

    Returns:
        num_ctx en [min_safe_ctx, safe_ctx_max].
    """
    resolved = _resolve_budget(budget)
    base = requested if requested is not None else recommend_num_ctx(model)
    cap = min(base, resolved.safe_ctx_max)
    if free_vram_mb is None:
        return cap
    headroom = free_vram_mb - resolved.min_free_vram_mb
    if headroom <= 0:
        floor = min(cap, resolved.min_safe_ctx)
        logger.warning(
            "gpu_guard: VRAM libre baja (%s MB, reserva %s MB); ventana "
            "minima %s para %s (anti-TDR)",
            free_vram_mb, resolved.min_free_vram_mb, floor, model,
        )
        return floor
    footprint = footprint_mb(model)
    if footprint <= headroom:
        return cap
    scaled = int(cap * headroom / footprint)
    stepped = (scaled // resolved.ctx_step) * resolved.ctx_step
    return max(resolved.min_safe_ctx, min(cap, stepped))


def should_degrade(
    model: str, free_vram_mb: int | None, budget: GpuBudget | None = None
) -> bool:
    """True si el modelo no cabe con el margen de seguridad (anti-OOM/TDR).

    Usa `vram_guard.fits_in_vram` sobre `footprint_mb(model)` con el margen
    `budget.vram_safety`. Sin dato de GPU (None) no hay degradacion (ciego:
    `fits_in_vram` permite).

    Args:
        model: Nombre/tag del modelo.
        free_vram_mb: MB libres (None = sin dato).
        budget: Presupuesto GPU; None usa ``GpuBudget.from_env()``.

    Returns:
        True si conviene cambiar a un modelo mas chico.
    """
    resolved = _resolve_budget(budget)
    return not fits_in_vram(
        footprint_mb(model), free_vram_mb, safety=resolved.vram_safety
    )


def pick_safe_model(
    requested: str,
    candidates: Iterable[str],
    free_vram_mb: int | None,
    budget: GpuBudget | None = None,
) -> str:
    """Degrada al candidato mas chico que quepa (o deja `requested` si cabe).

    Ordena los candidatos por footprint ascendente y devuelve el primero que
    no requiera degradacion. Si `requested` ya cabe, se devuelve sin cambios.
    Si ninguno cabe, devuelve `requested` (sin degradacion segura): el
    llamador debe derivar a cloud.

    Args:
        requested: Modelo pedido por el router.
        candidates: Modelos alternativos (misma capacidad generativa).
        free_vram_mb: MB libres (None = sin dato -> no degrada).
        budget: Presupuesto GPU; None usa ``GpuBudget.from_env()``.

    Returns:
        El modelo elegido (nunca lanza).
    """
    resolved = _resolve_budget(budget)
    if not should_degrade(requested, free_vram_mb, resolved):
        return requested
    ordered = sorted(set(candidates), key=lambda name: (footprint_mb(name), name))
    for candidate in ordered:
        if not should_degrade(candidate, free_vram_mb, resolved):
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
