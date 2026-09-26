"""Tests para QUAD gate + bitemporal cues (ADR-0088).

QUAD (liderazgo): toda asignacion trae Que/Hasta-cuando/Estandar/Impacto
+ 1 solo dueno (3 responsables = nadie). Bitemporal (Utopia/memoria):
cada hecho lleva valid_time (cuando es verdad en el mundo) + tx_time
(cuando entro al sistema) para invalidar sin borrar.
"""

import pytest

from harness.memory_rag.cue_ledger import CueLedger
from harness.validation.task_quad import (
    QUAD_FIELDS,
    check_quad,
)


def _quad_full() -> dict:
    """Task QUAD completa."""
    return {
        "que": "migrar endpoint a v2",
        "hasta_cuando": "2026-09-20 17:00",
        "estandar": "tests verdes + docs + rollback probado",
        "impacto": "cierra SEV-2 de latencia",
        "dueno": "builder",
    }


def test_quad_full_passes() -> None:
    """QUAD completa con 1 dueno pasa."""
    report = check_quad(_quad_full())
    assert report.passed is True
    assert report.missing == ()


def test_quad_missing_fields_listed() -> None:
    """Campos ausentes/vacios se reportan por nombre."""
    report = check_quad({"que": "x"})
    assert report.passed is False
    assert "dueno" in report.missing
    assert "hasta_cuando" in report.missing


def test_quad_multiple_owners_rejected() -> None:
    """3 responsables = nadie: lista o multi-dueno falla."""
    bad = _quad_full()
    bad["dueno"] = ["ana", "luis", "pei"]
    report = check_quad(bad)
    assert report.passed is False
    assert "dueno" in report.missing


def test_quad_dict_owner_rejected() -> None:
    """Dueno dict/set tambien es multi-responsable (no un solo nombre)."""
    for owner in ({"ana": 1}, {"ana", "luis"}):
        bad = _quad_full()
        bad["dueno"] = owner
        assert check_quad(bad).passed is False


def test_quad_fields_documented() -> None:
    """Los 5 campos QUAD estan documentados."""
    assert QUAD_FIELDS == ("que", "hasta_cuando", "estandar", "impacto", "dueno")


def test_quad_non_dict_raises() -> None:
    """No-dict falla accionable."""
    with pytest.raises(TypeError, match="WHAT"):
        check_quad("hazlo")  # type: ignore[arg-type]


def test_bitemporal_register_and_query() -> None:
    """Registro con valid_time/tx_time y query por validez."""
    ledger = CueLedger()
    ledger.register("API v1 activa", source="docs.md",
                    valid_from="2026-01-01", valid_to="2026-06-01")
    ledger.register("API v2 activa", source="docs.md",
                    valid_from="2026-06-01", valid_to=None)
    live = ledger.valid_at("2026-08-01")
    assert [e.cue for e in live] == ["API v2 activa"]
    old = ledger.valid_at("2026-03-01")
    assert [e.cue for e in old] == ["API v1 activa"]


def test_bitemporal_invalid_range_raises() -> None:
    """valid_to anterior a valid_from falla accionable."""
    ledger = CueLedger()
    with pytest.raises(ValueError, match="WHAT"):
        ledger.register("x", source="s", valid_from="2026-06-01", valid_to="2026-01-01")
