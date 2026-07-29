"""
Tests para GovernanceGuard — Constraint Pinning contra Governance Decay.

arXiv:2606.22528: Verifica que constraints de seguridad se mantengan
anclados fuera de la compaction lossy de contexto.
"""
from __future__ import annotations

import pytest

from harness.orchestrator.governance_guard import (
    DEFAULT_CONSTRAINTS,
    GovernanceGuard,
    PinnedConstraint,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def guard() -> GovernanceGuard:
    """Fixture: GovernanceGuard con constraints por defecto."""
    return GovernanceGuard()


@pytest.fixture
def empty_guard() -> GovernanceGuard:
    """Fixture: GovernanceGuard sin constraints."""
    return GovernanceGuard(constraints=[])


# ---------------------------------------------------------------------------
# Tests del core: listado y constraints por defecto
# ---------------------------------------------------------------------------


class TestConstraintPinning:
    """Verifica que los constraints se mantengan anclados y accesibles."""

    def test_default_constraints_loaded(self, guard: GovernanceGuard) -> None:
        """
        Los 5 constraints por defecto deben estar cargados.

        Verifica que el guardia inicialice correctamente con todos los
        DEFAULT_CONSTRAINTS definidos en el modulo.
        """
        pinned = guard.get_pinned()
        assert len(pinned) == len(DEFAULT_CONSTRAINTS)
        names = {c.name for c in pinned}
        expected = {c["name"] for c in DEFAULT_CONSTRAINTS}
        assert names == expected

    def test_get_pinned_returns_copy(self, guard: GovernanceGuard) -> None:
        """
        get_pinned() debe retornar una copia, no la lista interna.

        Verifica que mutaciones externas no afecten el estado interno.
        """
        pinned = guard.get_pinned()
        pinned.clear()
        assert len(guard.get_pinned()) == len(DEFAULT_CONSTRAINTS)

    def test_get_enabled_filters_disabled(self, guard: GovernanceGuard) -> None:
        """
        get_enabled() solo debe retornar constraints habilitados.

        Verifica que al deshabilitar un constraint, este no aparezca
        en la lista de habilitados.
        """
        guard.disable_constraint("no_eval_exec")
        enabled = guard.get_enabled()
        assert all(c.enabled for c in enabled)
        assert "no_eval_exec" not in {c.name for c in enabled}


# ---------------------------------------------------------------------------
# Tests de CRUD de constraints
# ---------------------------------------------------------------------------


class TestConstraintManagement:
    """CRUD de constraints: agregar, obtener, eliminar, habilitar/deshabilitar."""

    def test_add_and_get_constraint(self, guard: GovernanceGuard) -> None:
        """
        Agregar un nuevo constraint y recuperarlo por nombre.

        Verifica que add_constraint() almacene correctamente y que
        get_constraint() lo retorne con todos sus atributos.
        """
        guard.add_constraint(
            name="no_unsafe_subprocess",
            rule="No usar shell=True en subprocess",
            severity="critical",
        )
        c = guard.get_constraint("no_unsafe_subprocess")
        assert c is not None
        assert c.rule == "No usar shell=True en subprocess"
        assert c.severity == "critical"
        assert c.enabled is True

    def test_add_duplicate_raises(self, guard: GovernanceGuard) -> None:
        """
        Agregar un constraint con nombre duplicado debe lanzar ValueError.

        Verifica la unicidad de nombres de constraint.
        """
        with pytest.raises(ValueError, match="ya existe"):
            guard.add_constraint(name="no_except_pass", rule="Duplicado")

    def test_remove_constraint(self, guard: GovernanceGuard) -> None:
        """
        Eliminar un constraint existente.

        Verifica que remove_constraint() elimine correctamente y que
        get_constraint() retorne None despues.
        """
        guard.remove_constraint("docstrings_es")
        assert guard.get_constraint("docstrings_es") is None
        assert len(guard.get_pinned()) == len(DEFAULT_CONSTRAINTS) - 1

    def test_remove_nonexistent_raises(self, guard: GovernanceGuard) -> None:
        """
        Eliminar un constraint inexistente debe lanzar ValueError.
        """
        with pytest.raises(ValueError, match="no encontrado"):
            guard.remove_constraint("nonexistent")

    def test_enable_disable_toggle(self, guard: GovernanceGuard) -> None:
        """
        Habilitar y deshabilitar un constraint debe alternar su estado.

        Verifica que enable_constraint() y disable_constraint()
        modifiquen correctamente el flag enabled.
        """
        guard.disable_constraint("no_except_pass")
        c = guard.get_constraint("no_except_pass")
        assert c is not None and c.enabled is False

        guard.enable_constraint("no_except_pass")
        c = guard.get_constraint("no_except_pass")
        assert c is not None and c.enabled is True

    def test_enable_nonexistent_raises(self, guard: GovernanceGuard) -> None:
        """Habilitar constraint inexistente debe lanzar ValueError."""
        with pytest.raises(ValueError, match="no encontrado"):
            guard.enable_constraint("ghost")


# ---------------------------------------------------------------------------
# Tests de verificacion de codigo (check)
# ---------------------------------------------------------------------------


class TestCodeCheck:
    """Verificacion de codigo fuente contra constraints anclados."""

    def test_clean_code_no_violations(self, guard: GovernanceGuard) -> None:
        """
        Codigo limpio no debe generar violaciones.

        Verifica que codigo bien formado pase todos los constraints.
        """
        clean_code = '''
def sumar(a: int, b: int) -> int:
    """Sumar dos numeros enteros."""
    try:
        return a + b
    except TypeError as e:
        logger.error("Error de tipo: %s", e, exc_info=True)
        return 0
'''
        violations = guard.check(clean_code)
        assert len(violations) == 0

    def test_detect_except_pass(self, guard: GovernanceGuard) -> None:
        """
        except:pass debe detectarse como violacion.

        Verifica que el constraint no_except_pass identifique
        correctamente el patron peligroso.
        """
        bad_code = '''
try:
    resultado = 1 / 0
except:
    pass
'''
        violations = guard.check(bad_code)
        assert any("no_except_pass" in v or "except:pass" in v for v in violations)

    def test_detect_eval_usage(self, guard: GovernanceGuard) -> None:
        """
        Uso de eval() debe detectarse como violacion.

        Verifica que el constraint no_eval_exec identifique
        correctamente llamadas a eval().
        """
        bad_code = '''
def ejecutar(expr):
    return eval(expr)
'''
        violations = guard.check(bad_code)
        assert any("no_eval_exec" in v or "eval/exec" in v for v in violations)

    def test_detect_bare_except(self, guard: GovernanceGuard) -> None:
        """
        except sin especificar excepcion debe detectarse.

        Verifica que el constraint error_what_why_where identifique
        except sin tipo de excepcion.
        """
        bad_code = '''
try:
    archivo = open("datos.txt")
except:
    pass
'''
        violations = guard.check(bad_code)
        assert any("error_what_why_where" in v or "WHAT+WHY+WHERE" in v for v in violations)

    def test_disabled_constraint_no_check(self, guard: GovernanceGuard) -> None:
        """
        Constraint deshabilitado no debe generar violaciones.

        Verifica que al deshabilitar un constraint, su regla no se
        aplique durante la verificacion.
        """
        bad_code = '''
try:
    x = 1 / 0
except:
    pass
'''
        guard.disable_constraint("no_except_pass")
        violations = guard.check(bad_code)
        # Pueden haber otras violaciones (bare except), pero no la de except:pass
        names_in_violations = [v for v in violations if "no_except_pass" in v]
        assert len(names_in_violations) == 0


# ---------------------------------------------------------------------------
# Tests de auditoria
# ---------------------------------------------------------------------------


class TestAuditLog:
    """Registro de auditoria de operaciones."""

    def test_audit_tracks_operations(self, guard: GovernanceGuard) -> None:
        """
        Las operaciones CRUD deben quedar registradas en el audit log.
        """
        guard.add_constraint("test_rule", "Test", "low")
        guard.disable_constraint("test_rule")
        guard.enable_constraint("test_rule")
        guard.remove_constraint("test_rule")

        log = guard.get_audit_log()
        actions = [entry.split()[0] for entry in log]
        assert "ADD" in actions
        assert "DISABLE" in actions
        assert "ENABLE" in actions
        assert "REMOVE" in actions

    def test_audit_clears(self, guard: GovernanceGuard) -> None:
        """
        clear_audit_log() debe vaciar el log.
        """
        guard.add_constraint("test_rule", "Test", "low")
        guard.clear_audit_log()
        assert len(guard.get_audit_log()) == 0


# ---------------------------------------------------------------------------
# Tests de integridad y resumen
# ---------------------------------------------------------------------------


class TestGuardIntegrity:
    """Integridad del estado y resumen del GovernanceGuard."""

    def test_summary_structure(self, guard: GovernanceGuard) -> None:
        """
        get_summary() debe retornar un dict con las claves esperadas.
        """
        summary = guard.get_summary()
        assert "total" in summary
        assert "enabled" in summary
        assert "disabled" in summary
        assert "severities" in summary
        assert "audit_entries" in summary

    def test_summary_counts_match(self, empty_guard: GovernanceGuard) -> None:
        """
        Los conteos del resumen deben ser correctos.

        Verifica que total, enabled y disabled reflejen el estado real
        despues de operaciones.
        """
        empty_guard.add_constraint("a", "Rule A", "high")
        empty_guard.add_constraint("b", "Rule B", "critical")
        empty_guard.add_constraint("c", "Rule C", "low")
        empty_guard.disable_constraint("b")

        summary = empty_guard.get_summary()
        assert summary["total"] == 3
        assert summary["enabled"] == 2
        assert summary["disabled"] == 1
        assert summary["severities"]["high"] == 1
        assert summary["severities"]["critical"] == 1
        assert summary["severities"]["low"] == 1

    def test_governance_agent_contract(self, guard: GovernanceGuard) -> None:
        """
        Verificar el contrato minimo con agentes de governance.

        GovernanceGuard debe exponer: get_pinned(), check(code),
        get_summary() como interfaz publica estable.
        """
        assert hasattr(guard, "get_pinned")
        assert hasattr(guard, "check")
        assert hasattr(guard, "get_summary")
        assert callable(guard.get_pinned)
        assert callable(guard.check)
        assert callable(guard.get_summary)
