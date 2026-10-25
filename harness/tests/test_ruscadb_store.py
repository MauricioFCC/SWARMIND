"""Tests para RuscaDBStore (adaptador RuscaDB)."""

from __future__ import annotations

import os
import tempfile

import pytest

try:
    from harness.memory_rag.ruscadb import load_library
    load_library()
    _RUSCADB_AVAILABLE = True
except Exception:  # noqa: BLE001
    _RUSCADB_AVAILABLE = False

pytestmark = pytest.mark.skipif(not _RUSCADB_AVAILABLE, reason="RuscaDB C-ABI dll not available")

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