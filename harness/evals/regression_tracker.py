"""Graduacion de evals capability -> regression (spec frontera 11.15).

WHAT: ``RegressionTracker`` codifica la disciplina de evals de Anthropic
("Demystifying evals for AI agents", 2026-01):

- Las suites de REGRESION deben sostener pass-rate ~100%: una caida senala
  breakage. El tracker compara la corrida actual contra la baseline historica
  (media por tarea de las corridas PREVIAS) y nombra las tareas que cayeron
  mas de ``MAX_DROP_PP`` puntos — el reporte es accionable, no solo un numero.
- Pass-rate de 100% = senal SATURADA: la suite trackea regresiones pero ya no
  estimula mejorar; el reporte lo marca para endurecer tareas o graduar.
- Historial APPEND-ONLY en JSONL: las corridas previas jamas se reescriben
  (auditoria + recovery determinism: la baseline es funcion del historial
  durable, no de estado en memoria).
- La baseline excluye la corrida actual (no sesga su propia comparacion).

WHY: sin tracking historico, un refactor que degrada una suite al 80% pasa
inadvertido mientras el comando "exista"; sin deteccion de saturacion, un
100% perpetuo esconde que dejo de medir progreso.

WHERE: ``harness/evals/regression_tracker.py``.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

#: Pass-rate minimo de una suite ya graduada a REGRESION (~100% canon).
MIN_REGRESSION_PASS_RATE = 0.99
#: Caida maxima tolerada por tarea vs baseline, en puntos porcentuales.
MAX_DROP_PP = 1.0
#: Fraccion minima para considerar una suite saturada (pass-rate perfecto).
_SATURATION_FRACTION = 1.0


@dataclass(frozen=True)
class RegressionReport:
    """Veredicto de una corrida contra la baseline historica de su suite.

    Attributes:
        suite: Suite evaluada.
        pass_rate: Pass-rate actual (media de scores por tarea).
        baseline_pass_rate: Pass-rate medio de las corridas previas (None si
            no hay historial: no hay nada de lo que regresar).
        dropped: Tareas que cayeron vs baseline mas de ``MAX_DROP_PP``.
        saturated: True si el pass-rate es perfecto (senal saturada).
        below_bar: True si el pass-rate esta bajo ``MIN_REGRESSION_PASS_RATE``
            (la suite aun no esta graduada a regresion).
    """

    suite: str
    pass_rate: float
    baseline_pass_rate: float | None
    dropped: tuple[str, ...]
    saturated: bool
    below_bar: bool

    @property
    def is_regression(self) -> bool:
        """True si alguna tarea cayo mas del umbral permitido vs baseline."""
        return bool(self.dropped)


class RegressionTracker:
    """Historial append-only de suites de eval con veredicto de regression.

    Cada ``evaluate_and_record`` (1) valida la corrida, (2) calcula la baseline
    desde las corridas PREVIAS del mismo suite, (3) emite el
    :class:`RegressionReport` y (4) appendea la corrida al historial JSONL.
    """

    def __init__(self, history_path: Path) -> None:
        """Fija el historial JSONL.

        Args:
            history_path: Ruta del JSONL append-only
                (linea = ``{"suite": ..., "scores": {...}}``).
        """
        self._path = history_path

    def evaluate_and_record(
        self,
        suite: str,
        scores: Mapping[str, float],
        min_pass_rate: float = MIN_REGRESSION_PASS_RATE,
        max_drop_pp: float = MAX_DROP_PP,
    ) -> RegressionReport:
        """Verdicta la corrida actual contra la baseline y la persiste.

        Args:
            suite: Nombre de la suite (p. ej. ``"swe"``).
            scores: Score por tarea en [0, 1] (1.0 = tarea OK).
            min_pass_rate: Umbral de pass-rate para ``below_bar``.
            max_drop_pp: Caida maxima por tarea (puntos %) antes de alertar.

        Returns:
            Reporte con baseline, tareas caidas y flags saturacion/below_bar.

        Raises:
            ValueError: Si algun score esta fuera de [0, 1] o ``scores`` vacio.
        """
        current = self._validate(scores)
        prior = self._history(suite)
        baseline = self._baseline_scores(prior)
        pass_rate = sum(current.values()) / len(current)
        baseline_rate: float | None = None
        if prior:
            prior_rates = [sum(run.values()) / len(run) for run in prior]
            baseline_rate = sum(prior_rates) / len(prior_rates)
        max_fraction = max_drop_pp / 100.0
        dropped = tuple(
            sorted(
                task
                for task, score in current.items()
                if task in baseline and baseline[task] - score > max_fraction
            )
        )
        report = RegressionReport(
            suite=suite,
            pass_rate=pass_rate,
            baseline_pass_rate=baseline_rate,
            dropped=dropped,
            saturated=pass_rate >= _SATURATION_FRACTION,
            below_bar=pass_rate < min_pass_rate,
        )
        self._append(suite, current)
        if report.is_regression:
            logger.warning(
                "regression_tracker: REGRESSION en suite '%s': tareas caidas %s",
                suite,
                list(report.dropped),
            )
        return report

    def _validate(self, scores: Mapping[str, float]) -> dict[str, float]:
        """Copia y valida los scores de la corrida.

        Raises:
            ValueError: Si ``scores`` esta vacio o tiene valores fuera de [0, 1].
        """
        if not scores:
            raise ValueError(
                "WHAT: scores vacio. WHY: una corrida sin tareas no evalua "
                "nada. WHERE: RegressionTracker.evaluate_and_record."
            )
        validated: dict[str, float] = {}
        for task, score in scores.items():
            if not isinstance(score, (int, float)) or not 0.0 <= float(score) <= 1.0:
                raise ValueError(
                    f"WHAT: score invalido para '{task}': {score!r} fuera de "
                    "[0, 1]. WHY: los scores son fracciones de exito. "
                    "WHERE: RegressionTracker.evaluate_and_record."
                )
            validated[str(task)] = float(score)
        return validated

    def _history(self, suite: str) -> list[dict[str, float]]:
        """Scores de las corridas PREVIAS del suite (append-only en disco).

        Raises:
            ValueError: Si una linea del historial esta corrupta (nunca se
                ignora estado invalido en silencio).
        """
        if not self._path.exists():
            return []
        runs: list[dict[str, float]] = []
        for number, line in enumerate(
            self._path.read_text(encoding="utf-8").splitlines(), start=1
        ):
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(
                    f"WHAT: linea {number} del historial corrupta ({exc}). "
                    "WHY: el historial es la baseline durable; no se salta "
                    f"estado invalido. WHERE: {self._path}."
                ) from exc
            if record.get("suite") == suite:
                runs.append({str(k): float(v) for k, v in record["scores"].items()})
        return runs

    @staticmethod
    def _baseline_scores(prior: list[dict[str, float]]) -> dict[str, float]:
        """Media por tarea de las corridas previas (baseline)."""
        if not prior:
            return {}
        totals: dict[str, list[float]] = {}
        for run in prior:
            for task, score in run.items():
                totals.setdefault(task, []).append(score)
        return {task: sum(values) / len(values) for task, values in totals.items()}

    def _append(self, suite: str, scores: Mapping[str, float]) -> None:
        """Appendea una linea JSONL (append-only; nunca reescribe)."""
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with self._path.open("a", encoding="utf-8") as handle:
            handle.write(
                json.dumps({"suite": suite, "scores": dict(scores)}, ensure_ascii=False)
                + "\n"
            )
