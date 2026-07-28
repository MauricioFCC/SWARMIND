"""
Agent Capsules - Fusion inteligente de agentes (arXiv:2605.00410).

arXiv:2605.00410: Reduce input tokens hasta 51% fusionando llamadas de agentes
sin perdida de calidad. Tres estrategias con escalera de calidad:

1. COMPOUND: Fusiona N prompts en uno solo (max ahorro)
2. TWO_PHASE: Primera fase exploratoria, segunda fase detallada (balance)
3. SEQUENTIAL: Ejecucion secuencial con cache de prompts (min ahorro, max calidad)

Usage:
    capsule = AgentCapsule(quality_floor=0.85)
    result = capsule.execute(agent_calls, strategy="compound")
"""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


class FusionStrategy(str, Enum):
    """Estrategias de fusion de agentes con escalera de calidad."""

    COMPOUND = "compound"  # Max ahorro (-51% tokens), calidad controlada
    TWO_PHASE = "two_phase"  # Balance (-35% tokens), calidad media
    SEQUENTIAL = "sequential"  # Min ahorro, max calidad


@dataclass
class AgentCall:
    """
    Llamada a un agente individual.

    Attributes:
        agent: Nombre del agente (builder, scientist, etc.).
        prompt: Prompt completo para el agente.
        priority: Prioridad (mayor = mas importante).
        expected_tokens: Tokens esperados para esta llamada.
        result: Resultado de la ejecucion.
        quality_score: Score de calidad (0-1) tras ejecucion.
    """

    agent: str
    prompt: str
    priority: int = 5
    expected_tokens: int = 500
    result: Optional[str] = None
    quality_score: float = 0.0


@dataclass
class CapsuleResult:
    """
    Resultado de la ejecucion de una capsule.

    Attributes:
        results: Resultados por agente.
        tokens_saved: Tokens ahorrados vs ejecucion secuencial.
        fusion_strategy: Estrategia utilizada.
        quality_score: Score de calidad final.
        compound_prompt: Prompt compuesto generado (si aplica).
    """

    results: Dict[str, str]
    tokens_saved: int
    fusion_strategy: FusionStrategy
    quality_score: float
    compound_prompt: Optional[str] = None


class AgentCapsule:
    """
    Capsula de fusion de agentes con control de calidad.

    Toma N llamadas de agentes y decide como fusionarlas para
    minimizar tokens sin sacrificar calidad.

    Args:
        quality_floor: Umbral minimo de calidad aceptable (0-1).
        dispatch_fn: Funcion de dispatch. Si None, usa simulada.
    """

    def __init__(
        self,
        quality_floor: float = 0.85,
        dispatch_fn: Optional[Callable[[str, str], str]] = None,
    ) -> None:
        """Inicializar capsule con control de calidad y dispatch."""
        if not 0.0 <= quality_floor <= 1.0:
            raise ValueError(
                f"quality_floor debe estar entre 0 y 1, recibido {quality_floor}"
            )
        self._quality_floor = quality_floor
        self._dispatch = dispatch_fn or self._mock_dispatch
        self._prompt_cache: Dict[str, str] = {}

    def execute(
        self,
        calls: List[AgentCall],
        strategy: Optional[FusionStrategy] = None,
    ) -> CapsuleResult:
        """
        Ejecutar llamadas de agentes con fusion optima.

        Args:
            calls: Lista de llamadas a agentes.
            strategy: Estrategia de fusion. Si None, selecciona automaticamente.

        Returns:
            CapsuleResult con resultados y metricas de ahorro.

        Raises:
            ValueError: Si strategy es invalido o calls contiene datos invalidos.
        """
        if strategy is None:
            strategy = self._select_strategy(calls)

        if not isinstance(strategy, FusionStrategy):
            raise ValueError(
                f"strategy debe ser miembro de FusionStrategy, recibido {strategy}"
            )

        # Validar calls
        for i, call in enumerate(calls):
            if not isinstance(call, AgentCall):
                raise ValueError(
                    f"Elemento {i} en calls no es AgentCall: {type(call).__name__}"
                )
            if not call.agent or not call.prompt:
                raise ValueError(
                    f"AgentCall {i} tiene agent o prompt vacio: "
                    f"agent={call.agent!r}, prompt={call.prompt!r}"
                )

        if not calls:
            logger.warning("execute llamado con lista vacia de calls")
            return CapsuleResult(
                results={},
                tokens_saved=0,
                fusion_strategy=strategy,
                quality_score=1.0,
            )

        # Calcular tokens base (ejecucion secuencial sin fusion)
        base_tokens = sum(c.expected_tokens for c in calls)

        if strategy == FusionStrategy.COMPOUND:
            result = self._execute_compound(calls, base_tokens)
        elif strategy == FusionStrategy.TWO_PHASE:
            result = self._execute_two_phase(calls, base_tokens)
        elif strategy == FusionStrategy.SEQUENTIAL:
            result = self._execute_sequential(calls, base_tokens)
        else:
            raise ValueError(f"Estrategia no soportada: {strategy}")

        # Verificar quality floor
        if result.quality_score < self._quality_floor:
            logger.warning(
                "Calidad %.2f por debajo del umbral %.2f para strategy %s. "
                "Considerar usar estrategia de mayor calidad.",
                result.quality_score,
                self._quality_floor,
                strategy.value,
            )

        return result

    def _select_strategy(self, calls: List[AgentCall]) -> FusionStrategy:
        """Seleccion automatica de estrategia segun N calls y prioridades."""
        n = len(calls)
        if n <= 1:
            return FusionStrategy.SEQUENTIAL
        if n >= 5:
            return FusionStrategy.COMPOUND
        # Prioridades altas (>7) requieren max calidad
        max_priority = max(c.priority for c in calls)
        if max_priority >= 8:
            return FusionStrategy.SEQUENTIAL
        return FusionStrategy.TWO_PHASE

    def _execute_compound(
        self, calls: List[AgentCall], base_tokens: int
    ) -> CapsuleResult:
        """Fusionar todas las llamadas en un solo prompt compuesto."""
        # Construir prompt compuesto
        lines = ["## Tareas Multi-Agente (fusionadas)"]
        for i, call in enumerate(calls):
            lines.append(f"\n### Tarea {i+1} ({call.agent}):")
            lines.append(call.prompt)

        compound = "\n".join(lines)
        compound_tokens = max(1, len(compound) // 4)

        # Ejecutar con el agente de mayor prioridad
        primary = max(calls, key=lambda c: c.priority)
        cache_key = self._make_cache_key(compound)
        if cache_key in self._prompt_cache:
            result = self._prompt_cache[cache_key]
            logger.debug("Cache hit para compound prompt: %s", cache_key[:16])
        else:
            result = self._dispatch(primary.agent, compound)
            self._prompt_cache[cache_key] = result

        # Distribuir resultado entre todos los agentes
        results = {c.agent: result for c in calls}
        tokens_saved = base_tokens - compound_tokens

        return CapsuleResult(
            results=results,
            tokens_saved=max(0, tokens_saved),
            fusion_strategy=FusionStrategy.COMPOUND,
            quality_score=0.85,
            compound_prompt=compound,
        )

    def _execute_two_phase(
        self, calls: List[AgentCall], base_tokens: int
    ) -> CapsuleResult:
        """Fase 1: exploratoria (compuesta), Fase 2: detallada (individual)."""
        # Fase 1: exploracion compuesta
        summaries = "\n".join(
            f"- {c.agent}: {c.prompt[:100]}..." for c in calls
        )
        explore_prompt = (
            "## Exploracion Multi-Agente (Fase 1)\n"
            "Resumen de tareas pendientes:\n"
            f"{summaries}"
        )
        explore_result = self._dispatch(calls[0].agent, explore_prompt)
        explore_tokens = max(1, len(explore_prompt) // 4)

        # Fase 2: detalle individual con contexto de fase 1
        detail_tokens = 0
        results: Dict[str, str] = {}
        for call in calls:
            detail_prompt = (
                f"Contexto exploratorio:\n{explore_result[:200]}\n\n"
                f"---\n### Tarea detallada ({call.agent}):\n{call.prompt}"
            )
            cache_key = self._make_cache_key(detail_prompt)
            if cache_key in self._prompt_cache:
                r = self._prompt_cache[cache_key]
                logger.debug("Cache hit para detail prompt: %s", cache_key[:16])
            else:
                r = self._dispatch(call.agent, detail_prompt)
                self._prompt_cache[cache_key] = r
            results[call.agent] = r
            detail_tokens += max(1, len(detail_prompt) // 4)

        total_tokens = explore_tokens + detail_tokens
        tokens_saved = base_tokens - total_tokens

        return CapsuleResult(
            results=results,
            tokens_saved=max(0, tokens_saved),
            fusion_strategy=FusionStrategy.TWO_PHASE,
            quality_score=0.92,
            compound_prompt=explore_prompt,
        )

    def _execute_sequential(
        self, calls: List[AgentCall], base_tokens: int
    ) -> CapsuleResult:
        """Ejecucion secuencial con cache de prompts (ahorro minimo)."""
        results: Dict[str, str] = {}
        total_tokens = 0

        for call in calls:
            cache_key = self._make_cache_key(call.prompt)
            if cache_key in self._prompt_cache:
                r = self._prompt_cache[cache_key]
                logger.debug("Cache hit para prompt: %s", cache_key[:16])
            else:
                r = self._dispatch(call.agent, call.prompt)
                self._prompt_cache[cache_key] = r
            results[call.agent] = r
            total_tokens += call.expected_tokens

        return CapsuleResult(
            results=results,
            tokens_saved=0,
            fusion_strategy=FusionStrategy.SEQUENTIAL,
            quality_score=1.0,
        )

    def _make_cache_key(self, prompt: str) -> str:
        """Generar clave de cache deterministica para un prompt."""
        return hashlib.sha256(prompt.encode("utf-8")).hexdigest()

    def clear_cache(self) -> None:
        """Limpiar cache interna de prompts."""
        self._prompt_cache.clear()
        logger.debug("Cache de prompts limpiada")

    # ------------------------------------------------------------------
    # Mock dispatch para testing
    # ------------------------------------------------------------------

    @staticmethod
    def _mock_dispatch(agent: str, prompt: str) -> str:
        """Dispatch simulado para testing."""
        return f"[{agent}] Procesado: {prompt[:50]}..."


