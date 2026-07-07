"""
Tests for harness.memory_rag.embeddings — make_embedding delegation.

Verifica que make_embedding delega correctamente en
harness.common.fallback_embedding.
"""

from __future__ import annotations

import numpy as np
import pytest

from harness.memory_rag.embeddings import EMBEDDING_DIM, make_embedding


class TestMakeEmbedding:
    """Test that make_embedding delegates correctly to common.fallback_embedding."""

    def test_returns_numpy_array(self):
        vec = make_embedding("hello")
        assert isinstance(vec, np.ndarray)

    def test_default_dimension(self):
        vec = make_embedding("hello")
        assert vec.shape == (EMBEDDING_DIM,)

    def test_custom_dimension(self):
        vec = make_embedding("hello", dim=128)
        assert vec.shape == (128,)

    def test_returned_vector_is_normalized(self):
        vec = make_embedding("hello world")
        norm = np.linalg.norm(vec)
        assert abs(norm - 1.0) < 1e-6

    def test_empty_text_returns_zeros(self):
        vec = make_embedding("")
        assert vec.shape == (EMBEDDING_DIM,)
        assert np.all(vec == 0)

    def test_deterministic_output(self):
        v1 = make_embedding("deterministic test")
        v2 = make_embedding("deterministic test")
        assert np.allclose(v1, v2)

    def test_different_inputs_different_vectors(self):
        v1 = make_embedding("implement API")
        v2 = make_embedding("security audit")
        assert not np.allclose(v1, v2)

    def test_unicode_text(self):
        vec = make_embedding("español français 中文")
        assert vec.shape == (EMBEDDING_DIM,)
        assert abs(np.linalg.norm(vec) - 1.0) < 1e-6

    def test_matches_fallback_embedding(self):
        """Verify delegation: make_embedding matches fallback_embedding."""
        from harness.common import fallback_embedding
        v1 = make_embedding("delegation test")
        v2 = fallback_embedding("delegation test")
        assert np.allclose(v1, v2)

    def test_matches_fallback_embedding_custom_dim(self):
        from harness.common import fallback_embedding
        v1 = make_embedding("delegation test", dim=128)
        v2 = fallback_embedding("delegation test", dim=128)
        assert np.allclose(v1, v2)
