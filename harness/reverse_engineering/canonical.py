"""JSON canónico (RFC 8785 simplificado) y digests SHA-256.

Réplica en Python de `craft-anything/crates/evidence/src/canonical.rs`:
claves ordenadas por unidades UTF-16, sin espacios insignificantes, escapes
mínimos y profundidad acotada. El id de una evidencia es el SHA-256 de su JSON
canónico, así la misma observación produce siempre el mismo id y cualquier
edición posterior es detectable.
"""

from __future__ import annotations

import hashlib
import json
import math
from typing import Any

#: Profundidad máxima serializada; más allá se escribe ``null`` (anti-stack).
MAX_DEPTH = 512


def canonical_json(value: Any) -> str:
    """Serializa ``value`` a JSON canónico (claves ordenadas, sin espacios).

    Args:
        value: Valor JSON-compatible (dict, list, str, int, float, bool, None).

    Returns:
        Texto JSON canónico.

    Raises:
        ValueError: Si el valor no es JSON-compatible o contiene NaN/Infinito.
    """
    chunks: list[str] = []
    _write_value(chunks, value, 0)
    return "".join(chunks)


def sha256_hex(data: bytes) -> str:
    """Devuelve el SHA-256 en hexadecimal minúsculas de ``data``."""
    return hashlib.sha256(data).hexdigest()


def stable_id(prefix: str, payload: Any) -> str:
    """Construye ``<prefix>_<sha256(canonical_json(payload))>``."""
    return f"{prefix}_{sha256_hex(canonical_json(payload).encode('utf-8'))}"


def _write_value(out: list[str], value: Any, depth: int) -> None:
    """Escribe ``value`` recursivamente respetando el límite de profundidad."""
    if depth > MAX_DEPTH:
        out.append("null")
        return
    if value is None:
        out.append("null")
    elif isinstance(value, bool):
        out.append("true" if value else "false")
    elif isinstance(value, int):
        out.append(str(value))
    elif isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("JSON canónico no admite NaN ni Infinito")
        out.append(repr(value))
    elif isinstance(value, str):
        out.append(_write_string(value))
    elif isinstance(value, (list, tuple)):
        _write_array(out, value, depth)
    elif isinstance(value, dict):
        _write_object(out, value, depth)
    else:
        raise ValueError(f"valor no JSON-compatible: {type(value).__name__}")


def _write_array(out: list[str], items: Any, depth: int) -> None:
    """Escribe un array JSON canónico."""
    out.append("[")
    for index, item in enumerate(items):
        if index:
            out.append(",")
        _write_value(out, item, depth + 1)
    out.append("]")


def _write_object(out: list[str], mapping: dict[str, Any], depth: int) -> None:
    """Escribe un objeto JSON con claves ordenadas por UTF-16."""
    out.append("{")
    keys = sorted((str(key) for key in mapping), key=lambda key: key.encode("utf-16-be"))
    for index, key in enumerate(keys):
        if index:
            out.append(",")
        out.extend((_write_string(key), ":"))
        _write_value(out, mapping[key], depth + 1)
    out.append("}")


def _write_string(text: str) -> str:
    """Escapa una cadena con las reglas mínimas de JSON (no ASCII-only)."""
    escaped: list[str] = ['"']
    for char in text:
        if char == '"':
            escaped.append('\\"')
        elif char == "\\":
            escaped.append("\\\\")
        elif char == "\b":
            escaped.append("\\b")
        elif char == "\f":
            escaped.append("\\f")
        elif char == "\n":
            escaped.append("\\n")
        elif char == "\r":
            escaped.append("\\r")
        elif char == "\t":
            escaped.append("\\t")
        elif ord(char) < 0x20:
            escaped.append(f"\\u{ord(char):04x}")
        else:
            escaped.append(char)
    escaped.append('"')
    return "".join(escaped)


def dumps(value: Any) -> str:
    """Alias legible de :func:`canonical_json`."""
    return canonical_json(value)


def loads(text: str) -> Any:
    """Carga JSON y valida que no contenga NaN/Infinito."""
    return json.loads(text, parse_constant=_reject_constant)


def _reject_constant(name: str) -> Any:
    """Rechaza las constantes no estándar de ``json`` (NaN/Infinity)."""
    raise ValueError(f"JSON no estándar: {name}")
