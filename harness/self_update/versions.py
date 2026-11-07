"""Versiones semver compartidas de auto-actualizacion (spec self-update.md)."""
from __future__ import annotations

import re

NO_VERSION: tuple[int, ...] = (0, 0, 0)


def fmt_version(version: tuple[int, ...]) -> str:
    """Formatea (0, 2, 0) -> '0.2.0' para logs legibles."""
    return ".".join(str(x) for x in version)


def parse_semver(texto: str) -> tuple[int, ...] | None:
    """Convierte 'v1.2.3-rc1' -> (1, 2, 3); None si no hay digitos utiles.

    Args:
        texto: Version cruda (pyproject, git describe o entrada de log).

    Returns:
        Tupla a 3+ componentes normalizada, o None si es ilegible.
    """
    nucleo = re.split(r"[-+]", texto.strip().lstrip("vV"))[0]
    partes: list[int] = []
    for pieza in nucleo.split("."):
        match = re.match(r"\d+", pieza)
        if match is None:
            break
        partes.append(int(match.group()))
    if not partes:
        return None
    if len(partes) < 3:
        partes.extend([0] * (3 - len(partes)))
    return tuple(partes)
