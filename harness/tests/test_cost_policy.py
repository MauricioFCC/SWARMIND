"""Contrato de la politica de costos (ciclo 11.19 — ADR fr-0001).

WHAT: verifica ``harness/model_router/cost_policy.py`` contra el ADR:

- **fr-0001-routeo-costos-suicheo.md** (5 mejoras):
  1. Escalera de costo: free -> small -> standard -> frontier.
  2. Veto de escalada: si frontier estimado supera umbral, intentar
     standard antes (STEER-lite cost-aware).
  3. Tier free para complejidad baja (<= umbral) con output corto.
  4. Veto de presupuesto de salida: > umbral tokens de salida -> vetar
     modelos de costo de salida ultra-alto salvo force_tier.
  5. Seleccion de tier de votacion k-in-1 solo con modelos de input
     barato cuando gate_score alto y confidence baja.

WHY: el cascade_router actual escala directo a frontier sin evaluar si el
salto justifica el costo; el ADR exige un escalera intermedia y vetos.

WHERE: ``harness/model_router/cost_policy.py``.
"""

from __future__ import annotations

import pytest

from harness.model_router.cost_policy import (
    COST_ESCALATION_THRESHOLD_USD,
    COST_PRICE_TABLE,
    FREE_TIER_MAX_COMPLEXITY,
    OUTPUT_BUDGET_VETO_TOKENS,
    TIER_ORDER_COST,
    TierCost,
    estimated_cost_usd,
    pick_voting_tier,
    route_for_complexity,
    should_escalate_via_standard,
    veto_output_budget,
)


class TestEscaleraDeCosto:
    """Tiers ordenados de menor a mayor costo de salida."""

    def test_tier_order_es_creciente(self) -> None:
        prices = [COST_PRICE_TABLE[t].output_per_mtok for t in TIER_ORDER_COST]

        assert prices == sorted(prices), "la escalera debe ser monotonamente creciente"

    def test_tier_free_es_cero(self) -> None:
        free = COST_PRICE_TABLE["free"]

        assert free.input_per_mtok == 0.0
        assert free.output_per_mtok == 0.0

    def test_tier_cost_frozen(self) -> None:
        from dataclasses import FrozenInstanceError

        with pytest.raises(FrozenInstanceError):
            TierCost(input_per_mtok=0.0, output_per_mtok=1.0).output_per_mtok = 2.0  # type: ignore[misc]

    def test_precios_default_exactos_del_adr(self) -> None:
        """Los precios default son los del ADR fr-0001 (calibrables pero fijos)."""
        assert COST_PRICE_TABLE == {
            "free": TierCost(input_per_mtok=0.0, output_per_mtok=0.0),
            "small": TierCost(input_per_mtok=0.14, output_per_mtok=0.28),
            "standard": TierCost(input_per_mtok=0.10, output_per_mtok=0.50),
            "frontier": TierCost(input_per_mtok=2.00, output_per_mtok=10.00),
        }

    def test_precios_nunca_negativos(self) -> None:
        """Ningun tier puede tener precio negativo (invariantes de tabla)."""
        for tier, price in COST_PRICE_TABLE.items():
            assert price.input_per_mtok >= 0.0, f"{tier}: input negativo"
            assert price.output_per_mtok >= 0.0, f"{tier}: output negativo"


class TestEstimatedCost:
    """Costo estimado USD = (in * price_in + out * price_out) / 1M."""

    def test_costo_cero_para_free(self) -> None:
        assert estimated_cost_usd("free", 10_000, 5_000, COST_PRICE_TABLE) == 0.0

    def test_costo_small(self) -> None:
        cost = estimated_cost_usd("small", 100_000, 50_000, COST_PRICE_TABLE)

        assert cost == pytest.approx(
            (100_000 * COST_PRICE_TABLE["small"].input_per_mtok
             + 50_000 * COST_PRICE_TABLE["small"].output_per_mtok) / 1_000_000
        )

    def test_tier_desconocido_es_error(self) -> None:
        with pytest.raises(ValueError, match="desconocido"):
            estimated_cost_usd("fantasma", 1000, 1000, COST_PRICE_TABLE)


class TestEscalacionConscienteDeCosto:
    """Mejora 1: antes de saltar a frontier, intentar standard si el salto es caro."""

    def test_escalada_barata_no_usa_standard(self) -> None:
        assert should_escalate_via_standard(
            first_cost=0.001,
            frontier_cost=0.01,
            threshold=COST_ESCALATION_THRESHOLD_USD,
        ) is False, "salto barato: ir directo a frontier"

    def test_escalada_cara_usa_standard_primero(self) -> None:
        assert should_escalate_via_standard(
            first_cost=0.001,
            frontier_cost=0.10,
            threshold=COST_ESCALATION_THRESHOLD_USD,
        ) is True, "salto caro: intentar standard antes"

    def test_umbral_estricto(self) -> None:
        assert should_escalate_via_standard(0.0, 0.05, 0.05) is False, ">= umbral no es 'cara'"
        assert should_escalate_via_standard(0.0, 0.05001, 0.05) is True


class TestRutaPorComplejidad:
    """Mejora 2: tier free para complejidad baja y output corto."""

    def test_complejidad_baja_usa_free(self) -> None:
        assert route_for_complexity(
            complexity_score=2, estimated_output_tokens=1500,
            free_max_complexity=FREE_TIER_MAX_COMPLEXITY,
            free_max_output_tokens=2000,
        ) == "free"

    def test_complejidad_alta_no_usa_free(self) -> None:
        assert route_for_complexity(5, 1500, 2, 2000) == "standard"

    def test_output_largo_no_usa_free(self) -> None:
        assert route_for_complexity(1, 3000, 2, 2000) == "standard"

    def test_complejidad_media_estandar(self) -> None:
        assert route_for_complexity(4, 1000, 2, 2000) == "standard"

    def test_complejidad_frontier(self) -> None:
        assert route_for_complexity(8, 5000, 2, 2000) == "frontier"


class TestVetoPresupuestoSalida:
    """Mejora 5: salida > umbral -> vetar modelos de costo ultra-alto."""

    def test_salida_corta_no_veta(self) -> None:
        assert veto_output_budget(
            model="claude-opus-5.5", estimated_output_tokens=3000,
            veto_models=frozenset({"claude-opus-5.5"}),
            veto_threshold_tokens=OUTPUT_BUDGET_VETO_TOKENS,
        ) is False

    def test_salida_larga_veta_modelo_caro(self) -> None:
        assert veto_output_budget(
            model="claude-opus-5.5", estimated_output_tokens=5000,
            veto_models=frozenset({"claude-opus-5.5"}),
            veto_threshold_tokens=OUTPUT_BUDGET_VETO_TOKENS,
        ) is True

    def test_force_tier_escapa_veto(self) -> None:
        assert veto_output_budget(
            model="claude-opus-5.5", estimated_output_tokens=5000,
            veto_models=frozenset({"claude-opus-5.5"}),
            veto_threshold_tokens=OUTPUT_BUDGET_VETO_TOKENS,
            force_tier=True,
        ) is False

    def test_modelo_barado_no_veta(self) -> None:
        assert veto_output_budget(
            model="claude-haiku-5.5", estimated_output_tokens=5000,
            veto_models=frozenset({"claude-opus-5.5"}),
            veto_threshold_tokens=OUTPUT_BUDGET_VETO_TOKENS,
        ) is False


class TestVotacionKIn1:
    """Mejora 4: votacion k-in-1 solo con modelos de input barato."""

    def test_gate_alto_confianza_baja_usa_barato(self) -> None:
        assert pick_voting_tier(
            gate_score=75, confidence=0.5,
            cheap_input_tiers=("small", "standard"),
        ) == "standard"

    def test_gate_medio_confianza_alta_no_vota(self) -> None:
        assert pick_voting_tier(
            gate_score=60, confidence=0.8,
            cheap_input_tiers=("small", "standard"),
        ) is None, "sin votacion: confidence alta no justifica k-in-1"

    def test_gate_bajo_no_vota(self) -> None:
        assert pick_voting_tier(
            gate_score=50, confidence=0.5,
            cheap_input_tiers=("small", "standard"),
        ) is None

    def test_elige_el_mas_barato_de_los_baratos(self) -> None:
        """standard ($0.10/MTok input) es mas barato que small ($0.14)."""
        assert pick_voting_tier(
            gate_score=80, confidence=0.6,
            cheap_input_tiers=("small", "standard"),
        ) == "standard", "standard tiene el input mas barato de la tabla"


class TestAcoplamientoCascadeRouter:
    """El CascadeRouter expone un plan de escalera consciente de costo."""

    def test_plan_escalera_salta_frontier_barato(self) -> None:
        """Salto barato: small -> frontier (sin escalon intermedio)."""
        from harness.model_router.cascade_router import CascadeRouter

        router = CascadeRouter(decide_fn=lambda t: ("small", 0.8))
        plan = router.plan_cost_aware_escalation(
            input_tokens=1_000, output_tokens=1_000
        )

        assert plan == ("small", "frontier"), "salto < umbral: sin standard"

    def test_plan_escalera_cara_incluye_standard(self) -> None:
        """Salto caro: small -> standard -> frontier (escalera completa)."""
        from harness.model_router.cascade_router import CascadeRouter

        router = CascadeRouter(decide_fn=lambda t: ("small", 0.8))
        plan = router.plan_cost_aware_escalation(
            input_tokens=500_000, output_tokens=200_000
        )

        assert plan == ("small", "standard", "frontier"), (
            "salto > umbral: intentar standard antes de frontier"
        )


class TestAcoplamientoSessionAffinity:
    """La afinidad de sesion dispara cambio de modelo con cache roto."""

    def test_cache_sano_no_dispara_cambio(self) -> None:
        from harness.model_router.session_affinity import (
            CACHE_HEALTH_MIN_HIT_RATE,
            should_switch_on_cache_health,
        )

        assert should_switch_on_cache_health(CACHE_HEALTH_MIN_HIT_RATE) is False
        assert should_switch_on_cache_health(0.8) is False

    def test_cache_roto_dispara_cambio(self) -> None:
        from harness.model_router.session_affinity import (
            should_switch_on_cache_health,
        )

        assert should_switch_on_cache_health(0.59) is True
        assert should_switch_on_cache_health(0.0) is True
