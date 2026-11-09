"""Tests de install_hooks: resolucion del directorio de hooks EFECTIVO.

Regresion (hook inerte): git ignora ``.git/hooks`` por completo cuando
``core.hooksPath`` esta definido (``install.ps1``/``install.sh`` -> ``.githooks``).
Antes el pre-commit se escribia en ``.git/hooks`` y git NUNCA lo ejecutaba.
``_resolve_hooks_dir`` debe devolver el directorio donde git SI mira.

Regresion 2 (checks silenciados): la plantilla resolvia la raiz con
``$(dirname $0)/../..``, que desde ``.githooks/`` cae FUERA del repo, asi que
todos los ``if [ -f ]`` fallaban en silencio y el hook solo imprimia
"[pre-commit] OK" sin validar nada. La raiz se resuelve ahora con
``git rev-parse --show-toplevel`` y el hook valida arquitectura y skills.
"""
from __future__ import annotations

from pathlib import Path

from harness.scripts.install_hooks import (
    _LOCAL_HOOK_TEMPLATE,
    _PROJECT_ROOT,
    _resolve_hooks_dir,
)


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


class TestPlantillaDelHook:
    """La plantilla del hook debe resolver la raiz y ejecutar sus gates."""

    def test_raiz_se_resuelve_con_git(self) -> None:
        """`git rev-parse --show-toplevel`; el `../..` anterior caia fuera."""
        assert "git rev-parse --show-toplevel" in _LOCAL_HOOK_TEMPLATE
        assert "/../.." not in _LOCAL_HOOK_TEMPLATE

    def test_fallback_sube_un_solo_nivel(self) -> None:
        """El fallback sube UN nivel desde ``.githooks/`` hasta la raiz."""
        assert '"$(dirname -- "$0")/.."' in _LOCAL_HOOK_TEMPLATE

    def test_incluye_los_gates(self) -> None:
        """El hook valida arquitectura (ratchet) y skills (script + tests)."""
        assert "--gate --ratchet" in _LOCAL_HOOK_TEMPLATE
        assert "validate_skills.py" in _LOCAL_HOOK_TEMPLATE
        assert "test_skill_*.py" in _LOCAL_HOOK_TEMPLATE

    def test_los_gates_bloquean(self) -> None:
        """Cada gate sale con ``exit`` ante un fallo (no sigue en silencio)."""
        template = _LOCAL_HOOK_TEMPLATE
        for bloque in ("violaciones arquitectonicas", "skills invalidos", "tests de skills fallan"):
            assert bloque in template
            inicio = template.index(bloque)
            assert "exit" in template[inicio : inicio + 200]
