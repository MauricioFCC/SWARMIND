"""
Mesa de Trabajo — Multi-agent software quality debate system.

Organiza un debate estructurado entre N agentes especializados en diferentes
atributos de calidad de software (SoC, Low Coupling, High Cohesion, etc.).

Cada agente representa un principio y defiende su perspectiva.
Un moderador (Worktable) orquesta el debate en rondas.
Al final se produce un compendio con las decisiones acordadas.

Flujo:
1. RONDA 1: Cada agente presenta su postura inicial
2. RONDA 2: Los agentes se critican entre si
3. RONDA 3: Refinamiento de posturas
4. COMPENDIO: Sintesis final con acuerdos y trade-offs

Usage:
    wt = Worktable()
    compendio = wt.debate("Disenar una API REST para un sistema de pagos")
    print(compendio.summary)

Este modulo se convirtio en paquete (regla AGR < 500 lineas/archivo):
  - ``models.py``: enums y dataclasses del debate y modo creativo.
  - ``profiles.py``: registro de expertos (AGENT_PROFILES).
  - ``creative.py``: CreativeWorktable (pipeline ReDNA).
  - ``core.py``: Worktable (moderador del debate).
  - ``epic.py``: EpicMode (workflows multi-paso).

Todos los simbolos publicos del modulo original se re-exportan aqui, por lo
que los imports existentes ``from harness.orchestrator.worktable import
Worktable`` siguen funcionando identicos.
"""

from __future__ import annotations

import logging

from .core import Worktable
from .creative import CreativeWorktable
from .epic import EpicMode
from .models import (
    AgentPosition,
    Compendium,
    CreativeConfig,
    CreativeIdea,
    CreativePhase,
    DebateRound,
)
from .profiles import AGENT_PROFILES

logger = logging.getLogger(__name__)

__all__ = [
    "AGENT_PROFILES",
    "AgentPosition",
    "Compendium",
    "CreativeConfig",
    "CreativeIdea",
    "CreativePhase",
    "CreativeWorktable",
    "DebateRound",
    "EpicMode",
    "Worktable",
    "logger",
]
