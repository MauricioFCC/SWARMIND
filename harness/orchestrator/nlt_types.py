"""
nlt_types — Tipos y constantes para Natural Language Tool Calling.

Extraido de natural_language_tools.py para mantener modulos < 900 lines.

Incluye:
    - Constantes (STOPWORDS, CHAIN_CONNECTORS, PARAM_PATTERNS)
    - NLTool dataclass
    - NLTResult dataclass
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

# ---------------------------------------------------------------------------
# Constantes
# ---------------------------------------------------------------------------

# Umbral por defecto para considerar un match como valido
DEFAULT_CONFIDENCE_THRESHOLD = 0.35

# Palabras vacias (stopwords) ignoradas durante el scoring
_STOPWORDS: Set[str] = {
    "el", "la", "los", "las", "un", "una", "unos", "unas", "de", "del",
    "en", "por", "para", "con", "sin", "y", "e", "o", "u", "a", "ante",
    "bajo", "cabe", "contra", "desde", "durante", "entre", "hacia",
    "hasta", "mediante", "para", "según", "so", "sobre", "tras",
    "que", "es", "se", "su", "lo", "le", "ya", "este", "esta",
    "como", "más", "pero", "sus", "ha", "han", "puede", "todo",
    "también", "fue", "era", "son", "ser", "haber", "tener",
    "the", "a", "an", "and", "or", "in", "on", "at", "to", "for",
    "of", "with", "by", "from", "is", "it", "as", "be", "are",
    "was", "were", "been", "being", "have", "has", "had", "do",
    "does", "did", "will", "would", "could", "should", "may",
    "might", "shall", "can", "need", "dare", "ought", "used",
}

# Conectores para detectar encadenamiento de herramientas
_CHAIN_CONNECTORS: List[str] = [
    " y ", " e ", " luego ", " después ", " además ", " también ",
    " and ", " then ", " plus ", " also ",
]

# Patrones de extraccion de parametros comunes
_PARAM_PATTERNS: Dict[str, List[str]] = {
    "query": [
        r"(?:sobre|acerca\s+de|acerca\s+del|de[l]?\s+)(.+?)(?:$|\.|\,|\sy\s)",
        r"(?:buscar|encuentra|localiza)\s+(.+?)(?:$|\.|\,|\smax|\sen\s)",
        r"'(.*?)'",
        r"\"(.*?)\"",
    ],
    "documento": [
        r"(?:documento|doc|archivo|expediente|caso)\s+(?:N[o°]?\.?\s*)?([\w\-\.]+)",
        r"'([\w\-\.]+)'",
        r"\"([\w\-\.]+)\"",
    ],
    "doc1": [
        r"(?:entre|comparar)\s+(.+?)\s+(?:y|vs|versus|contra)",
        r"primer[oá]?\s+(?:documento|archivo|versi[oó]?n)?\s*(.+?)(?:$|\.|\,)",
        r"^(.+?)\s+(?:y|vs|versus|contra)\s+",
    ],
    "doc2": [
        r"(?:y|vs|versus|contra)\s+(.+?)(?:$|\.|\,)",
        r"segund[oá]?\s+(?:documento|archivo|versi[oó]?n)?\s*(.+?)(?:$|\.|\,)",
    ],
    "tipo": [
        r"(?:tipo\s+de\s+)?an[áa]lisis\s+(?:de\s+)?(.+?)(?:$|\.|\,)",
        r"modo\s+(.+?)(?:$|\.|\,)",
    ],
    "longitud": [
        r"(breve|normal|detallado|extenso|corto|largo|resumido|ejecutivo)",
        r"(?:resumen|longitud)\s+(.+?)(?:$|\.|\,)",
    ],
    "max": [
        r"(?:m[aá]ximo|top|l[ií]mite)\s*(?::\s*)?(\d+)",
        r"(\d+)\s*(?:resultados|docs|documentos|items)",
    ],
}


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------


@dataclass
class NLTool:
    """Definicion de una herramienta invocable por lenguaje natural.

    Cada NLTool encapsula el nombre, descripcion semantica, parametros
    esperados, ejemplos de uso y un handler opcional para ejecucion.

    Attributes:
        name: Nombre unico de la herramienta (ej: 'buscar').
        description: Descripcion en lenguaje natural de su funcionalidad.
        parameters: Diccionario {nombre_parametro: descripcion_textual}.
        examples: Lista de frases de ejemplo en lenguaje natural.
        handler: Callable opcional que ejecuta la herramienta.
    """

    name: str
    description: str
    parameters: Dict[str, str] = field(default_factory=dict)
    examples: List[str] = field(default_factory=list)
    handler: Optional[Callable[..., Any]] = None


@dataclass
class NLTResult:
    """Resultado del parseo de lenguaje natural a tool call estructurada.

    Attributes:
        tool: Nombre de la herramienta seleccionada.
        natural_input: Texto original ingresado por el usuario.
        structured_output: Diccionario con la accion y parametros extraidos.
        confidence: Nivel de confianza del matching (0.0 a 1.0).
        alternatives: Lista de (tool_name, confidence) con alternativas.
        chain: Lista de NLTResult para encadenamiento de herramientas.
    """

    tool: str
    natural_input: str
    structured_output: Dict[str, Any]
    confidence: float = 1.0
    alternatives: List[Tuple[str, float]] = field(default_factory=list)
    chain: List[NLTResult] = field(default_factory=list)
