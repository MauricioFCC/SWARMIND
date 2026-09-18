"""Tests para feature_flags — flags para trabajo incompleto (ADR-0083).

Frontera (trunk-based/DORA elite): sin flags no hay trunk real; merge !=
release (dark ship). Flags con default seguro (off) y evaluacion por
entorno; sin flag system no hay trunk-based development.
"""

import pytest

from harness.orchestrator.feature_flags import (
    FeatureFlags,
    is_enabled,
)


def test_disabled_by_default() -> None:
    """Flag desconocido/apagado retorna False (default seguro)."""
    flags = FeatureFlags()
    assert flags.is_enabled("nuevo-router") is False


def test_enable_and_check() -> None:
    """Habilitar un flag lo activa solo a el."""
    flags = FeatureFlags({"nuevo-router": True})
    assert flags.is_enabled("nuevo-router") is True
    assert flags.is_enabled("otro") is False


def test_is_enabled_function() -> None:
    """Atajo funcional con flags por defecto (todo off)."""
    assert is_enabled("cualquier-flag") is False


def test_empty_name_raises() -> None:
    """Nombre vacio falla accionable."""
    flags = FeatureFlags()
    with pytest.raises(ValueError, match="WHAT"):
        flags.is_enabled("   ")


def test_from_env_override(monkeypatch) -> None:
    """Variable SWARMIND_FF_<NAME>=1 enciende el flag (override operativo)."""
    monkeypatch.setenv("SWARMIND_FF_MI_FLAG", "1")
    flags = FeatureFlags.from_env()
    assert flags.is_enabled("mi-flag") is True
    assert flags.is_enabled("otro") is False


def test_flags_are_frozen_snapshot() -> None:
    """El snapshot de flags es inmutable."""
    flags = FeatureFlags({"a": True})
    with pytest.raises(AttributeError):
        flags.flags = {}  # type: ignore[misc]
