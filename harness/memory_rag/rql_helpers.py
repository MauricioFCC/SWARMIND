"""Helpers de RQL avanzado (Spec ruscadb-rql-advanced)."""

from __future__ import annotations


def cte_sql(cte_name: str, cte_query: str, main_query: str) -> str:
    """Genera RQL con CTE (WITH)."""
    return f"WITH {cte_name} AS ({cte_query}) {main_query}"


def union_sql(q1: str, q2: str) -> str:
    """Genera RQL UNION."""
    return f"{q1} UNION {q2}"


def intersect_sql(q1: str, q2: str) -> str:
    """Genera RQL INTERSECT."""
    return f"{q1} INTERSECT {q2}"


def window_sql(collection: str, func: str, partition_by: str | None = None, order_by: str = "created_at") -> str:
    """Genera RQL con window function."""
    partition = f"PARTITION BY {partition_by} " if partition_by else ""
    return f"SELECT *, {func} OVER ({partition}ORDER BY {order_by}) as w FROM {collection}"


__all__ = ["cte_sql", "intersect_sql", "union_sql", "window_sql"]
