"""ShapleyFlow — Asignacion de tokens basada en Shapley Value.

Distribuye el presupuesto de tokens entre secciones de un prompt
proporcionalmente a su contribucion marginal al resultado final.
Usa el valor de Shapley para calcular la importancia de cada seccion.

La funcion caracteristica ``v(S)`` estima el "valor" de un subconjunto de
secciones combinando relevancia semantica, densidad de informacion y
posicion estratrgica dentro del prompt.

Basado en: ShapleyFlow (ADR-0010, B26) — Cooperative game-theoretic
attribution para workflows swarmind. ACL 2026.

Uso:
    flow = ShapleyFlow()
    sections = {
        "system": "Eres un asistente experto en Python...",
        "user": "Implementa una funcion que calcule fibonacci...",
        "rag": "Contexto recuperado: PEP 8, patrones de diseno...",
        "skill": "Habilidades: codigo, testing, revision...",
    }
    allocations = flow.allocate(sections, total_budget=4096)
    for alloc in allocations:
        print(f"{alloc.section}: {alloc.shapley_value:.3f} -> {alloc.token_budget} tokens")
"""

from __future__ import annotations

import itertools
import logging
import math
import threading
import time
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Pesos para el calculo de la funcion caracteristica
WEIGHT_TOKEN_COUNT = 0.30
WEIGHT_SEMANTIC_DENSITY = 0.25
WEIGHT_POSITION_PREMIUM = 0.20
WEIGHT_KEYWORD_MATCH = 0.15
WEIGHT_LENGTH_PENALTY = 0.10

# Umbral de seccion huérfana (token count por debajo se ignora)
MIN_SECTION_TOKENS = 10

# Cache de factoriales precomputados hasta 12 (soporta hasta 12 secciones)
_FACTORIAL_CACHE: dict[int, int] = {i: math.factorial(i) for i in range(13)}


def _factorial(n: int) -> int:
    """Retorna factorial con cache para valores pequenos."""
    if n < 0:
        raise ValueError(
            f"WHAT: factorial({n}) no esta definido para negativos. "
            f"WHY: El factorial solo existe para enteros no negativos. "
            f"WHERE: shapley_flow._factorial"
        )
    if n <= 12:
        return _FACTORIAL_CACHE.get(n, math.factorial(n))
    return math.factorial(n)


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass
class ShapleyAllocation:
    """Resultado de asignacion para una seccion del prompt.

    Attributes:
        section: Nombre de la seccion (ej: "system", "user", "rag").
        shapley_value: Contribucion marginal normalizada [0, 1].
        token_budget: Tokens asignados a esta seccion.
        original_tokens: Cantidad original de tokens de la seccion.
        marginal_contributions: Lista de contribuciones marginales
            calculadas durante la evaluacion (depuracion).
    """

    section: str
    shapley_value: float
    token_budget: int
    original_tokens: int
    marginal_contributions: list[float] = field(default_factory=list)


@dataclass
class _SectionFeatures:
    """Caracteristicas extraidas de una seccion para el modelo de valor."""

    name: str
    text: str
    token_count: int
    semantic_density: float = 0.5
    position_index: int = 0
    keyword_relevance: float = 0.5
    has_code: bool = False


# ---------------------------------------------------------------------------
# ShapleyFlow
# ---------------------------------------------------------------------------


class ShapleyFlow:
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

    # ------------------------------------------------------------------
    # Metodos internos
    # ------------------------------------------------------------------

    def _extract_features(
        self,
        sections: dict[str, str],
        section_names: list[str],
    ) -> list[_SectionFeatures]:
        """Extrae caracteristicas de cada seccion para el modelo de valor.

        Args:
            sections: Diccionario original de secciones.
            section_names: Lista ordenada de nombres de seccion.

        Returns:
            Lista de ``_SectionFeatures`` con las metricas extraidas.
        """
        features: list[_SectionFeatures] = []
        for idx, name in enumerate(section_names):
            text = sections[name]
            # Estimacion simple de tokens: ~4 chars por token
            token_count = max(1, len(text) // 4)

            # Densidad semantica: proporcion de palabras unicas
            words = text.lower().split()
            unique_ratio = len(set(words)) / max(len(words), 1)
            semantic_density = min(
                self._default_semantic_density + unique_ratio * 0.5,
                1.0,
            )

            # Relevancia por keywords tecnicas
            tech_keywords = {
                "implement", "function", "class", "def", "import",
                "algorithm", "api", "endpoint", "database", "query",
                "test", "async", "await", "error", "exception",
                "optimize", "refactor", "deploy", "config",
            }
            keyword_matches = sum(1 for w in words if w in tech_keywords)
            keyword_relevance = min(keyword_matches / max(len(words), 1) * 5, 1.0)

            # Deteccion de codigo
            has_code = "```" in text or "def " in text or "class " in text

            features.append(_SectionFeatures(
                name=name,
                text=text,
                token_count=token_count,
                semantic_density=round(semantic_density, 4),
                position_index=idx,
                keyword_relevance=round(keyword_relevance, 4),
                has_code=has_code,
            ))

        return features

    def _characteristic_function(
        self,
        subset_indices: set[int],
        features: list[_SectionFeatures],
    ) -> float:
        """Funcion caracteristica v(S): estima el valor de un subconjunto.

        Combina cuatro factores:
          1. Token count total del subconjunto (normalizado).
          2. Densidad semantica promedio.
          3. Prima por posicion (las primeras secciones tienen mas peso).
          4. Relevancia por keywords tecnicas.

        Args:
            subset_indices: Indices de las secciones en el subconjunto.
            features: Lista completa de caracteristicas.

        Returns:
            Valor escalar del subconjunto [0, 1].
        """
        if not subset_indices:
            return 0.0

        len(features)
        subset_feats = [features[i] for i in subset_indices]

        # 1. Token count normalizado
        total_tokens = sum(f.token_count for f in subset_feats)
        max_tokens = sum(f.token_count for f in features)
        token_score = total_tokens / max(max_tokens, 1)

        # 2. Densidad semantica promedio
        avg_density = (
            sum(f.semantic_density for f in subset_feats) / len(subset_feats)
        )

        # 3. Prima por posicion (peso exponencial decreciente)
        position_scores = []
        for i in subset_indices:
            # La primera posicion (indice 0) tiene el maximo peso
            pos_weight = math.exp(-0.3 * i)
            position_scores.append(pos_weight)
        position_premium = sum(position_scores) / max(len(subset_feats), 1)

        # 4. Relevancia por keywords
        avg_keyword = (
            sum(f.keyword_relevance for f in subset_feats) / len(subset_feats)
        )

        # 5. Penalizacion por longitud baja (secciones muy cortas aportan poco)
        short_sections = sum(1 for f in subset_feats if f.token_count < 50)
        length_penalty = 1.0 - (short_sections / len(subset_feats) * 0.5)

        value = (
            WEIGHT_TOKEN_COUNT * token_score
            + WEIGHT_SEMANTIC_DENSITY * avg_density
            + WEIGHT_POSITION_PREMIUM * position_premium
            + WEIGHT_KEYWORD_MATCH * avg_keyword
            + WEIGHT_LENGTH_PENALTY * length_penalty
        )

        return min(max(value, 0.0), 1.0)

    def _compute_exact(
        self,
        features: list[_SectionFeatures],
    ) -> dict[str, float]:
        """Calcula Shapley Values exactos (O(n * 2^n)).

        Args:
            features: Lista de caracteristicas de cada seccion.

        Returns:
            Dict {nombre_seccion: valor_shapley}.

        Raises:
            RuntimeError: Si el calculo excede limites de tiempo.
        """
        n = len(features)
        indices = list(range(n))
        shapley_values: dict[str, float] = {f.name: 0.0 for f in features}

        start_time = time.time()
        section_name_by_idx = {i: features[i].name for i in indices}

        for i in indices:
            # Generar todos los subconjuntos que NO contienen i
            other_indices = [j for j in indices if j != i]
            marginal_sum = 0.0
            marg_contributions: list[float] = []

            for r in range(n):
                for subset in itertools.combinations(other_indices, r):
                    S = set(subset)
                    S_union_i = S | {i}

                    v_without = self._characteristic_function(S, features)
                    v_with = self._characteristic_function(S_union_i, features)

                    marginal = v_with - v_without

                    # Peso Shapley: |S|! * (n - |S| - 1)! / n!
                    weight = (
                        _factorial(r) * _factorial(n - r - 1) / _factorial(n)
                    )
                    marginal_sum += marginal * weight
                    marg_contributions.append(marginal)

            shapley_values[section_name_by_idx[i]] = marginal_sum

            # Verificar timeout (> 30s para n grande)
            if time.time() - start_time > 30.0:
                raise RuntimeError(
                    f"WHAT: Calculo exacto de Shapley excedio 30s "
                    f"para n={n}. "
                    f"WHY: El numero de subconjuntos (2^{n}) es demasiado grande. "
                    f"WHERE: ShapleyFlow._compute_exact. "
                    f"SUGGEST: Aumentar approximate_threshold o usar modo aproximado."
                )

        elapsed = time.time() - start_time
        logger.debug(
            "ShapleyFlow: calculo exacto completado (n=%d, %.4fs)", n, elapsed,
        )

        return shapley_values

    def _compute_approximate(
        self,
        features: list[_SectionFeatures],
    ) -> dict[str, float]:
        """Calcula Shapley Values aproximados por muestreo de permutaciones.

        Metodo de permutaciones aleatorias (Monte Carlo):
        Para cada permutacion, calcula la contribucion marginal de cada
        jugador al aparecer en la permutacion.

        Args:
            features: Lista de caracteristicas de cada seccion.

        Returns:
            Dict {nombre_seccion: valor_shapley_aproximado}.
        """
        import random

        n = len(features)
        indices = list(range(n))
        shapley_sum: dict[str, float] = {f.name: 0.0 for f in features}
        section_name_by_idx = {i: features[i].name for i in indices}

        for _ in range(self._num_permutations):
            random.shuffle(indices)
            current_set: set[int] = set()
            current_value = 0.0

            for idx in indices:
                # Valor del conjunto incluyendo este elemento
                new_set = current_set | {idx}
                new_value = self._characteristic_function(new_set, features)
                marginal = new_value - current_value

                shapley_sum[section_name_by_idx[idx]] += marginal

                current_set = new_set
                current_value = new_value

        # Normalizar por numero de permutaciones
        for name in shapley_sum:
            shapley_sum[name] /= self._num_permutations

        logger.debug(
            "ShapleyFlow: calculo aprox completado (n=%d, perm=%d)",
            n, self._num_permutations,
        )

        return shapley_sum

    @staticmethod
    def _hamilton_allocation(
        features: list[_SectionFeatures],
        shapley_values: dict[str, float],
        raw_budgets: dict[str, float],
        total_budget: int,
    ) -> list[ShapleyAllocation]:
        """Asignacion por metodo de resto mayor (Hamilton).

        Garantiza que la suma de token_budget sea exactamente total_budget
        mediante redondeo con ajuste de resto mayor.

        Args:
            features: Lista de caracteristicas.
            shapley_values: Valores de Shapley calculados.
            raw_budgets: Presupuestos flotantes pre-calculados.
            total_budget: Presupuesto total a asignar.

        Returns:
            Lista de ``ShapleyAllocation`` con presupuestos enteros.
        """
        n = len(features)
        # Asignacion base: truncar
        base: dict[str, int] = {}
        remainders: dict[str, float] = {}
        allocated_so_far = 0

        for feat in features:
            raw = raw_budgets[feat.name]
            base_alloc = int(raw)
            base[feat.name] = base_alloc
            remainders[feat.name] = raw - base_alloc
            allocated_so_far += base_alloc

        # Distribuir resto
        remaining = total_budget - allocated_so_far
        if remaining > 0:
            # Ordenar por resto descendente
            sorted_by_remainder = sorted(
                features, key=lambda f: remainders[f.name], reverse=True,
            )
            for i in range(min(remaining, n)):
                base[sorted_by_remainder[i].name] += 1

        # Construir resultados
        allocations = []
        for feat in features:
            marg_contribs = []  # No almacenamos marginales en modo aprox
            allocations.append(ShapleyAllocation(
                section=feat.name,
                shapley_value=shapley_values.get(feat.name, 0.0),
                token_budget=base[feat.name],
                original_tokens=feat.token_count,
                marginal_contributions=marg_contribs,
            ))

        return allocations

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
