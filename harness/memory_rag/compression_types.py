"""Compression types - Dataclasses and constants para compresion de prompts."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# ---------------------------------------------------------------------------
# Constantes
# ---------------------------------------------------------------------------

DEFAULT_TARGET_RATIO = 0.5
ACTIVATION_THRESHOLD_TOKENS = 64
DEFAULT_MAX_CONTEXT_TOKENS = 8000
JSON_WHITESPACE_PATTERN = re.compile(r':\s+')
CHARS_PER_TOKEN = 4
METHOD_AUTO = "auto"
METHOD_EXTRACTIVE = "extractive"
METHOD_ABSTRACTIVE = "abstractive"
METHOD_STRUCTURED = "structured"  # Aproximacion estandar (~4 chars por token)
FILLER_PHRASES = [
    r"I'd like to", r"I want to", r"I need to", r"I think that",
    r"It is important to", r"Please note that", r"As you know",
    r"In order to", r"Due to the fact that", r"At the end of the day",
    r"In my opinion", r"Based on the above", r"As previously mentioned",
    r"It should be noted that", r"In other words",
]
STOP_WORDS = {
    "a", "an", "the", "and", "or", "but", "in", "on", "at", "to",
    "for", "of", "with", "by", "from", "as", "is", "was", "are",
    "were", "be", "been", "being", "have", "has", "had", "do", "does",
    "did", "will", "would", "could", "should", "may", "might", "shall",
    "can", "need", "dare", "ought", "used", "it", "its", "this", "that",
    "these", "those", "i", "me", "my", "we", "our", "you", "your",
    "he", "him", "his", "she", "her", "they", "them", "their",
    "not", "no", "nor", "so", "very", "just", "also", "too", "only",
    "quite", "rather", "some", "any", "each", "every", "all", "both",
    "few", "several", "much", "many", "most", "more",
}


# Patrones de frases de relleno y sus reemplazos (usado por CompressionStrategies)
# Palabras clave preservadas (no se eliminan aunque sean stop words)
PRESERVED_KEYWORDS: list[str] = [
    "TODO", "FIXME", "HACK", "XXX", "NOTE", "OPTIMIZE",
    "deprecated", "warning", "error", "critical",
    "must", "shall", "should", "required", "mandatory",
    "http", "https", "api", "rest", "graphql",
    "class", "def", "function", "method", "interface",
    "import", "from", "return", "yield", "async", "await",
    "SELECT", "FROM", "WHERE", "INSERT", "UPDATE", "DELETE",
    "CREATE", "ALTER", "DROP", "TABLE", "INDEX",
    "docker", "kubernetes", "deploy", "config",
    "1.", "2.", "3.", "4.", "5.", "- [ ]", "- [x]",
]

FILLER_PATTERNS: list[tuple] = [
    (r"I'd like to", "I will"),
    (r"I want to", "I will"),
    (r"I need to", "I must"),
    (r"I think that", ""),
    (r"It is important to", "Must"),
    (r"Please note that", "Note:"),
    (r"As you know", ""),
    (r"In order to", "To"),
    (r"Due to the fact that", "Because"),
    (r"At the end of the day", "Finally"),
    (r"In my opinion", ""),
    (r"Based on the above", "Thus"),
    (r"As previously mentioned", ""),
    (r"It should be noted that", ""),
    (r"In other words", "I.e."),
]


def estimate_tokens(text: str) -> int:
    """Estima tokens usando tiktoken o fallback a chars/4.

    Args:
        text: Texto a estimar.

    Returns:
        Numero estimado de tokens.
    """
    try:
        import tiktoken
        enc = tiktoken.get_encoding("cl100k_base")
        return len(enc.encode(text))
    except ImportError:
        return max(1, len(text) // CHARS_PER_TOKEN)

# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CompressionResult:
    """Resultado de una operacion de compresion.

    Attributes:
        original_tokens: Tokens en el texto original.
        compressed_tokens: Tokens en el texto comprimido.
        ratio: Ratio de compresion (compressed/original).
        text: Texto comprimido.
        method: Metodo usado (extractive, abstractive).
        preserved_sections: Secciones preservadas.
    """
    original_tokens: int
    compressed_tokens: int
    ratio: float
    text: str
    method: str = "auto"
    preserved_sections: list[str] = field(default_factory=list)


@dataclass
class TokenBudget:
    """Presupuesto de tokens por seccion.

    Attributes:
        total: Tokens totales disponibles.
        used: Tokens usados.
        remaining: Tokens restantes.
        sections: Mapa de seccion -> presupuesto.
    """
    total: int
    used: int
    remaining: int
    sections: dict[str, int] = field(default_factory=dict)
