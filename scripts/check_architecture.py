"""Fitness functions de arquitectura (Clean Architecture hexagonal).

Verifica:
- F1: Domain no importa Infrastructure.
- F2: Domain no importa frameworks externos.
- F3: Tamano de modulo <= 500 lineas (advisory: deuda legacy).
- F4: Sin ciclos de import entre modulos de ``harness/`` (Tarjan SCC).
- F5: Tamano de funcion <= 30 lineas (advisory: deuda legacy).

Modos:
- Sin flags (default): reporta todo, advise-only, exit 0.
- ``--gate``: BLOQUEA (exit 1) con violaciones de F1/F2/F4; F3/F5 advisory.
- ``--strict``: BLOQUEA con cualquier violacion (incluye deuda legacy).
- ``--json``: emite el reporte como JSON (util para CI/telemetria).

Uso: python scripts/check_architecture.py [--gate|--strict] [--json]
"""

from __future__ import annotations

import ast
import json
import os
import sys
from collections import defaultdict
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

#: Reglas que bloquean merge en modo ``--gate`` (barato y sin deuda legacy).
BLOCKING_RULES = ("F1", "F2", "F4")


def _scan_domain() -> tuple[list[str], list[str]]:
    """Escanea ``harness/domain`` y separa violaciones de framework e infra.

    Returns:
        ``(frameworks, infra)``: dos listas de errores legibles.
    """
    frameworks: list[str] = []
    infra: list[str] = []
    if not DOMAIN.exists():
        return frameworks, infra
    for path in DOMAIN.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        try:
            tree = ast.parse(text)
        except SyntaxError as exc:
            frameworks.append(f"{path}: syntax error {exc}")
            continue
        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                names: list[str] = []
                if isinstance(node, ast.Import):
                    names = [a.name.split(".")[0] for a in node.names]
                elif node.module:
                    names = [node.module]
                for name in names:
                    root = name.split(".")[0]
                    if root in FORBIDDEN_FRAMEWORKS:
                        frameworks.append(f"{path}: framework prohibido en Domain: {root}")
                    if any(name.startswith(banned) for banned in FORBIDDEN_INFRA):
                        infra.append(f"{path}: infra prohibida en Domain: {name}")
    return frameworks, infra


def check_domain_purity() -> list[str]:
    """F1/F2: Domain no importa frameworks ni infraestructura."""
    frameworks, infra = _scan_domain()
    return frameworks + infra


def check_module_size() -> list[str]:
    """F3: ningun modulo > 500 lineas (deuda legacy, advisory)."""
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
    """F5: ninguna funcion > 30 lineas (deuda legacy, advisory)."""
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
                        errors.append(
                            f"{path}:{start} {node.name}() {size} lineas > "
                            f"{MAX_FUNCTION_LINES}"
                        )
    return errors


def _iter_module_imports(node: ast.AST) -> list[ast.AST]:
    """Recolecta imports a nivel de modulo (ignora los diferidos en funciones).

    Los imports dentro de una funcion NO se ejecutan al importar el modulo: son
    justamente la tecnica estandar para romper ciclos, por lo que F4 no debe
    contarlos. Los bloques ``if TYPE_CHECKING`` si se incluyen (dependencia
    declarada a proposito).

    Args:
        node: Nodo AST raiz (``ast.Module``).

    Returns:
        Lista de nodos ``Import``/``ImportFrom`` evaluados en tiempo de import.
    """
    found: list[ast.AST] = []
    for child in ast.iter_child_nodes(node):
        if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if isinstance(child, (ast.Import, ast.ImportFrom)):
            found.append(child)
        else:
            found.extend(_iter_module_imports(child))
    return found


def _module_graph() -> tuple[dict[str, Path], dict[str, set[str]]]:
    """Construye el grafo de imports internos de ``harness/``.

    Returns:
        ``(archivos, grafo)``: mapa nombre->ruta y adyacencia entre modulos.
    """
    files: dict[str, Path] = {}
    graph: dict[str, set[str]] = defaultdict(set)
    for path in HARNESS.rglob("*.py"):
        if "tests" in path.parts or "__pycache__" in path.parts:
            continue
        rel = path.relative_to(ROOT).with_suffix("")
        name = ".".join(rel.parts).removesuffix(".__init__")
        files[name] = path
    for name, path in files.items():
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError:
            continue
        for node in _iter_module_imports(tree):
            targets: list[str] = []
            if isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
                targets.append(node.module)
            elif isinstance(node, ast.Import):
                targets.extend(a.name for a in node.names)
            for mod in targets:
                if not mod.startswith("harness"):
                    continue
                parts = mod.split(".")
                for i in range(len(parts), 0, -1):
                    cand = ".".join(parts[:i])
                    if cand in files:
                        graph[name].add(cand)
                        break
    return files, graph


def check_import_cycles() -> list[str]:
    """F4: detecta ciclos de import entre modulos de harness/ (Tarjan SCC)."""
    errors: list[str] = []
    files, graph = _module_graph()
    index = {"n": 0}
    stack: list[str] = []
    low: dict[str, int] = {}
    idx: dict[str, int] = {}
    on_stack: set[str] = set()

    def strongconnect(v: str) -> None:
        idx[v] = index["n"]
        low[v] = index["n"]
        index["n"] += 1
        stack.append(v)
        on_stack.add(v)
        for w in graph.get(v, ()):
            if w not in idx:
                strongconnect(w)
                low[v] = min(low[v], low[w])
            elif w in on_stack:
                low[v] = min(low[v], idx[w])
        if low[v] == idx[v]:
            comp: list[str] = []
            while True:
                w = stack.pop()
                on_stack.discard(w)
                comp.append(w)
                if w == v:
                    break
            if len(comp) > 1:
                errors.append("ciclo de import: " + " <-> ".join(sorted(comp)))
    for node in list(files):
        if node not in idx:
            strongconnect(node)
    return errors


def run_checks() -> dict[str, list[str]]:
    """Ejecuta todas las fitness functions y agrupa los hallazgos por regla.

    Returns:
        dict ``F1..F5`` -> lista de violaciones (vacia si pasa).
    """
    frameworks, infra = _scan_domain()
    return {
        "F1": infra,
        "F2": frameworks,
        "F3": check_module_size(),
        "F4": check_import_cycles(),
        "F5": check_function_size(),
    }


def main(argv: list[str] | None = None) -> int:
    """Punto de entrada CLI.

    Args:
        argv: Argumentos (default ``sys.argv[1:]``).

    Returns:
        Exit code: 0 si pasa el modo elegido, 1 si hay violaciones bloqueantes.
    """
    args = list(sys.argv[1:] if argv is None else argv)
    findings = run_checks()
    blocking = BLOCKING_RULES if "--strict" not in args else tuple(findings)
    blocking_errors = [err for rule in blocking for err in findings[rule]]
    advisory = [err for rule, errs in findings.items() if rule not in blocking
                for err in errs]
    if "--json" in args:
        print(json.dumps(
            {
                "blocking_rules": list(blocking),
                "blocking": blocking_errors,
                "advisory": advisory,
                "counts": {rule: len(errs) for rule, errs in findings.items()},
            },
            indent=2,
        ))
    else:
        if blocking_errors:
            print(f"FAIL: {len(blocking_errors)} violaciones bloqueantes ({','.join(blocking)}):")
            for err in blocking_errors[:30]:
                print(f"  - {err}")
        else:
            print(f"OK: 0 violaciones bloqueantes ({','.join(blocking)}).")
        if advisory:
            print(f"ADVISORY: {len(advisory)} hallazgos (deuda legacy, no bloquean):")
            for err in advisory[:10]:
                print(f"  - {err}")
            if len(advisory) > 10:
                print(f"  ... y {len(advisory) - 10} mas")
    return 1 if blocking_errors else 0


if __name__ == "__main__":
    sys.exit(main())
