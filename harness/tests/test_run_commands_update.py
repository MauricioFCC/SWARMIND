"""Tests del comando ``!update`` (spec self-update-notice.md AC-SU5)."""

from __future__ import annotations

import pytest

import harness.run_commands as run_commands_mod
import harness.run_commands.handlers_other as handlers
from harness.self_update import (
    Action,
    CheckState,
    UpdateCheck,
    UpdateResult,
)

_REPO = None


def _check(state: CheckState = CheckState.UP_TO_DATE, behind: int = 0) -> UpdateCheck:
    """UpdateCheck minimo y determinista."""
    return UpdateCheck(
        state=state,
        behind=behind,
        ahead=0,
        local_version=(0, 11, 0),
        remote_version=(0, 11, 5) if behind else (0, 11, 0),
    )


class _Recorder:
    """Captura los mensajes renderizados del logger del paquete."""

    def __init__(self) -> None:
        self.infos: list[str] = []
        self.warnings: list[str] = []
        self.errors: list[str] = []

    def info(self, msg: str, *args: object) -> None:
        self.infos.append(msg % args if args else msg)

    def warning(self, msg: str, *args: object) -> None:
        self.warnings.append(msg % args if args else msg)

    def error(self, msg: str, *args: object) -> None:
        self.errors.append(msg % args if args else msg)

    def text(self) -> str:
        return " | ".join([*self.infos, *self.warnings, *self.errors])


@pytest.fixture
def spy_logger(monkeypatch):
    """Logger del paquete run_commands sustituido por el recorder."""
    recorder = _Recorder()
    monkeypatch.setattr(run_commands_mod, "logger", recorder)
    return recorder


class TestUpdateCommand:
    """Cada accion usa las funciones puras del core con guards intactos."""

    def test_check_logs_state(self, tmp_path, monkeypatch, spy_logger):
        """`!update check` imprime estado/behind/versiones sin mutar."""
        monkeypatch.setattr(handlers, "check_remote", lambda repo: _check(
            CheckState.BEHIND, behind=3
        ))
        handlers._handle_update("!update check", tmp_path)
        calls = spy_logger.text()
        assert "estado=behind" in calls
        assert "behind=3" in calls
        assert spy_logger.warnings == []

    def test_check_uses_repo_root(self, tmp_path, monkeypatch, spy_logger):
        """check_remote recibe la raiz entregada por run_commands."""
        seen: list[object] = []
        monkeypatch.setattr(
            handlers, "check_remote", lambda repo: seen.append(repo) or _check()
        )
        handlers._handle_update("!update check", tmp_path)
        assert seen == [tmp_path.resolve()]

    def test_apply_uses_guards_and_reports_action(
        self, tmp_path, monkeypatch, spy_logger
    ):
        """`!update apply` aplica via core; el resultado se reporta."""
        monkeypatch.setattr(handlers, "check_remote", lambda repo: _check())
        seen: dict[str, object] = {}

        def _apply(check, *, repo, log_path, allow_downgrade, downgrade_justification):
            seen["repo"] = repo
            seen["log"] = log_path
            seen["allow"] = allow_downgrade
            seen["just"] = downgrade_justification
            return UpdateResult(action=Action.UPDATED, changed=True, detail="ff")

        monkeypatch.setattr(handlers, "apply_update", _apply)
        handlers._handle_update("!update apply", tmp_path)
        assert seen["repo"] == tmp_path.resolve()
        assert seen["log"].name == "update_log.jsonl"
        assert seen["log"].parent.name == ".swarmind"
        assert seen["allow"] is False
        assert "accion=updated" in spy_logger.text()

    def test_apply_downgrade_requires_flag_and_justification(
        self, tmp_path, monkeypatch, spy_logger
    ):
        """Flags llegan al core (la responsabilidad anti-reversion es del core)."""
        monkeypatch.setattr(handlers, "check_remote", lambda repo: _check())
        seen: dict[str, object] = {}

        def _apply(_check, **kwargs):
            seen.update(kwargs)
            return UpdateResult(Action.DOWNGRADE_FORCED, True, "forced")

        monkeypatch.setattr(handlers, "apply_update", _apply)
        handlers._handle_update(
            "!update apply --allow-downgrade --justification=rollback-test",
            tmp_path,
        )
        assert seen["allow_downgrade"] is True
        assert seen["downgrade_justification"] == "rollback-test"
        assert "accion=downgrade_forced" in spy_logger.text()

    def test_audit_reports_monotonicity(self, tmp_path, monkeypatch, spy_logger):
        """`!update audit` consulta audit_log del core ( misconduct detectable)."""
        monkeypatch.setattr(handlers, "audit_log", lambda path: ["x"])
        handlers._handle_update("!update audit", tmp_path)
        assert "violaciones=1" in spy_logger.text()

    def test_failed_apply_logs_error(self, tmp_path, monkeypatch, spy_logger):
        """Un apply que falla se registra como error (no se oculta)."""
        monkeypatch.setattr(handlers, "check_remote", lambda repo: _check())

        def _apply(_check, **_kw):
            return UpdateResult(Action.FAILED, False, "merge conflict")

        monkeypatch.setattr(handlers, "apply_update", _apply)
        handlers._handle_update("!update apply", tmp_path)
        assert spy_logger.errors, "error de merge se registra"
        assert "merge conflict" in spy_logger.errors[0]


class TestFilenames:
    """Constantes del journal equal al CLI standalone."""

    def test_journal_matches_scripts_default(self, tmp_path) -> None:
        """`scripts/self_update.py` y `!update` comparten journal y raíz."""
        import sys
        from pathlib import Path

        scripts_dir = Path(__file__).resolve().parents[2] / "scripts"
        sys.path.insert(1, str(scripts_dir))
        import importlib

        mod = importlib.import_module("self_update")
        expected = (mod._REPO / ".swarmind" / "update_log.jsonl").name
        assert expected == "update_log.jsonl"
