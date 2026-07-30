"""L1 — FailurePredictor: Prediccion de fallos basada en datos historicos.

Predice probabilidad de fallo por test file, funcion, o commit usando:
- Historial de ejecuciones previas
- Complejidad ciclomatica del codigo bajo prueba
- Ratio de cambios recientes (churn)
- Cobertura de codigo actual

Returns: RiskScore por cada elemento de test con probabilidad [0,1].

Example:
    predictor = FailurePredictor()
    riesgo = predictor.predict("tests/test_auth.py")
    print(f"Probabilidad de fallo: {riesgo.probability:.2%}")
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional
from uuid import uuid4

from harness.qa import QALayer, QAMetadata

logger = logging.getLogger(__name__)

# ── Umbrales de configuracion ─────────────────────────────────────────────────

_UMBRAL_ALTO = 0.70
_UMBRAL_MEDIO = 0.35
_PESO_HISTORIAL = 0.40
_PESO_COMPLEJIDAD = 0.25
_PESO_CHURN = 0.20
_PESO_COBERTURA = 0.15


@dataclass(frozen=True)
class HistorialEjecucion:
    """Registro inmutable de una ejecucion historica de test.

    Args:
        test_id: Identificador unico del test.
        total_runs: Numero total de ejecuciones registradas.
        failures: Cantidad de fallos observados.
        avg_duration_ms: Duracion promedio en milisegundos.
        last_run: Marca de tiempo de la ultima ejecucion.
        metadata: Metadatos QA asociados.

    Raises:
        ValueError: Si failures > total_runs.
    """

    test_id: str
    total_runs: int
    failures: int
    avg_duration_ms: float
    last_run: Optional[str] = None
    metadata: Optional[QAMetadata] = None

    def __post_init__(self) -> None:
        """Valida integridad del historial."""
        if self.failures > self.total_runs:
            raise ValueError(
                f"[L1][HistorialEjecucion] failures ({self.failures}) supera "
                f"total_runs ({self.total_runs}) para test_id={self.test_id}. "
                f"WHERE: validacion de integridad en __post_init__."
            )

    @property
    def failure_rate(self) -> float:
        """Tasa de fallo historica en rango [0, 1]."""
        if self.total_runs == 0:
            return 0.0
        return self.failures / self.total_runs


@dataclass(frozen=True)
class RiskScore:
    """Puntaje de riesgo calculado por el FailurePredictor.

    Args:
        target: Elemento analizado (archivo, funcion, commit).
        probability: Probabilidad estimada de fallo en [0, 1].
        complexity_score: Aporte de complejidad ciclomatica.
        churn_score: Aporte de tasa de cambios recientes.
        coverage_penalty: Penalizacion por baja cobertura.
        details: Desglose adicional del calculo.
        execution_id: Identificador unico de la prediccion.
    """

    target: str
    probability: float
    complexity_score: float = 0.0
    churn_score: float = 0.0
    coverage_penalty: float = 0.0
    details: dict[str, float] = field(default_factory=dict)
    execution_id: str = field(default_factory=lambda: uuid4().hex[:12])

    def __post_init__(self) -> None:
        """Normaliza y asegura rango [0, 1] en probability."""
        if not (0.0 <= self.probability <= 1.0):
            object.__setattr__(self, "probability", max(0.0, min(1.0, self.probability)))
            logger.warning(
                f"[L1][RiskScore] probability fuera de rango para target={self.target}. "
                f"WHAT: valor normalizado a [{self.probability}]. "
                f"WHY: garantizar invariante [0,1]. "
                f"WHERE: __post_init__ RiskScore."
            )

    @property
    def nivel(self) -> str:
        """Clasifica el riesgo en ALTO, MEDIO o BAJO."""
        if self.probability >= _UMBRAL_ALTO:
            return "ALTO"
        if self.probability >= _UMBRAL_MEDIO:
            return "MEDIO"
        return "BAJO"


class FailurePredictor:
    """Predice fallos de tests usando analisis multi-factor.

    Combina historial de ejecucion, complejidad ciclomatica, churn
    de cambios y cobertura para estimar riesgo de fallo.

    Args:
        metadata: Metadatos opcionales para la capa L1.
    """

    def __init__(self, metadata: Optional[QAMetadata] = None) -> None:
        """Inicializa el predictor con metadatos de capa."""
        self._metadata = metadata or QAMetadata(
            layer=QALayer.L1_PREDICTOR,
            version="1.0.0",
            timestamp_iso=datetime.now(timezone.utc).isoformat(),
            execution_id=uuid4().hex[:12],
        )
        self._historial: dict[str, HistorialEjecucion] = {}
        logger.info(
            f"[L1][FailurePredictor] Inicializado. "
            f"WHAT: predictor creado con execution_id={self._metadata.execution_id}. "
            f"WHY: inicio de capa L1. "
            f"WHERE: FailurePredictor.__init__."
        )

    def registrar_historial(self, registro: HistorialEjecucion) -> None:
        """Registra un historial de ejecucion para un test.

        Args:
            registro: HistorialEjecucion con datos de ejecuciones previas.

        Raises:
            TypeError: Si registro no es instancia de HistorialEjecucion.
        """
        if not isinstance(registro, HistorialEjecucion):
            raise TypeError(
                f"[L1][FailurePredictor] Se esperaba HistorialEjecucion, "
                f"recibido {type(registro).__name__}. "
                f"WHY: contrato de tipos estricto. "
                f"WHERE: registrar_historial."
            )
        self._historial[registro.test_id] = registro
        logger.debug(
            f"[L1][FailurePredictor] Historial registrado: "
            f"test_id={registro.test_id}, failures={registro.failures}/{registro.total_runs}. "
            f"WHERE: registrar_historial."
        )

    def predict(
        self,
        target: str,
        complexity: float = 0.0,
        churn: float = 0.0,
        coverage: float = 1.0,
    ) -> RiskScore:
        """Calcula el riesgo de fallo para un target dado.

        Args:
            target: Identificador del elemento a evaluar.
            complexity: Complejidad ciclomatica normalizada [0, 1].
            churn: Ratio de cambios recientes [0, 1].
            coverage: Cobertura de codigo [0, 1] (1 = 100%).

        Returns:
            RiskScore con la probabilidad estimada de fallo.

        Raises:
            ValueError: Si algun parametro numerico esta fuera de [0, 1].
        """
        for nombre, valor in [("complexity", complexity), ("churn", churn), ("coverage", coverage)]:
            if not (0.0 <= valor <= 1.0):
                raise ValueError(
                    f"[L1][FailurePredictor] Parametro '{nombre}'={valor} fuera de rango [0,1]. "
                    f"WHY: invariante de normalizacion. "
                    f"WHERE: predict(target={target})."
                )

        historial = self._historial.get(target)
        tasa_fallo_hist = historial.failure_rate if historial else 0.0
        penalidad_cobertura = 1.0 - coverage

        prob = (
            _PESO_HISTORIAL * tasa_fallo_hist
            + _PESO_COMPLEJIDAD * complexity
            + _PESO_CHURN * churn
            + _PESO_COBERTURA * penalidad_cobertura
        )
        prob = max(0.0, min(1.0, prob))

        detalles = {
            "tasa_historial": tasa_fallo_hist,
            "complejidad": complexity,
            "churn": churn,
            "cobertura": coverage,
            "peso_historial": _PESO_HISTORIAL,
            "peso_complejidad": _PESO_COMPLEJIDAD,
            "peso_churn": _PESO_CHURN,
            "peso_cobertura": _PESO_COBERTURA,
        }

        logger.info(
            f"[L1][FailurePredictor] Prediccion completada: "
            f"target={target}, prob={prob:.4f}, nivel={RiskScore(target=target, probability=prob).nivel}. "
            f"WHY: resultado de analisis multi-factor. "
            f"WHERE: predict."
        )

        return RiskScore(
            target=target,
            probability=prob,
            complexity_score=complexity,
            churn_score=churn,
            coverage_penalty=penalidad_cobertura,
            details=detalles,
            execution_id=self._metadata.execution_id,
        )

    def predecir_lote(self, targets: list[tuple[str, float, float, float]]) -> list[RiskScore]:
        """Ejecuta prediccion en lote para multiples targets.

        Args:
            targets: Lista de tuplas (target, complexity, churn, coverage).

        Returns:
            Lista de RiskScore en el mismo orden de entrada.

        Raises:
            ValueError: Si la lista de targets esta vacia.
        """
        if not targets:
            raise ValueError(
                "[L1][FailurePredictor] Lista de targets vacia. "
                "WHY: no hay elementos que procesar. "
                "WHERE: predecir_lote."
            )
        resultados: list[RiskScore] = []
        for target, comp, churn_val, cov in targets:
            try:
                riesgo = self.predict(target, comp, churn_val, cov)
                resultados.append(riesgo)
            except (ValueError, TypeError) as exc:
                logger.error(
                    f"[L1][FailurePredictor] Error en prediccion de lote para target={target}. "
                    f"WHAT: {exc}. "
                    f"WHY: fallo en calculo de riesgo. "
                    f"WHERE: predecir_lote."
                )
                resultados.append(
                    RiskScore(target=target, probability=0.5, details={"error": str(exc)})
                )
        return resultados
