"""repomap.py — RepoMap con budget (repo-level understanding).

WHAT: mapa `path: kind name(sig)` del repo, rankeado por menciones y cortado
por presupuesto de tokens, con estadisticas de cobertura.
WHY: inyectar el repo crudo a un agente alimenta el loop de compactacion
(ADR-0092); la frontera (Aider repomap: cTags + ranking + budget) demuestra
que un mapa rankeado con techo rinde mas que el dump. Version minima honesta:
AST stdlib + conteo de menciones como proxy de PageRank, determinista.
WHERE: `context_injector`/orquestador antes de delegar a un builder; specs en
`specs/repomap.md`.
"""

from __future__ import annotations

import ast
import logging
import re
from dataclasses import dataclass
from pathlib import Path

#: Logger del modulo (avisos de archivos omitidos, nunca silencio).
LOGGER = logging.getLogger(__name__)

#: Tokens estimados por char (regla rapida del harness).
_CHARS_PER_TOKEN = 4
#: Presupuesto de tokens por defecto del mapa.
DEFAULT_BUDGET_TOKENS = 1000
#: Directorios que nunca entran al mapa.
SKIP_DIRS = frozenset({
    ".git", "__pycache__", ".venv", ".hypothesis", "node_modules",
    ".pytest_cache", ".mypy_cache", ".ruff_cache", ".ollama",
})


@dataclass(frozen=True)
class Symbol:
    """Simbolo extraido: clase o funcion con su firma.

    Attributes:
        kind: "class" o "def".
        name: Nombre del simbolo.
        signature: Args de la firma (vacio si no aplica).
        path: Archivo relativo donde vive.
    """

    kind: str
    name: str
    signature: str
    path: str


@dataclass(frozen=True)
class RepoMapStats:
    """Cobertura del mapa.

    Attributes:
        files: Archivos .py escaneados.
        symbols: Simbolos extraidos en total.
        kept: Lineas incluidas en el texto final.
        tokens: Tokens estimados del texto final.
    """

    files: int
    symbols: int
    kept: int
    tokens: int


@dataclass(frozen=True)
class RepoMap:
    """Mapa final + stats.

    Attributes:
        text: Lineas `path: kind name(sig)` dentro del budget.
        stats: Cobertura.
    """

    text: str
    stats: RepoMapStats


def _is_test_path(path: Path, root: Path) -> bool:
    """True si el archivo es test (`test_*.py` o bajo `tests/`)."""
    rel = path.relative_to(root).as_posix()
    return path.name.startswith("test_") or "/tests/" in f"/{rel}"


def _read_safe(path: Path) -> str:
    """Lee texto ignorando errores de encoding/IO, avisando de lo omitido.

    Args:
        path: Archivo a leer.

    Returns:
        Contenido del archivo, o cadena vacia si no es legible.
    """
    try:
        return path.read_text(encoding="utf-8", errors="ignore")
    except OSError as exc:
        LOGGER.warning("repomap: omitiendo %s: no legible (%s)", path, exc)
        return ""


def _to_symbol(node: ast.AST, label: str) -> Symbol:
    """Convierte un nodo AST de clase/funcion en `Symbol`.

    Args:
        node: Nodo `ClassDef`/`FunctionDef`/`AsyncFunctionDef`.
        label: Ruta relativa a reportar.

    Returns:
        Simbolo con kind/name/signature/path.
    """
    if isinstance(node, ast.ClassDef):
        return Symbol("class", node.name, "", label)
    name = getattr(node, "name", "")
    args = getattr(getattr(node, "args", None), "args", ())
    return Symbol("def", name, ", ".join(arg.arg for arg in args), label)


def extract_symbols(
    path: Path, rel: str | None = None, text: str | None = None
) -> list[Symbol]:
    """Extrae clases y funciones con firmas via AST (puro, sin ejecutar).

    Args:
        path: Archivo .py (si no es parseable se omite con aviso).
        rel: Ruta relativa a reportar (por defecto el nombre del archivo).
        text: Contenido ya leido; si se aporta, evita releer el archivo.

    Returns:
        Simbolos con kind/name/signature/path (vacio si no es parseable).
    """
    source = text if text is not None else _read_safe(path)
    if not source:
        return []
    try:
        tree = ast.parse(source)
    except (SyntaxError, ValueError) as exc:
        LOGGER.warning("repomap: omitiendo %s: no parseable (%s)", path, exc)
        return []
    label = rel if rel is not None else path.name
    kinds = (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)
    return [_to_symbol(node, label) for node in ast.walk(tree) if isinstance(node, kinds)]


def _py_files(root: Path, include_tests: bool) -> list[Path]:
    """Archivos .py del arbol, excluyendo ruido y (opcional) tests."""
    files: list[Path] = []
    for path in sorted(root.rglob("*.py")):
        if any(part in SKIP_DIRS for part in path.relative_to(root).parts):
            continue
        if not include_tests and _is_test_path(path, root):
            continue
        files.append(path)
    return files


def _collect(
    root: Path, files: list[Path]
) -> tuple[dict[str, list[Symbol]], dict[str, set[str]]]:
    """Lee cada archivo UNA vez y extrae simbolos + tokens del corpus.

    Args:
        root: Raiz del repo (para rutas relativas).
        files: Archivos a procesar.

    Returns:
        `(per_file, tokens_by_file)` indexados por ruta relativa.
    """
    per_file: dict[str, list[Symbol]] = {}
    tokens_by_file: dict[str, set[str]] = {}
    for path in files:
        rel = path.relative_to(root).as_posix()
        text = _read_safe(path)
        per_file[rel] = extract_symbols(path, rel, text=text)
        tokens_by_file[rel] = set(re.findall(r"[A-Za-z_]\w*", text))
    return per_file, tokens_by_file


def _rank(
    per_file: dict[str, list[Symbol]], files_by_token: dict[str, set[str]]
) -> list[tuple[int, str, Symbol]]:
    """Puntua cada simbolo por menciones en OTROS archivos (proxy PageRank).

    Args:
        per_file: Simbolos por archivo.
        files_by_token: Indice invertido token -> archivos que lo contienen.

    Returns:
        Lista `(score, rel, symbol)` con orden determinista.
    """
    scored: list[tuple[int, str, Symbol]] = []
    for rel, symbols in per_file.items():
        for symbol in symbols:
            mentions = len(files_by_token.get(symbol.name, frozenset()) - {rel})
            scored.append((-mentions, rel, symbol))
    scored.sort(key=lambda item: (item[0], item[1], item[2].name))
    return scored


def _render(scored: list[tuple[int, str, Symbol]], budget_tokens: int) -> list[str]:
    """Renderiza lineas `path: kind name(sig)` hasta agotar el presupuesto."""
    lines: list[str] = []
    used = 0
    for _, rel, symbol in scored:
        sig = f"({symbol.signature})" if symbol.signature else ""
        line = f"{rel}: {symbol.kind} {symbol.name}{sig}"
        cost = (len(line) + 1) // _CHARS_PER_TOKEN + 1
        if used + cost > budget_tokens:
            continue
        used += cost
        lines.append(line)
    return lines


def build_repomap(
    root: str | Path,
    budget_tokens: int = DEFAULT_BUDGET_TOKENS,
    include_tests: bool = False,
) -> RepoMap:
    """Construye el mapa rankeado dentro del presupuesto.

    Ranking: conteo de menciones del nombre en otros archivos (proxy de
    PageRank); desempate por (path, name) para determinismo. Complejidad
    O(total_chars + total_tokens + S log S): una sola lectura por archivo y
    un indice invertido token -> archivos.

    Args:
        root: Raiz del repo a mapear.
        budget_tokens: Techo de tokens estimados del texto.
        include_tests: Si True incluye tests en el mapa.

    Returns:
        RepoMap con texto y stats.
    """
    root = Path(root)
    files = _py_files(root, include_tests)
    per_file, tokens_by_file = _collect(root, files)
    files_by_token: dict[str, set[str]] = {}
    for rel, tokens in tokens_by_file.items():
        for token in tokens:
            files_by_token.setdefault(token, set()).add(rel)
    lines = _render(_rank(per_file, files_by_token), budget_tokens)
    text = "\n".join(lines)
    total = sum(len(symbols) for symbols in per_file.values())
    return RepoMap(
        text=text,
        stats=RepoMapStats(
            files=len(files), symbols=total, kept=len(lines),
            tokens=len(text) // _CHARS_PER_TOKEN,
        ),
    )
