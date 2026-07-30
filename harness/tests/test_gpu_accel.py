"""
Tests para GPU Acceleration Module.
Verifica deteccion de hardware, operaciones aceleradas y fallback a CPU.
"""
from __future__ import annotations

import numpy as np

from harness.gpu_accel import (
    HAVE_CUDA,
    GPUContext,
    cosine_similarity,
    cosine_similarity_batch,
    normalize,
    to_cpu,
    to_gpu,
    zeros,
)


class TestGPUDetection:
    """Verificacion de deteccion de hardware."""

    def test_have_cuda_defined(self) -> None:
        """HAVE_CUDA debe ser bool."""
        assert isinstance(HAVE_CUDA, bool)

    def test_gpu_context_available(self) -> None:
        """GPUContext debe reportar disponibilidad."""
        ctx = GPUContext()
        assert ctx.available == HAVE_CUDA

    def test_gpu_context_clear_cache(self) -> None:
        """clear_cache no debe lanzar error."""
        GPUContext.clear_cache()  # should not raise


class TestCosineSimilarity:
    """Similitud coseno con GPU fallback."""

    def test_identical_vectors(self) -> None:
        """Vectores identicos → similitud 1.0."""
        v = np.random.randn(384).astype(np.float32)
        sim = cosine_similarity(v, v)
        assert abs(sim - 1.0) < 1e-5

    def test_orthogonal_vectors(self) -> None:
        """Vectores ortogonales → similitud ~0."""
        v1 = np.array([1.0, 0.0], dtype=np.float32)
        v2 = np.array([0.0, 1.0], dtype=np.float32)
        sim = cosine_similarity(v1, v2)
        assert abs(sim) < 1e-5

    def test_opposite_vectors(self) -> None:
        """Vectores opuestos → similitud -1.0."""
        v = np.random.randn(384).astype(np.float32)
        sim = cosine_similarity(v, -v)
        assert abs(sim - (-1.0)) < 1e-5

    def test_zero_vector(self) -> None:
        """Vector cero → similitud 0."""
        v1 = np.random.randn(384).astype(np.float32)
        v2 = np.zeros(384, dtype=np.float32)
        sim = cosine_similarity(v1, v2)
        assert sim == 0.0

    def test_different_dimensions(self) -> None:
        """Vectores de 768 dim (como algunos LLM)."""
        v = np.random.randn(768).astype(np.float32)
        sim = cosine_similarity(v, v)
        assert abs(sim - 1.0) < 1e-5

    def test_random_vectors_range(self) -> None:
        """Vectores aleatorios deben dar similitud entre -1 y 1."""
        for _ in range(10):
            v1 = np.random.randn(384).astype(np.float32)
            v2 = np.random.randn(384).astype(np.float32)
            sim = cosine_similarity(v1, v2)
            assert -1.0 <= sim <= 1.0


class TestCosineSimilarityBatch:
    """Similitud coseno batch con GPU fallback."""

    def test_batch_shape(self) -> None:
        """Batch debe retornar array de N scores."""
        q = np.random.randn(384).astype(np.float32)
        batch = np.random.randn(50, 384).astype(np.float32)
        scores = cosine_similarity_batch(q, batch)
        assert scores.shape == (50,)

    def test_batch_empty(self) -> None:
        """Batch vacio debe retornar array vacio."""
        q = np.random.randn(384).astype(np.float32)
        batch = np.empty((0, 384), dtype=np.float32)
        scores = cosine_similarity_batch(q, batch)
        assert scores.shape == (0,)

    def test_batch_single(self) -> None:
        """Batch de 1 elemento."""
        q = np.random.randn(384).astype(np.float32)
        batch = np.random.randn(1, 384).astype(np.float32)
        scores = cosine_similarity_batch(q, batch)
        assert scores.shape == (1,)

    def test_batch_large(self) -> None:
        """Batch de 5000 elementos (tipico de busqueda vectorial)."""
        q = np.random.randn(384).astype(np.float32)
        batch = np.random.randn(5000, 384).astype(np.float32)
        scores = cosine_similarity_batch(q, batch)
        assert scores.shape == (5000,)
        # Scores deben estar en [-1, 1] o ser NaN (cuando norma=0)
        valid = np.logical_or(np.isnan(scores), np.logical_and(-1.0 <= scores, scores <= 1.0))
        assert np.all(valid)


class TestNormalize:
    """Normalizacion L2 con GPU fallback."""

    def test_normalize_single(self) -> None:
        """Vector unico normalizado debe tener L2=1."""
        v = np.random.randn(384).astype(np.float32)
        n = normalize(v)
        assert abs(np.linalg.norm(n) - 1.0) < 1e-5

    def test_normalize_batch(self) -> None:
        """Batch normalizado debe tener L2=1 por fila."""
        batch = np.random.randn(100, 384).astype(np.float32)
        n = normalize(batch)
        for i in range(100):
            assert abs(np.linalg.norm(n[i]) - 1.0) < 1e-5

    def test_normalize_zeros(self) -> None:
        """Vector cero normalizado debe ser cero."""
        v = np.zeros(384, dtype=np.float32)
        n = normalize(v)
        assert np.allclose(n, np.zeros(384))


class TestZeros:
    """Creacion de vectores cero."""

    def test_zeros_shape(self) -> None:
        """zeros(384) debe tener shape (384,)."""
        z = zeros(384)
        assert z.shape == (384,)

    def test_zeros_values(self) -> None:
        """zeros debe ser todo ceros."""
        z = zeros(128)
        assert np.all(z == 0.0)

    def test_zeros_dtype(self) -> None:
        """zeros debe ser float32 por defecto."""
        z = zeros(64)
        assert z.dtype == np.float32


class TestToFromGPU:
    """Transferencia CPU↔GPU."""

    def test_to_gpu_cpu_fallback(self) -> None:
        """to_gpu debe funcionar (retorna tensor en GPU o array en CPU)."""
        v = np.random.randn(10).astype(np.float32)
        result = to_gpu(v)
        # Verificar que se puede convertir a numpy via to_cpu
        back = to_cpu(result)
        assert np.allclose(back, v)

    def test_to_cpu_numpy(self) -> None:
        """to_cpu con numpy debe retornar el mismo array."""
        v = np.random.randn(10).astype(np.float32)
        result = to_cpu(v)
        assert np.allclose(result, v)

    def test_roundtrip_empty(self) -> None:
        """Roundtrip con array vacio."""
        v = np.array([], dtype=np.float32)
        gpu_v = to_gpu(v)
        back = to_cpu(gpu_v)
        assert np.allclose(back, v)
