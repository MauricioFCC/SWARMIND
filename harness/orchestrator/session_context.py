"""
Session Context — Preserves execution state across iterations.

Tracks the current plan, which subtasks are completed, what's pending,
and maintains a history of all results. This ensures the coordinator
NEVER loses context between user messages.

Key features:
  - Auto-saves to LanceDB for persistence across restarts
  - Tracks per-subtask results and completion status
  - Provides a summary of what was done and what's next
  - Supports multiple concurrent sessions
"""

from __future__ import annotations

import json
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import numpy as np

from harness.orchestrator.task_planner import SubTask, TaskPlan

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Session state
# ---------------------------------------------------------------------------

@dataclass
class SessionState:
    """
    Full state of a work session.

    Persisted to LanceDB so the coordinator can resume any session.
    """
    session_id: str
    original_message: str
    plan: "TaskPlan"
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    completed: bool = False
    messages: List[Dict] = field(default_factory=list)

    def to_dict(self) -> Dict:
        return {
            "session_id": self.session_id,
            "original_message": self.original_message,
            "plan": self.plan.to_dict(),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "completed": self.completed,
            "messages": self.messages[-20:],  # keep last 20
        }


# ---------------------------------------------------------------------------
# SessionContext
# ---------------------------------------------------------------------------

_SESSION_COLLECTION = "session_context"


class SessionContext:
    """
    Manages session state across user messages.

    Each message from a user creates or continues a session. The session
    tracks the task plan, subtask completions, results, and conversation
    history.

    Usage:
        ctx = SessionContext()
        session = ctx.get_or_create("user message")
        # ... work on subtasks ...
        ctx.mark_subtask_done(session, "st-1", "result")
        summary = ctx.get_status(session)
    """

    def __init__(self, vector_store: Optional[Any] = None) -> None:
        """
        Args:
            vector_store: LanceVectorStore instance. If None, runs in
                          memory-only mode (no persistence).
        """
        self._store = vector_store
        self._active_sessions: Dict[str, SessionState] = {}
        self._embedding_dim = 384

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_or_create(self, message: str, plan: TaskPlan) -> SessionState:
        """
        Get existing session for this message or create a new one.

        Uses the plan's session_id to track continuity. If the message
        is continuing previous work (no new plan), tries to find the
        last active session.

        Args:
            message: The user message.
            plan: The TaskPlan (may be None for continuation messages).

        Returns:
            SessionState for this session.
        """
        # If we have a plan, create new session
        if plan is not None:
            session = SessionState(
                session_id=plan.session_id,
                original_message=plan.original_message,
                plan=plan,
            )
            self._active_sessions[plan.session_id] = session
            self._persist(session)
            logger.info(
                "Session %s created: %s",
                session.session_id, plan.original_message[:60],
            )
            return session

        # Try to find the last active session
        last_session = self._load_most_recent()
        if last_session:
            # Add message to existing session
            last_session.messages.append({
                "role": "user",
                "content": message,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })
            last_session.updated_at = datetime.now(timezone.utc).isoformat()
            self._persist(last_session)
            logger.info("Session %s resumed.", last_session.session_id)
            return last_session

        # No session exists — create one without a plan
        sid = str(uuid.uuid4())[:8]
        empty_plan = TaskPlan(session_id=sid, original_message=message)
        session = SessionState(
            session_id=sid,
            original_message=message,
            plan=empty_plan,
        )
        self._active_sessions[sid] = session
        self._persist(session)
        logger.info("Session %s created (no plan).", sid)
        return session

    def get_session(self, session_id: str) -> Optional[SessionState]:
        """Get a session by ID."""
        if session_id in self._active_sessions:
            return self._active_sessions[session_id]
        return self._load_from_store(session_id)

    def get_active(self) -> Optional[SessionState]:
        """Get the most recent active session."""
        if self._active_sessions:
            # Return most recently updated
            return max(
                self._active_sessions.values(),
                key=lambda s: s.updated_at,
            )
        return self._load_most_recent()

    def mark_subtask_done(
        self,
        session: SessionState,
        subtask_id: str,
        result: str = "",
    ) -> bool:
        """
        Mark a subtask as completed with its result.

        Args:
            session: The session state.
            subtask_id: The subtask ID to mark done.
            result: The result/artifact from the subtask.

        Returns:
            True if the subtask was found and marked.
        """
        for st in session.plan.subtasks:
            if st.id == subtask_id:
                st.completed = True
                st.result = result
                session.updated_at = datetime.now(timezone.utc).isoformat()
                self._persist(session)

                progress = (
                    sum(1 for s in session.plan.subtasks if s.completed),
                    len(session.plan.subtasks),
                )
                logger.info(
                    "Session %s: subtask %s done (%d/%d)",
                    session.session_id, subtask_id, progress[0], progress[1],
                )

                # Check if session is complete
                if session.plan.is_complete():
                    session.completed = True
                    self._persist(session)
                    logger.info(
                        "Session %s COMPLETE!", session.session_id,
                    )
                return True

        logger.warning(
            "Session %s: subtask %s not found.",
            session.session_id, subtask_id,
        )
        return False

    def add_message(self, session: SessionState, role: str, content: str) -> None:
        """Add a message to the session history."""
        session.messages.append({
            "role": role,
            "content": content,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
        session.updated_at = datetime.now(timezone.utc).isoformat()
        self._persist(session)

    def get_status(self, session: SessionState) -> str:
        """
        Get a human-readable status of the session.

        Returns a formatted string showing:
          - Overall progress
          - Current level (what's executing now)
          - Next steps
          - Completed subtasks and their results
        """
        plan = session.plan
        total = len(plan.subtasks)
        done = sum(1 for s in plan.subtasks if s.completed)

        lines = [
            f"🔵 Sesión: {session.session_id}",
            f"📝 Tarea original: {plan.original_message[:100]}",
            f"📊 Progreso: {done}/{total} subtasks",
        ]

        # Show completed
        completed = [s for s in plan.subtasks if s.completed]
        if completed:
            lines.append(f"\n✅ Completadas ({len(completed)}):")
            for s in completed:
                lines.append(f"   ✅ [{s.agent}] {s.description}")
                if s.result:
                    # Truncate long results
                    result_preview = s.result[:120].replace('\n', ' ')
                    lines.append(f"      → {result_preview}...")

        # Show current level (ready to execute)
        next_level = plan.get_next_level()
        if next_level:
            is_parallel = len(next_level) > 1
            mode = "⚡ PARALELO" if is_parallel else "→ SECUENCIAL"
            lines.append(f"\n⏳ Siguiente nivel ({mode}):")
            for s in next_level:
                lines.append(f"   ⏳ [{s.agent}] {s.description}")

        # Show future levels
        all_levels = plan.get_levels()
        future_found = False
        for level in all_levels:
            if all(s.completed for s in level):
                continue
            if all(s.id in {st.id for st in next_level} for s in level):
                continue
            if not future_found:
                lines.append(f"\n⏸️  Próximos pasos:")
                future_found = True
            for s in level:
                if not s.completed and s not in next_level:
                    lines.append(f"   ⏸️  [{s.agent}] {s.description}")

        if session.completed:
            lines.append(f"\n🎉 ¡Sesión COMPLETA!")

        return "\n".join(lines)

    def _persist(self, session: SessionState) -> None:
        """Save session state to LanceDB."""
        if self._store is None:
            return
        try:
            vec = np.zeros(self._embedding_dim, dtype=np.float32)
            data = session.to_dict()
            # Store metadata as JSON string
            self._store.insert(
                _SESSION_COLLECTION,
                vec.reshape(1, -1),
                [{"session_id": session.session_id, "data": json.dumps(data)}],
            )
        except Exception as exc:
            logger.debug("Session persist error (non-fatal): %s", exc)

    def _load_from_store(self, session_id: str) -> Optional[SessionState]:
        """Load a session from LanceDB."""
        if self._store is None:
            return None
        try:
            dummy = np.zeros(self._embedding_dim, dtype=np.float32)
            results = self._store.search(
                _SESSION_COLLECTION, dummy, top_k=10,
                filters={"session_id": session_id},
            )
            if results:
                return self._deserialize(results[0])
        except Exception:
            pass
        return None

    def _load_most_recent(self) -> Optional[SessionState]:
        """Load the most recent session from LanceDB."""
        if self._store is None:
            return None
        try:
            dummy = np.zeros(self._embedding_dim, dtype=np.float32)
            results = self._store.search(
                _SESSION_COLLECTION, dummy, top_k=20,
            )
            if results:
                # Find the one with the latest updated_at
                best = max(results, key=lambda r: (
                    json.loads(r.get("metadata", {}).get("data", "{}")).get("updated_at", ""))
                )
                return self._deserialize(best)
        except Exception:
            pass
        return None

    def _deserialize(self, record: Dict) -> Optional[SessionState]:
        """Deserialize a LanceDB record into SessionState."""
        try:
            meta = record.get("metadata", {})
            if isinstance(meta, str):
                meta = json.loads(meta)
            data_str = meta.get("data", "{}")
            if isinstance(data_str, str):
                data = json.loads(data_str)
            else:
                data = data_str

            plan_data = data.get("plan", {})
            subtasks_data = plan_data.get("subtasks", [])
            subtasks = [
                SubTask(
                    id=s["id"],
                    agent=s["agent"],
                    description=s["description"],
                    dependencies=s.get("dependencies", []),
                    expected_output=s.get("expected_output", ""),
                    context_hint=s.get("context_hint", ""),
                    completed=s.get("completed", False),
                    result=s.get("result", ""),
                )
                for s in subtasks_data
            ]
            plan = TaskPlan(
                session_id=plan_data.get("session_id", data.get("session_id", "")),
                original_message=plan_data.get("original_message", data.get("original_message", "")),
                subtasks=subtasks,
            )
            return SessionState(
                session_id=data.get("session_id", ""),
                original_message=data.get("original_message", ""),
                plan=plan,
                created_at=data.get("created_at", ""),
                updated_at=data.get("updated_at", ""),
                completed=data.get("completed", False),
                messages=data.get("messages", []),
            )
        except Exception as exc:
            logger.debug("Session deserialize error: %s", exc)
            return None
