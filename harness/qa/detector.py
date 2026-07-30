"""L2 — VisualAnomalyDetector: Deteccion de anomalias visuales y de patrones.

Analiza resultados de ejecucion, trazas, logs y reportes para identificar
patrones anomalos usando tecnicas estadisticas y de procesamiento de senales.

Tipos de anomalia detectados:
- Picos en duracion de ejecucion (outliers temporales)
- Caidas abruptas en tasa de aprobacion
- Patrones de fallo correlacionados (modo comun de fallo)
- Desviacion en cobertura respecto a linea base

Example:
    detector = VisualAnomalyDetector()
    reporte = detector.scan(
        resultados={"test_login": 0.95, "test_logout": 0.45}
    )
    for a in reporte.anomalies:
        print(f"[{a.tipo.name}] {a.descripcion} (severidad={a.severidad:.2f})")
"""

from __future__ import annotations

import logging
import statistics
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum, auto
from uuid import uuid4

from harness.qa import QALayer, QAMetadata

logger = logging.getLogger(__name__)

# ── Umbrales de deteccion ─────────────────────────────────────────────────────

_Z_SCORE_ANOMALO = 2.0  # Desviaciones estandar para considerar anomalo
_TASA_MINIMA_ESPERADA = 0.80  # Minima tasa de aprobacion esperada
_VENTANA_MINIMA = 3  # Minimo de puntos para calcular desviacion


class AnomalyType(Enum):
    """Tipologia de anomalias detectables por el pipeline L2."""

    DURATION_SPIKE = auto()  # Pico anomalo en duracion
    APPROVAL_DROP = auto()  # Caida en tasa de aprobacion
    PATTERN_SHIFT = auto()  # Cambio en patron de ejecucion
    COVERAGE_DRIFT = auto()  # Desviacion en cobertura
    CORRELATED_FAILURE = auto()  # Modo comun de fallo
    NOISE_FLOOR = auto()  # Ruido de fondo elevado


@dataclass(frozen=True)
class AnomalyFinding:
    """Hallazgo individual de anomalia.

    Args:
        tipo: Tipo de anomalia detectada.
        severidad: Valor continuo [0, 1] indicando gravedad.
        descripcion: Texto descriptivo del hallazgo.
        ubicacion: Contexto donde se detecto (test, modulo, traza).
        valor_observado: Valor concreto que disparo la alerta.
        valor_esperado: Valor de referencia o linea base.
        metadata: Metadatos QA de la capa L2.
    """

    tipo: AnomalyType
    severidad: float
    descripcion: str
    ubicacion: str
    valor_observado: float
    valor_esperado: float
    metadata: QAMetadata | None = None

    def __post_init__(self) -> None:
        """Valida rango de severidad."""
        if not (0.0 <= self.severidad <= 1.0):
            object.__setattr__(self, "severidad", max(0.0, min(1.0, self.severidad)))
            logger.warning(
                f"[L2][AnomalyFinding] severidad fuera de rango en {self.ubicacion}. "
                f"WHAT: normalizado a {self.severidad}. "
                f"WHY: garantizar invariante [0,1]. "
                f"WHERE: __post_init__."
            )


@dataclass(frozen=True)
class AnomalyReport:
    """Reporte completo de deteccion de anomalias.

    Args:
        anomalies: Lista de hallazgos individuales.
        total_checks: Cantidad de elementos analizados.
        anomaly_rate: Proporcion de anomalias sobre total chequeado.
        scan_id: Identificador unico del escaneo.
        ejecutado_en: Marca de tiempo ISO de ejecucion.
    """

    anomalies: tuple[AnomalyFinding, ...]
    total_checks: int
    anomaly_rate: float
    scan_id: str = field(default_factory=lambda: uuid4().hex[:12])
    ejecutado_en: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    @property
    def es_critico(self) -> bool:
        """Indica si hay anomalias con severidad > 0.8."""
        return any(a.severidad > 0.8 for a in self.anomalies)

    @property
    def resumen(self) -> dict[str, int]:
        """Resumen de anomalias agrupadas por tipo."""
        resumen: dict[str, int] = {}
        for a in self.anomalies:
            resumen[a.tipo.name] = resumen.get(a.tipo.name, 0) + 1
        return resumen


class VisualAnomalyDetector:
    """Detector visual de anomalias en resultados de ejecucion.

    Analiza secuencias de metricas, trazas y reportes para identificar
    patrones fuera de lo esperado usando metodos estadisticos.

    Args:
        metadata: Metadatos opcionales para la capa L2.
        z_score_threshold: Umbral de desviacion para considerar anomalo.
    """

    def __init__(
        self,
        metadata: QAMetadata | None = None,
        z_score_threshold: float = _Z_SCORE_ANOMALO,
    ) -> None:
        """Inicializa el detector con configuracion de umbrales."""
        self._metadata = metadata or QAMetadata(
            layer=QALayer.L2_DETECTOR,
            version="1.0.0",
            timestamp_iso=datetime.now(timezone.utc).isoformat(),
            execution_id=uuid4().hex[:12],
        )
        self._z_score_threshold = z_score_threshold
        logger.info(
            f"[L2][VisualAnomalyDetector] Inicializado. "
            f"WHAT: detector con z_threshold={z_score_threshold}. "
            f"WHY: inicio de capa L2. "
            f"WHERE: VisualAnomalyDetector.__init__."
        )

    def _detectar_outliers_zscore(
        self, valores: list[float], ubicacion: str
    ) -> list[AnomalyFinding]:
        """Detecta outliers usando puntuacion Z.

        Args:
            valores: Lista de valores numericos a analizar.
            ubicacion: Contexto de los valores para el reporte.

        Returns:
            Lista de AnomalyFinding con los outliers detectados.
        """
        hallazgos: list[AnomalyFinding] = []
        if len(valores) < _VENTANA_MINIMA:
            return hallazgos

        try:
            media = statistics.mean(valores)
            desviacion = statistics.stdev(valores)
        except statistics.StatisticsError as exc:
            logger.warning(
                f"[L2][VisualAnomalyDetector] No se pudo calcular estadisticas "
                f"para {ubicacion}: {exc}. "
                f"WHY: datos insuficientes o varianza cero. "
                f"WHERE: _detectar_outliers_zscore."
            )
            return hallazgos

        if desviacion == 0.0:
            return hallazgos

        for idx, valor in enumerate(valores):
            z_score = abs(valor - media) / desviacion
            if z_score > self._z_score_threshold:
                severidad = min(1.0, (z_score - self._z_score_threshold) / 3.0)
                hallazgos.append(
                    AnomalyFinding(
                        tipo=AnomalyType.DURATION_SPIKE,
                        severidad=severidad,
                        descripcion=(
                            f"Outlier Z-score={z_score:.2f} en indice {idx} "
                            f"(valor={valor:.4f}, media={media:.4f})"
                        ),
                        ubicacion=f"{ubicacion}[{idx}]",
                        valor_observado=valor,
                        valor_esperado=media,
                        metadata=self._metadata,
                    )
                )
        return hallazgos

    def scan(
        self,
        resultados: dict[str, float],
        linea_base: dict[str, float] | None = None,
    ) -> AnomalyReport:
        """Ejecuta escaneo completo de anomalias sobre resultados.

        Args:
            resultados: Diccionario {identificador: metrica} con valores observados.
            linea_base: Diccionario opcional con valores de referencia esperados.

        Returns:
            AnomalyReport con todos los hallazgos del escaneo.

        Raises:
            ValueError: Si resultados esta vacio.
            TypeError: Si resultados no es un diccionario.
        """
        if not isinstance(resultados, dict):
            raise TypeError(
                f"[L2][VisualAnomalyDetector] 'resultados' debe ser dict, "
                f"recibido {type(resultados).__name__}. "
                f"WHY: contrato de tipos estricto. "
                f"WHERE: scan."
            )
        if not resultados:
            raise ValueError(
                "[L2][VisualAnomalyDetector] 'resultados' vacio. "
                "WHY: no hay datos para analizar. "
                "WHERE: scan."
            )

        hallazgos: list[AnomalyFinding] = []
        valores = list(resultados.values())
        identificadores = list(resultados.keys())

        # 1. Deteccion de outliers por Z-score
        outliers = self._detectar_outliers_zscore(valores, "resultados")
        hallazgos.extend(outliers)

        # 2. Deteccion de caidas en tasa de aprobacion
        for ident, valor in resultados.items():
            if linea_base and ident in linea_base:
                esperado = linea_base[ident]
                delta = esperado - valor
                if delta > (1.0 - _TASA_MINIMA_ESPERADA):
                    severidad = min(1.0, delta / esperado) if esperado > 0 else 0.5
                    hallazgos.append(
                        AnomalyFinding(
                            tipo=AnomalyType.APPROVAL_DROP,
                            severidad=severidad,
                            descripcion=(
                                f"Caida en {ident}: observado={valor:.4f}, "
                                f"esperado={esperado:.4f}, delta={delta:.4f}"
                            ),
                            ubicacion=ident,
                            valor_observado=valor,
                            valor_esperado=esperado,
                            metadata=self._metadata,
                        )
                    )
            elif valor < _TASA_MINIMA_ESPERADA:
                # Sin linea base, pero por debajo del umbral minimo
                hallazgos.append(
                    AnomalyFinding(
                        tipo=AnomalyType.APPROVAL_DROP,
                        severidad=1.0 - valor,
                        descripcion=(
                            f"Valor por debajo de umbral minimo en {ident}: "
                            f"{valor:.4f} < {_TASA_MINIMA_ESPERADA}"
                        ),
                        ubicacion=ident,
                        valor_observado=valor,
                        valor_esperado=_TASA_MINIMA_ESPERADA,
                        metadata=self._metadata,
                    )
                )

        # 3. Deteccion de correlacion de fallos (modo comun)
        if len(valores) >= _VENTANA_MINIMA:
            try:
                q1 = statistics.median_low(sorted(valores))
                q3 = statistics.median_high(sorted(valores))
                iqr = q3 - q1
                for idx, valor in enumerate(valores):
                    if iqr > 0 and valor < (q1 - 1.5 * iqr):
                        hallazgos.append(
                            AnomalyFinding(
                                tipo=AnomalyType.CORRELATED_FAILURE,
                                severidad=min(1.0, (q1 - valor) / iqr),
                                descripcion=(
                                    f"Fallo correlacionado en {identificadores[idx]}: "
                                    f"valor={valor:.4f} debajo de Q1-1.5*IQR"
                                ),
                                ubicacion=identificadores[idx],
                                valor_observado=valor,
                                valor_esperado=q1,
                                metadata=self._metadata,
                            )
                        )
            except (statistics.StatisticsError, IndexError) as exc:
                logger.debug(
                    f"[L2][VisualAnomalyDetector] IQR no disponible: {exc}. "
                    f"WHERE: scan->correlacion."
                )

        # 4. Compactacion de hallazgos duplicados por ubicacion+tipo
        vistos: set[tuple[str, str]] = set()
        hallazgos_unicos: list[AnomalyFinding] = []
        for h in hallazgos:
            clave = (h.ubicacion, h.tipo.name)
            if clave not in vistos:
                vistos.add(clave)
                hallazgos_unicos.append(h)

        total = len(resultados)
        tasa_anomalias = len(hallazgos_unicos) / total if total > 0 else 0.0

        logger.info(
            f"[L2][VisualAnomalyDetector] Scan completado: "
            f"{len(hallazgos_unicos)} anomalias en {total} checks "
            f"(tasa={tasa_anomalias:.2%}). "
            f"WHY: finalizacion de analisis L2. "
            f"WHERE: scan."
        )

        return AnomalyReport(
            anomalies=tuple(hallazgos_unicos),
            total_checks=total,
            anomaly_rate=tasa_anomalias,
            scan_id=uuid4().hex[:12],
        )

    def scan_trazas(self, trazas: list[str]) -> AnomalyReport:
        """Analiza trazas de ejecucion en busca de patrones anomalos.

        Args:
            trazas: Lista de lineas de traza o log.

        Returns:
            AnomalyReport con hallazgos sobre las trazas.

        Raises:
            TypeError: Si trazas no es una lista.
        """
        if not isinstance(trazas, list):
            raise TypeError(
                f"[L2][VisualAnomalyDetector] 'trazas' debe ser list, "
                f"recibido {type(trazas).__name__}. "
                f"WHY: contrato de tipos estricto. "
                f"WHERE: scan_trazas."
            )
        # Normalizamos trazas a metricas de longitud para deteccion
        metricas = {f"traza_{i}": len(t) for i, t in enumerate(trazas) if t}
        if not metricas:
            logger.info("[L2][VisualAnomalyDetector] No hay trazas no vacias para analizar.")
            return AnomalyReport(anomalies=(), total_checks=0, anomaly_rate=0.0)
        return self.scan(metricas)
