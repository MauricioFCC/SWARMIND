"""Tests de federation_bus — gobernanza deny-by-default y activación (ADR-0058)."""
from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from harness.federation.agent_card import AgentCard, AgentSkill, write_agent_card
from harness.federation.federation_bus import (
    FederationBus,
    GovernancePolicy,
    _mask_prompt,
)
from harness.federation.task_protocol import FederatedTask, TaskState


def _make_projects(tmp_path: Path) -> Path:
    """Crea client-app y provider-lib con cards válidas."""
    write_agent_card(
        AgentCard(
            name="client-app",
            description="App cliente",
            version="1.0.0",
            project_root=tmp_path / "client-app",
            skills=(),
        ),
        tmp_path / "client-app",
    )
    write_agent_card(
        AgentCard(
            name="provider-lib",
            description="Libreria compartida",
            version="1.0.0",
            project_root=tmp_path / "provider-lib",
            skills=(
                AgentSkill(
                    id="library-extension",
                    name="Extensión",
                    description="Implementa funciones",
                    tags=("library",),
                ),
            ),
        ),
        tmp_path / "provider-lib",
    )
    return tmp_path


def _policy() -> GovernancePolicy:
    """Allowlist: solo client-app→provider-lib."""
    return GovernancePolicy(allowlist={"client-app": frozenset({"provider-lib"})})


def _task() -> FederatedTask:
    """Tarea client-app→provider-lib válida."""
    return FederatedTask.create(
        origin_project="client-app",
        target_project="provider-lib",
        skill_id="library-extension",
        prompt="implementa la funcion faltante del modulo",
    )


class TestGovernancePolicy:
    """Matriz deny-by-default."""

    def test_explicit_pair_allowed(self) -> None:
        assert _policy().can_delegate("client-app", "provider-lib")

    def test_missing_origin_denied(self) -> None:
        assert not _policy().can_delegate("desconocido", "provider-lib")

    def test_reverse_pair_denied(self) -> None:
        assert not _policy().can_delegate("provider-lib", "client-app")


class TestSendTask:
    """Envío gobernado con subprocess mockeado."""

    def test_denied_pair_raises_permission_error(self, tmp_path: Path) -> None:
        root = _make_projects(tmp_path)
        bus = FederationBus(root, policy=_policy(), store_dir=tmp_path)
        rogue = FederatedTask.create("provider-lib", "client-app", "s", "p")
        with pytest.raises(PermissionError, match="denegada"):
            bus.send_task(rogue)
        assert bus.audit_trail[-1].action == "authorize-deny"

    def test_non_submitted_task_raises(self, tmp_path: Path) -> None:
        root = _make_projects(tmp_path)
        bus = FederationBus(root, policy=_policy(), store_dir=tmp_path)
        working = _task().transition(TaskState.WORKING)
        with pytest.raises(ValueError, match="SUBMITTED"):
            bus.send_task(working)

    def test_unknown_skill_raises_value_error(self, tmp_path: Path) -> None:
        root = _make_projects(tmp_path)
        bus = FederationBus(root, policy=_policy(), store_dir=tmp_path)
        bad = FederatedTask.create("client-app", "provider-lib", "skill-fantasma", "p")
        with pytest.raises(ValueError, match="no declara"):
            bus.send_task(bad)

    def test_unknown_target_raises_file_not_found(self, tmp_path: Path) -> None:
        root = _make_projects(tmp_path)
        policy = GovernancePolicy(allowlist={"client-app": frozenset({"fantasma"})})
        bus = FederationBus(root, policy=policy, store_dir=tmp_path)
        ghost = FederatedTask.create("client-app", "fantasma", "s", "p")
        with pytest.raises(FileNotFoundError, match="no existe"):
            bus.send_task(ghost)

    def test_successful_send_completes(self, tmp_path: Path) -> None:
        root = _make_projects(tmp_path)
        bus = FederationBus(root, policy=_policy(), store_dir=tmp_path)
        fake = subprocess.CompletedProcess(args=[], returncode=0,
                                           stdout="hecho", stderr="")
        with patch("harness.federation.federation_bus.subprocess.run",
                   return_value=fake):
            result = bus.send_task(_task())
        assert result.exit_code == 0
        assert result.stdout_preview == "hecho"
        stored = bus._store.load(result.task.task_id)
        assert stored.state.value == "completed"

    def test_failing_send_marks_failed_with_error(self, tmp_path: Path) -> None:
        root = _make_projects(tmp_path)
        bus = FederationBus(root, policy=_policy(), store_dir=tmp_path)
        fake = subprocess.CompletedProcess(args=[], returncode=2,
                                           stdout="", stderr="ModuleNotFound")
        with patch("harness.federation.federation_bus.subprocess.run",
                   return_value=fake):
            result = bus.send_task(_task())
        assert result.task.state.value == "failed"
        assert "exit code 2" in result.task.error

    def test_timeout_marks_failed(self, tmp_path: Path) -> None:
        root = _make_projects(tmp_path)
        bus = FederationBus(root, policy=_policy(), store_dir=tmp_path,
                            timeout_seconds=1)
        with patch(
            "harness.federation.federation_bus.subprocess.run",
            side_effect=subprocess.TimeoutExpired(cmd=[], timeout=1),
        ):
            result = bus.send_task(_task())
        assert result.task.state.value == "failed"
        assert "timeout" in result.task.error.lower()

    def test_audit_trail_records_send_and_complete(self, tmp_path: Path) -> None:
        root = _make_projects(tmp_path)
        bus = FederationBus(root, policy=_policy(), store_dir=tmp_path)
        fake = subprocess.CompletedProcess(args=[], returncode=0,
                                           stdout="", stderr="")
        with patch("harness.federation.federation_bus.subprocess.run",
                   return_value=fake):
            bus.send_task(_task())
        actions = [e.action for e in bus.audit_trail]
        assert actions == ["send", "complete"]


class TestMaskPrompt:
    """Enmascaramiento de prompts para el audit trail."""

    def test_short_prompt_untouched(self) -> None:
        assert _mask_prompt("hola mundo") == "hola mundo"

    def test_long_prompt_truncated(self) -> None:
        masked = _mask_prompt("x" * 500)
        assert len(masked) < 120
        assert masked.endswith("...")

    def test_whitespace_normalized(self) -> None:
        assert _mask_prompt("a\n\n  b") == "a b"
