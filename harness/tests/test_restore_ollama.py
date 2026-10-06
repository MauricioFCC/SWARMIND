"""Tests hermeticos de `scripts/restore_ollama.py` (sin red real).

Cubren idempotencia (no re-descarga), `--dry-run` sin descargas, filtro por
tier, servidor no disponible (exit 2) y validacion de ids contra el SSOT FLEET.
"""

from __future__ import annotations

import argparse
import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest

_SCRIPT = Path(__file__).resolve().parent.parent.parent / "scripts" / "restore_ollama.py"
_spec = importlib.util.spec_from_file_location("swarmind_restore_ollama", _SCRIPT)
assert _spec is not None and _spec.loader is not None
ro = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ro)


def _ns(**overrides) -> argparse.Namespace:
    """Construye un Namespace de argumentos con valores por defecto.

    Args:
        **overrides: Atributos a sobrescribir.

    Returns:
        Namespace listo para `ro.run`.
    """
    defaults = {
        "dry_run": False, "tier": None, "check": False, "skip_caps": False,
        "timeout": 5.0, "pull_timeout": 3600.0,
    }
    defaults.update(overrides)
    return argparse.Namespace(**defaults)


def test_present_models_are_not_pulled(monkeypatch) -> None:
    """Idempotencia: si todos los modelos ya estan, NO se llama pull."""
    installed = {entry.id for entry in ro.load_fleet()}
    pulled: list[str] = []
    monkeypatch.setattr(ro, "is_server_available", lambda timeout: True)
    monkeypatch.setattr(ro, "detect_installed", lambda timeout: (installed, True))
    monkeypatch.setattr(ro, "apply_limits", lambda: (True, "ok"))
    monkeypatch.setattr(ro, "pull_model", lambda entry, use_cli, timeout: pulled.append(entry.id) or True)

    code = ro.run(_ns())

    assert code == ro.EXIT_OK
    assert pulled == []


def test_dry_run_never_downloads_nor_touches_caps(monkeypatch) -> None:
    """`--dry-run` no descarga y no aplica topes (aunque falten modelos)."""
    pulled: list[str] = []
    caps_touched = False

    def fake_caps() -> tuple[bool, str]:
        nonlocal caps_touched
        caps_touched = True
        return True, "ok"

    monkeypatch.setattr(ro, "apply_limits", fake_caps)
    monkeypatch.setattr(ro, "is_server_available", lambda timeout: False)
    monkeypatch.setattr(ro, "pull_model", lambda entry, use_cli, timeout: pulled.append(entry.id) or True)

    code = ro.run(_ns(dry_run=True))

    assert code == ro.EXIT_OK
    assert pulled == []
    assert caps_touched is False


def test_tier_filter_selects_only_that_tier() -> None:
    """`--tier fast` devuelve unicamente entradas del tier fast."""
    selected = ro.select_fleet(ro.load_fleet(), "fast")

    assert len(selected) == 1
    assert all(entry.tier == "fast" for entry in selected)


def test_unknown_tier_is_rejected(monkeypatch) -> None:
    """Un tier inexistente falla con exit 1 y no descarga nada."""
    monkeypatch.setattr(ro, "load_fleet", lambda: (SimpleNamespace(id="known:latest", tier="fast", matches=()),))

    code = ro.run(_ns(tier="nope"))

    assert code == ro.EXIT_FAIL


def test_server_unavailable_returns_exit_2(monkeypatch, caplog) -> None:
    """Servidor no disponible -> exit 2 con mensaje accionable."""
    monkeypatch.setattr(ro, "apply_limits", lambda: (True, "ok"))
    monkeypatch.setattr(ro, "is_server_available", lambda timeout: False)

    with caplog.at_level("ERROR"):
        code = ro.run(_ns())

    assert code == ro.EXIT_UNAVAILABLE
    assert any("Servidor Ollama no responde" in record.message for record in caplog.records)


def test_unknown_id_is_rejected_against_fleet(monkeypatch) -> None:
    """`pull_model` rechaza ids que no pertenecen a FLEET."""
    monkeypatch.setattr(ro, "load_fleet", lambda: (SimpleNamespace(id="known:latest", tier="fast", matches=()),))

    assert ro.is_fleet_id("known:latest") is True
    with pytest.raises(ValueError):
        ro.pull_model(SimpleNamespace(id="evil:latest", matches=()), True, 5.0)


def test_run_only_pulls_missing_models(monkeypatch) -> None:
    """Descarga exactamente los ausentes; el presente se omite."""
    fleet = ro.load_fleet()
    present = fleet[0]
    pulled: list[str] = []
    monkeypatch.setattr(ro, "is_server_available", lambda timeout: True)
    monkeypatch.setattr(ro, "detect_installed", lambda timeout: ({present.id}, True))
    monkeypatch.setattr(ro, "apply_limits", lambda: (True, "ok"))
    monkeypatch.setattr(ro, "pull_model", lambda entry, use_cli, timeout: pulled.append(entry.id) or True)

    code = ro.run(_ns())

    expected = [entry.id for entry in fleet if entry.id != present.id]
    assert code == ro.EXIT_OK
    assert pulled == expected


def test_pull_uses_dedicated_pull_timeout(monkeypatch) -> None:
    """Las descargas usan `--pull-timeout`, no el timeout corto de red."""
    fleet = ro.load_fleet()
    seen: list[float] = []
    monkeypatch.setattr(ro, "is_server_available", lambda timeout: True)
    monkeypatch.setattr(ro, "detect_installed", lambda timeout: (set(), True))
    monkeypatch.setattr(ro, "apply_limits", lambda: (True, "ok"))
    monkeypatch.setattr(
        ro, "pull_model", lambda entry, use_cli, timeout: seen.append(timeout) or True
    )

    code = ro.run(_ns(pull_timeout=7200.0))

    assert code == ro.EXIT_OK
    assert seen == [7200.0] * len(fleet)
