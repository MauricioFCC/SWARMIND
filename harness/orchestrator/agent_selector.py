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

import hashlib
import logging
from enum import Enum

from harness.orchestrator.competence_model import CompetenceModel
from harness.orchestrator.decision_trace import (
    DecisionRecord,
    DecisionTrace,
    default_trace,
)
from harness.orchestrator.keyword_match import contains_word, score_keywords
from harness.orchestrator.prompt_sanitizer import sanitize_task

logger = logging.getLogger(__name__)

#: Observaciones REALES minimas (excluye el prior Beta(1,1)) para re-rankear.
#: Con menos, el re-rank es identidad (no corrompe el ranking por keyword).
MIN_EVIDENCE_FOR_RERANK = 1.0
#: Peso maximo del bonus de competencia (escalado por evidencia n/(n+k)).
COMPETENCE_BONUS_WEIGHT = 1.0
#: Longitud del `task_id` determinista derivado del mensaje saneado.
TASK_ID_LENGTH = 12


class ActivationLevel(str, Enum):
    """Nivel de activacion de agentes."""
    MINIMAL = "minimal"          # 1 agente
    PAIRED = "paired"            # 2 agentes
    STANDARD = "standard"        # 2-3 agentes
    SWARM = "swarm"              # 3 agentes (builder+scientist+guardian)
    FULL = "full"                # 4+ agentes (incluye evolve)


# Keywords que determinan que agente se necesita
AGENT_KEYWORDS: dict[str, list[str]] = {
    "builder": [
        "implement", "implementa", "implementar", "build", "code", "api",
        "endpoint", "rust", "go", "python", "typescript", "javascript",
        "web", "mobile", "frontend", "backend", "database", "sql", "query",
        "migracion", "deploy", "docker", "algoritmo", "modulo", "funcion",
        "clase", "refactor", "fix", "bug", "crea", "crear", "desarrolla",
        "desarrollar", "construye", "construir",
    ],
    "scientist": [
        "research", "investigar", "investiga", "study", "analyze", "analysis",
        "architecture", "design", "pattern", "paper", "algoritmo",
        "ml", "ai", "machine learning", "experiment", "hypothesis",
        "comparar", "compara", "evaluar", "evalua", "proponer", "propone",
        "recomendar", "recomienda", "investigacion", "analisis", "analiza",
        "analizar", "estudia", "estudiar", "disena", "disenar",
    ],
    "guardian": [
        "test", "tests", "testing", "coverage", "cobertura", "pruebas",
        "prueba", "security", "seguridad", "audit", "audita", "auditoria",
        "vulnerabilidad", "quality", "calidad", "review", "revisa", "revisar",
        "revision", "validate", "valida", "validacion", "verifica",
        "verificacion", "document", "documenta", "documentar",
        "documentacion", "docs", "readme",
    ],
    "evolve": [
        "evolve", "evoluciona", "improve", "optimize", "optimiza", "optimizar",
        "mejora", "mejorar", "skill", "cognition", "learn", "aprender",
        "auto-mejora", "self-improve", "evolution",
    ],
}

# Palabras que indican tarea simple (no requiere SWARM)
SIMPLE_INDICATORS: list[str] = [
    "simple", "basico", "rapido", "quick", "rapida",
    "solo una consulta", "duda rapida", "pregunta simple",
    "pequeno cambio", "minor fix",
]

# Palabras que indican tarea compleja (requiere SWARM completo)
COMPLEX_INDICATORS: list[str] = [
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

    def __init__(
        self,
        default_level: ActivationLevel = ActivationLevel.STANDARD,
        competence: CompetenceModel | None = None,
        trace: DecisionTrace | None = None,
    ):
        """Inicializa el selector con opcion de competencia evidenciada.

        Args:
            default_level: Nivel de activacion por defecto.
            competence: Modelo Beta/Thompson (agente x skill) opcional;
                si hay evidencia, re-rankea con bonus Thompson sobre el
                score keyword (ADR-0075: evidencia > keywords fijas).
            trace: Traza de decisiones donde registrar cada `select`; si es
                `None` usa el trace global `default_trace()` (ADR-0033).
        """
        self._default_level = default_level
        self._competence = competence
        self._trace = trace if trace is not None else default_trace()

    def select(
        self, message: str, skill: str = "general", abstain: bool = True
    ) -> list[str]:
        """
        Selecciona agentes basado en el mensaje (y evidencia si la hay).

        Matching por frontera de palabra (`keyword_match`): `"go"` no matchea
        `"good"`, `"ai"` no matchea `"email"`, `"test"` no matchea `"latest"`.

        Abstention: si NINGUN agente tiene score > 0 (tarea fuera de dominio),
        retorna `[]` para que el coordinator decida, en vez de forzar `builder`
        (ADR-0077). Mensaje vacio conserva el contrato `["builder"]`.

        Args:
            message: Tarea del usuario.
            skill: Skill para el re-rank de competencia (default "general").
            abstain: Si True (default), fuera de dominio devuelve `[]`. Si
                False, conserva la retrocompatibilidad (fuerza `builder`).

        Returns:
            Lista de agentes a activar (vacia si abstention).
        """
        if not message:
            return ["builder"]

        # 0. Saneado anti-inyeccion ANTES de detectar/rankear (VER prompt_sanitizer).
        sanitized = sanitize_task(message)
        if not sanitized:
            logger.info("agent_selector: abstention (input solo inyeccion)")
            agents = [] if abstain else ["builder"]
            self._record_decision(sanitized, agents, {})
            return agents

        # 1. Detectar nivel de activacion
        level = self._detect_level(sanitized)

        # 2. Puntuar relevancia de cada agente (frontera de palabra)
        scores = self._score_agents(sanitized)

        # 3. Re-rank con competencia evidenciada (solo con evidencia real)
        scores = self._rerank_with_competence(scores, skill)

        # 4. Abstention: sin senal de dominio, no forzar agente
        if abstain and all(score <= 0.0 for score in scores.values()):
            logger.info("agent_selector: abstention (fuera de dominio)")
            selected: list[str] = []
        else:
            # 5. Seleccionar segun nivel
            selected = self._select_by_level(scores, level)

        # 6. Trazar la decision (strategy/agent/score/task_id) — ADR-0033
        self._record_decision(sanitized, selected, scores)
        return selected

    def _record_decision(
        self, sanitized: str, selected: list[str], scores: dict[str, float]
    ) -> None:
        """Registra la decision de seleccion en el trace configurado.

        Args:
            sanitized: Mensaje ya saneado (fuente del `task_id` determinista).
            selected: Agentes elegidos; si esta vacio la decision es abstention.
            scores: Scores por agente (se registra el mejor como `score`).

        Returns:
            None.
        """
        task_id = hashlib.sha1(sanitized.encode("utf-8")).hexdigest()[:TASK_ID_LENGTH]
        best_score = max(scores.values(), default=0.0)
        agent = selected[0] if selected else "abstain"
        self._trace.record(
            DecisionRecord(
                strategy="agent_selector",
                agent=agent,
                score=best_score,
                task_id=task_id,
            )
        )

    def _rerank_with_competence(
        self, scores: dict[str, float], skill: str
    ) -> dict[str, float]:
        """Ajusta los scores keyword con la competencia evidenciada.

        El guard se basa en OBSERVACIONES REALES (`BetaPosterior.observations`,
        excluye el prior Beta(1,1)); con 0 observaciones la re-ordenacion es
        identidad. El bonus escala por evidencia (`n/(n+k)`) para que una sola
        observacion no revierta un keyword fuerte.

        Args:
            scores: Scores keyword por agente (0.0-1.0).
            skill: Skill para la posterior (agente x skill).

        Returns:
            Scores ajustados; identidad si no hay modelo o evidencia real.
        """
        if self._competence is None:
            return scores
        adjusted = dict(scores)
        for agent in list(adjusted):
            try:
                posterior = self._competence.posterior(agent, skill)
            except ValueError:
                # Par (agente, skill) fuera del modelo: sin evidencia,
                # estado esperado, no error (se queda el score keyword).
                logger.debug(
                    "agent_selector: sin posterior para (%s, %s)", agent, skill
                )
                continue
            if posterior.observations < MIN_EVIDENCE_FOR_RERANK:
                continue  # sin evidencia real: no compite con keywords
            bonus = (
                posterior.mean
                * COMPETENCE_BONUS_WEIGHT
                * posterior.evidence_weight()
            )
            adjusted[agent] = min(1.0, adjusted[agent] + bonus)
            logger.debug(
                "agent_selector: bonus competencia %s=%.2f (mean=%.2f, n=%.0f)",
                agent, bonus, posterior.mean, posterior.observations,
            )
        return adjusted

    def _detect_level(self, message: str) -> ActivationLevel:
        """Detecta nivel de activacion con frontera de palabra (DRY)."""
        for indicator in COMPLEX_INDICATORS:
            if contains_word(message, indicator):
                return ActivationLevel.SWARM

        for indicator in SIMPLE_INDICATORS:
            if contains_word(message, indicator):
                return ActivationLevel.MINIMAL

        # Deteccion por cantidad de keywords tecnicas que matchean
        tech_verbs = sum(
            score_keywords(message, keywords) for keywords in AGENT_KEYWORDS.values()
        )
        if tech_verbs >= 5:
            return ActivationLevel.SWARM
        if tech_verbs >= 3:
            return ActivationLevel.STANDARD
        if tech_verbs >= 1:
            return ActivationLevel.PAIRED
        return ActivationLevel.MINIMAL

    def _score_agents(self, message: str) -> dict[str, float]:
        """Puntua relevancia de cada agente (0.0 - 1.0) por frontera de palabra."""
        scores: dict[str, float] = {}
        for agent, keywords in AGENT_KEYWORDS.items():
            score = score_keywords(message, keywords)
            # Normalizar
            max_possible = len(keywords)
            scores[agent] = min(score / max(1, max_possible) * 2, 1.0)
        return scores

    def _select_by_level(self, scores: dict[str, float], level: ActivationLevel) -> list[str]:
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

    def estimate_tokens_saved(self, message: str) -> dict[str, int]:
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
