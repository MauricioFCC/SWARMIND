"""
Tests para Token Budget — TokenPool, TokenBudget, BudgetManager.

Cubre:
  - TokenPool: allocacion, commit, release, reset, can_allocate
  - TokenBudget: inicializacion, pools, gasto, confidence gate, fallos
  - BudgetManager: registro de agentes, redistribucion, sesiones
  - Edge cases: presupuesto cero, pools desconocidos, desactivacion
"""

from __future__ import annotations

from typing import Any, Dict

import pytest

from harness.memory_rag.token_budget import (
    CONFIDENCE_HIGH,
    CONFIDENCE_MEDIUM,
    DEFAULT_AGENT_BUDGET,
    DEFAULT_SESSION_BUDGET,
    MIN_RESERVE_TOKENS,
    POOL_CONVERSATION,
    POOL_RAG,
    POOL_SYSTEM,
    POOL_TOOL_OUTPUT,
    PRIORITY_CRITICAL,
    PRIORITY_HIGH,
    PRIORITY_LOW,
    PRIORITY_NORMAL,
    BudgetManager,
    TokenBudget,
    TokenPool,
)


# ===========================================================================
# Tests: TokenPool
# ===========================================================================


class TestTokenPool:
    """Tests unitarios para TokenPool."""

    def test_inicializacion(self):
        """TokenPool se inicializa con valores correctos."""
        pool = TokenPool(name="test", allocated=1000, priority=PRIORITY_HIGH)
        assert pool.name == "test"
        assert pool.allocated == 1000
        assert pool.used == 0
        assert pool.reserved == 0
        assert pool.priority == PRIORITY_HIGH

    def test_remaining_calculo(self):
        """remaining = allocated - used - reserved."""
        pool = TokenPool(name="test", allocated=1000, used=200, reserved=100)
        assert pool.remaining == 700

    def test_remaining_nunca_negativo(self):
        """remaining nunca retorna negativo."""
        pool = TokenPool(name="test", allocated=100, used=200)
        assert pool.remaining == 0

    def test_usage_pct_calculo(self):
        """usage_pct = used / allocated."""
        pool = TokenPool(name="test", allocated=1000, used=250)
        assert pool.usage_pct == 0.25

    def test_usage_pct_cero_si_no_allocated(self):
        """usage_pct es 0 si allocated es 0."""
        pool = TokenPool(name="test", allocated=0)
        assert pool.usage_pct == 0.0

    def test_can_allocate_true(self):
        """can_allocate retorna True si hay suficientes tokens."""
        pool = TokenPool(name="test", allocated=1000)
        assert pool.can_allocate(500) is True

    def test_can_allocate_false(self):
        """can_allocate retorna False si no hay suficientes."""
        pool = TokenPool(name="test", allocated=100, used=80)
        assert pool.can_allocate(50) is False

    def test_allocate_exitoso(self):
        """allocate reserva tokens y retorna los solicitados."""
        pool = TokenPool(name="test", allocated=1000)
        granted = pool.allocate(300)
        assert granted == 300
        assert pool.reserved == 300

    def test_allocate_limitado(self):
        """allocate retorna lo disponible si se pide mas de lo que hay."""
        pool = TokenPool(name="test", allocated=100, used=80)
        granted = pool.allocate(100)
        assert granted == 20
        assert pool.reserved == 20

    def test_commit_usa_reservados(self):
        """commit mueve tokens de reserved a used."""
        pool = TokenPool(name="test", allocated=1000)
        pool.allocate(300)
        pool.commit(200)
        assert pool.used == 200
        assert pool.reserved == 100

    def test_commit_no_excede_reservados(self):
        """commit no usa mas de lo reservado."""
        pool = TokenPool(name="test", allocated=1000)
        pool.allocate(100)
        pool.commit(999)
        assert pool.used == 100
        assert pool.reserved == 0

    def test_release_devuelve_reservados(self):
        """release libera tokens reservados."""
        pool = TokenPool(name="test", allocated=1000)
        pool.allocate(300)
        pool.release(100)
        assert pool.reserved == 200

    def test_release_no_excede_reservados(self):
        """release no libera mas de lo reservado."""
        pool = TokenPool(name="test", allocated=1000)
        pool.allocate(100)
        pool.release(999)
        assert pool.reserved == 0

    def test_reset_limpia_used_y_reserved(self):
        """reset pone used y reserved a 0."""
        pool = TokenPool(name="test", allocated=1000, used=300, reserved=100)
        pool.reset()
        assert pool.used == 0
        assert pool.reserved == 0

    def test_to_dict_incluye_campos_clave(self):
        """to_dict retorna todos los campos relevantes."""
        pool = TokenPool(name="test", allocated=1000, used=200)
        d = pool.to_dict()
        assert d["name"] == "test"
        assert d["allocated"] == 1000
        assert d["used"] == 200
        assert d["remaining"] == 800
        assert "usage_pct" in d
        assert "priority" in d


# ===========================================================================
# Tests: TokenBudget — inicializacion
# ===========================================================================


class TestTokenBudgetInit:
    """Tests de inicializacion de TokenBudget."""

    def test_inicializacion_valores_default(self):
        """TokenBudget se inicializa con pools y valores por defecto."""
        budget = TokenBudget(agent_id="test_agent")
        assert budget.agent_id == "test_agent"
        assert budget.total_budget == DEFAULT_AGENT_BUDGET
        assert budget.priority == PRIORITY_NORMAL
        assert budget.confidence == 0.0
        assert budget.min_reserve == MIN_RESERVE_TOKENS
        assert budget.disabled is False

    def test_inicializacion_crea_todos_los_pools(self):
        """Se crean todos los pools definidos en ALL_POOLS."""
        budget = TokenBudget(agent_id="test")
        pool_names = {POOL_SYSTEM, POOL_RAG, POOL_TOOL_OUTPUT, POOL_CONVERSATION}
        for name in pool_names:
            assert name in budget.pools, f"Falta pool: {name}"

    def test_pool_allocations_suman_budget(self):
        """La suma de allocated de todos los pools es igual al total_budget."""
        budget = TokenBudget(agent_id="test")
        total_allocated = sum(p.allocated for p in budget.pools.values())
        assert total_allocated == budget.total_budget

    def test_pool_priority_critical_para_system(self):
        """El pool system tiene prioridad CRITICAL."""
        budget = TokenBudget(agent_id="test")
        assert budget.pools[POOL_SYSTEM].priority == PRIORITY_CRITICAL

    def test_pool_priority_low_para_tool_output(self):
        """El pool tool_output tiene prioridad LOW."""
        budget = TokenBudget(agent_id="test")
        assert budget.pools[POOL_TOOL_OUTPUT].priority == PRIORITY_LOW

    def test_custom_budget_y_priority(self):
        """Se pueden especificar budget y priority personalizados."""
        budget = TokenBudget(
            agent_id="custom", total_budget=8000, priority=PRIORITY_CRITICAL
        )
        assert budget.total_budget == 8000
        assert budget.priority == PRIORITY_CRITICAL


# ===========================================================================
# Tests: TokenBudget — propiedades
# ===========================================================================


class TestTokenBudgetProperties:
    """Tests para propiedades de TokenBudget."""

    def test_total_used_suma_pools(self):
        """total_used suma el used de todos los pools."""
        budget = TokenBudget(agent_id="test")
        budget.pools[POOL_SYSTEM].used = 100
        budget.pools[POOL_RAG].used = 200
        assert budget.total_used == 300

    def test_total_remaining_calculo(self):
        """total_remaining = total_budget - total_used."""
        budget = TokenBudget(agent_id="test")
        budget.pools[POOL_SYSTEM].used = 500
        expected = budget.total_budget - 500
        assert budget.total_remaining == expected

    def test_usage_pct_calculo(self):
        """usage_pct = total_used / total_budget."""
        budget = TokenBudget(agent_id="test", total_budget=10000)
        budget.pools[POOL_SYSTEM].used = 2500
        assert budget.usage_pct == 0.25

    def test_usage_pct_cero_si_budget_cero(self):
        """usage_pct es 0 si total_budget es 0."""
        budget = TokenBudget(agent_id="test", total_budget=0)
        assert budget.usage_pct == 0.0


# ===========================================================================
# Tests: TokenBudget — can_spend
# ===========================================================================


class TestTokenBudgetCanSpend:
    """Tests para la propiedad can_spend."""

    def test_puede_gastar_por_defecto(self):
        """Por defecto can_spend es True."""
        budget = TokenBudget(agent_id="test")
        assert budget.can_spend is True

    def test_no_puede_gastar_si_disabled(self):
        """can_spend es False si disabled=True."""
        budget = TokenBudget(agent_id="test", disabled=True)
        assert budget.can_spend is False

    def test_no_puede_gastar_si_confidence_alta(self):
        """can_spend es False si confidence >= CONFIDENCE_HIGH."""
        budget = TokenBudget(agent_id="test")
        budget.confidence = CONFIDENCE_HIGH
        assert budget.can_spend is False

    def test_no_puede_gastar_si_presupuesto_agotado(self):
        """can_spend es False si total_remaining <= min_reserve."""
        budget = TokenBudget(agent_id="test", total_budget=MIN_RESERVE_TOKENS)
        # Sin gastar, remaining = MIN_RESERVE_TOKENS, can_spend debe ser False
        assert budget.can_spend is False

    def test_puede_gastar_con_presupuesto_suficiente(self):
        """can_spend es True si hay presupuesto suficiente y no hay restricciones."""
        budget = TokenBudget(agent_id="test", total_budget=10000)
        assert budget.can_spend is True

    def test_set_confidence_afecta_can_spend(self):
        """set_confidence actualiza can_spend correctamente."""
        budget = TokenBudget(agent_id="test")
        budget.set_confidence(0.95)
        assert budget.confidence == 0.95
        assert budget.can_spend is False

    def test_set_confidence_clamp(self):
        """set_confidence clamp entre 0.0 y 1.0."""
        budget = TokenBudget(agent_id="test")
        budget.set_confidence(-0.5)
        assert budget.confidence == 0.0
        budget.set_confidence(1.5)
        assert budget.confidence == 1.0


# ===========================================================================
# Tests: TokenBudget — request / commit / release
# ===========================================================================


class TestTokenBudgetSpending:
    """Tests para gasto de tokens via request/commit/release."""

    def test_request_exitoso(self):
        """request retorna tokens solicitados del pool."""
        budget = TokenBudget(agent_id="test", total_budget=10000)
        granted = budget.request(POOL_RAG, 500)
        assert granted == 500

    def test_request_pool_inexistente_retorna_cero(self):
        """request a pool desconocido retorna 0 sin error."""
        budget = TokenBudget(agent_id="test")
        granted = budget.request("inexistent_pool", 100)
        assert granted == 0

    def test_request_confidence_gate_bloquea(self):
        """Request con confidence alta bloquea gasto en pools no criticos."""
        budget = TokenBudget(agent_id="test", total_budget=10000)
        budget.set_confidence(0.95)  # > CONFIDENCE_HIGH
        granted = budget.request(POOL_RAG, 500)
        assert granted == 0

    def test_request_confidence_gate_no_bloquea_system(self):
        """Confidence alta NO bloquea pools system/user."""
        budget = TokenBudget(agent_id="test", total_budget=10000)
        budget.set_confidence(0.95)
        granted_system = budget.request(POOL_SYSTEM, 500)
        assert granted_system > 0

    def test_request_reduce_en_medium_confidence(self):
        """Confidence medium reduce la asignacion a 50%."""
        budget = TokenBudget(agent_id="test", total_budget=10000)
        budget.set_confidence(0.75)  # > CONFIDENCE_MEDIUM
        granted = budget.request(POOL_RAG, 1000)
        assert granted == 500  # 1000 * 0.5

    def test_request_redistribuye_desde_pools_baja_prioridad(self):
        """Si un pool se agota, redistribuye desde pools de menor prioridad."""
        budget = TokenBudget(agent_id="test", total_budget=10000)
        # Agotar pool conversation (baja prioridad)
        budget.pools[POOL_CONVERSATION].used = budget.pools[POOL_CONVERSATION].allocated
        # Pedir mas de RAG del que tiene
        rag_allocated = budget.pools[POOL_RAG].allocated
        granted = budget.request(POOL_RAG, rag_allocated + 500)
        # Deberia obtener al menos lo asignado originalmente + algo redistribuido
        assert granted >= rag_allocated

    def test_commit_libera_y_marca_uso(self):
        """commit marca tokens como usados."""
        budget = TokenBudget(agent_id="test", total_budget=10000)
        granted = budget.request(POOL_RAG, 500)
        before_used = budget.pools[POOL_RAG].used
        budget.commit(POOL_RAG, granted)
        assert budget.pools[POOL_RAG].used > before_used

    def test_release_devuelve_tokens(self):
        """release devuelve tokens reservados al pool."""
        budget = TokenBudget(agent_id="test", total_budget=10000)
        granted = budget.request(POOL_RAG, 500)
        before_reserved = budget.pools[POOL_RAG].reserved
        budget.release(POOL_RAG, 200)
        assert budget.pools[POOL_RAG].reserved < before_reserved

    def test_snapshot_retorna_estado_completo(self):
        """snapshot retorna dict con estado actual del budget."""
        budget = TokenBudget(agent_id="test", total_budget=10000)
        snap = budget.snapshot()
        assert snap["agent_id"] == "test"
        assert snap["total_budget"] == 10000
        assert "total_used" in snap
        assert "total_remaining" in snap
        assert "usage_pct" in snap
        assert "pools" in snap
        assert POOL_SYSTEM in snap["pools"]


# ===========================================================================
# Tests: TokenBudget — fallos (record_failure / max_failures)
# ===========================================================================


class TestTokenBudgetFailures:
    """Tests para manejo de fallos de agente."""

    def test_record_failure_reduce_presupuesto(self):
        """record_failure reduce el presupuesto total."""
        budget = TokenBudget(agent_id="test", total_budget=10000)
        budget.record_failure("agent_1", 1000)
        assert budget.total_budget < 10000

    def test_record_failure_penaliza_50pct(self):
        """Penaliza 50% de tokens usados: total_budget -= tokens_used * 0.5."""
        budget = TokenBudget(agent_id="test", total_budget=10000)
        budget.record_failure("agent_1", 2000)
        expected = 10000 - int(2000 * 0.5)
        assert budget.total_budget == expected

    def test_record_failure_no_presupuesto_negativo(self):
        """El presupuesto nunca baja de 0."""
        budget = TokenBudget(agent_id="test", total_budget=10)
        budget.record_failure("agent_1", 100)
        assert budget.total_budget >= 0

    def test_max_failures_desactiva(self):
        """Exceder max_failures desactiva el budget."""
        budget = TokenBudget(agent_id="test", max_failures=2)
        assert budget.disabled is False
        budget.record_failure("agent_1", 100)
        assert budget.disabled is False
        budget.record_failure("agent_1", 100)
        assert budget.disabled is True

    def test_fallos_seguimiento_por_agente(self):
        """Cada agente tiene su contador de fallos independiente."""
        budget = TokenBudget(agent_id="test", max_failures=3)
        budget.record_failure("agent_a", 100)
        budget.record_failure("agent_b", 100)
        budget.record_failure("agent_a", 100)
        # agent_a tiene 2 fallos, agent_b tiene 1, ninguno desactivado
        assert budget.disabled is False
        budget.record_failure("agent_a", 100)
        assert budget.disabled is True


# ===========================================================================
# Tests: BudgetManager
# ===========================================================================


class TestBudgetManagerInitAndRegister:
    """Tests de inicializacion y registro en BudgetManager."""

    def test_inicializacion(self):
        """BudgetManager se inicializa con valores por defecto."""
        mgr = BudgetManager()
        assert mgr._session_budget == DEFAULT_SESSION_BUDGET
        assert mgr._default_agent_budget == DEFAULT_AGENT_BUDGET
        assert mgr._min_reserve == MIN_RESERVE_TOKENS
        assert len(mgr._agent_budgets) == 0

    def test_register_agent_crea_token_budget(self):
        """register_agent crea y retorna un TokenBudget."""
        mgr = BudgetManager()
        budget = mgr.register_agent("agent_1")
        assert isinstance(budget, TokenBudget)
        assert budget.agent_id == "agent_1"
        assert budget.total_budget == DEFAULT_AGENT_BUDGET

    def test_register_agent_con_budget_personalizado(self):
        """register_agent acepta budget y priority personalizados."""
        mgr = BudgetManager()
        budget = mgr.register_agent("agent_1", budget=8000, priority=PRIORITY_HIGH)
        assert budget.total_budget == 8000
        assert budget.priority == PRIORITY_HIGH

    def test_register_agent_duplicado_retorna_existente(self):
        """Registrar el mismo agente dos veces retorna el existente."""
        mgr = BudgetManager()
        b1 = mgr.register_agent("agent_1")
        b2 = mgr.register_agent("agent_1", budget=99999)
        assert b1 is b2
        assert b1.total_budget == DEFAULT_AGENT_BUDGET  # No se sobreescribe

    def test_get_budget_retorna_existente(self):
        """get_budget retorna el TokenBudget de un agente registrado."""
        mgr = BudgetManager()
        mgr.register_agent("agent_1")
        budget = mgr.get_budget("agent_1")
        assert budget is not None
        assert budget.agent_id == "agent_1"

    def test_get_budget_inexistente_retorna_none(self):
        """get_budget retorna None si el agente no esta registrado."""
        mgr = BudgetManager()
        assert mgr.get_budget("inexistente") is None

    def test_get_or_create_crea_si_no_existe(self):
        """get_or_create crea un nuevo budget si no existe."""
        mgr = BudgetManager()
        budget = mgr.get_or_create("agent_new")
        assert budget is not None
        assert budget.agent_id == "agent_new"

    def test_get_or_create_retorna_existente(self):
        """get_or_create retorna el budget existente."""
        mgr = BudgetManager()
        b1 = mgr.register_agent("agent_1")
        b2 = mgr.get_or_create("agent_1")
        assert b1 is b2


# ===========================================================================
# Tests: BudgetManager — redistribucion y sesiones
# ===========================================================================


class TestBudgetManagerRedistribution:
    """Tests para redistribucion de presupuesto entre agentes."""

    def test_redistribute_idle_sin_donantes_retorna_vacio(self):
        """Sin donantes (agentes inactivos), redistribucion retorna {}."""
        mgr = BudgetManager()
        mgr.register_agent("agent_1")
        result = mgr.redistribute_idle()
        assert result == {}

    def test_redistribute_idle_sin_recipientes_retorna_vacio(self):
        """Sin recipientes activos, redistribucion retorna {}."""
        mgr = BudgetManager()
        budget = mgr.register_agent("agent_1")
        budget.confidence = CONFIDENCE_HIGH  # Inactivo
        result = mgr.redistribute_idle()
        assert result == {}

    def test_session_snapshot_retorna_agentes_de_sesion(self):
        """session_snapshot solo incluye agentes de la sesion indicada."""
        mgr = BudgetManager()
        mgr.register_agent("a1", session_id="ses_1")
        mgr.register_agent("a2", session_id="ses_1")
        mgr.register_agent("b1", session_id="ses_2")
        snap = mgr.session_snapshot("ses_1")
        assert "a1" in snap["agents"]
        assert "a2" in snap["agents"]
        assert "b1" not in snap["agents"]

    def test_reset_session_elimina_agentes(self):
        """reset_session elimina todos los agentes de una sesion."""
        mgr = BudgetManager()
        mgr.register_agent("a1", session_id="ses_1")
        mgr.register_agent("a2", session_id="ses_1")
        count = mgr.reset_session("ses_1")
        assert count == 2
        assert mgr.get_budget("a1") is None
        assert mgr.get_budget("a2") is None

    def test_get_stats_retorna_estadisticas(self):
        """get_stats retorna estadisticas globales del manager."""
        mgr = BudgetManager()
        mgr.register_agent("a1")
        mgr.register_agent("a2")
        stats = mgr.get_stats()
        assert stats["agents_registered"] == 2
        assert stats["total_budget_allocated"] > 0
        assert "session_budget" in stats
        assert "default_agent_budget" in stats


# ===========================================================================
# Tests: Edge cases y valores limite
# ===========================================================================


class TestTokenBudgetEdgeCases:
    """Tests de casos limite para TokenBudget."""

    def test_budget_cero(self):
        """TokenBudget con total_budget=0."""
        budget = TokenBudget(agent_id="test", total_budget=0)
        assert budget.total_remaining == 0
        assert budget.can_spend is False
        assert budget.usage_pct == 0.0

    def test_request_tokens_cero(self):
        """Solicitar 0 tokens retorna 0."""
        budget = TokenBudget(agent_id="test", total_budget=10000)
        granted = budget.request(POOL_RAG, 0)
        # allocate(0) deberia retornar 0 porque remaining >= 0
        assert granted == 0

    def test_request_tokens_negativos(self):
        """Solicitar tokens negativos: allocate pasa el valor negativo
        porque min(tokens, available) con tokens negativo retorna el negativo."""
        budget = TokenBudget(agent_id="test", total_budget=10000)
        granted = budget.request(POOL_RAG, -100)
        # allocate no valida negativos, retorna el valor solicitado
        assert granted == -100

    def test_commit_sobre_reservados_no_rompe(self):
        """Commit mas de lo reservado no causa error."""
        budget = TokenBudget(agent_id="test", total_budget=10000)
        budget.commit(POOL_RAG, 9999)  # Sin reservar, commit se ajusta
        # No debe lanzar excepcion
        assert True

    def test_release_sin_reservar(self):
        """Release sin tokens reservados no causa error."""
        budget = TokenBudget(agent_id="test", total_budget=10000)
        budget.release(POOL_RAG, 100)  # Sin reservar
        assert True

    def test_pool_priority_retorna_normal_para_desconocido(self):
        """_pool_priority retorna PRIORITY_NORMAL para pools desconocidos."""
        priority = TokenBudget._pool_priority("unknown_pool")
        assert priority == PRIORITY_NORMAL

    def test_confidence_gate_con_valor_exacto_limite(self):
        """Confidence exactamente en CONFIDENCE_HIGH bloquea."""
        budget = TokenBudget(agent_id="test", total_budget=10000)
        budget.set_confidence(CONFIDENCE_HIGH)
        granted = budget.request(POOL_RAG, 100)
        assert granted == 0

    def test_confidence_medium_exacto_corte(self):
        """Confidence exactamente en CONFIDENCE_MEDIUM reduce."""
        budget = TokenBudget(agent_id="test", total_budget=10000)
        budget.set_confidence(CONFIDENCE_MEDIUM)
        granted = budget.request(POOL_RAG, 1000)
        assert granted == 500


# ===========================================================================
# Tests: BudgetManager — registro con sesion
# ===========================================================================


class TestBudgetManagerSession:
    """Tests de manejo de sesiones en BudgetManager."""

    def test_register_agent_con_session_id(self):
        """register_agent asigna parent_session al TokenBudget."""
        mgr = BudgetManager()
        budget = mgr.register_agent("agent_s1", session_id="session_xyz")
        assert budget.parent_session == "session_xyz"

    def test_session_snapshot_incluye_totales(self):
        """session_snapshot incluye totales de la sesion."""
        mgr = BudgetManager()
        mgr.register_agent("a1", session_id="ses_1")
        snap = mgr.session_snapshot("ses_1")
        assert snap["session_id"] == "ses_1"
        assert snap["total_budget_allocated"] > 0
        assert "total_used" in snap
        assert "total_remaining" in snap
        assert "usage_pct" in snap

    def test_session_snapshot_sin_agentes_retorna_vacio(self):
        """session_snapshot sin agentes en la sesion retorna totales en 0."""
        mgr = BudgetManager()
        snap = mgr.session_snapshot("ses_vacia")
        assert snap["total_budget_allocated"] == 0
        assert snap["agents"] == {}
