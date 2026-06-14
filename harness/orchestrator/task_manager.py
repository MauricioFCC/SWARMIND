"""Task management module using LanceDB with SQLite fallback.

Manages the 'tasks_board' collection with full CRUD, status transitions,
and agent-based querying. Uses Pydantic models when available.
"""

from __future__ import annotations

import json
import os
import sqlite3
import time
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Literal, Optional, Tuple

try:
    from pydantic import BaseModel, Field
    HAS_PYDANTIC = True
except ImportError:
    HAS_PYDANTIC = False

try:
    import lancedb
    HAS_LANCEDB = True
except ImportError:
    HAS_LANCEDB = False


TaskStatus = Literal["pending", "in_progress", "done", "blocked"]


@dataclass
class TransitionEntry:
    """TransitionEntry."""
    from_status: str
    to_status: str
    timestamp: str
    reason: str

    def to_dict(self) -> Dict[str, Any]:
        """To dict."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TransitionEntry":
        """From dict."""
        return cls(**data)


@dataclass
class Task:
    """Task."""
    id: str = ""
    title: str = ""
    description: str = ""
    agent_assigned: str = ""
    status: str = "pending"
    priority: int = 0
    created_at: str = ""
    updated_at: str = ""
    transition_history: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """To dict."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Task":
        """From dict."""
        return cls(**data)


if HAS_PYDANTIC:

    class PydanticTask(BaseModel):
        """PydanticTask."""
        id: str = Field(default_factory=lambda: uuid.uuid4().hex[:12])
        title: str = ""
        description: str = ""
        agent_assigned: str = ""
        status: TaskStatus = "pending"
        priority: int = 0
        created_at: str = Field(
            default_factory=lambda: datetime.now(timezone.utc).isoformat()
        )
        updated_at: str = Field(
            default_factory=lambda: datetime.now(timezone.utc).isoformat()
        )
        transition_history: List[Dict[str, Any]] = Field(default_factory=list)

        def to_dict(self) -> Dict[str, Any]:
            """To dict."""
            return self.model_dump()

        @classmethod
        def from_dict(cls, data: Dict[str, Any]) -> "PydanticTask":
            """From dict."""
            return cls(**data)

    _TaskModel = PydanticTask
else:
    _TaskModel = Task

    class PydanticTask:
        """Placeholder when pydantic is not installed — never instantiated."""
        @classmethod
        def from_dict(cls, data: Dict[str, Any]) -> Task:
            """From dict."""
            return Task.from_dict(data)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _make_id() -> str:
    return uuid.uuid4().hex[:12]


def _validate_status(status: str) -> str:
    valid = {"pending", "in_progress", "done", "blocked"}
    if status not in valid:
        raise ValueError(f"Invalid status '{status}'. Must be one of: {', '.join(sorted(valid))}")
    return status


class TaskManager:
    """Manages tasks using LanceDB with automatic fallback to SQLite.

    All tasks are stored in a 'tasks_board' collection/table.
    The connection path defaults to harness/db/lancedb_store/.
    """

    def __init__(self, db_path: str = "", vector_store: Any = None) -> None:
        """Inicializa la instancia de la clase."""
        if vector_store is not None:
            db_path = getattr(vector_store, 'db_path', db_path)
        if not db_path:
            db_path = os.path.join(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                "db",
                "lancedb_store",
            )
        self._db_path: str = db_path
        self._table_name: str = "tasks_board"
        self._conn_lancedb: Any = None
        self._table: Any = None
        self._sqlite_conn: Optional[sqlite3.Connection] = None
        self._use_sqlite: bool = False
        self._initialize()

    def _initialize(self) -> None:
        if HAS_LANCEDB:
            try:
                self._conn_lancedb = lancedb.connect(self._db_path)
                tables = self._conn_lancedb.table_names()
                if self._table_name not in tables:
                    self._conn_lancedb.create_table(
                        self._table_name,
                        data=[{"id": "init", "title": "init", "description": "init",
                               "agent_assigned": "", "status": "pending", "priority": 0,
                               "created_at": _now_iso(), "updated_at": _now_iso(),
                               "transition_history": json.dumps([])}],
                        mode="overwrite",
                    )
                    self._conn_lancedb.open_table(self._table_name).delete("id = 'init'")
                self._table = self._conn_lancedb.open_table(self._table_name)
                return
            except Exception:
                pass

        self._use_sqlite = True
        os.makedirs(os.path.dirname(self._db_path), exist_ok=True)
        sqlite_path = os.path.join(self._db_path, "tasks_board.sqlite")
        self._sqlite_conn = sqlite3.connect(sqlite_path)
        self._sqlite_conn.row_factory = sqlite3.Row
        self._sqlite_conn.execute(
            """
            CREATE TABLE IF NOT EXISTS tasks_board (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                description TEXT DEFAULT '',
                agent_assigned TEXT DEFAULT '',
                status TEXT DEFAULT 'pending',
                priority INTEGER DEFAULT 0,
                created_at TEXT DEFAULT '',
                updated_at TEXT DEFAULT '',
                transition_history TEXT DEFAULT '[]'
            )
            """
        )
        self._sqlite_conn.commit()

    @property
    def db_path(self) -> str:
        """Db path."""
        return self._db_path

    def _serialize_task(self, task: _TaskModel) -> Dict[str, Any]:
        data = task.to_dict() if isinstance(task, (Task, PydanticTask)) else task
        if isinstance(data.get("transition_history"), list):
            data = {**data, "transition_history": json.dumps(data["transition_history"])}
        return data

    def _deserialize_task(self, row: Dict[str, Any]) -> _TaskModel:
        if isinstance(row.get("transition_history"), str):
            row = {
                **row,
                "transition_history": json.loads(row["transition_history"]),
            }
        model_cls = PydanticTask if HAS_PYDANTIC else Task
        return model_cls.from_dict(row)

    def _sqlite_to_dict(self, row: sqlite3.Row) -> Dict[str, Any]:
        return dict(row)

    def _run_sqlite_query(self, sql: str, params: Tuple = ()) -> List[Dict[str, Any]]:
        if not self._sqlite_conn:
            return []
        cursor = self._sqlite_conn.execute(sql, params)
        rows = cursor.fetchall()
        return [self._sqlite_to_dict(r) for r in rows]

    def _run_sqlite_execute(self, sql: str, params: Tuple = ()) -> None:
        if not self._sqlite_conn:
            return
        self._sqlite_conn.execute(sql, params)
        self._sqlite_conn.commit()

    def create_task(
        self,
        title: str,
        description: str = "",
        agent_assigned: str = "",
        status: str = "pending",
        priority: int = 0,
    ) -> _TaskModel:
        """Create a new task and persist it to the store."""
        status = _validate_status(status)
        now = _now_iso()
        task_id = _make_id()

        task_data = {
            "id": task_id,
            "title": title,
            "description": description,
            "agent_assigned": agent_assigned,
            "status": status,
            "priority": priority,
            "created_at": now,
            "updated_at": now,
            "transition_history": json.dumps([]),
        }

        if not self._use_sqlite and self._table is not None:
            self._table.add([task_data])
        else:
            self._run_sqlite_execute(
                """
                INSERT INTO tasks_board
                    (id, title, description, agent_assigned, status, priority, created_at, updated_at, transition_history)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    task_id, title, description, agent_assigned, status, priority,
                    now, now, task_data["transition_history"],
                ),
            )

        model_cls = PydanticTask if HAS_PYDANTIC else Task
        return model_cls(
            id=task_id,
            title=title,
            description=description,
            agent_assigned=agent_assigned,
            status=status,
            priority=priority,
            created_at=now,
            updated_at=now,
            transition_history=[],
        )

    def read_task(self, task_id: str) -> Optional[_TaskModel]:
        """Retrieve a single task by its ID."""
        if not self._use_sqlite and self._table is not None:
            results = self._table.search().where(f"id = '{task_id}'").limit(1).to_pandas()
            if len(results) == 0:
                return None
            row = results.iloc[0].to_dict()
            return self._deserialize_task(row)
        else:
            rows = self._run_sqlite_query(
                "SELECT * FROM tasks_board WHERE id = ?", (task_id,)
            )
            if not rows:
                return None
            return self._deserialize_task(rows[0])

    def update_task(self, task_id: str, **updates: Any) -> Optional[_TaskModel]:
        """Update fields on an existing task.

        Accepts keyword arguments matching Task fields.
        """
        task = self.read_task(task_id)
        if task is None:
            return None

        existing = task.to_dict()
        allowed_fields = {"title", "description", "agent_assigned", "status", "priority"}

        for key, value in updates.items():
            if key in allowed_fields:
                if key == "status":
                    value = _validate_status(value)
                existing[key] = value

        existing["updated_at"] = _now_iso()
        serialized = self._serialize_task(existing)

        if not self._use_sqlite and self._table is not None:
            self._table.update(where=f"id = '{task_id}'", values=serialized)
        else:
            set_clause = ", ".join(f"{k} = ?" for k in serialized if k != "id")
            values = [v for k, v in serialized.items() if k != "id"] + [task_id]
            self._run_sqlite_execute(
                f"UPDATE tasks_board SET {set_clause} WHERE id = ?",
                tuple(values),
            )

        return self._deserialize_task(serialized)

    def delete_task(self, task_id: str) -> bool:
        """Delete a task by ID. Returns True if a task was removed."""
        if not self._use_sqlite and self._table is not None:
            result = self._table.delete(f"id = '{task_id}'")
            return result is not None
        else:
            cursor = self._sqlite_conn.execute(
                "DELETE FROM tasks_board WHERE id = ?", (task_id,)
            )
            self._sqlite_conn.commit()
            return cursor.rowcount > 0

    def query_by_agent(self, agent: str) -> List[_TaskModel]:
        """Return all tasks assigned to a specific agent."""
        if not self._use_sqlite and self._table is not None:
            results = self._table.search().where(f"agent_assigned = '{agent}'").to_pandas()
            return [self._deserialize_task(row.to_dict()) for _, row in results.iterrows()]
        else:
            rows = self._run_sqlite_query(
                "SELECT * FROM tasks_board WHERE agent_assigned = ?", (agent,)
            )
            return [self._deserialize_task(r) for r in rows]

    def list_tasks(
        self,
        status: Optional[str] = None,
        agent: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[_TaskModel]:
        """List tasks with optional filtering by status and/or agent."""
        conditions = []
        params: List[Any] = []

        if status is not None:
            conditions.append("status = ?")
            params.append(status)
        if agent is not None:
            conditions.append("agent_assigned = ?")
            params.append(agent)

        if not self._use_sqlite and self._table is not None:
            where_clause = " AND ".join(conditions) if conditions else "1=1"
            results = (
                self._table.search()
                .where(where_clause)
                .limit(limit)
                .to_pandas()
            )
            return [self._deserialize_task(row.to_dict()) for _, row in results.iterrows()]
        else:
            where_clause = " AND ".join(conditions) if conditions else "1=1"
            sql = f"SELECT * FROM tasks_board WHERE {where_clause} ORDER BY created_at DESC LIMIT ? OFFSET ?"
            params.extend([limit, offset])
            rows = self._run_sqlite_query(sql, tuple(params))
            return [self._deserialize_task(r) for r in rows]

    def update_status(
        self, task_id: str, new_status: str, reason: str = ""
    ) -> Optional[_TaskModel]:
        """Update a task's status and log the transition automatically."""
        new_status = _validate_status(new_status)
        task = self.read_task(task_id)
        if task is None:
            return None

        existing = task.to_dict()
        old_status = existing["status"]

        if old_status == new_status:
            return task

        transition: Dict[str, Any] = {
            "from_status": old_status,
            "to_status": new_status,
            "timestamp": _now_iso(),
            "reason": reason,
        }

        history: List[Dict[str, Any]] = existing.get("transition_history", [])
        history.append(transition)

        existing["status"] = new_status
        existing["updated_at"] = _now_iso()
        existing["transition_history"] = history

        serialized = self._serialize_task(existing)

        if not self._use_sqlite and self._table is not None:
            self._table.update(where=f"id = '{task_id}'", values=serialized)
        else:
            set_clause = ", ".join(f"{k} = ?" for k in serialized if k != "id")
            values = [v for k, v in serialized.items() if k != "id"] + [task_id]
            self._run_sqlite_execute(
                f"UPDATE tasks_board SET {set_clause} WHERE id = ?",
                tuple(values),
            )

        return self._deserialize_task(serialized)

    def count_tasks(self, status: Optional[str] = None) -> int:
        """Return the number of tasks, optionally filtered by status."""
        if not self._use_sqlite and self._table is not None:
            df = self._table.search().to_pandas()
            if status is not None:
                df = df[df["status"] == status]
            return len(df)
        else:
            if status is not None:
                row = self._sqlite_conn.execute(
                    "SELECT COUNT(*) as cnt FROM tasks_board WHERE status = ?", (status,)
                ).fetchone()
            else:
                row = self._sqlite_conn.execute(
                    "SELECT COUNT(*) as cnt FROM tasks_board"
                ).fetchone()
            return row["cnt"] if row else 0

    def close(self) -> None:
        """Close the database connection if using SQLite fallback."""
        if self._sqlite_conn is not None:
            self._sqlite_conn.close()
            self._sqlite_conn = None
