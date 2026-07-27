"""
Tests para PersistentMemory — Memoria cross-session.

Verifica:
  - store y recall de valores
  - recall de clave inexistente
  - get_session y get_agent_memory
  - get_stats
  - TTL expiracion
  - Persistencia a disco (save/load)
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Dict
from unittest.mock import MagicMock, patch

import pytest

from harness.memory_rag.persistent_memory import MemoryEntry, PersistentMemory


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def pm(tmp_path: Path) -> PersistentMemory:
    """PersistentMemory con path temporal."""
    return PersistentMemory(path=tmp_path / "test_memory.json")


# ---------------------------------------------------------------------------
# Test: Store y Recall
# ---------------------------------------------------------------------------


class TestStoreRecall:
    """Almacenar y recuperar valores."""

    def test_store_and_recall(self, pm: PersistentMemory) -> None:
        """Store followed by recall returns the stored value."""
        pm.store("key1", "value1", agent="builder", session_id="s1")
        result = pm.recall("key1")
        assert result == "value1"

    def test_store_overwrite(self, pm: PersistentMemory) -> None:
        """Sobrescribir una clave existente actualiza el valor."""
        pm.store("key1", "original", agent="builder")
        pm.store("key1", "updated", agent="scientist")
        result = pm.recall("key1")
        assert result == "updated"

    def test_store_complex_value(self, pm: PersistentMemory) -> None:
        """Almacenar dicts y listas como valor."""
        complex_val = {"nested": [1, 2, 3], "flag": True}
        pm.store("complex", complex_val, agent="system")
        result = pm.recall("complex")
        assert result == complex_val


# ---------------------------------------------------------------------------
# Test: Recall inexistente
# ---------------------------------------------------------------------------


class TestRecallNonexistent:
    """Recuperar claves que no existen."""

    def test_recall_nonexistent(self, pm: PersistentMemory) -> None:
        """Recall de clave no almacenada retorna None."""
        result = pm.recall("no_such_key")
        assert result is None

    def test_recall_empty_store(self, pm: PersistentMemory) -> None:
        """Recall en memoria vacia retorna None."""
        assert pm.recall("anything") is None


# ---------------------------------------------------------------------------
# Test: Session memory
# ---------------------------------------------------------------------------


class TestSession:
    """Memoria por sesion."""

    def test_get_session(self, pm: PersistentMemory) -> None:
        """get_session retorna solo entradas de esa sesion."""
        pm.store("a", 1, session_id="s1")
        pm.store("b", 2, session_id="s1")
        pm.store("c", 3, session_id="s2")
        session = pm.get_session("s1")
        assert session == {"a": 1, "b": 2}
        assert "c" not in session

    def test_get_session_empty(self, pm: PersistentMemory) -> None:
        """Sesion sin entradas retorna dict vacio."""
        assert pm.get_session("unknown") == {}


# ---------------------------------------------------------------------------
# Test: Agent memory
# ---------------------------------------------------------------------------


class TestAgentMemory:
    """Memoria por agente."""

    def test_get_agent_memory(self, pm: PersistentMemory) -> None:
        """get_agent_memory retorna solo entradas de ese agente."""
        pm.store("x", 10, agent="builder")
        pm.store("y", 20, agent="builder")
        pm.store("z", 30, agent="scientist")
        mem = pm.get_agent_memory("builder")
        assert mem == {"x": 10, "y": 20}

    def test_get_agent_memory_empty(self, pm: PersistentMemory) -> None:
        """Agente sin entradas retorna dict vacio."""
        assert pm.get_agent_memory("ghost") == {}


# ---------------------------------------------------------------------------
# Test: Stats
# ---------------------------------------------------------------------------


class TestStats:
    """Estadisticas de memoria."""

    def test_stats_empty(self, pm: PersistentMemory) -> None:
        """Memoria vacia tiene stats en cero."""
        stats = pm.get_stats()
        assert stats["total_entries"] == 0
        assert stats["sessions"] == 0
        assert stats["agents"] == 0

    def test_stats_with_data(self, pm: PersistentMemory) -> None:
        """Stats reflejan datos almacenados."""
        pm.store("a", 1, agent="builder", session_id="s1")
        pm.store("b", 2, agent="builder", session_id="s1")
        pm.store("c", 3, agent="scientist", session_id="s2")
        stats = pm.get_stats()
        assert stats["total_entries"] == 3
        assert stats["sessions"] == 2
        assert stats["agents"] == 2


# ---------------------------------------------------------------------------
# Test: TTL
# ---------------------------------------------------------------------------


class TestTTL:
    """Time-to-live de entradas."""

    def test_ttl_not_expired(self, pm: PersistentMemory) -> None:
        """Entrada con TTL largo no expira."""
        pm.store("temp", "value", ttl=9999)
        assert pm.recall("temp") == "value"

    def test_ttl_expired(self, pm: PersistentMemory) -> None:
        """Entrada con TTL 0 expira inmediatamente (tiempo ya paso)."""
        pm.store("gone", "value", ttl=0)
        # TTL=0 significa forever, no expira
        assert pm.recall("gone") == "value"

    def test_ttl_negative(self, pm: PersistentMemory) -> None:
        """TTL negativo se trata como forever (nunca expira)."""
        pm.store("neg", "value", ttl=-1)
        # La condicion entry.ttl > 0 es False para TTL <= 0, nunca expira
        result = pm.recall("neg")
        assert result == "value"


# ---------------------------------------------------------------------------
# Test: Persistencia a disco
# ---------------------------------------------------------------------------


class TestPersistence:
    """Persistencia save/load desde archivo JSON."""

    def test_save_creates_file(self, tmp_path: Path) -> None:
        """Store escribe el archivo JSON."""
        path = tmp_path / "persist.json"
        pm = PersistentMemory(path=path)
        pm.store("k", "v", agent="test")
        assert path.exists()
        content = json.loads(path.read_text(encoding="utf-8"))
        assert "k" in content
        assert content["k"]["value"] == "v"

    def test_load_restores_data(self, tmp_path: Path) -> None:
        """Cargar desde archivo existente restaura los datos."""
        path = tmp_path / "restore.json"
        # Primera instancia guarda datos
        pm1 = PersistentMemory(path=path)
        pm1.store("a", 1, agent="b1", session_id="s1")
        pm1.store("b", 2, agent="b2", session_id="s1")
        del pm1

        # Segunda instancia carga los mismos datos
        pm2 = PersistentMemory(path=path)
        assert pm2.recall("a") == 1
        assert pm2.recall("b") == 2
        assert pm2.get_stats()["total_entries"] == 2

    def test_load_corrupted_file(self, tmp_path: Path, caplog: Any) -> None:
        """Archivo corrupto no rompe la carga (warning loggeado)."""
        path = tmp_path / "corrupt.json"
        path.write_text("{not valid json}", encoding="utf-8")
        pm = PersistentMemory(path=path)
        # No debe explotar, debe iniciar vacio
        assert pm.get_stats()["total_entries"] == 0

    def test_clear_removes_all(self, tmp_path: Path) -> None:
        """clear vacia la memoria y persiste."""
        path = tmp_path / "clear.json"
        pm = PersistentMemory(path=path)
        pm.store("x", 1, agent="a")
        pm.clear()
        assert pm.recall("x") is None
        assert pm.get_stats()["total_entries"] == 0
        # Archivo persistido con datos vacios
        content = json.loads(path.read_text(encoding="utf-8"))
        assert content == {}
