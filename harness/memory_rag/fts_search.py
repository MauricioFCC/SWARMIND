"""
FTS Search — Full-text search sobre memoria (inspirado en FTS5 de Hermes Agent).

Hermes Agent usa SQLite FTS5 para busqueda full-text sobre todas las sesiones.
Nosotros implementamos una capa similar sobre LanceDB, con soporte para:
  - Tokenizacion basica (split + stemming ligero)
  - Ranking por frecuencia
  - Snippet generation

Cuando SQLite FTS5 esta disponible, se usa como backend preferido.
Si no, fallback a busqueda en memoria.

Usage:
    from harness.memory_rag.fts_search import FTSSearch

    fts = FTSSearch()
    fts.index_document("doc_id_1", "sistema de trading con Rust y Python")
    fts.index_document("doc_id_2", "arquitectura hexagonal en Go")
    results = fts.search("trading Rust")
    # -> [("doc_id_1", 0.85, "...sistema de **trading** con **Rust** y Python...")]
"""

from __future__ import annotations

import logging
import os
import re
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

FTS_DB_PATH = Path(__file__).resolve().parent.parent / "db" / "fts_search.db"
STOPWORDS = frozenset({
    "the", "a", "an", "is", "are", "was", "were", "be", "been", "being",
    "have", "has", "had", "do", "does", "did", "will", "would", "could",
    "should", "may", "might", "shall", "can", "to", "of", "in", "for",
    "on", "with", "at", "by", "from", "as", "into", "through", "during",
    "before", "after", "above", "below", "between", "out", "off", "over",
    "under", "again", "further", "then", "once", "here", "there", "when",
    "where", "why", "how", "all", "each", "every", "both", "few", "more",
    "most", "other", "some", "such", "no", "nor", "not", "only", "own",
    "same", "so", "than", "too", "very", "just", "because", "but", "and",
    "or", "if", "while", "about", "up", "it", "its", "this", "that",
    "these", "those", "i", "me", "my", "we", "you", "he", "she", "they",
    "him", "her", "his", "their", "them", "el", "la", "los", "las",
    "un", "una", "unas", "unos", "y", "e", "o", "u", "a", "ante",
    "bajo", "con", "contra", "de", "desde", "en", "entre", "hacia",
    "hasta", "para", "por", "segun", "sin", "sobre", "tras",
})


# ---------------------------------------------------------------------------
# FTSSearch
# ---------------------------------------------------------------------------


class FTSSearch:
    """
    Full-text search sobre documentos indexados.

    Usa SQLite FTS5 si esta disponible, con fallback a busqueda en memoria.

    Uso:
        fts = FTSSearch()
        fts.index("doc1", "Contenido del documento", {"domain": "trading"})
        fts.index("doc2", "Otro documento", {"domain": "web"})
        results = fts.search("contenido", top_k=5)
    """

    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = db_path or FTS_DB_PATH
        self._conn: Optional[sqlite3.Connection] = None
        self._fts_available = False
        self._mem_index: Dict[str, Tuple[str, Dict[str, Any]]] = {}  # doc_id -> (text, meta)

        self._init_storage()

    # ------------------------------------------------------------------
    # Initialization
    # ------------------------------------------------------------------

    def _init_storage(self) -> None:
        """Initialize SQLite FTS5 or fallback to memory."""
        # Try FTS5 first
        if self._init_sqlite_fts():
            return

        # Fallback in-memory
        logger.info("FTSSearch using in-memory index (FTS5 not available)")
        self._fts_available = False

    def _init_sqlite_fts(self) -> bool:
        """Initialize SQLite with FTS5 support."""
        try:
            os.makedirs(str(self.db_path.parent), exist_ok=True)

            self._conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
            self._conn.execute("PRAGMA journal_mode=WAL")

            # Try to create FTS5 table
            try:
                self._conn.execute(
                    "CREATE VIRTUAL TABLE IF NOT EXISTS documents_fts "
                    "USING fts5(id UNINDEXED, domain, content, tokenize='porter unicode61')"
                )
                self._conn.execute(
                    "CREATE TABLE IF NOT EXISTS doc_metadata "
                    "(id TEXT PRIMARY KEY, domain TEXT, source TEXT, "
                    "created_at TEXT, metadata TEXT)"
                )
                self._fts_available = True
                logger.info("FTSSearch initialized with SQLite FTS5 at %s", self.db_path)
                return True
            except sqlite3.OperationalError as exc:
                if "no such module" in str(exc) and "fts5" in str(exc):
                    logger.warning("FTS5 not available in this SQLite build")
                    return False
                raise
        except Exception as exc:
            logger.warning("FTS5 init failed: %s", exc)
            if self._conn:
                try:
                    self._conn.close()
                except Exception as _exc:
                    logger.warning("fts_search: %s", _exc)
                self._conn = None
            return False

    # ------------------------------------------------------------------
    # Indexing
    # ------------------------------------------------------------------

    def index(
        self,
        doc_id: str,
        content: str,
        metadata: Optional[Dict[str, Any]] = None,
        domain: str = "general",
    ) -> bool:
        """
        Indexa un documento para busqueda full-text.

        Args:
            doc_id: Identificador unico del documento.
            content: Contenido textual a indexar.
            metadata: Metadatos opcionales (dict).
            domain: Dominio del documento.

        Returns:
            True si se indexo correctamente.
        """
        meta = metadata or {}
        if self._fts_available and self._conn is not None:
            return self._index_fts(doc_id, content, domain, meta)
        return self._index_memory(doc_id, content, meta)

    def index_batch(
        self,
        documents: List[Tuple[str, str, Optional[Dict[str, Any]], str]],
    ) -> int:
        """
        Indexa multiples documentos en batch.

        Args:
            documents: Lista de (doc_id, content, metadata, domain).

        Returns:
            Numero de documentos indexados.
        """
        count = 0
        for doc_id, content, metadata, domain in documents:
            if self.index(doc_id, content, metadata, domain):
                count += 1
        return count

    def _index_fts(
        self, doc_id: str, content: str, domain: str, metadata: Dict[str, Any]
    ) -> bool:
        """Index using SQLite FTS5."""
        try:
            import json

            # Remove old entry if exists
            self._conn.execute("DELETE FROM documents_fts WHERE id = ?", (doc_id,))
            self._conn.execute("DELETE FROM doc_metadata WHERE id = ?", (doc_id,))

            # Insert FTS
            self._conn.execute(
                "INSERT INTO documents_fts (id, domain, content) VALUES (?, ?, ?)",
                (doc_id, domain, content),
            )
            # Insert metadata
            self._conn.execute(
                "INSERT INTO doc_metadata (id, domain, source, created_at, metadata) "
                "VALUES (?, ?, ?, ?, ?)",
                (
                    doc_id, domain,
                    metadata.get("source", ""),
                    metadata.get("created_at", ""),
                    json.dumps(metadata),
                ),
            )
            self._conn.commit()
            return True
        except Exception as exc:
            logger.warning("FTS index failed for %s: %s", doc_id, exc)
            return False

    def _index_memory(self, doc_id: str, content: str, metadata: Dict[str, Any]) -> bool:
        """Index in memory (fallback)."""
        self._mem_index[doc_id] = (content, metadata)
        return True

    # ------------------------------------------------------------------
    # Search
    # ------------------------------------------------------------------

    def search(
        self,
        query: str,
        top_k: int = 10,
        domain_filter: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Busca documentos por contenido full-text.

        Args:
            query: Texto a buscar.
            top_k: Maximo resultados.
            domain_filter: Filtrar por dominio.

        Returns:
            Lista de dicts con: id, score, snippet, metadata.
        """
        if self._fts_available and self._conn is not None:
            return self._search_fts(query, top_k, domain_filter)
        return self._search_memory(query, top_k, domain_filter)

    def _search_fts(
        self, query: str, top_k: int, domain_filter: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Search using SQLite FTS5."""
        try:
            # Sanitize FTS5 query
            safe_query = " OR ".join(
                f'"{w}"' for w in query.split() if len(w) > 2 and w.lower() not in STOPWORDS
            )
            if not safe_query:
                return []

            sql = """
                SELECT d.id, d.domain, d.content, 
                       rank as score, m.metadata
                FROM documents_fts d
                LEFT JOIN doc_metadata m ON d.id = m.id
                WHERE documents_fts MATCH ?
            """
            params: List[Any] = [safe_query]

            if domain_filter:
                sql += " AND d.domain = ?"
                params.append(domain_filter)

            sql += " ORDER BY rank LIMIT ?"
            params.append(top_k)

            cursor = self._conn.execute(sql, params)
            results = []
            import json

            for row in cursor.fetchall():
                meta = {}
                if row["metadata"]:
                    try:
                        meta = json.loads(row["metadata"])
                    except (json.JSONDecodeError, TypeError):
                        meta = {"raw": str(row["metadata"])}

                snippet = self._make_snippet(row["content"], query)

                results.append({
                    "id": row["id"],
                    "score": max(0.0, 1.0 - float(row["score"]) / 100.0),
                    "snippet": snippet,
                    "domain": row["domain"],
                    "metadata": meta,
                })

            return results

        except Exception as exc:
            logger.warning("FTS search failed: %s", exc)
            return []

    def _search_memory(
        self, query: str, top_k: int, domain_filter: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Search in memory (fallback using TF scoring)."""
        query_terms = set(
            w.lower() for w in query.split()
            if len(w) > 2 and w.lower() not in STOPWORDS
        )
        if not query_terms:
            return []

        scored: List[Tuple[str, float, str, Dict[str, Any]]] = []

        for doc_id, (content, metadata) in self._mem_index.items():
            if domain_filter and metadata.get("domain") != domain_filter:
                continue

            content_lower = content.lower()
            score = 0.0
            for term in query_terms:
                count = content_lower.count(term)
                if count > 0:
                    score += count * (1.0 / len(query_terms))

            if score > 0:
                snippet = self._make_snippet(content, query)
                scored.append((doc_id, score, snippet, metadata))

        # Sort by score descending
        scored.sort(key=lambda x: -x[1])

        return [
            {"id": doc_id, "score": score, "snippet": snippet, "metadata": meta}
            for doc_id, score, snippet, meta in scored[:top_k]
        ]

    # ------------------------------------------------------------------
    # Utility
    # ------------------------------------------------------------------

    def delete(self, doc_id: str) -> bool:
        """Delete a document from the index."""
        if self._fts_available and self._conn is not None:
            try:
                self._conn.execute("DELETE FROM documents_fts WHERE id = ?", (doc_id,))
                self._conn.execute("DELETE FROM doc_metadata WHERE id = ?", (doc_id,))
                self._conn.commit()
                return True
            except Exception as exc:
                logger.warning("FTS delete failed for %s: %s", doc_id, exc)
                return False
        else:
            return self._mem_index.pop(doc_id, None) is not None

    def clear(self) -> None:
        """Clear all indexed documents."""
        if self._fts_available and self._conn is not None:
            try:
                self._conn.execute("DELETE FROM documents_fts")
                self._conn.execute("DELETE FROM doc_metadata")
                self._conn.commit()
            except Exception as exc:
                logger.warning("FTS clear failed: %s", exc)
        else:
            self._mem_index.clear()

    def get_stats(self) -> Dict[str, Any]:
        """Get search index statistics."""
        if self._fts_available and self._conn is not None:
            try:
                count = self._conn.execute(
                    "SELECT COUNT(*) FROM documents_fts"
                ).fetchone()[0]
                return {
                    "backend": "fts5",
                    "document_count": count,
                    "db_path": str(self.db_path),
                }
            except Exception as _exc:
                logger.warning("fts_search: %s", _exc)

        return {
            "backend": "memory",
            "document_count": len(self._mem_index),
        }

    def close(self) -> None:
        """Close the database connection."""
        if self._conn is not None:
            try:
                self._conn.close()
            except Exception as _exc:
                logger.warning("fts_search: %s", _exc)
            self._conn = None

    # ------------------------------------------------------------------
    # Private
    # ------------------------------------------------------------------

    @staticmethod
    def _make_snippet(text: str, query: str, context_chars: int = 80) -> str:
        """
        Create a highlighted snippet around query matches.

        Similar a SQLite snippet() de FTS5.
        """
        if not text or not query:
            return text[:200] if text else ""

        query_terms = set(
            w.lower() for w in query.split()
            if len(w) > 2 and w.lower() not in STOPWORDS
        )

        text_lower = text.lower()

        # Find the first occurrence of any term
        best_pos = -1
        best_term = ""
        for term in query_terms:
            pos = text_lower.find(term)
            if pos != -1 and (best_pos == -1 or pos < best_pos):
                best_pos = pos
                best_term = term

        if best_pos == -1:
            return text[:200] + ("..." if len(text) > 200 else "")

        # Extract context around the match
        start = max(0, best_pos - context_chars)
        end = min(len(text), best_pos + context_chars)

        snippet = ""
        if start > 0:
            snippet += "..."

        snippet += text[start:end]

        if end < len(text):
            snippet += "..."

        # Bold the matched terms (using ** for markdown)
        for term in query_terms:
            snippet = re.sub(
                re.escape(term),
                f"**{term}**",
                snippet,
                flags=re.IGNORECASE,
            )

        return snippet


# Shorter alias for convenience
FTSSearchEngine = FTSSearch
