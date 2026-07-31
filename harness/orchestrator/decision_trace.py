"""
Decision Trace (X-Swarmind-Decision) — ADR-0033.

Registra cada decision de routing del AgentBus como un registro inmutable
(strategy, agent, provider, latency_ms, score) con trazabilidad por task_id.
Espejo del header X-OmniRoute-Decision: sin trazabilidad no hay auditoria
ni evaluacion de routing.

Uso:
    trace = DecisionTrace(max_records=1000)
    record_id = trace.record(DecisionRecord(strategy="round_robin", agent="a"))
    header = record.to_header()  # "X-Swarmind-Decision: strategy=..."
"""

from __future__ import annotations

import json
import threading
import time
import uuid
from dataclasses import dataclass, field

from harness.orchestrator.structured_log import StructuredLogRecord

# ---------------------------------------------------------------------------
# DecisionRecord
# ---------------------------------------------------------------------------


@dataclass
class DecisionRecord:
    """
    Registro inmutable de una decision de routing.

    Attributes:
        strategy: estrategia de routing utilizada (ej. round_robin, weighted)
        agent: agente seleccionado por la decision
        provider: proveedor de LLM (vacio si no aplica)
        latency_ms: latencia observada en milisegundos
        score: puntuacion de la decision en [0, 1]
        timestamp: epoch seconds de cuando se tomo la decision
        task_id: identificador del task que origino la decision
    """

    strategy: str
    agent: str
    provider: str = ""
    latency_ms: float = 0.0
    score: float = 0.0
    timestamp: float = field(default_factory=time.time)
    task_id: str = ""

    def to_dict(self) -> dict:
        """
        Convierte el registro a un dict JSON-serializable.

        Returns:
            dict con las claves strategy, agent, provider, latency_ms,
            score, timestamp y task_id.
        """
        return {
            "strategy": self.strategy,
            "agent": self.agent,
            "provider": self.provider,
            "latency_ms": self.latency_ms,
            "score": self.score,
            "timestamp": self.timestamp,
            "task_id": self.task_id,
        }

    def to_header(self) -> str:
        """
        Formatea el registro como cabecera HTTP X-Swarmind-Decision.

        Returns:
            String con el formato exacto:
            "X-Swarmind-Decision: strategy=<s>; agent=<a>; provider=<p>;
            latency_ms=<l>; score=<sc>"
        """
        return (
            f"X-Swarmind-Decision: strategy={self.strategy}; agent={self.agent}; "
            f"provider={self.provider}; latency_ms={self.latency_ms:g}; "
            f"score={self.score:g}"
        )


# ---------------------------------------------------------------------------
# DecisionTrace
# ---------------------------------------------------------------------------


class DecisionTrace:
    """
    Traza thread-safe de decisiones con politica de eviction por antiguedad.

    Al exceder max_records se evicta el registro cuyo timestamp es el mas
    viejo (LRU por timestamp). Cada registro se identifica por un id unico.
    """

    def __init__(self, max_records: int = 1000) -> None:
        """
        Inicializa el trace vacio.

        Args:
            max_records: capacidad maxima de registros retenidos.

        Raises:
            ValueError: si max_records es menor a 1 (capacidad sin sentido).
        """
        if max_records < 1:
            raise ValueError(
                f"max_records debe ser >= 1, recibido {max_records} "
                "(WHY: un trace sin capacidad no puede retener decisiones; "
                "WHERE: DecisionTrace.__init__)"
            )
        self.max_records: int = max_records
        self._records: dict[str, DecisionRecord] = {}
        self._order: list[str] = []
        self._lock = threading.Lock()

    def record(self, decision: DecisionRecord) -> str:
        """
        Anade un registro al trace y aplica eviction si hay exceso.

        Args:
            decision: DecisionRecord a almacenar.

        Returns:
            id unico (str) asignado al registro almacenado.
        """
        with self._lock:
            record_id = uuid.uuid4().hex
            self._records[record_id] = decision
            self._order.append(record_id)
            if len(self._records) > self.max_records:
                self._evict_oldest_locked()
            return record_id

    def get_trace(self, task_id: str) -> list[dict]:
        """
        Devuelve los registros de un task en orden de insercion.

        Args:
            task_id: identificador del task a filtrar.

        Returns:
            lista de dicts (to_dict) de los registros con ese task_id.
        """
        with self._lock:
            return [
                self._records[record_id].to_dict()
                for record_id in self._order
                if self._records[record_id].task_id == task_id
            ]

    def last_decision(self) -> DecisionRecord | None:
        """
        Devuelve el registro mas recientemente insertado.

        Returns:
            DecisionRecord del ultimo registro, o None si el trace esta vacio.
        """
        with self._lock:
            if not self._order:
                return None
            return self._records[self._order[-1]]

    def to_json(self) -> str:
        """
        Serializa el trace completo a JSON.

        Returns:
            String JSON con la lista de registros en orden de insercion.
        """
        with self._lock:
            records = [
                self._records[record_id].to_dict() for record_id in self._order
            ]
        return json.dumps(records, ensure_ascii=False)

    def clear(self) -> None:
        """Vacia el trace por completo (registros y orden)."""
        with self._lock:
            self._records.clear()
            self._order.clear()

    def _evict_oldest_locked(self) -> None:
        """
        Evicta el registro con timestamp mas viejo (requiere lock tomado).

        En caso de empate de timestamp se evicta el insertado primero.
        """
        oldest_id = min(
            self._order, key=lambda record_id: self._records[record_id].timestamp
        )
        self._records.pop(oldest_id)
        self._order.remove(oldest_id)
        StructuredLogRecord.info(
            "decision_trace_eviction",
            message=(
                f"Evictado registro mas viejo del trace "
                f"({len(self._records)}/{self.max_records} retenidos)"
            ),
            record_id=oldest_id,
        )


# ---------------------------------------------------------------------------
# Funcion helper
# ---------------------------------------------------------------------------


def format_decision_header(record: DecisionRecord) -> str:
    """
    Alias de DecisionRecord.to_header para uso funcional.

    Args:
        record: DecisionRecord a formatear.

    Returns:
        String con el header X-Swarmind-Decision del registro.
    """
    return record.to_header()


__all__ = ["DecisionRecord", "DecisionTrace", "format_decision_header"]
