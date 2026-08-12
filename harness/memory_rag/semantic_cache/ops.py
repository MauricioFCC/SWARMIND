"""Helpers internos de ``SemanticCache`` (mixin).

Extraido mecanicamente de ``semantic_cache.py`` (regla AGR < 500 lineas).
Contiene los metodos privados de ``SemanticCache`` como mixin para que la
clase en ``core.py`` conserve la misma API sin cambios de logica ni firmas.
"""
from __future__ import annotations

import hashlib
import json
import logging
from datetime import UTC, datetime

import numpy as np

from harness.common import EMPTY_VECTOR

from .constants import (
    COLLECTION_SEMANTIC_CACHE,
    DEFAULT_EMBEDDING_DIM,
    DEFAULT_TTL_SECONDS,
)
from .models import CacheEntry

logger = logging.getLogger("harness.memory_rag.semantic_cache")


class _SemanticCacheOpsMixin:
    """Metodos privados de ``SemanticCache`` (backend y utilidades)."""

    def _normalize_similarity(self, raw_score: float) -> float:
        """Normalize raw score to a 0-1 similarity value (1 = identical).

        LanceDB usa L2 distance por defecto (0 = identical, higher = less similar),
        asi que convertimos: sim = 1/(1+L2).  L2=0 -> 1.0, L2=0.1 -> 0.91, ...

        El fallback in-memory usa cosine similarity (1 = identical, -1 = opposite),
        que se usa directamente (clamped a 0-1).
        """
        if getattr(self._store, '_lancedb_available', False):
            # LanceDB: raw_score is L2 distance -> convertir a similitud
            return 1.0 / (1.0 + raw_score)
        # In-memory: raw_score is cosine similarity -> clamp a [0, 1]
        return max(0.0, min(1.0, raw_score))

    @staticmethod
    def _hash_prompt(prompt: str) -> str:
        """Generar hash deterministico del prompt para busqueda exacta."""
        return hashlib.sha256(prompt.encode("utf-8")).hexdigest()

    def _search_exact(
        self, prompt_hash: str, agent_role: str
    ) -> tuple[str, CacheEntry] | None:
        """
        Buscar por hash exacto.

        Para LanceDB usa filtro ``WHERE`` directamente sobre la columna
        ``prompt_hash`` (mas eficiente que escanear top_k). Para el
        fallback in-memory itera sobre los items de la coleccion.
        """
        try:
            if self._store._lancedb_available and self._store._db is not None:
                tbl = self._store._db.open_table(COLLECTION_SEMANTIC_CACHE)
                # Construir WHERE con prompt_hash (+ agent_role si aplica)
                where_clause = f"prompt_hash = '{prompt_hash}'"
                if agent_role != "*":
                    where_clause += f" AND agent_role = '{agent_role}'"
                results = (
                    tbl.search(EMPTY_VECTOR.tolist())
                    .where(where_clause)
                    .limit(1)
                    .to_list()
                )
            else:
                # Fallback in-memory
                col = self._store._mem_collections.get(COLLECTION_SEMANTIC_CACHE)
                results = []
                if col:
                    for item in col.items.values():
                        meta = item.metadata
                        if meta.get("prompt_hash") != prompt_hash:
                            continue
                        r_role = meta.get("agent_role", "*")
                        if agent_role != "*" and r_role not in (agent_role, "*"):
                            continue
                        results.append({
                            "metadata": meta,
                            "score": 1.0,
                            "created_at": item.created_at,
                        })
                        break
        except Exception:  # noqa: BLE001
            return None

        for result in results:
            meta = result.get("metadata", {})
            # LanceDB almacena metadata como JSON string; convertirlo
            if isinstance(meta, str):
                try:
                    meta = json.loads(meta)
                except (json.JSONDecodeError, TypeError):
                    meta = {}
            if not isinstance(meta, dict):
                continue
            # Verificar agent_role (por si no se pudo incluir en WHERE)
            result_role = meta.get("agent_role", "*")
            if agent_role != "*" and result_role not in (agent_role, "*"):
                continue
            response = meta.get("response", "") or result.get("response", "")
            if not response:
                continue
            entry = CacheEntry(
                prompt_hash=prompt_hash,
                prompt_text=meta.get("prompt_text", "") or result.get("prompt_text", ""),
                response=response,
                agent_role=result_role,
                created_at=meta.get("created_at", "") or result.get("created_at", ""),
                last_accessed=meta.get("last_accessed", "")
                or result.get("last_accessed", ""),
                ttl_seconds=meta.get("ttl_seconds", DEFAULT_TTL_SECONDS)
                or result.get("ttl_seconds", DEFAULT_TTL_SECONDS),
                hit_count=meta.get("hit_count", 1) or result.get("hit_count", 1),
            )
            return response, entry
        return None

    def _update_hit_count(self, entry: CacheEntry) -> None:
        """Incrementar contador de hits para una entrada."""
        try:
            self._store.update_records(
                COLLECTION_SEMANTIC_CACHE,
                filters={"prompt_hash": entry.prompt_hash},
                updates={
                    "hit_count": entry.hit_count + 1,
                    "last_accessed": datetime.now(UTC).isoformat(),
                },
            )
        except Exception as _exc:  # noqa: BLE001
            logger.warning("semantic_cache: %s", _exc)

    def _delete_entry(self, prompt_hash: str) -> None:
        """
        Eliminar una entrada del cache usando prompt_hash.

        Para LanceDB usa ``tbl.delete()`` con filtro SQL directo.
        Para el fallback in-memory remueve el item del diccionario.
        """
        try:
            if self._store._lancedb_available and self._store._db is not None:
                tbl = self._store._db.open_table(COLLECTION_SEMANTIC_CACHE)
                tbl.delete(f"prompt_hash = '{prompt_hash}'")
            else:
                col = self._store._mem_collections.get(COLLECTION_SEMANTIC_CACHE)
                if col:
                    to_del = [
                        key
                        for key, item in col.items.items()
                        if item.metadata.get("prompt_hash") == prompt_hash
                    ]
                    for key in to_del:
                        del col.items[key]
            logger.debug("Cache entry deleted (hash=%s)", prompt_hash[:8])
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "Failed to delete cache entry (hash=%s): %s",
                prompt_hash[:8], exc,
            )

    @staticmethod
    def _is_expired(created_at: str, ttl_seconds: int) -> bool:
        """Verificar si una entrada ha expirado."""
        if not created_at:
            return True
        try:
            created = datetime.fromisoformat(created_at)
            elapsed = (datetime.now(UTC) - created).total_seconds()
            return elapsed > ttl_seconds
        except (ValueError, TypeError):
            return True

    @staticmethod
    def _default_embedding(text: str) -> np.ndarray:
        """
        Embedding deterministico mejorado con SHA256 + modulo.

        Mezcla el hash SHA256 del texto completo con la posicion y valor
        de cada byte para producir un vector mas discriminativo que la
        simple frecuencia de caracteres.

        Returns:
            Vector numpy normalizado de dimension ``DEFAULT_EMBEDDING_DIM``.
        """
        if not text:
            return np.zeros(DEFAULT_EMBEDDING_DIM, dtype=np.float32)

        vec = np.zeros(DEFAULT_EMBEDDING_DIM, dtype=np.float32)
        data = text.encode("utf-8", errors="replace")

        # Semilla global derivada del SHA256 del texto completo
        digest = hashlib.sha256(data).digest()
        seed_high = int.from_bytes(digest[:8], "little")
        seed_low = int.from_bytes(digest[8:16], "little")

        for i, byte_val in enumerate(data):
            # Combinacion no-lineal: posicion + byte + semillas SHA256
            mix = (i * 7 + byte_val * 3 + seed_high + (seed_low >> (i & 7)))
            idx = mix % DEFAULT_EMBEDDING_DIM
            vec[idx] += 1.0 + (byte_val / 255.0)

        norm = np.linalg.norm(vec)
        if norm > 0:
            vec /= norm

        return vec

    def _ensure_collection(self) -> None:
        """
        Asegurar que la coleccion ``semantic_cache`` existe con el schema correcto.

        Si la coleccion ya existe y tiene las columnas requeridas (``prompt_hash``,
        ``response``, etc.), la reutiliza. Si existe pero con schema incompleto
        (ej: creada por ``_ensure_lancedb_collections`` sin campos personalizados),
        la elimina y la recrea. Solo crea si no existe (no destructivo cuando el
        schema es correcto).
        """
        try:
            lancedb_available = getattr(self._store, '_lancedb_available', False)
            lancedb_db = getattr(self._store, '_db', None)

            if lancedb_available and lancedb_db is not None:
                # Usar list_tables() (no-deprecated) en lugar de table_names()
                tbl_names = set(lancedb_db.list_tables().tables)
                if COLLECTION_SEMANTIC_CACHE in tbl_names:
                    tbl = lancedb_db.open_table(COLLECTION_SEMANTIC_CACHE)
                    field_names = {f.name for f in tbl.schema}
                    # Verificar que tenga las columnas personalizadas
                    if "prompt_hash" in field_names and "response" in field_names:
                        logger.debug(
                            "Collection '%s' exists with correct schema, reusing",
                            COLLECTION_SEMANTIC_CACHE,
                        )
                        return
                    # Schema incompleto -> eliminar y recrear
                    logger.warning(
                        "Collection '%s' has incomplete schema, recreating",
                        COLLECTION_SEMANTIC_CACHE,
                    )
                    lancedb_db.drop_table(COLLECTION_SEMANTIC_CACHE)
                self._create_collection_with_schema()
            else:
                # Fallback in-memory: usar list_collections()
                existing = self._store.list_collections()
                if COLLECTION_SEMANTIC_CACHE not in existing:
                    self._create_collection_with_schema()
                else:
                    logger.debug(
                        "Collection '%s' already exists (in-memory), reusing",
                        COLLECTION_SEMANTIC_CACHE,
                    )
        except Exception as exc:  # noqa: BLE001
            # Ultimo recurso: intentar crear con overwrite
            try:
                logger.warning(
                    "Ensuring collection '%s' failed (%s), trying overwrite",
                    COLLECTION_SEMANTIC_CACHE, exc,
                )
                self._recreate_collection_with_schema()
            except Exception as inner:  # noqa: BLE001
                logger.warning(
                    "Could not ensure collection '%s': %s",
                    COLLECTION_SEMANTIC_CACHE, inner,
                )

    def _create_collection_with_schema(self) -> None:
        """Crear la coleccion con un sample row para definir el schema.

        LanceVectorStore.create_collection() usa data=[] que falla en
        LanceDB 0.33+. En su lugar, creamos la tabla directamente con
        un sample row que define todas las columnas necesarias, y luego
        borramos el placeholder.
        """
        lancedb_available = getattr(self._store, '_lancedb_available', False)
        lancedb_db = getattr(self._store, '_db', None)

        if lancedb_available and lancedb_db is not None:
            now = datetime.now(UTC).isoformat()
            sample = {
                "id": "__schema_init__",
                "vector": [0.0] * DEFAULT_EMBEDDING_DIM,
                "metadata": "{}",
                "created_at": now,
                "prompt_hash": "",
                "prompt_text": "",
                "prompt_text_short": "",
                "response": "",
                "agent_role": "",
                "hit_count": 0,
                "last_accessed": now,
                "ttl_seconds": DEFAULT_TTL_SECONDS,
            }
            lancedb_db.create_table(
                COLLECTION_SEMANTIC_CACHE,
                data=[sample],
                mode="create",
            )
            tbl = lancedb_db.open_table(COLLECTION_SEMANTIC_CACHE)
            tbl.delete("id = '__schema_init__'")
            logger.info(
                "Created LanceDB table '%s' with semantic_cache schema",
                COLLECTION_SEMANTIC_CACHE,
            )
        else:
            # Fallback: create_collection funciona para in-memory
            self._store.create_collection(COLLECTION_SEMANTIC_CACHE)
            logger.info("Created collection '%s' (in-memory)", COLLECTION_SEMANTIC_CACHE)

    def _recreate_collection_with_schema(self) -> None:
        """Forzar recreacion de la coleccion con schema completo (overwrite)."""
        lancedb_available = getattr(self._store, '_lancedb_available', False)
        lancedb_db = getattr(self._store, '_db', None)

        if lancedb_available and lancedb_db is not None:
            now = datetime.now(UTC).isoformat()
            sample = {
                "id": "__schema_init__",
                "vector": [0.0] * DEFAULT_EMBEDDING_DIM,
                "metadata": "{}",
                "created_at": now,
                "prompt_hash": "",
                "prompt_text": "",
                "prompt_text_short": "",
                "response": "",
                "agent_role": "",
                "hit_count": 0,
                "last_accessed": now,
                "ttl_seconds": DEFAULT_TTL_SECONDS,
            }
            lancedb_db.create_table(
                COLLECTION_SEMANTIC_CACHE,
                data=[sample],
                mode="overwrite",
            )
            tbl = lancedb_db.open_table(COLLECTION_SEMANTIC_CACHE)
            tbl.delete("id = '__schema_init__'")
            logger.info(
                "Recreated LanceDB table '%s' with semantic_cache schema (overwrite)",
                COLLECTION_SEMANTIC_CACHE,
            )
        else:
            # Fallback in-memory: recrear
            if COLLECTION_SEMANTIC_CACHE in self._store._mem_collections:
                del self._store._mem_collections[COLLECTION_SEMANTIC_CACHE]
            self._store.create_collection(COLLECTION_SEMANTIC_CACHE)
            logger.info("Recreated collection '%s' (in-memory overwrite)", COLLECTION_SEMANTIC_CACHE)

    def _try_remove_pending(self, prompt_hash: str) -> bool:
        """
        Eliminar entrada existente cuyo ``response`` contenga ``[PENDING]``.

        Si existe una entrada con el ``prompt_hash`` indicado y su campo
        ``response`` incluye la subcadena ``[PENDING]``, se elimina para
        evitar duplicados cuando ``set()`` inserte la respuesta real.

        Returns:
            True si se elimino una entrada pendiente, False en caso contrario.
        """
        try:
            if self._store._lancedb_available and self._store._db is not None:
                tbl = self._store._db.open_table(COLLECTION_SEMANTIC_CACHE)
                results = (
                    tbl.search(EMPTY_VECTOR.tolist())
                    .where(f"prompt_hash = '{prompt_hash}'")
                    .limit(1)
                    .to_list()
                )
                if results and "[PENDING]" in results[0].get("response", ""):
                    tbl.delete(f"prompt_hash = '{prompt_hash}'")
                    return True
            else:
                col = self._store._mem_collections.get(COLLECTION_SEMANTIC_CACHE)
                if col:
                    for key, item in list(col.items.items()):
                        if item.metadata.get("prompt_hash") == prompt_hash and "[PENDING]" in item.metadata.get("response", ""):
                                del col.items[key]
                                return True
        except Exception as _exc:  # noqa: BLE001
            logger.warning("semantic_cache: %s", _exc)
        return False
