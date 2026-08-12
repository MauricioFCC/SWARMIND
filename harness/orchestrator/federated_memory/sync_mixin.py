"""Federated Memory sync mixin — sync, clear y persistencia.

Extraccion mecanica del modulo original
``harness/orchestrator/federated_memory.py`` (sin cambios de logica
ni firmas): sync, clear, _get_project_file, _save_local, _load_local,
_start_sync_thread y stop_sync.
"""
from __future__ import annotations

import json
import logging
import threading
from datetime import UTC, datetime
from pathlib import Path

from .models import KnowledgeRecord

logger = logging.getLogger("harness.orchestrator.federated_memory")


class _SyncMixin:
    """Mixin con sync, persistencia y thread periodico."""

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
            "updated_at": datetime.now(UTC).isoformat(),
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
        """Inicia thread de sync periodico."""
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
        """Detiene el sync periodico."""
        if self._sync_thread and self._sync_thread.is_alive():
            self._sync_event.set()
            self._sync_thread.join(timeout=5)
            logger.info("Federated sync thread stopped.")
