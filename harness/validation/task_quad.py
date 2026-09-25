"""task_quad.py — Gate QUAD: claridad directiva anti-vaguedad (ADR-0088).

WHAT: Valida que una asignacion traiga Que/Hasta-cuando/Estandar/Impacto
+ 1 SOLO dueno (lista o multi-dueno = nadie responsable).
WHY: Framework QUAD — "haz lo mejor que puedas" es la frase mas peligrosa
del liderazgo; la vaguedad desmorona el estandar en la brecha de
interpretacion. La claridad habilita autonomia (no micromanagement).
WHERE: Antes de aceptar una tarea (coordinator); el spec la referencia.

Uso:
    report = check_quad({"que": ..., "hasta_cuando": ..., "estandar": ...,
                         "impacto": ..., "dueno": "builder"})
"""

from __future__ import annotations

from dataclasses import dataclass

#: Los 5 campos QUAD en orden.
QUAD_FIELDS: tuple[str, ...] = (
    "que",
    "hasta_cuando",
    "estandar",
    "impacto",
    "dueno",
)


@dataclass(frozen=True)
class QuadReport:
    """Resultado del gate QUAD.

    Attributes:
        passed: True si los 5 campos estan presentes y el dueno es uno solo.
        missing: Campos ausentes/vacios o dueno invalido ("dueno").
    """

    passed: bool
    missing: tuple[str, ...]


def _has_content(value: object) -> bool:
    """True si el valor aporta contenido (no vacio/blanco).

    Args:
        value: Valor del campo (str u otro).

    Returns:
        False para None, "", blancos o colecciones vacias.
    """
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, tuple, dict, set)):
        return len(value) > 0
    return True


def check_quad(task: dict) -> QuadReport:
    """Verifica los 5 campos QUAD + dueno unico.

    Args:
        task: Dict de la asignacion (claves = campos QUAD).

    Returns:
        QuadReport con pass y faltantes.

    Raises:
        TypeError: Si task no es dict (WHAT+WHY+WHERE).
    """
    if not isinstance(task, dict):
        raise TypeError(
            f"WHAT: task no es dict (es {type(task).__name__}). "
            "WHY: el gate lee campos por clave. "
            "WHERE: check_quad"
        )
    missing = [f for f in QUAD_FIELDS if not _has_content(task.get(f))]
    owner = task.get("dueno")
    if isinstance(owner, (list, tuple, set, dict)) and "dueno" not in missing:
        # Tres responsables = nadie responsable: un solo nombre.
        missing.append("dueno")
    return QuadReport(passed=not missing, missing=tuple(missing))
