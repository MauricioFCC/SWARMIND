"""
TokenUsageTracker — Medicion de tokens por agente/llamada (ADR-0041 H2).

WHAT: Registra el uso real de tokens (input/output/cache) por agente y
llamada, agrega resumenes por agente, detecta fugas de tokens via alertas
respecto al presupuesto (SSOT token_budgets.yaml) y exporta un snapshot
serializable para telemetria/dashboard.
WHY: Hallazgo Anthropic 2026 — en agentes, el token usage explica ~80% de
la varianza de rendimiento. "Mide y controla tokens por agente primero".
WHERE: Complementa ``TokenBudget`` (presupuesto asignado) con la MEDICION
del uso real; puede alimentar spans ``gen_ai.usage.*`` de
``harness.observability.opentelemetry_agent``.

Uso:
    tracker = TokenUsageTracker()
    tracker.record_from_provider("builder", "gpt-x", {
        "prompt_tokens": 100, "completion_tokens": 20, "cached_tokens": 30,
    })
    alerts = tracker.alerts({"builder": 3072})
"""

from __future__ import annotations

import logging
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constantes
# ---------------------------------------------------------------------------

# Memoria circular por defecto: cantidad maxima de registros retenidos.
MAX_RECORDS = 10000

# Umbral de alerta: si uso > ALERT_THRESHOLD * budget, se genera alerta.
ALERT_THRESHOLD = 0.8

# Salud de cache: hit_ratio < CACHE_HEALTH_MIN_RATIO con volumen
# >= min_input_tokens indica bug estructural (cache-buster).
# Frontera 2026: ProjectDiscovery 7% -> 84% hit = -59-70% spend.
CACHE_HEALTH_MIN_RATIO = 0.60

# Volumen minimo de input para que el diagnostico sea significativo.
CACHE_HEALTH_MIN_INPUT = 10000

# Mapeo de claves comunes de provider (OpenAI/Anthropic style) -> campos
# de UsageRecord. Se suma si varias claves mapean al mismo campo.
_PROVIDER_KEY_MAP: MappingProxyType[str, str] = MappingProxyType({
    "prompt_tokens": "input_tokens",
    "completion_tokens": "output_tokens",
    "cached_tokens": "cache_read_tokens",
    "cache_read_input_tokens": "cache_read_tokens",
    "cache_creation_input_tokens": "cache_write_tokens",
})


# ---------------------------------------------------------------------------
# Dataclasses inmutables
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class UsageRecord:
    """Registro de una llamada LLM con desglose de tokens.

    WHAT: Tupla inmutable que describe el uso de tokens de UNA llamada.
    WHY: La medicion por llamada es la unidad minima para detectar fugas
    de tokens por agente (hallazgo Anthropic 2026).
    WHERE: ``TokenUsageTracker.record`` / ``record_from_provider``.

    Attributes:
        agent: Identificador del agente (no vacio).
        model: Modelo LLM usado.
        input_tokens: Tokens de entrada (>= 0).
        output_tokens: Tokens de salida (>= 0).
        cache_read_tokens: Tokens leidos de cache de prompt (>= 0).
        cache_write_tokens: Tokens escritos a cache de prompt (>= 0).
        timestamp: Epoch (segundos) de la llamada.

    Raises:
        ValueError: Si ``agent`` esta vacio o ``input_tokens``/``output_tokens``
            (o cache) son negativos.
    """

    agent: str
    model: str
    input_tokens: int
    output_tokens: int
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    timestamp: float = field(default_factory=time.time)

    def __post_init__(self) -> None:
        """Valida el registro en el momento de la creacion (WHAT+WHY+WHERE)."""
        if not self.agent.strip():
            raise ValueError(
                f"WHAT: agent='{self.agent}' esta vacio. "
                f"WHY: cada registro debe pertenecer a un agente para agregar "
                f"por agente. "
                f"WHERE: UsageRecord.__post_init__"
            )
        for metric_name in ("input_tokens", "output_tokens", "cache_read_tokens", "cache_write_tokens"):
            value = getattr(self, metric_name)
            if value < 0:
                raise ValueError(
                    f"WHAT: {metric_name}={value} es negativo. "
                    f"WHY: los tokens nunca pueden ser negativos. "
                    f"WHERE: UsageRecord.__post_init__"
                )

    def total(self) -> int:
        """Total de tokens de la llamada (input+output+cache_read+cache_write)."""
        return (
            self.input_tokens
            + self.output_tokens
            + self.cache_read_tokens
            + self.cache_write_tokens
        )

    def summary(self) -> str:
        """Resumen legible del registro para logs/diagnostico."""
        return (
            f"agent={self.agent} model={self.model} "
            f"input={self.input_tokens} output={self.output_tokens} "
            f"cache_read={self.cache_read_tokens} cache_write={self.cache_write_tokens} "
            f"total={self.total()} ts={self.timestamp:.1f}"
        )


@dataclass(frozen=True)
class ModelEfficiencyEntry:
    """Eficiencia de un modelo (tokens/llamada) para re-ponderar routing.

    WHAT: Agregado por modelo: llamadas y tokens promedio totales.
    WHY: Frontera (Copilot harness 2026) — el mismo harness varia hasta 40%
    en tokens entre modelos; medir tokens/llamada permite re-ponderar el
    routing por eficiencia y no solo por precio.
    WHERE: ``TokenUsageTracker.model_efficiency_report``.

    Attributes:
        model: Nombre del modelo.
        calls: Numero de llamadas registradas.
        avg_total_tokens: Promedio de tokens totales por llamada.
    """

    model: str
    calls: int
    avg_total_tokens: float


@dataclass(frozen=True)
class CacheHealth:
    """Salud de cache de prompt de un agente.

    WHAT: Diagnostico de hit-ratio (cache_read / (input + cache_read)).
    WHY: Un hit bajo con volumen alto casi siempre es un bug estructural
        (cache-buster: timestamps en system, few-shots reordenados, tool
        list dinamica) y no mala suerte — detectarlo ahorra hasta -70%.
    WHERE: ``TokenUsageTracker.cache_health``.

    Attributes:
        agent: Identificador del agente.
        hit_ratio: Ratio en [0.0, 1.0].
        total_input: Input + cache_read acumulados.
        cache_read: Tokens leidos de cache acumulados.
        needs_attention: True si hay volumen y ratio < minimo.
        reason: Explicacion legible del diagnostico.
    """

    agent: str
    hit_ratio: float
    total_input: int
    cache_read: int
    needs_attention: bool
    reason: str


@dataclass(frozen=True)
class AgentUsageSummary:
    """Agregacion de uso de tokens para un agente.

    WHAT: Vista agregada de todos los registros de un agente.
    WHY: Los dashboards y alertas necesitan una unica estructura por agente
    en lugar de iterar miles de registros crudos.
    WHERE: ``TokenUsageTracker.usage_by_agent`` / ``top_consumers``.

    Attributes:
        agent: Identificador del agente.
        calls: Cantidad de llamadas registradas.
        total_tokens: Suma de tokens (input+output+cache) del agente.
        input_tokens: Suma de tokens de entrada.
        output_tokens: Suma de tokens de salida.
        cache_hits: Cantidad de llamadas con cache_read_tokens > 0.
        est_inferred: True si alguna llamada reporto tokens de cache
            (metricas estimadas/inferidas del provider).
    """

    agent: str
    calls: int
    total_tokens: int
    input_tokens: int
    output_tokens: int
    cache_hits: int
    est_inferred: bool

    def summary(self) -> str:
        """Resumen legible del agregado para logs/diagnostico."""
        return (
            f"agent={self.agent} calls={self.calls} total={self.total_tokens} "
            f"input={self.input_tokens} output={self.output_tokens} "
            f"cache_hits={self.cache_hits} inferred={self.est_inferred}"
        )


# ---------------------------------------------------------------------------
# Tracker principal
# ---------------------------------------------------------------------------


class TokenUsageTracker:
    """Medidor de tokens por agente con agregacion, alertas y export.

    WHAT: Guarda registros en un buffer circular thread-safe, agrega por
    agente y emite alertas cuando un agente supera el umbral de su budget.
    WHY: Sin medicion real no se puede controlar el gasto; los budgets
    (``TokenBudget``) definen el limite, este tracker mide lo consumido.
    WHERE: Runtime de orquestacion — despues de cada llamada LLM.

    Uso:
        tracker = TokenUsageTracker()
        tracker.record(UsageRecord("builder", "gpt-x", 100, 20))
        summary = tracker.usage_by_agent()["builder"]
        for alert in tracker.alerts({"builder": 3072}):
            logger.warning(alert)
    """

    def __init__(self, max_records: int = MAX_RECORDS) -> None:
        """Inicializa el tracker con un buffer circular.

        Args:
            max_records: Maximo de registros retenidos; al superarlo se
                descartan los mas antiguos (deque circular).

        Raises:
            ValueError: Si ``max_records`` < 1.
        """
        if max_records < 1:
            raise ValueError(
                f"WHAT: max_records={max_records} debe ser >= 1. "
                f"WHY: el buffer circular necesita al menos 1 slot. "
                f"WHERE: TokenUsageTracker.__init__"
            )
        self._max_records = max_records
        self._records: deque[UsageRecord] = deque(maxlen=max_records)
        self._lock = threading.RLock()

    def record(self, usage: UsageRecord) -> None:
        """Registra una llamada LLM; descarta la mas antigua si se excede max_records.

        Args:
            usage: Registro de uso de tokens a almacenar.
        """
        with self._lock:
            self._records.append(usage)

    def record_from_provider(self, agent: str, model: str, provider_usage: dict[str, int]) -> None:
        """Registra uso directamente desde un dict de usage del provider.

        WHAT: Mapea claves comunes de provider
        (``prompt_tokens``/``completion_tokens``/``cached_tokens``/
        ``cache_read_input_tokens``/``cache_creation_input_tokens``) a los
        campos de ``UsageRecord``. Claves desconocidas se ignoran.
        WHY: API comoda para integrar respuestas de LLM sin construir
        ``UsageRecord`` manualmente.
        WHERE: Adaptadores de proveedor (OpenAI/Anthropic) — post-llamada.

        Args:
            agent: Identificador del agente.
            model: Modelo LLM usado.
            provider_usage: Dict de usage con claves del proveedor.

        Raises:
            ValueError: Si ``agent`` esta vacio.
        """
        mapped: dict[str, int] = {}
        for provider_key, target in _PROVIDER_KEY_MAP.items():
            value = provider_usage.get(provider_key)
            if value is not None:
                mapped[target] = mapped.get(target, 0) + int(value)
        usage = UsageRecord(
            agent=agent,
            model=model,
            input_tokens=mapped.get("input_tokens", 0),
            output_tokens=mapped.get("output_tokens", 0),
            cache_read_tokens=mapped.get("cache_read_tokens", 0),
            cache_write_tokens=mapped.get("cache_write_tokens", 0),
        )
        self.record(usage)

    def usage_by_agent(self) -> dict[str, AgentUsageSummary]:
        """Agrega el uso de tokens por agente.

        Returns:
            Dict {agente: AgentUsageSummary} con calls, totales y cache hits.
        """
        with self._lock:
            grouped: dict[str, list[UsageRecord]] = {}
            for rec in self._records:
                grouped.setdefault(rec.agent, []).append(rec)
            return {
                agent: self._aggregate(agent, records)
                for agent, records in grouped.items()
            }

    def total_tokens(self) -> int:
        """Total global de tokens consumidos (todos los registros)."""
        with self._lock:
            return sum(rec.total() for rec in self._records)

    def top_consumers(self, n: int = 5) -> tuple[AgentUsageSummary, ...]:
        """Retorna los top N agentes por total de tokens (descendente).

        Args:
            n: Cantidad maxima de resultados.

        Returns:
            Tuple de ``AgentUsageSummary`` ordenada por total_tokens desc.
        """
        ordered = sorted(
            self.usage_by_agent().values(),
            key=lambda s: s.total_tokens,
            reverse=True,
        )
        return tuple(ordered[:n])

    def cache_hit_ratio(self, agent: str | None = None) -> float:
        """Ratio de cache: cache_read / (input + cache_read) en [0, 1].

        Args:
            agent: Si se especifica, limita al calculo del agente; si es
                None, calcula el ratio global.

        Returns:
            Ratio en [0.0, 1.0]; 0.0 si no hay datos o denominador 0.
        """
        with self._lock:
            records = (
                self._records
                if agent is None
                else [rec for rec in self._records if rec.agent == agent]
            )
            cache_read = sum(rec.cache_read_tokens for rec in records)
            input_tokens = sum(rec.input_tokens for rec in records)
            denominator = input_tokens + cache_read
            if denominator <= 0:
                return 0.0
            return min(1.0, max(0.0, cache_read / denominator))

    def cache_health(
        self, min_input_tokens: int = CACHE_HEALTH_MIN_INPUT
    ) -> tuple[CacheHealth, ...]:
        """Diagnostica la salud de cache de prompt por agente.

        WHAT: Calcula hit_ratio por agente y marca bug estructural cuando
        hay volumen suficiente y el ratio esta bajo el minimo.
        WHY: Frontera 2026 — hit <60% con volumen = cache-buster casi
        seguro (timestamps, few-shots reordenados, tools dinamicas);
        arreglarlo recorta hasta -70% del spend.
        WHERE: Monitoreo periodico junto a ``alerts``.

        Args:
            min_input_tokens: Volumen minimo para diagnosticar.

        Returns:
            Tuple de CacheHealth (uno por agente con registros).
        """
        with self._lock:
            grouped: dict[str, list[UsageRecord]] = {}
            for rec in self._records:
                grouped.setdefault(rec.agent, []).append(rec)
            health: list[CacheHealth] = []
            for agent, records in grouped.items():
                cache_read = sum(r.cache_read_tokens for r in records)
                input_tokens = sum(r.input_tokens for r in records)
                total = input_tokens + cache_read
                ratio = min(1.0, max(0.0, cache_read / total)) if total > 0 else 0.0
                needs = total >= min_input_tokens and ratio < CACHE_HEALTH_MIN_RATIO
                if needs:
                    reason = (
                        f"hit_ratio={ratio:.2f} < {CACHE_HEALTH_MIN_RATIO:.2f} con "
                        f"volumen={total}: probable cache-buster (timestamps en "
                        f"system, few-shots reordenados o tool list dinamica)."
                    )
                elif total < min_input_tokens:
                    reason = f"volumen insuficiente ({total} < {min_input_tokens})."
                else:
                    reason = f"hit_ratio={ratio:.2f} saludable."
                health.append(CacheHealth(
                    agent=agent,
                    hit_ratio=ratio,
                    total_input=total,
                    cache_read=cache_read,
                    needs_attention=needs,
                    reason=reason,
                ))
            return tuple(health)

    def pressure(self, budget_tokens: int) -> float:
        """Presion de contexto: tokens usados / presupuesto (determinista).

        WHAT: Proyeccion de presion sin llamadas LLM (deepseek-harness:
            token-meter determinista).
        WHY: Decidir prune/summarize/evict ANTES del overflow, no despues.
        WHERE: Monitoreo del pipeline de contexto junto a cache_health.

        Args:
            budget_tokens: Presupuesto total de tokens (> 0).

        Returns:
            Ratio en [0.0, +inf) (puede exceder 1.0 = overflow).

        Raises:
            ValueError: Si budget_tokens <= 0 (WHAT+WHY+WHERE).
        """
        if budget_tokens <= 0:
            raise ValueError(
                f"WHAT: budget_tokens invalido: {budget_tokens}. "
                "WHY: la presion divide por el presupuesto; debe ser > 0. "
                "WHERE: TokenUsageTracker.pressure"
            )
        with self._lock:
            used = sum(r.total() for r in self._records)
        return used / budget_tokens

    def model_efficiency_report(self) -> tuple[ModelEfficiencyEntry, ...]:
        """Eficiencia por modelo: tokens promedio por llamada (desc).

        WHAT: Agrupa los registros por modelo y calcula tokens/llamada.
        WHY: Frontera (Copilot 2026) — hasta 40% de variacion de tokens
        entre modelos con el mismo harness; la metrica permite re-ponderar
        el complexity/cascade routing por eficiencia real.
        WHERE: Monitoreo periodico junto a ``cache_health``.

        Returns:
            Tuple de ModelEfficiencyEntry ordenado por avg_total_tokens desc.
        """
        with self._lock:
            grouped: dict[str, list[UsageRecord]] = {}
            for rec in self._records:
                grouped.setdefault(rec.model, []).append(rec)
            entries: list[ModelEfficiencyEntry] = []
            for model, records in grouped.items():
                totals = [r.total() for r in records]
                entries.append(ModelEfficiencyEntry(
                    model=model,
                    calls=len(records),
                    avg_total_tokens=sum(totals) / len(totals) if totals else 0.0,
                ))
            entries.sort(key=lambda e: (-e.avg_total_tokens, e.model))
            return tuple(entries)

    def alerts(self, budgets: dict[str, int]) -> tuple[str, ...]:
        """Genera alertas para agentes que superan el umbral de su budget.

        WHAT: Para cada agente con presupuesto, emite una alerta legible si
        su uso total > ``budgets[agent] * ALERT_THRESHOLD``.
        WHY: Deteccion temprana de fugas de tokens por agente (hallazgo
        Anthropic 2026: medir y controlar tokens por agente primero).
        WHERE: Orquestacion — periodicamente, con budgets del SSOT
        ``token_budgets.yaml``.

        Args:
            budgets: Dict {agente: presupuesto en tokens}.

        Returns:
            Tuple de mensajes de alerta (WHAT+WHY+WHERE); vacio si no hay
            agentes sobre el umbral.
        """
        summaries = self.usage_by_agent()
        messages: list[str] = []
        for agent, budget in budgets.items():
            summary = summaries.get(agent)
            if summary is None:
                continue
            threshold = int(budget * ALERT_THRESHOLD)
            if summary.total_tokens > threshold:
                pct = (summary.total_tokens / budget * 100) if budget else 100.0
                messages.append(
                    f"WHAT: agente '{agent}' excedio {ALERT_THRESHOLD:.0%} de su "
                    f"presupuesto (uso={summary.total_tokens}/{budget} = {pct:.1f}%). "
                    f"WHY: deteccion temprana de fugas de tokens por agente. "
                    f"WHERE: TokenUsageTracker.alerts"
                )
        return tuple(messages)

    def export(self) -> dict[str, Any]:
        """Snapshot serializable para telemetria/dashboard.

        Returns:
            Dict plano con max_records, record_count, total_tokens y agentes
            agregados (JSON-serializable).
        """
        with self._lock:
            return {
                "max_records": self._max_records,
                "record_count": len(self._records),
                "total_tokens": self.total_tokens(),
                "agents": {
                    agent: {
                        "calls": summary.calls,
                        "total_tokens": summary.total_tokens,
                        "input_tokens": summary.input_tokens,
                        "output_tokens": summary.output_tokens,
                        "cache_hits": summary.cache_hits,
                        "est_inferred": summary.est_inferred,
                    }
                    for agent, summary in self.usage_by_agent().items()
                },
            }

    @staticmethod
    def _aggregate(agent: str, records: list[UsageRecord]) -> AgentUsageSummary:
        """Agrega una lista de registros en un AgentUsageSummary.

        Args:
            agent: Nombre del agente del grupo.
            records: Registros del agente (orden cronologico de insercion).

        Returns:
            AgentUsageSummary con totales y conteos del grupo.
        """
        input_tokens = sum(rec.input_tokens for rec in records)
        output_tokens = sum(rec.output_tokens for rec in records)
        cache_hits = sum(1 for rec in records if rec.cache_read_tokens > 0)
        est_inferred = any(
            rec.cache_read_tokens > 0 or rec.cache_write_tokens > 0
            for rec in records
        )
        return AgentUsageSummary(
            agent=agent,
            calls=len(records),
            total_tokens=sum(rec.total() for rec in records),
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cache_hits=cache_hits,
            est_inferred=est_inferred,
        )
