"""Mixin de calculo Shapley para ``ShapleyFlow``.

Extraido mecanicamente de ``shapley_flow.py`` (regla AGR < 500 lineas).
Contiene la funcion caracteristica ``_characteristic_function`` y los
dos modos de calculo: exacto (O(n * 2^n)) y aproximado por muestreo de
permutaciones (Monte Carlo).
"""
from __future__ import annotations

import itertools
import logging
import math
import time

from .constants import (
    WEIGHT_KEYWORD_MATCH,
    WEIGHT_LENGTH_PENALTY,
    WEIGHT_POSITION_PREMIUM,
    WEIGHT_SEMANTIC_DENSITY,
    WEIGHT_TOKEN_COUNT,
    _factorial,
)
from .models import _SectionFeatures

logger = logging.getLogger("harness.memory_rag.shapley_flow")


class _ShapleyComputationMixin:
    """Funcion caracteristica y calculo de Shapley Values."""

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
