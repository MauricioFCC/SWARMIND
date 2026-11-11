"""Tests del catálogo de conocimiento (spec ``knowledge-catalog.md``).

Contratos (AC1-AC8):
  1. ``canonical_id`` normaliza arXiv/DOI/GitHub y es idempotente (PBT).
  2. Ingesta repetida no duplica (dedupe + versionado por hash).
  3. ``index`` escribe vector/texto/metadata y crea nodos/aristas de grafo.
  4. ``search`` fusiona retrieval híbrido + expansión de grafo con RRF.
  5. Sin nodo en el grafo, ``search`` degrada a híbrido (H1).
  6. ``stats`` reporta total y desglose por tipo/estado.
  7. Entradas inválidas o con rutas personales se rechazan.
  8. ``export``/``ingest`` hacen round-trip estable.

El store se inyecta como fake: el DLL nativo de RuscaDB es Windows-only y CI
corre en Linux, así que los contratos se prueban sin backend nativo.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from hypothesis import given
from hypothesis import strategies as st

from harness.memory_rag.knowledge_catalog import (
    CatalogEntry,
    CatalogLink,
    EntryKind,
    EntryStatus,
    KnowledgeCatalog,
    canonical_id,
    catalog_text,
)
from harness.memory_rag.knowledge_catalog_types import entry_from_json
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


@pytest.fixture()
def graph() -> KnowledgeGraph:
    """Grafo en memoria (NetworkX, sin persistencia)."""
    return KnowledgeGraph()


@pytest.fixture()
def catalog(graph: KnowledgeGraph) -> KnowledgeCatalog:
    """Catálogo con store falso y grafo en memoria."""
    return KnowledgeCatalog(store=FakeStore(), graph=graph)


# ---------------------------------------------------------------------------
# AC1 — canonical_id
# ---------------------------------------------------------------------------


class TestCanonicalId:
    def test_arxiv_desde_abs_y_prefijo(self) -> None:
        """arXiv se normaliza igual venga como URL o como ``arXiv:``."""
        esperado = "paper:arxiv-2404.16130"
        assert canonical_id(EntryKind.PAPER, "https://arxiv.org/abs/2404.16130") == esperado
        assert canonical_id(EntryKind.PAPER, "arXiv:2404.16130") == esperado

    def test_doi_normalizado(self) -> None:
        """El DOI pierde barras y mayúsculas."""
        assert (
            canonical_id(EntryKind.PAPER, "doi:10.1145/1571941.1572114")
            == "paper:doi-10.1145-1571941.1572114"
        )

    def test_github_owner_repo(self) -> None:
        """GitHub se reduce a ``owner/repo`` sin esquema ni ``.git``."""
        assert (
            canonical_id(EntryKind.REPO, "https://github.com/DEEP-PolyU/Awesome-GraphRAG.git")
            == "repo:deep-polyu/awesome-graphrag"
        )

    @given(st.text(min_size=1, max_size=80))
    def test_idempotente(self, ref: str) -> None:
        """AC1: canonical_id(canonical_id(x)) == canonical_id(x)."""
        una = canonical_id(EntryKind.ARTICLE, ref)
        dos = canonical_id(EntryKind.ARTICLE, una)
        assert una == dos


# ---------------------------------------------------------------------------
# AC7 — validación
# ---------------------------------------------------------------------------


class TestValidacion:
    def test_titulo_vacio_rechazado(self) -> None:
        """Sin título no hay entrada."""
        with pytest.raises(ValueError, match="title"):
            _entry(title="   ")

    def test_url_personal_rechazada(self) -> None:
        """Una ruta de máquina en la URL se rechaza (privacidad)."""
        with pytest.raises(ValueError, match="personal"):
            _entry(url=r"C:\Users\ana\Documents\paper.pdf")

    def test_year_fuera_de_rango(self) -> None:
        """Años imposibles se rechazan."""
        with pytest.raises(ValueError, match="year"):
            _entry(year=1200)

    def test_kind_es_enum(self) -> None:
        """El tipo pertenece al enum cerrado del catálogo."""
        assert _entry().kind is EntryKind.PAPER


# ---------------------------------------------------------------------------
# AC2/AC3 — indexación, dedupe y grafo
# ---------------------------------------------------------------------------


class TestIndex:
    def test_ingesta_escribe_vector_texto_y_metadata(self, catalog: KnowledgeCatalog) -> None:
        """AC3: el store recibe vector 384-d, texto y metadata tipada."""
        report = catalog.index([_entry()])

        assert report["inserted"] == 1
        store = catalog.store
        assert isinstance(store, FakeStore)
        fila = next(iter(store.rows.values()))
        assert fila["vector"].shape == (384,)
        assert "Graph RAG" in fila["text"]
        assert fila["metadata"]["kind"] == "paper"
        assert fila["metadata"]["url"].startswith("https://arxiv.org/")

    def test_ingesta_repetida_no_duplica(self, catalog: KnowledgeCatalog) -> None:
        """AC2: mismo contenido dos veces => skipped, una sola fila."""
        catalog.index([_entry()])
        report = catalog.index([_entry()])

        assert report["skipped"] == 1
        assert report["inserted"] == 0
        store = catalog.store
        assert isinstance(store, FakeStore)
        assert len(store.rows) == 1

    def test_actualizacion_reemplaza_fila(self, catalog: KnowledgeCatalog) -> None:
        """Cambiar el contenido versiona: borra la fila vieja y deja una."""
        catalog.index([_entry()])
        report = catalog.index([_entry(summary="Resumen actualizado.")])

        assert report["updated"] == 1
        store = catalog.store
        assert isinstance(store, FakeStore)
        assert len(store.rows) == 1
        assert len(store.deleted) == 1

    def test_crea_nodos_y_aristas_de_grafo(self, catalog: KnowledgeCatalog) -> None:
        """AC3: el grafo conecta entrada ↔ concepto y ↔ tipo/instancia."""
        catalog.index([_entry(tags=("graph-rag",), concepts=("knowledge-graph",))])

        nodos = catalog.graph.query("catalog:paper:arxiv-2404.16130", max_depth=1)
        relaciones = {n["relation"] for n in nodos}
        destinos = {n["node"] for n in nodos}
        assert "about" in relaciones
        assert "instance_of" in relaciones
        assert "concept:graph-rag" in destinos
        assert "kind:paper" in destinos

    def test_enlace_entre_entradas(self, catalog: KnowledgeCatalog) -> None:
        """``cites`` conecta dos papers del catálogo."""
        catalog.index(
            [
                _entry(),
                _entry(
                    title="LightRAG",
                    url="https://arxiv.org/abs/2410.05779",
                    links=(CatalogLink(relation="cites", target="paper:arxiv-2404.16130"),),
                ),
            ]
        )

        vecinos = catalog.graph.query("catalog:paper:arxiv-2410.05779", max_depth=1)
        assert any(n["node"] == "catalog:paper:arxiv-2404.16130" for n in vecinos)


# ---------------------------------------------------------------------------
# AC4/AC5 — búsqueda híbrida y degradación
# ---------------------------------------------------------------------------


class TestSearch:
    def test_filtra_por_kind(self, catalog: KnowledgeCatalog) -> None:
        """AC4: ``kind`` acota los resultados a ese tipo."""
        catalog.index(
            [
                _entry(),
                _entry(kind=EntryKind.REPO, title="LightRAG repo",
                       url="https://github.com/HKUDS/LightRAG"),
            ]
        )

        hits = catalog.search("graph", top_k=5, kind=EntryKind.REPO)

        assert hits
        assert all(h["kind"] == "repo" for h in hits)

    def test_respeta_top_k(self, catalog: KnowledgeCatalog) -> None:
        """AC4: no devuelve más de ``top_k``."""
        catalog.index(
            [
                _entry(),
                _entry(title="GraphRAG-Bench", url="https://arxiv.org/abs/2506.02404"),
                _entry(title="A-MEM", url="https://arxiv.org/abs/2502.12110"),
            ]
        )

        assert len(catalog.search("graph", top_k=2)) <= 2

    def test_expande_con_grafo(self, catalog: KnowledgeCatalog) -> None:
        """AC4: un vecino del grafo entra como candidato aunque el texto no matchee."""
        catalog.index(
            [
                _entry(title="Paper semilla", url="https://arxiv.org/abs/2404.16130"),
                _entry(title="Vecino sin terminos", url="https://arxiv.org/abs/2410.05779",
                       links=(CatalogLink(relation="cites", target="paper:arxiv-2404.16130"),)),
            ]
        )

        hits = catalog.search("semilla", top_k=5, expand=True)

        ids = {h["catalog_id"] for h in hits}
        assert "paper:arxiv-2410.05779" in ids

    def test_sin_grafo_degrada_a_hibrido(self, catalog: KnowledgeCatalog) -> None:
        """AC5: con grafo vacío la búsqueda sigue devolviendo el hit híbrido."""
        catalog.index([_entry()])
        catalog.graph = KnowledgeGraph()  # grafo vacío (simula ausencia)

        hits = catalog.search("graph", top_k=5, expand=True)

        assert hits
        assert hits[0]["catalog_id"] == "paper:arxiv-2404.16130"


# ---------------------------------------------------------------------------
# AC6/AC8 — stats, export e ingesta
# ---------------------------------------------------------------------------


class TestStatsExport:
    def test_stats_desglosa_por_tipo_y_estado(self, catalog: KnowledgeCatalog) -> None:
        """AC6: total + kind/status."""
        catalog.index(
            [
                _entry(),
                _entry(kind=EntryKind.REPO, title="repo", url="https://github.com/a/b"),
            ]
        )

        stats = catalog.stats()

        assert stats["total"] == 2
        assert stats["by_kind"]["paper"] == 1
        assert stats["by_kind"]["repo"] == 1
        assert stats["by_status"]["evaluated"] == 2

    def test_export_ingest_roundtrip(
        self, catalog: KnowledgeCatalog, tmp_path: Path
    ) -> None:
        """AC8: export → ingest reconstruye el mismo catálogo."""
        catalog.index([_entry()])
        destino = tmp_path / "catalog.json"
        catalog.export(destino)

        otro = KnowledgeCatalog(store=FakeStore(), graph=KnowledgeGraph())
        report = otro.ingest(destino)

        assert report["inserted"] == 1
        assert otro.stats()["total"] == 1
        payload = json.loads(destino.read_text(encoding="utf-8"))
        assert payload["entries"][0]["catalog_id"] == "paper:arxiv-2404.16130"

    def test_texto_indexable_incluye_campos_clave(self) -> None:
        """``catalog_text`` alimenta FTS/embedding con título, resumen y tags."""
        texto = catalog_text(_entry())
        assert "Graph RAG" in texto
        assert "graph-rag" in texto
        assert "knowledge-graph" in texto


# ---------------------------------------------------------------------------
# Seed público y CLI
# ---------------------------------------------------------------------------


ROOT = Path(__file__).resolve().parents[2]
SEED = ROOT / "docs" / "knowledge" / "catalog.seed.json"


class TestSeedPublico:
    def test_seed_valido_y_sin_duplicados(self) -> None:
        """El seed versionado parsea, valida y tiene IDs únicos."""
        payload = json.loads(SEED.read_text(encoding="utf-8"))
        entradas = [entry_from_json(item) for item in payload["entries"]]
        ids = [e.catalog_id for e in entradas]
        assert len(entradas) >= 10
        assert len(ids) == len(set(ids))

    def test_seed_sin_rutas_personales(self) -> None:
        """El seed público no filtra rutas de máquina (SEG)."""
        texto = SEED.read_text(encoding="utf-8")
        assert "C:\\Users\\" not in texto
        assert "/home/" not in texto

    def test_cli_verify_ok(self) -> None:
        """``knowledge_catalog.py verify`` valida el seed sin abrir el store."""
        sys.path.insert(0, str(ROOT / "scripts"))
        import knowledge_catalog as cli

        assert cli.main(["verify", str(SEED)]) == 0

    def test_context_block_para_agentes(self, catalog: KnowledgeCatalog) -> None:
        """``context_block`` devuelve markdown compacto o vacío."""
        catalog.index([_entry()])

        bloque = catalog.context_block("graph rag", top_k=3)

        assert "Catálogo de conocimiento" in bloque
        assert "paper:arxiv-2404.16130" in bloque or "Graph RAG" in bloque
        assert catalog.context_block("zzz-sin-coincidencias", top_k=3) == ""


# ---------------------------------------------------------------------------
# Ciclo de vida: feedback y gaps (si no se alimenta, pierde efectividad)
# ---------------------------------------------------------------------------


class TestConsultaAutomatica:
    def test_deriva_indice_y_grafo_del_store(self, tmp_path: Path) -> None:
        """Sin rutas explícitas, el catálogo usa ``<data>/`` del store."""
        store = FakeStore()
        store.db_path = str(tmp_path / "data" / "ruscadb.db")  # type: ignore[attr-defined]

        catalog = KnowledgeCatalog(store)

        assert catalog.index_path == tmp_path / "data" / "knowledge_catalog.index.json"
        assert catalog.graph_path == tmp_path / "data" / "knowledge_catalog_graph.json"

    def test_recarga_indice_persistido(self, tmp_path: Path) -> None:
        """Un catálogo nuevo sobre el mismo store recupera el índice en disco."""
        store = FakeStore()
        store.db_path = str(tmp_path / "data" / "ruscadb.db")  # type: ignore[attr-defined]
        primero = KnowledgeCatalog(store)
        primero.index([_entry()])

        segundo = KnowledgeCatalog(store)

        assert segundo.stats()["total"] == 1
        assert segundo.graph.get_stats().get("nodes", 0) > 0
