"""DSL de factores de alpha (spec frontera 11.16 — Hubble + AlphaAgent + AlphaMCTS).

WHAT: lenguaje de operadores tipado + AST inmutable + evaluador numpy TOTAL
sobre paneles (T, N), con los gates estructurales de la frontera:

- **Hubble** (arXiv 2604.09601): el LLM NUNCA emite code libre — genera JSON
  que se reconstruye como AST validado (`parse_expr`, sandbox) y el
  evaluador es total: ceros, negativos, NaN y division por cero producen
  NaN, jamas excepciones ("zero runtime crashes": 104 candidatos, 0 crashes
  en el paper).
- **AlphaAgent** (arXiv 2502.16789, KDD'25): complejidad por conteo de
  nodos (`MAX_NODES=32`) y originalidad por similitud de subarboles
  (`subtree_similarity`: Jaccard sobre multiconjuntos de formulas canonicas
  de subtrees — simplificacion determinista del subtree isomorphism).
- **AlphaMCTS** (arXiv 2505.11122): Frequent Subtree Avoidance — genes
  abstractos con `abstract_gene` (ventanas -> "t" via Abs(.)) y conjunto
  prohibido top-k (`forbidden_genes`) que `violates_fsa` detecta.

WHY: sin DSL validado la mineria depende de exec de codigo LLM (crashes +
RCE); sin gates estructurales la exploracion colapsa en motifs crowded
(alpha decay medido en los 5 papers).

WHERE: ``harness/alpha_mining/factor_dsl.py`` (nucleo de mining_loop).
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import Enum
from typing import Any

import numpy as np
from numpy.typing import NDArray

from .rolling_rank import ts_rank as _ts_rank

#: Maximo de nodos de un AST (AlphaAgent: complexity control).
MAX_NODES = 32
#: Ventana temporal minima aceptada.
MIN_WINDOW = 2
#: Ventana temporal maxima aceptada.
MAX_WINDOW = 250
#: Epsilon numerica para division y desviacion.
EPS = 1e-12


class Field(str, Enum):
    """Columnas de entrada del panel (hojas del AST)."""

    OPEN = "open"
    HIGH = "high"
    LOW = "low"
    CLOSE = "close"
    VOLUME = "volume"
    RETURNS = "returns"


class Operator(str, Enum):
    """Operadores del DSL (registro cerrado: sin code libre del LLM)."""

    RANK = "rank"
    TS_RANK = "ts_rank"
    TS_MEAN = "ts_mean"
    TS_STD = "ts_std"
    TS_MAX = "ts_max"
    TS_MIN = "ts_min"
    DELTA = "delta"
    ZSCORE = "zscore"
    SCALE = "scale"
    SIGN = "sign"
    ABS = "abs"
    LOG = "log"
    ADD = "add"
    SUB = "sub"
    MUL = "mul"
    DIV = "div"
    TS_CORR = "ts_corr"


#: Aritad (numero de hijos) exigida por operador.
_ARITY: dict[Operator, int] = {
    Operator.RANK: 1,
    Operator.TS_RANK: 1,
    Operator.TS_MEAN: 1,
    Operator.TS_STD: 1,
    Operator.TS_MAX: 1,
    Operator.TS_MIN: 1,
    Operator.DELTA: 1,
    Operator.ZSCORE: 1,
    Operator.SCALE: 1,
    Operator.SIGN: 1,
    Operator.ABS: 1,
    Operator.LOG: 1,
    Operator.ADD: 2,
    Operator.SUB: 2,
    Operator.MUL: 2,
    Operator.DIV: 2,
    Operator.TS_CORR: 2,
}

#: Operadores que consumen ventana temporal.
_WINDOWED = frozenset(
    {
        Operator.TS_RANK,
        Operator.TS_MEAN,
        Operator.TS_STD,
        Operator.TS_MAX,
        Operator.TS_MIN,
        Operator.DELTA,
        Operator.ZSCORE,
        Operator.TS_CORR,
    }
)


@dataclass(frozen=True)
class Expr:
    """AST inmutable de un factor: hoja (field) o aplicacion (op + hijos).

    Attributes:
        op: Operador interno; None en hojas.
        field: Campo hoja; None en nodos internos.
        window: Ventana temporal (solo operadores windowed).
        children: Sub-arboles hijos.
    """

    op: Operator | None
    field: Field | None
    window: int | None
    children: tuple[Expr, ...]

    @classmethod
    def leaf(cls, field: Field) -> Expr:
        """Crea una hoja que referencia una columna del panel.

        Args:
            field: Columna (p. ej. ``Field.CLOSE``).

        Returns:
            Hoja validada.
        """
        return cls(op=None, field=field, window=None, children=())

    @classmethod
    def apply(cls, op: Operator, *children: Expr, window: int | None = None) -> Expr:
        """Aplica un operador a sus hijos (valida aritad y ventana).

        Args:
            op: Operador del registro.
            children: Sub-arboles hijos (aridad fija por operador).
            window: Ventana temporal (obligatoria solo en operadores windowed).

        Returns:
            Nodo interno validado.

        Raises:
            ValueError: Si aritad, ventana o sub-arboles son invalidos.
        """
        expr = cls(op=op, field=None, window=window, children=tuple(children))
        validate_expr(expr)
        return expr


def complexity(expr: Expr) -> int:
    """Cuenta los nodos del AST (AlphaAgent: parameter/complexity control).

    Args:
        expr: Arbol a medir.

    Returns:
        Numero total de nodos (hojas + internos).
    """
    return 1 + sum(complexity(child) for child in expr.children)


def validate_expr(expr: Expr, max_nodes: int | None = None) -> None:
    """Valida un AST completo (sandbox: nada invalido entra al evaluador).

    Args:
        expr: Arbol a validar.
        max_nodes: Si se indica, limite superior de complejidad.

    Raises:
        ValueError: Si la forma, aritad, ventana o complejidad son invalidas.
    """
    if expr.op is None:
        if expr.field is None or expr.children or expr.window is not None:
            raise ValueError(
                "WHAT: hoja invalida (se exige field sin hijos ni ventana). "
                "WHY: el AST debe ser una hoja limpia. WHERE: validate_expr."
            )
        return
    expected = _ARITY[expr.op]
    if len(expr.children) != expected:
        raise ValueError(
            f"WHAT: operador '{expr.op.value}' con {len(expr.children)} hijos, "
            f"se esperan {expected}. WHY: aritad del registro DSL. "
            "WHERE: validate_expr."
        )
    if expr.op in _WINDOWED and not MIN_WINDOW <= (expr.window or 0) <= MAX_WINDOW:
        raise ValueError(
            f"WHAT: ventana {expr.window} fuera de [{MIN_WINDOW}, {MAX_WINDOW}] "
            f"para '{expr.op.value}'. WHY: rolling invalido. WHERE: validate_expr."
        )
    if expr.op not in _WINDOWED and expr.window is not None:
        raise ValueError(
            f"WHAT: '{expr.op.value}' no admite ventana. WHY: es elemento a "
            "elemento. WHERE: validate_expr."
        )
    for child in expr.children:
        validate_expr(child, max_nodes)
    if max_nodes is not None and complexity(expr) > max_nodes:
        raise ValueError(
            f"WHAT: AST con {complexity(expr)} nodos > maximo {max_nodes}. "
            "WHY: complexity control (anti-overfitting). WHERE: validate_expr."
        )


def to_formula(expr: Expr) -> str:
    """Serializa el AST a formula canonica determinista.

    Args:
        expr: Arbol a serializar.

    Returns:
        Texto tipo ``ts_mean(close, 20)``.
    """
    if expr.op is None:
        return expr.field.value  # type: ignore[union-attr]
    inner = ", ".join(to_formula(child) for child in expr.children)
    if expr.window is not None:
        inner = f"{inner}, {expr.window}"
    return f"{expr.op.value}({inner})"


def to_dict(expr: Expr) -> dict[str, Any]:
    """Serializa el AST a JSON-valido (formato de salida del LLM).

    Args:
        expr: Arbol a serializar.

    Returns:
        Mapping ``{"field": ...}`` o ``{"op", "window"?, "children"}``.
    """
    if expr.op is None:
        return {"field": expr.field.value}  # type: ignore[union-attr]
    data: dict[str, Any] = {
        "op": expr.op.value,
        "children": [to_dict(child) for child in expr.children],
    }
    if expr.window is not None:
        data["window"] = expr.window
    return data


def parse_expr(data: Mapping[str, Any]) -> Expr:
    """Reconstruye y valida un AST desde JSON del LLM (sandbox de entrada).

    Args:
        data: JSON mapeado por el generador.

    Returns:
        AST validado equivalente (``parse_expr(to_dict(e)) == e``).

    Raises:
        ValueError: Si el JSON no es un mapping o usa operadores/campos
            desconocidos o formas invalidas.
    """
    if not isinstance(data, Mapping):
        # ValueError unico del sandbox: mining_loop captura un solo tipo de
        # excepcion ante cualquier JSON hostil del LLM.
        raise ValueError(  # noqa: TRY004
            f"WHAT: AST recibido como {type(data).__name__}, se esperaba un "
            "mapping. WHY: el generador JSON debe producir objetos. "
            "WHERE: parse_expr."
        ) from None
    if "field" in data:
        try:
            return Expr.leaf(Field(str(data["field"])))
        except ValueError as exc:
            raise ValueError(
                f"WHAT: campo desconocido '{data['field']}'. WHY: registro "
                f"cerrado de Fields. WHERE: parse_expr ({exc})."
            ) from exc
    try:
        op = Operator(str(data.get("op", "")))
    except ValueError as exc:
        raise ValueError(
            f"WHAT: operador desconocido '{data.get('op')}'. WHY: registro "
            f"cerrado de Operator. WHERE: parse_expr ({exc})."
        ) from exc
    raw_children = data.get("children", [])
    if not isinstance(raw_children, (list, tuple)):
        # ValueError unico del sandbox (ver rama de mapping).
        raise ValueError(  # noqa: TRY004
            "WHAT: 'children' no es una lista. WHY: aridad del registro DSL. "
            "WHERE: parse_expr."
        ) from None
    children = tuple(parse_expr(child) for child in raw_children)
    window = data.get("window")
    return Expr.apply(op, *children, window=int(window) if window is not None else None)


def evaluate(
    expr: Expr, panel: Mapping[Field, NDArray[np.float64]]
) -> NDArray[np.float64]:
    """Evalua el AST sobre un panel (T, N): **total**, nunca excepciones runtime.

    Ceros, negativos, NaN y division por cero producen NaN/valores finitos,
    jamas crash (Hubble: "zero runtime crashes"). La UNICA excepcion es un
    campo hoja ausente del panel (error de configuracion, legible).

    Args:
        expr: AST validado del factor.
        panel: Mapping Field -> ndarray (T, N).

    Returns:
        ndarray float64 (T, N) con los valores del factor.

    Raises:
        ValueError: Si falta una columna hoja del panel (WHAT+WHY+WHERE).
    """
    if expr.op is None:
        field = expr.field
        if field is None or field not in panel:
            available = ", ".join(sorted(f.value for f in panel))
            raise ValueError(
                f"WHAT: campo '{field.value if field else None}' ausente en el "
                f"panel (disponibles: {available}). WHY: toda hoja del AST "
                "debe existir. WHERE: evaluate."
            )
        return np.asarray(panel[field], dtype=float)
    args = [evaluate(child, panel) for child in expr.children]
    with np.errstate(all="ignore"):
        return _apply_op(expr.op, args, expr.window)


def abstract_gene(expr: Expr) -> str:
    """Gene abstracto del AST: formula con las ventanas colapsadas a "t".

    AlphaMCTS Abs(.): ignora parametros numericos para agrupar motifs
    estructuralmente identicos (ts_mean(close, 5) y ts_mean(close, 20)
    comparten gene "ts_mean(close, t)").

    Args:
        expr: AST a abstraer.

    Returns:
        Formula canonica abstracta.
    """
    if expr.op is None:
        return expr.field.value  # type: ignore[union-attr]
    inner = ", ".join(abstract_gene(child) for child in expr.children)
    if expr.op in _WINDOWED:
        inner = f"{inner}, t"
    return f"{expr.op.value}({inner})"


def subtree_similarity(a: Expr, b: Expr) -> float:
    """Jaccard sobre multiconjuntos de genes abstractos de todos los subtrees.

    Simplificacion determinista del pairwise subtree isomorphism de
    AlphaAgent: cada arbol se reduce a su multiconjunto de formulas
    abstractas (subtree propio + hojas); similitud = |A n B| / |A u B|
    con multiplicidades (min/max por gen).

    Args:
        a: Primer AST.
        b: Segundo AST.

    Returns:
        Similitud en [0, 1] (1.0 = misma estructura de motivos).
    """
    genes_a, genes_b = _subtree_genes(a), _subtree_genes(b)
    intersection = sum((genes_a & genes_b).values())
    union = sum((genes_a | genes_b).values())
    if union == 0:
        return 1.0
    return intersection / union


def forbidden_genes(corpus: Sequence[Expr], top_k: int) -> frozenset[str]:
    """Conjunto prohibido: los genes abstractos mas frecuentes del corpus.

    Args:
        corpus: Formulaes de factores existentes (zoo).
        top_k: Numero de genes a prohibir.

    Returns:
        frozenset con los ``top_k`` genes mas frecuentes (empates: orden
        de aparicion, Counter es estable).
    """
    counts: Counter[str] = Counter(abstract_gene(expr) for expr in corpus)
    return frozenset(gene for gene, _ in counts.most_common(top_k))


def violates_fsa(expr: Expr, forbidden: frozenset[str]) -> bool:
    """Detecta si el AST contiene un motif abstracto prohibido (FSA).

    Recorre TODOS los subtrees: un candidato que contenga el motif en
    cualquier nivel viola el anti-crowding.

    Args:
        expr: Candidato a evaluar.
        forbidden: Genes abstractos prohibidos.

    Returns:
        True si algun subtree tiene su gene en el conjunto prohibido.
    """
    if not forbidden:
        return False
    stack = [expr]
    while stack:
        node = stack.pop()
        if abstract_gene(node) in forbidden:
            return True
        stack.extend(node.children)
    return False


def _subtree_genes(expr: Expr) -> Counter[str]:
    """Multiconjunto de genes abstractos de todos los subtrees del AST."""
    genes: Counter[str] = Counter()
    stack = [expr]
    while stack:
        node = stack.pop()
        genes[abstract_gene(node)] += 1
        stack.extend(node.children)
    return genes


def _apply_op(op: Operator, args: list[NDArray[np.float64]], window: int | None) -> NDArray[np.float64]:
    """Dispatch del evaluador por operador (total por construccion)."""
    if op is Operator.RANK:
        return _cs_rank(args[0])
    if op is Operator.TS_RANK:
        return _ts_rank(args[0], int(window or 0))
    if op is Operator.TS_MEAN:
        return _rolling(args[0], int(window or 0), np.mean)
    if op is Operator.TS_STD:
        return _rolling(args[0], int(window or 0), _std_roll)
    if op is Operator.TS_MAX:
        return _rolling(args[0], int(window or 0), np.max)
    if op is Operator.TS_MIN:
        return _rolling(args[0], int(window or 0), np.min)
    if op is Operator.DELTA:
        return _delta(args[0], int(window or 0))
    if op is Operator.ZSCORE:
        return _zscore(args[0], int(window or 0))
    if op is Operator.SCALE:
        return _scale(args[0])
    if op is Operator.SIGN:
        return np.sign(args[0])
    if op is Operator.ABS:
        return np.abs(args[0])
    if op is Operator.LOG:
        return np.sign(args[0]) * np.log1p(np.abs(args[0]))
    if op is Operator.ADD:
        return args[0] + args[1]
    if op is Operator.SUB:
        return args[0] - args[1]
    if op is Operator.MUL:
        return args[0] * args[1]
    if op is Operator.DIV:
        return np.where(args[1] == 0, np.nan, args[0] / args[1])
    if op is Operator.TS_CORR:
        return _ts_corr(args[0], args[1], int(window or 0))
    raise ValueError(  # pragma: no cover - registro cerrado ya validado
        f"WHAT: operador '{op.value}' sin implementacion. WHY: registro DSL "
        "cerrado. WHERE: _apply_op."
    )


def _cs_rank(x: NDArray[np.float64]) -> NDArray[np.float64]:
    """Rank cross-seccional por fila sobre valores finitos, normalizado [0, 1]."""
    out = np.full(x.shape, np.nan)
    for row_index, row in enumerate(x):
        finite = np.isfinite(row)
        count = int(finite.sum())
        if count < 2:
            continue
        values = row[finite]
        order = np.argsort(values, kind="stable")
        ranks = np.empty(count, dtype=float)
        ranks[order] = np.arange(count, dtype=float)
        out[row_index, finite] = ranks / (count - 1)
    return out


def _rolling(
    x: NDArray[np.float64], window: int, fn: Any
) -> NDArray[np.float64]:
    """Reduccion rolling con ``fn(wins, axis=-1)`` (NaN propaga)."""
    out = np.full(x.shape, np.nan)
    if x.shape[0] >= window:
        wins = np.lib.stride_tricks.sliding_window_view(x, window, axis=0)
        out[window - 1 :] = fn(wins, axis=-1)
    return out


def _std_roll(wins: NDArray[np.float64], axis: int = -1) -> NDArray[np.float64]:
    """Desviacion estandar poblacional de las ventanas rolling (ddof=0)."""
    return np.std(wins, axis=axis)


def _delta(x: NDArray[np.float64], window: int) -> NDArray[np.float64]:
    """x[t] - x[t-window] con las primeras ``window`` filas en NaN."""
    out = np.full(x.shape, np.nan)
    if x.shape[0] > window:
        out[window:] = x[window:] - x[:-window]
    return out


def _zscore(x: NDArray[np.float64], window: int) -> NDArray[np.float64]:
    """(x - media) / std rolling; std ~ 0 -> 0.0 (constante, no division)."""
    mean = _rolling(x, window, np.mean)
    std = _rolling(x, window, _std_roll)
    safe = np.where(std < EPS, 1.0, std)
    values = (x - mean) / safe
    return np.where(std < EPS, 0.0, values)


def _scale(x: NDArray[np.float64]) -> NDArray[np.float64]:
    """Normaliza cada fila por su suma de valores absolutos (|s| ~ 0 -> NaN)."""
    totals = np.sum(np.abs(x), axis=1, keepdims=True)
    safe = np.where(np.abs(totals) < EPS, 1.0, totals)
    return np.where(np.abs(totals) < EPS, np.nan, x / safe)


def _ts_corr(
    a: NDArray[np.float64], b: NDArray[np.float64], window: int
) -> NDArray[np.float64]:
    """Pearson rolling por pares completos (NaN excluido; <2 muestras -> NaN)."""
    out = np.full(a.shape, np.nan)
    if a.shape[0] < window:
        return out
    wins_a = np.lib.stride_tricks.sliding_window_view(a, window, axis=0)
    wins_b = np.lib.stride_tricks.sliding_window_view(b, window, axis=0)
    mask = np.isfinite(wins_a) & np.isfinite(wins_b)
    count = mask.sum(axis=-1)
    a_masked = np.where(mask, wins_a, 0.0)
    b_masked = np.where(mask, wins_b, 0.0)
    safe_count = np.maximum(count, 1)
    sum_a = a_masked.sum(axis=-1)
    sum_b = b_masked.sum(axis=-1)
    sum_ab = (a_masked * b_masked).sum(axis=-1)
    sum_aa = (a_masked * a_masked).sum(axis=-1)
    sum_bb = (b_masked * b_masked).sum(axis=-1)
    cov = sum_ab - sum_a * sum_b / safe_count
    var_a = sum_aa - sum_a * sum_a / safe_count
    var_b = sum_bb - sum_b * sum_b / safe_count
    denom = np.sqrt(np.maximum(var_a, 0.0) * np.maximum(var_b, 0.0))
    valid = (count >= 2) & (var_a > EPS) & (var_b > EPS)
    out[window - 1 :] = np.where(valid, cov / np.where(valid, denom, 1.0), np.nan)
    return out
