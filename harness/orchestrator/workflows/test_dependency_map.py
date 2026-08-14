"""
test_dependency_map.py - Mapa de dependencias src<->tests (TDAD, arXiv 2603.17973).

Analiza via AST que tests importan cada archivo de src y produce un mapa que
se inyecta como contexto al agente: "si cambias X, corre estos tests".
Contexto > procedimiento: reduce regresiones ~70% al enfocar la verificacion
en los tests que realmente cubren el codigo modificado.

Uso:
    from harness.orchestrator.workflows.test_dependency_map import TestDependencyMap

    mapa = TestDependencyMap(root=".")
    for entry in mapa.build():
        print(entry.summary())
    print(mapa.render())
    print(mapa.coverage_stats())
    print(mapa.tests_for("harness/orchestrator/agent_bus.py"))
"""

from __future__ import annotations

import ast
import fnmatch
import logging
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constantes de descubrimiento y normalizacion
# ---------------------------------------------------------------------------

#: Patrones de nombre para archivos de test (test_*.py y *_test.py).
TEST_FILE_PATTERNS = ("test_*.py", "*_test.py")

#: Directorios que nunca se recorren como fuente (maquinaria o tests).
EXCLUDED_DIRS = frozenset({".venv", "venv", "__pycache__", "node_modules", ".git", "tests"})

#: Prefijos de paquete que se eliminan al normalizar nombres de modulo
#: para comparar imports de tests contra rutas de src (p.ej. "harness.").
IMPORT_PATTERNS = ("harness.",)


def _normalize_module_name(name: str) -> str:
    """Normaliza un nombre de modulo quitando prefijos de IMPORT_PATTERNS.

    Args:
        name: Nombre de modulo (p.ej. "harness.orchestrator.agent_bus").

    Returns:
        Nombre sin los prefijos de paquete (p.ej. "orchestrator.agent_bus").
    """
    normalized = name
    for pattern in IMPORT_PATTERNS:
        normalized = normalized.removeprefix(pattern)
    return normalized


def _module_matches(imported: str, wanted: str) -> bool:
    """True si un modulo importado coincide con el modulo buscado.

    La coincidencia acepta el modulo completo normalizado o cualquier sufijo
    con punto: "import harness.orchestrator.agent_bus" matchea "agent_bus".

    Args:
        imported: Nombre del modulo tal como aparece en el import.
        wanted: Nombre de modulo candidato del archivo src.

    Returns:
        True si imported y wanted refieren al mismo modulo.
    """
    norm_imported = _normalize_module_name(imported)
    norm_wanted = _normalize_module_name(wanted)
    return norm_imported == norm_wanted or norm_imported.endswith("." + norm_wanted)


# ---------------------------------------------------------------------------
# DependencyEntry
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class DependencyEntry:
    """Entrada del mapa: un archivo src y los tests que lo cubren.

    Attributes:
        src_path: Ruta del archivo fuente analizado.
        test_paths: Rutas de los tests que importan este src.
        imported_names: Simbolos que los tests importan desde el src.
    """

    src_path: str
    test_paths: tuple[str, ...]
    imported_names: tuple[str, ...]

    def summary(self) -> str:
        """Genera un resumen legible de la entrada para inyectar al agente.

        Returns:
            Cadena con la ruta src, los tests que la cubren y los simbolos
            importados (p.ej. "src/agent_bus.py cubierto por test_agent_bus.py").
        """
        tests = ", ".join(Path(test).name for test in self.test_paths)
        names = ", ".join(self.imported_names) or "(sin simbolos)"
        return f"{self.src_path} cubierto por {tests} (importa {names})"


# ---------------------------------------------------------------------------
# TestDependencyMap
# ---------------------------------------------------------------------------


class TestDependencyMap:
    """Mapa de dependencias src<->tests via AST para inyectar contexto.

    Uso:
        mapa = TestDependencyMap(root=".")
        mapa.build()
        print(mapa.render())
        print(mapa.coverage_stats())
        print(mapa.tests_for("src/agent_bus.py"))
    """

    #: Evita que pytest recolecte la clase como suite de tests.
    __test__ = False

    def __init__(self, root: str | Path) -> None:
        """
        Args:
            root: Directorio raiz del proyecto a analizar.
        """
        self.root = Path(root)
        self._entries: tuple[DependencyEntry, ...] | None = None
        self._ast_cache: dict[Path, ast.Module | None] = {}
        self._imports_cache: dict[Path, dict[str, set[str]]] = {}

    # ------------------------------------------------------------------
    # Descubrimiento de archivos
    # ------------------------------------------------------------------

    def _iter_python_files(self, directory: Path) -> tuple[Path, ...]:
        """Lista archivos .py de src, excluyendo tests y EXCLUDED_DIRS.

        Args:
            directory: Directorio a recorrer recursivamente.

        Returns:
            Tupla ordenada de rutas .py de src (los tests se listan aparte).
        """
        if not directory.exists():
            return ()
        files: list[Path] = []
        for path in directory.rglob("*.py"):
            if any(part in EXCLUDED_DIRS for part in path.parts):
                continue
            if any(fnmatch.fnmatch(path.name, pattern) for pattern in TEST_FILE_PATTERNS):
                continue
            files.append(path)
        return tuple(sorted(files))

    def _find_test_files(self) -> tuple[Path, ...]:
        """Encuentra tests (test_*.py / *_test.py) bajo root.

        Returns:
            Tupla ordenada de rutas de tests, excluyendo solo directorios de
            maquinaria (venv, __pycache__, ...). El directorio "tests" SI se
            recorre: es donde viven los tests.
        """
        if not self.root.exists():
            return ()
        excluded = EXCLUDED_DIRS - {"tests"}
        files: set[Path] = set()
        for pattern in TEST_FILE_PATTERNS:
            for path in self.root.rglob(pattern):
                if any(part in excluded for part in path.parts):
                    continue
                files.add(path)
        return tuple(sorted(files))

    # ------------------------------------------------------------------
    # Parseo de AST con cache y tolerancia a errores
    # ------------------------------------------------------------------

    def _read_ast(self, path: Path) -> ast.Module | None:
        """Lee y parsea el AST de un archivo, con cache y tolerancia.

        Args:
            path: Ruta del archivo .py a parsear.

        Returns:
            Nodo raiz del AST, o None si el archivo no existe o su sintaxis
            es invalida (se registra un warning sin abortar el analisis).
        """
        if path in self._ast_cache:
            return self._ast_cache[path]
        tree: ast.Module | None
        try:
            # utf-8-sig tolera archivos con BOM UTF-8 (U+FEFF) al inicio.
            source = path.read_text(encoding="utf-8-sig")
            tree = ast.parse(source, filename=str(path))
        except OSError as exc:
            logger.warning(
                "WHAT: No se pudo leer %s. "
                "WHY: %s. "
                "WHERE: TestDependencyMap._read_ast() en "
                "harness/orchestrator/workflows/test_dependency_map.py.",
                path, exc,
            )
            tree = None
        except SyntaxError as exc:
            logger.warning(
                "WHAT: AST invalido en %s. "
                "WHY: %s (linea %s). "
                "WHERE: TestDependencyMap._read_ast() en "
                "harness/orchestrator/workflows/test_dependency_map.py.",
                path, exc.msg, exc.lineno,
            )
            tree = None
        self._ast_cache[path] = tree
        return tree

    def _imports_map(self, path: Path) -> dict[str, set[str]]:
        """Mapea cada modulo importado del archivo a los nombres usados.

        Se cachea por ruta: cada archivo se recorre con ast.walk una sola vez
        aunque build() consulte multiples modulos sobre el mismo test.

        Args:
            path: Archivo .py a inspeccionar.

        Returns:
            Dict {modulo normalizado: conjunto de simbolos importados}. Vacio
            si el archivo no se pudo parsear.
        """
        if path in self._imports_cache:
            return self._imports_cache[path]
        tree = self._read_ast(path)
        if tree is None:
            self._imports_cache[path] = {}
            return {}
        imports: dict[str, set[str]] = {}
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    key = _normalize_module_name(alias.name)
                    imports.setdefault(key, set()).add(alias.asname or alias.name)
            elif isinstance(node, ast.ImportFrom) and node.module is not None:
                key = _normalize_module_name(node.module)
                names = imports.setdefault(key, set())
                for alias in node.names:
                    if alias.name != "*":
                        names.add(alias.asname or alias.name)
        self._imports_cache[path] = imports
        return imports

    def _imports_from(self, path: Path, module_name: str) -> set[str]:
        """Extrae los nombres importados de un modulo dado desde el AST.

        Args:
            path: Archivo (tipicamente de test) a inspeccionar.
            module_name: Nombre del modulo buscado (p.ej. "agent_bus").

        Returns:
            Conjunto de nombres importados: cubre "import x",
            "from x import y" y "from x.y import z". Vacio si el archivo no
            importa el modulo o no se pudo parsear.
        """
        wanted = _normalize_module_name(module_name)
        names: set[str] = set()
        for imported, symbols in self._imports_map(path).items():
            if _module_matches(imported, wanted):
                names.update(symbols)
        return names

    # ------------------------------------------------------------------
    # Construccion del mapa
    # ------------------------------------------------------------------

    def _module_aliases(self, src_path: Path) -> tuple[str, ...]:
        """Genera nombres de modulo candidatos para un archivo src.

        Args:
            src_path: Ruta del archivo fuente.

        Returns:
            Tupla ordenada de mas especifico a mas generico: ruta punteada
            completa, cada sufijo de la misma y el stem del archivo.
        """
        relative = src_path.relative_to(self.root)
        dotted = relative.with_suffix("").as_posix().replace("/", ".")
        normalized = _normalize_module_name(dotted)
        parts = normalized.split(".")
        aliases = [".".join(parts[index:]) for index in range(len(parts))]
        aliases.append(src_path.stem)
        return tuple(dict.fromkeys(aliases))

    def _imported_symbols(self, src_path: Path, test_path: Path) -> set[str]:
        """Simbolos que un test importa desde un src, usando alias candidatos.

        Args:
            src_path: Archivo fuente.
            test_path: Archivo de test.

        Returns:
            Conjunto de simbolos importados; vacio si el test no importa el src.
        """
        for alias in self._module_aliases(src_path):
            names = self._imports_from(test_path, alias)
            if names:
                return names
        return set()

    def build(self) -> tuple[DependencyEntry, ...]:
        """Analiza src y tests y genera las entradas con cobertura real.

        Para cada archivo src busca tests cuyo import coincida con alguno de
        sus nombres de modulo candidatos. Los src sin ningun test que los
        importe se omiten del mapa (no son testeables).

        Returns:
            Tupla ordenada por src_path de DependencyEntry con cobertura.
        """
        src_files = self._iter_python_files(self.root)
        test_files = self._find_test_files()
        entries: list[DependencyEntry] = []
        for src_path in src_files:
            covered_tests: list[tuple[Path, set[str]]] = []
            for test_path in test_files:
                imported_names = self._imported_symbols(src_path, test_path)
                if imported_names:
                    covered_tests.append((test_path, imported_names))
            if not covered_tests:
                continue
            covered_tests.sort(key=lambda item: item[0])
            entries.append(
                DependencyEntry(
                    src_path=str(src_path),
                    test_paths=tuple(str(test) for test, _ in covered_tests),
                    imported_names=tuple(
                        sorted(set().union(*(names for _, names in covered_tests)))
                    ),
                )
            )
        return tuple(sorted(entries, key=lambda entry: entry.src_path))

    def _map(self) -> tuple[DependencyEntry, ...]:
        """Devuelve el mapa construido, cacheandolo tras la primera llamada."""
        if self._entries is None:
            self._entries = self.build()
        return self._entries

    # ------------------------------------------------------------------
    # API publica
    # ------------------------------------------------------------------

    def tests_for(self, src_path: str) -> tuple[str, ...]:
        """Devuelve los tests que cubren un src dado (para inyectar al agente).

        Args:
            src_path: Ruta del archivo fuente consultado.

        Returns:
            Tupla de rutas de tests que cubren el src, o vacio si ninguno.

        Raises:
            FileNotFoundError: Si el archivo fuente no existe.
        """
        src = Path(src_path)
        if not src.exists():
            raise FileNotFoundError(
                "WHAT: El archivo fuente no existe: " + str(src_path) + ". "
                "WHY: tests_for() requiere una ruta valida de src para "
                "buscar los tests que la cubren. "
                "WHERE: TestDependencyMap.tests_for() en "
                "harness/orchestrator/workflows/test_dependency_map.py."
            )
        for entry in self._map():
            if Path(entry.src_path).absolute() == src.absolute():
                return entry.test_paths
        return ()

    def render(self) -> str:
        """Renderiza el mapa como texto markdown para el skill del agente.

        Returns:
            Tabla markdown "| src | tests |" con una fila por entrada en la
            forma "cambias X -> corre: test_a.py, test_b.py".
        """
        lines = ["| src | tests |", "|---|---|"]
        for entry in self._map():
            try:
                src_display = Path(entry.src_path).relative_to(self.root).as_posix()
            except ValueError:
                src_display = entry.src_path
            tests = ", ".join(Path(test).name for test in entry.test_paths)
            lines.append(f"| {src_display} | cambias {src_display} -> corre: {tests} |")
        return "\n".join(lines)

    def coverage_stats(self) -> dict[str, int]:
        """Metricas de cobertura del mapa de dependencias.

        Returns:
            Dict con total_src, src_with_tests, src_without_tests y total_tests.
        """
        total_src = len(self._iter_python_files(self.root))
        total_tests = len(self._find_test_files())
        src_with_tests = len(self._map())
        return {
            "total_src": total_src,
            "src_with_tests": src_with_tests,
            "src_without_tests": total_src - src_with_tests,
            "total_tests": total_tests,
        }
