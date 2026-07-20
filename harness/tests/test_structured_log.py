"""Tests para StructuredLogRecord — registro estructurado en JSON."""
from __future__ import annotations

import json
import logging
import pytest
from harness.orchestrator.structured_log import StructuredLogRecord


class TestStructuredLogRecord:
    """Verifica los metodos staticos de StructuredLogRecord."""

    def test_log_info(self, caplog):
        """info emite log con level INFO."""
        caplog.set_level(logging.INFO)
        StructuredLogRecord.info("evt_info", "mensaje informativo", session_id="sess-1")
        assert len(caplog.records) >= 1
        record = caplog.records[-1]
        assert record.levelname == "INFO"
        data = json.loads(record.message)
        assert data["event"] == "evt_info"
        assert data["session_id"] == "sess-1"
        assert data["message"] == "mensaje informativo"

    def test_log_warning(self, caplog):
        """warning emite log con level WARNING."""
        caplog.set_level(logging.WARNING)
        StructuredLogRecord.warning("evt_warn", "alerta", session_id="sess-2")
        assert len(caplog.records) >= 1
        assert caplog.records[-1].levelname == "WARNING"

    def test_log_error(self, caplog):
        """error emite log con level ERROR."""
        caplog.set_level(logging.ERROR)
        StructuredLogRecord.error("evt_error", "fallo critico", session_id="sess-3")
        assert len(caplog.records) >= 1
        record = caplog.records[-1]
        assert record.levelname == "ERROR"
        data = json.loads(record.message)
        assert data["event"] == "evt_error"
        assert data["level"] == "ERROR"

    def test_log_debug(self, caplog):
        """debug emite log con level DEBUG."""
        caplog.set_level(logging.DEBUG)
        StructuredLogRecord.debug("evt_debug", "depurando", session_id="sess-4")
        assert len(caplog.records) >= 1
        record = caplog.records[-1]
        assert record.levelname == "DEBUG"
        data = json.loads(record.message)
        assert data["event"] == "evt_debug"
        assert data["level"] == "DEBUG"

    def test_log_unknown_level_falls_back_to_info(self, caplog):
        """Level desconocido usa info como fallback."""
        caplog.set_level(logging.INFO)
        record = StructuredLogRecord("test_event", level="UNKNOWN")
        record.log(logging.getLogger())
        assert len(caplog.records) >= 1
        assert caplog.records[-1].levelname == "INFO"

    def test_log_includes_extra_fields(self, caplog):
        """Campos extra se incluyen en el JSON."""
        caplog.set_level(logging.INFO)
        StructuredLogRecord.info("evt_extra", "con extra", error_code=42, module_name="test")
        data = json.loads(caplog.records[-1].message)
        assert data["error_code"] == 42
        assert data["module_name"] == "test"

    def test_log_without_session_id(self, caplog):
        """Sin session_id el campo queda en string vacio."""
        caplog.set_level(logging.INFO)
        StructuredLogRecord.info("evt_no_session", "sin id")
        data = json.loads(caplog.records[-1].message)
        assert data["session_id"] == ""
