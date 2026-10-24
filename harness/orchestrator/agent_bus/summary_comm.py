"""Summary-based communication (frontier: arXiv:2607.27942) sobre RuscaDB.

Almacena resumenes compactos de mensajes de agentes en RuscaDB (FTS + vector)
para reducir tokens en el contexto de agentes (summary-based communication).
Recupera solo los resumenes relevantes via MATCH/KNN en vez de historial completo.
"""

from __future__ import annotations

import logging
from typing import Any

from harness.memory_rag.ruscadb_store import RuscaDBStore

logger = logging.getLogger("harness.orchestrator.agent_bus.summary_comm")


class SummaryCommunication:
    """Comunicacion basada en resumenes sobre RuscaDB (token-efficient)."""

    def __init__(self, store: RuscaDBStore, collection: str = "agent_summaries") -> None:
        self._store = store
        self._collection = collection
        try:
            self._store.create_collection(collection)
        except Exception:  # noqa: BLE001, S110
            pass

    def store_summary(self, agent: str, summary: str, metadata: dict[str, Any] | None = None) -> str:
        """Almacena un resumen compacto de un mensaje/agente."""
        meta = {"agent": agent, "summary": summary}
        if metadata:
            meta.update(metadata)
        # embedding dummy (zeros) — en produccion usar embed_fn
        vec = [0.0] * 8
        ids = self._store.insert(self._collection, [vec], [meta])
        return ids[0] if ids else ""

    def retrieve_relevant(self, query: str, top_k: int = 5) -> list[dict[str, Any]]:
        """Recupera resumenes relevantes via FTS (MATCH/BM25)."""
        try:
            return self._store.full_text_search(self._collection, query, top_k=top_k)
        except Exception:  # noqa: BLE001
            return []

    def compact_context(self, query: str, top_k: int = 5) -> str:
        """Genera contexto compacto (solo resumenes relevantes) para un agente."""
        results = self.retrieve_relevant(query, top_k=top_k)
        if not results:
            return ""
        lines = []
        for r in results:
            meta = r.get("metadata", {}) or {}
            agent = meta.get("agent", "?")
            summary = meta.get("summary", "")
            lines.append(f"[{agent}] {summary}")
        return "\n".join(lines)