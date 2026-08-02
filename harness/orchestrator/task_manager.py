"""Task management module using LanceDB with SQLite fallback.

Manages the 'tasks_board' collection with full CRUD, status transitions,
and agent-based querying. Uses Pydantic models when available.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import uuid
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

logger = logging.getLogger(__name__)

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

    def to_dict(self) -> dict[str, Any]:
        """To dict."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TransitionEntry:
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
    transition_history: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """To dict."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Task:
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
            default_factory=lambda: datetime.now(UTC).isoformat()
        )
        updated_at: str = Field(
            default_factory=lambda: datetime.now(UTC).isoformat()
        )
        transition_history: list[dict[str, Any]] = Field(default_factory=list)

        def to_dict(self) -> dict[str, Any]:
            """To dict."""
            return self.model_dump()

        @classmethod
        def from_dict(cls, data: dict[str, Any]) -> PydanticTask:
            """From dict."""
            return cls(**data)

    _TaskModel = PydanticTask
else:
    _TaskModel = Task

    class PydanticTask:
        """Placeholder when pydantic is not installed â€” never instantiated."""
        @classmethod
        def from_dict(cls, data: dict[str, Any]) -> Task:
            """From dict."""
            return Task.from_dict(data)


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


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
    The connection path defaults to harness/db/lancedb/.
    """

    def __init__(self, db_path: str = "", vector_store: Any = None) -> None:
        """Inicializa la instancia de la clase."""
        if vector_store is not None:
            db_path = getattr(vector_store, 'db_path', db_path)
        if not db_path:
            db_path = str(Path(__file__).resolve().parent.parent / "db" / "lancedb")
        self._db_path: str = db_path
        self._table_name: str = "tasks_board"
        self._conn_lancedb: Any = None
        self._table: Any = None
        self._sqlite_conn: sqlite3.Connection | None = None
        self._use_sqlite: bool = False
        self._initialize()

    def _initialize(self) -> None:
        db_dir = Path(self._db_path).parent
        if not db_dir.exists():
            db_dir.mkdir(parents=True, exist_ok=True)
        if HAS_LANCEDB:
            try:
                self._conn_lancedb = lancedb.connect(self._db_path)
                tables = self._conn_lancedb.list_tables().tables
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
            except Exception as _exc:  # noqa: BLE001
                logger.warning("task_manager: %s", _exc)

        self._use_sqlite = True
        Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)
        sqlite_path = str(Path(self._db_path) / "tasks_board.sqlite")
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

    def _serialize_task(self, task: _TaskModel) -> dict[str, Any]:
        data = task.to_dict() if isinstance(task, (Task, PydanticTask)) else task
        if isinstance(data.get("transition_history"), list):
            data = {**data, "transition_history": json.dumps(data["transition_history"])}
        return data

    def _deserialize_task(self, row: dict[str, Any]) -> _TaskModel:
        if isinstance(row.get("transition_history"), str):
            row = {
                **row,
                "transition_history": json.loads(row["transition_history"]),
            }
        model_cls = PydanticTask if HAS_PYDANTIC else Task
        return model_cls.from_dict(row)

    def _sqlite_to_dict(self, row: sqlite3.Row) -> dict[str, Any]:
        return dict(row)

    def _run_sqlite_query(self, sql: str, params: tuple = ()) -> list[dict[str, Any]]:
        if not self._sqlite_conn:
            return []
        cursor = self._sqlite_conn.execute(sql, params)
        rows = cursor.fetchall()
        return [self._sqlite_to_dict(r) for r in rows]

    def _run_sqlite_execute(self, sql: str, params: tuple = ()) -> None:
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

    def read_task(self, task_id: str) -> _TaskModel | None:
        """Retrieve a single task by its ID."""
        if not self._use_sqlite and self._table is not None:
            # task_id es internamente generado (uuid hex), seguro contra injection
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

    def update_task(self, task_id: str, **updates: Any) -> _TaskModel | None:
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
                # keys de allowed_fields validados, valores parametrizados
                f"UPDATE tasks_board SET {set_clause} WHERE id = ?",  # nosec B608
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

    def query_by_agent(self, agent: str) -> list[_TaskModel]:
        """Return all tasks assigned to a specific agent.

        El parametro ``agent`` se valida contra agentes conocidos para
        prevenir inyeccion en filtros LanceDB/SQL (CVE-style).
        """
        # Validar contra agentes conocidos para prevenir filter injection
        _VALID_AGENTS = frozenset({
            "coordinator", "builder", "scientist", "guardian", "evolve",
            "software-engineer", "data-architect", "devops-sre", "quality-gate",
            "project-manager", "product-owner", "ui-designer", "ux-researcher",
            "security-analyst", "technical-writer", "scrum-master",
        })
        clean_agent = agent.strip().lower()
        if clean_agent not in _VALID_AGENTS:
            logger.warning("Agent desconocido en query_by_agent: '%s'", agent)
            return []

        if not self._use_sqlite and self._table is not None:
            results = self._table.search().where(f"agent_assigned = '{clean_agent}'").to_pandas()
            return [self._deserialize_task(row.to_dict()) for _, row in results.iterrows()]
        else:
            rows = self._run_sqlite_query(
                "SELECT * FROM tasks_board WHERE agent_assigned = ?", (clean_agent,)
            )
            return [self._deserialize_task(r) for r in rows]

    def list_tasks(
        self,
        status: str | None = None,
        agent: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[_TaskModel]:
        """List tasks with optional filtering by status and/or agent."""
        conditions = []
        params: list[Any] = []

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
            # condiciones fijas construidas internamente, valores parametrizados
            sql = f"SELECT * FROM tasks_board WHERE {where_clause} ORDER BY created_at DESC LIMIT ? OFFSET ?"  # nosec B608
            params.extend([limit, offset])
            rows = self._run_sqlite_query(sql, tuple(params))
            return [self._deserialize_task(r) for r in rows]

    def update_status(
        self, task_id: str, new_status: str, reason: str = ""
    ) -> _TaskModel | None:
        """Update a task's status and log the transition automatically."""
        new_status = _validate_status(new_status)
        task = self.read_task(task_id)
        if task is None:
            return None

        existing = task.to_dict()
        old_status = existing["status"]

        if old_status == new_status:
            return task

        transition: dict[str, Any] = {
            "from_status": old_status,
            "to_status": new_status,
            "timestamp": _now_iso(),
            "reason": reason,
        }

        history: list[dict[str, Any]] = existing.get("transition_history", [])
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
                # keys validados, valores parametrizados
                f"UPDATE tasks_board SET {set_clause} WHERE id = ?",  # nosec B608
                tuple(values),
            )

        return self._deserialize_task(serialized)

    def count_tasks(self, status: str | None = None) -> int:
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
