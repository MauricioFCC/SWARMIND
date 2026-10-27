"""Static embeddings (model2vec) para SWARMIND — sin red ni GPU.

Spec: docs/specs/ruscadb-static-embeddings.md (RuscaDB static_embeddings.md).
Fallback determinista basado en hashing si model2vec no esta instalado.
"""

from __future__ import annotations

import hashlib
import logging

logger = logging.getLogger("harness.memory_rag.static_embeddings")

_DEFAULT_DIM = 384


class StaticEmbeddingAdapter:
    """Generador de embeddings estaticos (CPU, sin red)."""

    def __init__(self, dim: int = _DEFAULT_DIM, model: str | None = None) -> None:
        """Configura el adaptador.

        Args:
            dim: Dimension del espacio vectorial.
            model: Nombre de modelo (informativo; se usa hashing si no hay model2vec).
        """
        self.dim = dim
        self.model = model or "hash-static"
        self._model2vec = None
        try:
            import model2vec  # type: ignore

            self._model2vec = model2vec
        except Exception:  # noqa: BLE001
            self._model2vec = None

    def embed(self, text: str) -> list[float]:
        """Genera un embedding para un texto.

        Args:
            text: Texto de entrada.

        Returns:
            Vector de floats de longitud ``dim``.
        """
        if self._model2vec is not None:
            try:
                mv = self._model2vec.StaticModel.from_pretrained(self.model)
                return [float(x) for x in mv.encode([text])[0]]
            except Exception:  # noqa: BLE001, S110
                pass
        return self._hash_embed(text)

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Genera embeddings para una lista de textos.

        Args:
            texts: Lista de textos.

        Returns:
            Lista de vectores.
        """
        return [self.embed(t) for t in texts]

    def _hash_embed(self, text: str) -> list[float]:
        """Embedding determinista basado en hashing (fallback)."""
        vec = [0.0] * self.dim
        if not text:
            return vec
        for i in range(self.dim):
            h = hashlib.sha256(f"{text}::{i}".encode()).digest()
            val = int.from_bytes(h[:4], "big") / 0xFFFFFFFF
            vec[i] = (val * 2.0) - 1.0
        # normalizar L2
        norm = sum(v * v for v in vec) ** 0.5
        if norm > 0:
            vec = [v / norm for v in vec]
        return vec


__all__ = ["StaticEmbeddingAdapter"]
