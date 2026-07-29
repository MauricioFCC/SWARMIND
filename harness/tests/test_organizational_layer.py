# -*- coding: utf-8 -*-
"""
Tests para organizational_layer.py — Capa organizacional IMACS.

Cubre: asignación de roles Belbin, matriz RACI, validación de restricciones,
presets organizacionales, serialización, ciclos de vida completo y
especificaciones TeamSpec.

Basado en arXiv:2607.25446 (IMACS) — Decoupling Who, How, and Which.
"""
from __future__ import annotations

import json
import pytest

from harness.orchestrator.organizational_layer import (
    BelbinRole,
    CollaborationProtocol,
    MintzbergCoordination,
    OrganizationalLayer,
    RACIMatrix,
    TeamSpec,
)


# ===================================================================
# Tests unitarios — BelbinRole
# ===================================================================


class TestBelbinRole:
    """Tests para el enum BelbinRole y su factory ``from_str``."""

    def test_from_str_valid(self):
        """from_str debe convertir strings válidos case-insensitive."""
        assert BelbinRole.from_str("shaper") is BelbinRole.SHAPER
        assert BelbinRole.from_str("SHAPER") is BelbinRole.SHAPER
        assert BelbinRole.from_str("implementer") is BelbinRole.IMPLEMENTER
        assert BelbinRole.from_str("COMPLETER") is BelbinRole.COMPLETER
        assert BelbinRole.from_str("Teamworker") is BelbinRole.TEAMWORKER
        assert BelbinRole.from_str("specialist") is BelbinRole.SPECIALIST

    def test_from_str_invalid(self):
        """from_str debe lanzar ValueError para strings inválidos."""
        with pytest.raises(ValueError, match="Rol Belbin desconocido"):
            BelbinRole.from_str("captain")

    def test_all_roles_have_unique_values(self):
        """Todos los roles deben tener valores únicos."""
        values = [r.value for r in BelbinRole]
        assert len(values) == len(set(values)), "Valores de rol duplicados"


# ===================================================================
# Tests unitarios — RACIMatrix
# ===================================================================


class TestRACIMatrix:
    """Tests para la matriz RACI y sus validaciones."""

    def test_valid_raci_passes_validation(self):
        """RACI válido no debe lanzar excepción."""
        raci = RACIMatrix(
            responsible="builder",
            accountable="coordinator",
            consulted=["scientist"],
            informed=["guardian"],
        )
        raci.validate()  # no raise

    def test_raci_single_accountable_enforced(self):
        """Solo se permite un accountable (single-owner constraint)."""
        raci = RACIMatrix(
            responsible="builder",
            accountable="coordinator,manager",
        )
        with pytest.raises(ValueError, match="solo se permite un Accountable"):
            raci.validate()

    def test_raci_accountable_requires_responsible(self):
        """Accountable sin Responsible debe lanzar error."""
        raci = RACIMatrix(accountable="coordinator")
        with pytest.raises(ValueError, match="debe haber Responsible"):
            raci.validate()

    def test_raci_no_duplicates_in_consulted(self):
        """Consulted no debe tener duplicados."""
        raci = RACIMatrix(
            responsible="builder",
            accountable="coordinator",
            consulted=["scientist", "scientist"],
        )
        with pytest.raises(ValueError, match="consulted no puede tener"):
            raci.validate()

    def test_raci_no_duplicates_in_informed(self):
        """Informed no debe tener duplicados."""
        raci = RACIMatrix(
            responsible="builder",
            accountable="coordinator",
            informed=["guardian", "guardian"],
        )
        with pytest.raises(ValueError, match="informed no puede tener"):
            raci.validate()

    def test_raci_responsible_not_in_consulted(self):
        """Responsible no debe estar en consulted."""
        raci = RACIMatrix(
            responsible="builder",
            accountable="coordinator",
            consulted=["builder"],
        )
        with pytest.raises(
            ValueError, match="no debe estar en consulted"
        ):
            raci.validate()

    def test_raci_to_dict_roundtrip(self):
        """to_dict y from_dict deben ser inversos."""
        original = RACIMatrix(
            responsible="builder",
            accountable="coordinator",
            consulted=["scientist"],
            informed=["guardian", "evolver"],
        )
        data = original.to_dict()
        restored = RACIMatrix.from_dict(data)
        assert restored.responsible == original.responsible
        assert restored.accountable == original.accountable
        assert restored.consulted == original.consulted
        assert restored.informed == original.informed


# ===================================================================
# Tests — OrganizationalLayer (WHO / HOW / RACI)
# ===================================================================


class TestOrganizationalLayerRoles:
    """Tests de asignación de roles Belbin en la capa organizacional."""

    def setup_method(self):
        self.layer = OrganizationalLayer()

    def test_assign_and_get_role(self):
        """Asignar y recuperar rol Belbin."""
        self.layer.assign_role("agent-x", BelbinRole.SHAPER)
        assert self.layer.get_role("agent-x") is BelbinRole.SHAPER

    def test_get_role_nonexistent_returns_none(self):
        """get_role debe retornar None para agente sin rol."""
        assert self.layer.get_role("ghost") is None

    def test_assign_role_invalid_type_raises(self):
        """assign_role debe rechazar tipos no BelbinRole."""
        with pytest.raises(TypeError, match="debe ser BelbinRole"):
            self.layer.assign_role("agent-x", "shaper")  # type: ignore[arg-type]

    def test_remove_role_existing(self):
        """remove_role debe eliminar y retornar True."""
        self.layer.assign_role("agent-x", BelbinRole.IMPLEMENTER)
        assert self.layer.remove_role("agent-x") is True
        assert self.layer.get_role("agent-x") is None

    def test_remove_role_nonexistent(self):
        """remove_role debe retornar False para agente inexistente."""
        assert self.layer.remove_role("nobody") is False

    def test_has_role_exact_match(self):
        """has_role debe verificar rol exacto."""
        self.layer.assign_role("agent-x", BelbinRole.SPECIALIST)
        assert self.layer.has_role("agent-x", BelbinRole.SPECIALIST) is True
        assert self.layer.has_role("agent-x", BelbinRole.SHAPER) is False

    def test_list_roles_returns_snapshot(self):
        """list_roles debe retornar copia del estado actual."""
        self.layer.assign_role("a", BelbinRole.SHAPER)
        self.layer.assign_role("b", BelbinRole.IMPLEMENTER)
        roles = self.layer.list_roles()
        assert roles == {"a": BelbinRole.SHAPER, "b": BelbinRole.IMPLEMENTER}
        # La modificación externa no afecta al layer
        roles["c"] = BelbinRole.COMPLETER
        assert "c" not in self.layer.list_roles()

    def test_find_agents_by_role(self):
        """find_agents_by_role debe listar agentes con ese rol."""
        self.layer.assign_role("alpha", BelbinRole.SHAPER)
        self.layer.assign_role("beta", BelbinRole.IMPLEMENTER)
        self.layer.assign_role("gamma", BelbinRole.SHAPER)
        shapers = self.layer.find_agents_by_role(BelbinRole.SHAPER)
        assert sorted(shapers) == ["alpha", "gamma"]


class TestOrganizationalLayerCoordination:
    """Tests del mecanismo de coordinación (HOW)."""

    def setup_method(self):
        self.layer = OrganizationalLayer()

    def test_default_coordination_is_mutual_adjustment(self):
        """La coordinación por defecto debe ser MUTUAL_ADJUSTMENT."""
        assert self.layer.coordination is MintzbergCoordination.MUTUAL_ADJUSTMENT

    def test_set_coordination(self):
        """Cambiar el mecanismo de coordinación."""
        self.layer.coordination = MintzbergCoordination.DIRECT_SUPERVISION
        assert self.layer.coordination is MintzbergCoordination.DIRECT_SUPERVISION

    def test_set_coordination_invalid_type(self):
        """Asignar coordinación con tipo inválido debe lanzar TypeError."""
        with pytest.raises(TypeError, match="debe ser MintzbergCoordination"):
            self.layer.coordination = "adhoc"  # type: ignore[assignment]


class TestOrganizationalLayerRACI:
    """Tests de la matriz RACI en la capa organizacional."""

    def setup_method(self):
        self.layer = OrganizationalLayer()

    def test_create_raci_valid(self):
        """Crear RACI válido debe registrarlo."""
        raci = self.layer.create_raci(
            task="build-api",
            responsible="builder",
            accountable="coordinator",
            consulted=["scientist"],
            informed=["guardian"],
        )
        assert self.layer.get_raci("build-api") is raci
        assert raci.responsible == "builder"

    def test_get_raci_nonexistent_returns_none(self):
        """get_raci debe retornar None para tarea sin RACI."""
        assert self.layer.get_raci("ghost-task") is None

    def test_create_raci_invalid_raises(self):
        """Crear RACI inválido debe lanzar ValueError."""
        with pytest.raises(ValueError, match="solo se permite un Accountable"):
            self.layer.create_raci(
                task="bad",
                responsible="builder",
                accountable="coord,lead",
            )

    def test_remove_raci_existing(self):
        """remove_raci debe eliminar y retornar True."""
        self.layer.create_raci("t1", "a", "b")
        assert self.layer.remove_raci("t1") is True
        assert self.layer.get_raci("t1") is None

    def test_remove_raci_nonexistent(self):
        """remove_raci debe retornar False para tarea sin RACI."""
        assert self.layer.remove_raci("phantom") is False

    def test_list_raci_returns_snapshot(self):
        """list_raci debe retornar copia del estado."""
        self.layer.create_raci("t1", "a", "b")
        self.layer.create_raci("t2", "c", "d")
        assert len(self.layer.list_raci()) == 2

    def test_get_accountable_for_task(self):
        """get_accountable_for_task debe retornar el accountable."""
        self.layer.create_raci("t1", "builder", "coordinator")
        assert self.layer.get_accountable_for_task("t1") == "coordinator"

    def test_get_accountable_for_nonexistent_task(self):
        """get_accountable_for_task debe retornar None."""
        assert self.layer.get_accountable_for_task("void") is None

    def test_get_responsible_for_task(self):
        """get_responsible_for_task debe retornar el responsible."""
        self.layer.create_raci("t1", "builder", "coordinator")
        assert self.layer.get_responsible_for_task("t1") == "builder"


class TestOrganizationalLayerModelBinding:
    """Tests de model binding (asignación agente → modelo LLM)."""

    def setup_method(self):
        self.layer = OrganizationalLayer()

    def test_bind_and_get_model(self):
        """bind_model y get_model deben ser consistentes."""
        self.layer.bind_model("builder", "deepseek-v4-flash")
        assert self.layer.get_model("builder") == "deepseek-v4-flash"

    def test_get_model_unbound_returns_none(self):
        """get_model para agente sin binding debe retornar None."""
        assert self.layer.get_model("ghost") is None


# ===================================================================
# Tests — Presets organizacionales
# ===================================================================


class TestOrganizationalLayerPresets:
    """Tests de los tres presets organizacionales IMACS."""

    def test_belbin_preset_has_five_roles(self):
        """El preset belbin debe tener 5 roles asignados."""
        layer = OrganizationalLayer.from_preset_belbin()
        assert layer.agent_count == 5
        assert layer.get_role("coordinator") is BelbinRole.SHAPER
        assert layer.get_role("builder") is BelbinRole.IMPLEMENTER
        assert layer.get_role("guardian") is BelbinRole.COMPLETER
        assert layer.get_role("scientist") is BelbinRole.SPECIALIST
        assert layer.get_role("evolver") is BelbinRole.TEAMWORKER

    def test_belbin_preset_coordination(self):
        """El preset belbin debe usar MUTUAL_ADJUSTMENT."""
        layer = OrganizationalLayer.from_preset_belbin()
        assert layer.coordination is MintzbergCoordination.MUTUAL_ADJUSTMENT

    def test_adhocracy_preset(self):
        """El preset adhocracy debe tener 3 roles y supervisión directa."""
        layer = OrganizationalLayer.from_preset_adhocracy()
        assert layer.agent_count == 3
        assert layer.get_role("lead") is BelbinRole.SHAPER
        assert layer.get_role("creator") is BelbinRole.SPECIALIST
        assert layer.get_role("reviewer") is BelbinRole.COMPLETER
        assert layer.coordination is MintzbergCoordination.DIRECT_SUPERVISION

    def test_three_departments_preset(self):
        """El preset three-departments debe tener 4 roles jerárquicos."""
        layer = OrganizationalLayer.from_preset_three_departments()
        assert layer.agent_count == 4
        assert layer.get_role("chancellor") is BelbinRole.SHAPER
        assert layer.get_role("secretary") is BelbinRole.IMPLEMENTER
        assert layer.get_role("censor") is BelbinRole.COMPLETER
        assert layer.get_role("advisor") is BelbinRole.SPECIALIST
        assert layer.coordination is MintzbergCoordination.DIRECT_SUPERVISION

    def test_presets_team_name(self):
        """Cada preset debe tener su team_name correcto."""
        assert OrganizationalLayer.from_preset_belbin().team_name == "belbin"
        assert (
            OrganizationalLayer.from_preset_adhocracy().team_name == "adhocracy"
        )
        assert (
            OrganizationalLayer.from_preset_three_departments().team_name
            == "three-departments"
        )


# ===================================================================
# Tests — TeamSpec (especificación completa)
# ===================================================================


class TestTeamSpec:
    """Tests de TeamSpec — especificación completa de organización."""

    def test_valid_spec_passes_validation(self):
        """TeamSpec bien formado no debe tener errores."""
        spec = TeamSpec(
            name="test-team",
            roles={
                "builder": BelbinRole.IMPLEMENTER,
                "coordinator": BelbinRole.SHAPER,
            },
            coordination=MintzbergCoordination.STANDARD_PROCESSES,
            model_binding={
                "builder": "deepseek-v4-flash",
                "coordinator": "deepseek-v4-pro",
            },
            raci_assignments={
                "build-api": RACIMatrix(
                    responsible="builder",
                    accountable="coordinator",
                ),
            },
        )
        assert spec.validate() == []

    def test_spec_missing_model_binding(self):
        """TeamSpec con agente sin modelo entre bindings definidos debe reportar error."""
        spec = TeamSpec(
            name="incomplete",
            roles={
                "builder": BelbinRole.IMPLEMENTER,
                "coordinator": BelbinRole.SHAPER,
            },
            model_binding={"coordinator": "deepseek-v4-pro"},  # builder sin modelo
        )
        errors = spec.validate()
        assert any("no tiene binding" in e for e in errors)

    def test_spec_invalid_raci_reported(self):
        """Errores de validación RACI deben aparecer en validate()."""
        spec = TeamSpec(
            name="bad-raci",
            roles={
                "builder": BelbinRole.IMPLEMENTER,
                "coordinator": BelbinRole.SHAPER,
            },
            raci_assignments={
                "t1": RACIMatrix(
                    responsible="builder",
                    accountable="coordinator,manager",  # inválido
                ),
            },
        )
        errors = spec.validate()
        assert any("solo se permite un Accountable" in e for e in errors)

    def test_spec_raci_refers_undefined_agent(self):
        """RACI que refiere agente no definido en roles debe fallar."""
        spec = TeamSpec(
            name="ref-error",
            roles={"builder": BelbinRole.IMPLEMENTER},
            raci_assignments={
                "t1": RACIMatrix(
                    responsible="builder",
                    accountable="ghost",  # no está en roles
                ),
            },
        )
        errors = spec.validate()
        assert any("no está definido en roles" in e for e in errors)


# ===================================================================
# Tests — load_spec / to_spec / serialización
# ===================================================================


class TestOrganizationalLayerSerialization:
    """Tests de serialización y carga de configuraciones."""

    def setup_method(self):
        self.layer = OrganizationalLayer()

    def test_load_spec_roundtrip(self):
        """Cargar y exportar TeamSpec debe ser idempotente."""
        spec = TeamSpec(
            name="roundtrip",
            roles={
                "builder": BelbinRole.IMPLEMENTER,
                "coordinator": BelbinRole.SHAPER,
            },
            coordination=MintzbergCoordination.DIRECT_SUPERVISION,
            model_binding={
                "builder": "deepseek-v4-flash",
                "coordinator": "deepseek-v4-pro",
            },
            raci_assignments={
                "plan": RACIMatrix(
                    responsible="builder",
                    accountable="coordinator",
                    consulted=["scientist"],
                ),
            },
        )
        self.layer.load_spec(spec)
        exported = self.layer.to_spec()
        assert exported.name == "roundtrip"
        assert exported.roles == spec.roles
        assert exported.coordination == spec.coordination
        assert exported.model_binding == spec.model_binding
        assert exported.raci_assignments["plan"].responsible == "builder"
        assert (
            exported.raci_assignments["plan"].accountable == "coordinator"
        )
        assert exported.raci_assignments["plan"].consulted == ["scientist"]

    def test_load_invalid_spec_raises(self):
        """Cargar un TeamSpec inválido debe lanzar ValueError."""
        spec = TeamSpec(
            name="bad",
            roles={"builder": BelbinRole.IMPLEMENTER},
            raci_assignments={
                "t1": RACIMatrix(
                    responsible="builder",
                    accountable="coordinator,lead",
                ),
            },
        )
        with pytest.raises(ValueError, match="TeamSpec inválido"):
            self.layer.load_spec(spec)

    def test_to_dict_structure(self):
        """to_dict debe contener todas las claves esperadas."""
        self.layer.assign_role("builder", BelbinRole.IMPLEMENTER)
        self.layer.coordination = MintzbergCoordination.DIRECT_SUPERVISION
        self.layer.create_raci("t1", "builder", "coordinator")
        data = self.layer.to_dict()
        assert "team_name" in data
        assert "roles" in data
        assert "coordination" in data
        assert "model_binding" in data
        assert "raci" in data
        assert data["roles"]["builder"] == "implementer"
        assert data["coordination"] == "direct_supervision"

    def test_to_json_roundtrip(self):
        """to_json debe producir JSON válido y recuperable."""
        self.layer.assign_role("builder", BelbinRole.IMPLEMENTER)
        self.layer.create_raci("t1", "builder", "coordinator")
        json_str = self.layer.to_json()
        parsed = json.loads(json_str)
        assert parsed["roles"]["builder"] == "implementer"
        assert parsed["raci"]["t1"]["responsible"] == "builder"

    def test_clear_resets_state(self):
        """clear debe limpiar toda la configuración."""
        self.layer.assign_role("builder", BelbinRole.IMPLEMENTER)
        self.layer.create_raci("t1", "builder", "coordinator")
        self.layer.coordination = MintzbergCoordination.DIRECT_SUPERVISION
        self.layer.clear()
        assert self.layer.agent_count == 0
        assert self.layer.list_raci() == {}
        assert self.layer.coordination is MintzbergCoordination.MUTUAL_ADJUSTMENT
        assert self.layer.team_name == "default"


# ===================================================================
# Tests — Ciclo de vida completo (integración)
# ===================================================================


class TestOrganizationalLayerLifecycle:
    """Tests de integración: ciclo de vida completo de la capa."""

    def test_full_workflow(self):
        """Flujo completo: preset → asignaciones → RACI → exportar."""
        # 1. Crear desde preset belbin
        layer = OrganizationalLayer.from_preset_belbin()
        assert layer.agent_count == 5

        # 2. Asignar modelos
        layer.bind_model("coordinator", "deepseek-v4-pro")
        layer.bind_model("builder", "deepseek-v4-flash")
        layer.bind_model("scientist", "qwen3.7-plus")

        # 3. Crear RACI para tareas
        layer.create_raci(
            "implement-api",
            responsible="builder",
            accountable="coordinator",
            consulted=["scientist"],
            informed=["guardian"],
        )
        layer.create_raci(
            "review-code",
            responsible="guardian",
            accountable="coordinator",
        )

        # 4. Verificar consultas
        assert layer.get_accountable_for_task("implement-api") == "coordinator"
        assert layer.get_responsible_for_task("review-code") == "guardian"
        assert layer.get_accountable_for_task("void") is None

        # 5. Cambiar coordinación
        layer.coordination = MintzbergCoordination.STANDARD_PROCESSES
        assert layer.coordination is MintzbergCoordination.STANDARD_PROCESSES

        # 6. Exportar a spec y verificar
        spec = layer.to_spec()
        assert spec.name == "belbin"
        assert len(spec.raci_assignments) == 2
        assert spec.coordination is MintzbergCoordination.STANDARD_PROCESSES

        # 7. Serializar a JSON
        json_str = layer.to_json()
        parsed = json.loads(json_str)
        assert parsed["team_name"] == "belbin"
        assert len(parsed["raci"]) == 2

        # 8. Limpiar
        layer.clear()
        assert layer.agent_count == 0
        assert layer.team_name == "default"

    def test_preset_switch(self):
        """Cambiar de preset organizacional debe ser limpio."""
        layer = OrganizationalLayer.from_preset_belbin()
        assert layer.team_name == "belbin"
        assert layer.agent_count == 5

        # Cambiar a adhocracy (crear nueva instancia)
        layer2 = OrganizationalLayer.from_preset_adhocracy()
        assert layer2.team_name == "adhocracy"
        assert layer2.agent_count == 3
        assert layer2.get_role("lead") is BelbinRole.SHAPER
        assert layer2.get_role("creator") is BelbinRole.SPECIALIST

    def test_repr_output(self):
        """__repr__ debe mostrar información relevante."""
        layer = OrganizationalLayer.from_preset_belbin()
        rep = repr(layer)
        assert "belbin" in rep
        assert "5" in rep
        assert "mutual_adjustment" in rep


# ===================================================================
# Tests — ColaborationProtocol (enum WHICH)
# ===================================================================


class TestCollaborationProtocol:
    """Tests del enum CollaborationProtocol (capa WHICH)."""

    def test_all_protocols_defined(self):
        """Deben existir los 6 protocolos base de IMACS."""
        expected = {
            "VOTING",
            "DEBATE",
            "MOA",
            "BLENDER",
            "REFLEXION",
            "PLAN_EXECUTE",
        }
        actual = {p.name for p in CollaborationProtocol}
        assert actual == expected

    def test_get_active_protocol_default(self):
        """get_active_protocol debe retornar VOTING por defecto."""
        layer = OrganizationalLayer()
        assert layer.get_active_protocol() is CollaborationProtocol.VOTING

    def test_values_are_strings(self):
        """Todos los valores del enum deben ser strings."""
        for p in CollaborationProtocol:
            assert isinstance(p.value, str)
