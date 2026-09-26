"""Tests para la capa semántica gobernada (ADR-0050).

Cubre:
- Ruteo de consultas a agregados (3 rutas de referencia + sin match).
- Validación fail-fast de patrones regex inválidos.
- Lookup de ratio de reducción por nombre de agregado.
- Estimación de costo enrutado vs directo.
- Inmutabilidad de los dataclasses (regla IMM).
"""
from __future__ import annotations

import pytest

from harness.semantic import (
    BANK_CASE_COST_REDUCTION_RATIO,
    SemanticLayer,
    SemanticRoute,
    build_bank_reference_layer,
)

_QUERY_EDAD = "¿Cuál es la distribución de nuestra base de clientes en diferentes franjas de edad?"
_QUERY_VENTAS = "¿Cuál fue el rendimiento de las ventas del último trimestre?"
_QUERY_STOCK = "¿Cómo está el nivel de inventario de la bodega norte?"


@pytest.fixture
def layer() -> SemanticLayer:
    """Fixture: capa semántica de referencia del caso bancario."""
    return build_bank_reference_layer()


class TestRouteQuery:
    """Ruteo de consultas en lenguaje natural."""

    def test_distribucion_clientes_enruta_a_agregado(self, layer: SemanticLayer) -> None:
        route = layer.route_query(_QUERY_EDAD)
        assert route is not None
        assert route.target_aggregate == "customer_age_distribution_aggregate"
        assert route.metrics == ("customer_count",)
        assert route.dimensions == ("age_group",)

    def test_ventas_enruta_a_performance(self, layer: SemanticLayer) -> None:
        route = layer.route_query(_QUERY_VENTAS)
        assert route is not None
        assert route.target_aggregate == "sales_performance_aggregate"

    def test_inventario_enruta_a_summary(self, layer: SemanticLayer) -> None:
        route = layer.route_query(_QUERY_STOCK)
        assert route is not None
        assert route.target_aggregate == "inventory_summary_aggregate"

    def test_consulta_sin_match_devuelve_none(self, layer: SemanticLayer) -> None:
        assert layer.route_query("¿Qué hora es?") is None

    def test_rutas_son_insensibles_a_mayusculas(self, layer: SemanticLayer) -> None:
        route = layer.route_query("DISTRIBUCIÓN DE CLIENTES POR EDAD")
        assert route is not None


class TestValidation:
    """Validación fail-fast e inmutabilidad."""

    def test_regex_invalida_rechaza_construccion(self) -> None:
        bad_route = SemanticRoute(
            query_pattern="(distribuci[ón",  # bracket sin cerrar
            target_aggregate="broken",
            metrics=("m",),
            dimensions=("d",),
        )
        with pytest.raises(ValueError, match="patrón de ruta inválido"):
            SemanticLayer(name="x", description="y", routes=(bad_route,))

    def test_dataclasses_son_inmutables(self, layer: SemanticLayer) -> None:
        route = layer.routes[0]
        with pytest.raises(AttributeError):
            route.target_aggregate = "otro"  # type: ignore[misc]


class TestCostReduction:
    """Ratios de reducción de costo (caso 21,000x)."""

    def test_ratio_por_nombre_de_agregado(self, layer: SemanticLayer) -> None:
        ratio = layer.cost_reduction_for("customer_age_distribution_aggregate")
        assert ratio == pytest.approx(BANK_CASE_COST_REDUCTION_RATIO)

    def test_agregado_desconocido_devuelve_none(self, layer: SemanticLayer) -> None:
        assert layer.cost_reduction_for("no_existe") is None

    def test_estimacion_costo_enrutado(self, layer: SemanticLayer) -> None:
        route = layer.route_query(_QUERY_EDAD)
        assert route is not None
        routed = layer.estimate_routed_cost(direct_cost=17.93, route=route)
        assert routed < 0.001  # caso bancario: $17.93 -> <$0.001

    def test_capa_referencia_tiene_tres_rutas(self, layer: SemanticLayer) -> None:
        assert len(layer.routes) == 3
