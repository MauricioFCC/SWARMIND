"""semantic_layer — Capa semántica gobernada entre agentes IA y datos.

Implementa el ADR-0050: enrutar consultas en lenguaje natural hacia
agregados preconstruidos en lugar de escanear tablas subyacentes. El caso
de estudio bancario (5 consultas en producción) midió una reducción de
costo de cómputo de ~21,000x al usar la capa semántica:

- Sin capa: $17.93 y 3.15 TB escaneados.
- Con capa: <$0.001 y 144 MB escaneados.

Principios:
1. Métricas, dimensiones y definiciones gobernadas se declaran una vez.
2. Las consultas LLM se enrutan al agregado preconstruido correcto.
3. CQRS: las rutas solo cubren lecturas (queries); los comandos no pasan
   por aquí.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime

logger = logging.getLogger(__name__)

__all__ = [
    "BANK_CASE_COST_REDUCTION_RATIO",
    "SemanticDefinition",
    "SemanticDimension",
    "SemanticLayer",
    "SemanticMetric",
    "SemanticRoute",
    "build_bank_reference_layer",
]

# Ratio costo-enrutado / costo-directo medido en el caso bancario
# (1/21000). Valor de referencia; cada ruta puede sobreescribirlo.
BANK_CASE_COST_REDUCTION_RATIO = 1.0 / 21_000.0

# Frecuencia de revalidación por defecto de las métricas gobernadas.
DEFAULT_VALIDATION_FREQUENCY = "monthly"


@dataclass(frozen=True)
class SemanticMetric:
    """Métrica gobernada con definición única y consistente.

    Attributes:
        name: Identificador de la métrica (ej. ``customer_count``).
        description: Descripción técnica.
        unit: Unidad de medida (count, currency, percentage...).
        formula: Expresión SQL o fórmula que la calcula.
        friendly_description: Descripción para usuarios de negocio.
        is_validated: Si la métrica pasó su última validación.
        validation_frequency: Cadencia de revalidación gobernada.
    """

    name: str
    description: str
    unit: str
    formula: str | None = None
    friendly_description: str = ""
    is_validated: bool = False
    validation_frequency: str = DEFAULT_VALIDATION_FREQUENCY


@dataclass(frozen=True)
class SemanticDimension:
    """Dimensión gobernada para filtrado y agregación.

    Attributes:
        name: Identificador de la dimensión (ej. ``age_group``).
        description: Descripción técnica.
        values: Valores permitidos (picklist), si aplica.
        hierarchy: Jerarquía padre->hijo (ej. país->región->ciudad).
        is_mutable: Si los usuarios pueden agregar nuevos valores.
    """

    name: str
    description: str
    values: tuple[str, ...] | None = None
    hierarchy: tuple[str, ...] | None = None
    is_mutable: bool = False


@dataclass(frozen=True)
class SemanticDefinition:
    """Definición de negocio gobernada.

    Attributes:
        name: Identificador de la definición.
        description: Descripción técnica.
        definition: Definición formal (lenguaje natural o SQL).
        depends_on: Nombres de métricas/dimensiones de las que depende.
        validation_rules: Reglas que debe cumplir la definición.
    """

    name: str
    description: str
    definition: str
    depends_on: tuple[str, ...] = ()
    validation_rules: tuple[str, ...] = ()


@dataclass(frozen=True)
class SemanticRoute:
    """Ruta que mapea un patrón de consulta a un agregado preconstruido.

    Attributes:
        query_pattern: Regex (case-insensitive) que matchea la consulta.
        target_aggregate: Nombre del agregado/vista materializada destino.
        metrics: Métricas gobernadas involucradas.
        dimensions: Dimensiones de filtrado/agregación.
        requires_human_approval: Si el resultado requiere revisión humana.
        cost_reduction_ratio: Ratio costo-enrutado/costo-directo esperado.
    """

    query_pattern: str
    target_aggregate: str
    metrics: tuple[str, ...]
    dimensions: tuple[str, ...]
    requires_human_approval: bool = False
    cost_reduction_ratio: float = BANK_CASE_COST_REDUCTION_RATIO


@dataclass(frozen=True)
class SemanticLayer:
    """Capa semántica gobernada entre IA y almacén de datos.

    Attributes:
        name: Identificador de la capa.
        description: Descripción del dominio cubierto.
        metrics: Métricas gobernadas.
        dimensions: Dimensiones gobernadas.
        definitions: Definiciones de negocio.
        routes: Rutas de consulta disponibles.
        created_at: ISO-8601 UTC de creación.
    """

    name: str
    description: str
    metrics: tuple[SemanticMetric, ...] = ()
    dimensions: tuple[SemanticDimension, ...] = ()
    definitions: tuple[SemanticDefinition, ...] = ()
    routes: tuple[SemanticRoute, ...] = ()
    created_at: str = field(
        default_factory=lambda: datetime.now(UTC).isoformat()
    )

    def __post_init__(self) -> None:
        """Valida que todos los patrones de ruta compilen (fail fast).

        Raises:
            ValueError: Si algún ``query_pattern`` no es una regex válida.
        """
        for route in self.routes:
            try:
                re.compile(route.query_pattern, re.IGNORECASE)
            except re.error as exc:
                raise ValueError(
                    f"WHAT: patrón de ruta inválido '{route.query_pattern}'. "
                    f"WHY: no compila como regex ({exc}); enrutaría mal en runtime. "
                    f"WHERE: SemanticLayer(routes) -> '{route.target_aggregate}'"
                ) from exc

    def route_query(self, query: str) -> SemanticRoute | None:
        """Encuentra la primera ruta cuyo patrón matchea la consulta.

        Args:
            query: Consulta en lenguaje natural.

        Returns:
            La ruta correspondiente, o None si ninguna matchea.
        """
        for route in self.routes:
            if self._matches(query, route.query_pattern):
                return route
        return None

    def cost_reduction_for(self, target_aggregate: str) -> float | None:
        """Devuelve el ratio de reducción de costo de un agregado.

        Args:
            target_aggregate: Nombre del agregado destino.

        Returns:
            El ratio (costo_enrutado / costo_directo), o None si el
            agregado no tiene ruta asociada.
        """
        for route in self.routes:
            if route.target_aggregate == target_aggregate:
                return route.cost_reduction_ratio
        return None

    def estimate_routed_cost(self, direct_cost: float, route: SemanticRoute) -> float:
        """Estima el costo de cómputo usando la ruta en lugar del escaneo.

        Args:
            direct_cost: Costo del escaneo directo (mismas unidades).
            route: Ruta por la que se enruta la consulta.

        Returns:
            Costo estimado tras aplicar el ratio de la ruta.
        """
        return direct_cost * route.cost_reduction_ratio

    @staticmethod
    def _matches(query: str, pattern: str) -> bool:
        """Evalúa un patrón regex contra la consulta sin excepciones mudas.

        Args:
            query: Consulta en lenguaje natural.
            pattern: Patrón regex (case-insensitive).

        Returns:
            True si el patrón matchea; False si no matchea o el patrón es
            inválido (se registra warning, nunca se silencia).
        """
        try:
            return re.search(pattern, query, re.IGNORECASE) is not None
        except re.error as exc:
            logger.warning(
                "Patrón de ruta inválido '%s' (se ignora la ruta): %s", pattern, exc
            )
            return False


# ---------------------------------------------------------------------------
# Capa de referencia: caso de estudio bancario (ADR-0050)
# ---------------------------------------------------------------------------

_AGE_DISTRIBUTION_ROUTE = SemanticRoute(
    query_pattern=(
        r"(distribuci[oó]n|distribution).*?(clientes?|customer)"
        r".*?(edad|age|franjas|bins)"
    ),
    target_aggregate="customer_age_distribution_aggregate",
    metrics=("customer_count",),
    dimensions=("age_group",),
)

_SALES_PERFORMANCE_ROUTE = SemanticRoute(
    query_pattern=r"(rendimiento|performance|m[eé]trica).*?(ventas|sales|ingresos|revenue)",
    target_aggregate="sales_performance_aggregate",
    metrics=("total_sales", "average_sale", "growth_rate"),
    dimensions=("period", "region"),
)

# Lookaheads: en lenguaje natural el orden de las palabras no es fijo
# ("nivel de inventario" vs "inventario ... nivel").
_INVENTORY_ROUTE = SemanticRoute(
    query_pattern=(
        r"(?=.*(?:inventario|inventory|stock))"
        r"(?=.*(?:nivel|level|cantidad|quantity))"
    ),
    target_aggregate="inventory_summary_aggregate",
    metrics=("current_stock", "reserved_stock", "available_stock"),
    dimensions=("product_id", "location"),
)


def build_bank_reference_layer() -> SemanticLayer:
    """Construye la capa semántica de referencia del caso bancario.

    Réplica de las 3 rutas probadas en el estudio de origen (distribución
    de clientes, rendimiento de ventas e inventario), todas con el ratio
    de reducción de costo medido (~21,000x).

    Returns:
        Una nueva instancia inmutable lista para usar en tests o demos.
    """
    return SemanticLayer(
        name="bank_semantic_layer",
        description=(
            "Capa semántica gobernada para consultas bancarias y financieras "
            "(referencia ADR-0050, caso de estudio 21,000x)"
        ),
        routes=(
            _AGE_DISTRIBUTION_ROUTE,
            _SALES_PERFORMANCE_ROUTE,
            _INVENTORY_ROUTE,
        ),
    )
