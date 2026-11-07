"""Tests para ReflectionMemory (Spec recursive-harness-optimization)."""

from __future__ import annotations

from harness.evolve_loop.reflection_memory import ReflectionMemory


class _FakeStore:
    def __init__(self):
        self._data = []

    def create_collection(self, name):
        pass

    def insert(self, collection, vectors, metadata):
        self._data.append((collection, metadata))
        return ["id-1"]

    def full_text_search(self, collection, query, top_k=5):
        return [{"id": "id-1", "metadata": {"reflection": "evita X", "text": "evita X"}, "score": 1.0}]


def test_reflection_store_and_retrieve():
    store = _FakeStore()
    rm = ReflectionMemory(store)
    rid = rm.store("evita X", context={"task_id": "t1"})
    assert rid == "id-1"
    results = rm.retrieve("evita")
    assert results
    assert "evita X" in rm.compact_context("evita")


def test_reflection_handles_store_failure():
    class _Broken(_FakeStore):
        def insert(self, collection, vectors, metadata):
            raise RuntimeError("boom")

    rm = ReflectionMemory(_Broken())
    assert rm.store("x") == ""


def test_reflection_handles_retrieve_failure():
    class _Broken(_FakeStore):
        def full_text_search(self, collection, query, top_k=5):
            raise RuntimeError("boom")

    rm = ReflectionMemory(_Broken())
    assert rm.retrieve("x") == []
    assert rm.compact_context("x") == ""
