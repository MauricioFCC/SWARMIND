"""model_windows.py — Presupuesto de ventana anti-loop de compactacion (ADR-0092).

WHAT: Tabla de num_ctx recomendado por modelo (RTX 4060 8GB) + guard
`fits_in_window()` que valida que sistema+tarea quepan ANTES de ejecutar
en local.
WHY: Bug real: con num_ctx default (4096) y ~17K tokens de sistema+skills
(N1+N2+full), el modelo entra en loop de compactacion (analiza el
principio, nunca resuelve) y vuelca la GPU. Modelos 9B Q4 (~6GB pesos) +
KV de 16Kctx no caben en 8GB: 8192 es el techo seguro.
WHERE: `LocalExecutor` (gate previo) y `opencode.json` (`options.num_ctx`
por modelo).

Uso:
    if fits_in_window(model, task_chars=len(task)): ejecutar_local()
"""

from __future__ import annotations

import logging

logger = logging.getLogger("harness.model_router.model_windows")

#: num_ctx default seguro (2x el default 4096 de Ollama).
DEFAULT_NUM_CTX = 8192
#: Presupuesto de sistema FULL (N1+N2+skills full: lo que inyecta opencode hoy).
SYSTEM_BUDGET_TOKENS = 10_000
#: Presupuesto de sistema LEAN (N1 ~950 tok + 1 min-skill + margen): el perfil
#: que DEBE usar la ruta local (opencode: instructions minimas + tiers REFERENCE).
SYSTEM_BUDGET_LEAN = 2500
#: Ratio chars/token para estimar.
_CHARS_PER_TOKEN = 4

#: Ventana recomendada por modelo/familia (RTX 4060 8GB, Q4/Q8).
_MODEL_WINDOWS: tuple[tuple[str, int], ...] = (
    ("olmoe", 4096),          # arquitectura 4K (techo duro)
    ("lfm2.5", 8192),
    ("minicpm", 8192),
    ("llama3.2", 8192),
    ("qwen3:4b", 8192),
    ("qwen3-embedding", 8192),
    ("qwen3-vl", 8192),
    ("qwen2.5-coder", 8192),
    ("deepseek-r1", 8192),
    ("qwen3.8", 8192),        # 9B Q4: 16Kctx + 6GB pesos = OOM en 8GB
    ("qwopus", 8192),
    ("qwen3.5", 8192),
    ("glm-z1", 8192),
)


def recommend_num_ctx(model: str) -> int:
    """Recomienda num_ctx para un modelo (match por substring, case-insensitive).

    Args:
        model: Nombre/tag del modelo.

    Returns:
        Ventana recomendada, o DEFAULT_NUM_CTX si es desconocido.
    """
    lowered = model.lower()
    for key, window in _MODEL_WINDOWS:
        if key in lowered:
            return window
    logger.debug("model_windows: modelo desconocido '%s', default %d", model, DEFAULT_NUM_CTX)
    return DEFAULT_NUM_CTX


def fits_in_window(model: str, task_chars: int, system_tokens: int = SYSTEM_BUDGET_LEAN) -> bool:
    """True si sistema(lean)+tarea caben en la ventana (con margen de respuesta).

    Reserva la mitad de la ventana para sistema+tarea y deja la otra mitad
    para respuesta + KV headroom (anti-OOM). Por defecto usa el presupuesto
    LEAN (perfil local: N1 + min-skills); pasar SYSTEM_BUDGET_TOKENS para
    auditar el perfil full actual (demuestra el loop).

    Args:
        model: Nombre/tag del modelo.
        task_chars: Tamano de la tarea en chars.
        system_tokens: Presupuesto de sistema en tokens.

    Returns:
        True si cabe con margen (mitad de ventana libre para responder).
    """
    window = recommend_num_ctx(model)
    need = system_tokens + max(0, task_chars) // _CHARS_PER_TOKEN
    return need <= window // 2
