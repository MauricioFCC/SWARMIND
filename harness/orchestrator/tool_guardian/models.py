"""ToolGuardian models — enums y dataclasses de seguridad.

Extraccion mecanica del modulo original
``harness/orchestrator/tool_guardian.py`` (sin cambios de logica
ni firmas): ToolRiskLevel, CharacterizationStage, ToolPolicy y
CharacterizationResult.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class ToolRiskLevel(str, Enum):
    """Nivel de riesgo asignado a una tool tras el pipeline de caracterizacion.

    SAFE: Sin riesgo detectado, puede ejecutarse libremente.
    SUSPICIOUS: Comportamiento sospechoso, requiere supervision.
    MALICIOUS: Comportamiento malicioso confirmado, bloqueado.
    """

    SAFE = "safe"
    SUSPICIOUS = "suspicious"
    MALICIOUS = "malicious"


class CharacterizationStage(str, Enum):
    """Etapas del progressive characterization pipeline (arXiv:2607.21835)."""

    DESCRIPTION = "description"
    SYSCALL = "syscall"
    MOCK_EXECUTION = "mock_execution"
    SOURCE_ANALYSIS = "source_analysis"


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class ToolPolicy:
    """Politica de seguridad declarativa para una categoria de tool.

    Attributes:
        name: Nombre de la categoria (filesystem, network, shell, etc.).
        allowed_actions: Lista de acciones permitidas.
        blocked_actions: Lista de acciones bloqueadas explicitamente.
        required_capabilities: Capacidades que debe tener el agente.
        max_execution_time: Tiempo maximo de ejecucion en segundos.
        requires_human_approval: Si requiere aprobacion humana.
        allowed_domains: Dominios permitidos (solo network).
        allowed_paths: Rutas permitidas (solo filesystem).
    """

    name: str
    allowed_actions: list[str] = field(default_factory=list)
    blocked_actions: list[str] = field(default_factory=list)
    required_capabilities: list[str] = field(default_factory=list)
    max_execution_time: int = 30
    requires_human_approval: bool = False
    allowed_domains: list[str] = field(default_factory=list)
    allowed_paths: list[str] = field(default_factory=list)


@dataclass
class CharacterizationResult:
    """Resultado de una etapa del pipeline de caracterizacion.

    Attributes:
        stage: Etapa del pipeline.
        passed: True si la etapa fue superada sin hallazgos.
        score: Puntaje de riesgo de la etapa (0 = seguro, >0 = riesgo).
        evidence: Evidencia textual del analisis.
        details: Detalles adicionales estructurados.
    """

    stage: CharacterizationStage
    passed: bool = True
    score: float = 0.0
    evidence: list[str] = field(default_factory=list)
    details: dict[str, Any] = field(default_factory=dict)
