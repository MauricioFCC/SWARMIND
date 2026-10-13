"""pipeline_router.py — cascada de frontera: triage barato -> frontier (FR-1).

WHAT: integra ``TriageSLM`` (clasificador SLM barato) como PRIMERA etapa del
pipeline real, decide el ``PipelineType`` en una cascada estilo RouteLLM
(clasificador barato -> frontier solo si hace falta), consulta el
``DifficultyRouter`` heuristico SOLO en el caso "timido" (complexity == 3),
ensambla el prompt cache-shaped (FR-A2) y registra telemetria de tokens
(FR-A1/FR-3). WHY: el routing aprendido debe ejecutarse en el pipeline real,
no quedar standalone; la cascada reserva frontier para lo complejo y mide el
ahorro de cache con evidencia. WHERE: coordinator / orquestador, por encima de
``TriageSLM`` y ``DifficultyRouter`` (ADR-0103).

Cascada (frontera 2026, STEER/cascade):
    complexity <= 2  -> small (SHALLOW): prompt minimo, modelo barato.
    complexity == 3  -> "timido": desempata el ``DifficultyRouter`` heuristico
                        (source="fallback").
    complexity >= 4  -> frontier (DEEP): prompt completo tools+system+static+dynamic.

NF-3: ``route`` nunca lanza; ante cualquier fallo cae a la heuristica.

Uso:
    router = PipelineRouter()
    decision = router.route("integrar API REST con Docker")
    # decision.pipeline, decision.complexity, decision.source,
    # decision.intent, decision.prompt_blocks, decision.telemetry
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Literal

from harness.observability.token_telemetry import (
    MIN_HIT_RATE,
    TelemetryGate,
    TokenTelemetry,
)
from harness.orchestrator.difficulty_router import (
    ComplexityLevel,
    DifficultyRouter,
    PipelineType,
)
from harness.orchestrator.prompt_cache_shape import (
    ORDER,
    STABLE_KINDS,
    PromptBlock,
    build_cache_shaped_prompt,
)
from harness.orchestrator.triage_slm import TriageSLM

logger = logging.getLogger(__name__)

#: Complejidad maxima tratada como "small" (trivial/simple) -> pipeline SHALLOW.
SMALL_COMPLEXITY = 2
#: Complejidad "timida" que dispara el desempate heuristico -> source="fallback".
TENTATIVE_COMPLEXITY = 3
#: Complejidad minima tratada como "frontier" (compleja) -> pipeline DEEP.
FRONTIER_COMPLEXITY = 4

#: Tokens de salida fijos por decision de ruteo (telemetria: 1 decision).
TELEMETRY_OUTPUT_TOKENS = 1

#: Rol con el que ``PipelineRouter`` registra su uso de tokens.
ROUTER_ROLE = "router"

#: Origen de la decision de ruteo: SLM barato o heuristica de respaldo.
RoutingSource = Literal["slm", "fallback"]

#: Traduccion ``ComplexityLevel`` (heuristica) -> escala 1..5 del pipeline.
_LEVEL_TO_INT: dict[ComplexityLevel, int] = {
    ComplexityLevel.TRIVIAL: 1,
    ComplexityLevel.SIMPLE: 2,
    ComplexityLevel.MODERATE: 3,
    ComplexityLevel.COMPLEX: 4,
    ComplexityLevel.VERY_COMPLEX: 5,
}

#: Contenido de los bloques estables del prompt (prefijo cacheable).
_TOOLS_BLOCK = "tools: [dispatch, plan, execute, delegate]"
_SYSTEM_BLOCK = "system: coordinador SWARMIND (fan-out + votacion gobernada)"
_STATIC_BLOCK = "static: doctrina base (RSF, IDP, ERR, ARQ, SEG, TKN)"


@dataclass(frozen=True)
class RoutingDecision:
    """Decision inmutable de ruteo del pipeline (IMM: frozen dataclass).

    Attributes:
        pipeline: Pipeline seleccionado por la cascada.
        complexity: Complejidad final en la escala 1..5.
        source: Origen de la decision: ``"slm"`` (triage) o ``"fallback"``
            (heuristica ``DifficultyRouter``).
        intent: Intencion detectada por el triage (no vacia cuando aplica).
        prompt_blocks: Bloques del prompt en orden canonico
            (tools -> system -> static -> dynamic), como dicts serializables.
        telemetry: Reporte de ``TokenTelemetry`` tras registrar el uso.
    """

    pipeline: PipelineType
    complexity: int
    source: RoutingSource
    intent: str
    prompt_blocks: list[dict] = field(default_factory=list)
    telemetry: dict = field(default_factory=dict)


def _order_blocks(blocks: list[PromptBlock]) -> list[PromptBlock]:
    """Ordena los bloques al orden canonico de ``prompt_cache_shape``.

    Args:
        blocks: Bloques en cualquier orden.

    Returns:
        Nueva lista ordenada por ``(indice_de_kind, priority)``.
    """
    return sorted(blocks, key=lambda block: (ORDER.index(block.kind), block.priority))


def _blocks_for_pipeline(pipeline: PipelineType, text: str) -> list[PromptBlock]:
    """Selecciona los bloques del prompt segun el pipeline.

    WHAT: small -> bloques minimales (system+dynamic); standard -> system+static
    +dynamic; frontier -> prompt completo (tools+system+static+dynamic). WHY: el
    costo debe escalar con la complejidad; reservar tools/static para lo
    complejo evita inflar el contexto de tareas triviales (TKN).

    Args:
        pipeline: Pipeline seleccionado.
        text: Tarea del turno (bloque dinamico).

    Returns:
        Lista de ``PromptBlock`` (sin ordenar; el orden se aplica al final).
    """
    dynamic = PromptBlock(kind="dynamic", content=text)
    system = PromptBlock(kind="system", content=_SYSTEM_BLOCK)
    if pipeline is PipelineType.SHALLOW:
        return [system, dynamic]
    if pipeline is PipelineType.DEEP:
        return [
            PromptBlock(kind="tools", content=_TOOLS_BLOCK),
            system,
            PromptBlock(kind="static", content=_STATIC_BLOCK),
            dynamic,
        ]
    return [system, PromptBlock(kind="static", content=_STATIC_BLOCK), dynamic]


class PipelineRouter:
    """Cascada de frontera que integra triage SLM + heuristica + telemetria.

    Uso:
        router = PipelineRouter()
        decision = router.route("implementar API REST")
        if decision.pipeline is PipelineType.DEEP:
            ...  # frontier

    Args:
        triage: Clasificador de primera etapa; por defecto ``TriageSLM()``
            (sin ``small_model_callable``, delega en el fallback determinista).
        fallback_router: Heuristico de desempate; por defecto ``DifficultyRouter()``.
        telemetry: Acumulador de tokens; por defecto ``TokenTelemetry()``.
        cache_shaper: Ensamblador de prompt; por defecto
            ``build_cache_shaped_prompt`` (cache-shape canonico).
    """

    def __init__(
        self,
        *,
        triage: TriageSLM | None = None,
        fallback_router: DifficultyRouter | None = None,
        telemetry: TokenTelemetry | None = None,
        cache_shaper: Callable[[list[PromptBlock]], str] | None = None,
    ) -> None:
        """Inicializa la cascada con inyeccion de dependencias (keyword-only).

        Args:
            triage: Primera etapa (SLM barato). ``None`` -> ``TriageSLM()``.
            fallback_router: Desempate heuristico. ``None`` -> ``DifficultyRouter()``.
            telemetry: Telemetria de tokens. ``None`` -> ``TokenTelemetry()``.
            cache_shaper: Ensamblador cache-shaped. ``None`` ->
                ``build_cache_shaped_prompt``.
        """
        self._triage = triage if triage is not None else TriageSLM()
        self._fallback_router = (
            fallback_router if fallback_router is not None else DifficultyRouter()
        )
        self._telemetry = telemetry if telemetry is not None else TokenTelemetry()
        self._cache_shaper = (
            cache_shaper if cache_shaper is not None else build_cache_shaped_prompt
        )
        self._gate = TelemetryGate(threshold=MIN_HIT_RATE)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def route(self, text: str) -> RoutingDecision:
        """Clasifica ``text`` y devuelve la decision de ruteo (nunca lanza).

        Cascada: ``complexity <= 2`` -> small; ``complexity >= 4`` -> frontier;
        ``complexity == 3`` -> desempate por ``fallback_router``
        (``source="fallback"``). Ante fallo del triage, cae directo al fallback.

        Args:
            text: Tarea del usuario (puede ser vacia).

        Returns:
            ``RoutingDecision`` con pipeline, complejidad, fuente, intent,
            bloques de prompt en orden canonico y reporte de telemetria.
        """
        try:
            triage_result = self._triage.triage(text)
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "pipeline_router: WHAT: el triage SLM fallo: %s. "
                "WHY: excepcion/timeout del clasificador de primera etapa. "
                "WHERE: PipelineRouter.route -> fallback directo",
                exc,
            )
            return self._route_via_fallback(text, reason="triage_error")

        complexity = int(triage_result.complexity)
        intent = str(triage_result.intent)

        if complexity <= SMALL_COMPLEXITY:
            return self._finalize(
                text,
                PipelineType.SHALLOW,
                complexity,
                intent,
                "slm",
            )
        if complexity >= FRONTIER_COMPLEXITY:
            return self._finalize(
                text,
                PipelineType.DEEP,
                complexity,
                intent,
                "slm",
            )
        # Caso "timido" (== TENTATIVE_COMPLEXITY): desempate heuristico.
        return self._route_via_fallback(
            text,
            reason="tentative",
            intent=intent,
            complexity=complexity,
        )

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _route_via_fallback(
        self,
        text: str,
        *,
        reason: str,
        intent: str = "",
        complexity: int = TENTATIVE_COMPLEXITY,
    ) -> RoutingDecision:
        """Resuelve el ruteo con el ``DifficultyRouter`` (nunca lanza).

        Args:
            text: Tarea del usuario.
            reason: Motivo del desempate (``"tentative"`` o ``"triage_error"``),
                solo para trazabilidad en logs.
            intent: Intencion conocida del triage (si la hubo).
            complexity: Complejidad de reserva si el fallback no clasifica.

        Returns:
            ``RoutingDecision`` con ``source="fallback"``. Si el fallback
            heuristico tambien falla, devuelve una decision STANDARD valida.
        """
        pipeline = PipelineType.STANDARD
        resolved_complexity = complexity
        resolved_intent = intent
        try:
            fallback_decision = self._fallback_router.route(text)
            candidate_pipeline = getattr(fallback_decision, "pipeline", None)
            if isinstance(candidate_pipeline, PipelineType):
                pipeline = candidate_pipeline
            level = getattr(fallback_decision, "complexity", None)
            resolved_complexity = _LEVEL_TO_INT.get(level, complexity)
            if not resolved_intent and isinstance(level, ComplexityLevel):
                resolved_intent = level.value
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "pipeline_router: WHAT: fallback DifficultyRouter fallo (%s): %s. "
                "WHY: heuristica no disponible o entrada invalida. "
                "WHERE: PipelineRouter._route_via_fallback",
                reason,
                exc,
            )
        return self._finalize(
            text,
            pipeline,
            resolved_complexity,
            resolved_intent,
            "fallback",
        )

    def _finalize(
        self,
        text: str,
        pipeline: PipelineType,
        complexity: int,
        intent: str,
        source: RoutingSource,
    ) -> RoutingDecision:
        """Ensambla el prompt, registra telemetria y construye la decision.

        Args:
            text: Tarea del usuario (bloque dinamico).
            pipeline: Pipeline seleccionado.
            complexity: Complejidad final 1..5.
            intent: Intencion detectada (puede ser vacia).
            source: Origen de la decision (``"slm"``/``"fallback"``).

        Returns:
            ``RoutingDecision`` inmutable con bloques ordenados y telemetria.
        """
        ordered = _order_blocks(_blocks_for_pipeline(pipeline, text))
        prompt = self._cache_shaper(ordered)
        cached_blocks = sum(1 for block in ordered if block.kind in STABLE_KINDS)
        dynamic_blocks = sum(1 for block in ordered if block.kind == "dynamic")

        self._record_router_usage(cached_blocks, dynamic_blocks)
        self._warn_if_cache_buster()

        report = self._safe_report()
        report["cache_shaped_chars"] = len(prompt)
        return RoutingDecision(
            pipeline=pipeline,
            complexity=complexity,
            source=source,
            intent=intent,
            prompt_blocks=[
                {"kind": block.kind, "content": block.content, "priority": block.priority}
                for block in ordered
            ],
            telemetry=report,
        )

    def _record_router_usage(self, cached_blocks: int, dynamic_blocks: int) -> None:
        """Registra el uso de tokens del router en la telemetria (best-effort).

        Args:
            cached_blocks: Numero de bloques estables (prefijo cacheable).
            dynamic_blocks: Numero de bloques dinamicos del turno.
        """
        try:
            self._telemetry.record_usage(
                ROUTER_ROLE,
                cached=cached_blocks,
                input=dynamic_blocks,
                output=TELEMETRY_OUTPUT_TOKENS,
            )
        except (ValueError, TypeError) as exc:
            logger.warning(
                "pipeline_router: WHAT: no se pudo registrar telemetria: %s. "
                "WHY: conteo invalido o rol vacio. "
                "WHERE: PipelineRouter._record_router_usage",
                exc,
            )

    def _warn_if_cache_buster(self) -> None:
        """Loggea un warning si el hit-rate no alcanza el umbral (no bloquea)."""
        try:
            ok, message = self._gate.check(self._telemetry)
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "pipeline_router: WHAT: gate de telemetria no evaluable: %s. "
                "WHY: telemetria inconsistente. "
                "WHERE: PipelineRouter._warn_if_cache_buster",
                exc,
            )
            return
        if not ok:
            logger.warning(
                "pipeline_router: WHAT: %s. WHY: cache-shape suboptimo. "
                "WHERE: PipelineRouter.route",
                message,
            )

    def _safe_report(self) -> dict:
        """Obtiene el reporte de telemetria de forma defensiva.

        Returns:
            Copia del reporte si es un dict; dict vacio ante cualquier fallo.
        """
        try:
            report = self._telemetry.report()
        except Exception:  # noqa: BLE001
            return {}
        return dict(report) if isinstance(report, dict) else {}


__all__ = [
    "FRONTIER_COMPLEXITY",
    "ROUTER_ROLE",
    "SMALL_COMPLEXITY",
    "TELEMETRY_OUTPUT_TOKENS",
    "TENTATIVE_COMPLEXITY",
    "PipelineRouter",
    "RoutingDecision",
    "RoutingSource",
]
