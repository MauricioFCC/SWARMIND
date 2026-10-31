"""Tests del aviso de update en runtime (spec self-update-notice.md).

Adversarial: rate-limit sin tocar git, degradados sin cacheo de fallo,
excepciones nunca rompen el arranque.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from harness.self_update import CheckState, UpdateCheck
from harness.self_update import notice as notice_mod
from harness.self_update.notice import (
    NOTICE_STATE_VERSION,
    UpdateNotice,
    load_notice_state,
    notice_default_path,
    update_notice,
)

_REPO = Path("repo-simulado")


def _check(state: CheckState, behind: int = 0, ahead: int = 0) -> UpdateCheck:
    """UpdateCheck minimo para los tests (versiones fijas legibles)."""
    return UpdateCheck(
        state=state,
        behind=behind,
        ahead=ahead,
        local_version=(0, 11, 0),
        remote_version=(0, 11, 5) if behind else (0, 11, 0),
    )


def _patch_check(
    monkeypatch: pytest.MonkeyPatch,
    state: CheckState,
    behind: int = 0,
    ahead: int = 0,
) -> None:
    """Reemplaza check_remote por una funcion determinista (sin git)."""
    monkeypatch.setattr(
        notice_mod,
        "check_remote",
        lambda *a, **k: _check(state, behind=behind, ahead=ahead),
    )


class TestUpdateNotice:
    """Clasificacion de aviso por estado."""

    def test_behind_produces_notice_with_command(self, tmp_path, monkeypatch):
        """BEHIND da aviso con contador y comando sugerido."""
        _patch_check(monkeypatch, CheckState.BEHIND, behind=3)
        notice = update_notice(
            _REPO, state_path=tmp_path / "notice.json", run_git=lambda *a, **k: None
        )
        assert notice is not None
        assert notice.kind == "update"
        assert notice.behind == 3
        assert "!update check" in notice.message
        assert notice.command == "!update check"
        assert "0.11.5" in notice.message

    def test_up_to_date_and_ahead_are_not_reported(self, tmp_path, monkeypatch):
        """UP_TO_DATE y AHEAD no generan aviso (sin ruidos)."""
        state_path = tmp_path / "n.json"
        for state in (CheckState.UP_TO_DATE, CheckState.AHEAD):
            _patch_check(monkeypatch, state)
            assert (
                update_notice(
                    _REPO, state_path=state_path, run_git=lambda *a, **k: None
                )
                is None
            )
        # El state sí se marca (cooldown tras un fetch exitoso).
        payload = json.loads(state_path.read_text(encoding="utf-8"))
        assert payload["last_kind"] == "current"

    def test_diverged_asks_check_not_apply(self, tmp_path, monkeypatch):
        """DIVERGED informa el bloqueo, nunca sugiere aplicar a ciegas."""
        _patch_check(monkeypatch, CheckState.DIVERGED, behind=2, ahead=1)
        notice = update_notice(
            _REPO, state_path=tmp_path / "n.json", run_git=lambda *a, **k: None
        )
        assert notice is not None
        assert notice.kind == "diverged"
        assert "?update apply" not in notice.message

    def test_offline_returns_none_without_state(self, tmp_path, monkeypatch):
        """Degradados no avisan y no cachean el fallo (reintento pronto)."""
        state_path = tmp_path / "notice.json"
        for state in (CheckState.OFFLINE, CheckState.NO_GIT, CheckState.NO_REMOTE):
            _patch_check(monkeypatch, state)
            assert (
                update_notice(
                    _REPO, state_path=state_path, run_git=lambda *a, **k: None
                )
                is None
            )
        assert not state_path.exists(), "un fallo no debe fijar el cooldown"

    def test_exception_returns_none(self, tmp_path, monkeypatch):
        """Cualquier excepcion se degrade con log: el arranque no rompe."""

        def _boom(*_a, **_k):
            raise OSError("sin memoria")

        monkeypatch.setattr(notice_mod, "check_remote", _boom)
        assert (
            update_notice(
                _REPO, state_path=tmp_path / "n.json", run_git=lambda *a, **k: None
            )
            is None
        )


class TestCooldown:
    """Rate-limit: fetch solo cuando la ventana expira."""

    def test_cooldown_blocks_fetch(self, tmp_path, monkeypatch):
        """Dentro de la ventana no hay segunda llamada (0 fetch)."""
        fetched: list[str] = []
        monkeypatch.setattr(
            notice_mod,
            "check_remote",
            lambda *a, **k: (
                fetched.append("fetch"),
                _check(CheckState.BEHIND, behind=1),
            )[1],
        )
        state_path = tmp_path / "notice.json"
        first = update_notice(
            _REPO, state_path=state_path, run_git=lambda *a, **k: None
        )
        assert first is not None
        second = update_notice(
            _REPO, state_path=state_path, run_git=lambda *a, **k: None
        )
        assert second is None
        assert len(fetched) == 1

    def test_cooldown_expires_and_fetches_again(self, tmp_path, monkeypatch):
        """State con epoch viejo hace que vencida la ventana vuelva a fetch."""
        fetched: list[str] = []
        monkeypatch.setattr(
            notice_mod,
            "check_remote",
            lambda *a, **k: (
                fetched.append("fetch"),
                _check(CheckState.BEHIND, behind=1),
            )[1],
        )
        state_path = tmp_path / "notice.json"
        state_path.write_text(
            json.dumps(
                {
                    "checked_epoch": time.time() - 25 * 3600.0,
                    "last_kind": "update",
                    NOTICE_STATE_VERSION: 1,
                }
            ),
            encoding="utf-8",
        )
        notice = update_notice(
            _REPO,
            state_path=state_path,
            cooldown_hours=24.0,
            run_git=lambda *a, **k: None,
        )
        assert notice is not None
        assert len(fetched) == 1

    def test_state_survives_and_is_versioned(self, tmp_path, monkeypatch):
        """El state escrito incluye version y epoch (formato estable)."""
        _patch_check(monkeypatch, CheckState.UP_TO_DATE)
        state_path = tmp_path / "notice.json"
        update_notice(_REPO, state_path=state_path, run_git=lambda *a, **k: None)
        payload = json.loads(state_path.read_text(encoding="utf-8"))
        assert payload[NOTICE_STATE_VERSION] == 1
        assert payload["checked_epoch"] > 0
        assert payload["last_kind"] == "current"
        assert load_notice_state(state_path) == payload

    def test_cooldown_zero_always_fetches(self, tmp_path, monkeypatch):
        """cooldown_hours=0 (o negativo) anula el rate-limit (tests/CI)."""
        fetched: list[str] = []
        monkeypatch.setattr(
            notice_mod,
            "check_remote",
            lambda *a, **k: (fetched.append("fetch"), _check(CheckState.UP_TO_DATE))[1],
        )
        for _ in range(3):
            update_notice(
                _REPO,
                state_path=tmp_path / "n.json",
                cooldown_hours=0,
                run_git=lambda *a, **k: None,
            )
        assert len(fetched) == 3


class TestDefaults:
    """Path por defecto del state."""

    def test_default_path_lives_in_state_root(self, tmp_path, monkeypatch):
        """El path por defecto vive bajo ``.swarmind`` (junto al journal)."""
        monkeypatch.setattr(notice_mod, "_repo_root", lambda: tmp_path)
        path = notice_default_path()
        assert path.parent.name == ".swarmind"
        assert path.name == "update_notice.json"
        assert not path.exists(), "por defecto solo planifica, no toca disco"

    def test_default_path_is_not_version_dependent_of_cwd(self, tmp_path, monkeypatch):
        """El path no depende del cwd: nace del modulo, no de process cwd."""

        monkeypatch.setattr(notice_mod, "_repo_root", lambda: tmp_path)
        monkeypatch.chdir(tmp_path.parent)
        path = notice_default_path()
        assert path.parent.parent == tmp_path
class TestStartupHook:
    """Hook de arranque (SU-01/03/05/06)."""

    def _notice(self):
        return UpdateNotice(
            kind="update",
            message="update disponible: 1 commit en origin. !update check",
            command="!update check",
            behind=1,
        )

    def test_env_disabled_skips_fetch(self, monkeypatch):
        monkeypatch.setenv("SWARMIND_UPDATE_CHECK", "0")
        called = []
        monkeypatch.setattr(
            notice_mod, "update_notice", lambda *a, **k: (called.append("x"), None)[1]
        )
        from harness.run_support import print_update_notice_if_due

        assert print_update_notice_if_due() is False
        assert called == []

    def test_prints_notice_and_reports_true(self, tmp_path, monkeypatch, capsys):
        monkeypatch.delenv("SWARMIND_UPDATE_CHECK", raising=False)
        monkeypatch.setattr(notice_mod, "update_notice", lambda *a, **k: self._notice())
        from harness.run_support import print_update_notice_if_due

        assert print_update_notice_if_due(tmp_path) is True
        assert "update disponible" in capsys.readouterr().out

    def test_returns_false_when_not_due(self, monkeypatch):
        monkeypatch.delenv("SWARMIND_UPDATE_CHECK", raising=False)
        monkeypatch.setattr(notice_mod, "update_notice", lambda *a, **k: None)
        from harness.run_support import print_update_notice_if_due

        assert print_update_notice_if_due() is False

    def test_exception_is_silent(self, tmp_path, monkeypatch):
        def _boom(*_a, **_k):
            raise OSError("boom")

        monkeypatch.delenv("SWARMIND_UPDATE_CHECK", raising=False)
        monkeypatch.setattr(notice_mod, "update_notice", _boom)
        from harness.run_support import print_update_notice_if_due

        assert print_update_notice_if_due(tmp_path) is False
