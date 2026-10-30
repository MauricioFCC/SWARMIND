"""Adaptador RuscaDB: usa el potencial completo del motor (multi-modelo).

Cubre las capacidades del motor expuestas por el C-ABI extendido:

- relacional: escalares tipados, indices secundarios (``create_index``);
- documental: metadata JSON persistida y consultable;
- vectorial: KNN/HNSW sobre embeddings ``float32``;
- texto: FTS BM25 (``MATCH``) con columna ``text``;
- grafo: aristas tipadas + ``TRAVERSE edges DEPTH n``;
- multimodal: blob store content-addressed (``put_blob``/``get_blob``);
- MVCC: update/delete por ``RecordId`` con visibilidad por snapshot;
- operacional: ``integrity_check``, backup online, ``explain`` y ``last_lsn``.

Degrada con elegancia si la DLL cargada no exporta las funciones extendidas:
en ese caso usa solo el subconjunto disponible.
"""

from __future__ import annotations

import datetime as _dt
import json
import logging
import os
import re
import threading

_OPEN_LOCK = threading.RLock()
import uuid
from pathlib import Path
from typing import Any

import numpy as np

from .ruscadb import (
    RuscadbError,
    capabilities,
    close,
    commit,
    create_index,
    create_table,
    delete_record,
    execute,
    explain,
    gc_blobs,
    get_blob,
    get_record,
    insert_record,
    integrity_check,
    last_inserted_id,
    last_lsn,
    list_tables,
    put_blob,
    update_record,
)
from .ruscadb import (
    backup as rdb_backup,
)
from .ruscadb import (
    open_with_options as rdb_open_opts,
)

logger = logging.getLogger("harness.memory_rag.ruscadb_store")

#: Colecciones creadas en el primer arranque.
_DEFAULT_COLLECTIONS = ("memory", "semantic_cache", "agent_workspace_logs")

#: Esquema base de una coleccion (``text`` es la columna FTS BM25).
_SCHEMA = (
    {"name": "id", "type": "Text"},
    {"name": "text", "type": "Text"},
    {"name": "metadata", "type": "Text"},
    {"name": "created_at", "type": "Text"},
)

#: Identificadores RQL seguros (evita inyeccion por nombre de coleccion/columna).
_IDENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

#: Constante de Reciprocal Rank Fusion (Cormack et al., 2009).
_RRF_K = 60


def _safe_ident(name: str) -> str:
    """Valida un identificador RQL (tabla o columna).

    Args:
        name: Identificador a validar.

    Returns:
        El identificador si es seguro.

    Raises:
        ValueError: si no cumple el patron permitido.
    """
    if not isinstance(name, str) or not _IDENT_RE.match(name):
        raise ValueError(f"identificador RQL invalido: {name!r}")
    return name


def _escape_literal(value: str) -> str:
    """Escapa un literal de texto para RQL duplicando comillas simples.

    Args:
        value: Texto a escapar.

    Returns:
        El texto listo para interpolar entre comillas simples.
    """
    return str(value).replace("'", "''")


#: Marcadores tipicos de prompt-injection / memory poisoning (OWASP ASI06, 2026).
_INJECTION_MARKERS = (
    "ignore previous instructions",
    "ignore all previous",
    "system prompt",
    "you are now",
    "disregard the above",
    "override safety",
    "<script",
    "javascript:",
)


def _looks_like_injection(text: str) -> bool:
    """Heuristica ligera de memory poisoning (OWASP ASI06).

    Args:
        text: Texto a evaluar.

    Returns:
        True si contiene marcadores sospechosos.
    """
    low = (text or "").lower()
    return any(m in low for m in _INJECTION_MARKERS)


#: Peso de confianza por procedencia (SSGM / mnemonic sovereignty, 2026).
#: ``quarantined`` = 0.0: nunca se sirve por defecto (deny-by-default).
TRUST_TIER_WEIGHTS: dict[str, float] = {
    "verified": 1.0,
    "user_stated": 1.0,
    "derived": 0.85,
    "agent": 0.7,
    "external": 0.5,
    "quarantined": 0.0,
}

#: Vida media (dias) por defecto del decaimiento temporal tipo recencia.
DEFAULT_HALF_LIFE_DAYS = 30.0


class RuscaDBStore:
    """Vector store respaldado por RuscaDB (driving adapter del C-ABI)."""

    def __init__(
        self,
        db_path: str | None = None,
        allow_fallback: bool = False,
        config: Any = None,
        blob_path: str | None = None,
        readonly: bool = False,
    ) -> None:
        """Abre la base y garantiza las colecciones base.

        Args:
            db_path: Ruta de la base; por defecto ``config.ruscadb_path``.
            allow_fallback: Compatibilidad con la firma de LanceVectorStore.
            config: MemoryConfig opcional con ``ruscadb_path``.
            blob_path: Directorio del blob store; por defecto ``<db>.blobs``.
            readonly: Abre en modo solo lectura (lectores concurrentes).
        """
        if db_path is None and config is None:
            try:
                from .memory_config import get_memory_config

                config = get_memory_config()
            except Exception:  # noqa: BLE001
                config = None
        resolved = db_path or (config.ruscadb_path if config else None)
        if not resolved:
            # Default repo-local (mirrors LANCEDB_ROOT) para evitar colisiones
            # en CWD y no tocar la DB personal durante tests/CI.
            base_dir = Path(__file__).resolve().parent.parent / "db"
            base_dir.mkdir(parents=True, exist_ok=True)
            resolved = str(base_dir / "ruscadb.db")
        # Guardia: bajo pytest nunca tocar la DB personal, aunque el entorno
        # (setx) la apunte. Usa un DB compartido por proceso (no por instancia)
        # para evitar proliferacion de archivos; la contencion se serializa con
        # _OPEN_LOCK (RLock) en open/close.
        if os.environ.get("PYTEST_CURRENT_TEST") and not db_path:
            base_dir = Path(__file__).resolve().parent.parent / "db" / "test"
            base_dir.mkdir(parents=True, exist_ok=True)
            resolved = str(base_dir / "ruscadb.db")
        self.db_path = resolved
        self._allow_fallback = allow_fallback
        self._caps = capabilities()
        self._collections: set[str] = set()
        self._text_columns: dict[str, str] = {}
        self._embedding_dim: int = 384
        self._blob_path = blob_path or self._default_blob_path(self.db_path)
        self._readonly = readonly
        with _OPEN_LOCK:
            self._handle = rdb_open_opts(
                self.db_path,
                pool_capacity=8,
                blob_path=None if readonly else self._blob_path,
                readonly=readonly,
            )
        if not readonly:
            self._ensure_collections()
        # Cache de resultados de RQL (Spec ruscadb-query-cache) — in-memory, TTL 300s.
        from .query_cache import QueryResultCache

        self._query_cache = QueryResultCache(ttl_sec=300.0)
        self._query_cache_enabled = True
        # Metricas del cache semantico persistente (Spec ruscadb-semantic-cache).
        self._cache_hits = 0
        self._cache_misses = 0
        self._cache_expired = 0
        self._cache_sets = 0

    @staticmethod
    def _default_blob_path(db_path: str) -> str:
        """Deriva el directorio de blobs hermano de la base.

        Args:
            db_path: Ruta del archivo de la base.

        Returns:
            Ruta ``<stem>.blobs`` junto a la base.
        """
        path = Path(db_path)
        return str(path.parent / f"{path.stem}.blobs")

    # ------------------------------------------------------------------
    # Catalog
    # ------------------------------------------------------------------

    def list_collections(self) -> list[str]:
        """Lista las colecciones visibles (excluye tablas internas ``_*``)."""
        try:
            names = list_tables(self._handle)
            if names:
                self._collections = {name for name in names if not name.startswith("_")}
                return sorted(self._collections)
        except RuscadbError as exc:
            logger.debug("list_tables fallo: %s", exc)
        return sorted(self._collections)

    def create_collection(self, name: str, schema: Any = None) -> None:
        """Crea una coleccion con el esquema base e indices secundarios.

        Args:
            name: Nombre de la coleccion (identificador RQL valido).
            schema: Ignorado; se conserva por compatibilidad de firma.
        """
        _safe_ident(name)
        if name in self.list_collections():
            self._collections.add(name)
            return
        try:
            create_table(self._handle, name, list(_SCHEMA))
            self._index(name, "id")
            self._index(name, "created_at")
        except RuscadbError as exc:
            logger.debug("create_collection '%s' fallo: %s", name, exc)
        self._collections.add(name)

    def _index(self, collection: str, column: str) -> None:
        """Crea un indice secundario si la DLL lo soporta (best-effort).

        Args:
            collection: Tabla destino.
            column: Columna a indexar.
        """
        if not self._caps.get("ruscadb_create_index"):
            return
        try:
            create_index(self._handle, collection, column)
        except RuscadbError as exc:
            logger.debug("indice %s.%s no creado: %s", collection, column, exc)

    def _ensure_collections(self) -> None:
        """Crea las colecciones base y la tabla interna de mapeo (idempotente)."""
        existing = set(list_tables(self._handle))
        if "_rid_map" not in existing:
            try:
                create_table(
                    self._handle,
                    "_rid_map",
                    [
                        {"name": "id", "type": "Text"},
                        {"name": "collection", "type": "Text"},
                        {"name": "rid", "type": "Text"},
                    ],
                )
                self._index("_rid_map", "id")
            except RuscadbError as exc:
                logger.debug("_rid_map no creada: %s", exc)
        visible = set(self.list_collections())
        for name in _DEFAULT_COLLECTIONS:
            if name in visible:
                continue
            self.create_collection(name)

    def _text_column(self, collection: str) -> str:
        """Detecta la columna FTS disponible (``text`` o ``metadata``).

        Las bases creadas antes del esquema con ``text`` no tienen esa columna;
        en ese caso se usa ``metadata`` para no romper la busqueda.

        Args:
            collection: Tabla a inspeccionar.

        Returns:
            Nombre de la columna indexable con ``MATCH``.
        """
        if collection in self._text_columns:
            return self._text_columns[collection]
        column = "metadata"
        try:
            execute(self._handle, f"SELECT text FROM {_safe_ident(collection)} LIMIT 1")  # nosec B608
            column = "text"
        except RuscadbError:
            column = "metadata"
        self._text_columns[collection] = column
        return column

    # ------------------------------------------------------------------
    # Write path
    # ------------------------------------------------------------------

    @staticmethod
    def _derive_text(metadata: dict[str, Any]) -> str:
        """Extrae el texto indexable de la metadata.

        Args:
            metadata: Metadata del registro.

        Returns:
            Texto para BM25 (campos conocidos o valores string concatenados).
        """
        for key in ("text", "content", "summary", "title", "description"):
            value = metadata.get(key)
            if isinstance(value, str) and value.strip():
                return value
        parts = [str(v) for v in metadata.values() if isinstance(v, (str, int, float))]
        return " ".join(parts)

    def insert(
        self,
        collection: str,
        vectors: Any,
        metadata: list[dict[str, Any]],
        now: str | None = None,
        edges: list[list[dict[str, str]]] | None = None,
        texts: list[str] | None = None,
    ) -> list[str]:
        """Inserta vectores + metadata (+ aristas) en una sola transaccion.

        Args:
            collection: Coleccion destino.
            vectors: Matriz ``(n, dim)`` o vector unico.
            metadata: Lista de dicts de metadata por fila.
            now: Timestamp ISO; por defecto UTC actual.
            edges: Aristas por fila (``[{"label": str, "target": ULID}]``).
            texts: Texto indexable explicito por fila (opcional).

        Returns:
            Lista de ids logicos insertados.
        """
        _safe_ident(collection)
        if collection not in self.list_collections():
            self.create_collection(collection)
        column = self._text_column(collection)
        now = now or _dt.datetime.now(_dt.UTC).isoformat()
        ids: list[str] = []
        arr = np.asarray(vectors, dtype=np.float32)
        if arr.ndim == 1:
            arr = arr.reshape(1, -1)
        for i in range(arr.shape[0]):
            rid = str(uuid.uuid4())
            ids.append(rid)
            meta = dict(metadata[i]) if i < len(metadata) else {}
            text = texts[i] if texts and i < len(texts) else self._derive_text(meta)
            # Provenance / trust tagging (OWASP ASI06, frontier 2026): aditivo,
            # nunca pisa valores explicitos del caller.
            import hashlib as _hl
            if "source" not in meta:
                meta["source"] = "agent"
            if "trust_tier" not in meta:
                meta["trust_tier"] = "user_stated"
            if "content_hash" not in meta:
                meta["content_hash"] = _hl.sha256((text or "").encode("utf-8")).hexdigest()
            if _looks_like_injection(text) or _looks_like_injection(str(meta)):
                meta["trust_tier"] = "quarantined"
                logger.warning("memory_guard: entrada en cuarentena (posible poisoning)")
            scalars: dict[str, Any] = {
                "id": rid,
                "metadata": json.dumps(meta, ensure_ascii=False),
                "created_at": now,
            }
            if column == "text":
                scalars["text"] = text
            record: dict[str, Any] = {
                "scalars": scalars,
                "vector": arr[i].tolist(),
                "vector_meta": {
                    "model_id": "swarmind",
                    "dim": int(arr.shape[1]),
                    "metric": "L2",
                },
            }
            if edges and i < len(edges) and edges[i]:
                resolved: list[dict[str, str]] = []
                for edge in edges[i]:
                    target = str(edge.get("target", ""))
                    if target and not self._looks_like_ulid(target):
                        target = self._find_rid(collection, target) or target
                    resolved.append({"label": str(edge.get("label", "link")), "target": target})
                record["edges"] = resolved
            try:
                insert_record(self._handle, collection, record)
                rid_rusca = last_inserted_id()
                if rid_rusca:
                    self._map_rid(collection, rid, rid_rusca)
            except RuscadbError as exc:
                logger.warning("insert en '%s' fallo: %s", collection, exc)
        self._commit()
        self.invalidate_cache(collection)
        return ids

    def _map_rid(self, collection: str, logical_id: str, rid_rusca: str) -> None:
        """Registra el mapeo id logico -> ULID fisico en ``_rid_map``.

        Args:
            collection: Coleccion del registro.
            logical_id: Id logico (UUID) usado por SWARMIND.
            rid_rusca: ULID devuelto por el motor.
        """
        try:
            insert_record(
                self._handle,
                "_rid_map",
                {
                    "scalars": {
                        "id": logical_id,
                        "collection": collection,
                        "rid": rid_rusca,
                    }
                },
            )
        except RuscadbError as exc:
            logger.debug("no se pudo mapear _rid: %s", exc)

    def update_records(self, collection: str, records: list[dict[str, Any]]) -> None:
        """Actualiza registros por ``_rid`` (MVCC) o por ``id``.

        Args:
            collection: Coleccion destino.
            records: Registros con ``metadata`` y opcionalmente ``vector``.
        """
        _safe_ident(collection)
        for rec in records:
            meta = dict(rec.get("metadata") or {})
            text = rec.get("text") or self._derive_text(meta)
            scalars = {
                "metadata": json.dumps(meta, ensure_ascii=False),
                "text": text,
            }
            rid = meta.get("_rid")
            try:
                if rid and self._caps.get("ruscadb_update_record"):
                    update_record(self._handle, collection, str(rid), scalars)
                elif rec.get("id"):
                    self._update_by_logical_id(collection, str(rec["id"]), scalars)
            except RuscadbError as exc:
                logger.warning("update en '%s' fallo: %s", collection, exc)
        self._commit()

    def _update_by_logical_id(
        self, collection: str, logical_id: str, scalars: dict[str, Any]
    ) -> None:
        """Actualiza por columna ``id`` usando RQL parametrizado por escape.

        Args:
            collection: Tabla destino.
            logical_id: Valor de la columna ``id``.
            scalars: Columnas nuevas.
        """
        assignments = ", ".join(
            f"{_safe_ident(col)} = '{_escape_literal(val)}'"
            for col, val in scalars.items()
        )
        execute(
            self._handle,
            f"UPDATE {collection} SET {assignments} "  # nosec B608
            f"WHERE id = '{_escape_literal(logical_id)}'",
        )

    def delete(self, collection: str, ids: list[str]) -> int:
        """Borra logicamente registros por id logico o ULID.

        Args:
            collection: Coleccion destino.
            ids: Ids logicos (UUID) o ULIDs fisicos.

        Returns:
            Numero de filas borradas.
        """
        _safe_ident(collection)
        deleted = 0
        for ident in ids:
            rid = ident
            if self._caps.get("ruscadb_delete_record"):
                if not self._looks_like_ulid(ident):
                    rid = self._find_rid(collection, ident) or ""
                if rid:
                    try:
                        deleted += int(delete_record(self._handle, collection, rid))
                        continue
                    except RuscadbError as exc:
                        logger.debug("delete_record fallo: %s", exc)
            try:
                rows = execute(
                    self._handle,
                    f"DELETE FROM {collection} WHERE id = '{_escape_literal(ident)}'",  # nosec B608
                )
                if rows:
                    deleted += 1
            except RuscadbError as exc:
                logger.warning("delete en '%s' fallo: %s", collection, exc)
        self._commit()
        self.invalidate_cache(collection)
        return deleted

    @staticmethod
    def _looks_like_ulid(value: str) -> bool:
        """Heuristica de ULID (26 caracteres Crockford base32).

        Args:
            value: Identificador a clasificar.

        Returns:
            True si parece un ULID fisico de RuscaDB.
        """
        return len(value) == 26 and value.isalnum() and value.upper() == value

    def _find_rid(self, collection: str, logical_id: str) -> str | None:
        """Busca el ULID fisico a partir del id logico.

        Args:
            collection: Tabla destino.
            logical_id: Valor de la columna ``id``.

        Returns:
            El ULID fisico, o None si no se conoce.
        """
        try:
            rows = execute(
                self._handle,
                "SELECT rid FROM _rid_map "  # nosec B608
                f"WHERE id = '{_escape_literal(logical_id)}' "
                f"AND collection = '{_escape_literal(collection)}' LIMIT 1",
            )
            parsed = json.loads(rows) if isinstance(rows, str) else rows
            for row in parsed or []:
                rid = self._unwrap_scalar(row.get("rid"))
                if rid:
                    return str(rid)
        except (RuscadbError, json.JSONDecodeError, TypeError):
            pass
        return None

    def get_record(self, collection: str, rid: str) -> dict[str, Any] | None:
        """Devuelve el registro completo del motor por ULID.

        Args:
            collection: Tabla destino.
            rid: ULID fisico.

        Returns:
            Registro crudo del motor, o None si no existe.
        """
        if not self._caps.get("ruscadb_get_record"):
            return None
        try:
            return get_record(self._handle, collection, rid)
        except RuscadbError as exc:
            logger.debug("get_record fallo: %s", exc)
            return None

    def resolve_rid(self, collection: str, logical_id: str) -> str | None:
        """Resuelve el ULID fisico de un id logico.

        Args:
            collection: Coleccion del registro.
            logical_id: Id logico usado por SWARMIND.

        Returns:
            El ULID fisico, o None si no esta mapeado.
        """
        return self._find_rid(collection, logical_id)

    # ------------------------------------------------------------------
    # Read path
    # ------------------------------------------------------------------

    @staticmethod
    def _unwrap_scalar(value: Any) -> Any:
        """Desenvuelve un ``ScalarValue`` serializado (``{"Text": ...}``).

        Args:
            value: Valor crudo de una fila RQL.

        Returns:
            El valor escalar nativo.
        """
        if isinstance(value, dict) and len(value) == 1:
            key = next(iter(value))
            if key in ("Text", "Int", "UInt", "Float", "Bool", "Null", "TimestampMillis"):
                return value[key]
        return value

    def _parse_rows(self, rows: Any) -> list[dict[str, Any]]:
        """Normaliza filas RQL a ``{id, text, metadata}``.

        Args:
            rows: JSON serializado o lista de filas del motor.

        Returns:
            Lista de registros normalizados.
        """
        parsed = json.loads(rows) if isinstance(rows, str) else rows
        out: list[dict[str, Any]] = []
        for row in parsed or []:
            if not isinstance(row, dict):
                continue
            meta = self._unwrap_scalar(row.get("metadata"))
            if isinstance(meta, str):
                try:
                    meta = json.loads(meta)
                except json.JSONDecodeError:
                    meta = {"raw": meta}
            elif not isinstance(meta, dict):
                meta = {"value": meta}
            out.append(
                {
                    "id": self._unwrap_scalar(row.get("id")),
                    "text": self._unwrap_scalar(row.get("text")) or "",
                    "metadata": meta,
                    "created_at": self._unwrap_scalar(row.get("created_at")),
                    "raw": row,
                }
            )
        return out

    # ------------------------------------------------------------------
    # Gobernanza de retrieval: confianza + recencia
    # ------------------------------------------------------------------

    @staticmethod
    def _matches_filters(item: dict[str, Any], filters: dict[str, Any] | None) -> bool:
        """Comprueba igualdad campo->valor sobre el item o su metadata.

        Args:
            item: Resultado normalizado (``id``/``text``/``metadata``/...).
            filters: Filtros pedidos por el llamador (None = sin filtro).

        Returns:
            True si el item satisface todos los filtros.
        """
        if not filters:
            return True
        meta = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
        for key, value in filters.items():
            if item.get(key) == value or meta.get(key) == value:
                continue
            return False
        return True

    @staticmethod
    def _trust_options(kwargs: dict[str, Any]) -> dict[str, Any]:
        """Extrae las opciones de gobernanza de retrieval de los kwargs.

        Args:
            kwargs: kwargs recibidos por ``search``/``full_text_search``/``hybrid_search``.

        Returns:
            dict con ``allow_quarantined``, ``min_trust`` y ``half_life_days``.
        """
        return {
            "allow_quarantined": bool(kwargs.get("allow_quarantined", False)),
            "min_trust": float(kwargs.get("min_trust", 0.0)),
            "half_life_days": kwargs.get("half_life_days"),
        }

    @staticmethod
    def _age_days(created_at: Any, reference: _dt.datetime) -> float | None:
        """Antiguedad en dias de un timestamp ISO-8601.

        Args:
            created_at: Timestamp (str ISO o datetime).
            reference: Instante de referencia (UTC aware).

        Returns:
            Dias transcurridos, o ``None`` si no se puede interpretar.
        """
        if isinstance(created_at, _dt.datetime):
            moment = created_at
        elif isinstance(created_at, str) and created_at:
            try:
                moment = _dt.datetime.fromisoformat(created_at)
            except ValueError:
                return None
        else:
            return None
        if moment.tzinfo is None:
            moment = moment.replace(tzinfo=_dt.UTC)
        delta = reference - moment.astimezone(_dt.UTC)
        return max(delta.total_seconds() / 86400.0, 0.0)

    def _apply_trust_and_recency(
        self,
        items: list[dict[str, Any]],
        top_k: int,
        *,
        allow_quarantined: bool = False,
        min_trust: float = 0.0,
        half_life_days: float | None = None,
        now: _dt.datetime | None = None,
    ) -> list[dict[str, Any]]:
        """Filtra por confianza y pondera por recencia (retrieval gobernado).

        Modelo (frontier 2026): el score final es
        ``score * trust_weight * 0.5 ** (edad_dias / half_life)``. Las entradas
        en cuarentena se excluyen salvo ``allow_quarantined=True``
        (deny-by-default, MAPLE-Guard). Sin ``half_life_days`` no hay
        decaimiento (ranking identico al del motor).

        Args:
            items: Resultados ya puntuados por el motor.
            top_k: Numero maximo de resultados devueltos.
            allow_quarantined: Servir tambien entradas en cuarentena.
            min_trust: Peso minimo de confianza aceptado.
            half_life_days: Vida media del decaimiento en dias (None = off).
            now: Instante de referencia para la edad (default UTC actual).

        Returns:
            Lista filtrada, re-puntuada y ordenada por score descendente.
        """
        reference = now or _dt.datetime.now(_dt.UTC)
        kept: list[dict[str, Any]] = []
        for item in items:
            meta = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
            tier = str(meta.get("trust_tier") or "user_stated")
            weight = TRUST_TIER_WEIGHTS.get(tier)
            if weight is None:
                weight = TRUST_TIER_WEIGHTS["external"]
            if tier == "quarantined" and not allow_quarantined:
                logger.debug("retrieval: entrada en cuarentena excluida id=%s", item.get("id"))
                continue
            if weight < min_trust:
                continue
            recency = 1.0
            if half_life_days:
                age = self._age_days(
                    item.get("created_at") or meta.get("created_at"), reference
                )
                if age is not None:
                    recency = 0.5 ** (age / float(half_life_days))
            base = float(item.get("score", 0.0))
            item["trust_tier"] = tier
            item["trust_weight"] = weight
            item["recency_weight"] = recency
            item["score"] = base * weight * recency
            kept.append(item)
        kept.sort(key=lambda entry: entry.get("score", 0.0), reverse=True)
        return kept[:top_k]

    def search(
        self, collection: str, query_vector: Any, top_k: int = 5, **kwargs: Any
    ) -> list[dict[str, Any]]:
        """Busqueda densa KNN (HNSW) con gobernanza de confianza/recencia.

        Args:
            collection: Coleccion destino.
            query_vector: Vector de consulta.
            top_k: Numero de vecinos.
            **kwargs: ``allow_quarantined``, ``min_trust``, ``half_life_days``.

        Returns:
            Lista de ``{id, metadata, score, trust_tier}`` ordenada por cercania.
        """
        qv = np.asarray(query_vector, dtype=np.float32).tolist()
        try:
            rows = execute(
                self._handle,
                f"SELECT * FROM {_safe_ident(collection)} "  # nosec B608
                f"KNN embedding <|{int(top_k)}|> {json.dumps(qv)}",
            )
        except RuscadbError as exc:
            logger.warning("search en '%s' fallo: %s", collection, exc)
            return []
        out = self._parse_rows(rows)
        out = [item for item in out if self._matches_filters(item, kwargs.get("filters"))]
        for rank, item in enumerate(out):
            item["score"] = 1.0 / (rank + 1)
        return self._apply_trust_and_recency(
            out, top_k, **self._trust_options(kwargs)
        )

    def full_text_search(
        self, collection: str, query: str, top_k: int = 10, **kwargs: Any
    ) -> list[dict[str, Any]]:
        """Busqueda FTS BM25 (``MATCH``) con gobernanza de confianza.

        Args:
            collection: Coleccion destino.
            query: Texto de consulta.
            top_k: Numero maximo de resultados.
            **kwargs: ``filters``, ``allow_quarantined``, ``min_trust``,
                ``half_life_days``.

        Returns:
            Lista de ``{id, metadata, score, trust_tier}`` ordenada por BM25.
        """
        if not query.strip():
            return []
        column = self._text_column(collection)
        try:
            rows = execute(
                self._handle,
                f"SELECT * FROM {_safe_ident(collection)} "  # nosec B608
                f"WHERE MATCH({column}, '{_escape_literal(query)}')",
            )
        except RuscadbError as exc:
            logger.warning("full_text_search en '%s' fallo: %s", collection, exc)
            return []
        out = self._parse_rows(rows)
        out = [item for item in out if self._matches_filters(item, kwargs.get("filters"))]
        for rank, item in enumerate(out):
            item["score"] = 1.0 / (rank + 1)
        return self._apply_trust_and_recency(
            out, top_k, **self._trust_options(kwargs)
        )

    def hybrid_search(
        self,
        collection: str,
        query_vector: Any,
        query_text: str = "",
        top_k: int = 5,
        **kwargs: Any,
    ) -> list[dict[str, Any]]:
        """Fusiona KNN + BM25 con Reciprocal Rank Fusion (RRF) gobernado.

        Implementa RRF (Cormack et al., 2009) con ``k=60``: robusta a escalas
        distintas de score y estandar en retrieval hibrido (RAG-Fusion). El
        resultado se pondera por confianza de procedencia y, opcionalmente,
        por recencia.

        Args:
            collection: Coleccion destino.
            query_vector: Vector de consulta.
            query_text: Texto de consulta (opcional).
            top_k: Numero de resultados fusionados.
            **kwargs: ``filters``, ``allow_quarantined``, ``min_trust``,
                ``half_life_days``.

        Returns:
            Lista fusionada, deduplicada y gobernada por id.
        """
        options = self._trust_options(kwargs)
        filters = kwargs.get("filters")
        dense = self.search(
            collection, query_vector, top_k=top_k * 2, **options, filters=filters
        )
        sparse = (
            self.full_text_search(
                collection, query_text, top_k=top_k * 2, **options, filters=filters
            )
            if query_text
            else []
        )
        fused: dict[str, dict[str, Any]] = {}
        for source, items in (("dense", dense), ("sparse", sparse)):
            for rank, item in enumerate(items):
                key = str(item["id"])
                if key not in fused:
                    fused[key] = dict(item)
                    # RRF puro: el score del motor ya trae el peso de confianza
                    # aplicado; se descarta para no ponderarlo dos veces.
                    fused[key]["score"] = 0.0
                entry = fused[key]
                entry[f"{source}_rank"] = rank
                entry["score"] += 1.0 / (_RRF_K + rank + 1)
        ranked = sorted(fused.values(), key=lambda item: item["score"], reverse=True)
        return self._apply_trust_and_recency(ranked, top_k, **options)

    def graph_traverse(
        self,
        collection: str,
        depth: int = 2,
        start: str | None = None,
        **kwargs: Any,
    ) -> list[dict[str, Any]]:
        """Recorre el grafo tipado de la coleccion (CSR o BFS por RecordId).

        Con ``start`` se hace BFS sobre las aristas del registro (RQL no admite
        ``TRAVERSE`` con ``WHERE``); sin ``start`` se usa el recorrido nativo
        ``TRAVERSE edges DEPTH n`` del motor. Los nodos en cuarentena se
        excluyen por defecto, igual que en el retrieval (OWASP ASI06).

        Args:
            collection: Coleccion destino.
            depth: Profundidad de recorrido (>= 1).
            start: ULID de inicio (opcional).
            **kwargs: ``allow_quarantined``, ``min_trust``, ``half_life_days``.

        Returns:
            Nodos alcanzables normalizados.
        """
        depth = max(1, int(depth))
        options = self._trust_options(kwargs)
        if start:
            nodes = self._traverse_from(collection, start, depth)
        else:
            sql = f"SELECT * FROM {_safe_ident(collection)} TRAVERSE edges DEPTH {depth}"  # nosec B608
            try:
                rows = execute(self._handle, sql)
            except RuscadbError as exc:
                logger.warning("graph_traverse en '%s' fallo: %s", collection, exc)
                return []
            nodes = self._parse_rows(rows)
        for rank, item in enumerate(nodes):
            item.setdefault("score", 1.0 / (rank + 1))
        return self._apply_trust_and_recency(nodes, top_k=len(nodes), **options)

    def _traverse_from(
        self, collection: str, start: str, depth: int
    ) -> list[dict[str, Any]]:
        """BFS sobre las aristas de un nodo usando ``get_record``.

        Args:
            collection: Coleccion destino.
            start: ULID del nodo de inicio.
            depth: Profundidad maxima.

        Returns:
            Nodos alcanzables (incluye el inicio).
        """
        visited: set[str] = set()
        frontier = [start]
        out: list[dict[str, Any]] = []
        for _ in range(depth):
            next_frontier: list[str] = []
            for rid in frontier:
                if rid in visited:
                    continue
                visited.add(rid)
                record = self.get_record(collection, rid)
                if not record:
                    continue
                out.append(self._record_to_item(record))
                for edge in (record.get("edges") or {}).get("out") or []:
                    target = edge.get("node")
                    if isinstance(target, str) and target not in visited:
                        next_frontier.append(target)
            frontier = next_frontier
            if not frontier:
                break
        return out

    def _record_to_item(self, record: dict[str, Any]) -> dict[str, Any]:
        """Normaliza un registro crudo del motor al formato de retrieval.

        Args:
            record: Registro devuelto por :meth:`get_record`.

        Returns:
            ``{id, text, metadata, raw}``.
        """
        scalars = record.get("scalars") or {}
        return {
            "id": self._unwrap_scalar(scalars.get("id")),
            "text": self._unwrap_scalar(scalars.get("text")) or "",
            "metadata": self._record_metadata(record),
            "raw": record,
        }

    def get_collection_stats(self, name: str) -> dict[str, Any]:
        """Devuelve el conteo de filas y el LSN de la coleccion.

        Args:
            name: Coleccion a inspeccionar.

        Returns:
            ``{"count": int, "last_lsn": int}``.
        """
        count = 0
        try:
            rows = execute(self._handle, f"SELECT COUNT(*) as n FROM {_safe_ident(name)}")  # nosec B608
            parsed = json.loads(rows) if isinstance(rows, str) else rows
            count = int(self._unwrap_scalar(parsed[0].get("n", 0))) if parsed else 0
        except (RuscadbError, ValueError, TypeError, IndexError):
            count = 0
        return {
            "name": name,
            "item_count": count,
            "count": count,
            "schema": {},
            "last_updated": None,
            "last_lsn": self.current_lsn(),
        }

    def execute(self, sql: str) -> Any:
        """Ejecuta RQL crudo (escotilla para consultas avanzadas).

        Args:
            sql: Consulta RQL.

        Returns:
            JSON serializado del motor, o None si falla.
        """
        try:
            return execute(self._handle, sql)
        except RuscadbError as exc:
            logger.warning("execute fallo: %s", exc)
            return None

    def cached_execute(self, sql: str, collection: str | None = None) -> Any:
        """Ejecuta RQL con cache de resultados (Spec ruscadb-query-cache).

        Args:
            sql: Consulta RQL.
            collection: Coleccion afectada (para invalidacion).

        Returns:
            Resultado cacheado o fresco.
        """
        if not self._query_cache_enabled:
            return self.execute(sql)
        cached = self._query_cache.get(sql)
        if cached is not None:
            return cached
        result = self.execute(sql)
        self._query_cache.set(sql, result, collection=collection)
        return result

    def invalidate_cache(self, collection: str) -> int:
        """Invalida la cache de resultados para una coleccion.

        Args:
            collection: Coleccion a invalidar.

        Returns:
            Numero de entradas invalidadas.
        """
        return self._query_cache.invalidate(collection)

    def query_cache_stats(self) -> dict[str, int]:
        """Estadisticas de la cache de resultados."""
        return self._query_cache.stats()

    # ------------------------------------------------------------------
    # Multimodal (blob store content-addressed)
    # ------------------------------------------------------------------

    def put_blob(self, data: bytes) -> str:
        """Almacena un blob y devuelve su hash SHA-256.

        Args:
            data: Contenido binario.

        Returns:
            Hash del blob (cadena vacia si la DLL no lo soporta).
        """
        if not self._caps.get("ruscadb_put_blob"):
            return ""
        try:
            return put_blob(self._handle, data)
        except RuscadbError as exc:
            logger.warning("put_blob fallo: %s", exc)
            return ""

    def get_blob(self, blob_hash: str) -> bytes:
        """Lee un blob por su hash.

        Args:
            blob_hash: Hash devuelto por :meth:`put_blob`.

        Returns:
            Contenido binario (vacio si no existe).
        """
        if not blob_hash or not self._caps.get("ruscadb_get_blob"):
            return b""
        try:
            return get_blob(self._handle, blob_hash)
        except RuscadbError as exc:
            logger.warning("get_blob fallo: %s", exc)
            return b""

    def attach_blob(self, collection: str, logical_id: str, data: bytes) -> str:
        """Adjunta un blob a un registro actualizando su metadata.

        Args:
            collection: Coleccion destino.
            logical_id: Id logico del registro.
            data: Contenido binario.

        Returns:
            Hash del blob (cadena vacia si no se pudo).
        """
        blob_hash = self.put_blob(data)
        if not blob_hash:
            return ""
        rid = self._find_rid(collection, logical_id)
        if not rid:
            return blob_hash
        record = self.get_record(collection, rid)
        if not record:
            return blob_hash
        meta = self._record_metadata(record)
        meta["blob_hash"] = blob_hash
        meta["_rid"] = rid
        try:
            update_record(
                self._handle,
                collection,
                rid,
                {"metadata": json.dumps(meta, ensure_ascii=False)},
            )
            self._commit()
        except RuscadbError as exc:
            logger.warning("attach_blob fallo: %s", exc)
        return blob_hash

    def gc_blobs(self) -> int:
        """Purga blobs sin referencias vivas.

        Returns:
            Numero de blobs eliminados.
        """
        if not self._caps.get("ruscadb_gc_blobs"):
            return 0
        try:
            return gc_blobs(self._handle)
        except RuscadbError as exc:
            logger.warning("gc_blobs fallo: %s", exc)
            return 0

    def _record_metadata(self, record: dict[str, Any]) -> dict[str, Any]:
        """Extrae la metadata de un registro crudo del motor.

        Args:
            record: Registro devuelto por :meth:`get_record`.

        Returns:
            Metadata como dict.
        """
        scalars = record.get("scalars") or {}
        meta_raw = self._unwrap_scalar(scalars.get("metadata"))
        if isinstance(meta_raw, str):
            try:
                return json.loads(meta_raw)
            except json.JSONDecodeError:
                return {"raw": meta_raw}
        return meta_raw if isinstance(meta_raw, dict) else {}

    # ------------------------------------------------------------------
    # Operacional
    # ------------------------------------------------------------------

    def integrity(self) -> dict[str, Any]:
        """Ejecuta la verificacion de integridad del motor."""
        if not self._caps.get("ruscadb_integrity_check"):
            return {"available": False}
        try:
            return integrity_check(self._handle)
        except RuscadbError as exc:
            logger.warning("integrity_check fallo: %s", exc)
            return {"available": False, "error": str(exc)}

    def backup(self, destination: str) -> int:
        """Crea un backup online de la base.

        Args:
            destination: Directorio destino.

        Returns:
            Numero de archivos copiados.
        """
        if not self._caps.get("ruscadb_backup"):
            return 0
        try:
            return rdb_backup(self._handle, destination)
        except RuscadbError as exc:
            logger.warning("backup fallo: %s", exc)
            return 0

    def current_lsn(self) -> int:
        """Devuelve el LSN del ultimo commit."""
        if not self._caps.get("ruscadb_last_lsn"):
            return 0
        try:
            return last_lsn(self._handle)
        except RuscadbError:
            return 0

    def explain(self, sql: str) -> list[str]:
        """Devuelve el plan de ejecucion de una consulta RQL.

        Args:
            sql: Consulta a inspeccionar.

        Returns:
            Lineas del plan.
        """
        if not self._caps.get("ruscadb_explain"):
            return []
        try:
            return explain(self._handle, sql)
        except RuscadbError as exc:
            logger.warning("explain fallo: %s", exc)
            return []

    def delete_collection(self, name: str) -> None:
        """Borra logicamente todas las filas de una coleccion.

        Args:
            name: Coleccion a vaciar.
        """
        try:
            execute(self._handle, f"DELETE FROM {_safe_ident(name)}")  # nosec B608
            self._commit()
        except RuscadbError as exc:
            logger.debug("delete_collection '%s' fallo: %s", name, exc)
        self._collections.discard(name)

    def clear(self) -> None:
        """Vacia todas las colecciones visibles y el mapeo interno."""
        for collection in list(self.list_collections()):
            self.delete_collection(collection)
        try:
            execute(self._handle, "DELETE FROM _rid_map")
            self._commit()
        except RuscadbError:
            pass
        if not self._readonly:
            self._ensure_collections()

    def rerank(self, collection: str, query: str, candidates: list[dict[str, Any]], top_k: int = 5) -> list[dict[str, Any]]:
        """Rerankea candidatos con ColBERT-style MaxSim (Spec ruscadb-colbert-rerank).

        Args:
            collection: Coleccion origen (informativa).
            query: Consulta.
            candidates: Candidatos a rerankear.
            top_k: Numero de resultados.

        Returns:
            Lista rerankeada.
        """
        from .colbert_rerank import rerank as _rerank

        return _rerank(query, candidates, top_k=top_k)

    def graph_stats(self, collection: str) -> dict[str, Any]:
        """Calcula PageRank sobre el grafo de la coleccion (Spec ruscadb-graph-algorithms).

        Args:
            collection: Coleccion origen.

        Returns:
            Mapa nodo -> score PageRank.
        """
        from .graph_algorithms import pagerank

        adj: dict[str, list[str]] = {}
        try:
            rows = self.graph_traverse(collection, depth=3)
        except Exception:  # noqa: BLE001
            rows = []
        for r in rows:
            rid = str(r.get("id") or "")
            if rid:
                adj.setdefault(rid, [])
        # inferir aristas desde metadata si existen
        for r in rows:
            meta = r.get("metadata") or {}
            edges = meta.get("edges") or []
            if isinstance(edges, list):
                src = str(r.get("id") or "")
                for e in edges:
                    if isinstance(e, dict) and e.get("target"):
                        adj.setdefault(src, []).append(str(e["target"]))
        return pagerank(adj)

    def prepare(self, sql: str) -> str:
        """Registra un SQL en el cache de prepared statements.

        Args:
            sql: Consulta RQL.

        Returns:
            Clave canonica.
        """
        from .prepared_statements import PreparedStatementCache

        cache = getattr(self, "_prepared_cache", None)
        if cache is None:
            cache = PreparedStatementCache()
            self._prepared_cache = cache
        return cache.put(sql)

    def ts_bucket_sql(self, bucket_sec: int, agg: str = "COUNT(*)") -> str:
        """Genera RQL de time_bucket (Spec ruscadb-timeseries)."""
        from .timeseries_helpers import time_bucket_sql

        return time_bucket_sql(self._first_collection(), bucket_sec, agg=agg)

    def _first_collection(self) -> str:
        cols = self.list_collections()
        return cols[0] if cols else "memory"
    def execute_at(self, sql: str, snapshot_tx_id: int = 0) -> list[Any]:
        """Ejecuta RQL en un snapshot historico (time travel, SPEC-0129).

        Args:
            sql: Consulta RQL.
            snapshot_tx_id: TxId (LSN); 0 = actual.

        Returns:
            Filas visibles en ese snapshot.
        """
        from .ruscadb import execute_at as _execute_at

        try:
            return _execute_at(self._handle, sql, snapshot_tx_id)
        except RuscadbError as exc:
            logger.warning("execute_at fallo: %s", exc)
            return []

    def open_encrypted_store(db_path: str, passphrase: str) -> RuscaDBStore:
        """Factory para abrir un store cifrado.

        Args:
            db_path: Ruta de la base.
            passphrase: Secreto del usuario.

        Returns:
            Instancia de RuscaDBStore sobre handle cifrado.
        """
        from .ruscadb import open_encrypted as _open_encrypted

        store = RuscaDBStore.__new__(RuscaDBStore)
        store.db_path = db_path
        store._allow_fallback = False
        store._caps = capabilities()
        store._collections = set()
        store._text_columns = {}
        store._embedding_dim = 384
        store._blob_path = store._default_blob_path(db_path)
        store._readonly = False
        store._handle = _open_encrypted(db_path, passphrase)
        store._ensure_collections()
        return store

    def fts_search_mode(self, collection: str, query: str, mode: str = "exact", top_k: int = 10) -> list[dict[str, Any]]:
        """FTS con modo (exact/phrase/fuzzy) — Spec ruscadb-fts-advanced.

        Fuzzy se resuelve client-side (Levenshtein) porque RQL no expone
        MATCH ... FUZZY todavia (SPEC-0117 marca integracion futura).

        Args:
            collection: Coleccion.
            query: Texto.
            mode: 'exact', 'fuzzy', 'phrase'.
            top_k: Limite.

        Returns:
            Resultados normalizados.
        """
        if mode == "phrase":
            q = '"' + query + '"'
            try:
                rows = execute(self._handle, f"SELECT * FROM {_safe_ident(collection)} WHERE MATCH({self._text_column(collection)}, '{_escape_literal(q)}')")
            except RuscadbError as exc:
                logger.warning("fts_search_mode fallo: %s", exc)
                return []
            out = self._parse_rows(rows)
            for rank, item in enumerate(out):
                item["score"] = 1.0 / (rank + 1)
            return out[:top_k]

        if mode == "fuzzy":
            # client-side: scan all rows, filter by edit distance <= 2
            try:
                rows = execute(self._handle, f"SELECT * FROM {_safe_ident(collection)}")
            except RuscadbError as exc:
                logger.warning("fts_search_mode fallo: %s", exc)
                return []
            parsed = self._parse_rows(rows)
            q_tokens = query.lower().split()
            filtered = []
            for item in parsed:
                text = (item.get("text") or "").lower()
                if any(self._edit_distance(qt, wt) <= 2 for qt in q_tokens for wt in text.split()):
                    filtered.append(item)
            for rank, item in enumerate(filtered):
                item["score"] = 1.0 / (rank + 1)
            return filtered[:top_k]

        # exact
        return self.full_text_search(collection, query, top_k=top_k)

    @staticmethod
    def _edit_distance(a: str, b: str) -> int:
        """Distancia de Levenshtein entre dos strings."""
        if a == b:
            return 0
        if not a:
            return len(b)
        if not b:
            return len(a)
        prev = list(range(len(b) + 1))
        for i, ca in enumerate(a, 1):
            cur = [i]
            for j, cb in enumerate(b, 1):
                cost = 0 if ca == cb else 1
                cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + cost))
            prev = cur
        return prev[-1]

    def semantic_cache_get(self, key: str) -> Any:
        """Consulta el cache semantico persistente de RuscaDB.

        Implementa la lectura del Spec ``ruscadb-semantic-cache``: la clave se
        resolvio en ``id`` y el valor viaja serializado en ``text`` con
        metadatos de TTL. Contabiliza hit/miss/expirados para ``metrics``.

        Args:
            key: Clave de cache.

        Returns:
            Valor cacheado o None si no existe o expiro.
        """
        stored = self._semantic_cache_row(key)
        if stored is None:
            return None
        value, meta = stored
        ttl = meta.get("ttl_sec")
        cached_at = meta.get("cached_at")
        if isinstance(ttl, (int, float)) and ttl > 0:
            age = self._age_days(cached_at, _dt.datetime.now(_dt.UTC))
            # Fail-closed: si el TTL es exigible y no se puede datar la
            # entrada, se trata como expirada (nunca servir contenido obsoleto).
            if age is None or age * 86400.0 > float(ttl):
                self._cache_expired += 1
                self._cache_misses += 1
                return None
        self._cache_hits += 1
        return value

    def _semantic_cache_row(self, key: str) -> tuple[Any, dict[str, Any]] | None:
        """Lee la fila cruda del cache semantico.

        Args:
            key: Clave de cache.

        Returns:
            ``(valor, metadatos)`` o ``None`` si no existe.
        """
        sql = (
            "SELECT * FROM semantic_cache "  # nosec B608
            f"WHERE id = '{_escape_literal(key)}' LIMIT 1"
        )
        try:
            rows = execute(self._handle, sql)
            parsed = json.loads(rows) if isinstance(rows, str) else rows
        except (RuscadbError, ValueError, TypeError) as exc:
            logger.debug("semantic_cache_get fallo: %s", exc)
            return None
        if not parsed:
            self._cache_misses += 1
            return None
        row = parsed[0]
        meta = self._unwrap_scalar(row.get("metadata"))
        if isinstance(meta, str):
            try:
                meta = json.loads(meta)
            except json.JSONDecodeError:
                meta = {}
        if not isinstance(meta, dict):
            meta = {}
        raw = self._unwrap_scalar(row.get("text"))
        try:
            value = json.loads(raw) if isinstance(raw, str) else raw
        except json.JSONDecodeError:
            value = raw
        return value, meta

    def semantic_cache_set(
        self, key: str, value: Any, ttl_sec: float | None = None
    ) -> bool:
        """Guarda un valor en el cache semantico persistente (upsert).

        Args:
            key: Clave de cache (identificador de la entrada).
            value: Valor serializable a JSON.
            ttl_sec: TTL opcional en segundos; ``None`` = sin expiracion.

        Returns:
            True si la escritura se confirmo; False si el motor la rechazo.
        """
        if not isinstance(key, str) or not key.strip():
            raise ValueError("semantic_cache_set: key vacia o no-str")
        payload = json.dumps(value, ensure_ascii=False, default=str)
        meta = {
            "cached_at": _dt.datetime.now(_dt.UTC).isoformat(),
            "ttl_sec": ttl_sec,
        }
        try:
            execute(
                self._handle,
                "DELETE FROM semantic_cache "  # nosec B608
                f"WHERE id = '{_escape_literal(key)}'",
            )
            insert_record(
                self._handle,
                "semantic_cache",
                {
                    "scalars": {
                        "id": key,
                        "text": payload,
                        "metadata": json.dumps(meta, ensure_ascii=False),
                        "created_at": meta["cached_at"],
                    }
                },
            )
            self._commit()
        except (RuscadbError, ValueError) as exc:
            logger.warning("semantic_cache_set fallo: %s", exc)
            return False
        self._cache_sets += 1
        self.invalidate_cache("semantic_cache")
        return True

    def semantic_cache_clear(self) -> bool:
        """Vacia el cache semantico persistente.

        Returns:
            True si el motor confirmo el borrado; False si fallo (sin fingir
            exito).
        """
        try:
            execute(self._handle, "DELETE FROM semantic_cache")  # nosec B608
            self._commit()
        except (RuscadbError, ValueError) as exc:
            logger.warning("semantic_cache_clear fallo: %s", exc)
            return False
        self.invalidate_cache("semantic_cache")
        return True

    def semantic_cache_metrics(self) -> dict[str, Any]:
        """Metricas de acierto del cache semantico.

        Returns:
            ``{hits, misses, expired, sets, hit_rate}`` con ``hit_rate`` en
            ``[0.0, 1.0]`` (0.0 si aun no hubo lecturas).
        """
        lookups = self._cache_hits + self._cache_misses
        return {
            "hits": self._cache_hits,
            "misses": self._cache_misses,
            "expired": self._cache_expired,
            "sets": self._cache_sets,
            "hit_rate": (self._cache_hits / lookups) if lookups else 0.0,
        }

    def semantic_cache_delete(self, key: str) -> bool:
        """Elimina una entrada concreta del cache semantico persistente.

        Borra la fila persistente (``id = key``) y la fila vectorial homonima
        (``metadata.prompt_hash == key``) para que la ruta de similitud no
        sirva una entrada eliminada.

        Args:
            key: Clave a eliminar.

        Returns:
            True si el motor confirmo el borrado; False en caso contrario.
        """
        vector_ids = [
            str(item["id"])
            for item in self.semantic_cache_entries()
            if item.get("id") and (item.get("metadata") or {}).get("prompt_hash") == key
        ]
        return self._semantic_cache_delete_rows([key], vector_ids)

    def _semantic_cache_delete_rows(
        self, keys: list[str], vector_ids: list[str]
    ) -> bool:
        """Borra filas del cache (persistentes y vectoriales) y confirma.

        Args:
            keys: Claves persistentes (columna ``id``).
            vector_ids: Ids logicos de filas vectoriales a borrar.

        Returns:
            True si todas las sentencias se ejecutaron sin error.
        """
        ok = True
        for key in keys:
            try:
                execute(
                    self._handle,
                    "DELETE FROM semantic_cache "  # nosec B608
                    f"WHERE id = '{_escape_literal(key)}'",
                )
            except (RuscadbError, ValueError) as exc:
                logger.warning("semantic_cache_delete '%s' fallo: %s", key, exc)
                ok = False
        if vector_ids:
            self.delete("semantic_cache", vector_ids)
        self._commit()
        self.invalidate_cache("semantic_cache")
        return ok

    def semantic_cache_entries(self, limit: int = 10000) -> list[dict[str, Any]]:
        """Lista las entradas del cache semantico con sus metadatos.

        Args:
            limit: Maximo de entradas a devolver (cap explicito y documentado;
                el cache se purga periodicamente para no superarlo).

        Returns:
            Lista de ``{id, text, metadata, created_at}``.
        """
        sql = (
            "SELECT * FROM semantic_cache "  # nosec B608
            f"LIMIT {max(1, int(limit))}"
        )
        try:
            rows = execute(self._handle, sql)
        except RuscadbError as exc:
            logger.debug("semantic_cache_entries fallo: %s", exc)
            return []
        return self._parse_rows(rows)

    def semantic_cache_purge_expired(
        self, default_ttl: float | None = None
    ) -> int:
        """Purga entradas expiradas del cache semantico persistente.

        Un solo escaneo; despues borra en lote (sin re-escanear la tabla por
        cada expirada, que hacia la purga O(n²)).

        Args:
            default_ttl: TTL a aplicar cuando la entrada no lo declara.

        Returns:
            Numero de entradas eliminadas (0 si la operacion fallo).
        """
        now = _dt.datetime.now(_dt.UTC)
        entries = self.semantic_cache_entries()
        expired_keys: list[str] = []
        for item in entries:
            meta = item.get("metadata") or {}
            ttl = meta.get("ttl_sec", default_ttl)
            if not isinstance(ttl, (int, float)) or ttl <= 0:
                continue
            age = self._age_days(
                meta.get("cached_at") or item.get("created_at"), now
            )
            key = str(item.get("id") or "")
            if key and (age is None or age * 86400.0 > float(ttl)):
                expired_keys.append(key)
        if not expired_keys:
            return 0
        expired = set(expired_keys)
        vector_ids = [
            str(item["id"])
            for item in entries
            if item.get("id")
            and (item.get("metadata") or {}).get("prompt_hash") in expired
            and str(item["id"]) not in expired
        ]
        ok = self._semantic_cache_delete_rows(expired_keys, vector_ids)
        return len(expired_keys) if ok else 0

    def adaptive_search(self, query: str, top_k: int = 5, collection: str = "memory") -> list[Any]:
        """Retrieval adaptativo (arXiv:2403.14403) sobre este store.

        Args:
            query: Consulta de texto.
            top_k: Numero de resultados.
            collection: Coleccion.

        Returns:
            Lista de resultados ordenados.
        """
        try:
            from .adaptive_retriever import AdaptiveRetriever

            ar = AdaptiveRetriever.from_store(self, collection=collection)
            return ar.retrieve(query, top_k=top_k)
        except Exception as exc:  # noqa: BLE001
            logger.warning("adaptive_search fallo: %s", exc)
            return []

    def _keyword_score(self, text: str, query: str) -> float:
        """Score lexical simple (compatibilidad con LanceVectorStore).

        Args:
            text: Texto donde buscar.
            query: Termino buscado.

        Returns:
            Ocurrencias del termino en el texto.
        """
        if not text or not query:
            return 0.0
        return float(text.lower().count(query.lower()))

    def _commit(self) -> None:
        """Confirma los cambios pendientes (WAL-first)."""
        try:
            commit(self._handle)
        except RuscadbError as exc:
            logger.debug("commit fallo: %s", exc)

    def close(self) -> None:
        """Confirma y cierra el handle del motor."""
        with _OPEN_LOCK:
            self._commit()
            try:
                close(self._handle)
            except RuscadbError as exc:
                logger.debug("close fallo: %s", exc)

    def __del__(self) -> None:
        """Libera el handle (y el lock) si no se cerro explicitamente."""
        try:
            self.close()
        except Exception:  # noqa: BLE001, S110
            pass

    @classmethod
    def from_config(cls, config: Any = None) -> RuscaDBStore:
        """Construye el store desde un MemoryConfig.

        Args:
            config: MemoryConfig opcional.

        Returns:
            Instancia configurada.
        """
        return cls(config=config)
