"""Gate: la version del proyecto debe seguir el ciclo del CHANGELOG.

WHAT: ``pyproject.toml`` declara ``project.version`` y el CHANGELOG abre con
``## [<ciclo>]``. El auto-update usa esa version como cota anti-downgrade
(``_downgrade_blocked``), asi que un placeholder fijo (``0.1.0``) deja el gate
inerte: remoto y local siempre valen lo mismo.

WHY: verificado 2026-11-10 — con ``version = "0.1.0"`` y CHANGELOG en 11.91, el
merge ff-only protegia el avance pero el gate semver nunca podia bloquear una
reversion.

WHERE: ``pyproject.toml`` + ``CHANGELOG.md``; consumido por
``harness/self_update/core.py::parse_version``.
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

from harness.self_update import fmt_version, parse_semver, parse_version

ROOT = Path(__file__).resolve().parents[2]


def _version_pyproject() -> tuple[int, ...]:
    """Version declarada en ``pyproject.toml`` como tupla comparable."""
    data = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    parsed = parse_semver(str(data["project"]["version"]))
    assert parsed is not None, "pyproject.project.version ilegible"
    return parsed


def _version_changelog() -> tuple[int, ...]:
    """Primer ``## [X.Y]`` del CHANGELOG como tupla comparable."""
    texto = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    match = re.search(r"^## \[(\d+\.\d+(?:\.\d+)?)\]", texto, re.MULTILINE)
    assert match is not None, "CHANGELOG sin encabezado ## [X.Y]"
    parsed = parse_semver(match.group(1))
    assert parsed is not None, f"version de CHANGELOG ilegible: {match.group(1)}"
    return parsed


def test_version_pyproject_alineada_con_changelog() -> None:
    """Ambas fuentes declaran el mismo ciclo (sin drift)."""
    pyproject_v = _version_pyproject()
    changelog_v = _version_changelog()

    assert pyproject_v == changelog_v, (
        f"drift de version: pyproject={fmt_version(pyproject_v)} "
        f"changelog={fmt_version(changelog_v)}; actualiza pyproject.toml"
    )


def test_version_no_es_placeholder() -> None:
    """La version no puede quedar en 0.x (dejaria inerte el anti-downgrade)."""
    version = _version_pyproject()

    assert version >= (11, 0, 0), (
        f"version {fmt_version(version)} parece placeholder; el gate "
        "anti-downgrade de self_update solo funciona con el ciclo real"
    )


def test_parse_version_del_repo_usa_pyproject() -> None:
    """``parse_version`` (motor de update) coincide con la version declarada."""
    assert parse_version(ROOT) == _version_pyproject()
