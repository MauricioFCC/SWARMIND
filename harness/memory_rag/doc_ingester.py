"""
Document chunker and ingester for RAG pipelines.
Reads .md/.py files, chunks into 20-30 line blocks, auto-tags metadata,
vectorizes, and inserts into LanceVectorStore rag_chunks collection.
"""
from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

from harness.common import fallback_embedding
from harness.memory_rag.doc_converter import (
    DOC_EXTENSIONS,
    AnyDocConverter,
    DocumentConversionError,
    DocumentConverter,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Domain / tipo_doc auto-detection patterns
# ---------------------------------------------------------------------------

DOMAIN_PATTERNS: list[tuple[str, str]] = [
    (r"docs[/\\\\]dominios_negocio[/\\\\](.*?)\..*", lambda m: _slug(m.group(1))),
    (r"docs[/\\\\]arquitectura[/\\\\]", "arquitectura"),
    (r"docs[/\\\\]manual_usuario[/\\\\]", "manual_usuario"),
    (r"harness[/\\\\]orchestrator[/\\\\]", "orquestacion"),
    (r"harness[/\\\\]memory_rag[/\\\\]", "memoria_rag"),
    (r"harness[/\\\\]evolve_loop[/\\\\]", "evolucion"),
    (r"harness[/\\\\]tools_sandbox[/\\\\]", "sandbox"),
    (r"\.opencode[/\\\\]agents[/\\\\]", "agentes"),
    (r"\.opencode[/\\\\]skills[/\\\\]", "skills"),
    (r"\.opencode[/\\\\]core[/\\\\]", "core"),
    (r"\.opencode[/\\\\]config[/\\\\]", "configuracion"),
]

TIPO_DOC_PATTERNS: list[tuple[str, str]] = [
    (r"(adr|architecture decision record)", "adr"),
    (r"(schema|tabla|columna|base de datos|entidad)", "esquema_bd"),
    (r"(api|endpoint|ruta|route|http)", "api_endpoint"),
    (r"(regla|rule|norma|debe|must|requisito)", "regla_negocio"),
    (r"(interfaz|ui|componente|pantalla|widget)", "interfaz_ui"),
    (r"(test|prueba|spec|assert)", "test"),
    (r"(clase|class|def |funcion|metodo)", "codigo_fuente"),
    (r"(config|configuracion|setting|yml|yaml|json)", "configuracion"),
]

DEFAULT_TIPO_DOC = "documentacion"
DEFAULT_DOMAIN = "general"

_EXTENSION_TIPO: dict[str, str] = {
    ".py": "codigo_fuente",
    ".md": "documentacion",
    ".yml": "configuracion",
    ".yaml": "configuracion",
    ".json": "configuracion",
    # Documentos binarios convertidos a Markdown (firecrawl-anydoc)
    ".pdf": "documento",
    ".doc": "documento",
    ".docx": "documento",
    ".docm": "documento",
    ".odt": "documento",
    ".rtf": "documento",
    ".epub": "documento",
    ".ppt": "presentacion",
    ".pps": "presentacion",
    ".pot": "presentacion",
    ".pptx": "presentacion",
    ".pptm": "presentacion",
    ".ppsx": "presentacion",
    ".ppsm": "presentacion",
    ".odp": "presentacion",
    ".xls": "hoja_calculo",
    ".xlsx": "hoja_calculo",
    ".xlsm": "hoja_calculo",
    ".xlsb": "hoja_calculo",
    ".ods": "hoja_calculo",
    ".csv": "datos_tabulares",
}


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9_]", "_", text.lower().strip())


@dataclass
class Chunk:
    """Chunk."""
    text: str
    source_file: str
    start_line: int
    end_line: int
    domain: str = ""
    tipo_doc: str = ""
    tags: list[str] = field(default_factory=list)
    vector: np.ndarray | None = None

    def to_metadata(self) -> dict[str, Any]:
        """To metadata."""
        return {
            "source_file": self.source_file,
            "start_line": self.start_line,
            "end_line": self.end_line,
            "domain": self.domain,
            "tipo_doc": self.tipo_doc,
            "tags": self.tags,
        }


class DocumentChunker:
    """
    Splits text files into overlapping chunks of configurable size.
    """

    def __init__(
        self,
        chunk_size: int = 25,
        overlap: int = 3,
        embedding_fn=None,
        converter: DocumentConverter | None = None,
    ) -> None:
        """
        Inicializa el chunker con tamano de chunk y solapamiento.

        Args:
            chunk_size: Lineas por chunk (default 25).
            overlap: Solapamiento de lineas entre chunks (default 3).
            embedding_fn: Funcion de embedding para chunk_and_vectorize.
            converter: Convertidor binario->Markdown (DIP). Si None, se usa
                AnyDocConverter solo si firecrawl-anydoc esta instalado.
        """
        self.chunk_size = chunk_size
        self.overlap = overlap
        self._embedding_fn = embedding_fn or self._default_embedding
        self.converter: DocumentConverter | None = converter
        if self.converter is None:
            candidate = AnyDocConverter()
            if candidate.is_available():
                self.converter = candidate

    def chunk_file(self, filepath: str) -> list[Chunk]:
        """
        Read a file and split it into chunks.
        Returns list of Chunk objects with auto-detected metadata.

        Args:
            filepath: Ruta del archivo a trocear (texto o documento binario).

        Returns:
            Lista de Chunk; vacia si el archivo no existe, no se puede leer,
            o es binario sin converter disponible / conversion fallida.
        """
        path = Path(filepath)
        if not path.is_file():
            logger.warning("File not found: %s", filepath)
            return []

        ext = path.suffix.lower()
        tipo_doc = _EXTENSION_TIPO.get(ext, DEFAULT_TIPO_DOC)
        domain = self._detect_domain(str(path))
        tags = [domain, tipo_doc]

        lines = self._read_lines(path, ext)
        if not lines:
            return []
        return self._chunk_lines(lines, str(path), tipo_doc, domain, tags)

    def _read_lines(self, path: Path, ext: str) -> list[str]:
        """Lee lineas del archivo, convirtiendo binarios a Markdown si aplica.

        Args:
            path: Ruta del archivo.
            ext: Extension en minusculas (ej. ``.pdf``).

        Returns:
            Lista de lineas (con saltos conservados); vacia si la lectura o
            la conversion fallan, o si es binario sin converter disponible.
        """
        if ext in DOC_EXTENSIONS:
            converter = self.converter
            if converter is None:
                logger.warning(
                    "Documento binario sin converter disponible, skip: %s", path
                )
                return []
            text = self._convert_binary(path, converter)
            if text is None:
                return []
            return text.splitlines(keepends=True)

        try:
            with open(path, encoding="utf-8") as f:
                return f.readlines()
        except Exception as exc:  # noqa: BLE001
            logger.warning("Cannot read %s: %s", path, exc)
            return []

    @staticmethod
    def _convert_binary(path: Path, converter: DocumentConverter) -> str | None:
        """Convierte un documento binario a Markdown, logueando fallos.

        Args:
            path: Ruta del documento binario.
            converter: Convertidor inyectado (AnyDocConverter o mock).

        Returns:
            Texto Markdown convertido, o None si la conversion fallo.
        """
        try:
            text = converter.convert(path)
        except DocumentConversionError as exc:
            logger.warning("Conversion fallida: %s", exc)
            return None
        except Exception as exc:  # noqa: BLE001
            logger.warning("Conversion inesperada de %s: %s", path, exc)
            return None
        if not isinstance(text, str):
            logger.warning("Conversion devolvio tipo invalido para %s", path)
            return None
        return text

    def _chunk_lines(
        self,
        lines: list[str],
        source_file: str,
        tipo_doc: str,
        domain: str,
        tags: list[str],
    ) -> list[Chunk]:
        """Trocea lineas en chunks solapados con metadatos auto-detectados.

        Args:
            lines: Lineas del documento (texto o Markdown convertido).
            source_file: Ruta original del archivo.
            tipo_doc: Tipo de documento por extension.
            domain: Dominio detectado por ruta.
            tags: Tags base (domain + tipo_doc).

        Returns:
            Lista de Chunk resultantes.
        """
        chunks: list[Chunk] = []
        num_lines = len(lines)
        i = 0
        while i < num_lines:
            end = min(i + self.chunk_size, num_lines)
            chunk_text = "".join(lines[i:end]).strip()
            if not chunk_text:
                i += self.chunk_size - self.overlap
                continue

            # Refine tipo_doc from content
            content_tipo = self._detect_tipo_doc(chunk_text)
            effective_tipo = content_tipo if content_tipo != DEFAULT_TIPO_DOC else tipo_doc

            chunks.append(
                Chunk(
                    text=chunk_text,
                    source_file=source_file,
                    start_line=i + 1,
                    end_line=end,
                    domain=domain,
                    tipo_doc=effective_tipo,
                    tags=list(set(tags + [effective_tipo])),
                )
            )
            i += self.chunk_size - self.overlap

        return chunks

    def chunk_and_vectorize(self, filepath: str) -> list[Chunk]:
        """Chunk a file and compute embeddings for each chunk."""
        chunks = self.chunk_file(filepath)
        for chunk in chunks:
            chunk.vector = self._embedding_fn(chunk.text)
        return chunks

    @staticmethod
    def _detect_domain(filepath: str) -> str:
        for pattern, result in DOMAIN_PATTERNS:
            m = re.search(pattern, filepath, re.IGNORECASE)
            if m:
                return result(m) if callable(result) else result
        return DEFAULT_DOMAIN

    @staticmethod
    def _detect_tipo_doc(text: str) -> str:
        text_lower = text.lower()[:2000]
        for pattern, tipo in TIPO_DOC_PATTERNS:
            if re.search(pattern, text_lower):
                return tipo
        return DEFAULT_TIPO_DOC

    @staticmethod
    def _default_embedding(text: str) -> np.ndarray:
        """Delega en harness.common.fallback_embedding."""
        return fallback_embedding(text)


def _ensure_lancedb() -> None:
    """Verify LanceDB is available before ingesting documents."""
    try:
        import lancedb  # noqa: F401
    except ImportError:
        logger.info("=" * 60)
        logger.info("  LanceDB REQUERIDO para ingestion de documentos.")
        logger.info("=" * 60)
        logger.info()
        logger.info("  Ejecuta:  pip install lancedb")
        logger.info("  O bien:   python harness/scripts/init.py")
        logger.info("=" * 60)
        raise ImportError(
            "LanceDB no instalado. Es requerido para ingest_directory()."
        )


def ingest_directory(
    store,
    root_dirs: list[str],
    chunker: DocumentChunker | None = None,
) -> dict[str, int]:
    """
    Ingest all .md and .py files from directories into rag_chunks.

    Args:
        store: LanceVectorStore instance.
        root_dirs: List of directory paths relative to project root.
        chunker: DocumentChunker instance (default creates one).

    Returns:
        Dict with keys: files_processed, chunks_inserted, errors.
    """
    _ensure_lancedb()
    if chunker is None:
        chunker = DocumentChunker()

    project_root = Path(__file__).parent.parent.parent  # harness/memory_rag/ -> project root
    stats = {"files_processed": 0, "chunks_inserted": 0, "errors": 0}

    for rel_dir in root_dirs:
        abs_dir = project_root / rel_dir
        if not abs_dir.is_dir():
            logger.warning("Directory not found: %s", abs_dir)
            continue

        for fpath in sorted(abs_dir.rglob("*")):
            if fpath.suffix.lower() not in (".md", ".py"):
                continue
            if fpath.name == ".gitkeep":
                continue

            try:
                chunks = chunker.chunk_and_vectorize(str(fpath))
                stats["files_processed"] += 1

                if not chunks:
                    continue

                vectors = np.array([c.vector for c in chunks if c.vector is not None])
                metadata_list = [c.to_metadata() for c in chunks if c.vector is not None]

                if vectors.size == 0:
                    continue

                store.insert("rag_chunks", vectors, metadata_list)
                stats["chunks_inserted"] += len(chunks)

            except Exception as exc:  # noqa: BLE001
                logger.error("Error processing %s: %s", fpath, exc)
                stats["errors"] += 1

    return stats


# ---------------------------------------------------------------------------
# High-level convenience: scan a directory tree and ingest everything
# ---------------------------------------------------------------------------

# Source file extensions recognised for RAG ingestion.
# DOC_EXTENSIONS se incluyen: sin converter el chunker las omite con warning
# (no rompe el pipeline); con firecrawl-anydoc se convierten a Markdown.
RAG_EXTENSIONS: set = {
    ".py", ".rs", ".go", ".ts", ".tsx", ".js", ".jsx",
    ".md", ".yaml", ".yml", ".toml", ".json", ".sql",
} | set(DOC_EXTENSIONS)

# Directories always excluded from ingestion
# (harness/ y .opencode/ se ingieren por separado; el scan automatico los omite)
RAG_EXCLUDE: set = {
    "node_modules", "target", ".git", "__pycache__",
    ".venv", "venv", "env", ".env", "dist", "build",
    "harness",  # ya ingerido por el sistema
}


def ingest_project_directory(
    directory: str,
    extensions: set | None = None,
    exclude_dirs: set | None = None,
    chunk_size: int = 25,
    overlap: int = 3,
    show_progress: bool = True,
    include_docs: bool = False,
) -> dict[str, Any]:
    """
    High-level convenience: scan *directory* recursively, chunk every
    relevant source file, vectorise, and insert into the ``rag_chunks``
    LanceDB collection.

    Creates its own ``LanceVectorStore`` and ``DocumentChunker``, so the
    caller does not need to manage infrastructure.

    Args:
        directory: Root path of the project to scan.
        extensions: Set of file extensions to include (default: RAG_EXTENSIONS).
        exclude_dirs: Set of directory *names* to skip (default: RAG_EXCLUDE).
        chunk_size: Lines per chunk (default 25).
        overlap: Line overlap between consecutive chunks (default 3).
        show_progress: Log per-file progress (default True).
        include_docs: Anade DOC_EXTENSIONS (binarios -> Markdown) al scan.

    Returns:
        Dict with keys: files_processed, chunks_inserted, errors, elapsed_s.
    """
    _ensure_lancedb()

    exts = set(extensions or RAG_EXTENSIONS)
    if include_docs:
        exts |= set(DOC_EXTENSIONS)
    skip_dirs = exclude_dirs or RAG_EXCLUDE

    root = Path(directory).resolve()
    if not root.is_dir():
        raise NotADirectoryError(f"Directory not found: {root}")

    from harness.memory_rag.lance_vector_store import LanceVectorStore

    store = LanceVectorStore()
    chunker = DocumentChunker(chunk_size=chunk_size, overlap=overlap)

    stats: dict[str, Any] = {
        "files_processed": 0,
        "chunks_inserted": 0,
        "errors": 0,
    }
    start = time.time()

    # Collect all matching files, excluding skip_dirs
    files: list[Path] = []
    for fpath in sorted(root.rglob("*")):
        # Skip excluded directories
        if any(part in skip_dirs for part in fpath.parts):
            continue
        # Skip hidden files / dirs
        if any(part.startswith(".") for part in fpath.parts):
            continue
        if not fpath.is_file():
            continue
        if fpath.suffix.lower() not in exts:
            continue
        if fpath.name == ".gitkeep":
            continue
        files.append(fpath)

    if not files:
        logger.info("  No se encontraron archivos fuente para ingerir.")
        stats["elapsed_s"] = time.time() - start
        return stats

    total = len(files)
    for idx, fpath in enumerate(files, start=1):
        try:
            chunks = chunker.chunk_and_vectorize(str(fpath))
            stats["files_processed"] += 1

            if not chunks:
                continue

            vectors = np.array([c.vector for c in chunks if c.vector is not None])
            metadata_list = [c.to_metadata() for c in chunks if c.vector is not None]

            if vectors.size == 0:
                continue

            store.insert("rag_chunks", vectors, metadata_list)
            stats["chunks_inserted"] += len(chunks)

            if show_progress:
                logger.info(
                    "  [%d/%d] %s → chunk %d",
                    idx, total,
                    _relpath(fpath, root),
                    stats["chunks_inserted"],
                )

        except Exception as exc:  # noqa: BLE001
            logger.error("  Error processing %s: %s", fpath, exc)
            stats["errors"] += 1

    stats["elapsed_s"] = round(time.time() - start, 2)
    return stats


def _relpath(path: Path, anchor: Path) -> str:
    """Return a short relative path string for display."""
    try:
        return str(path.relative_to(anchor))
    except ValueError:
        return path.name


if __name__ == "__main__":
    import sys
    sys.path.insert(1, str(Path(__file__).parent.parent.parent))

    from harness.memory_rag.lance_vector_store import LanceVectorStore

    store = LanceVectorStore()
    chunker = DocumentChunker(chunk_size=25, overlap=3)

    dirs_to_scan = ["docs", "harness", ".opencode"]
    logger.info(f"Ingestando documentos desde: {dirs_to_scan}")
    stats = ingest_directory(store, dirs_to_scan, chunker)
    logger.info(f"Resultados: {stats}")
