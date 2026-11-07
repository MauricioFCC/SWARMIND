"""QA Pipeline 5-Capas — Sistema de Calidad Evolutivo para Swarmind.

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

# ── Configuracion global de logging estructurado ──────────────────────────────

logger: logging.Logger = logging.getLogger(__name__)

# Tipos base del stack (modulo sin dependencias: rompe el ciclo de imports).
# ── Exportaciones publicas de todas las capas ─────────────────────────────────
from harness.qa.agent import AgentResult, AutonomousTestAgent, MCPCommand
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
from harness.qa.types import QAContext, QALayer, QAMetadata, QASeverity

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
