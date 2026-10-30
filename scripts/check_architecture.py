"""Fitness functions de arquitectura (Clean Architecture hexagonal).

Verifica:
- F1: Domain no importa Infrastructure.
- F2: Domain no importa frameworks externos.
- F3: Tamano de modulo <= 500 lineas (advisory: deuda legacy).
- F4: Sin ciclos de import entre modulos de ``harness/`` (Tarjan SCC,
  incluye imports relativos; excluye el patron facade paquete<->submodulo).
- F5: Tamano de funcion <= 30 lineas (advisory: deuda legacy).
- F6: Los adaptadores cumplen la FIRMA de los puertos de dominio.
- F7: La deuda legacy (F3/F5) solo baja respecto a
  `scripts/architecture_baseline.json` (ratchet; requiere `--ratchet`).

Modos:
- Sin flags (default): reporta todo, advise-only, exit 0.
- ``--gate``: BLOQUEA (exit 1) con F1/F2/F4/F6/F8 (+F7 si se pasa ``--ratchet``).
- ``--strict``: BLOQUEA con cualquier violacion (incluye deuda legacy).
- ``--ratchet``: compara F3/F5 con el baseline (solo permite reducir).
- ``--write-baseline``: congela los conteos actuales de deuda.
- ``--list-contracts``: imprime los contratos declarativos cargados.
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
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
HARNESS = ROOT / "harness"
DOMAIN = HARNESS / "domain"

# El repo debe ganar a cualquier copia instalada/global de `harness` (p. ej.
# ~/.config/opencode/harness): al ejecutarse como script, sys.path[0] es
# `scripts/`, no la raiz del repo.
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

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
BLOCKING_RULES = ("F1", "F2", "F4", "F6", "F8")

#: Baseline de deuda (ratchet): solo se permite reducir, nunca aumentar.
RATCHET_BASELINE = ROOT / "scripts" / "architecture_baseline.json"
RATCHET_RULES = ("F3", "F5")

#: Contratos declarativos de dependencias (patron tach).
CONTRACTS_FILE = ROOT / "scripts" / "architecture_contracts.toml"

#: Contratos puerto -> adaptadores que deben cumplirlos (F6).
PORT_CONTRACTS: tuple[tuple[str, str, tuple[tuple[str, str], ...]], ...] = (
    (
        "harness.domain.ports",
        "VectorStorePort",
        (
            ("harness.memory_rag.ruscadb_store", "RuscaDBStore"),
            ("harness.memory_rag.lance_vector_store", "LanceVectorStore"),
        ),
    ),
    (
        "harness.domain.ports",
        "TextSearchPort",
        (("harness.memory_rag.ruscadb_store", "RuscaDBStore"),),
    ),
)


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
        text = _read_source(path)
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


def _read_source(path: Path) -> str:
    """Lee un archivo Python tolerando BOM UTF-8 (utf-8-sig).

    Args:
        path: Archivo a leer.

    Returns:
        El contenido como texto.
    """
    return path.read_text(encoding="utf-8-sig")


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
            n = len(_read_source(path).splitlines())
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
                tree = ast.parse(_read_source(path))
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


def _resolve_import_targets(
    node: ast.AST, module_name: str, is_package: bool
) -> list[str]:
    """Resuelve los modulos destino de un nodo de import (absoluto o relativo).

    Args:
        node: Nodo ``Import`` o ``ImportFrom``.
        module_name: Nombre punteado del modulo que contiene el import.
        is_package: True si el archivo es un ``__init__.py``.

    Returns:
        Lista de nombres de modulo candidatos (puede incluir simbolos; la
        resolucion por prefijo los descarta).
    """
    if isinstance(node, ast.Import):
        return [alias.name for alias in node.names]
    if not isinstance(node, ast.ImportFrom):
        return []
    if node.level == 0:
        return [node.module] if node.module else []
    package_parts = module_name.split(".") if is_package else module_name.split(".")[:-1]
    drop = node.level - 1
    if drop > len(package_parts):
        return []
    base_parts = package_parts[: len(package_parts) - drop]
    base = ".".join(base_parts)
    targets: list[str] = []
    if node.module:
        targets.append(f"{base}.{node.module}" if base else node.module)
    else:
        # ``from . import x``: cada alias puede ser un submodulo.
        for alias in node.names:
            targets.append(f"{base}.{alias.name}" if base else alias.name)
    return targets


def _module_graph() -> tuple[dict[str, Path], dict[str, set[str]]]:
    """Construye el grafo de imports internos de ``harness/``.

    Incluye imports relativos (``from ..x import y``), que son el estilo
    dominante en ``harness/memory_rag/**`` y antes eran invisibles para F4.

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
            tree = ast.parse(_read_source(path))
        except SyntaxError:
            continue
        is_package = path.name == "__init__.py"
        for node in _iter_module_imports(tree):
            for mod in _resolve_import_targets(node, name, is_package):
                if not mod.startswith("harness"):
                    continue
                parts = mod.split(".")
                for i in range(len(parts), 0, -1):
                    cand = ".".join(parts[:i])
                    if cand not in files:
                        continue
                    # Un submodulo que importa su propio paquete (__init__) es
                    # el patron facade (re-export) y no un ciclo accionable: el
                    # paquete ya esta en sys.modules cuando se importa el hijo.
                    if name.startswith(f"{cand}."):
                        break
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


def check_port_conformance() -> list[str]:
    """F6: los adaptadores cumplen la FIRMA de los puertos (no solo ``hasattr``).

    ``isinstance`` sobre un ``runtime_checkable`` Protocol solo verifica que el
    atributo exista; un ``hybrid_search(..., keyword_filter)`` vs
    ``query_text`` pasaria invisible y fallaria en runtime. Aqui se comparan
    los parametros requeridos y los nombres.

    Returns:
        Lista de desajustes legibles (vacia si todos los contratos se cumplen).
    """
    import importlib

    errors: list[str] = []
    for port_module, port_name, adapters in PORT_CONTRACTS:
        try:
            port = getattr(importlib.import_module(port_module), port_name)
        except (ImportError, AttributeError) as exc:
            errors.append(f"F6: no se pudo importar {port_module}.{port_name}: {exc}")
            continue
        port_methods = {
            name: value
            for name, value in vars(port).items()
            if not name.startswith("_") and callable(value)
        }
        for adapter_module, adapter_name in adapters:
            try:
                adapter = getattr(importlib.import_module(adapter_module), adapter_name)
            except (ImportError, AttributeError) as exc:
                errors.append(f"F6: {adapter_name} no importable: {exc}")
                continue
            for method_name, port_method in port_methods.items():
                adapter_method = getattr(adapter, method_name, None)
                if adapter_method is None:
                    errors.append(
                        f"F6: {adapter_name} no implementa {port_name}.{method_name}"
                    )
                    continue
                errors.extend(
                    f"F6: {adapter_name}.{method_name} {detail}"
                    for detail in _signature_mismatches(port_method, adapter_method)
                )
    return errors


def _signature_mismatches(port_method: Any, adapter_method: Any) -> list[str]:
    """Detecta desajustes de firma entre el puerto y su adaptador.

    Args:
        port_method: Funcion declarada en el Protocol.
        adapter_method: Implementacion en el adaptador.

    Returns:
        Lista de mensajes (vacia si la firma es compatible).
    """
    import inspect

    port_params = inspect.signature(port_method).parameters
    adapter_params = inspect.signature(adapter_method).parameters
    errors: list[str] = []
    for name, param in port_params.items():
        if name == "self" or param.kind in (
            inspect.Parameter.VAR_KEYWORD,
            inspect.Parameter.VAR_POSITIONAL,
        ):
            continue
        if name not in adapter_params:
            errors.append(f"no acepta el parametro del puerto '{name}'")
    for name, param in adapter_params.items():
        if name == "self" or param.kind in (
            inspect.Parameter.VAR_KEYWORD,
            inspect.Parameter.VAR_POSITIONAL,
        ):
            continue
        if param.default is inspect.Parameter.empty and name not in port_params:
            errors.append(f"exige un parametro extra no declarado en el puerto '{name}'")
    return errors


def load_contracts() -> list[dict]:
    """Carga los contratos declarativos del archivo TOML.

    Returns:
        Lista de contratos (vacia si el archivo no existe o es invalido).
    """
    import tomllib

    if not CONTRACTS_FILE.exists():
        return []
    try:
        payload = tomllib.loads(CONTRACTS_FILE.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError):
        return []
    return list(payload.get("contracts", []))


def check_declarative_contracts() -> list[str]:
    """F8: valida los contratos declarativos de ``architecture_contracts.toml``.

    Returns:
        Lista de violaciones (vacia si todos los contratos se cumplen).
    """
    import tomllib

    if not CONTRACTS_FILE.exists():
        return [f"F8: falta {CONTRACTS_FILE}"]
    try:
        payload = tomllib.loads(CONTRACTS_FILE.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as exc:
        return [f"F8: contratos ilegibles ({exc})"]
    contracts = payload.get("contracts", [])
    if not contracts:
        return ["F8: no hay contratos declarados"]
    _, graph = _module_graph()
    errors: list[str] = []
    for contract in contracts:
        name = str(contract.get("name") or "sin-nombre")
        module = str(contract.get("module") or "")
        if not module:
            errors.append(f"F8: contrato '{name}' sin 'module'")
            continue
        forbidden = tuple(str(item) for item in contract.get("forbidden", []))
        allowed = tuple(str(item) for item in contract.get("allowed", []))
        for dep in sorted(graph.get(module, set())):
            if _matches_prefix(dep, forbidden):
                errors.append(
                    f"F8: '{module}' importa '{dep}' prohibido por el contrato '{name}'"
                )
            elif allowed and not _matches_prefix(dep, allowed):
                errors.append(
                    f"F8: '{module}' importa '{dep}' fuera de la allow-list "
                    f"del contrato '{name}'"
                )
    return errors


def _matches_prefix(module: str, prefixes: tuple[str, ...]) -> bool:
    """Indica si ``module`` coincide con algun prefijo (exacto o anidado)."""
    return any(module == p or module.startswith(f"{p}.") for p in prefixes)


def check_debt_ratchet(findings: dict[str, list[str]]) -> list[str]:
    """F7: la deuda legacy (F3/F5) solo puede bajar respecto al baseline.

    Args:
        findings: Resultado de ``run_checks`` con las listas por regla.

    Returns:
        Lista de incrementos de deuda (vacia si no aumento).
    """
    if not RATCHET_BASELINE.exists():
        return [f"F7: falta el baseline {RATCHET_BASELINE}"]
    try:
        baseline = json.loads(RATCHET_BASELINE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return [f"F7: baseline ilegible ({exc})"]
    limits = baseline.get("rules", {})
    errors: list[str] = []
    for rule in RATCHET_RULES:
        current = len(findings.get(rule, []))
        allowed = int(limits.get(rule, 0))
        if current > allowed:
            errors.append(
                f"F7: deuda {rule} aumento {allowed} -> {current} "
                "(el ratchet solo permite reducir; corrige o justifica el baseline)"
            )
    return errors


def write_debt_baseline(findings: dict[str, list[str]]) -> Path:
    """Escribe el baseline de deuda con los conteos actuales.

    Args:
        findings: Resultado de ``run_checks``.

    Returns:
        Ruta del baseline escrito.
    """
    payload = {
        "generated": "auto",
        "rules": {rule: len(findings.get(rule, [])) for rule in RATCHET_RULES},
    }
    RATCHET_BASELINE.write_text(
        json.dumps(payload, indent=2) + "\n", encoding="utf-8"
    )
    return RATCHET_BASELINE


def run_checks(ratchet: bool = False) -> dict[str, list[str]]:
    """Ejecuta todas las fitness functions y agrupa los hallazgos por regla.

    Args:
        ratchet: Si True, agrega F7 (incremento de deuda vs baseline).

    Returns:
        dict ``F1..F7`` -> lista de violaciones (vacia si pasa).
    """
    frameworks, infra = _scan_domain()
    findings = {
        "F1": infra,
        "F2": frameworks,
        "F3": check_module_size(),
        "F4": check_import_cycles(),
        "F5": check_function_size(),
        "F6": check_port_conformance(),
        "F8": check_declarative_contracts(),
    }
    if ratchet:
        findings["F7"] = check_debt_ratchet(findings)
    return findings


def main(argv: list[str] | None = None) -> int:
    """Punto de entrada CLI.

    Args:
        argv: Argumentos (default ``sys.argv[1:]``).

    Returns:
        Exit code: 0 si pasa el modo elegido, 1 si hay violaciones bloqueantes.
    """
    args = list(sys.argv[1:] if argv is None else argv)
    if "--list-contracts" in args:
        contracts = load_contracts()
        print(json.dumps(contracts, indent=2, ensure_ascii=False))
        return 0 if contracts else 1
    findings = run_checks(ratchet="--ratchet" in args)
    if "--write-baseline" in args:
        path = write_debt_baseline(findings)
        print(f"baseline escrito: {path} -> {len(findings['F3'])} F3, "
              f"{len(findings['F5'])} F5")
        return 0
    if "--strict" in args:
        blocking: tuple[str, ...] = tuple(findings)
    elif "--gate" in args:
        blocking = BLOCKING_RULES + (("F7",) if "--ratchet" in args else ())
    else:
        # Default: advise-only (exit 0). Bloquear solo con --gate/--strict evita
        # romper scripts/hooks que invocan el checker sin flags.
        blocking = ()
    blocking_errors = [err for rule in blocking for err in findings.get(rule, [])]
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
