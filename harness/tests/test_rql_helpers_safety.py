"""Tests de seguridad de los builders de RQL (validacion de identificadores)."""

from __future__ import annotations

import pytest

from harness.memory_rag.rql_helpers import cte_sql, intersect_sql, union_sql, window_sql
from harness.memory_rag.timeseries_helpers import (
    downsample_sql,
    moving_average_sql,
    time_bucket_sql,
)


class TestTimeSeries:
    """Los helpers de time series solo interpolan valores validados."""

    def test_time_bucket_genera_rql(self) -> None:
        """Genera bucketing con agregado permitido."""
        sql = time_bucket_sql("metrics", 60)
        assert "time_bucket(60, created_at)" in sql
        assert "COUNT(*)" in sql
        assert "FROM metrics" in sql

    @pytest.mark.parametrize(
        "collection",
        ["metrics; DROP TABLE memory", "metrics WHERE 1=1", "", "9metrics"],
    )
    def test_time_bucket_rechaza_coleccion(self, collection: str) -> None:
        """Una coleccion fuera del patron de identificador es rechazada."""
        with pytest.raises(ValueError, match="collection"):
            time_bucket_sql(collection, 60)

    @pytest.mark.parametrize("agg", ["LOAD", "COUNT(*); DROP", "AVG(1)", ""])
    def test_time_bucket_rechaza_agregado(self, agg: str) -> None:
        """Solo se aceptan agregados de la allowlist con columna o ``*``."""
        with pytest.raises(ValueError, match="agregado"):
            time_bucket_sql("metrics", 60, agg=agg)

    def test_moving_average_valida_ventana_y_columna(self) -> None:
        """La ventana debe ser positiva y la columna un identificador."""
        assert "ROWS BETWEEN 2 PRECEDING" in moving_average_sql("metrics", 3)
        with pytest.raises(ValueError, match="window"):
            moving_average_sql("metrics", 0)
        with pytest.raises(ValueError, match="value_col"):
            moving_average_sql("metrics", 3, value_col="value; DROP")

    def test_downsample_normaliza_agregado(self) -> None:
        """``avg`` en minusculas se normaliza a ``AVG``."""
        assert "AVG(value)" in downsample_sql("metrics", 300, agg="avg")
        with pytest.raises(ValueError, match="agregado"):
            downsample_sql("metrics", 300, agg="LOAD")


class TestRqlHelpers:
    """Los helpers de RQL avanzado validan CTE, ventana y orden."""

    def test_cte_valida_nombre(self) -> None:
        """El nombre del CTE debe ser un identificador."""
        assert cte_sql("recientes", "SELECT 1", "SELECT * FROM recientes").startswith(
            "WITH recientes AS"
        )
        with pytest.raises(ValueError, match="cte_name"):
            cte_sql("x; DROP", "SELECT 1", "SELECT 1")

    def test_window_sql_valido(self) -> None:
        """Genera OVER con particion y orden validados."""
        sql = window_sql(
            "metrics", "ROW_NUMBER()", partition_by="session_id", order_by="ts"
        )
        assert "PARTITION BY session_id" in sql
        assert "ORDER BY ts" in sql
        assert "FROM metrics" in sql

    @pytest.mark.parametrize(
        "func", ["LOAD()", "row_number()", "SUM(value); DROP", "EVIL(x)"]
    )
    def test_window_sql_rechaza_funcion(self, func: str) -> None:
        """Solo funciones de ventana de la allowlist."""
        if func == "row_number()":
            assert window_sql("metrics", func).startswith("SELECT *,")
            return
        with pytest.raises(ValueError, match="funcion de ventana"):
            window_sql("metrics", func)

    def test_window_sql_rechaza_orden(self) -> None:
        """El orden no puede inyectar clausulas."""
        with pytest.raises(ValueError, match="order_by"):
            window_sql("metrics", "RANK()", order_by="ts; DROP")

    def test_union_e_intersect_conservan_consultas(self) -> None:
        """Los combinadores no modifican el RQL del caller."""
        assert union_sql("SELECT 1", "SELECT 2") == "SELECT 1 UNION SELECT 2"
        assert intersect_sql("SELECT 1", "SELECT 2") == "SELECT 1 INTERSECT SELECT 2"
