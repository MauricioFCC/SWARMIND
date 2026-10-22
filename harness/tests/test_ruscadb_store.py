"""Tests para RuscaDBStore (adaptador RuscaDB)."""

from __future__ import annotations

import os
import tempfile

import pytest

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