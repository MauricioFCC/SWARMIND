"""Tests del ciclo de vida del cat?logo (feedback y gaps).

Contrato: una consulta sin feedback es conocimiento perdido. El JSONL de uso
es append-only, tolerante a l?neas corruptas y alimenta la cola de gaps.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pytest

from harness.memory_rag.knowledge_catalog import (
    CatalogEntry,
    EntryKind,
    EntryStatus,
    KnowledgeCatalog,
)
from harness.memory_rag.knowledge_graph import KnowledgeGraph


class FakeStore:
    """Store en memoria con la misma superficie que usa el catálogo."""

    def __init__(self) -> None:
        """Inicializa filas, contador de ids y borrados."""
        self.rows: dict[str, dict[str, Any]] = {}
        self._n = 0
        self.deleted: list[str] = []
        self.insert_calls: list[dict[str, Any]] = []

    def insert(
        self,
        collection: str,
        vectors: Any,
        metadata: list[dict[str, Any]],
        now: str | None = None,
        edges: list[list[dict[str, str]]] | None = None,
        texts: list[str] | None = None,
    ) -> list[str]:
        """Inserta filas y devuelve ids ``row-N`` (como el store real)."""
        arr = np.asarray(vectors, dtype=np.float32)
        ids: list[str] = []
        for i, meta in enumerate(metadata):
            self._n += 1
            rid = f"row-{self._n}"
            self.rows[rid] = {
                "id": rid,
                "metadata": dict(meta),
                "text": texts[i] if texts else "",
                "vector": arr[i] if arr.ndim > 1 else arr,
            }
            ids.append(rid)
        self.insert_calls.append({"collection": collection, "n": len(ids)})
        return ids

    def delete(self, collection: str, ids: list[str]) -> int:
        """Borra filas por id (usado al actualizar una entrada)."""
        borrados = 0
        for rid in ids:
            if self.rows.pop(rid, None) is not None:
                borrados += 1
                self.deleted.append(rid)
        return borrados

    def hybrid_search(
        self,
        collection: str,
        query_vector: Any,
        query_text: str = "",
        top_k: int = 5,
        **kwargs: Any,
    ) -> list[dict[str, Any]]:
        """Ranking naive por solapamiento de términos (emula dense+BM25)."""
        terms = {t for t in query_text.lower().split() if t}
        scored: list[tuple[int, dict[str, Any]]] = []
        for row in self.rows.values():
            texto = f"{row['text']} {row['metadata'].get('title', '')}".lower()
            hits = sum(1 for t in terms if t in texto)
            if hits:
                scored.append((hits, row))
        scored.sort(key=lambda par: (-par[0], par[1]["id"]))
        return [
            {
                "id": row["id"],
                "metadata": dict(row["metadata"]),
                "text": row["text"],
                "score": 1.0 / (rank + 1),
            }
            for rank, (_, row) in enumerate(scored[:top_k])
        ]

    def get_collection_stats(self, name: str) -> dict[str, Any]:
        """Conteo de filas como el store real."""
        return {"name": name, "count": len(self.rows), "item_count": len(self.rows)}


def _entry(**overrides: Any) -> CatalogEntry:
    """Entrada base válida con overrides para cada test."""
    base: dict[str, Any] = {
        "kind": EntryKind.PAPER,
        "title": "From Local to Global: A Graph RAG Approach",
        "url": "https://arxiv.org/abs/2404.16130",
        "summary": "Grafo de entidades y comunidades para preguntas globales.",
        "authors": ("Edge", "Trinh"),
        "year": 2024,
        "tags": ("graph-rag", "retrieval"),
        "concepts": ("knowledge-graph",),
        "status": EntryStatus.EVALUATED,
        "source": "arxiv",
    }
    base.update(overrides)
    return CatalogEntry(**base)


class TestUsageLoop:
    def test_record_usage_escribe_jsonl(self, tmp_path: Path) -> None:
        """Cada consulta deja una línea auditable en el JSONL de uso."""
        catalog = KnowledgeCatalog(
            store=FakeStore(), graph=KnowledgeGraph(),
            index_path=tmp_path / "cat.index.json",
        )
        catalog.index([_entry()])

        record = catalog.record_usage(
            "graph rag", ["paper:arxiv-2404.16130"], outcome="useful", note="aplicado"
        )

        assert record is not None
        ruta = tmp_path / "knowledge_catalog_usage.jsonl"
        lineas = ruta.read_text(encoding="utf-8").strip().splitlines()
        assert len(lineas) == 1
        assert '"outcome": "useful"' in lineas[0]

    def test_usage_stats_agrega_y_lista_gaps(self, tmp_path: Path) -> None:
        """``usage_stats`` cuenta resultados, top de ids y gaps abiertos."""
        catalog = KnowledgeCatalog(
            store=FakeStore(), graph=KnowledgeGraph(),
            index_path=tmp_path / "cat.index.json",
        )
        catalog.record_usage("graph rag", ["paper:a"], outcome="useful")
        catalog.record_usage("falta algo", [], outcome="missing", note="sin fuente")

        stats = catalog.usage_stats()

        assert stats["total"] == 2
        assert stats["by_outcome"] == {"missing": 1, "useful": 1}
        assert stats["top_ids"][0]["catalog_id"] == "paper:a"
        assert stats["gaps"][0]["query"] == "falta algo"

    def test_uso_en_memoria_no_escribe(self) -> None:
        """Sin ``index_path`` el feedback es no-op (no hay memoria central)."""
        catalog = KnowledgeCatalog(store=FakeStore(), graph=KnowledgeGraph())

        assert catalog.record_usage("x", ["paper:a"]) is None
        assert catalog.usage_stats()["total"] == 0

    def test_outcome_invalido_rechazado(self) -> None:
        """Solo se admiten useful/stale/missing."""
        from harness.memory_rag.knowledge_catalog_usage import UsageRecord

        with pytest.raises(ValueError, match="outcome"):
            UsageRecord(query="x", outcome="fantasma")

    def test_read_usage_tolera_linea_corrupta(self, tmp_path: Path) -> None:
        """Una línea corrupta no rompe el historial."""
        from harness.memory_rag.knowledge_catalog_usage import read_usage

        ruta = tmp_path / "uso.jsonl"
        ruta.write_text('{"query":"ok","outcome":"useful"}\nno-json\n', encoding="utf-8")

        assert len(read_usage(ruta)) == 1




class TestCierreDeGaps:
    def test_gap_se_cierra_con_feedback_posterior(self, tmp_path: Path) -> None:
        """Un ``missing`` posteriormente resuelto deja de aparecer en gaps."""
        catalog = KnowledgeCatalog(
            store=FakeStore(), graph=KnowledgeGraph(),
            index_path=tmp_path / "cat.index.json",
        )
        catalog.record_usage("falta go", [], outcome="missing", note="sin fuente")
        catalog.record_usage("falta go", ["technique:go-proverbs"], outcome="useful")

        assert catalog.usage_stats()["gaps"] == []
