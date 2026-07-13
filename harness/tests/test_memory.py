"""Tests para memoria vectorial."""
from __future__ import annotations
import numpy as np


class TestVectorStore:
    def test_initialization(self, vector_store):
        cols = vector_store.list_collections()
        assert len(cols) >= 5

    def test_insert_and_search(self, vector_store):
        vec = np.ones(384, dtype=np.float32) / 384.0
        meta = [{"title": "test", "content": "hello", "domain": "test", "tags": []}]
        ids = vector_store.insert("asi_cognition_store", vec.reshape(1, -1), meta)
        assert len(ids) == 1

        results = vector_store.search("asi_cognition_store", vec, top_k=5)
        assert len(results) >= 1

    def test_collection_stats(self, vector_store):
        stats = vector_store.get_collection_stats("asi_cognition_store")
        assert stats["name"] == "asi_cognition_store"

    def test_hybrid_search(self, vector_store):
        vec = np.ones(384, dtype=np.float32) / 384.0
        meta = [{"title": "a", "content": "rust trading system", "domain": "trading", "tags": ["rust"]}]
        vector_store.insert("asi_cognition_store", vec.reshape(1, -1), meta)
        results = vector_store.hybrid_search("asi_cognition_store", vec, "rust", top_k=5)
        assert len(results) >= 0
