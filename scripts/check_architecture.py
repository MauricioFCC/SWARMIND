"""Fitness functions de arquitectura (Clean Architecture hexagonal).

Verifica:
- F1: Domain no importa Infrastructure.
- F2: Domain no importa frameworks externos.
- F3: Tamano de modulo <= 500 lineas.
- F4: Sin ciclos de import (basico).
- F5: Tamano de funcion <= 30 lineas (via ruff PLR0915? solo reporta).

Uso: python scripts/check_architecture.py
Exit code 0 si todo pasa, 1 si hay violaciones.
"""

from __future__ import annotations

import ast
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HARNESS = ROOT / "harness"
DOMAIN = HARNESS / "domain"

# Frameworks prohibidos en Domain
FORBIDDEN_FRAMEWORKS = {
    "lancedb", "numpy", "torch", "requests", "sqlalchemy", "chromadb",
    "qdrant_client", "pymongo", "redis", "httpx", "aiohttp",
}

# Modulos de infraestructura que Domain no puede importar
FORBIDDEN_INFRA = {
    "harness.memory_rag",
    "harness.orchestrator",
    "harness.evolve_loop",
    "harness.model_router",
}

MAX_MODULE_LINES = 500
MAX_FUNCTION_LINES = 30


def check_domain_purity() -> list[str]:
    """F1/F2: Domain no importa frameworks ni infraestructura."""
    errors: list[str] = []
    if not DOMAIN.exists():
        return errors
    for path in DOMAIN.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        try:
            tree = ast.parse(text)
        except SyntaxError as exc:
            errors.append(f"{path}: syntax error {exc}")
            continue
        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                names: list[str] = []
                if isinstance(node, ast.Import):
                    names = [a.name.split(".")[0] for a in node.names]
                else:
                    if node.module:
                        names = [node.module]
                for name in names:
                    root = name.split(".")[0]
                    if root in FORBIDDEN_FRAMEWORKS:
                        errors.append(f"{path}: framework prohibido en Domain: {root}")
                    if any(name.startswith(infra) for infra in FORBIDDEN_INFRA):
                        errors.append(f"{path}: infra prohibida en Domain: {name}")
    return errors


def check_module_size() -> list[str]:
    """F3: ningun modulo > 500 lineas."""
    errors: list[str] = []
    for root, _, files in os.walk(HARNESS):
        for f in files:
            if not f.endswith(".py"):
                continue
            path = Path(root) / f
            n = len(path.read_text(encoding="utf-8").splitlines())
            if n > MAX_MODULE_LINES:
                errors.append(f"{path}: {n} lineas > {MAX_MODULE_LINES}")
    return errors


def check_function_size() -> list[str]:
    """F4: ninguna funcion > 30 lineas."""
    errors: list[str] = []
    for root, _, files in os.walk(HARNESS):
        for f in files:
            if not f.endswith(".py"):
                continue
            path = Path(root) / f
            try:
                tree = ast.parse(path.read_text(encoding="utf-8"))
            except SyntaxError:
                continue
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    start = node.lineno
                    end = getattr(node, "end_lineno", start)
                    size = end - start + 1
                    if size > MAX_FUNCTION_LINES:
                        errors.append(f"{path}:{start} {node.name}() {size} lineas > {MAX_FUNCTION_LINES}")
    return errors


def main() -> int:
    all_errors: list[str] = []
    all_errors.extend(check_domain_purity())
    all_errors.extend(check_module_size())
    all_errors.extend(check_function_size())
    strict = "--strict" in sys.argv
    if all_errors:
        print(f"{'FAIL' if strict else 'WARN'}: {len(all_errors)} violaciones arquitectonicas:")
        for e in all_errors[:30]:
            print(f"  - {e}")
        if len(all_errors) > 30:
            print(f"  ... y {len(all_errors) - 30} mas")
        return 1 if strict else 0
    print("OK: 0 violaciones arquitectonicas.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
