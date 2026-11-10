"""Tests del auto-update de la instalacion GLOBAL de opencode (sello + clone).

Contratos:
  1. El sello (``.swarmind/install.json``) se escribe/lee y los formatos
     invalidos degradan a ``None`` (nunca lanzan).
  2. ``check_install`` compara el sello con ``git ls-remote`` sin clonar y
     clasifica UP_TO_DATE / BEHIND / OFFLINE / NO_REMOTE.
  3. ``apply_install`` clona, ejecuta el sync oficial, re-sella y limpia.
  4. ``install_notice`` respeta el cooldown y solo avisa si hay commits nuevos.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from harness.self_update import (
    CheckState,
    InstallStamp,
    apply_install,
    check_install,
    install_notice,
    read_stamp,
    stamp_from_repo,
    write_stamp,
)
from harness.self_update import install as install_mod
from harness.self_update.core import GitResult

_SHA_VIEJO = "a" * 40
_SHA_NUEVO = "b" * 40


def _fake_git(mapping: dict[str, GitResult]):
    """Runner DI que despacha por el primer argumento de git."""

    def _runner(args, cwd, timeout=60):
        return mapping.get(args[0], GitResult(1, "", f"inesperado: {args[0]}"))

    return _runner


def _stamp(**overrides) -> InstallStamp:
    """Sello base valido para los tests."""
    base = {
        "source": "https://github.com/MauricioFCC/SWARMIND.git",
        "branch": "main",
        "commit": _SHA_VIEJO,
        "version": "0.1.0",
        "synced_at": "2026-11-10T00:00:00+00:00",
    }
    base.update(overrides)
    return InstallStamp(**base)


def test_write_read_stamp_roundtrip(tmp_path: Path) -> None:
    """El sello persiste todos los campos en JSON versionado."""
    write_stamp(tmp_path, _stamp())

    leido = read_stamp(tmp_path)

    assert leido == _stamp()
    payload = json.loads((tmp_path / ".swarmind" / "install.json").read_text(encoding="utf-8"))
    assert payload["stamp_version"] == install_mod.STAMP_VERSION


@pytest.mark.parametrize(
    "contenido",
    ["", "no-json", "[]", json.dumps({"stamp_version": 999, "source": "x"})],
)
def test_read_stamp_invalido_degrada_a_none(tmp_path: Path, contenido: str) -> None:
    """Un sello corrupto o de otro formato no revienta."""
    destino = tmp_path / ".swarmind" / "install.json"
    destino.parent.mkdir(parents=True)
    destino.write_text(contenido, encoding="utf-8")

    assert read_stamp(tmp_path) is None


def test_stamp_from_repo_lee_origin_rama_y_version(tmp_path: Path) -> None:
    """El clon fuente aporta url, rama, commit y version de pyproject."""
    (tmp_path / "pyproject.toml").write_text('[project]\nversion = "11.91"\n', encoding="utf-8")
    runner = _fake_git({
        "remote": GitResult(0, "https://github.com/MauricioFCC/SWARMIND.git", ""),
        "rev-parse": GitResult(0, _SHA_VIEJO, ""),
    })

    def _runner(args, cwd, timeout=60):
        if args[:2] == ["rev-parse", "--abbrev-ref"]:
            return GitResult(0, "main", "")
        return runner(args, cwd, timeout)

    stamp = stamp_from_repo(tmp_path, run_git=_runner)

    assert stamp is not None
    assert stamp.source.endswith("SWARMIND.git")
    assert stamp.branch == "main"
    assert stamp.commit == _SHA_VIEJO
    assert stamp.version == "11.91"


def test_stamp_from_repo_sin_origin_devuelve_none(tmp_path: Path) -> None:
    """Sin origin no hay sello (no se inventa un remoto)."""
    runner = _fake_git({"remote": GitResult(2, "", "no origin")})

    assert stamp_from_repo(tmp_path, run_git=runner) is None


def test_check_install_sin_sello(tmp_path: Path) -> None:
    """Sin sello la copia no puede comprobarse y se reporta degradado."""
    check = check_install(tmp_path, run_git=_fake_git({}))

    assert check.state is CheckState.NO_GIT
    assert "install.json" in check.detail


def test_check_install_al_dia(tmp_path: Path) -> None:
    """Mismo SHA local y remoto => UP_TO_DATE."""
    write_stamp(tmp_path, _stamp())
    runner = _fake_git({"ls-remote": GitResult(0, f"{_SHA_VIEJO}\trefs/heads/main", "")})

    check = check_install(tmp_path, run_git=runner)

    assert check.state is CheckState.UP_TO_DATE
    assert check.remote_commit == _SHA_VIEJO


def test_check_install_remoto_avanzado(tmp_path: Path) -> None:
    """SHA distinto => BEHIND (hay commits nuevos)."""
    write_stamp(tmp_path, _stamp())
    runner = _fake_git({"ls-remote": GitResult(0, f"{_SHA_NUEVO}\trefs/heads/main", "")})

    check = check_install(tmp_path, run_git=runner)

    assert check.state is CheckState.BEHIND
    assert check.remote_commit == _SHA_NUEVO


def test_check_install_offline(tmp_path: Path) -> None:
    """Fallo de red en ls-remote => OFFLINE (no se cachea)."""
    write_stamp(tmp_path, _stamp())
    runner = _fake_git({"ls-remote": GitResult(128, "", "could not resolve host")})

    assert check_install(tmp_path, run_git=runner).state is CheckState.OFFLINE


def test_check_install_rechaza_origen_invalido(tmp_path: Path) -> None:
    """Un sello manipulado (flag o esquema raro) no se ejecuta."""
    write_stamp(tmp_path, _stamp(source="--upload-pack=evil"))

    check = check_install(tmp_path, run_git=_fake_git({}))

    assert check.state is CheckState.NO_REMOTE


def test_apply_install_sin_sello_falla(tmp_path: Path) -> None:
    """Sin sello, apply no adivina el origen."""
    result = apply_install(tmp_path, run_git=_fake_git({}))

    assert result.action == "failed"
    assert result.changed is False


def test_apply_install_al_dia_no_clona(tmp_path: Path) -> None:
    """Si el sello ya coincide con el remoto no se clona ni sincroniza."""
    write_stamp(tmp_path, _stamp())
    runner = _fake_git({"ls-remote": GitResult(0, f"{_SHA_VIEJO}\trefs/heads/main", "")})

    result = apply_install(tmp_path, run_git=runner)

    assert result.action == "up_to_date"
    assert result.changed is False


def _preparar_clon(workspace: Path) -> Path:
    """Crea el layout minimo de un clon SWARMIND en ``workspace/repo``."""
    repo = workspace / "repo"
    (repo / "scripts").mkdir(parents=True)
    (repo / "scripts" / "sync_opencode_global.py").write_text("", encoding="utf-8")
    (repo / "pyproject.toml").write_text('[project]\nversion = "11.92"\n', encoding="utf-8")
    return repo


def test_apply_install_clona_sincroniza_y_resella(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Camino feliz: clone -> sync -> nuevo commit/version en el sello."""
    write_stamp(tmp_path, _stamp())
    llamadas: list[list[str]] = []

    def _runner(args, cwd, timeout=60):
        llamadas.append(list(args))
        if args[0] == "ls-remote":
            return GitResult(0, f"{_SHA_NUEVO}\trefs/heads/main", "")
        if args[0] == "clone":
            _preparar_clon(Path(cwd))
            return GitResult(0, "", "")
        if args[0] == "rev-parse":
            return GitResult(0, _SHA_NUEVO, "")
        return GitResult(1, "", "inesperado")

    def _sync_ok(cmd, **kwargs):
        assert kwargs["env"]["OPENCODE_GLOBAL_DIR"] == str(tmp_path)
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr(install_mod.subprocess, "run", _sync_ok)

    result = apply_install(tmp_path, run_git=_runner, python="python")

    assert result.action == "updated"
    assert result.changed is True
    assert result.from_commit == _SHA_VIEJO
    assert result.to_commit == _SHA_NUEVO
    assert any(c[0] == "clone" for c in llamadas)
    nuevo = read_stamp(tmp_path)
    assert nuevo is not None
    assert nuevo.commit == _SHA_NUEVO
    assert nuevo.version == "11.92"


def test_apply_install_clone_fallido(tmp_path: Path) -> None:
    """Si git clone falla, apply degrada a failed sin tocar el sello."""
    write_stamp(tmp_path, _stamp())
    runner = _fake_git({
        "ls-remote": GitResult(0, f"{_SHA_NUEVO}\trefs/heads/main", ""),
        "clone": GitResult(128, "", "fatal: repository not found"),
    })

    result = apply_install(tmp_path, run_git=runner)

    assert result.action == "failed"
    assert read_stamp(tmp_path).commit == _SHA_VIEJO  # type: ignore[union-attr]


def test_install_notice_respeta_cooldown(tmp_path: Path) -> None:
    """Con state reciente no se hace fetch ni se avisa."""
    write_stamp(tmp_path, _stamp())
    state = tmp_path / ".swarmind" / "update_notice.json"
    state.parent.mkdir(parents=True, exist_ok=True)
    state.write_text(json.dumps({"checked_epoch": 9e18}), encoding="utf-8")

    def _runner(args, cwd, timeout=60):
        raise AssertionError("no debe hacer red dentro del cooldown")

    assert install_notice(tmp_path, run_git=_runner) is None


def test_install_notice_avisa_si_hay_commits(tmp_path: Path) -> None:
    """Fuera del cooldown y con remoto avanzado, devuelve el mensaje."""
    write_stamp(tmp_path, _stamp())
    runner = _fake_git({"ls-remote": GitResult(0, f"{_SHA_NUEVO}\trefs/heads/main", "")})

    mensaje = install_notice(tmp_path, cooldown_hours=0, run_git=runner)

    assert mensaje is not None
    assert "update disponible" in mensaje
    assert _SHA_NUEVO[:7] in mensaje
    assert (tmp_path / ".swarmind" / "update_notice.json").is_file()
