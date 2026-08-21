"""Tests de task_protocol — lifecycle A2A y store idempotente (ADR-0058)."""
from __future__ import annotations

from pathlib import Path

import pytest

from harness.federation.task_protocol import (
    FederatedTask,
    TaskState,
    TaskStore,
)


class TestTaskState:
    """Estados terminales del lifecycle A2A."""

    def test_terminal_states(self) -> None:
        assert TaskState.COMPLETED.is_terminal
        assert TaskState.FAILED.is_terminal
        assert TaskState.CANCELED.is_terminal

    def test_non_terminal_states(self) -> None:
        assert not TaskState.SUBMITTED.is_terminal
        assert not TaskState.WORKING.is_terminal
        assert not TaskState.INPUT_REQUIRED.is_terminal


class TestFederatedTask:
    """Creación y transiciones de tareas inmutables."""

    def test_create_valid_task(self) -> None:
        task = FederatedTask.create(
            origin_project="onyx",
            target_project="cqe",
            skill_id="quant-lib-extension",
            prompt="implementa sharpe_ratio",
        )
        assert task.state is TaskState.SUBMITTED
        assert len(task.task_id) == 12

    @pytest.mark.parametrize(
        "kwargs",
        [
            {"origin_project": "", "target_project": "cqe",
             "skill_id": "s", "prompt": "p"},
            {"origin_project": "onyx", "target_project": " ",
             "skill_id": "s", "prompt": "p"},
            {"origin_project": "onyx", "target_project": "cqe",
             "skill_id": "", "prompt": "p"},
            {"origin_project": "onyx", "target_project": "cqe",
             "skill_id": "s", "prompt": ""},
        ],
    )
    def test_create_empty_fields_raise(self, kwargs: dict[str, str]) -> None:
        with pytest.raises(ValueError, match="está vacío"):
            FederatedTask.create(**kwargs)  # type: ignore[arg-type]

    def test_transition_updates_state_and_timestamp(self) -> None:
        task = FederatedTask.create("o", "t", "s", "p")
        working = task.transition(TaskState.WORKING)
        assert working.state is TaskState.WORKING
        assert working.updated_at >= task.updated_at
        # Inmutabilidad: la original no cambia.
        assert task.state is TaskState.SUBMITTED

    def test_transition_from_terminal_raises(self) -> None:
        done = FederatedTask.create("o", "t", "s", "p").transition(
            TaskState.WORKING
        ).transition(TaskState.COMPLETED)
        with pytest.raises(ValueError, match="terminal"):
            done.transition(TaskState.FAILED)

    def test_illegal_transition_raises(self) -> None:
        task = FederatedTask.create("o", "t", "s", "p")
        with pytest.raises(ValueError, match="ilegal"):
            task.transition(TaskState.COMPLETED)  # submitted→completed


class TestTaskStore:
    """Persistencia idempotente en .opencode/federated/tasks."""

    def test_save_and_load_roundtrip(self, tmp_path: Path) -> None:
        store = TaskStore(tmp_path)
        task = FederatedTask.create("onyx", "cqe", "s", "p")
        store.save(task)
        loaded = store.load(task.task_id)
        assert loaded == task

    def test_duplicate_save_raises(self, tmp_path: Path) -> None:
        store = TaskStore(tmp_path)
        task = FederatedTask.create("o", "t", "s", "p")
        store.save(task)
        with pytest.raises(ValueError, match="ya existe"):
            store.save(task)

    def test_update_applies_transition_and_persists(
        self, tmp_path: Path
    ) -> None:
        store = TaskStore(tmp_path)
        task = FederatedTask.create("o", "t", "s", "p")
        store.save(task)
        updated = store.update(task.task_id, TaskState.WORKING)
        assert store.load(task.task_id).state is TaskState.WORKING
        assert updated.state is TaskState.WORKING

    def test_load_missing_raises_file_not_found(self, tmp_path: Path) -> None:
        store = TaskStore(tmp_path)
        with pytest.raises(FileNotFoundError, match="no existe"):
            store.load("fantasma")

    def test_list_tasks_filter_by_target(self, tmp_path: Path) -> None:
        store = TaskStore(tmp_path)
        t1 = FederatedTask.create("a", "cqe", "s", "p1")
        t2 = FederatedTask.create("b", "onyx", "s", "p2")
        store.save(t1)
        store.save(t2)
        targets = [t.target_project for t in store.list_tasks(target_project="cqe")]
        assert targets == ["cqe"]

    def test_deserialize_unknown_state_raises(self, tmp_path: Path) -> None:
        store = TaskStore(tmp_path)
        task = FederatedTask.create("o", "t", "s", "p")
        path = store.save(task)
        corrupt = path.read_text(encoding="utf-8").replace(
            '"submitted"', '"estado-raro"'
        )
        path.write_text(corrupt, encoding="utf-8")
        with pytest.raises(ValueError, match="desconocido"):
            store.load(task.task_id)
