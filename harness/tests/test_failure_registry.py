"""Tests del Failure Registry — registro estructurado de fallos.

Verifica:
  - Record creation con todos los campos
  - Persistencia JSONL (append + reload)
  - Queries: get_recent, get_by_type, get_by_severity, get_unresolved
  - Stats aggregation
  - Deduplicación de skills derivados
  - Inmutabilidad de FailureRecord (frozen dataclass)
"""
from __future__ import annotations

from pathlib import Path

import pytest

from harness.failure_registry import (
    FailureRecord,
    FailureRegistry,
    FailureType,
    Severity,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def registry(tmp_path: Path) -> FailureRegistry:
    """Registry aislado en directorio temporal."""
    return FailureRegistry(path=tmp_path / "failures.jsonl")


@pytest.fixture
def populated_registry(registry: FailureRegistry) -> FailureRegistry:
    """Registry con 5 fallos de prueba."""
    registry.record(
        task="deploy sync",
        failure_type="runtime",
        error_msg="FileNotFoundError",
        root_cause="JSON local no existe",
        resolution="Fallback a Path.home()",
        skill_derived="config-fallback",
        severity="medium",
    )
    registry.record(
        task="test failing",
        failure_type="test",
        error_msg="AssertionError",
        root_cause="Mock mal configurado",
        resolution="pending",
        severity="high",
    )
    registry.record(
        task="lint error",
        failure_type="lint",
        error_msg="ruff E501",
        root_cause="Linea > 88 chars",
        resolution="Reformat",
        severity="low",
    )
    registry.record(
        task="deploy sync v2",
        failure_type="runtime",
        error_msg="PermissionError",
        root_cause="Symlink sin Developer Mode",
        resolution="Fallback a copy",
        skill_derived="symlink-fallback",
        severity="medium",
    )
    registry.record(
        task="security scan",
        failure_type="security",
        error_msg="Hardcoded secret",
        root_cause="API key en test fixture",
        resolution="Usar os.getenv",
        severity="critical",
    )
    return registry


# ---------------------------------------------------------------------------
# FailureRecord (inmutabilidad)
# ---------------------------------------------------------------------------


class TestFailureRecord:
    """FailureRecord es un frozen dataclass (IMM)."""

    def test_creation_with_all_fields(self) -> None:
        """Campos requeridos + opcionales se crean correctamente."""
        record = FailureRecord(
            id="20260826T120000-1234",
            timestamp="2026-08-26T12:00:00+00:00",
            task="test task",
            failure_type=FailureType.RUNTIME,
            error_msg="test error",
            root_cause="test cause",
            resolution="test resolution",
            skill_derived="test-skill",
            severity=Severity.MEDIUM,
            file_path="test.py",
            function_name="test_func",
            tags=("tag1", "tag2"),
        )
        assert record.task == "test task"
        assert record.failure_type == FailureType.RUNTIME
        assert record.severity == Severity.MEDIUM
        assert record.tags == ("tag1", "tag2")

    def test_frozen_immutable(self) -> None:
        """No se puede modificar un FailureRecord después de crearlo."""
        record = FailureRecord(
            id="1", timestamp="t", task="x",
            failure_type=FailureType.TEST, error_msg="e",
            root_cause="r", resolution="res",
            skill_derived="", severity=Severity.LOW,
        )
        with pytest.raises(AttributeError):
            record.task = "modified"  # type: ignore[misc]

    def test_to_dict_roundtrip(self) -> None:
        """Serialización a dict y deserialización conservan todos los campos."""
        original = FailureRecord(
            id="20260826T120000-5678",
            timestamp="2026-08-26T12:00:00+00:00",
            task="roundtrip test",
            failure_type=FailureType.DEPLOY,
            error_msg="deploy failed",
            root_cause="network timeout",
            resolution="retry",
            skill_derived="retry-pattern",
            severity=Severity.HIGH,
            tags=("deploy", "network"),
        )
        d = original.to_dict()
        restored = FailureRecord.from_dict(d)
        assert restored == original
        assert restored.tags == ("deploy", "network")

    def test_tags_empty_tuple_default(self) -> None:
        """Tags vacío se serializa como lista y se deserializa como tuple."""
        record = FailureRecord(
            id="1", timestamp="t", task="x",
            failure_type=FailureType.CONFIG, error_msg="e",
            root_cause="r", resolution="res",
            skill_derived="", severity=Severity.LOW,
        )
        d = record.to_dict()
        assert d["tags"] == []
        restored = FailureRecord.from_dict(d)
        assert restored.tags == ()


# ---------------------------------------------------------------------------
# FailureRegistry (CRUD + queries)
# ---------------------------------------------------------------------------


class TestFailureRegistryCRUD:
    """Operaciones básicas del registry."""

    def test_record_returns_failure_record(self, registry: FailureRegistry) -> None:
        """record() retorna un FailureRecord con id y timestamp."""
        record = registry.record(
            task="test",
            failure_type="runtime",
            error_msg="err",
            root_cause="cause",
            resolution="fix",
        )
        assert isinstance(record, FailureRecord)
        assert record.id.startswith("2026")  # timestamp-based
        assert record.task == "test"

    def test_record_persists_to_disk(self, tmp_path: Path) -> None:
        """El registro se persiste en JSONL y sobrevive recarga."""
        path = tmp_path / "failures.jsonl"
        reg1 = FailureRegistry(path=path)
        reg1.record(
            task="persist test",
            failure_type="test",
            error_msg="err",
            root_cause="cause",
            resolution="fix",
        )
        # Recargar desde disco
        reg2 = FailureRegistry(path=path)
        assert len(reg2) == 1
        assert reg2._records[0].task == "persist test"

    def test_multiple_records_append(self, registry: FailureRegistry) -> None:
        """Múltiples registros se appenden (no sobreescriben)."""
        for i in range(5):
            registry.record(
                task=f"task-{i}",
                failure_type="runtime",
                error_msg=f"err-{i}",
                root_cause="cause",
                resolution="fix",
            )
        assert len(registry) == 5

    def test_string_coercion_failure_type(self, registry: FailureRegistry) -> None:
        """failure_type acepta string y lo convierte a enum."""
        record = registry.record(
            task="str type",
            failure_type="security",  # string, no FailureType.SECURITY
            error_msg="err",
            root_cause="cause",
            resolution="fix",
        )
        assert record.failure_type == FailureType.SECURITY

    def test_string_coercion_severity(self, registry: FailureRegistry) -> None:
        """severity acepta string y lo convierte a enum."""
        record = registry.record(
            task="str severity",
            failure_type="runtime",
            error_msg="err",
            root_cause="cause",
            resolution="fix",
            severity="critical",  # string
        )
        assert record.severity == Severity.CRITICAL


class TestFailureRegistryQueries:
    """Consultas y filtros del registry."""

    def test_get_recent_returns_n_most_recent(
        self, populated_registry: FailureRegistry
    ) -> None:
        """get_recent(n) retorna los N más recientes ordenados."""
        recent = populated_registry.get_recent(n=3)
        assert len(recent) == 3
        # Orden descendente por timestamp
        assert recent[0].timestamp >= recent[1].timestamp >= recent[2].timestamp

    def test_get_by_type_filters_correctly(
        self, populated_registry: FailureRegistry
    ) -> None:
        """get_by_type retorna solo fallos del tipo indicado."""
        runtime_failures = populated_registry.get_by_type("runtime")
        assert len(runtime_failures) == 2
        assert all(r.failure_type == FailureType.RUNTIME for r in runtime_failures)

    def test_get_by_severity_filters_correctly(
        self, populated_registry: FailureRegistry
    ) -> None:
        """get_by_severity retorna solo fallos de la severidad indicada."""
        high = populated_registry.get_by_severity("high")
        assert len(high) == 1
        assert high[0].severity == Severity.HIGH

    def test_get_unresolved_returns_pending(
        self, populated_registry: FailureRegistry
    ) -> None:
        """get_unresolved retorna fallos con resolution='pending'."""
        unresolved = populated_registry.get_unresolved()
        assert len(unresolved) == 1
        assert unresolved[0].resolution == "pending"

    def test_get_skills_derived_deduplicated(
        self, populated_registry: FailureRegistry
    ) -> None:
        """get_skills_derived retorna nombres únicos ordenados."""
        skills = populated_registry.get_skills_derived()
        assert isinstance(skills, list)
        assert len(skills) == 2  # config-fallback, symlink-fallback
        assert skills == sorted(skills)  # ordenados


class TestFailureRegistryStats:
    """Métricas y agregaciones."""

    def test_stats_returns_complete_dict(
        self, populated_registry: FailureRegistry
    ) -> None:
        """stats() retorna total, unresolved, by_type, by_severity, skills."""
        stats = populated_registry.stats()
        assert stats["total"] == 5
        assert stats["unresolved"] == 1
        assert "runtime" in stats["by_type"]
        assert stats["by_type"]["runtime"] == 2
        assert "medium" in stats["by_severity"]
        assert len(stats["skills_derived"]) == 2
        assert stats["latest"] is not None

    def test_stats_empty_registry(self, registry: FailureRegistry) -> None:
        """stats() funciona con registry vacío."""
        stats = registry.stats()
        assert stats["total"] == 0
        assert stats["unresolved"] == 0
        assert stats["latest"] is None

    def test_len(self, populated_registry: FailureRegistry) -> None:
        """len() retorna el número total de registros."""
        assert len(populated_registry) == 5

    def test_repr(self, populated_registry: FailureRegistry) -> None:
        """repr() muestra count y path."""
        r = repr(populated_registry)
        assert "5 records" in r


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    """Casos extremos y robustez."""

    def test_corrupt_jsonl_handled_gracefully(self, tmp_path: Path) -> None:
        """JSONL corrupto se ignora sin crashear."""
        path = tmp_path / "failures.jsonl"
        path.write_text("not json\n{\"valid\": true}\nalso bad\n", encoding="utf-8")
        registry = FailureRegistry(path=path)
        # Solo el registro válido se carga
        assert len(registry) == 0  # {"valid": true} no tiene campos requeridos

    def test_missing_file_creates_empty_registry(self, tmp_path: Path) -> None:
        """Archivo inexistente crea registry vacío (idempotente)."""
        registry = FailureRegistry(path=tmp_path / "nonexistent.jsonl")
        assert len(registry) == 0

    def test_tags_as_list_coerced_to_tuple(self, registry: FailureRegistry) -> None:
        """Tags como lista se convierten a tuple (inmutabilidad)."""
        record = registry.record(
            task="list tags",
            failure_type="runtime",
            error_msg="err",
            root_cause="cause",
            resolution="fix",
            tags=["tag1", "tag2"],  # list, no tuple
        )
        assert record.tags == ("tag1", "tag2")
        assert isinstance(record.tags, tuple)
