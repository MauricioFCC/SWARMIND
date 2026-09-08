"""structured_enforcer.py — Salida con schema + retry con feedback (ADR-0073).

WHAT: Valida la salida cruda contra un JSON schema; si falla, re-ask al
modelo con feedback accionable del error (max max_retries intentos).
WHY: Frontera — JSON schema obligatorio da 99.9% adherencia vs <70% sin
constraint (30x menos fallos de parse); sin schema hay 300K+ respuestas
malformadas por 1M requests y cada retry sin feedback re-paga tokens.
WHERE: Votaciones, veredictos de agentes y toda salida machine-readable
del orquestador; complementa a nlt_types (que consume el dict final).

Uso:
    data = enforce_schema(retry_fn, SCHEMA, max_retries=2)
"""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Callable

logger = logging.getLogger("harness.orchestrator.structured_enforcer")

#: Regex para extraer JSON de fences markdown u otros envoltorios.
_JSON_EXTRACT_RE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.DOTALL)


class StructuredEnforcementError(Exception):
    """La salida no cumplio el schema tras agotar los retries."""


def _extract_json(raw: str) -> str:
    """Extrae el cuerpo JSON de un raw (soporta fences markdown).

    Args:
        raw: Texto crudo del modelo.

    Returns:
        Substring candidato a JSON (el raw completo si no hay fences).
    """
    match = _JSON_EXTRACT_RE.search(raw)
    return match.group(1) if match else raw


def _validate(data: object, schema: dict) -> str | None:
    """Validacion minima de schema (type/required/properties/minimum).

    Args:
        data: Objeto parseado del JSON.
        schema: JSON schema simplificado (object con required/properties).

    Returns:
        Descripcion del primer error o None si es valido.
    """
    if not isinstance(data, dict):
        return f"se esperaba objeto JSON, se recibio {type(data).__name__}"
    required = schema.get("required", [])
    properties = schema.get("properties", {})
    for field in required:
        if field not in data:
            return f"falta el campo requerido '{field}'"
    for field, spec in properties.items():
        if field not in data:
            continue
        expected = spec.get("type")
        value = data[field]
        type_ok = {
            "string": lambda v: isinstance(v, str),
            "integer": lambda v: isinstance(v, int) and not isinstance(v, bool),
            "number": lambda v: isinstance(v, (int, float)) and not isinstance(v, bool),
            "boolean": lambda v: isinstance(v, bool),
            "object": lambda v: isinstance(v, dict),
            "array": lambda v: isinstance(v, list),
        }.get(expected, lambda v: True)(value)
        if not type_ok:
            return f"campo '{field}' debe ser {expected} (se recibio {type(value).__name__})"
        minimum = spec.get("minimum")
        if minimum is not None and isinstance(value, (int, float)) and value < minimum:
            return f"campo '{field}' debe ser >= {minimum} (se recibio {value})"
    return None


def enforce_schema(
    retry_fn: Callable[[str], str],
    schema: dict,
    max_retries: int = 2,
    instruction: str = "Devuelve SOLO JSON valido conforme al schema.",
) -> dict:
    """Obtiene un dict conforme al schema con retries con feedback.

    Args:
        retry_fn: (feedback) -> raw del modelo. Primer call usa feedback
            de instruccion; los siguientes llevan el error concreto.
        schema: JSON schema simplificado (type/required/properties/minimum).
        max_retries: Intentos adicionales tras el primero.
        instruction: Feedback inicial (prompt de formato).

    Returns:
        Dict validado.

    Raises:
        ValueError: Si schema vacio (WHAT+WHY+WHERE).
        StructuredEnforcementError: Si tras los retries no valida.
    """
    if not schema:
        raise ValueError(
            "WHAT: schema vacio. "
            "WHY: sin schema no hay contrato que validar. "
            "WHERE: enforce_schema"
        )
    feedback = instruction
    attempts = max_retries + 1
    last_error = "sin intentos"
    for attempt in range(attempts):
        raw = retry_fn(feedback)
        candidate = _extract_json(str(raw))
        try:
            data = json.loads(candidate)
        except json.JSONDecodeError as exc:
            last_error = f"JSON malformado: {exc}"
            feedback = f"{instruction} Error: {last_error}"
            logger.warning("structured_enforcer: intento %d fallo: %s", attempt + 1, last_error)
            continue
        error = _validate(data, schema)
        if error is None:
            return data
        last_error = error
        feedback = f"{instruction} Error: {error}"
        logger.warning("structured_enforcer: intento %d fallo: %s", attempt + 1, error)
    raise StructuredEnforcementError(
        f"WHAT: salida no conforme al schema tras {attempts} intentos ({last_error}). "
        "WHY: el schema define el contrato machine-readable del orquestador. "
        "WHERE: enforce_schema"
    )
