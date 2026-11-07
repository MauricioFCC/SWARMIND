"""Tests de install_hooks: resolucion del directorio de hooks EFECTIVO.

Regresion (hook inerte): git ignora ``.git/hooks`` por completo cuando
``core.hooksPath`` esta definido (``install.ps1``/``install.sh`` -> ``.githooks``).
Antes el pre-commit se escribia en ``.git/hooks`` y git NUNCA lo ejecutaba.
``_resolve_hooks_dir`` debe devolver el directorio donde git SI mira.
"""
from __future__ import annotations

from pathlib import Path

from harness.scripts.install_hooks import _PROJECT_ROOT, _resolve_hooks_dir


class TestResolveHooksDir:
    """El directorio de hooks debe respetar ``core.hooksPath``."""

    def test_relative_override_resolves_under_project_root(self) -> None:
        """Un valor relativo se resuelve relativo a la raiz del proyecto."""
        assert _resolve_hooks_dir("custom/git-hooks") == (
            _PROJECT_ROOT / "custom" / "git-hooks"
        )

    def test_absolute_override_is_honored(self, tmp_path: Path) -> None:
        """Un valor absoluto se usa tal cual."""
        assert _resolve_hooks_dir(str(tmp_path)) == tmp_path

    def test_default_returns_effective_hooks_dir(self) -> None:
        """Sin override devuelve un directorio de hooks valido (no lanza)."""
        resolved = _resolve_hooks_dir()
        assert isinstance(resolved, Path)
        # ``.githooks`` cuando core.hooksPath esta definido; ``hooks`` (.git/hooks) si no.
        assert resolved.name in {"hooks", ".githooks"}
