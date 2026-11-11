"""Catálogo de conocimiento: dual-store RuscaDB + grafo tipado.

WHAT: mantiene en la memoria central un catálogo tipado de conocimiento
externo (repositorios, papers, artículos, técnicas, arquitecturas y algoritmos)
con **doble representación**: texto embebido + BM25 en la colección RuscaDB
``knowledge_catalog`` y un grafo tipado ``KnowledgeGraph`` (entrada ↔ concepto
↔ tipo ↔ cita ↔ repo). La búsqueda fusiona dense + sparse + expansión de grafo
con Reciprocal Rank Fusion (RRF, ``k=60``).

WHY: hoy el equipo re-investiga desde cero en cada tarea; el conocimiento
externo que se lee (papers, repos, técnicas) no se acumula ni se conecta. El
research ``docs/research/frontier-2026-11-11-knowledge-catalog.md`` comparó 4
hipótesis y eligió H3 (dual-store híbrido): mejor multi-hop que RAG plano,
mejor recall que grafo puro y mucho menor costo/no-determinismo que GraphRAG
con comunidades LLM (H4, fuera del camino caliente).

WHERE: ``harness/memory_rag/knowledge_catalog.py`` (I/O y búsqueda) +
``knowledge_catalog_types.py`` (esquema puro) + CLI
``scripts/knowledge_catalog.py``; consumo por agentes vía la colección
``knowledge_catalog`` y el grafo persistido.

Invariantes: determinista (embeddings y IDs estables), idempotente (dedupe por
ID canónico + hash de contenido), sin LLM en indexación/búsqueda, sin secretos
ni rutas personales en las entradas.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Protocol

import numpy as np

from harness.memory_rag.embeddings import make_embedding
from harness.memory_rag.knowledge_catalog_types import (
    CatalogEntry,
    CatalogLink,
    EntryKind,
    EntryStatus,
    canonical_id,
    catalog_text,
    content_hash,
    entry_from_json,
    entry_metadata,
)
from harness.memory_rag.knowledge_catalog_usage import (
    UsageRecord,
    append_usage,
    read_usage,
    summarize_usage,
    usage_path,
)
from harness.memory_rag.knowledge_graph import KnowledgeGraph

logger = logging.getLogger(__name__)

__all__ = [
    "COLLECTION",
    "CatalogEntry",
    "CatalogLink",
    "EntryKind",
    "EntryStatus",
    "KnowledgeCatalog",
    "canonical_id",
    "catalog_text",
]

#: Colección canónica del catálogo en la memoria central.
COLLECTION = "knowledge_catalog"
#: Constante RRF estándar (Cormack et al., 2009; misma que el dual-store).
RRF_K = 60
#: Peso de un candidato descubierto solo por el grafo.
GRAPH_WEIGHT = 0.5
#: Semillas del ranking híbrido que se expanden por el grafo.
EXPAND_SEEDS = 3


class CatalogStore(Protocol):
    """Superficie mínima del store que el catálogo necesita (DI para tests).

    Contrato (mismo que ``RuscaDBStore``):

    - ``insert(collection, vectors, metadata, now=None, edges=None, texts=None)``
      → ids de fila.
    - ``delete(collection, ids)`` → filas borradas.
    - ``hybrid_search(collection, query_vector, query_text="", top_k=5, **kw)``
      → hits ``{id, metadata, score}``.
    - ``get_collection_stats(name)`` → ``{"count": int, ...}``.
    """

    def insert(self, *args: Any) -> list[str]:
        """Inserta filas y devuelve sus ids."""

    def delete(self, *args: Any) -> int:
        """Borra filas por id."""

    def hybrid_search(self, *args: Any) -> list[dict[str, Any]]:
        """Búsqueda densa + BM25 fusionada con RRF."""

    def get_collection_stats(self, *args: Any) -> dict[str, Any]:
        """Estadísticas de la colección."""


class KnowledgeCatalog:
    """Catálogo dual-store: colección RuscaDB + grafo tipado.

    Args:
        store: Store compatible con :class:`CatalogStore` (RuscaDB en prod).
        collection: Colección destino (default ``knowledge_catalog``).
        graph: Grafo NetworkX; si es ``None`` se crea en memoria.
        index_path: JSON del índice de dedupe (``catalog_id -> fila``).
        graph_path: JSON de persistencia del grafo.
        embedding: Función texto→vector (default determinista 384-d).
    """

    def __init__(
        self,
        store: CatalogStore,
        *,
        collection: str = COLLECTION,
        graph: KnowledgeGraph | None = None,
        index_path: Path | None = None,
        graph_path: Path | None = None,
        embedding: Any = make_embedding,
    ) -> None:
        """Inicializa catálogo, grafo e índice persistente (si hay rutas)."""
        self.store = store
        self.collection = collection
        self.graph = graph if graph is not None else KnowledgeGraph(graph_path)
        self.index_path = index_path
        self.graph_path = graph_path
        self._embed = embedding
        self._index: dict[str, dict[str, Any]] = {}
        self._row_to_cid: dict[str, str] = {}
        self._load_index()

    # ------------------------------------------------------------------
    # Índice y persistencia
    # ------------------------------------------------------------------

    def _load_index(self) -> None:
        """Carga el índice de dedupe desde disco (si existe y es válido)."""
        if self.index_path is None or not self.index_path.is_file():
            return
        try:
            payload = json.loads(self.index_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("catálogo: índice ilegible (%s); se reconstruye", exc)
            return
        for cid, dato in (payload.get("entries") or {}).items():
            if isinstance(dato, dict) and "row_id" in dato:
                self._index[cid] = dato
                self._row_to_cid[str(dato["row_id"])] = cid

    def _save_index(self) -> None:
        """Persiste el índice de forma atómica (best-effort)."""
        if self.index_path is None:
            return
        self.index_path.parent.mkdir(parents=True, exist_ok=True)
        temporal = self.index_path.with_suffix(".tmp")
        temporal.write_text(
            json.dumps({"version": 1, "entries": self._index}, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        temporal.replace(self.index_path)

    def _save_graph(self) -> None:
        """Persiste el grafo si hay ruta configurada."""
        if self.graph_path is not None:
            self.graph.save(self.graph_path)

    # ------------------------------------------------------------------
    # Ingesta
    # ------------------------------------------------------------------

    def index(self, entries: list[CatalogEntry]) -> dict[str, Any]:
        """Ingesta idempotente: dedupe por ID y versionado por hash.

        Args:
            entries: Entradas validadas a indexar.

        Returns:
            Reporte ``{"inserted", "updated", "skipped", "errors"}``.
        """
        report: dict[str, Any] = {"inserted": 0, "updated": 0, "skipped": 0, "errors": []}
        for entry in entries:
            try:
                self._index_one(entry, report)
            except (ValueError, OSError) as exc:
                report["errors"].append(f"{entry.url}: {exc}")
        self._save_index()
        self._save_graph()
        return report

    def _index_one(self, entry: CatalogEntry, report: dict[str, Any]) -> None:
        """Indexa una entrada y actualiza contadores del reporte."""
        cid = entry.catalog_id
        huella = content_hash(entry)
        previo = self._index.get(cid)
        if previo is not None and previo.get("content_hash") == huella:
            report["skipped"] += 1
            return
        if previo is not None:
            self.store.delete(self.collection, [str(previo["row_id"])])
            self._row_to_cid.pop(str(previo["row_id"]), None)
        texto = catalog_text(entry)
        vector = np.asarray(self._embed(texto), dtype=np.float32).reshape(1, -1)
        meta = entry_metadata(entry)
        fila = self.store.insert(self.collection, vector, [meta], texts=[texto])[0]
        self._index[cid] = {
            "row_id": fila,
            "content_hash": huella,
            "version": int(previo.get("version", 0)) + 1 if previo else 1,
            "metadata": meta,
        }
        self._row_to_cid[fila] = cid
        self._graph_entry(entry)
        report["updated" if previo else "inserted"] += 1

    def _graph_entry(self, entry: CatalogEntry) -> None:
        """Añade la entrada y sus aristas al grafo tipado."""
        nodo = f"catalog:{entry.catalog_id}"
        self.graph.add_node(
            nodo, entry.kind.value, {"title": entry.title, "url": entry.url}
        )
        self.graph.connect(nodo, f"kind:{entry.kind.value}", "instance_of")
        for concepto in (*entry.tags, *entry.concepts):
            from harness.memory_rag.knowledge_catalog_types import _slug

            self.graph.connect(nodo, f"concept:{_slug(concepto)}", "about")
        for link in entry.links:
            self.graph.connect(nodo, f"catalog:{link.target}", link.relation)

    # ------------------------------------------------------------------
    # Búsqueda
    # ------------------------------------------------------------------

    def search(
        self,
        query: str,
        *,
        top_k: int = 5,
        kind: EntryKind | None = None,
        expand: bool = True,
        max_neighbors: int = EXPAND_SEEDS,
    ) -> list[dict[str, Any]]:
        """Búsqueda híbrida (dense + BM25 + grafo) con RRF.

        Args:
            query: Texto de consulta.
            top_k: Número máximo de resultados.
            kind: Filtra por tipo de entrada.
            expand: Expande el grafo desde las mejores semillas.
            max_neighbors: Semillas del ranking que se expanden.

        Returns:
            Lista de hits ``{catalog_id, kind, title, url, score, sources}``.
        """
        if not query.strip():
            return []
        base = self._retrieve(query, top_k, kind)
        scores, fuentes = self._score_base(base)
        if expand:
            self._expand_graph(base[:max_neighbors], scores, fuentes, kind)
        return self._rank(scores, fuentes, top_k)

    def _retrieve(
        self, query: str, top_k: int, kind: EntryKind | None
    ) -> list[dict[str, Any]]:
        """Retrieval híbrido con filtro de tipo aplicado también en cliente."""
        vector = np.asarray(self._embed(query), dtype=np.float32)
        filtros = {"kind": kind.value} if kind is not None else None
        base = self.store.hybrid_search(
            self.collection,
            vector,
            query_text=query,
            top_k=max(top_k * 2, top_k),
            filters=filtros,
        )
        if kind is None:
            return base
        return [
            item
            for item in base
            if str((item.get("metadata") or {}).get("kind", "")) == kind.value
        ]

    def _score_base(
        self, base: list[dict[str, Any]]
    ) -> tuple[dict[str, float], dict[str, set[str]]]:
        """Convierte el ranking híbrido en scores RRF por ``catalog_id``."""
        scores: dict[str, float] = {}
        fuentes: dict[str, set[str]] = {}
        for rank, item in enumerate(base):
            cid = self._row_to_cid.get(str(item.get("id")))
            if cid is None:
                continue
            scores[cid] = scores.get(cid, 0.0) + 1.0 / (RRF_K + rank + 1)
            fuentes.setdefault(cid, set()).add("hybrid")
        return scores, fuentes

    def _expand_graph(
        self,
        semillas: list[dict[str, Any]],
        scores: dict[str, float],
        fuentes: dict[str, set[str]],
        kind: EntryKind | None = None,
    ) -> None:
        """Suma vecinos del grafo (salientes y entrantes) con peso atenuado."""
        for seed_rank, item in enumerate(semillas):
            cid = self._row_to_cid.get(str(item.get("id")))
            if cid is None:
                continue
            for reverse in (False, True):
                for destino in self.graph.neighbors(f"catalog:{cid}", reverse=reverse):
                    if not destino.startswith("catalog:"):
                        continue
                    target = destino.removeprefix("catalog:")
                    if target not in self._index:
                        continue
                    if kind is not None:
                        meta = self._index[target].get("metadata", {})
                        if str(meta.get("kind", "")) != kind.value:
                            continue
                    scores[target] = scores.get(target, 0.0) + GRAPH_WEIGHT / (
                        RRF_K + seed_rank + 1
                    )
                    fuentes.setdefault(target, set()).add("graph")

    def _rank(
        self,
        scores: dict[str, float],
        fuentes: dict[str, set[str]],
        top_k: int,
    ) -> list[dict[str, Any]]:
        """Ordena por score y materializa los hits desde el índice."""
        ordenados = sorted(scores.items(), key=lambda par: (-par[1], par[0]))
        hits: list[dict[str, Any]] = []
        for cid, score in ordenados[:top_k]:
            meta = self._index.get(cid, {}).get("metadata", {})
            hits.append({
                "catalog_id": cid,
                "kind": meta.get("kind", ""),
                "title": meta.get("title", ""),
                "url": meta.get("url", ""),
                "summary": meta.get("summary", ""),
                "tags": meta.get("tags", []),
                "score": round(score, 6),
                "sources": sorted(fuentes.get(cid, ())),
            })
        return hits

    # ------------------------------------------------------------------
    # Stats, export e ingesta desde JSON
    # ------------------------------------------------------------------

    def stats(self) -> dict[str, Any]:
        """Resumen del catálogo por tipo y estado (desde el índice)."""
        by_kind: dict[str, int] = {}
        by_status: dict[str, int] = {}
        for dato in self._index.values():
            meta = dato.get("metadata", {})
            kind = str(meta.get("kind", "unknown"))
            status = str(meta.get("status", "unknown"))
            by_kind[kind] = by_kind.get(kind, 0) + 1
            by_status[status] = by_status.get(status, 0) + 1
        store_stats = self.store.get_collection_stats(self.collection)
        return {
            "total": len(self._index),
            "rows": int(store_stats.get("count", 0)),
            "by_kind": dict(sorted(by_kind.items())),
            "by_status": dict(sorted(by_status.items())),
            "graph_nodes": self.graph.get_stats().get("nodes", 0),
            "graph_edges": self.graph.get_stats().get("edges", 0),
        }

    def export(self, path: Path) -> Path:
        """Exporta el catálogo a JSON canónico (para versionar/compartir)."""
        entradas = []
        for cid, dato in sorted(self._index.items()):
            meta = dict(dato.get("metadata", {}))
            meta["catalog_id"] = cid
            entradas.append(meta)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps({"version": 1, "entries": entradas}, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        return path

    def ingest(self, path: Path) -> dict[str, Any]:
        """Carga entradas desde un JSON de seed y las indexa."""
        payload = json.loads(path.read_text(encoding="utf-8"))
        crudas = payload.get("entries", payload) if isinstance(payload, dict) else payload
        entradas = [entry_from_json(item) for item in crudas]
        return self.index(entradas)

    def context_block(self, query: str, top_k: int = 3) -> str:
        """Bloque markdown compacto del catálogo para inyectar en contexto.

        Args:
            query: Necesidad de conocimiento (tarea, técnica, arquitectura).
            top_k: Máximo de entradas a incluir.

        Returns:
            Texto listo para prompt ('' si no hay coincidencias).
        """
        hits = self.search(query, top_k=top_k)
        if not hits:
            return ""
        lineas = [f"Catálogo de conocimiento (top {len(hits)} para «{query}»):"]
        lineas.extend(
            f"- [{hit['kind']}] {hit['title']} — {hit['url']}" for hit in hits
        )
        return "\n".join(lineas)

    # ------------------------------------------------------------------
    # Ciclo de vida: feedback y gaps
    # ------------------------------------------------------------------

    def record_usage(
        self,
        query: str,
        catalog_ids: list[str] | tuple[str, ...] = (),
        *,
        outcome: str = "useful",
        note: str = "",
    ) -> UsageRecord | None:
        """Registra una consulta y su resultado (append-only).

        Args:
            query: Necesidad consultada.
            catalog_ids: Entradas usadas (vacío en ``missing``).
            outcome: ``useful``, ``stale`` o ``missing``.
            note: Comentario (qué faltó o cómo se aplicó).

        Returns:
            El registro escrito, o ``None`` si el catálogo es en memoria.
        """
        path = usage_path(self.index_path)
        if path is None:
            return None
        record = UsageRecord(
            query=query, catalog_ids=tuple(catalog_ids), outcome=outcome, note=note
        )
        append_usage(path, record)
        self._log_gap(record)
        return record

    @staticmethod
    def _log_gap(record: UsageRecord) -> None:
        """Avisa cuando una consulta deja un gap que hay que alimentar."""
        if record.outcome == "missing":
            logger.warning(
                "catálogo: gap detectado para «%s» (%s); añade una entrada",
                record.query,
                record.note or "sin nota",
            )

    def usage_stats(self, top: int = 5) -> dict[str, object]:
        """Resumen del uso registrado y gaps abiertos."""
        return summarize_usage(read_usage(usage_path(self.index_path)), top=top)
