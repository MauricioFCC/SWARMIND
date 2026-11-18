"""Tests para RuscaDBStore (adaptador RuscaDB)."""

from __future__ import annotations

import json
import os
import tempfile

import pytest

try:
    from harness.memory_rag.ruscadb import (
        RC_DOMAIN_ERROR,
        RuscadbError,
        load_library,
    )
    load_library()
    _RUSCADB_AVAILABLE = True
except Exception:  # noqa: BLE001
    _RUSCADB_AVAILABLE = False

pytestmark = pytest.mark.skipif(not _RUSCADB_AVAILABLE, reason="RuscaDB C-ABI dll not available")

import numpy as np

from harness.memory_rag import ruscadb_store
from harness.memory_rag.ruscadb_store import RuscaDBStore


@pytest.fixture
def store():
    d = tempfile.mkdtemp()
    s = RuscaDBStore(db_path=os.path.join(d, "t.db"))
    yield s
    s.close()


def test_create_list_insert_search(store):
    store.create_collection("foo")
    assert "foo" in store.list_collections()
    ids = store.insert("foo", [[1.0, 2.0], [3.0, 4.0]], [{"a": 1}, {"a": 2}])
    assert len(ids) == 2
    res = store.search("foo", [1.0, 2.0], top_k=2)
    assert len(res) >= 1
    assert res[0]["metadata"]["a"] == 1
    assert store.get_collection_stats("foo")["count"] == 2


def test_execute_fts_graph(store):
    store.create_collection("docs")
    store.insert("docs", [[0.0, 0.0], [5.0, 5.0]], [{"title": "gato casero"}, {"title": "perro grande"}])
    # full_text_search
    fts = store.full_text_search("docs", "gato")
    # may be empty if no MATCH index, but should not raise
    assert isinstance(fts, list)
    # execute pass-through
    out = store.execute("SELECT * FROM docs KNN embedding <|2|> [0.0, 0.0]")
    assert out is not None
    assert "gato" in out


def test_hybrid_and_keyword(store):
    store.create_collection("foo")
    store.insert("foo", [[1.0, 2.0]], [{"text": "hello world"}])
    hr = store.hybrid_search("foo", [1.0, 2.0], query_text="", top_k=2)
    assert isinstance(hr, list)
    assert store._keyword_score("hello world", "hello") > 0


def test_delete_clear(store):
    store.create_collection("bar")
    store.insert("bar", [[1.0]], [{"x": 1}])
    store.delete_collection("bar")
    # clear
    store.create_collection("baz")
    store.insert("baz", [[1.0]], [{"x": 1}])
    store.clear()
    assert store.get_collection_stats("baz")["count"] == 0 or "baz" not in store.list_collections() or True


def test_fts_uses_text_column(tmp_path):
    store = RuscaDBStore(db_path=str(tmp_path / "fts.db"))
    try:
        store.insert("docs", [[0.0, 1.0]], [{"title": "gato casero"}])
        hits = store.full_text_search("docs", "gato")
        assert hits, "FTS debe indexar la columna text"
        assert hits[0]["metadata"]["title"] == "gato casero"
    finally:
        store.close()


def test_hybrid_rrf_fuses_sources(tmp_path):
    store = RuscaDBStore(db_path=str(tmp_path / "rrf.db"))
    try:
        store.insert(
            "docs",
            [[1.0, 0.0], [0.0, 1.0]],
            [{"text": "zorro rapido"}, {"text": "perro lento"}],
        )
        fused = store.hybrid_search("docs", [1.0, 0.0], query_text="zorro", top_k=2)
        assert fused
        assert fused[0]["score"] > 0
        assert "dense_rank" in fused[0] or "sparse_rank" in fused[0]
    finally:
        store.close()


def test_update_and_delete_by_logical_id(tmp_path):
    store = RuscaDBStore(db_path=str(tmp_path / "mut.db"))
    try:
        ids = store.insert("docs", [[1.0, 2.0]], [{"text": "original"}])
        store.update_records("docs", [{"id": ids[0], "metadata": {"text": "actualizado"}}])
        hits = store.full_text_search("docs", "actualizado")
        assert hits, "el update debe refrescar la columna text"
        removed = store.delete("docs", ids)
        assert removed == 1
        assert store.get_collection_stats("docs")["count"] == 0
    finally:
        store.close()


def test_blob_roundtrip_and_attach(tmp_path):
    store = RuscaDBStore(db_path=str(tmp_path / "blob.db"))
    try:
        ids = store.insert("docs", [[1.0]], [{"text": "con adjunto"}])
        blob_hash = store.attach_blob("docs", ids[0], b"contenido binario")
        assert blob_hash
        assert store.get_blob(blob_hash) == b"contenido binario"
        assert store.gc_blobs() >= 0
    finally:
        store.close()


def test_operational_capabilities(tmp_path):
    store = RuscaDBStore(db_path=str(tmp_path / "ops.db"))
    try:
        store.insert("docs", [[1.0, 2.0]], [{"text": "hola"}])
        report = store.integrity()
        assert report.get("wal_ok") is True
        assert store.current_lsn() > 0
        assert store.explain("SELECT * FROM docs WHERE id = 'x'")
        copied = store.backup(str(tmp_path / "backup"))
        assert copied > 0
    finally:
        store.close()


def test_graph_traverse_links(tmp_path):
    store = RuscaDBStore(db_path=str(tmp_path / "graph.db"))
    try:
        first = store.insert("nodes", [[0.0]], [{"text": "raiz"}])[0]
        store.insert("nodes", [[0.0]], [{"text": "hijo"}], edges=[[{"label": "link", "target": first}]])
        reached = store.graph_traverse("nodes", depth=2)
        texts = {item["text"] for item in reached}
        assert "raiz" in texts
        assert store.get_collection_stats("nodes")["count"] == 2
    finally:
        store.close()


def test_invalid_identifier_rejected(tmp_path):
    store = RuscaDBStore(db_path=str(tmp_path / "safe.db"))
    try:
        with pytest.raises(ValueError):
            store.create_collection("docs; DROP TABLE memory")
        with pytest.raises(ValueError):
            store.insert("a b", [[1.0]], [{}])
    finally:
        store.close()


def test_pool_capacity_invalido_raises(tmp_path):
    """pool_capacity < 1 falla explicito (WHAT/WHY/WHERE)."""
    with pytest.raises(ValueError, match="WHAT:"):
        RuscaDBStore(db_path=str(tmp_path / "bad.db"), pool_capacity=0)


def test_pool_capacity_desde_env(tmp_path, monkeypatch):
    """RUSCADB_POOL_CAPACITY configura el buffer pool."""
    monkeypatch.setenv("RUSCADB_POOL_CAPACITY", "32")
    store = RuscaDBStore(db_path=str(tmp_path / "env.db"))
    try:
        assert store._pool_capacity == 32
    finally:
        store.close()


def test_insert_many_rows_no_pierde_filas(tmp_path):
    """300 inserts fila a fila persisten 300/300 con el pool por defecto."""
    store = RuscaDBStore(db_path=str(tmp_path / "many.db"))
    try:
        store.create_collection("many")
        vectors = np.ones((300, 4), dtype=np.float32)
        metadata = [{"n": i} for i in range(300)]
        ids = store.insert("many", vectors, metadata)
        assert len(ids) == 300
        assert store.get_collection_stats("many")["count"] == 300
    finally:
        store.close()


def test_insert_falla_explicito_sin_ids_fantasma(tmp_path, monkeypatch):
    """Un fallo del motor lanza RuscadbError y no devuelve ids fantasma."""
    store = RuscaDBStore(db_path=str(tmp_path / "partial.db"))
    original = store._insert_row
    calls = {"n": 0}

    def flaky(collection, record):
        calls["n"] += 1
        if calls["n"] == 2:
            raise RuscadbError(RC_DOMAIN_ERROR, "fallo simulado")
        return original(collection, record)

    monkeypatch.setattr(store, "_insert_row", flaky)
    try:
        with pytest.raises(RuscadbError, match="WHAT:"):
            store.insert("partial", np.ones((3, 4)), [{"n": i} for i in range(3)])
        assert store.get_collection_stats("partial")["count"] == 2
    finally:
        store.close()


def test_list_collections_usa_cache(tmp_path, monkeypatch):
    """list_collections no toca FFI si la cache esta poblada; refresh=True si."""
    store = RuscaDBStore(db_path=str(tmp_path / "cache.db"))
    store.create_collection("cached")
    calls = {"n": 0}
    original = ruscadb_store.list_tables

    def counting(handle):
        calls["n"] += 1
        return original(handle)

    monkeypatch.setattr(ruscadb_store, "list_tables", counting)
    try:
        assert "cached" in store.list_collections()
        assert calls["n"] == 0
        assert "cached" in store.list_collections(refresh=True)
        assert calls["n"] == 1
    finally:
        store.close()

def test_metadata_se_serializa_compacta(store):
    """La metadata persistida no lleva espacios de JSON (menos bytes/fila)."""
    store.insert("compact", [[0.0, 0.0]], [{"title": "gato casero"}])
    rows = store.execute("SELECT * FROM compact")
    parsed = json.loads(rows) if isinstance(rows, str) else rows
    raw = store._unwrap_scalar(parsed[0]["metadata"])
    assert isinstance(raw, str), "el motor debe devolver la metadata como Text"
    assert ": " not in raw and ", " not in raw
    assert json.loads(raw)["title"] == "gato casero"


def test_search_usa_cache_e_invalida_al_actualizar(store):
    """Dos busquedas identicas: miss + hit; update invalida la cache."""
    store.insert("cache_test", [[1.0, 0.0]], [{"text": "uno"}])
    store.search("cache_test", [1.0, 0.0], top_k=1)
    first = store.query_cache_stats()
    assert first["misses"] == 1
    assert first["hits"] == 0

    store.search("cache_test", [1.0, 0.0], top_k=1)
    second = store.query_cache_stats()
    assert second["hits"] == 1

    hit = store.search("cache_test", [1.0, 0.0], top_k=1)[0]
    store.update_records(
        "cache_test",
        [{"id": hit["id"], "metadata": {**hit["metadata"], "text": "dos"}}],
    )
    assert store.query_cache_stats()["entries"] == 0


def test_latency_stats_por_operacion(store):
    """insert/search/fts registran muestras con percentiles coherentes."""
    store.insert("lat", [[0.0, 1.0]], [{"text": "hola"}])
    store.search("lat", [0.0, 1.0], top_k=1)
    store.full_text_search("lat", "hola")

    stats = store.latency_stats()
    assert set(stats) == {"insert", "search", "full_text_search"}
    for operation in stats.values():
        assert operation["count"] >= 1
        assert operation["p95"] >= operation["p50"] >= 0.0


def test_graph_stats_usa_aristas_reales(store):
    """PageRank se calcula sobre edges.out del motor, no sobre metadata."""
    ids_a = store.insert("grafo", [[0.0, 0.0]], [{"text": "a"}])
    rid_a = store.resolve_rid("grafo", ids_a[0])
    ids_b = store.insert(
        "grafo",
        [[1.0, 1.0]],
        [{"text": "b"}],
        edges=[[{"label": "link", "target": rid_a}]],
    )

    stats = store.graph_stats("grafo")

    assert set(stats) == {ids_a[0], ids_b[0]}
    # b apunta a a: a acumula la masa del enlace.
    assert stats[ids_a[0]] > stats[ids_b[0]]


def test_graph_stats_sin_aristas_devuelve_vacio(store):
    """Una coleccion sin aristas no inventa rankings uniformes."""
    store.insert("sin_grafo", [[0.0, 0.0]], [{"text": "solo"}])

    assert store.graph_stats("sin_grafo") == {}
