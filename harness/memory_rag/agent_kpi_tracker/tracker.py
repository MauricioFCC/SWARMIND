"""AgentKpiTracker — núcleo del tracker de KPIs (extraccion mecanica).

Clase publica AgentKpiTracker: inicializacion con LanceVectorStore
y MemoryConfig, aseguramiento de colecciones e insercion de filas.
El registro y los reportes se heredan de mixins en submódulos contiguos.
"""
from __future__ import annotations

import logging

import numpy as np

from harness.memory_rag.lance_vector_store import LanceVectorStore
from harness.memory_rag.memory_config import (
    MemoryConfig,
    TelemetryLevel,
    get_memory_config,
)

from .constants import ALL_KPI_COLLECTIONS
from .recording import _RecordingMixin
from .reporting import _ReportingMixin

logger = logging.getLogger(__name__)

class AgentKpiTracker(_RecordingMixin, _ReportingMixin):
    """
    Tracker de KPIs que persiste mÃ©tricas de rendimiento en LanceDB.

    Uso:
        tracker = AgentKpiTracker(store=vector_store)
        
        # Registrar rendimiento de agente
        tracker.record_agent_performance(
            session_id="ses-001",
            agent_name="builder",
            subtask_count=5,
            success_count=4,
            error_count=1,
            total_duration_ms=12000.0,
        )
        
        # Registrar evento de telemetrÃ­a
        tracker.record_telemetry_event(
            event_type="plan_created",
            session_id="ses-001",
            agent="planner",
            duration_ms=450.0,
        )
        
        # Finalizar sesiÃ³n â†’ genera KPIs agregados
        tracker.finalize_session_kpi(
            session_id="ses-001",
            task="implementar API",
            total_duration_ms=150000.0,
            total_subtasks=5,
            total_errors=1,
        )
    """

    def __init__(
        self,
        store: LanceVectorStore | None = None,
        config: MemoryConfig | None = None,
    ) -> None:
        """
        Args:
            store: LanceVectorStore instance. Si es None, crea uno con config.
            config: MemoryConfig. Si es None, usa get_memory_config().
        """
        self._config = config or get_memory_config()

        if store:
            self._store = store
        else:
            from harness.memory_rag.lance_vector_store import LanceVectorStore
            self._store = LanceVectorStore(
                db_path=self._config.lancedb_path,
                allow_fallback=self._config.allow_fallback,
            )

        self._ensure_collections()

        self._enabled = self._config.telemetry_level != TelemetryLevel.OFF
        self._full_telemetry = self._config.telemetry_level == TelemetryLevel.FULL

        logger.info(
            "AgentKpiTracker initialized | backend=%s | telemetry=%s | full=%s",
            self._config.backend.value,
            self._config.telemetry_level.value,
            self._full_telemetry,
        )

    def _ensure_collections(self) -> None:
        """Asegura que las colecciones KPI existan."""
        existing = set(self._store.list_collections())
        for coll in ALL_KPI_COLLECTIONS:
            if coll not in existing:
                try:
                    self._store.create_collection(coll)
                    logger.info("Created KPI collection '%s'", coll)
                except Exception as e:  # noqa: BLE001
                    logger.warning("Could not create collection '%s': %s", coll, e)

    def _insert(self, collection: str, row: dict) -> str | None:
        """Inserta una fila en LanceDB como vector de ceros (bÃºsqueda por metadata)."""
        try:
            # Use zero vector for metadata-only records
            vec = np.zeros(self._config.embedding_dim, dtype=np.float32)
            ids = self._store.insert(collection, vec.reshape(1, -1), [row])
            return ids[0] if ids else None
        except Exception as e:  # noqa: BLE001
            logger.warning("KPI insert error in %s: %s", collection, e)
            return None
