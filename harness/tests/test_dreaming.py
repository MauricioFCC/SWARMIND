"""Tests para DreamingConsolidator — Dreaming-lite (ADR-0034, Idea 3).

Cubre: dedup por Jaccard, stale removal, compactación por densidad,
copy-on-write (inmutabilidad del origen), idempotencia y consolidación de dir.
"""

import json

import pytest

from harness.memory_rag.dreaming import (
    ConsolidationResult,
    DreamingConsolidator,
    jaccard_similarity,
)


def _entry(key, content, refs=0, age_days=10, ts=None):
    """Helper para construir entradas de memoria con forma de dict."""
    return {
        "key": key,
        "content": content,
        "reference_count": refs,
        "age_days": age_days,
        "updated_at": ts or "2026-07-01T00:00:00Z",
    }


class TestJaccard:
    """Similitud de Jaccard entre contenidos."""

    def test_identical_text(self):
        assert jaccard_similarity("a b c", "a b c") == pytest.approx(1.0)

    def test_disjoint_text(self):
        assert jaccard_similarity("a b c", "d e f") == pytest.approx(0.0)

    def test_partial_overlap(self):
        # {a,b,c} ∩ {b,c,d} = {b,c} ; union = {a,b,c,d} -> 2/4 = 0.5
        assert jaccard_similarity("a b c", "b c d") == pytest.approx(0.5)

    def test_empty(self):
        assert jaccard_similarity("", "") == pytest.approx(0.0)


class TestDedup:
    """Fusión de entradas semánticamente similares."""

    def test_dedups_near_duplicates(self):
        d = DreamingConsolidator(similarity_threshold=0.7)
        entries = [
            _entry("k1", "la API usa autenticacion jwt para usuarios"),
            _entry("k2", "la API usa autenticacion jwt para usuarios registrados"),
            _entry("k3", "el despliegue usa docker compose en produccion"),
        ]
        result = d.consolidate(entries)
        assert result.removed == 1
        assert len(result.entries) == 2

    def test_keeps_most_recent_on_dedup(self):
        d = DreamingConsolidator(similarity_threshold=0.6)
        entries = [
            _entry("vieja", "el servicio expone el puerto 8080", ts="2026-06-01"),
            _entry("nueva", "el servicio expone el puerto 8080 y usa TLS",
                   ts="2026-07-01"),
        ]
        result = d.consolidate(entries)
        assert len(result.entries) == 1
        assert result.entries[0]["key"] == "nueva"


class TestStaleRemoval:
    """Eliminación de entradas viejas sin referencias."""

    def test_removes_old_unreferenced(self):
        d = DreamingConsolidator(max_age_days=30)
        entries = [
            _entry("vieja", "nota vieja sin uso", refs=0, age_days=120),
            _entry("usada", "nota con referencias", refs=5, age_days=120),
            _entry("reciente", "nota reciente", refs=0, age_days=5),
        ]
        result = d.consolidate(entries)
        keys = {e["key"] for e in result.entries}
        assert "vieja" not in keys
        assert "usada" in keys
        assert "reciente" in keys

    def test_referenced_old_is_kept(self):
        d = DreamingConsolidator(max_age_days=30)
        entries = [_entry("k", "contenido", refs=3, age_days=200)]
        result = d.consolidate(entries)
        assert len(result.entries) == 1


class TestCompaction:
    """Compacción por densidad: entradas largas se resumen."""

    def test_compacts_verbose_entries(self):
        d = DreamingConsolidator(min_density_chars=200)
        long_content = " ".join(["palabra"] * 500)
        entries = [_entry("k1", long_content, refs=2, age_days=5)]
        result = d.consolidate(entries)
        assert len(result.entries) == 1
        assert len(result.entries[0]["content"]) < len(long_content)
        assert result.compacted == 1

    def test_keeps_short_entries(self):
        d = DreamingConsolidator(min_density_chars=200)
        entries = [_entry("k1", "nota corta y densa", refs=2, age_days=5)]
        result = d.consolidate(entries)
        assert result.compacted == 0
        assert result.entries[0]["content"] == "nota corta y densa"


class TestPurity:
    """Copy-on-write e idempotencia."""

    def test_input_not_mutated(self):
        d = DreamingConsolidator()
        entries = [_entry("k1", "contenido A"), _entry("k2", "contenido B")]
        original = [dict(e) for e in entries]
        d.consolidate(entries)
        assert entries == original

    def test_idempotent(self):
        d = DreamingConsolidator()
        entries = [_entry("k1", "contenido A"), _entry("k2", "contenido B")]
        r1 = d.consolidate(entries)
        r2 = d.consolidate(entries)
        assert r1.entries == r2.entries
        assert r1.removed == r2.removed


class TestDirConsolidation:
    """Consolidación de directorios (sessions -> knowledge)."""

    def test_consolidate_dir_writes_dest(self, tmp_path):
        source = tmp_path / "sessions"
        dest = tmp_path / "knowledge"
        source.mkdir()
        (source / "s1.json").write_text(
            json.dumps({"key": "a", "content": "misma idea repetida", "age_days": 1}),
            encoding="utf-8",
        )
        (source / "s2.json").write_text(
            json.dumps({"key": "b", "content": "misma idea repetida", "age_days": 1}),
            encoding="utf-8",
        )
        d = DreamingConsolidator(similarity_threshold=0.9)
        result = d.consolidate_dir(str(source), str(dest))
        assert result.source_entries == 2
        assert dest.exists()
        files = list(dest.glob("*.json"))
        assert len(files) == len(result.entries)

    def test_consolidate_dir_keeps_source_intact(self, tmp_path):
        source = tmp_path / "sessions"
        source.mkdir()
        (source / "s1.json").write_text(
            json.dumps({"key": "a", "content": "contenido", "age_days": 1}),
            encoding="utf-8",
        )
        d = DreamingConsolidator()
        d.consolidate_dir(str(source), str(tmp_path / "out"))
        assert (source / "s1.json").exists()

    def test_consolidate_dir_missing_source(self, tmp_path):
        d = DreamingConsolidator()
        with pytest.raises(FileNotFoundError):
            d.consolidate_dir(str(tmp_path / "nope"), str(tmp_path / "out"))


class TestResult:
    """Estructura del resultado."""

    def test_result_counts(self):
        d = DreamingConsolidator(similarity_threshold=0.9)
        entries = [
            _entry("k1", "a b c d e"),
            _entry("k2", "a b c d e f g"),
            _entry("k3", "x y z"),
        ]
        result = d.consolidate(entries)
        assert isinstance(result, ConsolidationResult)
        assert result.source_entries == 3
        assert result.removed == result.source_entries - len(result.entries)
        assert result.compacted >= 0
