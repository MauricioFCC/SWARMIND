"""Helpers de time series para RuscaDB (Spec ruscadb-timeseries).

Genera RQL de bucketing, ventanas y downsampling. Como la API es publica, los
identificadores y agregados se validan contra allowlists antes de interpolar:
un caller no confiable no debe poder inyectar RQL.
"""

from __future__ import annotations

import re

_IDENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_AGG_CALL = re.compile(r"^([A-Za-z]+)\((\*|[A-Za-z_][A-Za-z0-9_]*)\)$")
_AGG_NAMES = frozenset({"COUNT", "AVG", "SUM", "MIN", "MAX"})


def _ident(name: str, field: str) -> str:
    """Valida un identificador RQL (coleccion o columna).

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


def _aggregate(expr: str) -> str:
    """Valida un agregado con argumento (``COUNT(*)``, ``AVG(value)``).

    Args:
        expr: Expresion recibida.

    Returns:
        Funcion normalizada en mayusculas y argumento original.

    Raises:
        ValueError: si la funcion no esta permitida o el argumento no es
            ``*`` ni un identificador.
    """
    match = _AGG_CALL.fullmatch(expr.strip()) if isinstance(expr, str) else None
    if not match or match.group(1).upper() not in _AGG_NAMES:
        raise ValueError(f"agregado RQL no permitido: {expr!r}")
    return f"{match.group(1).upper()}({match.group(2)})"


def _aggregate_name(name: str) -> str:
    """Valida el nombre de una funcion de agregado sin argumento.

    Args:
        name: Nombre recibido (``AVG``, ``SUM``...).

    Returns:
        Nombre en mayusculas.

    Raises:
        ValueError: si no esta en la allowlist.
    """
    upper = name.strip().upper() if isinstance(name, str) else ""
    if upper not in _AGG_NAMES:
        raise ValueError(f"agregado RQL no permitido: {name!r}")
    return upper


def time_bucket_sql(
    collection: str, bucket_sec: int, agg: str = "COUNT(*)", value_col: str = "*"
) -> str:
    """Genera RQL de time_bucket.

    Args:
        collection: Coleccion destino (identificador validado).
        bucket_sec: Ancho del bucket en segundos.
        agg: Agregado permitido (``COUNT(*)`` por defecto).
        value_col: Columna de valor; validada por contrato (reservada).

    Returns:
        Consulta RQL con bucketing temporal.
    """
    table = _ident(collection, "collection")
    if value_col != "*":
        _ident(value_col, "value_col")
    expression = _aggregate(agg)
    seconds = int(bucket_sec)
    # nosec B608: table/expression vienen de allowlists validadas arriba.
    return (
        f"SELECT time_bucket({seconds}, created_at) as bucket, {expression}"  # nosec B608
        f" FROM {table} GROUP BY bucket ORDER BY bucket"
    )


def moving_average_sql(collection: str, window: int, value_col: str = "value") -> str:
    """Genera RQL de moving average (ventana sobre ``created_at``).

    Args:
        collection: Coleccion destino (identificador validado).
        window: Filas de la ventana (entero >= 1).
        value_col: Columna numerica a promediar (identificador validado).

    Returns:
        Consulta RQL con ``AVG(...) OVER``.
    """
    table = _ident(collection, "collection")
    column = _ident(value_col, "value_col")
    rows = int(window)
    if rows < 1:
        raise ValueError(f"window invalida: {window!r}")
    # nosec B608: table/column vienen de _ident y rows es un int.
    return (
        f"SELECT {column}, AVG({column}) OVER (ORDER BY created_at ROWS BETWEEN"  # nosec B608
        f" {rows - 1} PRECEDING AND CURRENT ROW) as ma FROM {table}"
    )


def downsample_sql(collection: str, bucket_sec: int, agg: str = "AVG") -> str:
    """Genera RQL de downsampling.

    Args:
        collection: Coleccion destino (identificador validado).
        bucket_sec: Ancho del bucket en segundos.
        agg: Funcion de agregado permitida (``AVG`` por defecto).

    Returns:
        Consulta RQL que agrega ``value`` por bucket.
    """
    table = _ident(collection, "collection")
    function = _aggregate_name(agg)
    seconds = int(bucket_sec)
    # nosec B608: table/function vienen de allowlists validadas arriba.
    return (
        f"SELECT time_bucket({seconds}, created_at) as bucket, {function}(value)"  # nosec B608
        f" as value FROM {table} GROUP BY bucket"
    )


__all__ = ["downsample_sql", "moving_average_sql", "time_bucket_sql"]
