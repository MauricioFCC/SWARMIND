"""
behavioral_tracer.py — Trazabilidad de decisiones de agentes.

Registra el "por que" detras de cada accion del agente, no solo el output.
Permite fingerprints de comportamiento para auditoria y mejora continua.

Uso:
    tracer = BehavioralTracer()
    with tracer.trace("builder", task_id="task-001") as ctx:
        ctx.record_decision(
            action="elegir_algoritmo",
            chosen="quicksort",
            alternatives=["mergesort", "heapsort"],
            rationale="O(n log n) promedio, in-place",
            confidence=0.85,
        )
        ctx.set_result("codigo implementado")
    report = tracer.get_report("task-001")
"""

from __future__ import annotations
import json
import time
import logging
from collections import defaultdict
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional
from contextlib import contextmanager

logger = logging.getLogger(__name__)


@dataclass
class DecisionRecord:
    """Una decision tomada por un agente."""
    action: str                           # Que decision (ej: "elegir_algoritmo")
    chosen: str                           # Opcion elegida
    alternatives: List[str]               # Opciones consideradas
    rationale: str                        # Por que eligio esta
    confidence: float = 0.0               # Confianza 0..1
    timestamp: float = field(default_factory=time.time)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class TraceSession:
    """Sesion de trazabilidad para una tarea."""
    agent: str
    task_id: str
    start_time: float = field(default_factory=time.time)
    end_time: Optional[float] = None
    decisions: List[DecisionRecord] = field(default_factory=list)
    result: Optional[str] = None
    error: Optional[str] = None
    tokens_consumed: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "agent": self.agent,
            "task_id": self.task_id,
            "duration_sec": (self.end_time or time.time()) - self.start_time,
            "decisions": [asdict(d) for d in self.decisions],
            "result_preview": (self.result or "")[:200],
            "error": self.error,
            "tokens_consumed": self.tokens_consumed,
        }

    def fingerprint(self) -> str:
        """Genera una huella unica del comportamiento del agente.

        La huella se basa en las decisiones tomadas, no en el output.
        Permite identificar si el mismo agente esta actuando consistentemente.
        """
        import hashlib
        sig = "|".join(
            f"{d.action}:{d.chosen}:{d.confidence:.2f}"
            for d in self.decisions
        )
        return hashlib.sha256(sig.encode()).hexdigest()[:16]


class BehavioralTracer:
    """Trazabilidad de decisiones de agentes."""

    def __init__(self):
        self._sessions: Dict[str, TraceSession] = {}
        self._agent_fingerprints: Dict[str, List[str]] = defaultdict(list)

    @contextmanager
    def trace(self, agent: str, task_id: str):
        """Context manager para trazar una tarea.

        Args:
            agent: Nombre del agente.
            task_id: ID unico de la tarea.
        """
        session = TraceSession(agent=agent, task_id=task_id)
        self._sessions[task_id] = session
        try:
            yield _TraceContext(session)
            self._agent_fingerprints[agent].append(session.fingerprint())
        except Exception as e:
            session.error = str(e)
            raise
        finally:
            session.end_time = time.time()

    def get_report(self, task_id: str) -> Optional[Dict[str, Any]]:
        """Obtiene el reporte de trazabilidad de una tarea."""
        session = self._sessions.get(task_id)
        if not session:
            return None
        return session.to_dict()

    def get_agent_behavior_summary(self, agent: str) -> Dict[str, Any]:
        """Resumen del comportamiento historico de un agente.

        Returns:
            Dict con fingerprint mas comun, decisiones frecuentes, etc.
        """
        fingerprints = self._agent_fingerprints.get(agent, [])
        if not fingerprints:
            return {"agent": agent, "sessions": 0}

        # Fingerprint mas comun
        from collections import Counter
        common_fp = Counter(fingerprints).most_common(1)[0]

        return {
            "agent": agent,
            "sessions": len(fingerprints),
            "unique_behavior_count": len(set(fingerprints)),
            "most_common_fingerprint": common_fp[0],
            "most_common_count": common_fp[1],
            "consistency_ratio": common_fp[1] / len(fingerprints),
        }


class _TraceContext:
    """Contexto interno para registrar decisiones."""

    def __init__(self, session: TraceSession):
        self._session = session

    def record_decision(
        self,
        action: str,
        chosen: str,
        alternatives: Optional[List[str]] = None,
        rationale: str = "",
        confidence: float = 0.0,
        **metadata,
    ):
        """Registra una decision del agente.

        Args:
            action: Nombre de la accion (ej: "elegir_algoritmo").
            chosen: Opcion elegida.
            alternatives: Opciones consideradas.
            rationale: Razon de la decision.
            confidence: Confianza 0..1.
            metadata: Metadatos adicionales.
        """
        record = DecisionRecord(
            action=action,
            chosen=chosen,
            alternatives=alternatives or [],
            rationale=rationale,
            confidence=confidence,
            metadata=metadata,
        )
        self._session.decisions.append(record)
        logger.debug("Decision [%s]: %s -> %s (confianza=%.2f)", action, chosen, rationale, confidence)

    def set_result(self, result: str):
        """Establece el resultado final de la tarea."""
        self._session.result = result

    def add_tokens(self, count: int):
        """Acumula consumo de tokens."""
        self._session.tokens_consumed += count
