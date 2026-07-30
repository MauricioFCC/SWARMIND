"""Reglas de guardrails incorporadas para Swarmind.

Cada regla es una funcion pura con firma: ``(text: str) -> tuple[bool, str]``
donde el primer elemento indica si hubo violacion (True = violado) y el
segundo contiene la razon legible de la deteccion.

Reglas disponibles:
    - anti_prompt_injection: Bloquea "ignore previous instructions" y variantes.
    - anti_pii_leak: Detecta emails, tarjetas de credito, SSN en texto.
    - anti_code_injection: Bloquea codigo malicioso en outputs (eval, exec, etc.).
    - max_length: Limita longitud del texto a N tokens aproximados.
    - toxicity: Detecta lenguaje toxico basado en palabras clave.
    - tool_allowlist: Verifica que solo tools autorizadas sean invocadas.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Callable
from re import Pattern

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constantes compartidas
# ---------------------------------------------------------------------------

# Token estimation ~4 chars por token (aproximacion conservadora)
_CHARS_PER_TOKEN: float = 4.0

# ---------------------------------------------------------------------------
# Firmas de tipo
# ---------------------------------------------------------------------------

GuardrailCheckFn = Callable[[str], tuple[bool, str]]
"""Firma de toda regla de guardrail: (texto) -> (violado: bool, razon: str)."""

# ---------------------------------------------------------------------------
# Compilacion de patrones recurrentes (una sola vez)
# ---------------------------------------------------------------------------

# Patrones de prompt injection
_PROMPT_INJECTION_PATTERNS: list[Pattern[str]] = [
    # Ingles
    re.compile(r"ignore\s+(all\s+)?previous\s+instructions", re.IGNORECASE),
    re.compile(r"disregard\s+(all\s+)?(prior|previous)\s+(instructions|directives)", re.IGNORECASE),
    re.compile(r"forget\s+(all\s+)?(prior|previous)\s+(instructions|context)", re.IGNORECASE),
    re.compile(r"you\s+are\s+(now|not)\s+(bound|required|obligated)\s+to", re.IGNORECASE),
    re.compile(r"override\s+(system\s+)?(prompt|instructions|directives)", re.IGNORECASE),
    re.compile(r"do\s+not\s+follow\s+(the\s+)?(above|previous|given)", re.IGNORECASE),
    re.compile(r"act\s+as\s+if\s+you\s+are\s+(not\s+)?(an?\s+)?(AI|assistant|bot)", re.IGNORECASE),
    re.compile(r"print\s+(your\s+)?(system\s+)?prompt", re.IGNORECASE),
    re.compile(r"reveal\s+(your\s+)?(system\s+)?(prompt|instructions)", re.IGNORECASE),
    # Espanol
    re.compile(r"ignora\s+(todas\s+)?las\s+instrucciones\s+(previas|anteriores)", re.IGNORECASE),
    re.compile(r"olvida\s+(todas\s+)?las\s+(instrucciones|directrices)\s+(previas|anteriores)", re.IGNORECASE),
    re.compile(r"no\s+sigas\s+(las\s+)?(instrucciones|indicaciones)\s+(previas|anteriores)", re.IGNORECASE),
    re.compile(r"eres\s+(ahora|un)\s+(libre|nuevo)\s+(de|sin)\s+(restricciones|limites)", re.IGNORECASE),
    re.compile(r"actua\s+como\s+si\s+(no\s+)?(fueras|fueses)\s+un\s+(AI|asistente|bot)", re.IGNORECASE),
    re.compile(r"muestra\s+(tu\s+)?(prompt|instrucciones)\s+(de\s+)?sistema", re.IGNORECASE),
    re.compile(r"revele\s+(tu\s+)?(prompt|instrucciones)\s+(de\s+)?sistema", re.IGNORECASE),
]

# Patrones de PII
_EMAIL_PATTERN: Pattern[str] = re.compile(
    r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}"
)

_CREDIT_CARD_PATTERN: Pattern[str] = re.compile(
    r"\b(?:\d{4}[-\s]?){3}\d{4}\b"
)

_SSN_PATTERN: Pattern[str] = re.compile(
    r"\b(?!000|666|9\d{2})\d{3}[-\s]?(?!00)\d{2}[-\s]?(?!0000)\d{4}\b"
)

# Patrones de code injection
_CODE_INJECTION_PATTERNS: list[Pattern[str]] = [
    re.compile(r"\beval\s*\(", re.IGNORECASE),
    re.compile(r"\bexec\s*\(", re.IGNORECASE),
    re.compile(r"\b__import__\s*\(", re.IGNORECASE),
    re.compile(r"\bcompile\s*\(.*\b(exec|eval|single)\b", re.IGNORECASE),
    re.compile(r"\bos\.system\s*\(", re.IGNORECASE),
    re.compile(r"\bsubprocess\.(call|Popen|run|check_output)\s*\(", re.IGNORECASE),
    re.compile(r"\bctypes\.(CDLL|windll|cdll)\s*\(", re.IGNORECASE),
    re.compile(r"\bpickle\.(load|loads)\s*\(", re.IGNORECASE),
    re.compile(r"\bshelve\.open\s*\(", re.IGNORECASE),
    re.compile(r"\bmarshal\.(load|loads)\s*\(", re.IGNORECASE),
]

# Palabras clave de toxicidad
_TOXIC_KEYWORDS: set[str] = {
    "kill yourself", "shut up", "you are stupid", "you are useless",
    "go die", "i hate you", "you are an idiot", "fuck you",
    "stupid ai", "worthless", "you are terrible", "useless bot",
    "i will destroy", "die", "shut your mouth", "you are garbage",
}

# TODO: tool_allowlist se maneja con ToolGuardian en el engine.
# La funcion tool_allowlist aqui es un wrapper que verifica contra
# una lista de tools permitidas pasada como estado externo.

# ---------------------------------------------------------------------------
# Reglas de guardrail individuales
# ---------------------------------------------------------------------------


def anti_prompt_injection(text: str) -> tuple[bool, str]:
    """Detecta intentos de prompt injection en el texto.

    Busca patrones conocidos de jailbreak como "ignore previous instructions",
    "override system prompt", etc.

    Args:
        text: Texto a inspeccionar (prompt de entrada).

    Returns:
        tuple[bool, str]: (True si hay injection, razon de la deteccion).
    """
    if not text or not text.strip():
        return False, ""

    for pattern in _PROMPT_INJECTION_PATTERNS:
        match = pattern.search(text)
        if match:
            matched_text: str = match.group()[:80]
            logger.debug(
                "[Guardrails] Prompt injection detectado: '%s' en entrada",
                matched_text,
            )
            return True, f"Prompt injection detectado: '{matched_text}'"

    return False, ""


def anti_pii_leak(text: str) -> tuple[bool, str]:
    """Detecta informacion de identificacion personal (PII) en el texto.

    Busca emails, numeros de tarjeta de credito y SSN/identificacion.

    Args:
        text: Texto a inspeccionar.

    Returns:
        tuple[bool, str]: (True si hay PII, descripcion de lo encontrado).
    """
    if not text or not text.strip():
        return False, ""

    encontrados: list[str] = []

    # Buscar emails
    emails: list[str] = _EMAIL_PATTERN.findall(text)
    if emails:
        encontrados.append(f"{len(emails)} email(s) detectado(s)")

    # Buscar tarjetas de credito (patron Luhn se podria agregar, aqui va pattern match)
    cards: list[str] = _CREDIT_CARD_PATTERN.findall(text)
    if cards:
        encontrados.append(f"{len(cards)} posible(s) tarjeta(s) de credito")

    # Buscar SSN
    ssns: list[str] = _SSN_PATTERN.findall(text)
    if ssns:
        encontrados.append(f"{len(ssns)} posible(es) identificacion(es) personal(es)")

    if encontrados:
        razon: str = "PII detectado: " + "; ".join(encontrados)
        logger.debug("[Guardrails] %s", razon)
        return True, razon

    return False, ""


def anti_code_injection(text: str) -> tuple[bool, str]:
    """Detecta codigo malicioso o peligroso en el texto (outputs, respuestas).

    Busca eval(), exec(), subprocess, os.system, pickle, y otras funciones
    que permiten ejecucion remota de codigo.

    Args:
        text: Texto a inspeccionar.

    Returns:
        tuple[bool, str]: (True si hay code injection, patron encontrado).
    """
    if not text or not text.strip():
        return False, ""

    for pattern in _CODE_INJECTION_PATTERNS:
        match = pattern.search(text)
        if match:
            matched: str = match.group()[:80]
            logger.debug(
                "[Guardrails] Code injection detectado: '%s' en salida",
                matched,
            )
            return True, f"Codigo peligroso detectado: '{matched}'"

    return False, ""


def max_length(text: str, max_tokens: int = 4096) -> tuple[bool, str]:
    """Verifica que el texto no exceda un maximo de tokens aproximados.

    La estimacion usa ~4 caracteres por token (aproximacion conservadora
    util para modelos GPT/LLaMA). No es exacta pero es rapida y O(1).

    Args:
        text: Texto a medir.
        max_tokens: Maximo de tokens permitidos (default: 4096).

    Returns:
        tuple[bool, str]: (True si excede el limite, detalle del exceso).
    """
    if not text:
        return False, ""

    approx_tokens: float = len(text) / _CHARS_PER_TOKEN
    if approx_tokens > max_tokens:
        logger.debug(
            "[Guardrails] Exceso de longitud: ~%d tokens (max %d)",
            int(approx_tokens), max_tokens,
        )
        return True, (
            f"Texto excede limite de ~{max_tokens} tokens "
            f"(estimado: ~{int(approx_tokens)} tokens)"
        )

    return False, ""


def toxicity(text: str) -> tuple[bool, str]:
    """Detecta lenguaje toxico, ofensivo o abusivo en el texto.

    Usa una lista de palabras clave conocidas. No es un clasificador NLU,
    disenado como filtro rapido de primera linea.

    Args:
        text: Texto a inspeccionar.

    Returns:
        tuple[bool, str]: (True si hay toxicidad, keyword encontrada).
    """
    if not text or not text.strip():
        return False, ""

    text_lower: str = text.lower()
    for keyword in _TOXIC_KEYWORDS:
        if keyword in text_lower:
            logger.debug(
                "[Guardrails] Toxicidad detectada: keyword '%s' en texto",
                keyword,
            )
            return True, f"Lenguaje toxico detectado: '{keyword}'"

    return False, ""


def tool_allowlist(
    text: str,
    allowed_tools: set[str] | None = None,
) -> tuple[bool, str]:
    """Verifica que solo tools autorizadas sean invocadas en el texto.

    NOTA: Esta es una funcion parcial que requiere ``allowed_tools``.
    El ``GuardrailEngine`` inyecta la lista de tools permitidas al wrapper.

    Args:
        text: Texto a inspeccionar (debe contener nombres de tools).
        allowed_tools: Conjunto de nombres de tools permitidas. Si es None,
            se usa un set vacio (todo se considera no permitido).

    Returns:
        tuple[bool, str]: (True si hay tools no autorizadas, detalle).
    """
    if not text or not text.strip():
        return False, ""

    if allowed_tools is None:
        allowed_tools = set()

    # Patron simple para detectar invocaciones a tools en formato JSON o texto
    tool_invocations: list[str] = re.findall(
        r'"tool(_name)?"\s*:\s*"([^"]+)"',
        text,
    )
    # Tambien busca formato simple: tool_name(...)
    tool_calls: list[str] = re.findall(
        r'\b([a-z_][a-z0-9_]*)\s*\(',
        text,
    )

    encontradas: set[str] = set()
    for _, name in tool_invocations:
        if name not in allowed_tools:
            encontradas.add(name)

    for name in tool_calls:
        # Filtra llamadas a funciones built-in de Python
        if (
            name not in allowed_tools
            and name not in _PYTHON_BUILTINS
            and len(name) > 2
        ):
            encontradas.add(name)

    if encontradas:
        tools_str: str = ", ".join(sorted(encontradas)[:10])
        logger.debug(
            "[Guardrails] Tools no autorizadas: %s",
            tools_str,
        )
        return True, f"Tool(s) no autorizada(s) detectada(s): {tools_str}"

    return False, ""


# Conjunto de builtins de Python para evitar falsos positivos en tool_allowlist
_PYTHON_BUILTINS: set[str] = {
    "abs", "all", "any", "bool", "bytearray", "bytes", "callable", "chr",
    "classmethod", "compile", "complex", "delattr", "dict", "dir", "divmod",
    "enumerate", "eval", "exec", "filter", "float", "format", "frozenset",
    "getattr", "globals", "hasattr", "hash", "hex", "id", "input", "int",
    "isinstance", "issubclass", "iter", "len", "list", "locals", "map",
    "max", "memoryview", "min", "next", "object", "oct", "open", "ord",
    "pow", "print", "property", "range", "repr", "reversed", "round",
    "set", "setattr", "slice", "sorted", "staticmethod", "str", "sum",
    "super", "tuple", "type", "vars", "zip", "self", "cls", "True",
    "False", "None", "ValueError", "TypeError", "KeyError", "Exception",
    "BaseException", "KeyboardInterrupt", "StopIteration", "NotImplemented",
    "Ellipsis",
}
