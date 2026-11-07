"""Contrato del DSL de factores (spec frontera 11.16 — Hubble + AlphaAgent).

WHAT: verifica ``harness/alpha_mining/factor_dsl.py`` contra las capacidades
medidas en los papers frontera:

- **Hubble** (arXiv 2604.09601): DSL de operadores — el LLM NUNCA emite code
  libre; el AST se reconstruye desde JSON validado (sandbox) y el evaluador
  es **total**: cero crashes con ceros, negativos, NaN y división por cero.
- **AlphaAgent** (arXiv 2502.16789, KDD'25): control de complejidad por
  conteo de nodos + originalidad por similitud de subárboles (Jaccard sobre
  multiconjuntos de subtrees canónicos, simplificación determinista del
  pairwise subtree isomorphism).
- **AlphaMCTS** (arXiv 2505.11122): Frequent Subtree Avoidance — genes
  abstractos (ventanas -> "t" via Abs) y conjunto prohibido top-k.

WHY: sin DSL validado, el loop de minería depende de `exec` de código LLM
(crashes y RCE); sin gates estructurales, la exploración colapsa en motifs
crowded (alpha decay).

WHERE: ``harness/alpha_mining/factor_dsl.py``.
"""

from __future__ import annotations

import numpy as np
import pytest

from harness.alpha_mining.factor_dsl import (
    MAX_NODES,
    Expr,
    Field,
    Operator,
    _ts_rank,
    abstract_gene,
    complexity,
    evaluate,
    forbidden_genes,
    parse_expr,
    subtree_similarity,
    to_dict,
    to_formula,
    validate_expr,
    violates_fsa,
)
from harness.tests.fixtures_alpha import make_panel

_CLOSE = Expr.leaf(Field.CLOSE)
_HIGH = Expr.leaf(Field.HIGH)
_LOW = Expr.leaf(Field.LOW)


class TestEvaluacionTotal:
    """El evaluador es total y determinista (Hubble: zero runtime crashes)."""

    def test_hoja_devuelve_el_campo(self) -> None:
        panel = make_panel()

        values = evaluate(_CLOSE, panel)

        assert np.array_equal(values, panel[Field.CLOSE])

    def test_ts_mean_ventana_3(self) -> None:
        panel = {Field.CLOSE: np.array([[1.0], [2.0], [3.0], [4.0]])}
        expr = Expr.apply(Operator.TS_MEAN, _CLOSE, window=3)

        values = evaluate(expr, panel)

        assert np.isnan(values[0, 0]) and np.isnan(values[1, 0])
        assert values[2, 0] == pytest.approx(2.0)
        assert values[3, 0] == pytest.approx(3.0)

    def test_delta_ventana_2(self) -> None:
        panel = {Field.CLOSE: np.array([[1.0], [2.0], [5.0], [9.0]])}
        expr = Expr.apply(Operator.DELTA, _CLOSE, window=2)

        values = evaluate(expr, panel)

        assert np.isnan(values[1, 0])
        assert values[2, 0] == pytest.approx(4.0)
        assert values[3, 0] == pytest.approx(7.0)

    def test_rank_cross_seccional(self) -> None:
        panel = {Field.CLOSE: np.array([[10.0, 20.0, 30.0]])}
        expr = Expr.apply(Operator.RANK, _CLOSE)

        values = evaluate(expr, panel)

        assert np.allclose(values[0], [0.0, 0.5, 1.0])

    def test_rank_excluye_nan(self) -> None:
        panel = {Field.CLOSE: np.array([[10.0, np.nan, 30.0]])}

        values = evaluate(Expr.apply(Operator.RANK, _CLOSE), panel)

        assert values[0, 0] == pytest.approx(0.0)
        assert values[0, 2] == pytest.approx(1.0)
        assert np.isnan(values[0, 1])

    def test_div_por_cero_es_nan_no_crash(self) -> None:
        panel = {Field.CLOSE: np.array([[1.0, 0.0]])}
        expr = Expr.apply(Operator.DIV, _CLOSE, _CLOSE)

        values = evaluate(expr, panel)

        assert values[0, 0] == pytest.approx(1.0)
        assert np.isnan(values[0, 1]), "DIV por cero -> NaN (totalidad, no excepcion)"

    def test_log_preserva_signo(self) -> None:
        panel = {Field.CLOSE: np.array([[-1.0], [np.e - 1.0]])}

        values = evaluate(Expr.apply(Operator.LOG, _CLOSE), panel)

        assert values[0, 0] == pytest.approx(-np.log(2.0))
        assert values[1, 0] == pytest.approx(1.0)

    def test_zscore_de_constante_es_cero(self) -> None:
        panel = {Field.CLOSE: np.array([[5.0], [5.0], [5.0], [5.0]])}
        expr = Expr.apply(Operator.ZSCORE, _CLOSE, window=3)

        values = evaluate(expr, panel)

        assert np.allclose(values[2:], 0.0)

    def test_ts_corr_perfecta_es_uno(self) -> None:
        close = np.array([[1.0], [2.0], [3.0], [4.0], [5.0]])
        panel = {Field.CLOSE: close, Field.VOLUME: close * 3.0}
        expr = Expr.apply(Operator.TS_CORR, _CLOSE, Expr.leaf(Field.VOLUME), window=3)

        values = evaluate(expr, panel)

        assert values[-1, 0] == pytest.approx(1.0)

    def test_campo_faltante_es_error_legible(self) -> None:
        with pytest.raises(ValueError, match="high"):
            evaluate(_HIGH, {Field.CLOSE: np.array([[1.0]])})

    def test_ts_rank_total_con_nan_en_ventana(self) -> None:
        """TS_RANK es total: NaN actual -> NaN; <2 finitos -> NaN; sin crash."""
        nan = np.nan
        panel = {
            Field.CLOSE: np.array([[1.0], [2.0], [3.0], [nan], [5.0], [nan], [nan], [8.0]])
        }

        values = evaluate(Expr.apply(Operator.TS_RANK, _CLOSE, window=3), panel)

        assert np.isfinite(values[2, 0]), "caso nominal: 3 finitos, rank computado"
        assert np.isnan(values[3, 0]), "valor actual NaN con 2 finitos -> NaN"
        assert np.isnan(values[6, 0]), "ventana con <2 finitos -> NaN (sin crash)"
        assert np.isnan(values[7, 0]), "<2 finitos + actual finito -> NaN (sin division/0)"

    def test_panel_hostil_nunca_crash(self) -> None:
        """Zero-crash: todos los ops sobre panel con ceros/NaN/negativos."""
        t, n = 30, 4
        rng = np.random.default_rng(11)
        hostile = rng.normal(0.0, 1.0, size=(t, n))
        hostile[::7] = 0.0
        hostile[::5] = np.nan
        panel = {
            Field.CLOSE: hostile,
            Field.HIGH: np.abs(hostile),
            Field.VOLUME: np.where(hostile > 0, hostile, 1.0),
        }
        for op in Operator:
            expr = _op_for(op, (_CLOSE,))
            values = evaluate(expr, panel)
            assert values.shape == (t, n)


def _op_for(op: Operator, children: tuple[Expr, ...]) -> Expr:
    """Construye un Expr valido para ``op`` (window por defecto)."""
    windowed = {
        Operator.TS_MEAN,
        Operator.TS_STD,
        Operator.DELTA,
        Operator.TS_RANK,
        Operator.TS_MAX,
        Operator.TS_MIN,
        Operator.ZSCORE,
    }
    if op in windowed:
        return Expr.apply(op, children[0], window=3)
    if op is Operator.TS_CORR:
        return Expr.apply(op, children[0], Expr.leaf(Field.HIGH), window=3)
    if op in {Operator.ADD, Operator.SUB, Operator.MUL, Operator.DIV}:
        return Expr.apply(op, children[0], Expr.leaf(Field.VOLUME))
    return Expr.apply(op, *children)


class TestValidacionYFormula:
    """Sandbox de reconstruccion desde JSON + serializacion determinista."""

    def test_ventana_fuera_de_rango_se_rechaza(self) -> None:
        with pytest.raises(ValueError, match="ventana"):
            Expr.apply(Operator.TS_MEAN, _CLOSE, window=1)

    def test_arity_incorrecta_se_rechaza(self) -> None:
        with pytest.raises(ValueError, match="hijos"):
            validate_expr(Expr.apply(Operator.ADD, _CLOSE))

    def test_complejidad_cuenta_nodos(self) -> None:
        expr = Expr.apply(Operator.ADD, _CLOSE, _HIGH)

        assert complexity(_CLOSE) == 1
        assert complexity(expr) == 3

    def test_to_formula_determinista(self) -> None:
        expr = Expr.apply(Operator.TS_MEAN, _CLOSE, window=20)

        assert to_formula(expr) == "ts_mean(close, 20)"

    def test_parse_roundtrip_identidad(self) -> None:
        expr = Expr.apply(
            Operator.TS_CORR,
            Expr.apply(Operator.RANK, _CLOSE),
            Expr.leaf(Field.VOLUME),
            window=10,
        )

        rebuilt = parse_expr(to_dict(expr))

        assert rebuilt == expr, "parse(to_dict(e)) == e: roundtrip exacto del AST"

    def test_parse_operador_desconocido_se_rechaza(self) -> None:
        with pytest.raises(ValueError, match="operador"):
            parse_expr({"op": "exec", "children": [{"field": "close"}]})

    def test_parse_json_no_mapping_se_rechaza(self) -> None:
        with pytest.raises(ValueError, match="AST"):
            parse_expr([1, 2, 3])


class TestGatesEstructurales:
    """Originalidad (AlphaAgent) y FSA (AlphaMCTS)."""

    def test_similitud_identica_es_uno(self) -> None:
        expr = Expr.apply(Operator.TS_MEAN, _CLOSE, window=20)

        assert subtree_similarity(expr, expr) == pytest.approx(1.0)

    def test_similitud_disjunta_es_cero(self) -> None:
        a = Expr.apply(Operator.TS_MEAN, _CLOSE, window=20)
        b = Expr.apply(Operator.SIGN, _HIGH)

        assert subtree_similarity(a, b) == pytest.approx(0.0)

    def test_gene_abstrae_la_ventana(self) -> None:
        a = Expr.apply(Operator.TS_MEAN, _CLOSE, window=20)
        b = Expr.apply(Operator.TS_MEAN, _CLOSE, window=5)

        assert abstract_gene(a) == abstract_gene(b), "Abs(.) ignora parametros"

    def test_forbidden_genes_toma_los_mas_frecuentes(self) -> None:
        corpus = [
            Expr.apply(Operator.TS_MEAN, _CLOSE, window=w) for w in (5, 10, 15)
        ] + [Expr.apply(Operator.SIGN, _HIGH)]

        forbidden = forbidden_genes(corpus, top_k=1)

        assert forbidden == frozenset({abstract_gene(corpus[0])})

    def test_violates_fsa_detecta_motif_prohibido(self) -> None:
        candidate = Expr.apply(Operator.TS_MEAN, _CLOSE, window=30)
        forbidden = frozenset({abstract_gene(candidate)})

        assert violates_fsa(candidate, forbidden) is True
        assert violates_fsa(Expr.apply(Operator.SCALE, _CLOSE), forbidden) is False

    def test_max_nodos_es_constante_documentada(self) -> None:
        assert MAX_NODES == 32


def _naive_ts_rank(x, window):
    """Referencia O(T*W) para el test de equivalencia del Fenwick."""
    out = np.full(x.shape, np.nan)
    for column in range(x.shape[1]):
        series = x[:, column]
        for t in range(window - 1, x.shape[0]):
            segment = series[t - window + 1 : t + 1]
            finite = np.isfinite(segment)
            count = int(finite.sum())
            current = series[t]
            if count < 2 or not np.isfinite(current):
                continue
            values = segment[finite]
            below = int((values < current).sum())
            equal = int((values == current).sum())
            out[t, column] = (below + (equal - 1) / 2.0) / (count - 1)
    return out


class TestTsRankEquivalence:
    """Fenwick vs referencia ingenua: mismo resultado, distinta complejidad."""

    @pytest.mark.parametrize("seed", [0, 1, 2, 3, 4])
    def test_fenwick_matches_naive_with_ties_and_nan(self, seed):
        """Paneles con empates y NaN producen exactamente el mismo rank."""
        rng = np.random.default_rng(seed)
        x = np.round(rng.normal(0.0, 1.0, size=(40, 3)), 1)
        x[rng.random(x.shape) < 0.15] = np.nan
        expected = _naive_ts_rank(x, window=7)
        got = _ts_rank(x, window=7)
        np.testing.assert_allclose(got, expected, equal_nan=True)

    def test_window_gt_rows_is_all_nan(self):
        """Ventana mayor que la serie no produce valores (sin crash)."""
        x = np.arange(10.0).reshape(5, 2)
        assert np.isnan(_ts_rank(x, window=50)).all()
