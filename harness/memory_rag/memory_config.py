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
    
    # Custom: apunta a shared_memory (rutas portables via MEMORY_ROOT/
    # LANCEDB_PATH/HERMES_PATH o el .swarmind_config.json de la memoria central)
    config = MemoryConfig(
        backend="lancedb",
        lancedb_path="<ruta-a-lancedb>",
        hermes_path="<ruta-a-shared-memory>",
    )
    
    # Modo memoria (sin persistencia)
    config = MemoryConfig(backend="memory")
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Memoria central (SSOT: .swarmind_config.json de backup_memory.py)
# ---------------------------------------------------------------------------

# Rutas canonicas por convencion (SIEMPRE overrideables via env:
# MEMORY_ROOT / LANCEDB_PATH / HERMES_PATH). No son hardcode de produccion:
# son el fallback documentado cuando no hay config explicita.
_MEMORY_ROOT_ENV = "MEMORY_ROOT"
_LANCEDB_PATH_ENV = "LANCEDB_PATH"
_HERMES_PATH_ENV = "HERMES_PATH"
_DOCUMENTS_DIR = "Documents"
_DEFAULT_MEMORY_ROOT = "Memory_Proyects"


def _safe_home() -> Path | None:
    """Path.home() resiliente: None si el entorno no define HOME.

    WHY: entornos CI/headless pueden carecer de HOME/USERPROFILE; el harness
    no debe crashear al construir MemoryConfig, sino degradar a env/defaults.
    WHERE: memory_config._safe_home
    """
    try:
        return Path.home()
    except (RuntimeError, OSError):
        return None


def _discover_swarmind_config() -> Path | None:
    """Localiza el .swarmind_config.json de la memoria central.

    Prioridad de busqueda (nada hardcode en produccion; todo configurable):
      1. Variable MEMORY_ROOT (SSOT del root de la memoria central).
      2. ~/Documents/Memory_Proyects (canonica, fallback documentado).

    Returns:
        Ruta al .swarmind_config.json, o None si no existe.
    """
    env_root = os.environ.get(_MEMORY_ROOT_ENV, "")
    candidates: list[Path] = []
    if env_root:
        candidates.append(Path(env_root) / ".swarmind_config.json")
    home = _safe_home()
    if home is not None:
        candidates.append(
            home / _DOCUMENTS_DIR / _DEFAULT_MEMORY_ROOT / ".swarmind_config.json"
        )
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return None


def _memory_root_from_config() -> str | None:
    """Extrae memory_root del .swarmind_config.json (si existe).

    Returns:
        Ruta del memory_root, o None si no hay config valida.
    """
    config_path = _discover_swarmind_config()
    if config_path is None:
        return None
    try:
        data = json.loads(config_path.read_text(encoding="utf-8"))
        root = data.get("memory_root")
        if root and Path(root).is_dir():
            return str(Path(root))
    except (OSError, ValueError) as exc:
        logger.warning(
            "No se pudo leer %s: %s. "
            "WHY: config corrupta o inaccesible. "
            "WHERE: memory_config._memory_root_from_config",
            config_path, exc,
        )
    return None


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
    kpi_collections: set[str] = field(default_factory=lambda: {
        "agent_performance",
        "skill_effectiveness",
        "telemetry_events",
        "session_kpis",
    })

    def __post_init__(self) -> None:
        """Resuelve rutas por defecto si no se especificaron."""
        memory_root = _memory_root_from_config()

        # Resolver lancedb_path por defecto
        if not self.lancedb_path:
            # Prioridad: memoria central (Memory_Proyects/data/lancedb)
            central_db = (
                Path(memory_root) / "data" / "lancedb"
                if memory_root and (Path(memory_root) / "data" / "lancedb").is_dir()
                else None
            )
            if central_db is not None:
                self.lancedb_path = str(central_db)
            else:
                base = Path(__file__).resolve().parent.parent  # harness/
                self.lancedb_path = str(base / "db" / "lancedb")

        # Resolver hermes_path si está configurado (resiliente sin HOME)
        if not self.hermes_path:
            # Si la memoria central tiene 99_Hermes_Brain, es el hermes_path
            if memory_root and (Path(memory_root) / "99_Hermes_Brain").is_dir():
                self.hermes_path = memory_root
            elif _HERMES_PATH_ENV in os.environ:
                candidate = Path(os.environ.get(_HERMES_PATH_ENV, ""))
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

    def to_dict(self) -> dict:
        d = asdict(self)
        d["kpi_collections"] = list(d["kpi_collections"])
        d["backend"] = self.backend.value
        d["telemetry_level"] = self.telemetry_level.value
        d["is_hermes_available"] = self.is_hermes_available
        return d

    @classmethod
    def from_dict(cls, d: dict) -> MemoryConfig:
        if "backend" in d:
            d["backend"] = MemoryBackend(d["backend"])
        if "telemetry_level" in d:
            d["telemetry_level"] = TelemetryLevel(d["telemetry_level"])
        if "kpi_collections" in d:
            d["kpi_collections"] = set(d["kpi_collections"])
        return cls(**d)

    @classmethod
    def from_env(cls) -> MemoryConfig:
        """Carga configuración desde variables de entorno."""
        return cls(
            backend=MemoryBackend(os.environ.get("MEMORY_BACKEND", "lancedb")),
            lancedb_path=os.environ.get(_LANCEDB_PATH_ENV, ""),
            hermes_path=os.environ.get(_HERMES_PATH_ENV, ""),
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

_GLOBAL_CONFIG: MemoryConfig | None = None


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
