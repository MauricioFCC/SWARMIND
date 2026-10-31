"""Helpers de time series para RuscaDB (Spec ruscadb-timeseries).

Genera RQL de bucketing, ventanas y downsampling.
"""

from __future__ import annotations


def time_bucket_sql(collection: str, bucket_sec: int, agg: str = "COUNT(*)", value_col: str = "*") -> str:
    """Genera RQL de time_bucket."""
    return f"SELECT time_bucket({bucket_sec}, created_at) as bucket, {agg} FROM {collection} GROUP BY bucket ORDER BY bucket"


def moving_average_sql(collection: str, window: int, value_col: str = "value") -> str:
    """Genera RQL de moving average (via window function si disponible)."""
    return f"SELECT {value_col}, AVG({value_col}) OVER (ORDER BY created_at ROWS BETWEEN {window-1} PRECEDING AND CURRENT ROW) as ma FROM {collection}"


def downsample_sql(collection: str, bucket_sec: int, agg: str = "AVG") -> str:
    """Genera RQL de downsampling."""
    return f"SELECT time_bucket({bucket_sec}, created_at) as bucket, {agg}(value) as value FROM {collection} GROUP BY bucket"


__all__ = ["downsample_sql", "moving_average_sql", "time_bucket_sql"]
