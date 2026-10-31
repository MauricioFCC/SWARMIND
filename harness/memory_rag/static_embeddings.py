"""Static embeddings (model2vec) para SWARMIND — sin red ni GPU.

Spec: docs/specs/ruscadb-static-embeddings.md (RuscaDB static_embeddings.md).
Fallback determinista basado en ``harness.common.fallback_embedding`` si
model2vec no esta instalado (o falla la carga del modelo).
"""

from __future__ import annotations

import logging
from typing import Any

from harness.common import fallback_embedding as _fallback

logger = logging.getLogger("harness.memory_rag.static_embeddings")

_DEFAULT_DIM = 384


class StaticEmbeddingAdapter:
    """Generador de embeddings estaticos (CPU, sin red).

    El modelo model2vec (si esta disponible) se carga de forma perezosa y
    una sola vez por instancia; el fallback determinista garantiza throughput
    >= 1000 docs/s en CPU sin dependencia de red.
    """

    def __init__(self, dim: int = _DEFAULT_DIM, model: str | None = None) -> None:
        """Configura el adaptador.

        Args:
            dim: Dimension del espacio vectorial.
            model: Nombre de modelo model2vec (informativo).
        """
        self.dim = dim
        self.model = model or "minishlab/potion-base-32M"
        self._model: Any = None
        self._loaded = False

    def _load_model(self) -> Any:
        if self._loaded:
            return self._model
        self._loaded = True
        try:
            import model2vec  # type: ignore

            self._model = model2vec.StaticModel.from_pretrained(self.model)
        except Exception as exc:  # noqa: BLE001
            logger.debug("model2vec no disponible: %s", exc)
            self._model = None
        return self._model

    def embed(self, text: str) -> list[float]:
        """Genera un embedding para un texto.

        Args:
            text: Texto de entrada.

        Returns:
            Vector de floats de longitud ``dim``.
        """
        model = self._load_model()
        if model is not None:
            try:
                vec = model.encode([text])[0]
                out = [float(x) for x in vec]
                if len(out) != self.dim:
                    # re-proyectar por truncado/padding para mantener contrato
                    if len(out) > self.dim:
                        out = out[: self.dim]
                    else:
                        out = out + [0.0] * (self.dim - len(out))
                return out
            except Exception as exc:  # noqa: BLE001
                logger.debug("model2vec encode fallo: %s", exc)
        return [float(x) for x in _fallback(text, dim=self.dim)]

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Genera embeddings para una lista de textos.

        Args:
            texts: Lista de textos.

        Returns:
            Lista de vectores.
        """
        model = self._load_model()
        if model is not None:
            try:
                encoded = model.encode(texts)
                out: list[list[float]] = []
                for vec in encoded:
                    v = [float(x) for x in vec]
                    if len(v) != self.dim:
                        if len(v) > self.dim:
                            v = v[: self.dim]
                        else:
                            v = v + [0.0] * (self.dim - len(v))
                    out.append(v)
                return out
            except Exception as exc:  # noqa: BLE001
                logger.debug("model2vec encode_batch fallo: %s", exc)
        return [[float(x) for x in _fallback(t, dim=self.dim)] for t in texts]

    def __repr__(self) -> str:
        return f"StaticEmbeddingAdapter(dim={self.dim}, model={self.model!r})"


__all__ = ["StaticEmbeddingAdapter"]
