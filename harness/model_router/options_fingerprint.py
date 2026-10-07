"""options_fingerprint.py — Fingerprint canonico de opciones de generacion.

Produce un hash SHA-256 estable de :class:`GenerationOptions` para detectar
cambios de configuracion y garantizar determinismo en salidas estructuradas
(``json``, ``tool_call``, ``structured``).

Reglas: SEG (serializacion sin ambiguedad), IMM (dataclass frozen),
MAG (sin numeros magicos), DOC (docstrings ES).
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, fields

DETERMINISTIC_TEMPERATURE = 0.0
DETERMINISTIC_SEED = 42
FINGERPRINT_HEX_LEN = 64
DETERMINISTIC_OUTPUT_KINDS = frozenset({"json", "tool_call", "structured"})

# Separador ASCII Unit Separator (0x1F): ausente en texto/prompts normales,
# evita colisiones entre concatenaciones de campos adyacentes.
_FIELD_SEPARATOR = "\x1f"

__all__ = [
    "DETERMINISTIC_OUTPUT_KINDS",
    "DETERMINISTIC_SEED",
    "DETERMINISTIC_TEMPERATURE",
    "FINGERPRINT_HEX_LEN",
    "GenerationOptions",
    "deterministic_options",
    "options_fingerprint",
    "should_be_deterministic",
]


@dataclass(frozen=True)
class GenerationOptions:
    """Opciones inmutables para una llamada de generacion.

    Args:
        model: Identificador del modelo.
        num_ctx: Tamano de la ventana de contexto en tokens.
        temperature: Temperatura de muestreo.
        top_p: Nucleus sampling (por defecto ``1.0``).
        seed: Semilla de muestreo; ``None`` si no se fija.
        keep_alive: Tiempo de retencion del modelo en memoria.
        system_prompt: Prompt de sistema aplicado.
        adapter: Adaptador/LoRA opcional asociado al modelo.
    """

    model: str
    num_ctx: int
    temperature: float
    top_p: float = 1.0
    seed: int | None = None
    keep_alive: str = "0"
    system_prompt: str = ""
    adapter: str = ""


def options_fingerprint(options: GenerationOptions) -> str:
    """Calcula el fingerprint SHA-256 de un conjunto de opciones.

    La serializacion respeta el orden de declaracion de los campos y usa
    ``repr`` (sin ambiguedad entre tipos) con un separador de control. Asi,
    la misma entrada produce siempre el mismo hash y cualquier campo distinto
    produce un hash distinto.

    Args:
        options: Opciones de generacion a resumir.

    Returns:
        Hash SHA-256 en hexadecimal (``FINGERPRINT_HEX_LEN`` caracteres).
    """
    payload = _FIELD_SEPARATOR.join(
        f"{field.name}={getattr(options, field.name)!r}" for field in fields(options)
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def deterministic_options(model: str, num_ctx: int, **kw: object) -> GenerationOptions:
    """Construye opciones deterministas (temperatura 0 y semilla fija).

    Args:
        model: Identificador del modelo.
        num_ctx: Tamano de la ventana de contexto en tokens.
        **kw: Otros campos de :class:`GenerationOptions` (top_p, keep_alive,
            system_prompt, adapter).

    Returns:
        ``GenerationOptions`` con ``temperature=DETERMINISTIC_TEMPERATURE`` y
        ``seed=DETERMINISTIC_SEED`` forzados.

    Raises:
        TypeError: Si ``kw`` contiene claves desconocidas para la dataclass.
    """
    kw["temperature"] = DETERMINISTIC_TEMPERATURE
    kw["seed"] = DETERMINISTIC_SEED
    return GenerationOptions(model=model, num_ctx=num_ctx, **kw)


def should_be_deterministic(kind: str) -> bool:
    """Indica si un tipo de salida exige generacion determinista.

    Args:
        kind: Tipo de salida esperada (p. ej. ``"json"``).

    Returns:
        ``True`` si ``kind`` esta en ``DETERMINISTIC_OUTPUT_KINDS``.
    """
    return kind in DETERMINISTIC_OUTPUT_KINDS
