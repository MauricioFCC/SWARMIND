"""Tipos compartidos del stack QA (contrato entre las 5 capas).

Viven en un modulo propio para romper el ciclo de imports
``harness.qa <-> harness.qa.detector <-> ...``: los tipos no dependen de
ninguna capa, y las capas importan de aqui (no del ``__init__`` del paquete).

Referencia: fitness function F4 (ciclos de import) — ``scripts/check_architecture.py``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any


class QASeverity(Enum):
    """Severidad de un hallazgo en el pipeline de calidad."""

    CRITICAL = auto()
    HIGH = auto()
    MEDIUM = auto()
    LOW = auto()
    INFO = auto()


class QALayer(Enum):
    """Identificadores de capa en el stack QA 5-capas."""

    L1_PREDICTOR = auto()
    L2_DETECTOR = auto()
    L3_GENERATOR = auto()
    L4_AGENT = auto()
    L5_ORCHESTRATOR = auto()


@dataclass(frozen=True)
class QAMetadata:
    """Metadatos estandar para todo resultado del pipeline QA.

    Args:
        layer: Capa que produjo el resultado.
        version: Version del modulo que genero el resultado.
        timestamp_iso: Marca de tiempo ISO 8601.
        execution_id: Identificador unico de ejecucion.
        extra: Datos adicionales arbitrarios.
    """

    layer: QALayer
    version: str
    timestamp_iso: str
    execution_id: str
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class QAContext:
    """Contexto compartido entre capas del pipeline.

    Propaga informacion de ejecucion, configuracion y estado a traves de las
    5 capas sin acoplamiento directo.

    Args:
        target: Componente o modulo bajo prueba.
        config: Diccionario de configuracion arbitraria.
        metadata: Metadatos de la ejecucion actual.
        tags: Etiquetas para filtrado y segmentacion.
    """

    target: str
    config: dict[str, Any] = field(default_factory=dict)
    metadata: QAMetadata | None = None
    tags: set[str] = field(default_factory=set)


__all__ = ["QAContext", "QALayer", "QAMetadata", "QASeverity"]
