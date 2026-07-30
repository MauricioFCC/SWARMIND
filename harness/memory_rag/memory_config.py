"""
Memory Configuration — configuración modular del sistema de memoria.

Permite:
  - Configurar rutas de LanceDB y shared_memory
  - Cambiar backend (LanceDB / memoria / Hermes)
  - Ajustar dimensiones de embedding
  - Activar/desactivar colecciones de telemetría y KPIs

Uso:
    from harness.memory_rag.memory_config import MemoryConfig
    
    # Default: usa LanceDB en harness/db/lancedb/
    config = MemoryConfig()
    
    # Custom: apunta a shared_memory
    config = MemoryConfig(
        backend="lancedb",
        lancedb_path="$HOME/Documents/DEV-SPACE/shared_memory/99_Hermes_Brain/lancedb_data",
        hermes_path="$HOME/Documents/DEV-SPACE/shared_memory",
    )
    
    # Modo memoria (sin persistencia)
    config = MemoryConfig(backend="memory")
"""

from __future__ import annotations

import logging
import os
from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
from typing import Dict, Optional, Set

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class MemoryBackend(str, Enum):
    LANCEDB = "lancedb"          # LanceDB (default, recomendado)
    MEMORY = "memory"            # In-memory (sin persistencia, tests)
    HERMES = "hermes"            # shared_memory (estructura de carpetas)


class TelemetryLevel(str, Enum):
    OFF = "off"                  # No guardar telemetría
    BASIC = "basic"              # Solo eventos principales
    FULL = "full"                # Todos los eventos + vectores


# ---------------------------------------------------------------------------
# Config dataclass
# ---------------------------------------------------------------------------

@dataclass
class MemoryConfig:
    """
    Configuración completa del sistema de memoria.

    Attributes:
        backend: Backend de almacenamiento.
        lancedb_path: Ruta a la base LanceDB.
        hermes_path: Ruta raíz de shared_memory.
        embedding_dim: Dimensión de vectores de embedding.
        allow_fallback: Permitir fallback a memoria si LanceDB no está.
        telemetry_level: Nivel de telemetría a registrar.
        kpi_collections: Conjunto de colecciones KPI activas.
        auto_create_collections: Crear colecciones automáticamente al iniciar.
        enable_hermes_bridge: Sincronizar con shared_memory.
    """
    backend: MemoryBackend = MemoryBackend.LANCEDB

    # Rutas
    lancedb_path: str = ""
    hermes_path: str = ""

    # Embeddings
    embedding_dim: int = 384

    # Flags
    allow_fallback: bool = False
    telemetry_level: TelemetryLevel = TelemetryLevel.BASIC
    auto_create_collections: bool = True
    enable_hermes_bridge: bool = False

    # Colecciones KPI activas (por defecto todas activas)
    kpi_collections: Set[str] = field(default_factory=lambda: {
        "agent_performance",
        "skill_effectiveness",
        "telemetry_events",
        "session_kpis",
    })

    def __post_init__(self) -> None:
        """Resuelve rutas por defecto si no se especificaron."""
        # Resolver lancedb_path por defecto
        if not self.lancedb_path:
            base = Path(__file__).resolve().parent.parent  # harness/
            self.lancedb_path = str(base / "db" / "lancedb")

        # Resolver hermes_path si está configurado
        if not self.hermes_path:
            candidate = (
                Path(os.environ.get("HERMES_PATH", ""))
                if "HERMES_PATH" in os.environ
                else Path.home() / "Documents" / "DEV-SPACE" / "shared_memory"
            )
            if candidate.exists():
                self.hermes_path = str(candidate)

    @property
    def hermes_brain_path(self) -> str:
        """Ruta al cerebro de Hermes (LanceDB dentro de Hermes)."""
        if self.hermes_path:
            return str(Path(self.hermes_path) / "99_Hermes_Brain" / "lancedb_data")
        return ""

    @property
    def hermes_config_path(self) -> str:
        """Ruta a los configs de Hermes."""
        if self.hermes_path:
            return str(Path(self.hermes_path) / "99_Hermes_Brain" / "configs")
        return ""

    @property
    def is_hermes_available(self) -> bool:
        """Checkea si shared_memory está accesible."""
        if not self.hermes_path or not self.enable_hermes_bridge:
            return False
        return Path(self.hermes_path).exists()

    def to_dict(self) -> Dict:
        d = asdict(self)
        d["kpi_collections"] = list(d["kpi_collections"])
        d["backend"] = self.backend.value
        d["telemetry_level"] = self.telemetry_level.value
        d["is_hermes_available"] = self.is_hermes_available
        return d

    @classmethod
    def from_dict(cls, d: Dict) -> "MemoryConfig":
        if "backend" in d:
            d["backend"] = MemoryBackend(d["backend"])
        if "telemetry_level" in d:
            d["telemetry_level"] = TelemetryLevel(d["telemetry_level"])
        if "kpi_collections" in d:
            d["kpi_collections"] = set(d["kpi_collections"])
        return cls(**d)

    @classmethod
    def from_env(cls) -> "MemoryConfig":
        """Carga configuración desde variables de entorno."""
        return cls(
            backend=MemoryBackend(os.environ.get("MEMORY_BACKEND", "lancedb")),
            lancedb_path=os.environ.get("LANCEDB_PATH", ""),
            hermes_path=os.environ.get("HERMES_PATH", ""),
            embedding_dim=int(os.environ.get("EMBEDDING_DIM", "384")),
            allow_fallback=os.environ.get("MEMORY_FALLBACK", "false").lower() == "true",
            telemetry_level=TelemetryLevel(
                os.environ.get("TELEMETRY_LEVEL", "basic")
            ),
            enable_hermes_bridge=os.environ.get("HERMES_BRIDGE", "false").lower() == "true",
        )


# ---------------------------------------------------------------------------
# Memory config registry
# ---------------------------------------------------------------------------

_GLOBAL_CONFIG: Optional[MemoryConfig] = None


def get_memory_config() -> MemoryConfig:
    """Obtiene la configuración global de memoria."""
    global _GLOBAL_CONFIG
    if _GLOBAL_CONFIG is None:
        _GLOBAL_CONFIG = MemoryConfig.from_env()
    return _GLOBAL_CONFIG


def set_memory_config(config: MemoryConfig) -> None:
    """Establece la configuración global de memoria."""
    global _GLOBAL_CONFIG
    _GLOBAL_CONFIG = config
    logger.info(
        "Memory config updated: backend=%s, lancedb=%s, hermes=%s",
        config.backend.value,
        config.lancedb_path,
        config.hermes_path or "not configured",
    )


def reset_memory_config() -> None:
    """Resetea la configuración global a valores de entorno."""
    global _GLOBAL_CONFIG
    _GLOBAL_CONFIG = None
    logger.info("Memory config reset to env defaults")
