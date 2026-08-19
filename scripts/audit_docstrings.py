"""audit_docstrings.py — Auditoria DOC: verifica docstrings en harness/ con Griffe.

Escanea modulos, clases, funciones y metodos publicos de `harness/` usando
**Griffe** (parsing AST, sin ejecutar codigo) y reporta los que carecen de
docstring. Es el gate automatico de la regla DOC (0 funciones sin docstring).

Eficiencia (TKN): solo AST, cero ejecucion, cero LLM. Salida en consola con
archivo:linea:miembro para accion inmediata.

Uso:
    python scripts/audit_docstrings.py                # audit completo
    python scripts/audit_docstrings.py --strict      # exit 1 si hay faltantes
    python scripts/audit_docstrings.py --package memory_rag

Exit codes: 0 = todo con docstring, 1 = hay faltantes (si --strict),
2 = error de entrada.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import griffe

# ---------------------------------------------------------------------------
# Constantes (MAG)
# ---------------------------------------------------------------------------
_HARNESS_ROOT = Path(__file__).resolve().parents[1] / "harness"
_IMPORT_ALIASES = {"Alias"}


def _is_import(member: griffe.Object) -> bool:
    """Determina si un miembro es un import (no definido en el modulo).

    Args:
        member: Miembro de griffe (alias, clase, funcion).

    Returns:
        True si es un Alias de importacion (no requiere docstring propio).
    """
    return type(member).__name__ in _IMPORT_ALIASES


def _collect_missing(obj: griffe.Object, missing: list[tuple[str, str]]) -> None:
    """Recolecta miembros publicos sin docstring dentro de un objeto.

    Args:
        obj: Objeto griffe (modulo, clase) a inspeccionar.
        missing: Lista acumuladora de (ubicacion, nombre) sin docstring.
    """
    for name, member in obj.members.items():
        if name.startswith("_") or _is_import(member):
            continue
        if isinstance(member, (griffe.Function, griffe.Class)):
            if member.docstring is None:
                missing.append((str(member.lineno), member.path))
        if isinstance(member, griffe.Class):
            _collect_missing(member, missing)


def audit(package: str) -> list[tuple[str, str]]:
    """Audita docstrings de un paquete de harness/.

    Args:
        package: Nombre del paquete dentro de harness/ ("memory_rag",
            "orchestrator", o "harness" para todo).

    Returns:
        Lista de (linea, ruta) de miembros publicos sin docstring.

    Raises:
        FileNotFoundError: Si el paquete no existe en harness/.
    """
    pkg_path = _HARNESS_ROOT if package == "harness" else _HARNESS_ROOT / package
    if not pkg_path.exists():
        raise FileNotFoundError(
            f"WHAT: paquete '{package}' no existe en harness/"
            f"WHY: la ruta {pkg_path} no se encuentra"
            f"WHERE: scripts/audit_docstrings.py -> audit()"
        )
    top = griffe.load("harness", search_paths=[str(_HARNESS_ROOT.parent)])
    mod = top if package == "harness" else top[package]
    missing: list[tuple[str, str]] = []
    _collect_missing(mod, missing)
    return sorted(missing, key=lambda item: item[1])


def main() -> int:
    """Punto de entrada CLI: audita docstrings y reporta el resultado.

    Returns:
        0 si no hay faltantes (o sin --strict); 1 con faltantes y --strict;
        2 si el paquete no existe.
    """
    parser = argparse.ArgumentParser(description="Audita docstrings con Griffe")
    parser.add_argument("--package", default="harness", help="Paquete a auditar")
    parser.add_argument("--strict", action="store_true", help="Exit 1 si hay faltantes")
    args = parser.parse_args()
    try:
        missing = audit(args.package)
    except FileNotFoundError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2
    total = len(missing)
    print(f"Auditoria DOC ({args.package}): {total} miembros publicos sin docstring")
    for lineno, path in missing[:40]:
        print(f"  linea {lineno}: {path}")
    if total > 40:
        print(f"  ... y {total - 40} mas")
    if total and args.strict:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())