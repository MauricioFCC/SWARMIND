"""
Federated Memory â€” sincronizaciÃ³n automÃ¡tica de conocimiento entre proyectos.

Cada proyecto mantiene su propia base LanceDB local, pero puede:
  1. Exportar conocimiento a un formato federado (JSON)
  2. Importar conocimiento desde otros proyectos federados
  3. Sincronizar automÃ¡ticamente en segundo plano

El conocimiento federado incluye:
  - Patrones de Ã©xito/fracaso por tipo de tarea
  - Prompts optimizados por agente
  - Decisiones arquitectÃ³nicas (ADRs)
  - MÃ©tricas de rendimiento por skill
  - Embeddings de chunks relevantes

Arquitectura:
  â”Œâ”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”     â”Œâ”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”     â”Œâ”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”
  â”‚  Proyecto A  â”‚     â”‚  Proyecto B  â”‚     â”‚  Proyecto C  â”‚
  â”‚  (Harness)   â”‚     â”‚  (Harness)   â”‚     â”‚  (Harness)   â”‚
  â”‚  LanceDB_A   â”‚     â”‚  LanceDB_B   â”‚     â”‚  LanceDB_C   â”‚
  â””â”€â”€â”€â”€â”€â”€â”¬â”€â”€â”€â”€â”€â”€â”˜     â””â”€â”€â”€â”€â”€â”€â”¬â”€â”€â”€â”€â”€â”€â”˜     â””â”€â”€â”€â”€â”€â”€â”¬â”€â”€â”€â”€â”€â”€â”˜
         â”‚                   â”‚                   â”‚
         â””â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”¼â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”˜
                             â”‚
                    â”Œâ”€â”€â”€â”€â”€â”€â”€â”€â”´â”€â”€â”€â”€â”€â”€â”€â”€â”
                    â”‚ Federated Store  â”‚
                    â”‚ (shared dir /   â”‚
                    â”‚  S3 / network)  â”‚
                    â””â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”˜
"""

from __future__ import annotations

import json
import logging
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Types of federated knowledge
# ---------------------------------------------------------------------------

class KnowledgeType(str, Enum):
    PATTERN = "pattern"           # Patrones de Ã©xito/fracaso
    PROMPT = "prompt"             # Prompts optimizados
    ADR = "adr"                   # Decisiones arquitectÃ³nicas
    METRIC = "metric"             # MÃ©tricas de rendimiento
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
        id: Identificador Ãºnico (ej. "pattern:task_planner:subtask_count")
        type: Tipo de conocimiento (KnowledgeType)
        source_project: Proyecto de origen
        source_agent: Agente que generÃ³ el conocimiento
        key: Clave semÃ¡ntica del conocimiento
        value: Valor (serializable)
        tags: Tags para bÃºsqueda
        version: VersiÃ³n del registro
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
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    updated_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
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
        elapsed = (datetime.now(timezone.utc) - created).total_seconds()
        return elapsed > self.ttl_seconds


# ---------------------------------------------------------------------------
# FederatedMemoryStore
# ---------------------------------------------------------------------------

class FederatedMemoryStore:
    """
    AlmacÃ©n de memoria federada con capacidad de sync entre proyectos.

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
            auto_sync: Si True, inicia sync periÃ³dico en background.
            sync_interval_sec: Intervalo de sync en segundos (default 5min).
        """
        self._project_name = project_name

        if federated_dir:
            self._federated_dir = Path(federated_dir)
        else:
            # Default: project root / .opencode / federated /
            self._federated_dir = (
                Path(__file__).resolve().parent.parent.parent
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

    # ------------------------------------------------------------------
    # Public API - Store
    # ------------------------------------------------------------------

    def store_knowledge(
        self,
        key: str,
        value: Any,
        ktype: KnowledgeType = KnowledgeType.PATTERN,
        source_agent: str = "system",
        tags: list[str] | None = None,
        confidence: float = 1.0,
        ttl_seconds: int = 0,
    ) -> KnowledgeRecord:
        """
        Almacena un registro de conocimiento.

        Args:
            key: Clave semÃ¡ntica (ej. "task_planner:optimal_subtask_count").
            value: Valor serializable.
            ktype: Tipo de conocimiento.
            source_agent: Agente que generÃ³ el conocimiento.
            tags: Tags para bÃºsqueda.
            confidence: Confianza 0.0-1.0.
            ttl_seconds: TTL en segundos (0 = forever).

        Returns:
            KnowledgeRecord creado/actualizado.
        """
        record_id = f"{ktype.value}:{self._project_name}:{key}"

        with self._lock:
            existing = self._local_store.get(record_id)

            if existing:
                # Update existing
                existing.value = value
                existing.version += 1
                existing.updated_at = datetime.now(timezone.utc).isoformat()
                existing.confidence = confidence
                existing.tags = list(set(existing.tags + (tags or [])))
                record = existing
            else:
                record = KnowledgeRecord(
                    id=record_id,
                    type=ktype,
                    source_project=self._project_name,
                    source_agent=source_agent,
                    key=key,
                    value=value,
                    tags=tags or [],
                    confidence=confidence,
                    ttl_seconds=ttl_seconds,
                )
                self._local_store[record_id] = record

        self._save_local()
        return record

    def delete_knowledge(self, key: str, ktype: KnowledgeType) -> bool:
        """Elimina un registro de conocimiento."""
        record_id = f"{ktype.value}:{self._project_name}:{key}"
        with self._lock:
            if record_id in self._local_store:
                del self._local_store[record_id]
                self._save_local()
                return True
        return False

    # ------------------------------------------------------------------
    # Public API - Query
    # ------------------------------------------------------------------

    def query_knowledge(
        self,
        key_prefix: str = "",
        ktype: KnowledgeType | None = None,
        tags: list[str] | None = None,
        min_confidence: float = 0.0,
        include_expired: bool = False,
        limit: int = 50,
    ) -> list[KnowledgeRecord]:
        """
        Consulta conocimiento federado.

        Args:
            key_prefix: Filtro por prefijo de key.
            ktype: Filtro por tipo de conocimiento.
            tags: Filtro por tags (AND).
            min_confidence: Confianza mÃ­nima.
            include_expired: Incluir registros expirados.
            limit: MÃ¡ximo de resultados.

        Returns:
            Lista de KnowledgeRecord matching.
        """
        # Force sync from disk
        self._load_local()

        results = []
        with self._lock:
            for record in self._local_store.values():
                # Filter: type
                if ktype and record.type != ktype:
                    continue

                # Filter: key prefix
                if key_prefix and not record.key.startswith(key_prefix):
                    continue

                # Filter: tags
                if tags and not all(t in record.tags for t in tags):
                    continue

                # Filter: confidence
                if record.confidence < min_confidence:
                    continue

                # Filter: expired
                if not include_expired and record.is_expired():
                    continue

                results.append(record)

        results.sort(key=lambda r: r.confidence, reverse=True)
        return results[:limit]

    def get_knowledge(
        self, key: str, ktype: KnowledgeType,
    ) -> KnowledgeRecord | None:
        """Obtiene un registro especÃ­fico por key + type."""
        results = self.query_knowledge(
            key_prefix=key, ktype=ktype, include_expired=False, limit=1,
        )
        return results[0] if results else None

    def list_projects(self) -> set[str]:
        """Lista todos los proyectos que han contribuido conocimiento."""
        projects = set()
        with self._lock:
            for record in self._local_store.values():
                projects.add(record.source_project)
        return projects

    def get_stats(self) -> dict:
        """EstadÃ­sticas del store federado."""
        with self._lock:
            total = len(self._local_store)
            by_type: dict = {}
            by_project: dict = {}
            expired = 0

            for record in self._local_store.values():
                t = record.type.value if isinstance(record.type, KnowledgeType) else str(record.type)
                p = record.source_project
                by_type[t] = by_type.get(t, 0) + 1
                by_project[p] = by_project.get(p, 0) + 1
                if record.is_expired():
                    expired += 1

        return {
            "total_records": total,
            "expired_records": expired,
            "by_type": by_type,
            "by_project": by_project,
            "projects": len(by_project),
            "federated_dir": str(self._federated_dir),
        }

    # ------------------------------------------------------------------
    # Sync
    # ------------------------------------------------------------------

    def sync(self) -> int:
        """
        Sincroniza el conocimiento local con el directorio federado.

        Lee todos los archivos JSON de otros proyectos, los mergea
        con el store local, y escribe el store actualizado.

        Returns:
            Cantidad de registros nuevos importados.
        """
        imported = 0
        with self._lock:
            # Read all federated files (except our own)
            our_file = self._get_project_file()

            for fpath in self._federated_dir.glob("knowledge_*.json"):
                if fpath.resolve() == our_file.resolve():
                    continue  # Skip our own file

                try:
                    with open(fpath, "r", encoding="utf-8") as f:
                        data = json.load(f)

                    for record_dict in data.get("records", []):
                        record = KnowledgeRecord.from_dict(record_dict)

                        # Don't overwrite our own records with same id
                        if record.id in self._local_store:
                            # Our version is newer? skip
                            existing = self._local_store[record.id]
                            if existing.version >= record.version:
                                continue

                        # Merge
                        self._local_store[record.id] = record
                        imported += 1

                except (json.JSONDecodeError, KeyError) as e:
                    logger.warning(
                        "Federated sync: error reading %s: %s",
                        fpath.name, e,
                    )

            # Write our knowledge (with our updates + others merged)
            self._save_local()

        if imported > 0:
            logger.info(
                "Federated sync: imported %d records from %d projects",
                imported, len(self.list_projects()),
            )
        return imported

    def clear(self) -> None:
        """Limpia todo el conocimiento local (no afecta otros proyectos)."""
        with self._lock:
            self._local_store.clear()
            self._save_local()
        logger.info("FederatedMemoryStore cleared.")

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _get_project_file(self) -> Path:
        """Obtiene la ruta del archivo JSON de este proyecto."""
        safe_name = self._project_name.replace(" ", "_").replace("/", "_")
        return self._federated_dir / f"knowledge_{safe_name}.json"

    def _save_local(self) -> None:
        """Escribe el store local a disco."""
        filepath = self._get_project_file()
        records = [
            r.to_dict() for r in self._local_store.values()
        ]
        data = {
            "project": self._project_name,
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "record_count": len(records),
            "records": records,
        }
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    def _load_local(self) -> None:
        """Carga el store local desde disco."""
        filepath = self._get_project_file()
        if not filepath.exists():
            return

        try:
            with open(filepath, "r", encoding="utf-8") as f:
                data = json.load(f)

            with self._lock:
                for record_dict in data.get("records", []):
                    record = KnowledgeRecord.from_dict(record_dict)
                    self._local_store[record.id] = record

        except (json.JSONDecodeError, KeyError) as e:
            logger.warning("Federated load: error reading %s: %s", filepath, e)

    def _start_sync_thread(self) -> None:
        """Inicia thread de sync periÃ³dico."""
        def sync_loop():
            while not self._sync_event.is_set():
                self.sync()
                self._sync_event.wait(timeout=self._sync_interval)

        self._sync_thread = threading.Thread(
            target=sync_loop,
            name="federated-sync",
            daemon=True,
        )
        self._sync_thread.start()
        logger.info(
            "Federated sync thread started (interval=%ds)",
            self._sync_interval,
        )

    def stop_sync(self) -> None:
        """Detiene el sync periÃ³dico."""
        if self._sync_thread and self._sync_thread.is_alive():
            self._sync_event.set()
            self._sync_thread.join(timeout=5)
            logger.info("Federated sync thread stopped.")


# ---------------------------------------------------------------------------
# Convenience: auto-discover and sync across projects
# ---------------------------------------------------------------------------

def discover_federated_projects(
    base_dir: str | None = None,
) -> list[str]:
    """
    Descubre proyectos federados escaneando directorios.

    Busca archivos knowledge_*.json en el directorio federado
    y devuelve los nombres de proyectos encontrados.

    Args:
        base_dir: Directorio base (default: workspace root).

    Returns:
        Lista de nombres de proyectos federados.
    """
    if not base_dir:
        base_dir = Path(__file__).resolve().parent.parent.parent

    federated_dir = Path(base_dir) / ".opencode" / "federated"
    if not federated_dir.exists():
        return []

    projects = []
    for fpath in federated_dir.glob("knowledge_*.json"):
        try:
            with open(fpath, "r", encoding="utf-8") as f:
                data = json.load(f)
            if "project" in data:
                projects.append(data["project"])
        except (json.JSONDecodeError, KeyError):
            continue

    return projects


def sync_all_projects(base_dir: str | None = None) -> dict[str, int]:
    """
    Sincroniza todos los proyectos federados descubiertos.

    Returns:
        Dict: {project_name: records_imported}
    """
    projects = discover_federated_projects(base_dir)
    results = {}
    for project in projects:
        try:
            store = FederatedMemoryStore(project_name=project)
            imported = store.sync()
            results[project] = imported
        except Exception as e:  # noqa: BLE001
            logger.warning("Error syncing project %s: %s", project, e)
            results[project] = -1
    return results
