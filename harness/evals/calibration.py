"""calibration.py — Calibracion probabilistica de la confianza (Brier/ECE/MCE).

Mide si la confianza declarada por un modelo coincide con su acierto real.
Un predictor bien calibrado que afirma 0.8 debe acertar ~80% de las veces.

Metricas:
    - ``brier``: error cuadratico medio de la probabilidad (menor es mejor).
    - ``ece``: Expected Calibration Error, promedio ponderado de los gaps.
    - ``mce``: Maximum Calibration Error, el peor gap por bin.

Reglas: SEG (valida rangos), ERR (errores accionables), IMM (dataclasses
frozen), MAG (sin numeros magicos), DOC (docstrings ES).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

DEFAULT_BINS = 10
MIN_POINTS = 5
GOOD_BRIER_MAX = 0.20
ECE_MAX = 0.10
PERFECT_TOLERANCE = 1e-9

#: Estrategia de bineado por masa igual (frontera: los LLM se concentran en
#: confianzas altas y el bineado de ancho fijo deja bins vacios y sesga el ECE).
BIN_STRATEGY_EQUAL_MASS = "equal_mass"
#: Estrategia de bineado por ancho uniforme (bins fijos en [0, 1]).
BIN_STRATEGY_EQUAL_WIDTH = "equal_width"
#: Estrategia por defecto (frontera 2026).
DEFAULT_BIN_STRATEGY = BIN_STRATEGY_EQUAL_MASS

__all__ = [
    "BIN_STRATEGY_EQUAL_MASS",
    "BIN_STRATEGY_EQUAL_WIDTH",
    "DEFAULT_BINS",
    "DEFAULT_BIN_STRATEGY",
    "ECE_MAX",
    "GOOD_BRIER_MAX",
    "MIN_POINTS",
    "PERFECT_TOLERANCE",
    "CalibrationReport",
    "DecileBin",
    "calibrate",
    "is_well_calibrated",
]


@dataclass(frozen=True)
class DecileBin:
    """Bin de confianza con su calibracion agregada.

    Args:
        low: Limite inferior del bin (inclusive).
        high: Limite superior del bin (exclusive, salvo el ultimo).
        count: Cantidad de observaciones en el bin.
        avg_confidence: Confianza media declarada en el bin.
        accuracy: Tasa de acierto observada en el bin.
        gap: Distancia absoluta entre accuracy y avg_confidence.
    """

    low: float
    high: float
    count: int
    avg_confidence: float
    accuracy: float
    gap: float


@dataclass(frozen=True)
class CalibrationReport:
    """Reporte inmutable de calibracion de un conjunto de pronosticos.

    Args:
        n: Numero total de observaciones.
        brier: Error cuadratico medio (Brier score).
        ece: Expected Calibration Error ponderado por tamano de bin.
        mce: Maximum Calibration Error (peor gap).
        hit_rate: Tasa de acierto global.
        deciles: Bins de confianza en orden ascendente.
    """

    n: int
    brier: float
    ece: float
    mce: float
    hit_rate: float
    deciles: tuple[DecileBin, ...]


def _target(success: bool) -> float:
    """Convierte el acierto booleano a su etiqueta numerica 1.0/0.0.

    Args:
        success: Resultado real del pronostico.

    Returns:
        ``1.0`` si acerto, ``0.0`` en caso contrario.
    """
    return 1.0 if success else 0.0


def _validate_point(confidence: float, success: bool, index: int) -> None:
    """Valida un unico pronostico de confianza.

    Args:
        confidence: Probabilidad declarada.
        success: Acierto real.
        index: Posicion en la secuencia (contexto del error).

    Raises:
        ValueError: Si la confianza no esta en ``[0, 1]``.
        TypeError: Si el acierto no es booleano.
    """
    if not 0.0 <= confidence <= 1.0:
        raise ValueError(
            f"calibrate: WHAT=confianza fuera de [0,1] ({confidence}); "
            f"WHY=p debe ser una probabilidad valida; "
            f"WHERE=harness/evals/calibration.calibrate (indice {index})"
        )
    if not isinstance(success, bool):
        raise TypeError(
            f"calibrate: WHAT=acierto no booleano ({type(success).__name__}); "
            f"WHY=y debe ser True o False; "
            f"WHERE=harness/evals/calibration.calibrate (indice {index})"
        )


def _validated_pairs(
    outcomes: Sequence[tuple[float, bool]],
) -> list[tuple[float, bool]]:
    """Valida los pronosticos y los normaliza a una lista de pares.

    Args:
        outcomes: Secuencia de ``(confianza, acierto)``.

    Returns:
        Lista de pares validados con confianza como ``float``.

    Raises:
        ValueError: Si hay menos de ``MIN_POINTS`` puntos.
    """
    if len(outcomes) < MIN_POINTS:
        raise ValueError(
            f"calibrate: WHAT=n<{MIN_POINTS} (n={len(outcomes)}); "
            f"WHY=se requieren al menos {MIN_POINTS} puntos para calibrar; "
            f"WHERE=harness/evals/calibration.calibrate"
        )
    pairs: list[tuple[float, bool]] = []
    for index, (confidence, success) in enumerate(outcomes):
        _validate_point(confidence, success, index)
        pairs.append((float(confidence), success))
    return pairs


def _make_bin(low: float, high: float, pairs: list[tuple[float, bool]]) -> DecileBin:
    """Construye un bin con sus metricas agregadas.

    Args:
        low: Limite inferior del bin.
        high: Limite superior del bin.
        pairs: Observaciones asignadas al bin.

    Returns:
        ``DecileBin`` con confianza media, accuracy y gap.
    """
    count = len(pairs)
    if count == 0:
        return DecileBin(low=low, high=high, count=0, avg_confidence=0.0, accuracy=0.0, gap=0.0)
    avg_confidence = sum(confidence for confidence, _ in pairs) / count
    accuracy = sum(_target(success) for _, success in pairs) / count
    gap = abs(accuracy - avg_confidence)
    if gap < PERFECT_TOLERANCE:
        gap = 0.0
    return DecileBin(low, high, count, avg_confidence, accuracy, gap)


def _bins_equal_width(
    pairs: list[tuple[float, bool]], bins: int
) -> tuple[DecileBin, ...]:
    """Agrupa los pares en bins de ancho uniforme en ``[0, 1]``.

    Args:
        pairs: Observaciones validadas.
        bins: Numero de intervalos de igual ancho.

    Returns:
        Tupla de ``DecileBin`` (longitud ``bins``), en orden ascendente.
    """
    width = 1.0 / bins
    grouped: list[list[tuple[float, bool]]] = [[] for _ in range(bins)]
    for confidence, success in pairs:
        index = min(int(confidence * bins), bins - 1)
        grouped[index].append((confidence, success))
    return tuple(
        _make_bin(index * width, (index + 1) * width, grouped[index])
        for index in range(bins)
    )


def _bins_equal_mass(
    pairs: list[tuple[float, bool]], bins: int
) -> tuple[DecileBin, ...]:
    """Agrupa los pares en bins de masa (cantidad) aproximadamente igual.

    Frontera 2026: con confianzas concentradas en valores altos, el bineado de
    ancho fijo deja bins vacios y sesga el ECE; el bineado por masa reparte el
    mismo numero de observaciones por bin. Se omiten los bins vacios (n < bins).

    Args:
        pairs: Observaciones validadas.
        bins: Numero maximo de intervalos.

    Returns:
        Tupla de ``DecileBin`` no vacios, en orden ascendente de confianza.
    """
    ordered = sorted(pairs, key=lambda item: item[0])
    n = len(ordered)
    chunks: list[DecileBin] = []
    for index in range(bins):
        chunk = ordered[index * n // bins:(index + 1) * n // bins]
        if chunk:
            chunks.append(_make_bin(chunk[0][0], chunk[-1][0], chunk))
    return tuple(chunks)


def _build_bins(
    pairs: list[tuple[float, bool]], bins: int, strategy: str
) -> tuple[DecileBin, ...]:
    """Selecciona la estrategia de bineado y agrupa los pares.

    Args:
        pairs: Observaciones validadas.
        bins: Numero de intervalos.
        strategy: ``BIN_STRATEGY_EQUAL_MASS`` o ``BIN_STRATEGY_EQUAL_WIDTH``.

    Returns:
        Tupla de ``DecileBin``, en orden ascendente.

    Raises:
        ValueError: Si la estrategia no es reconocida (WHAT+WHY+WHERE).
    """
    if strategy == BIN_STRATEGY_EQUAL_WIDTH:
        return _bins_equal_width(pairs, bins)
    if strategy == BIN_STRATEGY_EQUAL_MASS:
        return _bins_equal_mass(pairs, bins)
    raise ValueError(
        f"calibrate: WHAT=estrategia desconocida ({strategy!r}); "
        f"WHY=usa {BIN_STRATEGY_EQUAL_MASS!r} o {BIN_STRATEGY_EQUAL_WIDTH!r}; "
        f"WHERE=harness/evals/calibration._build_bins"
    )


def calibrate(
    outcomes: Sequence[tuple[float, bool]],
    *,
    bins: int = DEFAULT_BINS,
    strategy: str = DEFAULT_BIN_STRATEGY,
) -> CalibrationReport:
    """Calibra un conjunto de pronosticos de confianza.

    Args:
        outcomes: Secuencia de ``(confianza p en [0,1], acierto y bool)``.
        bins: Numero de bins (por defecto ``DEFAULT_BINS``).
        strategy: Estrategia de bineado; por defecto ``equal_mass`` (frontera).

    Returns:
        ``CalibrationReport`` con Brier, ECE, MCE, hit rate y bins.

    Raises:
        ValueError: Si ``bins < 1``, estrategia desconocida, menos de
            ``MIN_POINTS`` puntos, o confianza/acierto fuera de rango.
    """
    if bins < 1:
        raise ValueError(
            f"calibrate: WHAT=bins<1 ({bins}); "
            f"WHY=se requiere al menos un bin; "
            f"WHERE=harness/evals/calibration.calibrate"
        )
    pairs = _validated_pairs(outcomes)
    return _build_report(pairs, bins, strategy)


def _build_report(
    pairs: list[tuple[float, bool]], bins: int, strategy: str
) -> CalibrationReport:
    """Calcula las metricas agregadas del reporte de calibracion.

    Args:
        pairs: Observaciones validadas.
        bins: Numero de bins.
        strategy: Estrategia de bineado.

    Returns:
        ``CalibrationReport`` con Brier, ECE, MCE, hit rate y bins.
    """
    n = len(pairs)
    brier = sum((confidence - _target(success)) ** 2 for confidence, success in pairs) / n
    hit_rate = sum(_target(success) for _, success in pairs) / n
    deciles = _build_bins(pairs, bins, strategy)
    ece = sum(bin_.count / n * bin_.gap for bin_ in deciles)
    mce = max((bin_.gap for bin_ in deciles), default=0.0)
    return CalibrationReport(
        n=n, brier=brier, ece=ece, mce=mce, hit_rate=hit_rate, deciles=deciles
    )


def is_well_calibrated(report: CalibrationReport) -> bool:
    """Indica si un reporte cumple los umbrales institucionales.

    Args:
        report: Reporte devuelto por :func:`calibrate`.

    Returns:
        ``True`` si ``brier <= GOOD_BRIER_MAX`` y ``ece <= ECE_MAX``.
    """
    return report.brier <= GOOD_BRIER_MAX and report.ece <= ECE_MAX
