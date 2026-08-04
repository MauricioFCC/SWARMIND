"""Tests TDD (spec-first) para gpu_optimize.

Contrato (spec):
- gpu_embedding(text) devuelve embedding 1D (dim=384).
- gpu_embedding(texts=[...]) devuelve embedding 2D (N, dim).
- _cpu_embedding es determinístico (mismo texto -> mismo vector).
- _cpu_embedding("") devuelve vector de ceros.
- gpu_embedding normaliza (norma 1 o ceros).
- batch_embed_messages procesa lista de mensajes.

Invariantes (PBT):
- Para cualquier texto, embedding tiene dim = 384 y norma 1 (o es cero).
- Para el mismo texto repetido, embedding idéntico (determinismo).
"""
from __future__ import annotations

import numpy as np

from harness.gpu_optimize import (
    _cpu_embedding,
    batch_embed_messages,
    gpu_embedding,
    gpu_self_test,
)


class TestGPUEmbeddingContract:
    """Contrato principal de embeddings."""

    def test_single_text_returns_1d(self) -> None:
        """Spec: gpu_embedding(text) devuelve vector 1D de dim 384."""
        vec = gpu_embedding("hola mundo")
        assert vec.ndim == 1
        assert vec.shape == (384,)

    def test_batch_returns_2d(self) -> None:
        """Spec: gpu_embedding(texts=[...]) devuelve matriz (N, 384)."""
        vecs = gpu_embedding("ignorado", texts=["a", "bb", "ccc"])
        assert vecs.ndim == 2
        assert vecs.shape == (3, 384)

    def test_empty_text_returns_zeros(self) -> None:
        """Spec: embedding de texto vacío es vector de ceros."""
        vec = _cpu_embedding("")
        assert np.all(vec == 0)

    def test_cpu_embedding_deterministic(self) -> None:
        """Spec: mismo texto -> mismo vector (determinismo)."""
        v1 = _cpu_embedding("texto de prueba")
        v2 = _cpu_embedding("texto de prueba")
        assert np.array_equal(v1, v2)

    def test_embedding_normalized(self) -> None:
        """Spec: embedding normalizado (norma 1) para texto no vacío."""
        vec = _cpu_embedding("hello world")
        norm = np.linalg.norm(vec)
        assert abs(norm - 1.0) < 1e-5

    def test_different_texts_different_embeddings(self) -> None:
        """Spec: textos distintos generan vectores distintos."""
        v1 = _cpu_embedding("alpha")
        v2 = _cpu_embedding("beta")
        assert not np.array_equal(v1, v2)

    def test_batch_messages(self) -> None:
        """Spec: batch_embed_messages procesa lista de strings."""
        messages = ["msg uno", "msg dos", "msg tres"]
        vecs = batch_embed_messages(messages)
        assert vecs is not None
        assert vecs.shape[0] == 3
        assert vecs.shape[1] == 384


class TestGPUEmbeddingInvariants:
    """Invariantes (spec-first)."""

    def test_dimension_always_384(self) -> None:
        """Invariante: cualquier embedding tiene dim 384."""
        for text in ["a", "palabra", "oración más larga con espacios y símbolos!@#"]:
            vec = _cpu_embedding(text)
            assert vec.shape == (384,)

    def test_norm_is_one_or_zero(self) -> None:
        """Invariante: norma es 1 (texto no vacío) o 0 (vacío)."""
        rng = np.random.default_rng(1)
        for _ in range(10):
            t = "".join(chr(97 + rng.integers(0, 26)) for _ in range(rng.integers(1, 30)))
            vec = _cpu_embedding(t)
            norm = np.linalg.norm(vec)
            assert abs(norm - 1.0) < 1e-5 or norm == 0

    def test_self_test_runs(self) -> None:
        """Spec: gpu_self_test ejecuta sin error y devuelve dict."""
        result = gpu_self_test()
        assert isinstance(result, dict)
