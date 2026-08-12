"""Federated Memory core — clase principal ``FederatedMemoryStore``.

Extraccion mecanica del modulo original
``harness/orchestrator/federated_memory.py`` (sin cambios de logica
ni firmas). La clase compone los mixins por responsabilidad:

- ``_StoreMixin`` (store_mixin.py): store/delete/query/stats.
- ``_SyncMixin`` (sync_mixin.py): sync/clear/persistencia/thread.
"""
from __future__ import annotations

import logging
import threading
from pathlib import Path

from .models import KnowledgeRecord
from .store_mixin import _StoreMixin
from .sync_mixin import _SyncMixin

logger = logging.getLogger("harness.orchestrator.federated_memory")


class FederatedMemoryStore(_StoreMixin, _SyncMixin):
    """
    Almacen de memoria federada con capacidad de sync entre proyectos.

    Almacena conocimiento en archivos JSON dentro de un directorio compartido.
    Cada proyecto escribe y lee del mismo directorio, permitiendo
    que el conocimiento fluya entre proyectos.

    Uso:
        store = FederatedMemoryStore(project_name="Swarmind")

        # Exportar conocimiento
        store.store_knowledge(
            key="task_planner:optimal_subtask_count",
            value=5,
            ktype=KnowledgeType.PATTERN,
            source_agent="planner",
            tags=["task_planner", "optimization"],
        )

        # Importar conocimiento
        records = store.query_knowledge("task_planner")
        for r in records:
            print(f"{r.key} = {r.value} (from {r.source_project})")

        # Sincronizar
        store.sync()
    """

    def __init__(
        self,
        project_name: str = "Swarmind",
        federated_dir: str | None = None,
        auto_sync: bool = False,
        sync_interval_sec: int = 300,
    ) -> None:
        """
        Args:
            project_name: Nombre de este proyecto (para identificar origen).
            federated_dir: Directorio compartido para archivos federados.
                           Default: {workspace}/.opencode/federated/
            auto_sync: Si True, inicia sync periodico en background.
            sync_interval_sec: Intervalo de sync en segundos (default 5min).
        """
        self._project_name = project_name

        if federated_dir:
            self._federated_dir = Path(federated_dir)
        else:
            # Default: project root / .opencode / federated /
            self._federated_dir = (
                Path(__file__).resolve().parent.parent.parent.parent
                / ".opencode" / "federated"
            )

        self._federated_dir.mkdir(parents=True, exist_ok=True)

        # In-memory cache
        self._local_store: dict[str, KnowledgeRecord] = {}

        # Lock para threadsafety
        self._lock = threading.Lock()

        # Sync thread (if auto_sync)
        self._sync_thread: threading.Thread | None = None
        self._sync_event = threading.Event()
        self._sync_interval = sync_interval_sec

        if auto_sync:
            self._start_sync_thread()

        # Cargar conocimiento local existente
        self._load_local()

        logger.info(
            "FederatedMemoryStore initialized | project=%s | dir=%s",
            self._project_name, self._federated_dir,
        )
