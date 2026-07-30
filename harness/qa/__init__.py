"""QA Pipeline 5-Capas — Sistema de Calidad Agentico para Swarmind.

Implementa el stack completo de madurez QA segun auditoria de 50 equipos (Julio 2026):

L1 — AI/ML: FailurePredictor (prediccion de fallos antes de ejecutar)
L2 — Neural Networks: VisualAnomalyDetector (deteccion de patrones anomalos)
L3 — Gen AI: TestCaseGenerator (generacion de casos con guardrails anti-alucinacion)
L4 — AI Agents: AutonomousTestAgent (ejecucion autonoma con MCP)
L5 — Swarmind AI: QAOrchestrator (orquestacion extremo a extremo)

Referencia: ToolGuardian arXiv:2607.21835, IMACS arXiv:2607.25446

Uso tipico:
    from harness.qa import FailurePredictor, VisualAnomalyDetector
    from harness.qa import TestCaseGenerator, AutonomousTestAgent, QAOrchestrator

    riesgo = FailurePredictor().predict("tests/test_auth.py")
    anomalias = VisualAnomalyDetector().scan(resultados)
    casos = TestCaseGenerator().generate(especificacion)
    agente = AutonomousTestAgent().run(casos)
    reporte = QAOrchestrator().execute(componente="auth")
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any

# ── Configuracion global de logging estructurado ──────────────────────────────

logger: logging.Logger = logging.getLogger(__name__)


class QASeverity(Enum):
    """Severidad de un hallazgo en el pipeline de calidad."""

    CRITICAL = auto()
    HIGH = auto()
    MEDIUM = auto()
    LOW = auto()
    INFO = auto()


class QALayer(Enum):
    """Identificadores de capa en el stack QA 5-capas."""

    L1_PREDICTOR = auto()
    L2_DETECTOR = auto()
    L3_GENERATOR = auto()
    L4_AGENT = auto()
    L5_ORCHESTRATOR = auto()


@dataclass(frozen=True)
class QAMetadata:
    """Metadatos estandar para todo resultado del pipeline QA.

    Args:
        layer: Capa que produjo el resultado.
        version: Version del modulo que genero el resultado.
        timestamp_iso: Marca de tiempo ISO 8601.
        execution_id: Identificador unico de ejecucion.
        extra: Datos adicionales arbitrarios.

    Returns:
        QAMetadata inmutable con trazabilidad completa.
    """

    layer: QALayer
    version: str
    timestamp_iso: str
    execution_id: str
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class QAContext:
    """Contexto compartido entre capas del pipeline.

    Propaga informacion de ejecucion, configuracion y estado
    a traves de las 5 capas sin acoplamiento directo.

    Args:
        target: Componente o modulo bajo prueba.
        config: Diccionario de configuracion arbitraria.
        metadata: Metadatos de la ejecucion actual.
        tags: Etiquetas para filtrado y segmentacion.
    """

    target: str
    config: dict[str, Any] = field(default_factory=dict)
    metadata: QAMetadata | None = None
    tags: set[str] = field(default_factory=set)


# ── Exportaciones publicas de todas las capas ─────────────────────────────────

from harness.qa.agent import AgentResult, AutonomousTestAgent
from harness.qa.detector import (
    AnomalyReport,
    AnomalyType,
    VisualAnomalyDetector,
)
from harness.qa.generator import (
    GuardrailResult,
    TestCaseGenerator,
    TestSuite,
)
from harness.qa.orchestrator import (
    OrchestrationReport,
    PipelineStatus,
    QAOrchestrator,
)
from harness.qa.predictor import (
    FailurePredictor,
    HistorialEjecucion,
    RiskScore,
)

__all__ = [
    "AgentResult",
    "AnomalyReport",
    "AnomalyType",
    # L4 — AutonomousTestAgent
    "AutonomousTestAgent",
    # L1 — FailurePredictor
    "FailurePredictor",
    "GuardrailResult",
    "HistorialEjecucion",
    "MCPCommand",
    "OrchestrationReport",
    "PipelineStatus",
    "QAContext",
    "QALayer",
    # Dataclasses base
    "QAMetadata",
    # L5 — QAOrchestrator
    "QAOrchestrator",
    # Enums
    "QASeverity",
    "RiskScore",
    # L3 — TestCaseGenerator
    "TestCaseGenerator",
    "TestSuite",
    # L2 — VisualAnomalyDetector
    "VisualAnomalyDetector",
]
