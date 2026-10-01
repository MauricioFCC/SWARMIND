"""model_windows.py — Presupuesto de ventana anti-volcado (ADR-0092).

WHAT: Tabla de num_ctx MEDIDO por modelo (RTX 4060 8GB) + guard
`fits_in_window()` que valida que sistema+tarea+respuesta quepan ANTES
de ejecutar en local.
WHY: Bug real x2: (1) con ~17K tokens de sistema+skills el modelo entra en
loop de compactacion y vuelca la GPU; (2) medido 2026-09-29 (`ollama ps`
CONTEXT + `ollama show` sin PARAMETER): los blobs canonicos hf.co corren
con el default 4096, NO 8192 — el gate anterior admitia 2x de mas y el
KV desbordaba con otro residente (nvlddmkm 153). Ventana honesta +
respuesta acotada (num_predict) = sin desborde posible.
WHERE: `LocalExecutor` (gate previo + options num_predict) y
`opencode.json` (modelos cortos con ctx horneado).

Uso:
    if fits_in_window(model, task_chars=len(task)): ejecutar_local()
"""

from __future__ import annotations

import logging

from harness.model_router.fleet_manifest import model_entry

logger = logging.getLogger("harness.model_router.model_windows")

#: num_ctx default honesto (default real de Ollama, medido 2026-09-29).
DEFAULT_NUM_CTX = 4096
#: Reserva para respuesta: el techo de lo que LocalExecutor permite generar
#: (CLOSED_TASK_NUM_PREDICT) con margen x2. Nada local puede pedir mas alla.
RESPONSE_RESERVE_TOKENS = 1024
#: Presupuesto de sistema FULL (N1+N2+skills full: lo que inyecta opencode hoy).
SYSTEM_BUDGET_TOKENS = 10_000
#: Presupuesto de sistema LEAN (N1 ~950 tok + 1 min-skill + margen): el perfil
#: que DEBE usar la ruta local (opencode: instructions minimas + tiers REFERENCE).
SYSTEM_BUDGET_LEAN = 2500
#: Ratio chars/token para estimar.
_CHARS_PER_TOKEN = 4

#: Ventana de FALLBACK por familia (RTX 4060 8GB; primera coincidencia gana:
#: especificos antes). Los modelos de flota resuelven por manifiesto (SSOT,
#: ADR-0101), que GANA sobre esta tabla; aqui solo quedan familias ajenas que
#: el usuario pudiera instalar (los retirados se eliminaron 2026-09-30).
_MODEL_WINDOWS: tuple[tuple[str, int], ...] = (
    ("qwen38", 16384),        # alias corto con ctx horneado (medido 2026-09-29)
    ("minicpm", 32768),       # alias minicpm5-2b-32k mide 32768 (canonical: manifiesto 8192)
    ("qwen3-embedding", 4096),
    ("qwen3-vl", 4096),
    ("qwen3.8", 16384),       # manifiesto gana (medido 16K, no 8K)
    ("qwopus", 16384),        # manifiesto gana (medido 16384)
    ("qwen3.5", 16384),       # familia reasoning 9B (medido 16K)
)


def recommend_num_ctx(model: str) -> int:
    """Recomienda num_ctx para un modelo.

    Prioridad: manifiesto de flota (SSOT medida, ADR-0101) -> tabla medida
    de fallback (modelos ajenos a la flota) -> default honesto (4096).

    Args:
        model: Nombre/tag del modelo.

    Returns:
        Ventana a solicitar, o DEFAULT_NUM_CTX si es desconocido.
    """
    entry = model_entry(model)
    if entry is not None:
        return entry.num_ctx
    lowered = model.lower()
    for key, window in _MODEL_WINDOWS:
        if key in lowered:
            return window
    logger.debug("model_windows: modelo desconocido '%s', default %d", model, DEFAULT_NUM_CTX)
    return DEFAULT_NUM_CTX


def fits_in_window(model: str, task_chars: int, system_tokens: int = SYSTEM_BUDGET_LEAN) -> bool:
    """True si sistema+tarea+respuesta acotada caben en la ventana MEDIDA.

    Reserva RESPONSE_RESERVE_TOKENS para la respuesta (techo de lo que la
    ruta local genera: num_predict acotado). Por defecto usa el presupuesto
    LEAN (perfil local: N1 + min-skills); pasar SYSTEM_BUDGET_TOKENS para
    auditar el perfil full actual (demuestra el loop).

    Args:
        model: Nombre/tag del modelo.
        task_chars: Tamano de la tarea en chars.
        system_tokens: Presupuesto de sistema en tokens.

    Returns:
        True si cabe con la reserva de respuesta intacta (anti-desborde KV).
    """
    window = recommend_num_ctx(model)
    need = system_tokens + max(0, task_chars) // _CHARS_PER_TOKEN
    return need <= window - RESPONSE_RESERVE_TOKENS
