"""Auditoría PEP 649/749: usos que dependen de anotaciones en runtime.

PEP 649 (Python 3.14) hace que las anotaciones sean **perezosas**: se guardan
en ``__annotate__`` y se resuelven al acceder a ``__annotations__`` /
``typing.get_type_hints``. Código que introspecciona anotaciones puede cambiar
de comportamiento (orden de evaluación, efectos laterales, ``TYPE_CHECKING``).

Este script escanea ``harness/`` y ``scripts/`` y mantiene un baseline
**explícito con justificación** de cada uso:

- ``runtime-eval``: ``typing.get_type_hints`` / ``annotationlib``.
- ``raw-annotations``: acceso directo a ``__annotations__``.
- ``signature``: ``inspect.signature(...)``.

`--gate` falla si aparece un uso nuevo no registrado; los usos del baseline
deben llevar ``rationale`` no vacío. Un uso que desaparece se reporta como
aviso (baseline obsoleto), nunca como fallo.

Uso:

    python scripts/audit_pep649.py            # reporta
    python scripts/audit_pep649.py --gate     # falla con usos nuevos
    python scripts/audit_pep649.py --write-baseline
"""

from __future__ import annotations

import argparse
import ast
import json
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BASELINE_PATH = Path(__file__).with_name("pep649_baseline.json")

#: Rutas auditadas (tests excluidos: usan introspección a propósito).
TARGETS: tuple[str, ...] = ("harness", "scripts")

#: Nombres que indican evaluación/introspección de anotaciones.
RUNTIME_EVAL_NAMES = frozenset({"get_type_hints", "annotationlib"})
SIGNATURE_NAMES = frozenset({"signature"})


@dataclass(frozen=True)
class Hit:
    """Uso detectado de anotaciones en runtime.

    Args:
        path: Ruta relativa al repo.
        qualname: Función/clase que contiene el uso (``<module>`` si top-level).
        kind: ``runtime-eval``, ``raw-annotations`` o ``signature``.
        line: Línea del uso.
    """

    path: str
    qualname: str
    kind: str
    line: int

    @property
    def key(self) -> str:
        """Clave estable (independiente de la línea) para el baseline."""
        return f"{self.path}::{self.qualname}::{self.kind}"


class _AnnotationVisitor(ast.NodeVisitor):
    """Recorre el AST anotando el ``qualname`` contenedor y los hits."""

    def __init__(self, path: str) -> None:
        self.path = path
        self.hits: list[Hit] = []
        self._stack: list[str] = []

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        """Entra en una clase (contexto de qualname)."""
        self._stack.append(node.name)
        self.generic_visit(node)
        self._stack.pop()

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        """Entra en una función (contexto de qualname)."""
        self._stack.append(node.name)
        self.generic_visit(node)
        self._stack.pop()

    visit_AsyncFunctionDef = visit_FunctionDef

    def visit_Call(self, node: ast.Call) -> None:
        """Detecta ``get_type_hints``/``annotationlib``/``signature``."""
        name = _call_name(node.func)
        if name in RUNTIME_EVAL_NAMES:
            self._add(node, "runtime-eval")
        elif name in SIGNATURE_NAMES:
            self._add(node, "signature")
        self.generic_visit(node)

    def visit_Attribute(self, node: ast.Attribute) -> None:
        """Detecta accesos directos a ``__annotations__``."""
        if node.attr == "__annotations__":
            self._add(node, "raw-annotations")
        self.generic_visit(node)

    def _add(self, node: ast.AST, kind: str) -> None:
        self.hits.append(
            Hit(
                path=self.path,
                qualname=".".join(self._stack) or "<module>",
                kind=kind,
                line=getattr(node, "lineno", 0),
            )
        )


def _call_name(func: ast.AST) -> str:
    """Nombre final de un callable (``get_type_hints``, ``signature``, ...)."""
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return ""


def scan_file(path: Path, root: Path = ROOT) -> list[Hit]:
    """Escanea un archivo en busca de introspección de anotaciones.

    Args:
        path: Archivo ``.py``.
        root: Raíz para relativizar la ruta.

    Returns:
        Lista de hits (vacía si no hay o no parsea).
    """
    try:
        tree = ast.parse(path.read_text(encoding="utf-8-sig"))
    except (OSError, SyntaxError):
        return []
    visitor = _AnnotationVisitor(path.relative_to(root).as_posix())
    visitor.visit(tree)
    return visitor.hits


def scan_tree(targets: tuple[str, ...] = TARGETS, root: Path = ROOT) -> list[Hit]:
    """Escanea los targets excluyendo tests.

    Args:
        targets: Directorios a auditar.
        root: Raíz del repo.

    Returns:
        Hits ordenados por ruta y línea.
    """
    hits: list[Hit] = []
    for target in targets:
        for path in (root / target).rglob("*.py"):
            parts = set(path.parts)
            if "tests" in parts or path.name.startswith("test_"):
                continue
            hits.extend(scan_file(path, root))
    return sorted(hits, key=lambda hit: (hit.path, hit.line, hit.kind))


def load_baseline() -> dict[str, str]:
    """Lee el baseline ``clave -> justificación``.

    Returns:
        Mapa de usos aceptados (vacío si no existe o está corrupto).
    """
    if not BASELINE_PATH.exists():
        return {}
    try:
        payload = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    entries = payload.get("entries", payload)
    if not isinstance(entries, list):
        return {}
    return {
        str(entry.get("key")): str(entry.get("rationale", ""))
        for entry in entries
        if isinstance(entry, dict) and entry.get("key")
    }


def write_baseline(hits: list[Hit], rationale: str = "pendiente de justificar") -> None:
    """Escribe el baseline con los hits actuales.

    Args:
        hits: Hits detectados.
        rationale: Justificación por defecto para los nuevos.
    """
    existing = load_baseline()
    payload = {
        "version": 1,
        "entries": [
            {
                "key": hit.key,
                "kind": hit.kind,
                "rationale": existing.get(hit.key) or rationale,
            }
            for hit in hits
        ],
    }
    BASELINE_PATH.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(f"baseline PEP 649 escrito: {BASELINE_PATH} ({len(hits)} usos)")


def evaluate(hits: list[Hit], baseline: dict[str, str]) -> tuple[list[str], list[str]]:
    """Compara usos actuales contra el baseline.

    Args:
        hits: Hits detectados.
        baseline: Baseline ``clave -> justificación``.

    Returns:
        ``(fallos, avisos)``: usos nuevos sin registrar y entradas obsoletas.
    """
    current = {hit.key for hit in hits}
    failures = [
        f"uso nuevo sin registrar: {hit.key} (linea {hit.line})"
        for hit in hits
        if hit.key not in baseline
    ]
    failures.extend(
        f"uso sin justificar: {key}"
        for key, rationale in baseline.items()
        if key in current and not rationale.strip()
    )
    warnings = sorted(key for key in baseline if key not in current)
    return failures, warnings


def main(argv: list[str] | None = None) -> int:
    """Entrypoint de la auditoría.

    Args:
        argv: Argumentos CLI (``None`` usa ``sys.argv``).

    Returns:
        Exit code (0 = OK, 1 = uso nuevo/sin justificar).
    """
    parser = argparse.ArgumentParser(description="Auditoria PEP 649")
    parser.add_argument("--gate", action="store_true", help="falla con usos nuevos")
    parser.add_argument("--write-baseline", action="store_true", help="fija baseline")
    parser.add_argument("--json", action="store_true", help="salida JSON")
    args = parser.parse_args(argv)

    hits = scan_tree()
    if args.write_baseline:
        write_baseline(hits)
    failures, warnings = evaluate(hits, load_baseline())

    if args.json:
        print(
            json.dumps(
                {
                    "hits": [
                        {
                            "key": hit.key,
                            "kind": hit.kind,
                            "line": hit.line,
                        }
                        for hit in hits
                    ],
                    "failures": failures,
                    "warnings": warnings,
                },
                indent=2,
                sort_keys=True,
            )
        )
    else:
        print(f"PEP 649: {len(hits)} usos de anotaciones en runtime")
        for hit in hits:
            print(f"  {hit.path}:{hit.line} {hit.kind} ({hit.qualname})")
        for warning in warnings:
            print(f"  AVISO baseline obsoleto: {warning}")

    if failures and (args.gate or args.write_baseline):
        print("\nGATE PEP 649: FAIL", file=sys.stderr)
        for failure in failures:
            print(f"  - {failure}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
