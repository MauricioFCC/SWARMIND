"""AIFactory core — clase base ``AIFactory``.

Contiene el estado, propiedades publicas, gestion de metricas y el
constructor de resultados. Los metodos de ejecucion por capa viven en
``_LayerExecutorMixin`` (layers.py, incluye ``process_stream``) y los
pipelines en ``_PipelineMixin`` (pipeline.py).

El nombre de logger se fija en ``harness.aifactory.factory`` para
preservar la identidad del logger del modulo original.
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Any

from harness.aifactory.factory_types import (
    EvalReport,
    FactoryConfig,
    FactoryResult,
    FactoryStatus,
    LayerTrace,
)

from .layers import _LayerExecutorMixin
from .pipeline import _PipelineMixin

logger = logging.getLogger("harness.aifactory.factory")


class AIFactory(_PipelineMixin, _LayerExecutorMixin):
    """Orquestador del pipeline AI Factory de 7 capas.

    Coordina la ejecucion secuencial de las capas de inteligencia,
    conocimiento, ejecucion, integracion, confianza y evaluacion.
    Implementa el patron Pipeline con trazabilidad completa,
    compensacion de fallos y metricas en tiempo real.

    La arquitectura sigue el principio de Separacion de Concerns:
    cada capa es independiente y se comunica via el contexto del
    pipeline, permitiendo reemplazo individual sin afectar las demas.

    Attributes:
        config: Configuracion activa del factory.
        status: Estado actual del pipeline.
    """

    def __init__(self, config: FactoryConfig | None = None) -> None:
        """Inicializa el AIFactory con configuracion opcional.

        Si no se provee config, se usa FactoryConfig con valores
        por defecto: guardrails y evals habilitados, max_retries=3.

        Args:
            config: Configuracion del factory. Si es None, usa defaults.
        """
        self._config: FactoryConfig = config or FactoryConfig()
        self._status: FactoryStatus = FactoryStatus.IDLE
        self._metrics: dict[str, Any] = {
            "total_pipelines": 0,
            "completed": 0,
            "failed": 0,
            "blocked": 0,
            "compensated": 0,
            "total_latency_ms": 0.0,
            "layer_metrics": {},
        }
        self._lock: threading.Lock = threading.Lock()
        self._is_locked: bool = False
        logger.info(
            "[AIFactory] Inicializado | config=guardrails:%s evals:%s "
            "max_retries:%d",
            self._config.guardrails_enabled,
            self._config.evals_enabled,
            self._config.max_retries,
        )

    # ------------------------------------------------------------------
    # Propiedades publicas
    # ------------------------------------------------------------------

    @property
    def config(self) -> FactoryConfig:
        """Configuracion activa del factory (inmutable).

        Returns:
            FactoryConfig con la configuracion actual.
        """
        return self._config

    @property
    def status(self) -> FactoryStatus:
        """Estado actual del pipeline.

        Returns:
            FactoryStatus indicando la etapa actual de ejecucion.
        """
        return self._status

    # ------------------------------------------------------------------
    # Metodos de gestion de estado
    # ------------------------------------------------------------------

    def get_status(self) -> FactoryStatus:
        """Retorna el estado actual del pipeline.

        Util para monitoreo externo, health checks y dashboards.

        Returns:
            FactoryStatus actual del orquestador.
        """
        return self._status

    def get_metrics(self) -> dict[str, Any]:
        """Retorna las metricas acumuladas de todas las ejecuciones.

        Incluye conteo de pipelines completados, fallidos, bloqueados,
        compensados, latencia total y metricas desglosadas por capa.

        Returns:
            Diccionario con metricas del factory.
        """
        return dict(self._metrics)

    def reset(self) -> None:
        """Reinicia el estado del factory a valores iniciales.

        Resetea el estado a IDLE, libera el lock y limpia las metricas
        acumuladas. Util para comenzar un nuevo ciclo de ejecuciones
        sin crear una nueva instancia.

        No afecta la configuracion activa (self._config).
        """
        self._status = FactoryStatus.IDLE
        self._lock = False
        self._metrics = {
            "total_pipelines": 0,
            "completed": 0,
            "failed": 0,
            "blocked": 0,
            "compensated": 0,
            "total_latency_ms": 0.0,
            "layer_metrics": {},
        }
        logger.info("[AIFactory] Estado reseteado a IDLE.")

    # ------------------------------------------------------------------
    # Metodos auxiliares
    # ------------------------------------------------------------------

    @staticmethod
    def _build_result(
        input_text: str,
        output: str | None,
        status: FactoryStatus,
        layers: list[LayerTrace],
        pipeline_start: float,
        eval_report: EvalReport | None = None,
        guardrail_results: list[dict[str, Any]] | None = None,
        pipeline_id: str = "",
        error: str | None = None,
    ) -> FactoryResult:
        """Construye un FactoryResult con los parametros dados.

        Args:
            input_text: Texto de entrada.
            output: Texto de salida (puede ser None si fallo).
            status: Estado final del pipeline.
            layers: Lista de trazas de capas.
            pipeline_start: Timestamp de inicio del pipeline.
            eval_report: Reporte de evaluacion.
            guardrail_results: Resultados de guardrails.
            pipeline_id: Identificador del pipeline.
            error: Mensaje de error global.

        Returns:
            FactoryResult completo y congelado.
        """
        total_latency = (time.perf_counter() - pipeline_start) * 1000
        return FactoryResult(
            input=input_text,
            output=output,
            status=status,
            layers=layers,
            latency_ms=round(total_latency, 2),
            eval_report=eval_report,
            guardrail_results=guardrail_results or [],
            pipeline_id=pipeline_id,
            error=error,
        )
