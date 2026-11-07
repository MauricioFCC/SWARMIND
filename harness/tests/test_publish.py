"""Tests de `scripts/publish.py` (push + sync + verify)."""

from __future__ import annotations

from scripts import publish


class _Result:
    """Resultado mínimo compatible con ``subprocess.CompletedProcess``."""

    def __init__(self, returncode: int = 0, stdout: str = "", stderr: str = "") -> None:
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


class TestHelpers:
    """Funciones puras de decisión."""

    def test_clean_tree(self):
        """Sin líneas en porcelain el árbol está limpio."""
        assert publish.is_clean("") is True
        assert publish.is_clean("  \n") is True

    def test_dirty_tree(self):
        """Cualquier línea de porcelain bloquea la publicación."""
        assert publish.is_clean(" M harness/x.py\n") is False

    def test_push_args_with_upstream(self):
        """Con upstream se usa `git push` simple."""
        assert publish.push_args("main", True) == ["push"]

    def test_push_args_without_upstream_sets_origin(self):
        """Sin upstream se configura `-u origin <branch>`."""
        assert publish.push_args("feat/x", False) == ["push", "-u", "origin", "feat/x"]


class TestMain:
    """Flujo de publicación con git/scripts simulados."""

    def _fake_git(self, monkeypatch, *, clean: bool = True, push_rc: int = 0) -> None:
        def _git(*args: str) -> _Result:
            if args[:2] == ("status", "--porcelain"):
                return _Result(0, "" if clean else " M x\n")
            if args[:2] == ("rev-parse", "--abbrev-ref"):
                return _Result(0, "feat/x\n")
            if args[0] == "push":
                return _Result(push_rc, "", "" if push_rc == 0 else "rejected")
            return _Result(0, "")

        monkeypatch.setattr(publish, "_git", _git)

    def test_dirty_tree_blocks(self, monkeypatch, capsys):
        """Con cambios sin commitear no se publica."""
        self._fake_git(monkeypatch, clean=False)
        assert publish.main([]) == 1
        assert "arbol_sucio" in capsys.readouterr().err

    def test_dry_run_does_not_push(self, monkeypatch):
        """Dry-run valida el plan sin ejecutar git push ni scripts."""
        self._fake_git(monkeypatch)
        called: list[str] = []
        monkeypatch.setattr(publish, "_run", lambda *a: called.append("run") or _Result())
        assert publish.main(["--dry-run"]) == 0
        assert called == []

    def test_push_failure_returns_1(self, monkeypatch, capsys):
        """Un push rechazado se reporta con exit 1."""
        self._fake_git(monkeypatch, push_rc=1)
        assert publish.main([]) == 1
        assert "push_fallo" in capsys.readouterr().err

    def test_success_runs_sync_and_verify(self, monkeypatch):
        """El camino feliz ejecuta sync + verify y devuelve 0."""
        self._fake_git(monkeypatch)
        scripts: list[str] = []

        def _run(script: str, *_args: str) -> _Result:
            scripts.append(script)
            return _Result()

        monkeypatch.setattr(publish, "_run", _run)
        assert publish.main([]) == 0
        assert scripts == ["sync_opencode_global.py", "verify_global_sync.py"]

    def test_drift_after_sync_returns_1(self, monkeypatch, capsys):
        """Si la verificación post-sync detecta drift, falla."""
        self._fake_git(monkeypatch)

        def _run(script: str, *_args: str) -> _Result:
            return _Result(1 if script == "verify_global_sync.py" else 0)

        monkeypatch.setattr(publish, "_run", _run)
        assert publish.main([]) == 1
        assert "drift_post_sync" in capsys.readouterr().err
