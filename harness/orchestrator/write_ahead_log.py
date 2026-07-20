"""
Write-Ahead Log — Resiliencia ante fallos con retry/cancelacion.

Basado en patron Write-Ahead Log de sistemas de bases de datos.
Adaptado para sistemas multi-agente segun ADR-0018 Token Economics.

Provee:
- Registro de operaciones antes de ejecucion
- Reintento idempotente con backoff exponencial
- Cancelacion first-class de operaciones en progreso
- Recuperacion de estado tras crash
"""

from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, Optional, TypeVar

T = TypeVar("T")

logger = logging.getLogger(__name__)


class WALStatus(str, Enum):
    """Estados posibles de una entrada en el Write-Ahead Log."""

    PENDING = "pending"
    COMMITTED = "committed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class WALEntry:
    """
    Entrada individual del Write-Ahead Log.

    Attributes:
        operation_id: Identificador unico de la operacion.
        operation_type: Tipo de operacion (ej: 'llm_call', 'db_write').
        payload: Datos de la operacion (JSON-serializable).
        status: Estado actual de la operacion.
        created_at: Timestamp de creacion.
        retry_count: Numero de reintentos realizados.
        max_retries: Maximo de reintentos permitidos.
        error: Ultimo error registrado.
    """

    def __init__(
        self,
        operation_id: str,
        operation_type: str,
        payload: Dict[str, Any],
        max_retries: int = 3,
    ) -> None:
        self.operation_id = operation_id
        self.operation_type = operation_type
        self.payload = payload
        self.status = WALStatus.PENDING
        self.created_at = datetime.now(timezone.utc).isoformat()
        self.retry_count = 0
        self.max_retries = max_retries
        self.error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Serializar entrada a dict (JSON-compatible)."""
        return {
            "operation_id": self.operation_id,
            "operation_type": self.operation_type,
            "payload": self.payload,
            "status": self.status.value,
            "created_at": self.created_at,
            "retry_count": self.retry_count,
            "max_retries": self.max_retries,
            "error": self.error,
        }


class WriteAheadLog:
    """
    Write-Ahead Log para operaciones multi-agente.

    Usage:
        wal = WriteAheadLog()

        # Registrar operacion pendiente
        entry = wal.begin("llm_call", {"prompt": "..."})

        # Ejecutar con reintento automatico
        result = wal.execute(entry, my_llm_function)

        # Reintentar operaciones fallidas
        recovered = wal.recover_pending()
    """

    def __init__(self, log_dir: Optional[str] = None) -> None:
        """
        Args:
            log_dir: Directorio para persistir el log. Si es None, solo en memoria.
        """
        self._entries: Dict[str, WALEntry] = {}
        self._log_dir = Path(log_dir) if log_dir else None
        if self._log_dir:
            self._log_dir.mkdir(parents=True, exist_ok=True)

    def begin(
        self,
        operation_type: str,
        payload: Dict[str, Any],
        max_retries: int = 3,
    ) -> WALEntry:
        """
        Iniciar una nueva operacion en el log.

        Args:
            operation_type: Tipo de operacion.
            payload: Datos de la operacion.
            max_retries: Maximo de reintentos.

        Returns:
            La entrada creada.
        """
        import uuid
        entry = WALEntry(
            operation_id=str(uuid.uuid4())[:8],
            operation_type=operation_type,
            payload=payload,
            max_retries=max_retries,
        )
        self._entries[entry.operation_id] = entry
        self._persist()
        logger.debug("WAL begin: %s [%s]", entry.operation_id, operation_type)
        return entry

    def execute(
        self,
        entry: WALEntry,
        fn: Callable[..., T],
        *args: Any,
        **kwargs: Any,
    ) -> T:
        """
        Ejecutar una funcion con respaldo del WAL.

        Si la funcion falla, reintenta con backoff exponencial.
        Si se agotan los reintentos, marca como FAILED.

        Args:
            entry: Entrada del WAL.
            fn: Funcion a ejecutar.
            *args: Argumentos posicionales para fn.
            **kwargs: Argumentos nominales para fn.

        Returns:
            Resultado de la funcion.

        Raises:
            RuntimeError: Si se agotan los reintentos.
        """
        last_error: Optional[Exception] = None
        for attempt in range(entry.max_retries + 1):
            try:
                result = fn(*args, **kwargs)
                entry.status = WALStatus.COMMITTED
                self._persist()
                logger.debug(
                    "WAL commit: %s (attempt %d/%d)",
                    entry.operation_id, attempt + 1, entry.max_retries + 1,
                )
                return result
            except Exception as exc:
                last_error = exc
                entry.retry_count = attempt + 1
                entry.error = str(exc)
                entry.status = WALStatus.FAILED
                self._persist()
                logger.warning(
                    "WAL retry %d/%d: %s — %s",
                    attempt + 1, entry.max_retries + 1,
                    entry.operation_id, exc,
                )
                if attempt < entry.max_retries:
                    time.sleep(2 ** attempt * 0.1)  # Backoff: 0.1, 0.2, 0.4s

        raise RuntimeError(
            f"WAL: operacion {entry.operation_id} fallo tras "
            f"{entry.max_retries + 1} intentos. Ultimo error: {last_error}"
        )

    def cancel(self, operation_id: str) -> bool:
        """
        Cancelar una operacion pendiente.

        Args:
            operation_id: ID de la operacion a cancelar.

        Returns:
            True si se cancelo, False si no existia.
        """
        entry = self._entries.get(operation_id)
        if entry and entry.status == WALStatus.PENDING:
            entry.status = WALStatus.CANCELLED
            self._persist()
            logger.info("WAL cancel: %s", operation_id)
            return True
        return False

    def recover_pending(self) -> list[WALEntry]:
        """
        Recuperar operaciones pendientes (para recovery tras crash).

        Returns:
            Lista de entradas pendientes.
        """
        return [
            e for e in self._entries.values()
            if e.status == WALStatus.PENDING
        ]

    def get_status(self, operation_id: str) -> Optional[WALStatus]:
        """
        Obtener estado de una operacion.

        Args:
            operation_id: ID de la operacion.

        Returns:
            Estado de la operacion o None si no existe.
        """
        entry = self._entries.get(operation_id)
        return entry.status if entry else None

    def _persist(self) -> None:
        """Persistir el log a disco (si hay log_dir configurado)."""
        if not self._log_dir:
            return
        try:
            path = self._log_dir / "wal_log.json"
            data = {
                e.operation_id: e.to_dict()
                for e in self._entries.values()
            }
            path.write_text(json.dumps(data, indent=2, ensure_ascii=False))
        except Exception as exc:
            logger.warning("WAL persist error: %s", exc)

    def load_from_disk(self) -> int:
        """
        Cargar entradas desde disco (para recovery).

        Returns:
            Numero de entradas cargadas.
        """
        if not self._log_dir:
            return 0
        path = self._log_dir / "wal_log.json"
        if not path.exists():
            return 0
        try:
            data = json.loads(path.read_text())
            for op_id, entry_data in data.items():
                entry = WALEntry(
                    operation_id=entry_data["operation_id"],
                    operation_type=entry_data["operation_type"],
                    payload=entry_data["payload"],
                    max_retries=entry_data.get("max_retries", 3),
                )
                entry.status = WALStatus(entry_data["status"])
                entry.retry_count = entry_data.get("retry_count", 0)
                entry.error = entry_data.get("error")
                self._entries[op_id] = entry
            logger.info("WAL loaded %d entries from disk", len(data))
            return len(data)
        except Exception as exc:
            logger.warning("WAL load error: %s", exc)
            return 0
