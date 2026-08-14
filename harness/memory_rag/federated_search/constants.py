"""Constantes de la busqueda federada (extraccion mecanica)."""

DEFAULT_TOP_K_PER_BACKEND = 20  # recolectar mas de cada backend para fusion

DEFAULT_MMR_LAMBDA = 0.5        # balance relevancia (0) vs diversidad (1)

DEFAULT_CACHE_MAX_SIZE = 100

DEFAULT_CACHE_TTL_SEC = 300.0   # 5 minutos

DEFAULT_EMBEDDING_DIM = 384

_DEFAULT_BACKENDS = ("lancedb", "chroma", "qdrant")
