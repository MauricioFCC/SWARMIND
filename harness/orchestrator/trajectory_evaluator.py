"""Agentic Trajectory Evaluator - auditoria de la eficiencia del DAG de ejecucion.

Evalua la TRAYECTORIA del grafo de ejecucion multi-agente, no solo el output
final: deteccion determinista de redundancia (pasos consecutivos repetidos) y
eficiencia con LLM-as-a-Judge (ADR-0033, plan maestro Fase 3.1). Responde dos
preguntas operativas: (1) ¿el coordinador pudo resolver la tarea con N agentes
en vez de M? y (2) ¿el builder dio rodeos innecesarios?

Sin judge se usa una heuristica determinista (apropiada para tests y entornos
sin LLM): efficiency = 100 - redundancy * 50 - penalizacion_agentes.

Uso:
    evaluator = TrajectoryEvaluator()
    report = evaluator.evaluate("task-1", steps)
    print(evaluator.summarize(report))
"""

from __future__ import annotations

import logging
import re
from collections.abc import Callable
from dataclasses import asdict, dataclass, field

logger = logging.getLogger(__name__)

# Umbrales de veredicto y pesos de la heuristica
VERDICT_OPTIMAL_THRESHOLD: float = 80.0
VERDICT_ACCEPTABLE_THRESHOLD: float = 60.0
REDUNDANCY_PENALTY_WEIGHT: float = 50.0
AGENT_OVERLOAD_PENALTY: float = 20.0
AGENT_OVERLOAD_MIN: int = 4

# Puntaje por defecto por veredicto del judge (cuando no da numero explicito)
_DEFAULT_JUDGE_SCORE: dict[str, float] = {
    "OPTIMAL": 90.0,
    "ACCEPTABLE": 70.0,
    "INEFFICIENT": 40.0,
}


@dataclass
class TrajectoryStep:
    """Nodo del DAG de ejecucion: una accion ejecutada por un agente.

    Args:
        agent: Nombre del agente que ejecuto la accion (ej: 'builder').
        action: Descripcion corta de la accion ejecutada.
        duration_ms: Duracion del paso en milisegundos.
        result: Estado del paso ('success', 'failed' o 'partial').
        output_tokens: Tokens generados como salida.
        dependencies: IDs de pasos previos de los que depende.
    """

    agent: str
    action: str
    duration_ms: float = 0.0
    result: str = "success"
    output_tokens: int = 0
    dependencies: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        """Serializa el paso como dict plano (JSON-serializable).

        Returns:
            dict con agent, action, duration_ms, result, output_tokens
            y dependencies.
        """
        return asdict(self)


@dataclass
class TrajectoryReport:
    """Resultado de la evaluacion de una trayectoria completa.

    Args:
        task_id: Identificador de la tarea evaluada.
        steps: Numero total de pasos del DAG.
        agents_used: Cantidad de agentes distintos participantes.
        total_duration_ms: Suma de duraciones de todos los pasos.
        redundancy_score: Proporcion de trabajo redundante (0.0-1.0).
        efficiency_score: Eficiencia normalizada entre 0 y 100.
        verdict: 'OPTIMAL', 'ACCEPTABLE' o 'INEFFICIENT'.
        recommendations: Recomendaciones accionables en espanol.
    """

    task_id: str
    steps: int
    agents_used: int
    total_duration_ms: float
    redundancy_score: float
    efficiency_score: float
    verdict: str
    recommendations: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        """Serializa el reporte como dict plano (JSON-serializable).

        Returns:
            dict con todos los campos del reporte.
        """
        return asdict(self)


def build_judge_prompt(task_id: str, steps: list[TrajectoryStep]) -> str:
    """Construye el prompt del LLM-as-a-Judge con rubrica explicita.

    Serializa la trayectoria paso a paso y formula las preguntas operativas
    (reduccion de agentes y rodeos del builder).

    Args:
        task_id: Identificador de la tarea a evaluar.
        steps: Pasos del DAG en orden cronologico.

    Returns:
        Prompt en espanol listo para enviar al judge.
    """
    serialized = "\n".join(
        f"{i}. agente={s.agent}, accion={s.action}, resultado={s.result}, "
        f"duracion_ms={s.duration_ms}, tokens={s.output_tokens}, "
        f"dependencias=[{', '.join(s.dependencies) or 'ninguna'}]"
        for i, s in enumerate(steps, start=1)
    )
    return (
        "Eres un juez experto en eficiencia de orquestacion multi-agente "
        "(LLM-as-a-Judge). Evalua la TRAYECTORIA del DAG, no solo el output.\n\n"
        f"TAREA EVALUADA: {task_id}\n\n"
        f"PASOS DE LA TRAYECTORIA:\n{serialized}\n\n"
        "RUBRICA DE EVALUACION:\n"
        "- OPTIMAL: directa, sin rodeos y con el minimo de agentes necesario.\n"
        "- ACCEPTABLE: ineficiencias menores (un reintento, un agente de mas).\n"
        "- INEFFICIENT: rodeos evidentes, agentes redundantes o reintentos "
        "multiples.\n\n"
        "PREGUNTAS OBLIGATORIAS:\n"
        "1. ¿El coordinador pudo resolver la tarea con N agentes en vez de M?\n"
        "2. ¿El builder dio rodeos innecesarios antes de llegar a la solucion?\n\n"
        "Responde EXACTAMENTE con:\n"
        "VERDICTO: OPTIMAL | ACCEPTABLE | INEFFICIENT\n"
        "RAZON: explicacion breve y accionable\n"
    )


class TrajectoryEvaluator:
    """Evaluador de trayectorias: redundancia determinista + LLM-as-judge.

    Args:
        judge: Callable que recibe el prompt (build_judge_prompt) y devuelve
            el veredicto del LLM como texto. None usa una heuristica
            determinista (apropiada para tests y entornos sin LLM).
    """

    def __init__(self, judge: Callable[[str], str] | None = None) -> None:
        """Inicializa el evaluador.

        Args:
            judge: Callable prompt->veredicto; None activa el fallback.
        """
        self._judge = judge

    def evaluate(self, task_id: str, steps: list[TrajectoryStep]) -> TrajectoryReport:
        """Evalua una trayectoria y produce un TrajectoryReport.

        Calcula metricas de tamano (steps, agents_used, total_duration_ms),
        redundancia por heuristica y eficiencia via judge o heuristica.

        Args:
            task_id: Identificador de la tarea evaluada.
            steps: Pasos del DAG en orden cronologico.

        Returns:
            TrajectoryReport con metricas, veredicto y recomendaciones.

        Raises:
            ValueError: Si steps esta vacio (WHAT+WHY+WHERE).
        """
        if not steps:
            raise ValueError(
                "WHAT: no hay pasos que evaluar en la trayectoria. "
                "WHY: un DAG vacio impide calcular redundancia ni eficiencia "
                f"(task_id={task_id!r}). "
                "WHERE: TrajectoryEvaluator.evaluate() en "
                "harness/orchestrator/trajectory_evaluator.py."
            )
        agents_used = len({s.agent for s in steps})
        total_duration_ms = float(sum(s.duration_ms for s in steps))
        redundancy_score, redundant_agents = self._compute_redundancy(steps)
        if self._judge is not None:
            efficiency_score, verdict, rationale = self._evaluate_with_judge(
                task_id, steps, agents_used, redundancy_score
            )
        else:
            efficiency_score = self._heuristic_efficiency(
                agents_used, len(steps), redundancy_score
            )
            verdict = self._verdict_for(efficiency_score)
            rationale = None
        return TrajectoryReport(
            task_id=task_id,
            steps=len(steps),
            agents_used=agents_used,
            total_duration_ms=total_duration_ms,
            redundancy_score=redundancy_score,
            efficiency_score=efficiency_score,
            verdict=verdict,
            recommendations=self._build_recommendations(
                len(steps), agents_used, redundancy_score, redundant_agents, rationale
            ),
        )

    def summarize(self, report: TrajectoryReport) -> str:
        """Genera un resumen de una linea legible del reporte.

        Args:
            report: TrajectoryReport producido por evaluate().

        Returns:
            String de una linea con metricas clave y el veredicto.
        """
        recs = "; ".join(report.recommendations) if report.recommendations else "sin recomendaciones"
        return (
            f"Tarea '{report.task_id}': {report.steps} pasos, "
            f"{report.agents_used} agentes, {report.total_duration_ms:.1f}ms, "
            f"eficiencia {report.efficiency_score:.1f}/100, "
            f"redundancia {report.redundancy_score:.2f} -> {report.verdict}. "
            f"Recomendaciones: {recs}"
        )

    def _compute_redundancy(self, steps: list[TrajectoryStep]) -> tuple[float, list[str]]:
        """Corridas consecutivas mismo agente+accion: 1.0 por paso, 0.5 si es reintento tras fallo."""
        total = len(steps)
        count = 0.0
        redundant_agents: list[str] = []
        i = 0
        while i < total:
            j = i
            while (
                j + 1 < total
                and steps[j + 1].agent == steps[j].agent
                and steps[j + 1].action == steps[j].action
            ):
                j += 1
            if j - i + 1 >= 2:
                if steps[i].agent not in redundant_agents:
                    redundant_agents.append(steps[i].agent)
                for k in range(i, j + 1):
                    count += 0.5 if k > i and steps[k - 1].result == "failed" else 1.0
            i = j + 1
        return (min(1.0, count / total) if total else 0.0), redundant_agents

    def _heuristic_efficiency(self, agents_used: int, steps_count: int, redundancy_score: float) -> float:
        """Eficiencia determinista: 100 - redundancy*50 - penalizacion por sobre-delegacion."""
        efficiency = 100.0 - redundancy_score * REDUNDANCY_PENALTY_WEIGHT
        if agents_used > AGENT_OVERLOAD_MIN and steps_count < 2 * agents_used:
            efficiency -= AGENT_OVERLOAD_PENALTY
        return max(0.0, min(100.0, efficiency))

    def _verdict_for(self, efficiency_score: float) -> str:
        """Mapea un score [0-100] a OPTIMAL, ACCEPTABLE o INEFFICIENT."""
        if efficiency_score >= VERDICT_OPTIMAL_THRESHOLD:
            return "OPTIMAL"
        if efficiency_score >= VERDICT_ACCEPTABLE_THRESHOLD:
            return "ACCEPTABLE"
        return "INEFFICIENT"

    def _fallback(self, agents_used: int, steps_count: int, redundancy_score: float) -> tuple[float, str, None]:
        """Heuristica como (score, veredicto, rationale=None) para judge invalido."""
        score = self._heuristic_efficiency(agents_used, steps_count, redundancy_score)
        return score, self._verdict_for(score), None

    def _evaluate_with_judge(
        self, task_id: str, steps: list[TrajectoryStep], agents_used: int, redundancy_score: float
    ) -> tuple[float, str, str | None]:
        """Invoca al judge, parsea su veredicto y hace fallback heuristico ante fallos."""
        prompt = build_judge_prompt(task_id, steps)
        try:
            response = self._judge(prompt)  # type: ignore[misc]
        except Exception as exc:  # noqa: BLE001 - fallback defensivo si el judge callable falla  # pragma: no cover - defensivo
            logger.error(
                "WHAT: el judge fallo al evaluar '%s'. WHY: excepcion %s al "
                "invocar el callable. WHERE: TrajectoryEvaluator._evaluate_with_judge() "
                "en harness/orchestrator/trajectory_evaluator.py.",
                task_id,
                exc,
            )
            response = ""
        if not isinstance(response, str) or not response.strip():
            logger.warning(
                "WHAT: el judge devolvio respuesta vacia o invalida para '%s'. "
                "WHY: sin texto no se parsea veredicto. WHERE: "
                "TrajectoryEvaluator._evaluate_with_judge(). Usa heuristica.",
                task_id,
            )
            return self._fallback(agents_used, len(steps), redundancy_score)
        parsed = self._parse_judge_response(response)
        if parsed is None:
            logger.warning(
                "WHAT: veredicto del judge no reconocible para '%s'. WHY: la "
                "respuesta no contiene OPTIMAL/ACCEPTABLE/INEFFICIENT. WHERE: "
                "TrajectoryEvaluator._parse_judge_response(). Usa heuristica.",
                task_id,
            )
            return self._fallback(agents_used, len(steps), redundancy_score)
        verdict, score, rationale = parsed
        return score, verdict, rationale

    def _parse_judge_response(self, response: str) -> tuple[str, float, str | None] | None:
        """Extrae (verdict, score, rationale) del texto del judge; None si no reconoce veredicto."""
        text = response.strip()
        for keyword in ("INEFFICIENT", "ACCEPTABLE", "OPTIMAL"):
            if re.search(rf"\b{keyword}\b", text, re.IGNORECASE):
                score = self._extract_score(text)
                if score is None:
                    score = _DEFAULT_JUDGE_SCORE[keyword]
                return keyword, score, self._extract_rationale(text, keyword)
        return None

    @staticmethod
    def _extract_score(text: str) -> float | None:
        """Extrae un score explicito ('score: 85' o '85/100') acotado a [0, 100]."""
        match = re.search(
            r"(?i)\b(?:score|puntuacion|puntaje|calificacion)\s*[:=]\s*(\d{1,3})", text
        )
        if match is None:
            match = re.search(r"(\d{1,3})\s*/\s*100", text)
        if match is None:
            return None
        return min(100.0, max(0.0, float(match.group(1))))

    @staticmethod
    def _extract_rationale(text: str, verdict: str) -> str | None:
        """Extrae la razon (campo RAZON o resto de linea tras el veredicto)."""
        razon = re.search(r"(?i)RAZON\s*:\s*([^\n]+)", text)
        if razon is not None:
            return razon.group(1).strip()
        upper = text.upper()
        idx = upper.find(verdict)
        if idx < 0:
            return None
        tail = text[idx + len(verdict):].splitlines()[0] if text[idx + len(verdict):] else ""
        for separator in (":", "-"):
            if separator in tail:
                tail = tail.split(separator, 1)[1].strip()
        return tail.strip() or None

    def _build_recommendations(
        self,
        steps_count: int,
        agents_used: int,
        redundancy_score: float,
        redundant_agents: list[str],
        judge_rationale: str | None,
    ) -> list[str]:
        """Genera recomendaciones accionables en espanol segun las metricas."""
        recommendations: list[str] = []
        if redundancy_score > 0.0:
            recommendations.extend(
                f"Eliminar pasos redundantes del agente {agent} "
                "(misma accion ejecutada consecutivamente sin progreso)."
                for agent in redundant_agents
            )
        if agents_used > AGENT_OVERLOAD_MIN and steps_count < 2 * agents_used:
            recommendations.append(
                f"Reducir agentes de {agents_used} a {max(1, (steps_count + 1) // 2)}: "
                "el coordinador sobre-delego para una trayectoria corta."
            )
        if judge_rationale:
            recommendations.append(f"Veredicto del judge: {judge_rationale}")
        if not recommendations:
            recommendations.append("Sin recomendaciones: trayectoria eficiente.")
        return recommendations


__all__ = [
    "TrajectoryEvaluator",
    "TrajectoryReport",
    "TrajectoryStep",
    "build_judge_prompt",
]
