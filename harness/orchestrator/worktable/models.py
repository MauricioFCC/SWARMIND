"""Modelos de datos de la Mesa de Trabajo (Worktable).

Submodulo del paquete :mod:`harness.orchestrator.worktable`.

Contiene los enums y dataclasses del debate multi-agente y del modo
creativo, extraidos de forma mecanica desde ``worktable.py``
(regla AGR: archivos < 500 lineas).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class CreativePhase(str, Enum):
    """Fases del proceso creativo ReDNA."""
    DIVERGENT = "divergent"       # Generar N ideas libremente
    CONVERGENT = "convergent"     # Seleccionar bajo restricciones
    INTEGRATION = "integration"   # Integrar ideas seleccionadas


@dataclass
class CreativeIdea:
    """
    Idea generada en el proceso creativo.

    Attributes:
        content: Contenido de la idea.
        agent: Agente que la genero.
        phase: Fase en la que se genero.
        novelty: Puntaje de novedad (0-1).
        feasibility: Puntaje de factibilidad (0-1).
        selected: Si fue seleccionada para integracion.
    """
    content: str
    agent: str
    phase: CreativePhase = CreativePhase.DIVERGENT
    novelty: float = 0.0
    feasibility: float = 0.5
    selected: bool = False


@dataclass
class CreativeConfig:
    """
    Configuracion del proceso creativo.

    Attributes:
        topology: Topologia de comunicacion (sparse, random, small-world).
        divergence_pressure: Presion para opiniones disidentes (0-1).
        independence_rounds: Rondas de generacion aislada antes de compartir.
        authority_penalty: Penalizar deferencia a agente senior.
        num_ideas: Numero de ideas a generar en fase divergente.
    """
    topology: str = "sparse"
    divergence_pressure: float = 0.3
    independence_rounds: int = 2
    authority_penalty: float = 0.1
    num_ideas: int = 5


class DebateRound(Enum):
    """Rondas del debate estructurado."""
    OPENING = "opening"          # Ronda 1: Postura inicial
    CRITIQUE = "critique"        # Ronda 2: Critica cruzada
    REFINEMENT = "refinement"    # Ronda 3: Refinamiento
    COMPENDIUM = "compendium"    # Final: Sintesis


@dataclass
class AgentPosition:
    """
    Postura de un agente en el debate.

    Attributes:
        agent_name: Nombre del principio/atributo.
        stance: Postura (a favor/en contra/neutral).
        arguments: Argumentos principales.
        concerns: Preocupaciones sobre otras posturas.
        vote: Voto final (aceptar/rechazar/abstencion).
    """
    agent_name: str
    stance: str = "neutral"
    arguments: list[str] = field(default_factory=list)
    concerns: list[str] = field(default_factory=list)
    vote: str = "abstencion"


@dataclass
class Compendium:
    """
    Compendio final del debate.

    Attributes:
        summary: Resumen ejecutivo de la decision.
        agreements: Puntos de acuerdo entre agentes.
        trade_offs: Compromisos identificados.
        rejected: Opciones rechazadas y por que.
        recommendations: Recomendaciones finales.
        participants: Agentes participantes.
        rounds: Numero de rondas realizadas.
    """
    summary: str = ""
    agreements: list[str] = field(default_factory=list)
    trade_offs: list[dict[str, str]] = field(default_factory=list)
    rejected: list[str] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)
    participants: list[str] = field(default_factory=list)
    rounds: int = 0
