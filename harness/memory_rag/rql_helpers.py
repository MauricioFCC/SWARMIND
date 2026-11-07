"""Helpers de RQL avanzado (Spec ruscadb-rql-advanced).

Como la API es publica, los nombres de CTE, colecciones, columnas y funciones
de ventana se validan antes de interpolarlos en el RQL.
"""

from __future__ import annotations

import re

_IDENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_WINDOW_CALL = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)\((\*|[A-Za-z_][A-Za-z0-9_]*)?\)$")
_WINDOW_NAMES = frozenset(
    {
        "AVG",
        "COUNT",
        "DENSE_RANK",
        "LAG",
        "LEAD",
        "MAX",
        "MIN",
        "RANK",
        "ROW_NUMBER",
        "SUM",
    }
)


def _ident(name: str, field: str) -> str:
    """Valida un identificador RQL.

    Args:
        name: Identificador recibido.
        field: Nombre del parametro, para el mensaje de error.

    Returns:
        El identificador sin cambios si es valido.

    Raises:
        ValueError: si no cumple ``[A-Za-z_][A-Za-z0-9_]*``.
    """
    if not isinstance(name, str) or not _IDENT.match(name):
        raise ValueError(f"{field} invalido para RQL: {name!r}")
    return name


def _window_function(func: str) -> str:
    """Valida una funcion de ventana con argumento opcional.

    Args:
        func: Expresion recibida (``ROW_NUMBER()``, ``SUM(value)``...).

    Returns:
        Funcion normalizada en mayusculas.

    Raises:
        ValueError: si la funcion no esta permitida.
    """
    match = _WINDOW_CALL.fullmatch(func.strip()) if isinstance(func, str) else None
    if not match or match.group(1).upper() not in _WINDOW_NAMES:
        raise ValueError(f"funcion de ventana no permitida: {func!r}")
    return func.strip()


def cte_sql(cte_name: str, cte_query: str, main_query: str) -> str:
    """Genera RQL con CTE (``WITH``).

    Args:
        cte_name: Nombre del CTE (identificador validado).
        cte_query: Subconsulta del CTE (RQL del caller).
        main_query: Consulta principal (RQL del caller).

    Returns:
        RQL con la clausula ``WITH``.
    """
    name = _ident(cte_name, "cte_name")
    # nosec B608: name viene de _ident; cte_query/main_query son RQL del caller.
    return f"WITH {name} AS ({cte_query}) {main_query}"


def union_sql(q1: str, q2: str) -> str:
    """Genera RQL ``UNION``.

    Args:
        q1: Primera consulta RQL.
        q2: Segunda consulta RQL.

    Returns:
        RQL con ``UNION``.
    """
    return f"{q1} UNION {q2}"


def intersect_sql(q1: str, q2: str) -> str:
    """Genera RQL ``INTERSECT``.

    Args:
        q1: Primera consulta RQL.
        q2: Segunda consulta RQL.

    Returns:
        RQL con ``INTERSECT``.
    """
    return f"{q1} INTERSECT {q2}"


def window_sql(
    collection: str,
    func: str,
    partition_by: str | None = None,
    order_by: str = "created_at",
) -> str:
    """Genera RQL con window function.

    Args:
        collection: Coleccion destino (identificador validado).
        func: Funcion de ventana permitida (``ROW_NUMBER()``...).
        partition_by: Columna de particion opcional.
        order_by: Columna de orden (identificador validado).

    Returns:
        RQL con ``OVER (...)``.
    """
    table = _ident(collection, "collection")
    function = _window_function(func)
    order = _ident(order_by, "order_by")
    partition = f"PARTITION BY {_ident(partition_by, 'partition_by')} " if partition_by else ""
    # nosec B608: table/function/partition/order vienen de allowlists.
    return f"SELECT *, {function} OVER ({partition}ORDER BY {order}) as w FROM {table}"  # nosec B608


__all__ = ["cte_sql", "intersect_sql", "union_sql", "window_sql"]
