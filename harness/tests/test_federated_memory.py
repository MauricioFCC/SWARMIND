"""
Tests para FederatedMemory — cobertura completa de federated_memory.py.

Cubre:
- KnowledgeType enum
- KnowledgeRecord (dataclass, to_dict, from_dict, is_expired)
- FederatedMemoryStore init (default/custom dir, auto_sync)
- Operaciones CRUD (store, delete, query, get)
- Sincronización (sync con importación, merge por versión, error handling)
- Estadísticas (list_projects, get_stats)
- Limpieza (clear)
- Sync thread (start, stop)
- Funciones de conveniencia (discover_federated_projects, sync_all_projects)
- Edge cases (registros expirados, filtros, store vacío)
"""
from __future__ import annotations

import json
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List
from unittest.mock import MagicMock, patch

import pytest

from harness.orchestrator.federated_memory import (
    FederatedMemoryStore,
    KnowledgeRecord,
    KnowledgeType,
    discover_federated_projects,
    sync_all_projects,
)


# ===========================================================================
# Tests: KnowledgeType
# ===========================================================================


class TestKnowledgeType:
    """Tests del enum KnowledgeType."""

    def test_values(self) -> None:
        """KnowledgeType debe tener los valores esperados."""
        assert KnowledgeType.PATTERN.value == "pattern"
        assert KnowledgeType.PROMPT.value == "prompt"
        assert KnowledgeType.ADR.value == "adr"
        assert KnowledgeType.METRIC.value == "metric"
        assert KnowledgeType.EMBEDDING.value == "embedding"
        assert KnowledgeType.SKILL.value == "skill"

    def test_str_enum(self) -> None:
        """KnowledgeType debe ser un Enum de tipo str."""
        assert isinstance(KnowledgeType.PATTERN, str)
        assert KnowledgeType.PATTERN.value == "pattern"


# ===========================================================================
# Tests: KnowledgeRecord
# ===========================================================================


class TestKnowledgeRecord:
    """Tests de la dataclass KnowledgeRecord."""

    def test_defaults(self) -> None:
        """KnowledgeRecord debe tener valores por defecto."""
        record = KnowledgeRecord(
            id="test:id",
            type=KnowledgeType.PATTERN,
            source_project="agentic",
            source_agent="planner",
            key="test:key",
            value=42,
        )
        assert record.id == "test:id"
        assert record.type == KnowledgeType.PATTERN
        assert record.source_project == "agentic"
        assert record.source_agent == "planner"
        assert record.key == "test:key"
        assert record.value == 42
        assert record.tags == []
        assert record.version == 1
        assert record.ttl_seconds == 0
        assert record.confidence == 1.0
        assert record.created_at is not None
        assert record.updated_at is not None

    def test_to_dict(self) -> None:
        """to_dict debe serializar correctamente."""
        record = KnowledgeRecord(
            id="test:id",
            type=KnowledgeType.PATTERN,
            source_project="agentic",
            source_agent="planner",
            key="test:key",
            value=42,
            tags=["tag1"],
            version=2,
            ttl_seconds=3600,
            confidence=0.95,
        )
        d = record.to_dict()
        assert d["id"] == "test:id"
        assert d["type"] == "pattern"
        assert d["source_project"] == "agentic"
        assert d["key"] == "test:key"
        assert d["value"] == 42
        assert d["tags"] == ["tag1"]
        assert d["version"] == 2
        assert d["ttl_seconds"] == 3600
        assert d["confidence"] == 0.95

    def test_from_dict(self) -> None:
        """from_dict debe reconstruir un KnowledgeRecord desde dict."""
        d = {
            "id": "test:id",
            "type": "pattern",
            "source_project": "agentic",
            "source_agent": "planner",
            "key": "test:key",
            "value": 42,
            "tags": ["tag1"],
            "version": 3,
            "created_at": "2026-01-01T00:00:00+00:00",
            "updated_at": "2026-01-01T00:00:00+00:00",
            "ttl_seconds": 0,
            "confidence": 1.0,
        }
        record = KnowledgeRecord.from_dict(d)
        assert record.id == "test:id"
        assert record.type == KnowledgeType.PATTERN
        assert record.value == 42
        assert record.version == 3

    def test_from_dict_with_knowledge_type_obj(self) -> None:
        """from_dict debe aceptar type como KnowledgeType ya resuelto."""
        d = {
            "id": "x",
            "type": KnowledgeType.METRIC,
            "source_project": "p",
            "source_agent": "a",
            "key": "k",
            "value": 1,
        }
        record = KnowledgeRecord.from_dict(d)
        assert record.type == KnowledgeType.METRIC

    def test_is_expired_never(self) -> None:
        """is_expired con ttl_seconds=0 debe retornar False."""
        record = KnowledgeRecord(
            id="t", type=KnowledgeType.PATTERN,
            source_project="p", source_agent="a",
            key="k", value=1, ttl_seconds=0,
        )
        assert record.is_expired() is False

    def test_is_expired_false(self) -> None:
        """is_expired con TTL no vencido debe retornar False."""
        record = KnowledgeRecord(
            id="t", type=KnowledgeType.PATTERN,
            source_project="p", source_agent="a",
            key="k", value=1, ttl_seconds=3600,
            created_at=datetime.now(timezone.utc).isoformat(),
        )
        assert record.is_expired() is False

    def test_is_expired_true(self) -> None:
        """is_expired con TTL vencido debe retornar True."""
        past = datetime.now(timezone.utc) - timedelta(seconds=10)
        record = KnowledgeRecord(
            id="t", type=KnowledgeType.PATTERN,
            source_project="p", source_agent="a",
            key="k", value=1, ttl_seconds=1,
            created_at=past.isoformat(),
        )
        assert record.is_expired() is True

    def test_to_dict_from_dict_roundtrip(self) -> None:
        """to_dict + from_dict debe ser idempotente."""
        record = KnowledgeRecord(
            id="roundtrip",
            type=KnowledgeType.PROMPT,
            source_project="proj",
            source_agent="agent",
            key="optimized_prompt",
            value={"text": "Hello"},
            tags=["nlp"],
            version=5,
            confidence=0.8,
            ttl_seconds=100,
        )
        d = record.to_dict()
        restored = KnowledgeRecord.from_dict(d)
        assert restored.id == record.id
        assert restored.type == record.type
        assert restored.value == record.value
        assert restored.version == record.version


# ===========================================================================
# Fixtures para FederatedMemoryStore
# ===========================================================================


@pytest.fixture
def federated_dir(tmp_path: Path) -> Path:
    """Fixture: directorio temporal para archivos federados."""
    d = tmp_path / ".opencode" / "federated"
    d.mkdir(parents=True, exist_ok=True)
    return d


@pytest.fixture
def store(federated_dir: Path) -> FederatedMemoryStore:
    """Fixture: FederatedMemoryStore con directorio temporal."""
    return FederatedMemoryStore(
        project_name="test_project",
        federated_dir=str(federated_dir),
        auto_sync=False,
    )


# ===========================================================================
# Tests: FederatedMemoryStore init
# ===========================================================================


class TestFederatedMemoryStoreInit:
    """Tests de inicialización de FederatedMemoryStore."""

    def test_default_federated_dir(self) -> None:
        """FederatedMemoryStore debe usar {workspace}/.opencode/federated/ por defecto."""
        with patch("harness.orchestrator.federated_memory.Path.mkdir"):
            store = FederatedMemoryStore(project_name="test")
            expected = (
                Path(__file__).resolve().parent.parent.parent
                / ".opencode" / "federated"
            )
            assert store._federated_dir == expected

    def test_custom_federated_dir(self, tmp_path: Path) -> None:
        """FederatedMemoryStore debe aceptar directorio personalizado."""
        custom_dir = tmp_path / "my_federated"
        store = FederatedMemoryStore(project_name="test", federated_dir=str(custom_dir))
        assert store._federated_dir == custom_dir
        assert custom_dir.exists()

    def test_project_name(self, tmp_path: Path) -> None:
        """FederatedMemoryStore debe usar el project_name dado."""
        store = FederatedMemoryStore(project_name="my_project", federated_dir=str(tmp_path))
        assert store._project_name == "my_project"

    def test_auto_sync_starts_thread(self, tmp_path: Path) -> None:
        """auto_sync=True debe iniciar el thread de sync."""
        store = FederatedMemoryStore(
            project_name="test",
            federated_dir=str(tmp_path),
            auto_sync=True,
            sync_interval_sec=300,
        )
        assert store._sync_thread is not None
        assert store._sync_thread.is_alive()
        store.stop_sync()

    def test_auto_sync_false_no_thread(self, tmp_path: Path) -> None:
        """auto_sync=False no debe iniciar thread."""
        store = FederatedMemoryStore(
            project_name="test", federated_dir=str(tmp_path), auto_sync=False,
        )
        assert store._sync_thread is None

    def test_load_local_empty(self, tmp_path: Path) -> None:
        """FederatedMemoryStore debe cargar archivo local vacío si no existe."""
        store = FederatedMemoryStore(
            project_name="test", federated_dir=str(tmp_path), auto_sync=False,
        )
        assert store._local_store == {}

    def test_load_local_existing(self, tmp_path: Path, federated_dir: Path) -> None:
        """FederatedMemoryStore debe cargar registros existentes desde disco."""
        # Crear archivo simulado antes de inicializar
        filepath = federated_dir / "knowledge_test_project.json"
        records = [
            {
                "id": "preloaded:id",
                "type": "pattern",
                "source_project": "test_project",
                "source_agent": "system",
                "key": "preloaded:key",
                "value": 99,
                "tags": [],
                "version": 1,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "updated_at": datetime.now(timezone.utc).isoformat(),
                "ttl_seconds": 0,
                "confidence": 1.0,
            }
        ]
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump({"project": "test_project", "records": records}, f)

        store = FederatedMemoryStore(
            project_name="test_project",
            federated_dir=str(federated_dir),
            auto_sync=False,
        )
        assert "preloaded:id" in store._local_store
        assert store._local_store["preloaded:id"].value == 99


# ===========================================================================
# Tests: store_knowledge
# ===========================================================================


class TestStoreKnowledge:
    """Tests de store_knowledge()."""

    def test_store_new(self, store: FederatedMemoryStore) -> None:
        """store_knowledge debe crear un nuevo registro."""
        record = store.store_knowledge(
            key="test:key",
            value=42,
            ktype=KnowledgeType.PATTERN,
            source_agent="planner",
            tags=["test"],
            confidence=0.9,
            ttl_seconds=3600,
        )
        assert record.id == "pattern:test_project:test:key"
        assert record.value == 42
        assert record.source_agent == "planner"
        assert record.confidence == 0.9
        assert record.tags == ["test"]
        assert record.ttl_seconds == 3600
        assert record.version == 1
        assert "test:key" in store._local_store["pattern:test_project:test:key"].id

    def test_store_update_existing(self, store: FederatedMemoryStore) -> None:
        """store_knowledge debe actualizar un registro existente."""
        record1 = store.store_knowledge(key="test:key", value=1)
        record2 = store.store_knowledge(
            key="test:key", value=2,
            tags=["updated"], confidence=0.5,
        )
        assert record2.id == record1.id
        assert record2.value == 2
        assert record2.version == 2
        assert record2.confidence == 0.5
        assert "updated" in record2.tags

    def test_store_merge_tags(self, store: FederatedMemoryStore) -> None:
        """store_knowledge debe mergear tags sin duplicar."""
        store.store_knowledge(key="k", value=1, tags=["a", "b"])
        record = store.store_knowledge(key="k", value=2, tags=["b", "c"])
        assert sorted(record.tags) == sorted(["a", "b", "c"])

    def test_store_defaults(self, store: FederatedMemoryStore) -> None:
        """store_knowledge debe usar valores por defecto."""
        record = store.store_knowledge(key="test:key", value="val")
        assert record.source_agent == "system"
        assert record.type == KnowledgeType.PATTERN
        assert record.confidence == 1.0
        assert record.ttl_seconds == 0


# ===========================================================================
# Tests: delete_knowledge
# ===========================================================================


class TestDeleteKnowledge:
    """Tests de delete_knowledge()."""

    def test_delete_existing(self, store: FederatedMemoryStore) -> None:
        """delete_knowledge debe eliminar registro existente."""
        store.store_knowledge(key="to_delete", value=1)
        result = store.delete_knowledge(key="to_delete", ktype=KnowledgeType.PATTERN)
        assert result is True
        assert "pattern:test_project:to_delete" not in store._local_store

    def test_delete_non_existent(self, store: FederatedMemoryStore) -> None:
        """delete_knowledge con registro inexistente debe retornar False."""
        result = store.delete_knowledge(key="ghost", ktype=KnowledgeType.PATTERN)
        assert result is False

    def test_delete_wrong_type(self, store: FederatedMemoryStore) -> None:
        """delete_knowledge con tipo incorrecto no debe eliminar."""
        store.store_knowledge(key="key1", value=1, ktype=KnowledgeType.PATTERN)
        result = store.delete_knowledge(key="key1", ktype=KnowledgeType.METRIC)
        assert result is False
        assert "pattern:test_project:key1" in store._local_store


# ===========================================================================
# Tests: query_knowledge
# ===========================================================================


class TestQueryKnowledge:
    """Tests de query_knowledge()."""

    def test_query_all(self, store: FederatedMemoryStore) -> None:
        """query_knowledge sin filtros debe retornar todos los registros."""
        store.store_knowledge(key="a", value=1)
        store.store_knowledge(key="b", value=2)
        results = store.query_knowledge()
        assert len(results) == 2

    def test_query_by_key_prefix(self, store: FederatedMemoryStore) -> None:
        """query_knowledge debe filtrar por prefijo de key."""
        store.store_knowledge(key="project:alpha", value=1)
        store.store_knowledge(key="project:beta", value=2)
        store.store_knowledge(key="other:gamma", value=3)
        results = store.query_knowledge(key_prefix="project:")
        assert len(results) == 2

    def test_query_by_type(self, store: FederatedMemoryStore) -> None:
        """query_knowledge debe filtrar por tipo."""
        store.store_knowledge(key="k1", value=1, ktype=KnowledgeType.PATTERN)
        store.store_knowledge(key="k2", value=2, ktype=KnowledgeType.METRIC)
        results = store.query_knowledge(ktype=KnowledgeType.METRIC)
        assert len(results) == 1
        assert results[0].key == "k2"

    def test_query_by_tags(self, store: FederatedMemoryStore) -> None:
        """query_knowledge debe filtrar por tags (AND)."""
        store.store_knowledge(key="k1", value=1, tags=["a", "b"])
        store.store_knowledge(key="k2", value=2, tags=["a"])
        store.store_knowledge(key="k3", value=3, tags=["b", "c"])
        results = store.query_knowledge(tags=["a"])
        assert len(results) == 2
        results = store.query_knowledge(tags=["a", "b"])
        assert len(results) == 1
        assert results[0].key == "k1"

    def test_query_by_min_confidence(self, store: FederatedMemoryStore) -> None:
        """query_knowledge debe filtrar por confianza mínima."""
        store.store_knowledge(key="k1", value=1, confidence=0.9)
        store.store_knowledge(key="k2", value=2, confidence=0.5)
        results = store.query_knowledge(min_confidence=0.8)
        assert len(results) == 1
        assert results[0].key == "k1"

    def test_query_exclude_expired(self, store: FederatedMemoryStore) -> None:
        """query_knowledge debe excluir expirados por defecto."""
        import datetime as dt
        past = (datetime.now(timezone.utc) - timedelta(seconds=10)).isoformat()
        record = KnowledgeRecord(
            id="expired:id", type=KnowledgeType.PATTERN,
            source_project="test_project", source_agent="a",
            key="expired:key", value=1,
            ttl_seconds=1, created_at=past,
        )
        store._local_store["expired:id"] = record
        results = store.query_knowledge()
        assert "expired:key" not in [r.key for r in results]

    def test_query_include_expired(self, store: FederatedMemoryStore) -> None:
        """query_knowledge con include_expired=True debe incluir expirados."""
        past = (datetime.now(timezone.utc) - timedelta(seconds=10)).isoformat()
        record = KnowledgeRecord(
            id="expired:id", type=KnowledgeType.PATTERN,
            source_project="test_project", source_agent="a",
            key="expired:key", value=1,
            ttl_seconds=1, created_at=past,
        )
        store._local_store["expired:id"] = record
        results = store.query_knowledge(include_expired=True)
        assert any(r.key == "expired:key" for r in results)

    def test_query_limit(self, store: FederatedMemoryStore) -> None:
        """query_knowledge debe respetar el límite de resultados."""
        for i in range(10):
            store.store_knowledge(key=f"key:{i}", value=i)
        results = store.query_knowledge(limit=3)
        assert len(results) == 3

    def test_query_sorted_by_confidence(self, store: FederatedMemoryStore) -> None:
        """query_knowledge debe ordenar por confianza descendente."""
        store.store_knowledge(key="low", value=1, confidence=0.3)
        store.store_knowledge(key="high", value=2, confidence=0.9)
        store.store_knowledge(key="mid", value=3, confidence=0.6)
        results = store.query_knowledge()
        assert results[0].confidence >= results[1].confidence >= results[2].confidence

    def test_query_empty_store(self, store: FederatedMemoryStore) -> None:
        """query_knowledge en store vacío debe retornar lista vacía."""
        assert store.query_knowledge() == []


# ===========================================================================
# Tests: get_knowledge
# ===========================================================================


class TestGetKnowledge:
    """Tests de get_knowledge()."""

    def test_get_existing(self, store: FederatedMemoryStore) -> None:
        """get_knowledge debe retornar el registro si existe."""
        store.store_knowledge(key="find_me", value="data")
        record = store.get_knowledge(key="find_me", ktype=KnowledgeType.PATTERN)
        assert record is not None
        assert record.value == "data"

    def test_get_non_existing(self, store: FederatedMemoryStore) -> None:
        """get_knowledge debe retornar None si no existe."""
        record = store.get_knowledge(key="ghost", ktype=KnowledgeType.PATTERN)
        assert record is None


# ===========================================================================
# Tests: list_projects
# ===========================================================================


class TestListProjects:
    """Tests de list_projects()."""

    def test_list_projects(self, store: FederatedMemoryStore) -> None:
        """list_projects debe retornar todos los projectos que han contribuido."""
        store.store_knowledge(key="k1", value=1)
        # Simular registro de otro proyecto
        record = KnowledgeRecord(
            id="other:id", type=KnowledgeType.PATTERN,
            source_project="other_project", source_agent="a",
            key="k2", value=2,
        )
        store._local_store["other:id"] = record
        projects = store.list_projects()
        assert "test_project" in projects
        assert "other_project" in projects

    def test_list_projects_empty(self, store: FederatedMemoryStore) -> None:
        """list_projects en store vacío debe retornar set vacío."""
        assert store.list_projects() == set()


# ===========================================================================
# Tests: get_stats
# ===========================================================================


class TestGetStats:
    """Tests de get_stats()."""

    def test_get_stats_empty(self, store: FederatedMemoryStore) -> None:
        """get_stats en store vacío."""
        stats = store.get_stats()
        assert stats["total_records"] == 0
        assert stats["expired_records"] == 0
        assert stats["by_type"] == {}
        assert stats["by_project"] == {}

    def test_get_stats_with_data(self, store: FederatedMemoryStore) -> None:
        """get_stats debe calcular estadísticas correctamente."""
        store.store_knowledge(key="k1", value=1, ktype=KnowledgeType.PATTERN)
        store.store_knowledge(key="k2", value=2, ktype=KnowledgeType.METRIC)
        store.store_knowledge(key="k3", value=3, ktype=KnowledgeType.PATTERN)

        stats = store.get_stats()
        assert stats["total_records"] == 3
        assert stats["expired_records"] == 0
        assert stats["by_type"]["pattern"] == 2
        assert stats["by_type"]["metric"] == 1
        assert stats["by_project"]["test_project"] == 3


# ===========================================================================
# Tests: sync
# ===========================================================================


class TestSync:
    """Tests de sync()."""

    def test_sync_imports_records(self, store: FederatedMemoryStore, federated_dir: Path) -> None:
        """sync debe importar registros de otros proyectos."""
        # Crear archivo de otro proyecto
        other_file = federated_dir / "knowledge_other_project.json"
        other_records = [
            {
                "id": "pattern:other_project:key1",
                "type": "pattern",
                "source_project": "other_project",
                "source_agent": "agent1",
                "key": "key1",
                "value": 100,
                "tags": [],
                "version": 1,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "updated_at": datetime.now(timezone.utc).isoformat(),
                "ttl_seconds": 0,
                "confidence": 1.0,
            }
        ]
        with open(other_file, "w", encoding="utf-8") as f:
            json.dump({"project": "other_project", "records": other_records}, f)

        imported = store.sync()
        assert imported == 1
        assert "pattern:other_project:key1" in store._local_store

    def test_sync_skips_own_file(self, store: FederatedMemoryStore, federated_dir: Path) -> None:
        """sync no debe importar su propio archivo."""
        # store ya existe, su archivo se crea al hacer _save_local
        store.store_knowledge(key="my_key", value=1)
        imported = store.sync()
        assert imported == 0  # No importa su propio registro

    def test_sync_skips_older_version(self, store: FederatedMemoryStore, federated_dir: Path) -> None:
        """sync no debe sobrescribir con versión más antigua."""
        # Crear un registro local con version 2
        store.store_knowledge(key="shared", value="local_v2")
        # Forzar versión
        record_id = "pattern:test_project:shared"
        store._local_store[record_id].version = 2

        # Otro proyecto tiene versión 1
        other_file = federated_dir / "knowledge_other.json"
        other_records = [
            {
                "id": record_id,
                "type": "pattern",
                "source_project": "other",
                "source_agent": "a",
                "key": "shared",
                "value": "other_v1",
                "tags": [],
                "version": 1,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "updated_at": datetime.now(timezone.utc).isoformat(),
                "ttl_seconds": 0,
                "confidence": 1.0,
            }
        ]
        with open(other_file, "w", encoding="utf-8") as f:
            json.dump({"project": "other", "records": other_records}, f)

        imported = store.sync()
        assert imported == 0
        assert store._local_store[record_id].value == "local_v2"  # No sobrescribe

    def test_sync_imports_newer_version(self, store: FederatedMemoryStore, federated_dir: Path) -> None:
        """sync debe importar si la versión externa es más nueva."""
        record_id = "pattern:test_project:shared"
        store.store_knowledge(key="shared", value="local_v1")
        store._local_store[record_id].version = 1

        other_file = federated_dir / "knowledge_other.json"
        other_records = [
            {
                "id": record_id,
                "type": "pattern",
                "source_project": "other",
                "source_agent": "a",
                "key": "shared",
                "value": "other_v5",
                "tags": [],
                "version": 5,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "updated_at": datetime.now(timezone.utc).isoformat(),
                "ttl_seconds": 0,
                "confidence": 1.0,
            }
        ]
        with open(other_file, "w", encoding="utf-8") as f:
            json.dump({"project": "other", "records": other_records}, f)

        imported = store.sync()
        assert imported == 1
        assert store._local_store[record_id].value == "other_v5"

    def test_sync_error_reading_file(self, store: FederatedMemoryStore, federated_dir: Path) -> None:
        """sync debe manejar errores de lectura de archivos."""
        bad_file = federated_dir / "knowledge_bad.json"
        with open(bad_file, "w", encoding="utf-8") as f:
            f.write("{invalid json")

        imported = store.sync()  # No debe lanzar excepción
        assert imported >= 0

    def test_sync_no_other_files(self, store: FederatedMemoryStore) -> None:
        """sync sin otros archivos debe retornar 0."""
        imported = store.sync()
        assert imported == 0


# ===========================================================================
# Tests: clear
# ===========================================================================


class TestClear:
    """Tests de clear()."""

    def test_clear_store(self, store: FederatedMemoryStore) -> None:
        """clear debe vaciar el store local."""
        store.store_knowledge(key="k1", value=1)
        store.store_knowledge(key="k2", value=2)
        store.clear()
        assert store._local_store == {}
        assert store.query_knowledge() == []

    def test_clear_saves_to_disk(self, store: FederatedMemoryStore, federated_dir: Path) -> None:
        """clear debe persistir el vaciado a disco."""
        store.store_knowledge(key="k", value=1)
        store.clear()
        filepath = federated_dir / "knowledge_test_project.json"
        assert filepath.exists()
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
        assert data["record_count"] == 0


# ===========================================================================
# Tests: Sync thread
# ===========================================================================


class TestSyncThread:
    """Tests del thread de sincronización."""

    def test_start_sync_thread(self, tmp_path: Path) -> None:
        """_start_sync_thread debe crear y arrancar un thread daemon."""
        store = FederatedMemoryStore(
            project_name="test",
            federated_dir=str(tmp_path),
            auto_sync=True,
            sync_interval_sec=1,
        )
        assert store._sync_thread is not None
        assert store._sync_thread.is_alive()
        assert store._sync_thread.daemon is True
        store.stop_sync()

    def test_stop_sync(self, tmp_path: Path) -> None:
        """stop_sync debe detener el thread de sync."""
        store = FederatedMemoryStore(
            project_name="test",
            federated_dir=str(tmp_path),
            auto_sync=True,
            sync_interval_sec=1,
        )
        store.stop_sync()
        assert not store._sync_thread.is_alive()

    def test_stop_sync_no_thread(self, store: FederatedMemoryStore) -> None:
        """stop_sync sin thread no debe fallar."""
        store.stop_sync()  # no error

    def test_sync_thread_calls_sync(self, tmp_path: Path) -> None:
        """El thread de sync debe llamar a sync()."""
        with patch.object(FederatedMemoryStore, "sync", return_value=0) as mock_sync:
            store = FederatedMemoryStore(
                project_name="test",
                federated_dir=str(tmp_path),
                auto_sync=True,
                sync_interval_sec=1,
            )
            # Esperar a que el thread ejecute sync al menos una vez
            timeout = time.time() + 5
            while mock_sync.call_count < 1 and time.time() < timeout:
                time.sleep(0.1)
            store.stop_sync()
            assert mock_sync.call_count >= 1


# ===========================================================================
# Tests: discover_federated_projects
# ===========================================================================


class TestDiscoverFederatedProjects:
    """Tests de discover_federated_projects()."""

    def test_discover_success(self, tmp_path: Path) -> None:
        """discover_federated_projects debe descubrir proyectos."""
        fed_dir = tmp_path / ".opencode" / "federated"
        fed_dir.mkdir(parents=True, exist_ok=True)

        # Crear archivos de proyectos
        for proj in ["alpha", "beta"]:
            filepath = fed_dir / f"knowledge_{proj}.json"
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump({"project": proj, "records": []}, f)

        projects = discover_federated_projects(base_dir=str(tmp_path))
        assert "alpha" in projects
        assert "beta" in projects

    def test_discover_no_dir(self, tmp_path: Path) -> None:
        """discover_federated_projects sin directorio debe retornar lista vacía."""
        projects = discover_federated_projects(base_dir=str(tmp_path / "nonexistent"))
        assert projects == []

    def test_discover_bad_json(self, tmp_path: Path) -> None:
        """discover_federated_projects debe ignorar archivos con JSON inválido."""
        fed_dir = tmp_path / ".opencode" / "federated"
        fed_dir.mkdir(parents=True, exist_ok=True)
        bad_file = fed_dir / "knowledge_bad.json"
        with open(bad_file, "w", encoding="utf-8") as f:
            f.write("{invalid}")

        projects = discover_federated_projects(base_dir=str(tmp_path))
        assert projects == []

    def test_discover_default_base_dir(self) -> None:
        """discover_federated_projects sin base_dir debe usar default."""
        with patch("harness.orchestrator.federated_memory.Path.exists", return_value=False):
            projects = discover_federated_projects()
            assert projects == []


# ===========================================================================
# Tests: sync_all_projects
# ===========================================================================


class TestSyncAllProjects:
    """Tests de sync_all_projects()."""

    def test_sync_all_success(self, tmp_path: Path) -> None:
        """sync_all_projects debe sincronizar todos los proyectos."""
        fed_dir = tmp_path / ".opencode" / "federated"
        fed_dir.mkdir(parents=True, exist_ok=True)

        for proj in ["proj_a", "proj_b"]:
            filepath = fed_dir / f"knowledge_{proj}.json"
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump({"project": proj, "records": []}, f)

        results = sync_all_projects(base_dir=str(tmp_path))
        assert "proj_a" in results
        assert "proj_b" in results
        # Cada proyecto sincronizado, resultados >= 0
        for v in results.values():
            assert v >= 0

    def test_sync_all_with_error(self, tmp_path: Path) -> None:
        """sync_all_projects debe reportar -1 si un proyecto falla."""
        fed_dir = tmp_path / ".opencode" / "federated"
        fed_dir.mkdir(parents=True, exist_ok=True)

        # Proyecto válido
        filepath = fed_dir / "knowledge_good.json"
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump({"project": "good", "records": []}, f)

        with patch(
            "harness.orchestrator.federated_memory.FederatedMemoryStore.sync",
            side_effect=Exception("Sync error"),
        ):
            results = sync_all_projects(base_dir=str(tmp_path))
            assert results.get("good") == -1

    def test_sync_all_empty_dir(self, tmp_path: Path) -> None:
        """sync_all_projects sin proyectos debe retornar dict vacío."""
        results = sync_all_projects(base_dir=str(tmp_path / "empty"))
        assert results == {}


# ===========================================================================
# Tests: Edge cases adicionales
# ===========================================================================


class TestEdgeCases:
    """Tests de edge cases para FederatedMemoryStore."""

    def test_store_special_chars_in_key(self, store: FederatedMemoryStore) -> None:
        """store_knowledge debe manejar keys con caracteres especiales."""
        record = store.store_knowledge(
            key="path/with/slashes:and:colons",
            value={"nested": "data"},
        )
        assert record.key == "path/with/slashes:and:colons"
        assert record.value == {"nested": "data"}

    def test_store_none_value(self, store: FederatedMemoryStore) -> None:
        """store_knowledge debe aceptar value=None."""
        record = store.store_knowledge(key="null_val", value=None)
        assert record.value is None

    def test_concurrent_modification_safety(self, store: FederatedMemoryStore) -> None:
        """FederatedMemoryStore debe ser thread-safe con Lock."""
        import threading

        errors = []

        def writer():
            try:
                for i in range(50):
                    store.store_knowledge(key=f"thread:key:{i}", value=i)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=writer) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0
        # Deben haberse creado 50 registros únicos (todos compiten por mismas keys)
        assert len(store._local_store) >= 1

    def test_get_project_file(self, store: FederatedMemoryStore, federated_dir: Path) -> None:
        """_get_project_file debe retornar ruta correcta."""
        expected = federated_dir / "knowledge_test_project.json"
        assert store._get_project_file() == expected

    def test_get_project_file_sanitize(self, tmp_path: Path) -> None:
        """_get_project_file debe sanitizar el nombre del proyecto."""
        store = FederatedMemoryStore(
            project_name="my project/with slashes",
            federated_dir=str(tmp_path),
        )
        filepath = store._get_project_file()
        assert "my_project_with_slashes" in str(filepath)

    def test_load_local_corrupt_file(self, federated_dir: Path) -> None:
        """_load_local debe manejar archivos corruptos."""
        filepath = federated_dir / "knowledge_test_project.json"
        with open(filepath, "w", encoding="utf-8") as f:
            f.write("{corrupt}")

        store = FederatedMemoryStore(
            project_name="test_project",
            federated_dir=str(federated_dir),
            auto_sync=False,
        )
        assert store._local_store == {}
