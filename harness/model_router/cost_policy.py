"""Politica de costos para routeo de modelos (ciclo 11.19 — ADR fr-0001).

WHAT: 5 mejoras del ADR ``fr-0001-routeo-costos-suicheo.md`` como
funciones puras e inyectables (sin rng, deterministas):

1. **Escalera de costo** (``TIER_ORDER_COST``): free -> small ->
   standard -> frontier, monotonamente creciente en costo de salida.
2. **Escalacion consciente de costo** (``should_escalate_via_standard``):
   si saltar de small a frontier supera el umbral USD, intentar un tier
   intermedio eficiente antes (STEER-lite cost-aware).
3. **Ruta por complejidad** (``route_for_complexity``): complejidad baja
   + output corto -> tier ``free`` (cero riesgo de reintento).
4. **Veto de presupuesto de salida** (``veto_output_budget``): salida
   estimada > umbral -> vetar modelos de costo de salida ultra-alto salvo
   ``force_tier`` explicito del usuario.
5. **Votacion k-in-1** (``pick_voting_tier``): votar k veces en una sola
   llamada solo cuando ``gate_score`` es alto y ``confidence`` baja, y
   solo con tiers de input barato.

WHY: el cascade_router escala directo a frontier (~10-40x mas caro) sin
evaluar si el salto se justifica para la tarea; el ADR exige escalera
intermedia, tier free, vetos por presupuesto y voting economico.

WHERE: ``harness/model_router/cost_policy.py`` (consumido por
``cascade_router``, ``session_affinity`` y ``request_governor``).
"""

from __future__ import annotations

from dataclasses import dataclass

#: Tope de tokens de salida por encima del cual se aplica el veto de
#: modelos ultra-caros (ADR: 4000 tokens de salida estimados).
OUTPUT_BUDGET_VETO_TOKENS = 4000

#: Complejidad maxima para enviar directo al tier ``free`` (ADR: <= 2).
FREE_TIER_MAX_COMPLEXITY = 2

#: Output maximo (tokens) para calificar al tier ``free`` (ADR: < 2000).
FREE_MAX_OUTPUT_TOKENS = 2000

#: Umbral USD: si saltar a frontier cuesta mas que esto, intentar
#: standard primero (ADR: $0.05).
COST_ESCALATION_THRESHOLD_USD = 0.05

#: Gate score minimo para considerar votacion k-in-1 (ADR: >= 70).
VOTING_GATE_MIN_SCORE = 70

#: Confidence maxima para justificar votacion k-in-1 (ADR: < 0.7).
VOTING_MAX_CONFIDENCE = 0.7

#: Tiers validos en la escalera de costo (orden creciente de salida).
TIER_ORDER_COST: tuple[str, ...] = ("free", "small", "standard", "frontier")

#: Orden de tiers candidatos para votacion k-in-1 (input barato primero).
VOTING_CHEAP_TIERS: tuple[str, ...] = ("small", "standard")


@dataclass(frozen=True)
class TierCost:
    """Precio USD por millon de tokens de un tier de la escalera.

    Attributes:
        input_per_mtok: USD por millon de tokens de entrada.
        output_per_mtok: USD por millon de tokens de salida.
    """

    input_per_mtok: float
    output_per_mtok: float


#: Tabla de precios default (calibrable; fuentes: ADR fr-0001 + opencode.ai/go).
#: Los valores son DEFAULTS calibrables via inyeccion de price_table.
COST_PRICE_TABLE: dict[str, TierCost] = {
    "free": TierCost(input_per_mtok=0.0, output_per_mtok=0.0),
    "small": TierCost(input_per_mtok=0.14, output_per_mtok=0.28),
    "standard": TierCost(input_per_mtok=0.10, output_per_mtok=0.50),
    "frontier": TierCost(input_per_mtok=2.00, output_per_mtok=10.00),
}

#: Complejidad minima para saltar directo al tier ``frontier``.
FRONTIER_MIN_COMPLEXITY = 8

#: Modelos de costo de salida ultra-alto vetados por presupuesto (ADR).
OUTPUT_BUDGET_VETO_MODELS: frozenset[str] = frozenset(
    {"gpt-5.4-pro", "claude-opus-5.5"}
)

_TOKENS_PER_MILLION = 1_000_000


def estimated_cost_usd(
    tier: str,
    input_tokens: int,
    output_tokens: int,
    price_table: dict[str, TierCost] | None = None,
) -> float:
    """Costo USD estimado de una llamada al ``tier``.

    Args:
        tier: Tier de ``TIER_ORDER_COST``.
        input_tokens: Tokens de entrada estimados.
        output_tokens: Tokens de salida estimados.
        price_table: Precios por tier (default ``COST_PRICE_TABLE``).

    Returns:
        Costo en USD (float, >= 0).

    Raises:
        ValueError: Si el tier es desconocido.
    """
    table = price_table or COST_PRICE_TABLE
    if tier not in table:
        raise ValueError(
            f"WHAT: tier desconocido '{tier}'. "
            f"WHY: debe estar en {list(table)}. "
            "WHERE: estimated_cost_usd"
        )
    price = table[tier]
    return (
        input_tokens * price.input_per_mtok + output_tokens * price.output_per_mtok
    ) / _TOKENS_PER_MILLION


def should_escalate_via_standard(
    first_cost: float,
    frontier_cost: float,
    threshold: float = COST_ESCALATION_THRESHOLD_USD,
) -> bool:
    """¿Intentar un tier ``standard`` antes de saltar a ``frontier``?

    STEER-lite cost-aware: si el costo INCREMENTAL de saltar directo a
    frontier (``frontier_cost - first_cost``) supera el umbral, el
    escalon intermedio (standard) amortiza el salto.

    Args:
        first_cost: Costo USD del intento small ya ejecutado.
        frontier_cost: Costo USD estimado del intento frontier.
        threshold: Umbral USD (default ``COST_ESCALATION_THRESHOLD_USD``).

    Returns:
        True si conviene intentar ``standard`` antes que ``frontier``.
    """
    return (frontier_cost - first_cost) > threshold


def route_for_complexity(
    complexity_score: int,
    estimated_output_tokens: int,
    free_max_complexity: int = FREE_TIER_MAX_COMPLEXITY,
    free_max_output_tokens: int = FREE_MAX_OUTPUT_TOKENS,
) -> str:
    """Tier inicial por complejidad (ADR mejora 2: free para lo trivial).

    Args:
        complexity_score: Score de complejidad (0-10).
        estimated_output_tokens: Output estimado de la tarea.
        free_max_complexity: Complejidad maxima para tier free.
        free_max_output_tokens: Output maximo para tier free.

    Returns:
        Tier ``"free"``, ``"standard"`` o ``"frontier"``.
    """
    if (
        complexity_score <= free_max_complexity
        and estimated_output_tokens <= free_max_output_tokens
    ):
        return "free"
    if complexity_score >= FRONTIER_MIN_COMPLEXITY:
        return "frontier"
    return "standard"


def veto_output_budget(
    model: str,
    estimated_output_tokens: int,
    veto_models: frozenset[str] = OUTPUT_BUDGET_VETO_MODELS,
    veto_threshold_tokens: int = OUTPUT_BUDGET_VETO_TOKENS,
    force_tier: bool = False,
) -> bool:
    """¿Vetar ``model`` por presupuesto de salida excesivo (ADR mejora 5)?

    Args:
        model: Nombre del modelo candidato.
        estimated_output_tokens: Output estimado de la tarea.
        veto_models: Modelos de costo de salida ultra-alto.
        veto_threshold_tokens: Output maximo antes de aplicar el veto.
        force_tier: Escape hatch explicito del usuario (anula el veto).

    Returns:
        True si el modelo esta vetado para esta tarea.
    """
    if force_tier:
        return False
    return model in veto_models and estimated_output_tokens > veto_threshold_tokens


def pick_voting_tier(
    gate_score: int,
    confidence: float,
    cheap_input_tiers: tuple[str, ...] = VOTING_CHEAP_TIERS,
    price_table: dict[str, TierCost] | None = None,
) -> str | None:
    """Tier para votacion k-in-1 economico (ADR mejora 4).

    La votacion multiple en una sola llamada replica el prompt de entrada
    k veces, por lo que el costo de INPUT domina; solo se vota cuando el
    ``gate_score`` es alto y ``confidence`` es baja (el modelo duda pero
    la senal de verificacion es fuerte), y siempre con el tier de input
    mas barato entre los candidatos.

    Args:
        gate_score: Score del gate de verificacion (0-100).
        confidence: Confidence del modelo (0.0-1.0).
        cheap_input_tiers: Tiers candidatos de input barato.
        price_table: Precios por tier (default ``COST_PRICE_TABLE``).

    Returns:
        Tier elegido (el de menor ``input_per_mtok``) o None si no vota.
    """
    if gate_score < VOTING_GATE_MIN_SCORE or confidence >= VOTING_MAX_CONFIDENCE:
        return None
    if not cheap_input_tiers:
        return None
    table = price_table or COST_PRICE_TABLE
    priced = [t for t in cheap_input_tiers if t in table]
    if not priced:
        return None
    return min(priced, key=lambda t: table[t].input_per_mtok)
