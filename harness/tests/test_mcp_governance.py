"""Tests para MCPGovernor — gobernanza de tools MCP (ADR-0049).

Cubre:
- Deny-by-default sin política registrada.
- Enforcement de allowlist por agente.
- Cuota deslizante por minuto.
- Audit trail con parámetros enmascarados (solo claves).
- Integración con MCPManager.execute (permitido y denegado).
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from harness.tools_sandbox.mcp_governance import (
    AuditEntry,
    GovernanceDecision,
    MCPGovernor,
    ToolPolicy,
)


@pytest.fixture
def manager() -> MagicMock:
    """Fixture: MCPManager simulado que devuelve un resultado exitoso."""
    mock = MagicMock()
    mock.execute.return_value = {"success": True, "output": "ok"}
    return mock


@pytest.fixture
def governor(manager: MagicMock) -> MCPGovernor:
    """Fixture: gobernador con política para 'builder' (tool read_file)."""
    gov = MCPGovernor(manager)
    gov.register_policy(
        ToolPolicy(
            agent_id="builder",
            allowed_tools=frozenset({"read_file"}),
            max_calls_per_minute=3,
        )
    )
    return gov


class TestAuthorize:
    """Autorización: deny-by-default, allowlist y cuota."""

    def test_sin_politica_deniega_por_defecto(self, governor: MCPGovernor) -> None:
        decision = governor.authorize("desconocido", "read_file")
        assert isinstance(decision, GovernanceDecision)
        assert decision.allowed is False
        assert "sin política" in decision.reason

    def test_tool_fuera_de_allowlist_deniega(self, governor: MCPGovernor) -> None:
        decision = governor.authorize("builder", "write_file")
        assert decision.allowed is False
        assert "allowlist" in decision.reason

    def test_tool_en_allowlist_autoriza(self, governor: MCPGovernor) -> None:
        decision = governor.authorize("builder", "read_file")
        assert decision.allowed is True

    def test_cuota_excedida_deniega(self, governor: MCPGovernor) -> None:
        for _ in range(3):
            assert governor.authorize("builder", "read_file").allowed is True
        decision = governor.authorize("builder", "read_file")
        assert decision.allowed is False
        assert "Cuota excedida" in decision.reason


class TestExecute:
    """Integración con el manager subyacente."""

    def test_ejecucion_permitida_delega_en_manager(
        self, governor: MCPGovernor, manager: MagicMock
    ) -> None:
        result = governor.execute("builder", "read_file", {"path": "/tmp/a.txt"})
        assert result == {"success": True, "output": "ok"}
        manager.execute.assert_called_once()

    def test_ejecucion_denegada_lanza_permission_error(
        self, governor: MCPGovernor, manager: MagicMock
    ) -> None:
        with pytest.raises(PermissionError, match="denegada"):
            governor.execute("desconocido", "read_file", {})
        manager.execute.assert_not_called()


class TestAuditTrail:
    """Audit trail inmutable con parámetros enmascarados."""

    def test_registra_intentos_permitidos_y_denegados(
        self, governor: MCPGovernor
    ) -> None:
        governor.execute("builder", "read_file", {"path": "/tmp/x"})
        with pytest.raises(PermissionError):
            governor.execute("builder", "drop_table", {"table": "users"})
        trail = governor.get_audit_trail()
        assert len(trail) == 2
        assert all(isinstance(entry, AuditEntry) for entry in trail)
        assert trail[0].allowed is True
        assert trail[1].allowed is False

    def test_parametros_enmascarados_solo_claves(self, governor: MCPGovernor) -> None:
        governor.execute("builder", "read_file", {"path": "/tmp/secreto", "mode": "r"})
        entry = governor.get_audit_trail()[-1]
        assert entry.param_keys == ("mode", "path")
        assert "/tmp/secreto" not in str(entry)

    def test_trail_es_tupla_inmutable(self, governor: MCPGovernor) -> None:
        governor.execute("builder", "read_file", {"path": "/tmp/a"})
        trail = governor.get_audit_trail()
        assert isinstance(trail, tuple)
        assert len(trail) == 1
        with pytest.raises(AttributeError):  # FrozenInstanceError
            trail[0].allowed = False  # type: ignore[misc]


class TestPolicyRegistration:
    """Registro y ciclo de vida de políticas."""

    def test_agent_id_vacio_rechazado(self, manager: MagicMock) -> None:
        gov = MCPGovernor(manager)
        with pytest.raises(ValueError, match="agent_id vacío"):
            gov.register_policy(ToolPolicy(agent_id="", allowed_tools=frozenset()))

    def test_unregister_quita_acceso(self, governor: MCPGovernor) -> None:
        governor.unregister_policy("builder")
        assert governor.authorize("builder", "read_file").allowed is False
