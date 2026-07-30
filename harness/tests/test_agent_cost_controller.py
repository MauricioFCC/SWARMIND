"""
Tests para AgentCostController — Control de costos de agentes.

Verifica deteccion de loops infinitos, limites de presupuesto,
registro de llamadas y reinicio de estados.
"""
from __future__ import annotations

from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from harness.orchestrator.agent_cost_controller import AgentCostController


class TestAgentCostControllerInit:
    """Tests de inicializacion del controlador de costos."""

    def test_default_values(self):
        """Debe inicializar con valores por defecto correctos."""
        ctrl = AgentCostController()
        assert ctrl._max_tokens == 50000
        assert ctrl._max_repeat == 5
        assert ctrl.get_stats() == {}

    def test_custom_values(self):
        """Debe aceptar valores personalizados."""
        ctrl = AgentCostController(max_tokens_per_session=1000, max_repeat_calls=2)
        assert ctrl._max_tokens == 1000
        assert ctrl._max_repeat == 2

    def test_invalid_max_tokens_raises(self):
        """Debe lanzar ValueError si max_tokens_per_session <= 0."""
        with pytest.raises(ValueError, match="max_tokens_per_session debe ser > 0"):
            AgentCostController(max_tokens_per_session=0)
        with pytest.raises(ValueError, match="max_tokens_per_session debe ser > 0"):
            AgentCostController(max_tokens_per_session=-10)

    def test_invalid_max_repeat_raises(self):
        """Debe lanzar ValueError si max_repeat_calls <= 0."""
        with pytest.raises(ValueError, match="max_repeat_calls debe ser > 0"):
            AgentCostController(max_repeat_calls=0)
        with pytest.raises(ValueError, match="max_repeat_calls debe ser > 0"):
            AgentCostController(max_repeat_calls=-1)


class TestAgentCostControllerRegistration:
    """Tests de registro de llamadas de agentes."""

    def setup_method(self):
        self.ctrl = AgentCostController(max_tokens_per_session=1000, max_repeat_calls=2)

    def test_register_first_call_returns_true(self):
        """La primera llamada debe retornar True y crear el registro."""
        result = self.ctrl.register_call("test_agent", "prompt inicial", 50)
        assert result is True
        stats = self.ctrl.get_stats()
        assert "test_agent" in stats
        assert stats["test_agent"]["tokens"] == 50
        assert stats["test_agent"]["calls"] == 1
        assert stats["test_agent"]["loops"] == 0

    def test_register_multiple_agents(self):
        """Debe manejar multiples agentes independientemente."""
        self.ctrl.register_call("agent_a", "prompt a", 30)
        self.ctrl.register_call("agent_b", "prompt b", 40)
        stats = self.ctrl.get_stats()
        assert stats["agent_a"]["tokens"] == 30
        assert stats["agent_b"]["tokens"] == 40
        assert stats["agent_a"]["calls"] == 1
        assert stats["agent_b"]["calls"] == 1

    def test_accumulate_tokens_across_calls(self):
        """Debe acumular tokens correctamente en multiples llamadas."""
        self.ctrl.register_call("agent", "primera", 100)
        self.ctrl.register_call("agent", "segunda", 200)
        stats = self.ctrl.get_stats()
        assert stats["agent"]["tokens"] == 300
        assert stats["agent"]["calls"] == 2


class TestAgentCostControllerLoopDetection:
    """Tests de deteccion de loops infinitos por prompt repetido.

    Nota: El primer llamado con un hash nuevo resetea repeat_count a 0.
    Las repeticiones subsiguientes incrementan repeat_count. Con
    max_repeat_calls=3, se permite hasta 4 llamadas identicas
    (repeat_count=3 no supera max_repeat=3), y la 5ta es bloqueada.
    """

    def setup_method(self):
        self.ctrl = AgentCostController(max_tokens_per_session=10000, max_repeat_calls=3)

    def test_repeat_within_limit_returns_true(self):
        """Repetir el mismo prompt dentro del limite debe retornar True.

        Con max_repeat=3, hasta 4 llamadas identicas estan permitidas
        (repeat_count llega a 3, y 3 > 3 es False).
        """
        for i in range(4):
            result = self.ctrl.register_call("agent", "mismo prompt", 10)
            assert result is True, f"i={i} debio retornar True"
        stats = self.ctrl.get_stats()
        assert stats["agent"]["loops"] == 3

    def test_repeat_exceeds_limit_returns_false(self):
        """Superar el maximo de repeticiones debe retornar False.

        Con max_repeat=3, la 5ta llamada identica es bloqueada
        (repeat_count=4 > max_repeat=3).
        """
        for _ in range(4):
            self.ctrl.register_call("agent", "mismo prompt", 10)
        # 5th call should be blocked (repeat_count=4 > max_repeat=3)
        result = self.ctrl.register_call("agent", "mismo prompt", 10)
        assert result is False

    def test_different_prompt_resets_repeat_counter(self):
        """Un prompt diferente debe reiniciar el contador de repeticiones."""
        self.ctrl.register_call("agent", "prompt A", 10)
        self.ctrl.register_call("agent", "prompt A", 10)
        self.ctrl.register_call("agent", "prompt B", 10)  # diferente, resetea
        stats = self.ctrl.get_stats()
        assert stats["agent"]["loops"] == 0

    def test_repeat_detection_per_agent_independent(self):
        """La deteccion de loops debe ser independiente por agente."""
        for _ in range(4):
            self.ctrl.register_call("agent_a", "repetido", 10)
        # agent_a should be blocked on 5th (repeat_count=4 > max_repeat=3)
        result_a = self.ctrl.register_call("agent_a", "repetido", 10)
        assert result_a is False
        # agent_b with different prompt should work
        result_b = self.ctrl.register_call("agent_b", "original", 10)
        assert result_b is True


class TestAgentCostControllerBudget:
    """Tests de control de presupuesto de tokens."""

    def setup_method(self):
        self.ctrl = AgentCostController(max_tokens_per_session=100, max_repeat_calls=10)

    def test_budget_not_exceeded_returns_true(self):
        """Llamadas dentro del presupuesto deben retornar True."""
        assert self.ctrl.register_call("agent", "prompt", 50) is True
        assert self.ctrl.register_call("agent", "otro", 50) is True

    def test_budget_exceeded_returns_false(self):
        """Superar el presupuesto de tokens debe retornar False."""
        self.ctrl.register_call("agent", "prompt", 60)
        result = self.ctrl.register_call("agent", "otro", 50)
        assert result is False
        stats = self.ctrl.get_stats()
        assert stats["agent"]["tokens"] == 110

    def test_budget_check_is_per_agent(self):
        """El limite de presupuesto debe ser individual por agente."""
        self.ctrl.register_call("agent_a", "grande", 90)
        result_a = self.ctrl.register_call("agent_a", "otro", 20)
        assert result_a is False  # agent_a excedio
        # agent_b debe poder operar normalmente
        result_b = self.ctrl.register_call("agent_b", "chico", 30)
        assert result_b is True
        assert self.ctrl.get_stats()["agent_b"]["tokens"] == 30

    def test_budget_exact_limit_still_allowed(self):
        """Llamada que consume exactamente el presupuesto debe ser aceptada."""
        result = self.ctrl.register_call("agent", "justo", 100)
        assert result is True
        # Siguiente llamada debe exceder
        result2 = self.ctrl.register_call("agent", "extra", 1)
        assert result2 is False


class TestAgentCostControllerReset:
    """Tests de reinicio de registros de costo."""

    def setup_method(self):
        self.ctrl = AgentCostController()

    def test_reset_specific_agent(self):
        """Reset de un agente especifico debe eliminar solo ese registro."""
        self.ctrl.register_call("agent_a", "prompt", 10)
        self.ctrl.register_call("agent_b", "prompt", 20)
        self.ctrl.reset("agent_a")
        stats = self.ctrl.get_stats()
        assert "agent_a" not in stats
        assert "agent_b" in stats

    def test_reset_all_agents(self):
        """Reset sin argumentos debe eliminar todos los registros."""
        self.ctrl.register_call("agent_a", "prompt", 10)
        self.ctrl.register_call("agent_b", "prompt", 20)
        self.ctrl.reset()
        assert self.ctrl.get_stats() == {}

    def test_reset_nonexistent_agent_does_nothing(self):
        """Reset de un agente que no existe no debe lanzar error."""
        self.ctrl.register_call("agent_a", "prompt", 10)
        self.ctrl.reset("nonexistent")
        assert "agent_a" in self.ctrl.get_stats()


class TestAgentCostControllerEdgeCases:
    """Tests de casos borde del controlador de costos."""

    def test_zero_tokens_call(self):
        """Llamada con cero tokens debe ser valida."""
        ctrl = AgentCostController()
        result = ctrl.register_call("agent", "prompt", 0)
        assert result is True
        assert ctrl.get_stats()["agent"]["tokens"] == 0

    def test_empty_prompt_string(self):
        """Prompt vacio debe generar un hash y registrarse correctamente."""
        ctrl = AgentCostController()
        result = ctrl.register_call("agent", "", 10)
        assert result is True

    def test_session_id_tracking(self):
        """El session_id debe almacenarse en el registro."""
        ctrl = AgentCostController()
        ctrl.register_call("agent", "prompt", 10, session_id="session_xyz")
        assert ctrl._records["agent"].session_id == "session_xyz"

    def test_get_stats_after_multiple_agents(self):
        """get_stats debe reflejar el estado completo tras multiples ops."""
        ctrl = AgentCostController()
        ctrl.register_call("ag1", "hello", 30)
        ctrl.register_call("ag2", "world", 40)
        ctrl.register_call("ag1", "again", 20)
        stats = ctrl.get_stats()
        assert stats["ag1"]["tokens"] == 50
        assert stats["ag1"]["calls"] == 2
        assert stats["ag2"]["tokens"] == 40
        assert stats["ag2"]["calls"] == 1
