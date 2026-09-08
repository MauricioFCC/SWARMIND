"""llm_grep.py — Grep frontera para LLMs: ripgrep-first, 3 capas, budget-aware.

Orden frontera 2026 (ceaksan 2026-05-19, arXiv:2605.15184): LEXICAL
(ripgrep) primero, STRUCTURAL (ast-grep) si el patron es estructural,
SEMANTIC (HybridRetriever existente) solo como ultimo recurso. Salida
compaction-friendly: ``ruta:linea`` + 2 lineas de contexto, dedup por
``(ruta, linea)``, gitignore-aware via ``rg`` nativo.

Uso:
    grep = LlmGrep.lexical_only(root)
    hits, report = grep.search("def retrieve", top_k=20)
"""

from __future__ import annotations

import logging
import re
import shutil
import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

logger = logging.getLogger("harness.memory_rag.llm_grep")
# ---------------------------------------------------------------------------
# Constantes (MAG)
# ---------------------------------------------------------------------------
#: Lineas de contexto por hit (alineado con tool-result clearing Claude Code).
MAX_CONTEXT_LINES = 2
#: Caracteres maximos del preview por hit (compaction-friendly).
MAX_PREVIEW_CHARS = 300
#: Hits minimos para no escalar a la siguiente capa.
MIN_HITS_NO_ESCALATE = 1
#: Ratio semantico >20% sugiere misrouting (ceaksan: heuristica, no regla dura).
SEMANTIC_RATIO_WARN = 0.20
#: Timeout I/O para subprocesos rg/ast-grep.
SUBPROCESS_TIMEOUT_S = 30.0
#: Patrones que marcan una query como estructural.
STRUCTURAL_RE = re.compile(
    r"\b(def|class|fn|interface|struct|impl|trait|enum|async def)\b"
)


@dataclass(frozen=True)
class GrepHit:
    """Hit de busqueda en formato compaction-friendly.

    Attributes:
        path: Ruta del archivo (relativa a root si es posible).
        line: Numero de linea (1-based).
        col: Columna del match (1-based, 0 si desconocida).
        preview: Texto de la linea recortado a MAX_PREVIEW_CHARS.
    """

    path: str
    line: int
    col: int = 0
    preview: str = ""


@dataclass(frozen=True)
class GrepBudget:
    """Presupuesto de busqueda (Failure-Spend Governance).

    Attributes:
        max_hits: Maximo de hits a devolver.
        max_bytes: Maximo de bytes acumulados en previews.
    """

    max_hits: int = 50
    max_bytes: int = 20000


@dataclass(frozen=True)
class RouteReport:
    """Reporte de routing auditable (detecta misrouting semantico).

    Attributes:
        backend: Capa que resolvio (lexical|structural|semantic).
        hits: Numero de hits devueltos.
        lexical_hits: Hits de la capa lexical.
        semantic_ratio: Fraccion de queries resueltas por semantica (0..1).
        semantic_warning: True si semantic_ratio > SEMANTIC_RATIO_WARN.
    """

    backend: str
    hits: int
    lexical_hits: int = 0
    semantic_ratio: float = 0.0
    semantic_warning: bool = False


class LexicalBackend(Protocol):
    """Backend lexical (ripgrep)."""

    def search(self, pattern: str, root: Path, top_k: int) -> list[GrepHit]:
        """Busca patron literal/regex y retorna hits."""
        ...


class StructuralBackend(Protocol):
    """Backend estructural (ast-grep, opcional)."""

    def search(self, pattern: str, root: Path, top_k: int) -> list[GrepHit]:
        """Busca patron estructural y retorna hits."""
        ...


class SemanticBackend(Protocol):
    """Backend semantico (HybridRetriever existente)."""

    def search(self, query: str, top_k: int) -> list[GrepHit]:
        """Busca por concepto y retorna hits."""
        ...


def is_structural_query(query: str) -> bool:
    """Detecta si la query es estructural (definiciones de codigo).

    Args:
        query: Consulta del usuario.

    Returns:
        True si menciona construcciones estructurales.
    """
    return bool(STRUCTURAL_RE.search(query))


def dedup_hits(hits: list[GrepHit]) -> list[GrepHit]:
    """Elimina duplicados por (path, line) preservando orden.

    Args:
        hits: Hits crudos (posibles repetidos entre capas).

    Returns:
        Hits unicos en orden de primera aparicion.
    """
    seen: set[tuple[str, int]] = set()
    unique: list[GrepHit] = []
    for hit in hits:
        key = (hit.path, hit.line)
        if key not in seen:
            seen.add(key)
            unique.append(hit)
    return unique


def apply_budget(hits: list[GrepHit], budget: GrepBudget) -> list[GrepHit]:
    """Aplica el presupuesto max_hits/max_bytes a los hits.

    Args:
        hits: Hits deduplicados.
        budget: Presupuesto de la busqueda.

    Returns:
        Hits recortados al presupuesto.
    """
    capped = hits[: budget.max_hits]
    total = 0
    out: list[GrepHit] = []
    for hit in capped:
        total += len(hit.preview.encode("utf-8", errors="ignore"))
        if total > budget.max_bytes:
            break
        out.append(hit)
    return out


def _parse_vimgrep_line(line: str, root: Path) -> GrepHit | None:
    """Parsea una linea ``--vimgrep`` (path:line:col:text).

    Args:
        line: Linea cruda de rg.
        root: Raiz para relativizar rutas.

    Returns:
        GrepHit o None si la linea no parsea.
    """
    parts = line.split(":", 3)
    if len(parts) < 4:
        return None
    raw_path, raw_line, raw_col, text = parts
    try:
        line_no = int(raw_line)
        col_no = int(raw_col)
    except ValueError:
        return None
    try:
        rel = str(Path(raw_path).relative_to(root))
    except ValueError:
        rel = raw_path
    preview = " ".join(text.split())[:MAX_PREVIEW_CHARS]
    return GrepHit(path=rel, line=line_no, col=col_no, preview=preview)


class RipgrepBackend:
    """Backend lexical con binario ``rg`` (gitignore-aware nativo).

    Args:
        timeout_s: Timeout del subproceso.
    """

    def __init__(self, timeout_s: float = SUBPROCESS_TIMEOUT_S) -> None:
        self._timeout_s = timeout_s

    def search(self, pattern: str, root: Path, top_k: int) -> list[GrepHit]:
        """Ejecuta ``rg --vimgrep`` y parsea hits (max top_k).

        Args:
            pattern: Patron regex/literal.
            root: Directorio raiz de busqueda.
            top_k: Maximo de hits a parsear.

        Returns:
            Hits lexicales (vacio si rg no encuentra).

        Raises:
            ValueError: Si el patron esta vacio o top_k no es positivo.
            FileNotFoundError: Si ``rg`` no esta instalado.
        """
        if not pattern.strip():
            raise ValueError(
                "WHAT: patron de busqueda vacio"
                "WHY: ripgrep necesita un patron no vacio"
                "WHERE: RipgrepBackend.search()"
            )
        if top_k <= 0:
            raise ValueError(
                f"WHAT: top_k invalido: {top_k}"
                f"WHY: debe ser entero positivo"
                f"WHERE: RipgrepBackend.search()"
            )
        rg_bin = shutil.which("rg")
        if rg_bin is None:
            raise FileNotFoundError(
                "WHAT: binario 'rg' (ripgrep) no encontrado en PATH"
                "WHY: la capa lexical lo requiere; instalar desde "
                "https://github.com/BurntSushi/ripgrep"
                "WHERE: RipgrepBackend.search()"
            )
        proc = subprocess.run(
            [rg_bin, "--vimgrep", "--no-heading", "-m", str(top_k), "-e", pattern, "."],
            cwd=str(root),
            capture_output=True,
            text=True,
            timeout=self._timeout_s,
            check=False,
        )
        hits: list[GrepHit] = []
        for raw in proc.stdout.splitlines()[:top_k]:
            hit = _parse_vimgrep_line(raw, root)
            if hit is not None:
                hits.append(hit)
        return hits


class NoopStructuralBackend:
    """Backend estructural no-op (sin binario ast-grep)."""

    def search(self, pattern: str, root: Path, top_k: int) -> list[GrepHit]:
        """Retorna vacio documentando la ausencia del binario.

        Args:
            pattern: Patron (ignorado).
            root: Raiz (ignorada).
            top_k: Maximo (ignorado).

        Returns:
            Lista vacia siempre.
        """
        return []


class TgrepBackend:
    """Backend trigram-indexado opcional (Microsoft tgrep, Rust).

    WHAT: Delega a ``tgrep`` si el binario esta disponible (indice
    trigram + watcher; Microsoft Copilot CLI lo usa internamente).
    WHY: Frontera 2026 — busqueda de codigo 50%+ mas rapida que grep
    en codebases grandes; complementa a rg (indiced una vez).
    WHERE: Capa structural/lexical alternativa cuando el indice existe.

    Args:
        timeout_s: Timeout del subproceso.
    """

    def __init__(self, timeout_s: float = SUBPROCESS_TIMEOUT_S) -> None:
        self._timeout_s = timeout_s

    def search(self, pattern: str, root: Path, top_k: int) -> list[GrepHit]:
        """Ejecuta ``tgrep -n`` y parsea hits (max top_k).

        Args:
            pattern: Patron regex/literal.
            root: Raiz de busqueda.
            top_k: Maximo de hits.

        Returns:
            Hits parseados (vacio si tgrep no esta instalado o no matchea).

        Raises:
            ValueError: Si el patron esta vacio o top_k no es positivo.
        """
        if not pattern.strip():
            raise ValueError(
                "WHAT: patron de busqueda vacio"
                "WHY: tgrep necesita un patron no vacio"
                "WHERE: TgrepBackend.search()"
            )
        if top_k <= 0:
            raise ValueError(
                f"WHAT: top_k invalido: {top_k}"
                f"WHY: debe ser entero positivo"
                f"WHERE: TgrepBackend.search()"
            )
        tgrep_bin = shutil.which("tgrep")
        if tgrep_bin is None:
            logger.info(
                "llm_grep: binario 'tgrep' no disponible; backend no-op "
                "(instalar desde https://github.com/microsoft/tgrep)"
            )
            return []
        proc = subprocess.run(
            [tgrep_bin, "-n", "-m", str(top_k), pattern, "."],
            cwd=str(root),
            capture_output=True,
            text=True,
            timeout=self._timeout_s,
            check=False,
        )
        hits: list[GrepHit] = []
        for raw in proc.stdout.splitlines()[:top_k]:
            hit = _parse_vimgrep_line(raw, root) if ":" in raw else None
            if hit is None:
                # Formato path:line:text sin columna -> col=0
                parts = raw.split(":", 2)
                if len(parts) == 3 and parts[1].isdigit():
                    hits.append(GrepHit(
                        path=parts[0], line=int(parts[1]), col=0,
                        preview=" ".join(parts[2].split())[:MAX_PREVIEW_CHARS],
                    ))
            else:
                hits.append(hit)
        return hits


def hybrid_to_hits_adapter(
    retrieve_fn: Callable[[str, int], list[dict]],
) -> SemanticBackend:
    """Adapta ``HybridRetriever.retrieve`` al protocolo semantico.

    Args:
        retrieve_fn: Funcion (query, top_k) -> items con 'id'/'metadata'.

    Returns:
        Backend semantico que emite GrepHits.
    """

    class _Adapter:
        def search(self, query: str, top_k: int) -> list[GrepHit]:
            """Delega al retriever hibrido y normaliza a GrepHit."""
            items = retrieve_fn(query, top_k)
            hits: list[GrepHit] = []
            for item in items:
                meta = item.get("metadata", {}) or {}
                path = str(meta.get("path", item.get("id", "")))
                preview = str(meta.get("preview", ""))[:MAX_PREVIEW_CHARS]
                hits.append(GrepHit(path=path, line=0, preview=preview))
            return hits

    return _Adapter()


class LlmGrep:
    """Orquestador ripgrep-first con 3 capas y budget governance.

    Args:
        root: Raiz de busqueda para capas lexical/estructural.
        lexical: Backend lexical (default RipgrepBackend).
        structural: Backend estructural (default no-op).
        semantic: Backend semantico opcional (ultimo recurso).
        budget: Presupuesto de hits/bytes.
    """

    def __init__(
        self,
        root: Path,
        lexical: LexicalBackend | None = None,
        structural: StructuralBackend | None = None,
        semantic: SemanticBackend | None = None,
        budget: GrepBudget | None = None,
    ) -> None:
        self._root = root
        self._lexical = lexical or RipgrepBackend()
        self._structural = structural or NoopStructuralBackend()
        self._semantic = semantic
        self._budget = budget or GrepBudget()
        self._semantic_uses = 0
        self._total_searches = 0

    @classmethod
    def lexical_only(cls, root: Path, budget: GrepBudget | None = None) -> LlmGrep:
        """Fabrica solo-lexical (sin dependencias semanticas).

        Args:
            root: Raiz de busqueda.
            budget: Presupuesto opcional.

        Returns:
            Instancia sin backend semantico.
        """
        return cls(root=root, semantic=None, budget=budget)

    def search(self, query: str, top_k: int = 20) -> tuple[list[GrepHit], RouteReport]:
        """Busca con escalado lexical→estructural→semantico.

        Args:
            query: Patron o pregunta conceptual.
            top_k: Maximo de hits deseados.

        Returns:
            Tupla (hits con budget aplicado, reporte de routing).

        Raises:
            ValueError: Si la query esta vacia o top_k no es positivo.
        """
        if not query.strip():
            raise ValueError(
                "WHAT: query vacia"
                "WHY: se necesita patron o pregunta para buscar"
                "WHERE: LlmGrep.search()"
            )
        if top_k <= 0:
            raise ValueError(
                f"WHAT: top_k invalido: {top_k}"
                f"WHY: debe ser entero positivo"
                f"WHERE: LlmGrep.search()"
            )
        self._total_searches += 1
        lexical_hits = self._lexical.search(query, self._root, top_k)
        if len(lexical_hits) >= MIN_HITS_NO_ESCALATE:
            return self._finalize(lexical_hits, "lexical", len(lexical_hits))
        if is_structural_query(query):
            structural_hits = self._structural.search(query, self._root, top_k)
            if structural_hits:
                return self._finalize(structural_hits, "structural", len(lexical_hits))
        if self._semantic is not None:
            self._semantic_uses += 1
            semantic_hits = self._semantic.search(query, top_k)
            return self._finalize(semantic_hits, "semantic", len(lexical_hits))
        return self._finalize(lexical_hits, "lexical", len(lexical_hits))

    def _finalize(
        self, hits: list[GrepHit], backend: str, lexical_hits: int
    ) -> tuple[list[GrepHit], RouteReport]:
        """Aplica dedup+budget y construye el reporte de routing.

        Args:
            hits: Hits crudos de la capa ganadora.
            backend: Nombre de la capa ganadora.
            lexical_hits: Hits que dio la capa lexical.

        Returns:
            Tupla (hits finales, reporte).
        """
        final = apply_budget(dedup_hits(hits), self._budget)
        ratio = self._semantic_uses / max(self._total_searches, 1)
        report = RouteReport(
            backend=backend,
            hits=len(final),
            lexical_hits=lexical_hits,
            semantic_ratio=ratio,
            semantic_warning=ratio > SEMANTIC_RATIO_WARN,
        )
        return final, report
