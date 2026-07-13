"""
agent_selector.py — Seleccion inteligente de agentes por tarea.

En lugar de lanzar SIEMPRE builder+scientist+guardian (SWARM),
analiza la tarea y selecciona SOLO los agentes necesarios.

Esto ahorra tokens, tiempo de ejecucion, y llamadas al LLM.

Niveles de activacion:
  - TRIVIAL: 1 agente (builder o scientist)
  - SIMPLE:  2 agentes (builder+scientist o builder+guardian)
  - MODERATE: 2-3 agentes (builder+scientist+guardian)
  - COMPLEX: 3 agentes (SWARM completo)
  - VERY_COMPLEX: 3+ agentes (SWARM + evolve)
"""

from __future__ import annotations

import re
import logging
from enum import Enum
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


class ActivationLevel(str, Enum):
    """Nivel de activacion de agentes."""
    MINIMAL = "minimal"          # 1 agente
    PAIRED = "paired"            # 2 agentes
    STANDARD = "standard"        # 2-3 agentes
    SWARM = "swarm"              # 3 agentes (builder+scientist+guardian)
    FULL = "full"                # 4+ agentes (incluye evolve)


# Keywords que determinan que agente se necesita
AGENT_KEYWORDS: Dict[str, List[str]] = {
    "builder": [
        "implement", "build", "code", "api", "endpoint", "rust", "go", "python",
        "typescript", "javascript", "web", "mobile", "frontend", "backend",
        "database", "sql", "query", "migracion", "deploy", "docker",
        "algoritmo", "modulo", "funcion", "clase", "refactor", "fix", "bug",
    ],
    "scientist": [
        "research", "investigar", "investiga", "study", "analyze", "analysis",
        "architecture", "design", "pattern", "paper", "algoritmo",
        "ml", "ai", "machine learning", "experiment", "hypothesis",
        "comparar", "evaluar", "proponer", "recomendar",
        "investigacion", "analisis",
    ],
    "guardian": [
        "test", "testing", "coverage", "cobertura", "pruebas",
        "security", "seguridad", "audit", "vulnerabilidad",
        "quality", "calidad", "review", "revisar", "validate",
        "document", "documentar", "docs", "readme",
    ],
    "evolve": [
        "evolve", "improve", "optimize", "optimizar",
        "skill", "cognition", "learn", "aprender",
        "auto-mejora", "self-improve", "evolution",
    ],
}

# Palabras que indican tarea simple (no requiere SWARM)
SIMPLE_INDICATORS: List[str] = [
    "simple", "basico", "rapido", "quick", "rapida",
    "solo una consulta", "duda rapida", "pregunta simple",
    "pequeno cambio", "minor fix",
]

# Palabras que indican tarea compleja (requiere SWARM completo)
COMPLEX_INDICATORS: List[str] = [
    "complejo", "grande", "multi-modulo", "multiples archivos",
    "arquitectura", "sistema completo", "full stack",
    "produccion", "enterprise", "escalable",
    "swarm", "todos los agentes", "full team",
]


class AgentSelector:
    """
    Selecciona los agentes necesarios para una tarea.

    Uso:
        selector = AgentSelector()
        agents = selector.select("implementa API REST en Rust")
        # → ["builder", "guardian"]
    """

    def __init__(self, default_level: ActivationLevel = ActivationLevel.STANDARD):
        self._default_level = default_level

    def select(self, message: str) -> List[str]:
        """
        Selecciona agentes basado en el mensaje.

        Args:
            message: Tarea del usuario.

        Returns:
            Lista de agentes a activar (ordenada por relevancia).
        """
        if not message:
            return ["builder"]

        msg_lower = message.lower()

        # 1. Detectar nivel de activacion
        level = self._detect_level(msg_lower)

        # 2. Puntuar relevancia de cada agente
        scores = self._score_agents(msg_lower)

        # 3. Seleccionar segun nivel
        return self._select_by_level(scores, level)

    def _detect_level(self, msg_lower: str) -> ActivationLevel:
        """Detecta nivel de activacion basado en el mensaje."""
        # Palabras de complejidad
        for w in COMPLEX_INDICATORS:
            if w in msg_lower:
                return ActivationLevel.SWARM

        for w in SIMPLE_INDICATORS:
            if w in msg_lower:
                return ActivationLevel.MINIMAL

        # Deteccion por cantidad de verbos tecnicos
        tech_verbs = 0
        for agent_kws in AGENT_KEYWORDS.values():
            for kw in agent_kws:
                if kw in msg_lower:
                    tech_verbs += 1

        if tech_verbs >= 5:
            return ActivationLevel.SWARM
        elif tech_verbs >= 3:
            return ActivationLevel.STANDARD
        elif tech_verbs >= 1:
            return ActivationLevel.PAIRED
        else:
            return ActivationLevel.MINIMAL

    def _score_agents(self, msg_lower: str) -> Dict[str, float]:
        """Puntua relevancia de cada agente (0.0 - 1.0)."""
        scores: Dict[str, float] = {}
        for agent, keywords in AGENT_KEYWORDS.items():
            score = sum(1 for kw in keywords if kw in msg_lower)
            # Normalizar
            max_possible = len(keywords)
            scores[agent] = min(score / max(1, max_possible) * 2, 1.0)
        return scores

    def _select_by_level(self, scores: Dict[str, float], level: ActivationLevel) -> List[str]:
        """Selecciona agentes segun nivel y puntajes."""
        # Ordenar por relevancia descendente
        ranked = sorted(scores.items(), key=lambda x: -x[1])

        if level == ActivationLevel.MINIMAL:
            # Solo el agente mas relevante (minimo 1)
            selected = [ranked[0][0]] if ranked else ["builder"]

        elif level == ActivationLevel.PAIRED:
            # Top 2 agentes con score > 0
            selected = [name for name, score in ranked if score > 0][:2]
            if len(selected) < 1:
                selected = ["builder"]

        elif level == ActivationLevel.STANDARD:
            # Top 2-3 agentes
            selected = [name for name, score in ranked if score > 0][:3]
            if len(selected) < 2:
                # Si falta, agregar guardian por defecto
                if "guardian" not in selected:
                    selected.append("guardian")
                if "builder" not in selected:
                    selected.append("builder")

        elif level == ActivationLevel.SWARM:
            # builder + scientist + guardian
            selected = ["builder", "scientist", "guardian"]
            # Agregar evolve si es relevante
            if scores.get("evolve", 0) > 0.3:
                selected.append("evolve")

        else:  # FULL
            selected = ["builder", "scientist", "guardian", "evolve"]

        return selected

    def estimate_tokens_saved(self, message: str) -> Dict[str, int]:
        """Estima tokens ahorrados vs SWARM completo."""
        selected = self.select(message)
        full_swarm = ["builder", "scientist", "guardian"]

        tokens_full = len(full_swarm) * 500  # ~500 tokens por agente
        tokens_selected = len(selected) * 500

        return {
            "selected_agents": len(selected),
            "agents_saved": len(full_swarm) - len(selected),
            "tokens_saved": tokens_full - tokens_selected,
            "estimated_tokens": tokens_selected,
        }
