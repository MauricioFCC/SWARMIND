"""Alpha Zoo persistente (spec frontera 11.16 — AlphaMCTS + AlphaAgent + Hubble).

WHAT: repositorio durable de factores validados + knowledge base de fallos +
seleccion top-k family-aware:

- **AlphaMCTS** (arXiv 2505.11122): "Alpha Zoo" — coleccion de alphas
  efectivos (criterio IC) que la busqueda acumula y reutiliza.
- **AlphaAgent** (KDD'25): knowledge base de factores FALLIDOS categorizada
  por modo de fallo; el feedback de la KB evita repetir pitfalls.
- **Hubble** (arXiv 2604.09601): seleccion family-aware — el top-k final
  reparte cuota entre familias de factores (trend/volatility/range/...) en
  lugar de acumular motivos crowded de una sola familia.

Persistencia: JSONL estricto (linea = {"kind": "factor"|"failure", ...});
un journal corrupto se rechaza con error legible (nunca estado invalido).

WHY: un zoo sin dedup/originalidad acumula el mismo motif (crowding → alpha
decay); un top-k sin capa por familia devuelve N variantes de una idea.

WHERE: ``harness/alpha_mining/alpha_zoo.py``.
"""

from __future__ import annotations

import json
import logging
from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any

from harness.alpha_mining.factor_dsl import (
    Expr,
    Field,
    Operator,
    parse_expr,
    subtree_similarity,
    to_formula,
)

logger = logging.getLogger(__name__)

#: Similitud minima para considerar dos factores "el mismo motif".
DEFAULT_MIN_ORIGINALITY = 0.8


class FactorFamily(str, Enum):
    """Familias de factores (Hubble: exploracion y seleccion por familia)."""

    TREND = "trend"
    MEAN_REVERSION = "mean_reversion"
    VOLATILITY = "volatility"
    RANGE = "range"
    LIQUIDITY_VOLUME = "liquidity_volume"
    PRICE_VOLUME = "price_volume"
    OTHER = "other"


@dataclass(frozen=True)
class ZooEntry:
    """Factor validado almacenado en el zoo.

    Attributes:
        formula: Formula canonica (dedup por texto).
        tree: AST JSON-serializable (para similitud posterior).
        family: Familia clasificada.
        score: Score compuesto del eval (0-1).
        rank_ic: RankIC observado.
        round_index: Ronda de mineria que lo produjo.
    """

    formula: str
    tree: dict[str, Any]
    family: FactorFamily
    score: float
    rank_ic: float
    round_index: int


def classify_family(expr: Expr) -> FactorFamily:
    """Clasifica un AST en familia (heuristica determinista, orden fijo).

    Reglas en orden: volatilidad (TS_STD/ZSCORE) > rango (TS_MAX+TS_MIN) >
    liquidez-volumen (VOLUME con DIV/SCALE) > precio-volumen (TS_CORR) >
    tendencia (DELTA) > mean-reversion (RANK) > other.

    Args:
        expr: AST del factor.

    Returns:
        Familia del factor.
    """
    ops = _collect_ops(expr)
    fields = _collect_fields(expr)
    if ops & {Operator.TS_STD, Operator.ZSCORE}:
        return FactorFamily.VOLATILITY
    if Operator.TS_MAX in ops and Operator.TS_MIN in ops:
        return FactorFamily.RANGE
    if Field.VOLUME in fields and ops & {Operator.DIV, Operator.SCALE}:
        return FactorFamily.LIQUIDITY_VOLUME
    if Operator.TS_CORR in ops:
        return FactorFamily.PRICE_VOLUME
    if Operator.DELTA in ops:
        return FactorFamily.TREND
    if Operator.RANK in ops:
        return FactorFamily.MEAN_REVERSION
    return FactorFamily.OTHER


class AlphaZoo:
    """Zoo durable de factores + KB de fallos + seleccion family-aware.

    Cada mutacion (add/record_failure) se appendea al JSONL antes de
    devolver; el estado en memoria es una proyeccion del historial durable.
    """

    def __init__(self, path: Path) -> None:
        """Carga (o crea) el journal JSONL del zoo.

        Args:
            path: Ruta del JSONL (lineas {"kind": "factor"|"failure", ...}).

        Raises:
            ValueError: Si el journal esta corrupto (nunca estado invalido).
        """
        self._path = path
        self._entries: list[ZooEntry] = []
        self._failures: Counter[str] = Counter()
        # Indice exacto formula -> presencia: el dedup exacto pasa de O(n) a
        # O(1) antes del loop de similitud (que sigue siendo O(n) por AST).
        self._formulas: set[str] = set()
        self._load()
        self._formulas = {entry.formula for entry in self._entries}

    @property
    def entries(self) -> tuple[ZooEntry, ...]:
        """Factores del zoo en orden de insercion."""
        return tuple(self._entries)

    def is_similar(
        self, expr: Expr, *, min_originality: float = DEFAULT_MIN_ORIGINALITY
    ) -> bool:
        """True si el AST choca con una entrada existente (anti-crowding).

        Barato (sin backtest): se consulta ANTES de evaluar para no gastar
        compute en duplicados (AlphaAgent: originalidad pre-eval).

        Args:
            expr: Candidato a depositar.
            min_originality: Similitud maxima tolerada vs factores existentes.

        Returns:
            True si es duplicado por formula o similitud >= min_originality.
        """
        formula = to_formula(expr)
        if formula in self._formulas:
            return True
        for existing in self._entries:
            if subtree_similarity(expr, parse_expr(existing.tree)) >= min_originality:
                return True
        return False

    def add(self, entry: ZooEntry, *, min_originality: float = DEFAULT_MIN_ORIGINALITY) -> bool:
        """Agrega un factor si pasa dedup + gate de originalidad.

        Args:
            entry: Factor validado a incorporar.
            min_originality: Similitud maxima tolerada vs factores existentes.

        Returns:
            True si entro al zoo; False si es duplicado o demasiado similar
            (motif crowded — el caller debe registrar el rechazo).
        """
        candidate = parse_expr(entry.tree)
        if self.is_similar(candidate, min_originality=min_originality):
            logger.info(
                "alpha_zoo: rechazado '%s' (duplicado o demasiado similar al zoo)",
                entry.formula,
            )
            return False
        self._entries.append(entry)
        self._formulas.add(entry.formula)
        self._append({"kind": "factor", **_entry_to_record(entry)})
        return True

    def top_k(self, k: int, *, per_family_cap: int | None = None) -> tuple[ZooEntry, ...]:
        """Top-k por score con diversidad opcional por familia (Hubble).

        Args:
            k: Tamano maximo del top set.
            per_family_cap: Si se indica, cuota maxima por familia.

        Returns:
            Entradas ordenadas por (-score, formula); con cap, se llena
            greedy respetando la cuota familiar.
        """
        ordered = sorted(self._entries, key=lambda e: (-e.score, e.formula))
        if per_family_cap is None:
            return tuple(ordered[:k])
        counts: Counter[FactorFamily] = Counter()
        picked: list[ZooEntry] = []
        for entry in ordered:
            if len(picked) >= k:
                break
            if counts[entry.family] < per_family_cap:
                counts[entry.family] += 1
                picked.append(entry)
        return tuple(picked)

    def record_failure(self, formula: str, mode: str) -> None:
        """Registra un factor fallido en la KB categorizada (AlphaAgent).

        Args:
            formula: Formula canonica rechazada.
            mode: Modo de fallo (p. ej. "metricas", "fsa", "complejidad").
        """
        self._failures[mode] += 1
        self._append({"kind": "failure", "mode": mode, "formula": formula})

    def failure_modes(self) -> Mapping[str, int]:
        """Conteo de fallos por modo (feedback para prompts de iteracion)."""
        return dict(self._failures)

    def _load(self) -> None:
        """Hidrata el zoo desde el JSONL (estricto: corrupto = error)."""
        if not self._path.exists():
            return
        for number, line in enumerate(
            self._path.read_text(encoding="utf-8").splitlines(), start=1
        ):
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(
                    f"WHAT: linea {number} del zoo journal corrupta ({exc}). "
                    "WHY: el zoo es estado durable de la mineria; no se salta "
                    f"estado invalido. WHERE: {self._path}."
                ) from exc
            self._ingest(record)

    def _ingest(self, record: dict[str, Any]) -> None:
        """Aplica una linea del journal al estado en memoria."""
        if record.get("kind") == "failure":
            self._failures[str(record["mode"])] += 1
            return
        self._entries.append(
            ZooEntry(
                formula=str(record["formula"]),
                tree=dict(record["tree"]),
                family=FactorFamily(record["family"]),
                score=float(record["score"]),
                rank_ic=float(record["rank_ic"]),
                round_index=int(record["round_index"]),
            )
        )

    def _append(self, record: dict[str, Any]) -> None:
        """Appendea una linea JSONL (append-only; nunca reescribe)."""
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with self._path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")


def _entry_to_record(entry: ZooEntry) -> dict[str, Any]:
    """Convierte una entrada a registro JSONL."""
    return {
        "formula": entry.formula,
        "tree": entry.tree,
        "family": entry.family.value,
        "score": entry.score,
        "rank_ic": entry.rank_ic,
        "round_index": entry.round_index,
    }


def _collect_ops(expr: Expr) -> set[Operator]:
    """Recolecta todos los operadores del AST."""
    ops: set[Operator] = set()
    if expr.op is not None:
        ops.add(expr.op)
    for child in expr.children:
        ops |= _collect_ops(child)
    return ops


def _collect_fields(expr: Expr) -> set[Field]:
    """Recolecta todas las hojas de campo del AST."""
    fields: set[Field] = set()
    if expr.field is not None:
        fields.add(expr.field)
    for child in expr.children:
        fields |= _collect_fields(child)
    return fields
