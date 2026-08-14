"""Federated Memory models — ``KnowledgeType`` y ``KnowledgeRecord``.

Extraccion mecanica del modulo original
``harness/orchestrator/federated_memory.py`` (sin cambios de logica
ni firmas).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any

# ---------------------------------------------------------------------------
# Types of federated knowledge
# ---------------------------------------------------------------------------

class KnowledgeType(str, Enum):
    PATTERN = "pattern"           # Patrones de exito/fracaso
    PROMPT = "prompt"             # Prompts optimizados
    ADR = "adr"                   # Decisiones arquitectonicas
    METRIC = "metric"             # Metricas de rendimiento
    EMBEDDING = "embedding"       # Vectores de conocimiento
    SKILL = "skill"               # Skills y su efectividad


# ---------------------------------------------------------------------------
# Knowledge record
# ---------------------------------------------------------------------------

@dataclass
class KnowledgeRecord:
    """
    Un registro de conocimiento federado.

    Attributes:
        id: Identificador unico (ej. "pattern:task_planner:subtask_count")
        type: Tipo de conocimiento (KnowledgeType)
        source_project: Proyecto de origen
        source_agent: Agente que genero el conocimiento
        key: Clave semantica del conocimiento
        value: Valor (serializable)
        tags: Tags para busqueda
        version: Version del registro
        created_at: Timestamp ISO
        updated_at: Timestamp ISO
        ttl_seconds: TTL opcional (0 = forever)
        confidence: Confianza 0.0-1.0
    """
    id: str
    type: KnowledgeType
    source_project: str
    source_agent: str
    key: str
    value: Any
    tags: list[str] = field(default_factory=list)
    version: int = 1
    created_at: str = field(
        default_factory=lambda: datetime.now(UTC).isoformat()
    )
    updated_at: str = field(
        default_factory=lambda: datetime.now(UTC).isoformat()
    )
    ttl_seconds: int = 0
    confidence: float = 1.0

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "type": self.type.value if isinstance(self.type, KnowledgeType) else self.type,
            "source_project": self.source_project,
            "source_agent": self.source_agent,
            "key": self.key,
            "value": self.value,
            "tags": self.tags,
            "version": self.version,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "ttl_seconds": self.ttl_seconds,
            "confidence": self.confidence,
        }

    @classmethod
    def from_dict(cls, d: dict) -> KnowledgeRecord:
        d["type"] = KnowledgeType(d["type"]) if isinstance(d.get("type"), str) else d.get("type")
        return cls(**d)

    def is_expired(self) -> bool:
        if self.ttl_seconds <= 0:
            return False
        created = datetime.fromisoformat(self.created_at)
        elapsed = (datetime.now(UTC) - created).total_seconds()
        return elapsed > self.ttl_seconds
