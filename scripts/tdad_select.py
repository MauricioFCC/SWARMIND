"""tdad_select.py — Selección de tests impactados por cambios (TDAD minimal).

Implementa el enfoque TDAD (Test-Driven Agentic Development, arXiv:2603.17973):
antes de aplicar un cambio, el agente necesita saber QUÉ tests verificar, no
instrucciones de proceso. Para ello se recorre un grafo explícito código->test:

  1. Se parsean los imports (ast, stdlib) de cada módulo de harness/.
  2. Se construye el grafo de dependencias módulo -> módulos que importa.
  3. Para cada archivo modificado se buscan: (a) su test directo
     test_<modulo>.py, (b) los tests de los módulos que dependen
     transitivamente de él (reverse BFS sobre el grafo).

Solo stdlib (argparse/ast/subprocess): sin librerías externas de análisis
(YAGNI). Idempotente: mismo input -> mismo output (sets + orden estable).

Uso:
    python scripts/tdad_select.py --base origin/main --dry-run
    python scripts/tdad_select.py harness/common.py --dry-run
    python scripts/tdad_select.py --base origin/main --run
    python scripts/tdad_select.py --base origin/main --exit-code
"""

from __future__ import annotations

import argparse
import ast
import logging
import subprocess
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
_HARNESS_DIR = _REPO_ROOT / "harness"
_TESTS_DIR = _HARNESS_DIR / "tests"
_DIFF_FILTER = "ACMR"  # Añadidos, Copiados, Modificados, Renombrados (git)
_PY_EXT = ".py"
_INIT_FILE = "__init__.py"
_PYCACHE_DIR = "__pycache__"
_HARNESS_PKG = "harness"
_PKG_PREFIX = "harness."
_TEST_PREFIX = "test_"
_EXIT_OK = 0
_EXIT_NO_TESTS = 1  # Cambios sin tests seleccionados (--exit-code, CI)
_EXIT_ERROR = 2
_LOG = logging.getLogger("tdad_select")


# ---------------------------------------------------------------------------
# Grafo de dependencias (módulo -> módulos que importa)
# ---------------------------------------------------------------------------


def module_name_for(file_path: Path, harness_dir: Path) -> str | None:
    """Devuelve el nombre de módulo dotted de un archivo bajo harness/.

    Ejemplos: harness/common.py -> "common", harness/aifactory/__init__.py -> "aifactory",
    harness/orchestrator/planner.py -> "orchestrator.planner".

    Args:
        file_path: Ruta del archivo .py (absoluta o relativa).
        harness_dir: Directorio raíz de harness/.

    Returns:
        Nombre de módulo dotted, o None si el archivo no está bajo harness_dir.
    """
    try:
        relative = file_path.resolve().relative_to(harness_dir.resolve())
    except ValueError:
        return None
    parts = list(relative.parts)
    if parts[-1] == _INIT_FILE:
        return ".".join(parts[:-1]) or _HARNESS_PKG
    return ".".join(parts[:-1] + [parts[-1][: -len(_PY_EXT)]])


def _top_level_modules(harness_dir: Path) -> set[str]:
    """Devuelve los nombres de paquetes/módulos de primer nivel de harness/."""
    names: set[str] = set()
    for entry in harness_dir.iterdir():
        if entry.is_file() and entry.suffix == _PY_EXT and entry.name != _INIT_FILE:
            names.add(entry.stem)
        elif entry.is_dir() and (entry / _INIT_FILE).exists():
            names.add(entry.name)
    return names


def _match_internal(imported: str, known_modules: set[str], top_level: set[str]) -> set[str]:
    """Devuelve el módulo interno de mayor profundidad que coincide con el import.

    Args:
        imported: Nombre dotted importado (ej. "harness.common", "numpy", "common").
        known_modules: Nombres de todos los módulos internos de harness/.
        top_level: Nombres de paquetes/módulos de primer nivel de harness/.

    Returns:
        Conjunto con el módulo interno coincidente (vacío si es externo).
    """
    if imported == _HARNESS_PKG:
        return {_HARNESS_PKG} if _HARNESS_PKG in known_modules else set()
    imported = imported.removeprefix(_PKG_PREFIX)
    parts = imported.split(".")
    if parts[0] not in top_level and imported not in known_modules:
        return set()
    for depth in range(len(parts), 0, -1):
        candidate = ".".join(parts[:depth])
        if candidate in known_modules:
            return {candidate}
    return set()


def _relative_targets(module_name: str, level: int, imported: str) -> set[str]:
    """Resuelve un import relativo a posibles nombres dotted (hoja o paquete).

    Un import `from .x import y` puede aparecer en un módulo hoja (a.b.c ->
    paquete a.b) o en un __init__.py (a.b.c -> paquete a.b.c). Se devuelven
    ambos candidatos y _match_internal filtra contra los módulos existentes.

    Args:
        module_name: Nombre del módulo que contiene el import (ej. "a.b.c").
        level: Nivel del import relativo (1 para ".", 2 para "..", etc.).
        imported: Nombre importado (módulo o alias).

    Returns:
        Conjunto de nombres dotted candidatos (vacío si no hay paquete base).
    """
    parts = module_name.split(".")
    anchors = {
        ".".join(parts[: len(parts) - level]),
        ".".join(parts[: len(parts) - level + 1]),
    }
    return {f"{anchor}.{imported}" for anchor in anchors if anchor}


def parse_imports(
    source: str,
    module_name: str,
    known_modules: set[str],
    top_level: set[str],
) -> set[str]:
    """Devuelve los módulos internos de harness/ que importa un archivo fuente.

    Args:
        source: Contenido del archivo .py.
        module_name: Nombre de módulo dotted del archivo (ver module_name_for).
        known_modules: Nombres de todos los módulos internos de harness/.
        top_level: Nombres de paquetes/módulos de primer nivel de harness/.

    Returns:
        Conjunto de módulos internos importados (nombres dotted).

    Raises:
        ValueError: Si el source no es Python válido (SyntaxError).
    """
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        raise ValueError(f"sintaxis inválida: {exc}") from exc

    internal: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                internal |= _match_internal(alias.name, known_modules, top_level)
        elif isinstance(node, ast.ImportFrom):
            if node.level > 0:
                if node.module:
                    for target in _relative_targets(module_name, node.level, node.module):
                        internal |= _match_internal(target, known_modules, top_level)
                else:
                    for alias in node.names:
                        for target in _relative_targets(module_name, node.level, alias.name):
                            internal |= _match_internal(target, known_modules, top_level)
            elif node.module:
                internal |= _match_internal(node.module, known_modules, top_level)
    return internal


def build_dependency_graph(
    harness_dir: Path, tests_dir: Path
) -> tuple[dict[str, set[str]], set[str], set[str]]:
    """Construye el grafo de dependencias de imports entre módulos de harness/.

    Args:
        harness_dir: Directorio raíz de harness/.
        tests_dir: Directorio de tests (excluido del grafo).

    Returns:
        Tupla (deps, known_modules, top_level): deps[módulo] = módulos que importa.
    """
    py_files = [
        path
        for path in harness_dir.rglob("*.py")
        if tests_dir not in path.parents and _PYCACHE_DIR not in path.parts
    ]
    known_modules = {
        module
        for path in py_files
        if (module := module_name_for(path, harness_dir)) is not None
    }
    top_level = _top_level_modules(harness_dir)
    deps: dict[str, set[str]] = {}
    for path in py_files:
        module = module_name_for(path, harness_dir)
        if module is None:
            continue
        try:
            deps[module] = parse_imports(
                path.read_text(encoding="utf-8-sig", errors="replace"),
                module,
                known_modules,
                top_level,
            )
        except ValueError as exc:
            _LOG.warning("build_dependency_graph: %s (se omite módulo %s): %s", path, module, exc)
            deps[module] = set()
    return deps, known_modules, top_level


def reverse_dependencies(deps: dict[str, set[str]]) -> dict[str, set[str]]:
    """Invierte el grafo: módulo -> conjunto de módulos que dependen de él.

    Args:
        deps: Grafo directo módulo -> módulos que importa.

    Returns:
        Grafo inverso módulo -> módulos que lo importan.
    """
    dependents: dict[str, set[str]] = {}
    for module, imports in deps.items():
        for imported in imports:
            dependents.setdefault(imported, set()).add(module)
    return dependents


def transitive_dependents(module: str, dependents: dict[str, set[str]]) -> set[str]:
    """Devuelve los módulos que dependen transitivamente de `module` (BFS).

    Args:
        module: Módulo modificado.
        dependents: Grafo inverso (ver reverse_dependencies).

    Returns:
        Conjunto de módulos que (directa o indirectamente) importan a `module`.
    """
    visited: set[str] = set()
    queue = list(dependents.get(module, set()))
    while queue:
        current = queue.pop()
        if current in visited:
            continue
        visited.add(current)
        queue.extend(dependents.get(current, set()))
    return visited


# ---------------------------------------------------------------------------
# Selección de tests
# ---------------------------------------------------------------------------


def direct_test_for(file_path: Path, tests_dir: Path) -> Path | None:
    """Devuelve el test directo test_<modulo>.py si existe, o None.

    Args:
        file_path: Archivo modificado (.py).
        tests_dir: Directorio harness/tests/.

    Returns:
        Ruta del test directo, o None si no existe.
    """
    if file_path.name == _INIT_FILE:
        stem = file_path.parent.name
    else:
        stem = file_path.stem
    candidate = tests_dir / f"{_TEST_PREFIX}{stem}{_PY_EXT}"
    return candidate if candidate.exists() else None


def select_tests(
    modified_files: list[Path],
    dependents: dict[str, set[str]],
    tests_dir: Path,
    harness_dir: Path,
) -> tuple[list[Path], list[str]]:
    """Selecciona los tests impactados por los archivos modificados.

    Para cada archivo: (a) su test directo test_<modulo>.py, (b) los tests de
    los módulos que dependen transitivamente de él, (c) si es un test, él mismo.

    Args:
        modified_files: Archivos modificados (ruta absoluta).
        dependents: Grafo inverso (ver reverse_dependencies).
        tests_dir: Directorio harness/tests/.
        harness_dir: Directorio raíz de harness/.

    Returns:
        Tupla (tests seleccionados ordenados y deduplicados, avisos).
    """
    selected: set[Path] = set()
    warnings: list[str] = []
    for file_path in modified_files:
        if file_path.suffix != _PY_EXT:
            warnings.append(f"no aplica (no es código Python): {file_path}")
            continue
        if tests_dir in file_path.parents:
            selected.add(file_path)
            continue
        candidates: set[Path | None] = {direct_test_for(file_path, tests_dir)}
        module = module_name_for(file_path, harness_dir)
        if module is not None:
            for dep in transitive_dependents(module, dependents):
                candidates.add(tests_dir / f"{_TEST_PREFIX}{dep.split('.')[-1]}{_PY_EXT}")
        found = {path for path in candidates if path is not None and path.exists()}
        if found:
            selected |= found
        else:
            warnings.append(f"sin test asociado: {file_path}")
    return sorted(selected, key=str), warnings


# ---------------------------------------------------------------------------
# Recolección de archivos modificados
# ---------------------------------------------------------------------------


def _files_from_git_diff(base: str, repo_root: Path) -> list[Path]:
    """Obtiene los archivos modificados desde git diff --name-only.

    Args:
        base: Ref git (ej. origin/main).
        repo_root: Raíz del repositorio.

    Returns:
        Lista de rutas de archivos modificados (existentes en el working tree).

    Raises:
        ValueError: Si git falla (ref inexistente o repo sin git).
    """
    result = subprocess.run(
        ["git", "diff", "--name-only", f"--diff-filter={_DIFF_FILTER}", base],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()
        raise ValueError(f"git diff contra {base!r} falló (code={result.returncode}): {detail}")
    return [repo_root / line for line in result.stdout.splitlines() if line.strip()]


def collect_modified_files(paths: list[str], base: str | None, repo_root: Path) -> list[Path]:
    """Recolecta los archivos modificados: argumentos explícitos o git diff.

    Args:
        paths: Rutas explícitas pasadas por CLI.
        base: Ref git (ej. origin/main) para `git diff --name-only`.
        repo_root: Raíz del repositorio.

    Returns:
        Lista de rutas absolutas de archivos modificados (existentes).

    Raises:
        ValueError: Si una ruta explícita no existe o no hay ninguna entrada.
    """
    if base is not None:
        return _files_from_git_diff(base, repo_root)
    if not paths:
        raise ValueError("sin entrada: pase archivos modificados o use --base <ref>")
    files: list[Path] = []
    for raw in paths:
        candidate = Path(raw)
        if not candidate.is_absolute():
            candidate = repo_root / candidate
        if not candidate.exists():
            raise ValueError(f"archivo inexistente: {raw}")
        files.append(candidate)
    return files


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def run_pytest(test_paths: list[Path], cwd: Path) -> int:
    """Ejecuta pytest sobre los tests seleccionados y devuelve su exit code.

    Args:
        test_paths: Tests seleccionados.
        cwd: Directorio de trabajo (raíz del repo).

    Returns:
        Exit code de pytest.

    Raises:
        RuntimeError: Si no se puede lanzar pytest (OSError).
    """
    try:
        result = subprocess.run(
            [sys.executable, "-m", "pytest", *(str(path) for path in test_paths)],
            cwd=cwd,
            check=False,
        )
    except OSError as exc:
        raise RuntimeError(f"no se pudo ejecutar pytest: {exc}") from exc
    return result.returncode


def parse_args(argv: list[str]) -> argparse.Namespace:
    """Construye y procesa los argumentos de la CLI.

    Args:
        argv: Argumentos (sin el nombre del programa).

    Returns:
        Namespace de argparse con files, base, dry_run, run y exit_code.
    """
    parser = argparse.ArgumentParser(
        prog="tdad_select",
        description="Selecciona los tests impactados por cambios (TDAD minimal, arXiv:2603.17973).",
    )
    parser.add_argument("files", nargs="*", help="Archivos modificados (alternativo a --base).")
    parser.add_argument(
        "--base",
        default=None,
        help="Ref git (ej. origin/main) para git diff --name-only.",
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--dry-run", action="store_true", help="Solo listar los tests (por defecto).")
    group.add_argument("--run", action="store_true", help="Ejecutar pytest sobre los tests seleccionados.")
    parser.add_argument(
        "--exit-code",
        action="store_true",
        help="Exit 1 si hay cambios sin tests seleccionados (conveniente para CI).",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Punto de entrada de la CLI: selecciona tests y opcionalmente los ejecuta.

    Args:
        argv: Argumentos de línea de comandos (None usa sys.argv[1:]).

    Returns:
        Exit code: 0 éxito, 1 sin tests con --exit-code, 2 error.
    """
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    args = parse_args(argv)
    try:
        modified = collect_modified_files(args.files, args.base, _REPO_ROOT)
    except ValueError as exc:
        _LOG.error("collect_modified_files: %s", exc)
        return _EXIT_ERROR
    if not modified:
        _LOG.info("no hay archivos modificados: nada que seleccionar")
        return _EXIT_OK
    deps, _known, _top = build_dependency_graph(_HARNESS_DIR, _TESTS_DIR)
    dependents = reverse_dependencies(deps)
    selected, warnings = select_tests(modified, dependents, _TESTS_DIR, _HARNESS_DIR)
    for warning in warnings:
        _LOG.warning("selección: %s", warning)
    for test_path in selected:
        print(test_path.relative_to(_REPO_ROOT))
    _LOG.info("tests impactados: %d de %d archivos modificados", len(selected), len(modified))
    if selected and args.run:
        try:
            return run_pytest(selected, _REPO_ROOT)
        except RuntimeError as exc:
            _LOG.error("run_pytest: %s", exc)
            return _EXIT_ERROR
    if args.exit_code and not selected:
        return _EXIT_NO_TESTS
    return _EXIT_OK


if __name__ == "__main__":
    sys.exit(main())