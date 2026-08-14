"""Clase principal ``ShapleyFlow`` para el paquete homonimo.

Extraido mecanicamente de ``shapley_flow.py`` (regla AGR < 500 lineas).
Contiene la API publica (``__init__``, ``allocate``, ``get_stats``,
``get_last_allocation``, ``_shapley_value``) y la funcion de conveniencia
``create_shapley_flow``. Los metodos de calculo se componen via mixins
(``_FeatureExtractionMixin``, ``_ShapleyComputationMixin``,
``_HamiltonAllocationMixin``) para conservar la misma API.
"""
from __future__ import annotations

import logging
import threading
import time
from typing import Any

from .allocation import _HamiltonAllocationMixin
from .compute import _ShapleyComputationMixin
from .constants import MIN_SECTION_TOKENS
from .features import _FeatureExtractionMixin
from .models import ShapleyAllocation

logger = logging.getLogger("harness.memory_rag.shapley_flow")


# ---------------------------------------------------------------------------
# ShapleyFlow
# ---------------------------------------------------------------------------


class ShapleyFlow(
    _FeatureExtractionMixin,
    _ShapleyComputationMixin,
    _HamiltonAllocationMixin,
):
    """Asignacion de tokens basada en Shapley Value.

    WHAT: Calcula el valor de Shapley para cada seccion de un prompt
    y distribuye el presupuesto de tokens proporcionalmente.
    WHY: Las secciones de un prompt contribuyen de forma desigual al
    resultado final; el Shapley Value es la unica metrica que garantiza
    eficiencia, simetria, linealidad y equidad en la distribucion.
    WHERE: Usado en el pipeline de optimizacion de contexto antes de
    enviar el prompt al LLM, despues de recuperar RAG y compilar skills.

    La implementacion usa la formula exacta de Shapley:

        phi_i(v) = sum_{S subseteq N\\{i}}
            (|S|! * (n - |S| - 1)! / n!) *
            (v(S union {i}) - v(S))

    Para n secciones, la complejidad es O(n * 2^n). Para n > 10 se
    activa automaticamente un modo aproximado por muestreo de permutaciones.

    Uso:
        flow = ShapleyFlow(approximate_threshold=10)
        allocs = flow.allocate({"system": "...", "user": "..."}, 4096)
    """

    def __init__(
        self,
        approximate_threshold: int = 10,
        num_permutations: int = 1000,
        default_semantic_density: float = 0.5,
    ) -> None:
        """Inicializa el asignador ShapleyFlow.

        Args:
            approximate_threshold: Numero maximo de secciones para usar
                el calculo exacto. Por encima usa aproximacion Monte Carlo.
                Default: 10.
            num_permutations: Numero de permutaciones para la
                aproximacion Monte Carlo. Default: 1000.
            default_semantic_density: Densidad semantica por defecto
                cuando no se puede calcular. Default: 0.5.

        Raises:
            ValueError: Si approximate_threshold < 2,
                num_permutations < 100, o
                default_semantic_density fuera de [0, 1].
        """
        if approximate_threshold < 2:
            raise ValueError(
                f"WHAT: approximate_threshold={approximate_threshold} < 2. "
                f"WHY: Se necesitan al menos 2 secciones para calcular Shapley. "
                f"WHERE: ShapleyFlow.__init__"
            )
        if num_permutations < 100:
            raise ValueError(
                f"WHAT: num_permutations={num_permutations} < 100. "
                f"WHY: Muy pocas permutaciones producen estimaciones inestables. "
                f"WHERE: ShapleyFlow.__init__"
            )
        if not 0.0 <= default_semantic_density <= 1.0:
            raise ValueError(
                f"WHAT: default_semantic_density={default_semantic_density} "
                f"fuera de [0, 1]. "
                f"WHY: La densidad semantica debe estar normalizada. "
                f"WHERE: ShapleyFlow.__init__"
            )

        self._approximate_threshold = approximate_threshold
        self._num_permutations = num_permutations
        self._default_semantic_density = default_semantic_density
        self._lock = threading.Lock()

        # Estadisticas internas
        self._allocation_count: int = 0
        self._total_sections_processed: int = 0
        self._last_allocation_stats: dict[str, Any] = {}

        logger.info(
            "ShapleyFlow initialized (threshold=%d, permutations=%d)",
            approximate_threshold, num_permutations,
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def allocate(
        self,
        sections: dict[str, str],
        total_budget: int,
    ) -> list[ShapleyAllocation]:
        """Distribuye el presupuesto de tokens entre secciones del prompt.

        WHAT: Calcula el Shapley Value de cada seccion y asigna tokens
        proporcionalmente. Las secciones con mayor valor reciben mas tokens.
        WHY: La asignacion uniforme desperdicia tokens en secciones de
        bajo valor; ShapleyFlow maximiza la eficiencia del presupuesto.
        WHERE: Antes de ensamblar el contexto final para una llamada LLM.

        Args:
            sections: Diccionario {nombre_seccion: texto}. Ejemplo:
                {"system": "...", "user": "...", "rag": "...", "skill": "..."}.
            total_budget: Presupuesto total de tokens a distribuir.
                Debe ser >= 64.

        Returns:
            Lista de ``ShapleyAllocation``, uno por seccion, ordenada por
            valor de Shapley descendente.

        Raises:
            ValueError: Si ``sections`` esta vacio, ``total_budget`` < 64,
                o alguna seccion tiene menos de ``MIN_SECTION_TOKENS`` tokens.
        """
        # --- Validaciones ---
        if not sections:
            raise ValueError(
                "WHAT: sections dict esta vacio. "
                "WHY: No hay secciones para asignar presupuesto. "
                "WHERE: ShapleyFlow.allocate"
            )
        if total_budget < 64:
            raise ValueError(
                f"WHAT: total_budget={total_budget} < 64. "
                f"WHY: El presupuesto minimo para una llamada LLM es 64 tokens. "
                f"WHERE: ShapleyFlow.allocate"
            )

        # --- Extraer caracteristicas ---
        section_names = list(sections.keys())
        features_list = self._extract_features(sections, section_names)

        for feat in features_list:
            if feat.token_count < MIN_SECTION_TOKENS:
                logger.warning(
                    "ShapleyFlow: seccion '%s' tiene solo %d tokens "
                    "(por debajo del minimo %d)",
                    feat.name, feat.token_count, MIN_SECTION_TOKENS,
                )

        # --- Calcular Shapley Values ---
        n = len(features_list)
        if n <= self._approximate_threshold:
            shapley_values = self._compute_exact(features_list)
        else:
            shapley_values = self._compute_approximate(features_list)

        # --- Asignar presupuesto ---
        total_value = sum(shapley_values.values())
        if total_value <= 0.0:
            # Fallback: distribucion uniforme
            logger.warning(
                "ShapleyFlow: suma de valores es cero, usando distribucion uniforme"
            )
            uniform = total_budget // max(n, 1)
            allocations = [
                ShapleyAllocation(
                    section=feat.name,
                    shapley_value=1.0 / max(n, 1),
                    token_budget=uniform,
                    original_tokens=feat.token_count,
                )
                for feat in features_list
            ]
        else:
            # Redondear y ajustar para que sume exactamente total_budget
            raw_budgets: dict[str, float] = {}
            for feat in features_list:
                ratio = shapley_values[feat.name] / total_value
                raw_budgets[feat.name] = ratio * total_budget

            # Asignacion con algoritmo de resto mayor (Hamilton)
            allocations = self._hamilton_allocation(
                features_list, shapley_values, raw_budgets, total_budget,
            )

        # Ordenar por valor descendente
        allocations.sort(key=lambda x: x.shapley_value, reverse=True)

        # Actualizar estadisticas
        with self._lock:
            self._allocation_count += 1
            self._total_sections_processed += len(features_list)
            self._last_allocation_stats = {
                "sections": len(features_list),
                "total_budget": total_budget,
                "exact_mode": n <= self._approximate_threshold,
                "allocations": [
                    {
                        "section": a.section,
                        "shapley_value": round(a.shapley_value, 4),
                        "token_budget": a.token_budget,
                        "original_tokens": a.original_tokens,
                    }
                    for a in allocations
                ],
                "timestamp": time.time(),
            }

        logger.info(
            "ShapleyFlow: %d secciones, %d tokens asignados "
            "(exact=%s, secciones_top=%s valor=%.3f)",
            n, total_budget,
            n <= self._approximate_threshold,
            allocations[0].section if allocations else "N/A",
            allocations[0].shapley_value if allocations else 0.0,
        )

        return allocations

    def get_stats(self) -> dict[str, Any]:
        """Retorna estadisticas de uso del ShapleyFlow.

        Returns:
            Diccionario con: total_allocations, total_sections_processed,
            last_allocation_timestamp, y configuracion actual.
        """
        with self._lock:
            return {
                "total_allocations": self._allocation_count,
                "total_sections_processed": self._total_sections_processed,
                "approximate_threshold": self._approximate_threshold,
                "num_permutations": self._num_permutations,
                "last_allocation": self._last_allocation_stats,
                "timestamp": time.time(),
            }

    def get_last_allocation(self) -> dict[str, Any] | None:
        """Retorna la ultima asignacion realizada (para depuracion).

        Returns:
            Copia del diccionario de la ultima asignacion, o None si
            aun no se ha ejecutado ninguna.
        """
        with self._lock:
            if not self._last_allocation_stats:
                return None
            return dict(self._last_allocation_stats)

    def _shapley_value(
        self,
        section_name: str,
        sections: dict[str, str],
    ) -> float:
        """Calcula el valor de Shapley para una seccion especifica.

        Metodo de conveniencia para consultar el valor de una sola
        seccion sin ejecutar la asignacion completa.

        Args:
            section_name: Nombre de la seccion a evaluar.
            sections: Diccionario completo de secciones.

        Returns:
            Valor de Shapley de la seccion [0, 1].

        Raises:
            ValueError: Si section_name no existe en sections.
        """
        if section_name not in sections:
            raise ValueError(
                f"WHAT: section_name='{section_name}' no encontrada en sections. "
                f"WHY: Solo se puede calcular Shapley para secciones existentes. "
                f"WHERE: ShapleyFlow._shapley_value. "
                f"AVAILABLE: {list(sections.keys())}"
            )

        features = self._extract_features(sections, list(sections.keys()))
        n = len(features)

        # Usar calculo exacto o aproximado segun el tamano
        if n <= self._approximate_threshold:
            all_values = self._compute_exact(features)
        else:
            all_values = self._compute_approximate(features)

        return all_values.get(section_name, 0.0)


# ---------------------------------------------------------------------------
# Funcion de conveniencia (top-level)
# ---------------------------------------------------------------------------


def create_shapley_flow(
    approximate_threshold: int = 10,
    num_permutations: int = 1000,
) -> ShapleyFlow:
    """Crea una instancia de ShapleyFlow con configuracion estandar.

    Args:
        approximate_threshold: Umbral para modo aproximado.
            Default: 10.
        num_permutations: Permutaciones Monte Carlo.
            Default: 1000.

    Returns:
        Instancia configurada de ``ShapleyFlow``.
    """
    return ShapleyFlow(
        approximate_threshold=approximate_threshold,
        num_permutations=num_permutations,
    )
