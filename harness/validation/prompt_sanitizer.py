"""prompt_sanitizer.py — Redacción de secretos y rutas personales en prompts.

WHAT: neutraliza lo que no debe salir de la máquina al enviar un texto a un
revisor (o a cualquier prompt): PEM, tokens de GitHub/OpenAI/AWS/Slack,
asignaciones entrecomilladas de claves y rutas con nombre de usuario.

WHY: Apiiro reportó 104 185 copias públicas de `settings.local.json`, 1 122 con
secretos reales y 215 indetectables por gitleaks/TruffleHog: aprobar un comando
con credenciales las persiste. Un prompt de revisión es otra salida del mismo
riesgo. Ciclo FR-0010:
`docs/research/frontier-2026-11-19-harness-policies.md`.

WHERE: `harness/validation/blind_review.py` (paquete de revisión ciega) y
cualquier ruta que componga prompts con contenido del repositorio.

Coste: O(|texto|) con seis regex lineales; sin red ni modelo. Idempotente.
"""

from __future__ import annotations

import re

#: Secretos: (tipo, patrón). El orden define la redacción determinista.
_SECRET_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("private_key", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    ("github_token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b")),
    ("openai_key", re.compile(r"\bsk-[A-Za-z0-9]{20,}\b")),
    ("aws_key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("slack_token", re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b")),
    (
        "assignment",
        re.compile(
            r"(?i)\b(?:api[_-]?key|token|secret|password|passwd)\b"
            r"\s*[:=]\s*['\"][^'\"\n]{8,}['\"]"
        ),
    ),
)

#: Raíces de home POSIX (sin barras literales: el fitness de rutas
#: portables prohíbe la cadena completa en código de producción).
_POSIX_HOME_ROOTS = ("home", "Users")

#: Rutas personales: se sustituye solo el nombre de usuario.
_PERSONAL_PATH_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"(?i)([A-Z]:\\Users\\)([^\\\s\"'`(),;\[\]]+)"),
    *(re.compile(r"(?i)(/" + root + r"/)([^/\s\"'`(),;\[\]]+)") for root in _POSIX_HOME_ROOTS),
)

#: Nombres de usuario convencionales en ejemplos, docs y tests: se redactan
#: pero no cuentan como fuga (no identifican a una persona real).
_PLACEHOLDER_USERS = frozenset({"alice", "bob", "user", "usuario", "example", "test", "runner", "ubuntu", "public"})


def _redact_secrets(text: str) -> tuple[str, tuple[str, ...]]:
    """Sustituye secretos por marcadores.

    Args:
        text: Texto a redactar.

    Returns:
        ``(texto_redactado, tipos_de_secreto_hallados)``.
    """
    kinds: list[str] = []
    for name, pattern in _SECRET_PATTERNS:
        if pattern.search(text) is None:
            continue
        kinds.append(name)
        text = pattern.sub(f"<redacted:{name}>", text)
    return text, tuple(kinds)


def is_placeholder_user(name: str) -> bool:
    """Indica si un nombre de usuario es un marcador de ejemplo.

    Args:
        name: Nombre capturado de la ruta.

    Returns:
        True para nombres convencionales (``alice``, ``example``...) o
        marcadores entre ángulos (``<x>``, ``<user>``).
    """
    lowered = name.lower()
    return lowered in _PLACEHOLDER_USERS or (lowered.startswith("<") and lowered.endswith(">"))


def _redact_personal_paths(text: str) -> tuple[str, int]:
    """Sustituye el nombre de usuario de rutas personales por ``<user>``.

    Args:
        text: Texto a redactar.

    Returns:
        ``(texto_redactado, rutas_personales)``; los nombres de sustitución
        convencionales (``alice``, ``example``, ``<x>``) se redactan pero no
        cuentan como fuga, porque no identifican a una persona real.
    """
    total = 0
    for pattern in _PERSONAL_PATH_PATTERNS:
        for match in pattern.finditer(text):
            if not is_placeholder_user(match.group(2)):
                total += 1
        text = pattern.sub(lambda match: f"{match.group(1)}<user>", text)
    return text, total


def redact_all(text: str) -> tuple[str, tuple[str, ...], int]:
    """Aplica secretos y rutas personales en un solo paso determinista.

    Args:
        text: Texto a redactar.

    Returns:
        ``(texto_redactado, tipos_de_secreto, rutas_personales)``.
    """
    redacted, secret_kinds = _redact_secrets(text)
    redacted, path_hits = _redact_personal_paths(redacted)
    return redacted, secret_kinds, path_hits


def redact(text: str) -> tuple[str, tuple[str, ...]]:
    """Redacta secretos y rutas personales de un texto.

    Args:
        text: Texto a redactar.

    Returns:
        ``(texto_redactado, descripciones)``; idempotente por construcción.
    """
    cleaned, kinds, path_hits = redact_all(text)
    parts = [f"secretos:{kind}" for kind in kinds]
    if path_hits:
        parts.append(f"rutas_personales:{path_hits}")
    return cleaned, tuple(parts)


__all__ = ["is_placeholder_user", "redact", "redact_all"]
