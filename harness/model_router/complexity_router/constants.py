"""Constantes del enrutador por complejidad semantica.

Extraccion mecanica del modulo original ``harness/model_router/complexity_router.py``
(sin cambios de logica ni firmas). Contiene umbrales, ponderaciones,
vocabulario de senales y nombres de rutas usados por ``ComplexityRouter``.

Referencia: RouteLLM (arXiv 2406.18665) — routing por dificultad para
ahorrar ~2x en costo sin degradar calidad.

Attributes:
    DEFAULT_THRESHOLD: Umbral por defecto de complejidad (score >= umbral -> frontier).
    LONG_HIGH: Longitud alta de tarea en caracteres.
    LONG_MED: Longitud media de tarea en caracteres.
    LONG_LOW: Longitud baja de tarea en caracteres.
    SCORE_*: Ponderaciones de cada senal.
    KEYWORD_REASONING: Palabras clave de razonamiento profundo.
    KEYWORD_COMPLEX_DOMAINS: Palabras clave de dominios complejos.
    SIMPLE_TASK_TERMS: Terminos de tareas simples.
    SIGNAL_*: Nombres de senales activables.
    ROUTE_SMALL / ROUTE_FRONTIER: Rutas posibles.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Constantes (sin magic numbers — todos nombrados)
# ---------------------------------------------------------------------------

# Umbral por defecto de complejidad: score >= umbral -> frontier
DEFAULT_THRESHOLD: float = 50.0

# Umbrales de longitud de tarea (caracteres)
LONG_HIGH: int = 800
LONG_MED: int = 400
LONG_LOW: int = 60

# Ponderaciones de cada señal
SCORE_LENGTH_HIGH: float = 30.0
SCORE_LENGTH_MEDIUM: float = 15.0
SCORE_SHORT_TASK: float = -15.0
SCORE_KEYWORD_REASONING: float = 50.0
SCORE_REASONING_MAX: float = 50.0
SCORE_COMPLEX_DOMAIN: float = 20.0
SCORE_SIMPLE_TERM: float = -20.0
SCORE_MULTI_INSTRUCTION: float = 10.0
SCORE_MIN: float = 0.0
SCORE_MAX: float = 100.0

# Vocabulario de señales
KEYWORD_REASONING: frozenset[str] = frozenset({
    "analiza", "razona", "compara", "sintetiza", "diseña", "arquitectura",
    "debug", "optimiza", "evalúa", "justifica", "deriva", "prueba", "demuestra",
})
KEYWORD_COMPLEX_DOMAINS: frozenset[str] = frozenset({
    "legal", "ciencia", "investigacion", "cuantitativo", "seguridad",
})
SIMPLE_TASK_TERMS: frozenset[str] = frozenset({
    "formatea", "traduce", "resume", "extrae", "clasifica", "lista", "renombra", "parsea",
})

# Nombres de señales y rutas
SIGNAL_SHORT_TASK: str = "short_task"
SIGNAL_LONG_MEDIUM: str = "long_medium"
SIGNAL_LONG_HIGH: str = "long_high"
SIGNAL_KEYWORD_REASONING: str = "keyword_reasoning"
SIGNAL_DOMAIN_COMPLEX: str = "domain_complex"
SIGNAL_SIMPLE_TASK_TERM: str = "simple_task_term"
SIGNAL_MULTI_INSTRUCTION: str = "multi_instruction"
ROUTE_SMALL: str = "small"
ROUTE_FRONTIER: str = "frontier"
