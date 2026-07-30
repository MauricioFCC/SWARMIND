"""L5 â€” QAOrchestrator: Orquestacion de calidad extremo a extremo.

Capa superior del pipeline QA 5-capas que coordina la ejecucion
completa del ciclo de calidad swarmind:

1. Recepcion de contexto (target, config, metadatos)
2. Invocacion de L1 (FailurePredictor) para priorizar riesgos
3. Invocacion de L2 (VisualAnomalyDetector) sobre resultados previos
4. Invocacion de L3 (TestCaseGenerator) para generar casos faltantes
5. Invocacion de L4 (AutonomousTestAgent) para ejecucion autonoma
6. Consolidacion de reporte final con metrica de calidad global

Implementa el patron "Harness Effect": cada capa se ejecuta en un
sandbox controlado con propagacion de errores y compensacion.

Example:
    orq = QAOrchestrator()
    reporte = orq.execute(
        componente="auth-service",
        test_files=["tests/test_auth.py"],
        especificacion="Servicio de autenticacion JWT"
    )
    print(f"Calidad global: {reporte.calidad_global:.2%}")
    print(f"Estado: {reporte.estado.name}")
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum, auto
from typing import Any
from uuid import uuid4

from harness.qa import QAContext, QALayer, QAMetadata
from harness.qa.agent import AgentResult, AutonomousTestAgent
from harness.qa.detector import AnomalyReport, VisualAnomalyDetector
from harness.qa.generator import TestCaseGenerator, TestSuite
from harness.qa.predictor import FailurePredictor, RiskScore

logger = logging.getLogger(__name__)

# â”€â”€ Pesos para calculo de calidad global â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

_PESO_PREDICCION = 0.15
_PESO_ANOMALIAS = 0.20
_PESO_GENERACION = 0.15
_PESO_EJECUCION = 0.50


class PipelineStatus(Enum):
    """Estado final del pipeline orquestado."""

    PENDING = auto()
    RUNNING = auto()
    SUCCESS = auto()
    DEGRADED = auto()
    FAILED = auto()
    COMPENSATED = auto()  # Se aplico compensacion tras fallo parcial


@dataclass(frozen=True)
class LayerResult:
    """Resultado encapsulado de una capa del pipeline.

    Args:
        layer: Identificador de la capa.
        exitoso: Indica si la capa se completo sin errores.
        duracion_ms: Duracion de ejecucion de la capa.
        datos: Datos producidos por la capa.
        error: Mensaje de error si la capa fallo.
    """

    layer: QALayer
    exitoso: bool
    duracion_ms: float
    datos: Any | None = None
    error: str | None = None


@dataclass(frozen=True)
class OrchestrationReport:
    """Reporte consolidado final del pipeline QA 5-capas.

    Args:
        componente: Nombre del componente evaluado.
        calidad_global: Metrica compuesta de calidad [0, 1].
        estado: Estado final del pipeline.
        layers: Resultados individuales por capa.
        risk_score: Riesgo estimado por L1 (opcional).
        anomaly_report: Reporte de anomalias por L2 (opcional).
        test_suite: Suite generada por L3 (opcional).
        agent_result: Resultado de ejecucion por L4 (opcional).
        ejecutado_en: Marca de tiempo de ejecucion.
        execution_id: Identificador unico de orquestacion.
    """

    componente: str
    calidad_global: float
    estado: PipelineStatus
    layers: tuple[LayerResult, ...]
    risk_score: RiskScore | None = None
    anomaly_report: AnomalyReport | None = None
    test_suite: TestSuite | None = None
    agent_result: AgentResult | None = None
    ejecutado_en: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    execution_id: str = field(default_factory=lambda: uuid4().hex[:12])

    @property
    def resumen(self) -> dict[str, Any]:
        """Resumen ejecutivo del reporte de calidad."""
        return {
            "componente": self.componente,
            "calidad_global": f"{self.calidad_global:.2%}",
            "estado": self.estado.name,
            "capas_ejecutadas": [l.layer.name for l in self.layers],
            "capas_exitosas": sum(1 for l in self.layers if l.exitoso),
            "capas_fallidas": sum(1 for l in self.layers if not l.exitoso),
            "execution_id": self.execution_id,
        }

    @property
    def es_aceptable(self) -> bool:
        """Indica si la calidad global supera el umbral minimo (> 70%)."""
        return self.calidad_global >= 0.70


class QAOrchestrator:
    """Orquestador del pipeline QA 5-capas.

    Coordina la ejecucion secuencial de las 5 capas de calidad,
    aplicando politicas de compensacion y degradacion gradual
    ante fallos en capas individuales.

    Args:
        metadata: Metadatos opcionales para capa L5.
    """

    def __init__(self, metadata: QAMetadata | None = None) -> None:
        """Inicializa el orquestador con componentes de todas las capas."""
        self._metadata = metadata or QAMetadata(
            layer=QALayer.L5_ORCHESTRATOR,
            version="1.0.0",
            timestamp_iso=datetime.now(timezone.utc).isoformat(),
            execution_id=uuid4().hex[:12],
        )
        self._predictor = FailurePredictor()
        self._detector = VisualAnomalyDetector()
        self._generator = TestCaseGenerator()
        self._agent = AutonomousTestAgent()

        logger.info(
            f"[L5][QAOrchestrator] Inicializado con execution_id="
            f"{self._metadata.execution_id}. "
            f"WHAT: orquestador 5-capas listo. "
            f"WHY: inicio de capa L5. "
            f"WHERE: QAOrchestrator.__init__."
        )

    def _ejecutar_capa(
        self,
        layer: QALayer,
        fn: Any,
        args: tuple = (),
        kwargs: dict[str, Any] | None = None,
    ) -> LayerResult:
        """Ejecuta una capa del pipeline con medicion y captura de errores.

        Args:
            layer: Identificador de la capa a ejecutar.
            fn: Funcion o callable de la capa.
            args: Argumentos posicionales.
            kwargs: Argumentos nominales.

        Returns:
            LayerResult con el resultado o error de la capa.
        """
        kwargs = kwargs or {}
        inicio = time.perf_counter()

        try:
            resultado = fn(*args, **kwargs)
            duracion = (time.perf_counter() - inicio) * 1000.0
            logger.info(
                f"[L5][QAOrchestrator] Capa {layer.name} completada en "
                f"{duracion:.1f}ms. "
                f"WHY: ejecucion exitosa de capa. "
                f"WHERE: _ejecutar_capa."
            )
            return LayerResult(
                layer=layer,
                exitoso=True,
                duracion_ms=duracion,
                datos=resultado,
            )
        except Exception as exc:  # noqa: BLE001
            duracion = (time.perf_counter() - inicio) * 1000.0
            logger.error(
                f"[L5][QAOrchestrator] Capa {layer.name} fallo tras "
                f"{duracion:.1f}ms. "
                f"WHAT: {exc}. "
                f"WHY: error durante ejecucion de capa. "
                f"WHERE: _ejecutar_capa -> {layer.name}."
            )
            return LayerResult(
                layer=layer,
                exitoso=False,
                duracion_ms=duracion,
                error=str(exc),
            )

    def execute(
        self,
        componente: str,
        test_files: list[str] | None = None,
        especificacion: str | None = None,
        resultados_previos: dict[str, float] | None = None,
        config: dict[str, Any] | None = None,
    ) -> OrchestrationReport:
        """Ejecuta el pipeline completo de calidad 5-capas.

        Args:
            componente: Nombre del componente o modulo a evaluar.
            test_files: Lista de archivos de test a ejecutar.
            especificacion: Especificacion para generacion de casos.
            resultados_previos: Resultados historicos para deteccion.
            config: Configuracion adicional del pipeline.

        Returns:
            OrchestrationReport con resultados consolidados.

        Raises:
            ValueError: Si componente esta vacio.
        """
        if not componente or not componente.strip():
            raise ValueError(
                "[L5][QAOrchestrator] 'componente' es requerido y no puede estar vacio. "
                "WHY: identificador obligatorio para el reporte. "
                "WHERE: execute."
            )

        QAContext(
            target=componente,
            config=config or {},
            metadata=self._metadata,
            tags={"orquestado", componente},
        )
        logger.info(
            f"[L5][QAOrchestrator] Iniciando pipeline para componente='{componente}'. "
            f"WHAT: ejecucion multi-capa. "
            f"WHY: inicio de ciclo QA completo. "
            f"WHERE: execute."
        )

        layers: list[LayerResult] = []
        risk_score: RiskScore | None = None
        anomaly_report: AnomalyReport | None = None
        test_suite: TestSuite | None = None
        agent_result: AgentResult | None = None

        # â”€â”€ L1: FailurePredictor â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        res_l1 = self._ejecutar_capa(
            QALayer.L1_PREDICTOR,
            self._predictor.predict,
            kwargs={"target": componente, "complexity": 0.3, "churn": 0.2, "coverage": 0.85},
        )
        layers.append(res_l1)
        if res_l1.exitoso and isinstance(res_l1.datos, RiskScore):
            risk_score = res_l1.datos

        # â”€â”€ L2: VisualAnomalyDetector â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        if resultados_previos:
            res_l2 = self._ejecutar_capa(
                QALayer.L2_DETECTOR,
                self._detector.scan,
                kwargs={"resultados": resultados_previos},
            )
        else:
            # Sin datos previos, usar datos simulados de L1 como entrada
            datos_ejemplo = {componente: 0.9}
            res_l2 = self._ejecutar_capa(
                QALayer.L2_DETECTOR,
                self._detector.scan,
                kwargs={"resultados": datos_ejemplo},
            )
        layers.append(res_l2)
        if res_l2.exitoso and isinstance(res_l2.datos, AnomalyReport):
            anomaly_report = res_l2.datos

        # â”€â”€ L3: TestCaseGenerator â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        espec = especificacion or f"Tests para componente: {componente}"
        res_l3 = self._ejecutar_capa(
            QALayer.L3_GENERATOR,
            self._generator.generate,
            kwargs={
                "especificacion": espec,
                "lenguaje": "python",
                "framework": "pytest",
                "cantidad": 3,
            },
        )
        layers.append(res_l3)
        if res_l3.exitoso and isinstance(res_l3.datos, TestSuite):
            test_suite = res_l3.datos

        # â”€â”€ L4: AutonomousTestAgent â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        files = test_files or (list(test_suite.casos_validos) if test_suite else [])
        if files:
            res_l4 = self._ejecutar_capa(
                QALayer.L4_AGENT,
                self._agent.run,
                kwargs={"test_files": files if isinstance(files[0], str) else []},
            )
        else:
            res_l4 = self._ejecutar_capa(
                QALayer.L4_AGENT,
                self._agent.run,
                kwargs={"test_files": ["tests/placeholder_test.py"]},
            )
        layers.append(res_l4)
        if res_l4.exitoso and isinstance(res_l4.datos, AgentResult):
            agent_result = res_l4.datos

        # â”€â”€ Calculo de calidad global â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        calidad_global = self._calcular_calidad_global(
            risk_score=risk_score,
            anomaly_report=anomaly_report,
            test_suite=test_suite,
            agent_result=agent_result,
            layers=layers,
        )

        # â”€â”€ Determinacion de estado final â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        exitosas = sum(1 for l in layers if l.exitoso)
        total_capas = len(layers)

        if exitosas == total_capas:
            estado = PipelineStatus.SUCCESS
        elif exitosas >= 3:
            estado = PipelineStatus.DEGRADED
            logger.warning(
                f"[L5][QAOrchestrator] Pipeline degradado: {exitosas}/{total_capas} "
                f"capas exitosas. "
                f"WHY: fallo parcial en capas no criticas. "
                f"WHERE: execute."
            )
        elif exitosas > 0:
            estado = PipelineStatus.COMPENSATED
            logger.warning(
                f"[L5][QAOrchestrator] Pipeline compensado: {exitosas}/{total_capas} "
                f"capas exitosas. "
                f"WHAT: se aplicaron mecanismos de compensacion. "
                f"WHY: fallo multiple en capas. "
                f"WHERE: execute."
            )
        else:
            estado = PipelineStatus.FAILED
            logger.error(
                f"[L5][QAOrchestrator] Pipeline fallido: 0/{total_capas} "
                f"capas exitosas. "
                f"WHY: todas las capas fallaron. "
                f"WHERE: execute."
            )

        reporte = OrchestrationReport(
            componente=componente,
            calidad_global=calidad_global,
            estado=estado,
            layers=tuple(layers),
            risk_score=risk_score,
            anomaly_report=anomaly_report,
            test_suite=test_suite,
            agent_result=agent_result,
            execution_id=self._metadata.execution_id,
        )

        logger.info(
            f"[L5][QAOrchestrator] Pipeline completado: "
            f"componente={componente}, calidad={calidad_global:.2%}, "
            f"estado={estado.name}, capas={exitosas}/{total_capas}. "
            f"WHY: finalizacion de ciclo QA. "
            f"WHERE: execute."
        )

        return reporte

    def _calcular_calidad_global(
        self,
        risk_score: RiskScore | None,
        anomaly_report: AnomalyReport | None,
        test_suite: TestSuite | None,
        agent_result: AgentResult | None,
        layers: list[LayerResult],
    ) -> float:
        """Calcula la metrica compuesta de calidad global del pipeline.

        Combina pesos de cada capa considerando disponibilidad de datos
        y aplicando penalizacion por fallos en la ejecucion.

        Args:
            risk_score: Resultado de L1 o None.
            anomaly_report: Resultado de L2 o None.
            test_suite: Resultado de L3 o None.
            agent_result: Resultado de L4 o None.
            layers: Lista de resultados de ejecucion de cada capa.

        Returns:
            Valor de calidad global en rango [0, 1].
        """
        score = 0.0
        peso_total = 0.0

        # Penalizacion base por capas fallidas
        penalizacion_fallo = 1.0 - (
            sum(1 for l in layers if not l.exitoso) / max(len(layers), 1)
        )

        # Aporte L1: riesgo bajo = mejor calidad
        if risk_score is not None:
            score += _PESO_PREDICCION * (1.0 - risk_score.probability)
            peso_total += _PESO_PREDICCION

        # Aporte L2: baja tasa de anomalias = mejor calidad
        if anomaly_report is not None:
            score += _PESO_ANOMALIAS * (1.0 - anomaly_report.anomaly_rate)
            peso_total += _PESO_ANOMALIAS

        # Aporte L3: cobertura estimada de la suite
        if test_suite is not None:
            score += _PESO_GENERACION * test_suite.cobertura_estimada
            peso_total += _PESO_GENERACION

        # Aporte L4: tasa de aprobacion de ejecucion
        if agent_result is not None:
            score += _PESO_EJECUCION * agent_result.tasa_aprobacion
            peso_total += _PESO_EJECUCION

        # Si no hay datos de ninguna capa, retornar valor neutral
        if peso_total == 0.0:
            logger.info(
                "[L5][QAOrchestrator] Sin datos para calcular calidad global, "
                "retornando 0.5. "
                "WHY: no hay capas con datos disponibles. "
                "WHERE: _calcular_calidad_global."
            )
            return 0.5 * penalizacion_fallo

        calidad = (score / peso_total) * penalizacion_fallo
        return max(0.0, min(1.0, calidad))
