"""Mixin de asignacion Hamilton para ``ShapleyFlow``.

Extraido mecanicamente de ``shapley_flow.py`` (regla AGR < 500 lineas).
Contiene ``_hamilton_allocation``, que convierte los presupuestos
flotantes en enteros que suman exactamente ``total_budget`` mediante el
metodo de resto mayor.
"""
from __future__ import annotations

from .models import ShapleyAllocation, _SectionFeatures


class _HamiltonAllocationMixin:
    """Asignacion de presupuesto por metodo de resto mayor (Hamilton)."""

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
