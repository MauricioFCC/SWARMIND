"""Contrato del Alpha Zoo (spec frontera 11.16 — AlphaMCTS + AlphaAgent + Hubble).

WHAT: verifica ``harness/alpha_mining/alpha_zoo.py`` contra la frontera:

- **AlphaMCTS** (arXiv 2505.11122): "Alpha Zoo" — repositorio persistente de
  alphas efectivos coleccionados durante la busqueda.
- **AlphaAgent** (KDD'25): knowledge base de factores FALLIDOS categorizada
  por modo de fallo (evita repetir pitfalls en iteraciones siguientes).
- **Hubble** (arXiv 2604.09601): seleccion FAMILY-AWARE — el top-k final
  respeta diversidad entre familias de factores (trend/volatility/range/...)
  en lugar de acumular motivos crowded de una sola familia.

WHY: un zoo sin dedup/originalidad acumula el mismo motif (crowding → alpha
decay); un top-k sin capa por familia devuelve 5 variantes de la misma idea.

WHERE: ``harness/alpha_mining/alpha_zoo.py``.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from harness.alpha_mining.alpha_zoo import (
    AlphaZoo,
    FactorFamily,
    ZooEntry,
    classify_family,
)
from harness.alpha_mining.factor_dsl import (
    Expr,
    Field,
    Operator,
    subtree_similarity,
    to_dict,
)

_CLOSE = Expr.leaf(Field.CLOSE)
_VOLUME = Expr.leaf(Field.VOLUME)
_HIGH = Expr.leaf(Field.HIGH)
_LOW = Expr.leaf(Field.LOW)


def _entry(formula: str, tree: dict, family: FactorFamily, score: float) -> ZooEntry:
    """Entry de zoo minima para tests."""
    return ZooEntry(
        formula=formula,
        tree=tree,
        family=family,
        score=score,
        rank_ic=score / 10.0,
        round_index=0,
    )


class TestClasificacionFamiliar:
    """Heuristica determinista de familias (Hubble family-aware)."""

    def test_volatilidad(self) -> None:
        assert (
            classify_family(Expr.apply(Operator.TS_STD, _CLOSE, window=20))
            is FactorFamily.VOLATILITY
        )

    def test_rango(self) -> None:
        expr = Expr.apply(
            Operator.SUB,
            Expr.apply(Operator.TS_MAX, _HIGH, window=10),
            Expr.apply(Operator.TS_MIN, _LOW, window=10),
        )

        assert classify_family(expr) is FactorFamily.RANGE

    def test_liquidez_volumen(self) -> None:
        expr = Expr.apply(
            Operator.DIV, _CLOSE, Expr.apply(Operator.TS_MEAN, _VOLUME, window=20)
        )

        assert classify_family(expr) is FactorFamily.LIQUIDITY_VOLUME

    def test_precio_volumen(self) -> None:
        expr = Expr.apply(Operator.TS_CORR, _CLOSE, _VOLUME, window=10)

        assert classify_family(expr) is FactorFamily.PRICE_VOLUME

    def test_tendencia(self) -> None:
        expr = Expr.apply(Operator.DELTA, _CLOSE, window=5)

        assert classify_family(expr) is FactorFamily.TREND

    def test_mean_reversion(self) -> None:
        assert classify_family(Expr.apply(Operator.RANK, _CLOSE)) is (
            FactorFamily.MEAN_REVERSION
        )

    def test_otra_familia(self) -> None:
        assert classify_family(Expr.apply(Operator.SIGN, _CLOSE)) is FactorFamily.OTHER


class TestPersistencia:
    """El zoo es durable (JSONL) y estricto con estado invalido."""

    def test_add_persiste_y_recarga(self, tmp_path: Path) -> None:
        zoo = AlphaZoo(tmp_path / "zoo.jsonl")
        expr = Expr.apply(Operator.TS_MEAN, _CLOSE, window=20)
        entry = _entry("ts_mean(close, 20)", to_dict(expr), FactorFamily.TREND, 0.5)

        assert zoo.add(entry) is True

        fresh = AlphaZoo(tmp_path / "zoo.jsonl")
        assert [e.formula for e in fresh.entries] == ["ts_mean(close, 20)"]

    def test_duplicado_por_formula_se_rechaza(self, tmp_path: Path) -> None:
        zoo = AlphaZoo(tmp_path / "zoo.jsonl")
        expr = Expr.apply(Operator.RANK, _CLOSE)
        entry = _entry("rank(close)", to_dict(expr), FactorFamily.MEAN_REVERSION, 0.4)

        assert zoo.add(entry) is True
        assert zoo.add(entry) is False

    def test_arbol_identico_con_nombre_distinto_se_rechaza(self, tmp_path: Path) -> None:
        """Originalidad: mismo AST, formula renombrada -> rechazado (AlphaAgent)."""
        zoo = AlphaZoo(tmp_path / "zoo.jsonl")
        expr = Expr.apply(Operator.DIV, _CLOSE, _VOLUME)
        first = _entry("div(close, volume)", to_dict(expr), FactorFamily.OTHER, 0.4)
        second = _entry("close / volume", to_dict(expr), FactorFamily.OTHER, 0.9)

        assert zoo.add(first) is True
        assert zoo.add(second) is False

    def test_journal_corrupto_explicita_error(self, tmp_path: Path) -> None:
        path = tmp_path / "zoo.jsonl"
        path.write_text("{no-es-json\n", encoding="utf-8")

        with pytest.raises(ValueError, match=r"linea 1 del zoo"):
            AlphaZoo(path)

    def test_similitud_en_el_umbral_0_8_se_rechaza(self, tmp_path: Path) -> None:
        """Jaccard exacto 0.8 (== umbral) -> rechazado (gate inclusivo)."""
        zoo = AlphaZoo(tmp_path / "zoo.jsonl")
        base = Expr.apply(Operator.ADD, Expr.apply(Operator.RANK, _CLOSE), _VOLUME)
        extended = Expr.apply(Operator.SIGN, base)

        assert subtree_similarity(base, extended) == pytest.approx(0.8)

        base_entry = _entry(
            "add(rank(close), volume)", to_dict(base), FactorFamily.OTHER, 0.5
        )
        extended_entry = _entry(
            "sign(add(rank(close), volume))", to_dict(extended), FactorFamily.OTHER, 0.6
        )
        assert zoo.add(base_entry) is True
        assert zoo.add(extended_entry) is False, (
            "similitud == umbral se trata como crowded (>=, no >)"
        )


class TestSeleccionFamilyAware:
    """Top-k con capa por familia (Hubble: diversidad en el top set)."""

    def _diverse_zoo(self, tmp_path: Path) -> AlphaZoo:
        zoo = AlphaZoo(tmp_path / "zoo.jsonl")
        specs = [
            (
                "ts_std(close, 20)",
                Expr.apply(Operator.TS_STD, _CLOSE, window=20),
                FactorFamily.VOLATILITY,
                0.9,
            ),
            (
                "zscore(volume, 10)",
                Expr.apply(Operator.ZSCORE, _VOLUME, window=10),
                FactorFamily.VOLATILITY,
                0.8,
            ),
            (
                "sub(ts_max(high), ts_min(low))",
                Expr.apply(
                    Operator.SUB,
                    Expr.apply(Operator.TS_MAX, _HIGH, window=10),
                    Expr.apply(Operator.TS_MIN, _LOW, window=10),
                ),
                FactorFamily.RANGE,
                0.7,
            ),
            (
                "sub(ts_max(open), ts_min(close))",
                Expr.apply(
                    Operator.SUB,
                    Expr.apply(Operator.TS_MAX, Expr.leaf(Field.OPEN), window=10),
                    Expr.apply(Operator.TS_MIN, _CLOSE, window=10),
                ),
                FactorFamily.RANGE,
                0.6,
            ),
        ]
        for formula, expr, family, score in specs:
            zoo.add(_entry(formula, to_dict(expr), family, score))
        return zoo

    def test_top_k_ordena_por_score(self, tmp_path: Path) -> None:
        zoo = AlphaZoo(tmp_path / "zoo.jsonl")
        specs = [
            ("a", 0.2, Field.CLOSE),
            ("b", 0.9, Field.VOLUME),
            ("c", 0.5, Field.OPEN),
        ]
        for formula, score, field in specs:
            expr = Expr.apply(Operator.SIGN, Expr.leaf(field))
            zoo.add(_entry(formula, to_dict(expr), FactorFamily.OTHER, score))

        top = zoo.top_k(3)

        assert [e.formula for e in top] == ["b", "c", "a"]

    def test_per_family_cap_limita_por_familia(self, tmp_path: Path) -> None:
        zoo = self._diverse_zoo(tmp_path)

        top = zoo.top_k(4, per_family_cap=1)

        assert len(top) == 2, "cap=1 por familia -> 1 volatility + 1 range"
        assert top[0].family is FactorFamily.VOLATILITY
        assert top[1].family is FactorFamily.RANGE

    def test_empates_se_rompen_por_formula(self, tmp_path: Path) -> None:
        zoo = AlphaZoo(tmp_path / "zoo.jsonl")
        for formula, field in [("bbb", Field.CLOSE), ("aaa", Field.VOLUME)]:
            expr = Expr.apply(Operator.SCALE, Expr.leaf(field))
            zoo.add(_entry(formula, to_dict(expr), FactorFamily.OTHER, 0.5))

        top = zoo.top_k(2)

        assert [e.formula for e in top] == ["aaa", "bbb"], "desempate determinista"


class TestKnowledgeBaseDeFallos:
    """KB de fallos categorizada (AlphaAgent: failure-mode knowledge base)."""

    def test_conteo_por_modo(self, tmp_path: Path) -> None:
        zoo = AlphaZoo(tmp_path / "zoo.jsonl")

        zoo.record_failure("f1", "metricas")
        zoo.record_failure("f2", "metricas")
        zoo.record_failure("f3", "fsa")

        assert dict(zoo.failure_modes()) == {"metricas": 2, "fsa": 1}

    def test_kb_sobrevive_a_reinicio(self, tmp_path: Path) -> None:
        zoo = AlphaZoo(tmp_path / "zoo.jsonl")
        zoo.record_failure("f1", "complejidad")

        fresh = AlphaZoo(tmp_path / "zoo.jsonl")

        assert dict(fresh.failure_modes()) == {"complejidad": 1}
