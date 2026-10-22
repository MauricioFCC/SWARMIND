"""RuscaDB-backed vector store (drop-in para LanceVectorStore).

Usa el binding ctypes de RuscaDB (harness.memory_rag.ruscadb) para
almacenamiento multi-modelo + vectorial. Aprovecha KNN (HNSW) y MATCH (BM25)
de RuscaDB via RQL.
"""

from __future__ import annotations

import json
import logging
import uuid
from typing import Any

import numpy as np

from .ruscadb import (
    RuscadbError,
    close,
    commit,
    create_table,
    execute,
    insert_record,
    list_tables,
)
from .ruscadb import (
    open as rdb_open,
)

logger = logging.getLogger("harness.memory_rag.ruscadb_store")

_DEFAULT_COLLECTIONS = ("memory", "semantic_cache", "agent_workspace_logs")


class RuscaDBStore:
    """Vector store backed by RuscaDB (ctypes binding)."""

    def __init__(self, db_path: str | None = None, allow_fallback: bool = False, config: Any = None) -> None:
        self.db_path = db_path or (config.ruscadb_path if config else None) or "ruscadb.db"
        self._allow_fallback = allow_fallback
        self._handle = rdb_open(self.db_path, pool_capacity=8)
        self._collections: set[str] = set()
        self._embedding_dim: int = 384
        self._ensure_collections()

    def _ensure_collections(self) -> None:
        existing = set(self.list_collections())
        for name in _DEFAULT_COLLECTIONS:
            if name in existing:
                continue
            try:
                create_table(self._handle, name, [
                    {"name": "id", "type": "Text"},
                    {"name": "metadata", "type": "Text"},
                    {"name": "created_at", "type": "Text"},
                ])
                self._collections.add(name)
            except RuscadbError as exc:
                logger.debug("Could not create collection '%s': %s", name, exc)
            self._collections.add(name)

    def list_collections(self) -> list[str]:
        try:
            names = list_tables(self._handle)
            if names:
                self._collections = set(names)
                return sorted(self._collections)
        except RuscadbError:
            pass
        return sorted(self._collections)

    def create_collection(self, name: str, schema: Any = None) -> None:
        if name in self.list_collections():
            self._collections.add(name)
            return
        try:
            create_table(self._handle, name, [
                {"name": "id", "type": "Text"},
                {"name": "metadata", "type": "Text"},
                {"name": "created_at", "type": "Text"},
            ])
        except RuscadbError as exc:
            logger.debug("create_collection '%s' failed: %s", name, exc)
        self._collections.add(name)
        self._collections.add(name)

    def insert(self, collection: str, vectors: Any, metadata: list[dict[str, Any]], now: str | None = None) -> list[str]:
        if collection not in self.list_collections():
            self.create_collection(collection)
        import datetime as _dt
        now = now or _dt.datetime.now(_dt.UTC).isoformat()
        ids: list[str] = []
        arr = np.asarray(vectors)
        if arr.ndim == 1:
            arr = arr.reshape(1, -1)
        for i in range(arr.shape[0]):
            rid = str(uuid.uuid4())
            ids.append(rid)
            rec = {
                "scalars": {"id": rid, "metadata": json.dumps(metadata[i] if i < len(metadata) else {}), "created_at": now},
                "vector": arr[i].tolist(),
                "vector_meta": {"model_id": "swarmind", "dim": arr.shape[1], "metric": "L2"},
            }
            try:
                insert_record(self._handle, collection, rec)
            except RuscadbError as exc:
                logger.warning("insert failed: %s", exc)
        try:
            commit(self._handle)
        except RuscadbError:
            pass
        return ids

    def search(self, collection: str, query_vector: Any, top_k: int = 5, **kwargs: Any) -> list[dict[str, Any]]:
        qv = np.asarray(query_vector).tolist()
        try:
            rows = execute(self._handle, "SELECT * FROM " + collection + " KNN embedding <|" + str(top_k) + "|> " + json.dumps(qv))
        except RuscadbError as exc:
            logger.warning("search failed: %s", exc)
            return []
        out = []
        for r in (json.loads(rows) if isinstance(rows, str) else rows):
            if not isinstance(r, dict):
                continue
            meta_raw = r.get("metadata")
            meta = self._unwrap_scalar(meta_raw)
            if isinstance(meta, str):
                try:
                    meta = json.loads(meta)
                except json.JSONDecodeError:
                    meta = {"raw": meta}
            elif not isinstance(meta, dict):
                meta = {"value": meta}
            rid = self._unwrap_scalar(r.get("id"))
            out.append({"id": rid, "metadata": meta, "score": r.get("_distance", 0.0)})
        return out

    @staticmethod
    def _unwrap_scalar(v: Any) -> Any:
        if isinstance(v, dict) and len(v) == 1:
            key = next(iter(v))
            if key in ("Text", "Int", "Float", "Bool", "Null"):
                return v[key]
        return v

    def delete_collection(self, name: str) -> None:
        try:
            execute(self._handle, f"DROP TABLE {name}")
        except RuscadbError:
            pass
        self._collections.discard(name)

    def clear(self) -> None:
        for c in list(self.list_collections()):
            self.delete_collection(c)
        self._ensure_collections()

    def get_collection_stats(self, name: str) -> dict[str, Any]:
        try:
            rows = execute(self._handle, f"SELECT COUNT(*) as n FROM {name}")
            parsed = json.loads(rows) if isinstance(rows, str) else rows
            n = parsed[0].get("n", 0) if parsed else 0
            # n may be {"Int": x}
            if isinstance(n, dict):
                n = next(iter(n.values())) if n else 0
            return {"count": n}
        except RuscadbError:
            return {"count": 0}

    def update_records(self, collection: str, records: list[dict[str, Any]]) -> None:
        # RuscaDB: re-insert (upsert not guaranteed); best-effort
        for rec in records:
            try:
                self.insert(collection, [rec.get("vector", [])], [rec.get("metadata", {})])
            except Exception:  # noqa: BLE001, S110
                pass

    def hybrid_search(self, collection: str, query_vector: Any, query_text: str = "", top_k: int = 5, **kwargs: Any) -> list[dict[str, Any]]:
        # Combine KNN + MATCH
        res = self.search(collection, query_vector, top_k=top_k)
        if query_text:
            try:
                rows = execute(self._handle, "SELECT * FROM {} WHERE MATCH(title, '{}')".format(collection, query_text.replace("'", "''")))
                parsed = json.loads(rows) if isinstance(rows, str) else rows
                for r in parsed:
                    meta_raw = r.get("metadata")
                    meta = json.loads(meta_raw) if isinstance(meta_raw, str) else (meta_raw or {})
                    res.append({"id": r.get("id"), "metadata": meta, "score": 0.0})
            except RuscadbError:
                pass
        return res[:top_k]

    def execute(self, sql: str) -> Any:
        try:
            return execute(self._handle, sql)
        except RuscadbError as exc:
            logger.warning('execute failed: %s', exc)
            return None

    def full_text_search(self, collection: str, query: str, top_k: int = 10) -> list[dict[str, Any]]:
        try:
            rows = execute(self._handle, "SELECT * FROM " + collection + " WHERE MATCH(title, '" + query.replace(chr(39), chr(39)+chr(39)) + "')")
        except RuscadbError:
            try:
                rows = execute(self._handle, "SELECT * FROM " + collection + " WHERE MATCH(content, '" + query.replace(chr(39), chr(39)+chr(39)) + "')")
            except RuscadbError as exc:
                logger.warning('full_text_search failed: %s', exc)
                return []
        parsed = json.loads(rows) if isinstance(rows, str) else rows
        out = []
        for r in (parsed or []):
            if not isinstance(r, dict):
                continue
            meta = self._unwrap_scalar(r.get('metadata'))
            if isinstance(meta, str):
                try:
                    meta = json.loads(meta)
                except json.JSONDecodeError:
                    meta = {'raw': meta}
            rid = self._unwrap_scalar(r.get('id'))
            out.append({'id': rid, 'metadata': meta, 'score': 0.0})
        return out[:top_k]

    def graph_traverse(self, collection: str, depth: int = 2) -> list[dict[str, Any]]:
        try:
            rows = execute(self._handle, "SELECT * FROM " + collection + " TRAVERSE edges DEPTH " + str(depth))
        except RuscadbError as exc:
            logger.warning('graph_traverse failed: %s', exc)
            return []
        parsed = json.loads(rows) if isinstance(rows, str) else rows
        out = []
        for r in (parsed or []):
            if not isinstance(r, dict):
                continue
            rid = self._unwrap_scalar(r.get('id'))
            out.append({'id': rid, 'raw': r})
        return out

    def _keyword_score(self, text: str, query: str) -> float:
        if not text or not query:
            return 0.0
        t = text.lower()
        q = query.lower()
        return float(t.count(q))

    def close(self) -> None:
        try:
            commit(self._handle)
        except RuscadbError:
            pass
        try:
            close(self._handle)
        except RuscadbError:
            pass

    @classmethod
    def from_config(cls, config: Any = None) -> RuscaDBStore:
        return cls(config=config)