"""Constantes del paquete ``semantic_cache``.

Extraido mecanicamente de ``semantic_cache.py`` (regla AGR < 500 lineas).
Sin cambios de logica: mismos nombres y valores.
"""
from __future__ import annotations

COLLECTION_SEMANTIC_CACHE = "semantic_cache"
DEFAULT_SIMILARITY_THRESHOLD = 0.92
DEFAULT_TTL_SECONDS = 3600  # 1 hora
DEFAULT_EMBEDDING_DIM = 384
#: Cada cuantos ``set()`` se invoca ``clear_expired()`` (barrido proactivo).
#: El TTL solo se aplicaba en read perezoso: sin este sweeper la coleccion
#: en disco crecia sin cota (138 MB) pese al TTL. Barre cada 100 inserts
#: para acortar la coleccion sin escanear en cada ``set()`` (KISS/FSZ).
SWEEP_EVERY_N_SETS = 100
