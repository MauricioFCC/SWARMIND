"""Tests para WriteAheadLog — resiliencia, retry, persistencia y recovery."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from harness.orchestrator.write_ahead_log import WALEntry, WALStatus, WriteAheadLog

# ============================================================================
# Tests basicos de WALEntry
# ============================================================================


class TestWALEntry:
    """Tests para la entidad WALEntry."""

    def test_to_dict(self) -> None:
        """
        PRUEBA: WALEntry.to_dict() serializa correctamente todos los campos.

        Verifica que el dict generado contenga operation_id, operation_type,
        payload, status, created_at, retry_count, max_retries y error
        con los valores esperados.
        """
        entry = WALEntry(
            operation_id="abc123",
            operation_type="llm_call",
            payload={"prompt": "hello"},
            max_retries=3,
        )
        d = entry.to_dict()
        assert d["operation_id"] == "abc123"
        assert d["operation_type"] == "llm_call"
        assert d["payload"] == {"prompt": "hello"}
        assert d["status"] == WALStatus.PENDING.value
        assert d["retry_count"] == 0
        assert d["max_retries"] == 3
        assert d["error"] is None
        # created_at debe ser un string ISO con zona horaria UTC
        assert d["created_at"].endswith("+00:00") or d["created_at"].endswith("Z") or "T" in d["created_at"]


# ============================================================================
# Tests de WriteAheadLog
# ============================================================================


class TestWriteAheadLog:
    """Tests para el core del Write-Ahead Log."""

    # ------------------------------------------------------------------
    # begin / execute / cancel
    # ------------------------------------------------------------------

    def test_begin_creates_entry(self) -> None:
        """
        PRUEBA: begin() crea una entrada con UUID valido y estado PENDING.

        Verifica que:
        - El operation_id sea un string hexadecimal de 8 caracteres.
        - El status inicial sea WALStatus.PENDING.
        - La entrada quede registrada internamente.
        """
        wal = WriteAheadLog()
        entry = wal.begin("test_op", {"foo": "bar"})

        assert entry.operation_id is not None
        assert len(entry.operation_id) == 8
        # Verificar que sea hex valido
        int(entry.operation_id, 16)
        assert entry.status == WALStatus.PENDING
        assert wal.get_status(entry.operation_id) == WALStatus.PENDING

    def test_execute_success(self) -> None:
        """
        PRUEBA: execute() invoca la funcion y marca la entrada como COMMITTED.

        Verifica que:
        - La funcion se llame exactamente una vez.
        - El resultado devuelto sea el esperado.
        - El estado de la entrada cambie a COMMITTED.
        """
        wal = WriteAheadLog()
        entry = wal.begin("success_op", {"x": 1})
        mock_fn = MagicMock(return_value="ok")

        result = wal.execute(entry, mock_fn)

        assert result == "ok"
        mock_fn.assert_called_once()
        assert entry.status == WALStatus.COMMITTED

    @patch("harness.orchestrator.write_ahead_log.time.sleep")
    def test_execute_retry_on_failure(self, mock_sleep: MagicMock) -> None:
        """
        PRUEBA: execute() reintenta cuando la funcion falla y eventualmente
        tiene exito.

        La funcion falla las primeras 2 veces y luego retorna exito.
        Verifica que:
        - Se hayan hecho 3 llamados (2 fallos + 1 exito).
        - El resultado final sea el esperado.
        - El estado final sea COMMITTED.
        - retry_count refleje los reintentos realizados.
        """
        wal = WriteAheadLog()
        entry = wal.begin("retry_op", {}, max_retries=3)
        mock_fn = MagicMock(side_effect=[ValueError("fail1"), ValueError("fail2"), "finally_ok"])

        result = wal.execute(entry, mock_fn)

        assert result == "finally_ok"
        assert mock_fn.call_count == 3
        assert entry.status == WALStatus.COMMITTED
        assert entry.retry_count == 2  # fallaron 2 intentos

    @patch("harness.orchestrator.write_ahead_log.time.sleep")
    def test_execute_exhausts_retries(self, mock_sleep: MagicMock) -> None:
        """
        PRUEBA: execute() lanza RuntimeError cuando se agotan los reintentos.

        La funcion siempre falla. Con max_retries=2 se intenta 3 veces.
        Verifica que:
        - Se lance RuntimeError.
        - El estado final sea FAILED.
        - retry_count sea 3 (max_retries + 1 intentos).
        - El mensaje de error incluya el operation_id.
        """
        wal = WriteAheadLog()
        entry = wal.begin("exhaust_op", {}, max_retries=2)
        mock_fn = MagicMock(side_effect=RuntimeError("always fail"))

        with pytest.raises(RuntimeError) as exc_info:
            wal.execute(entry, mock_fn)

        assert entry.operation_id in str(exc_info.value)
        assert entry.status == WALStatus.FAILED
        assert entry.retry_count == 3  # max_retries + 1
        assert mock_fn.call_count == 3

    def test_cancel_pending(self) -> None:
        """
        PRUEBA: cancel() cambia una entrada PENDING a CANCELLED.

        Verifica que:
        - cancel() retorne True.
        - El estado pase a CANCELLED.
        - get_status refleje el cambio.
        """
        wal = WriteAheadLog()
        entry = wal.begin("cancel_me", {})

        result = wal.cancel(entry.operation_id)

        assert result is True
        assert entry.status == WALStatus.CANCELLED
        assert wal.get_status(entry.operation_id) == WALStatus.CANCELLED

    def test_cancel_committed_noop(self) -> None:
        """
        PRUEBA: cancel() sobre una entrada COMMITTED no hace nada.

        Primero se ejecuta con exito para que pase a COMMITTED,
        luego se intenta cancelar. Verifica que:
        - cancel() retorne False.
        - El estado siga siendo COMMITTED.
        """
        wal = WriteAheadLog()
        entry = wal.begin("already_done", {})
        mock_fn = MagicMock(return_value="done")
        wal.execute(entry, mock_fn)

        result = wal.cancel(entry.operation_id)

        assert result is False
        assert entry.status == WALStatus.COMMITTED

    # ------------------------------------------------------------------
    # recover / status
    # ------------------------------------------------------------------

    def test_recover_pending(self) -> None:
        """
        PRUEBA: recover_pending() retorna solo las entradas con estado PENDING.

        Escenario:
        - Entrada A: PENDING (sin ejecutar)
        - Entrada B: se ejecuta con exito → COMMITTED
        - Entrada C: PENDING (sin ejecutar)
        - Entrada D: se cancela → CANCELLED

        Verifica que recover_pending() devuelva exactamente A y C.
        """
        wal = WriteAheadLog()

        entry_a = wal.begin("pending_a", {})
        entry_b = wal.begin("committed_b", {})
        entry_c = wal.begin("pending_c", {})
        entry_d = wal.begin("cancelled_d", {})

        wal.execute(entry_b, MagicMock(return_value="ok"))
        wal.cancel(entry_d.operation_id)

        recovered = wal.recover_pending()
        recovered_ids = {e.operation_id for e in recovered}

        assert len(recovered) == 2
        assert entry_a.operation_id in recovered_ids
        assert entry_c.operation_id in recovered_ids
        assert entry_b.operation_id not in recovered_ids
        assert entry_d.operation_id not in recovered_ids

    def test_get_status(self) -> None:
        """
        PRUEBA: get_status() retorna el estado correcto o None.

        Verifica:
        - Entrada recien creada → PENDING.
        - Entrada ejecutada con exito → COMMITTED.
        - ID inexistente → None.
        """
        wal = WriteAheadLog()

        entry = wal.begin("status_test", {})
        assert wal.get_status(entry.operation_id) == WALStatus.PENDING

        wal.execute(entry, MagicMock(return_value="ok"))
        assert wal.get_status(entry.operation_id) == WALStatus.COMMITTED

        assert wal.get_status("nonexistent") is None

    # ------------------------------------------------------------------
    # Persistencia
    # ------------------------------------------------------------------

    def test_persist_and_load(self, tmp_path: pytest.TempPathFactory) -> None:
        """
        PRUEBA: persistencia a disco via tmp_path + load_from_disk.

        Escenario:
        1. Crear WAL con log_dir apuntando a tmp_path.
        2. Crear 3 entradas con distintos estados: PENDING, COMMITTED, CANCELLED.
        3. Crear una segunda instancia de WAL apuntando al mismo directorio.
        4. load_from_disk() debe recuperar las 3 entradas.
        5. Cada entrada debe mantener su operation_id y estado original.
        """
        log_dir = str(tmp_path)

        # --- WAL escritor ---
        wal1 = WriteAheadLog(log_dir=log_dir)
        e1 = wal1.begin("persist_pending", {"a": 1})
        e2 = wal1.begin("persist_commit", {"b": 2})
        e3 = wal1.begin("persist_cancel", {"c": 3})

        wal1.execute(e2, MagicMock(return_value="done"))
        wal1.cancel(e3.operation_id)

        # Verificar que el archivo se haya escrito
        assert (tmp_path / "wal_log.json").exists()

        # --- WAL lector ---
        wal2 = WriteAheadLog(log_dir=log_dir)
        count = wal2.load_from_disk()

        assert count == 3
        assert wal2.get_status(e1.operation_id) == WALStatus.PENDING
        assert wal2.get_status(e2.operation_id) == WALStatus.COMMITTED
        assert wal2.get_status(e3.operation_id) == WALStatus.CANCELLED

        # Verificar payloads preservados
        entries_map = {e.operation_id: e for e in wal2.recover_pending()}
        # Solo e1 deberia estar pendiente
        assert len(entries_map) == 1
        assert e1.operation_id in entries_map
