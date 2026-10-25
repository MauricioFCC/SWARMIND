"""Contratos del bootstrap de memoria colectiva (ciclo 11.20 — spec memory-lifecycle).

WHAT: verifica ``harness/memory_rag/memory_bootstrap.py``:

- primera instalación crea la memoria colectiva (data/lancedb + backups +
  .swarmind_config.json) de forma idempotente y cross-platform;
- detecta forks locales del proyecto (harness/db/lancedb) y migra solo
  tablas de valor (append por filas si la local es más nueva);
- NUNCA migra colecciones volátiles (semantic_cache, agent_workspace_logs
  son regenerables — doctrina backup_memory.py);
- prune elimina colecciones volátiles que exceden el cap (1 GB).

WHY: sin .swarmind_config.json el harness cae al fallback legacy y creó un
fork de 4.8 GB en harness/db/lancedb; spec specs/memory-lifecycle.md.

WHERE: ``harness/memory_rag/memory_bootstrap.py``.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

try:
    import lancedb
    _LANCEDB_AVAILABLE = True
except ImportError:
    _LANCEDB_AVAILABLE = False

import pytest

pytestmark = pytest.mark.skipif(not _LANCEDB_AVAILABLE, reason="lancedb not installed")

from harness.memory_rag.memory_bootstrap import (
    VOLATILE_COLLECTIONS,
    VOLATILE_MAX_BYTES,
    BootstrapReport,
    bootstrap_memory,
    default_memory_root,
    detect_project_local_memory,
    migrate_local_to_central,
    prune_volatile_collections,
)


def _mk_table(db_dir: Path, name: str, rows: int = 3) -> None:
    """Crea una tabla .lance determinista con ``rows`` filas."""
    db = lancedb.connect(str(db_dir))
    data = [{"id": i, "text": f"row-{i}"} for i in range(rows)]
    db.create_table(name, data=data)


class TestDefaultMemoryRoot:
    """Raiz colectiva: MEMORY_ROOT env > ~/Documents/Memory_Proyects."""

    def test_respeta_memory_root_env(self, tmp_path: Path, monkeypatch) -> None:
        monkeypatch.setenv("MEMORY_ROOT", str(tmp_path / "custom"))

        assert default_memory_root() == tmp_path / "custom"

    def test_default_documents_cross_platform(self, monkeypatch, tmp_path: Path) -> None:
        monkeypatch.delenv("MEMORY_ROOT", raising=False)
        monkeypatch.setenv("HOME", str(tmp_path))
        monkeypatch.setenv("USERPROFILE", str(tmp_path))

        root = default_memory_root()

        assert root == tmp_path / "Documents" / "Memory_Proyects"


class TestBootstrapMemory:
    """Primera instalación: crea estructura + config SSOT."""

    def test_crea_estructura_y_config(self, tmp_path: Path) -> None:
        report = bootstrap_memory(tmp_path / "mem")

        assert isinstance(report, BootstrapReport)
        assert report.data_dir.is_dir()
        assert report.backups_dir.is_dir()
        assert report.config_file.is_file()
        assert report.created is True

    def test_config_es_readable_por_memory_config(self, tmp_path: Path) -> None:
        report = bootstrap_memory(tmp_path / "mem")

        data = json.loads(report.config_file.read_text(encoding="utf-8"))

        assert data["memory_root"] == str(tmp_path / "mem")
        assert "backup_keep" in data, "shape mergeable con backup_memory._DEFAULTS"

    def test_idempotente(self, tmp_path: Path) -> None:
        root = tmp_path / "mem"
        bootstrap_memory(root)

        second = bootstrap_memory(root)

        assert second.created is False, "segunda ejecución no recrea config"


class TestDetectLocalFork:
    """Detección de memoria local del proyecto (cualquier SO)."""

    def test_detecta_tablas_lance(self, tmp_path: Path) -> None:
        project = tmp_path / "proj"
        _mk_table(project / "harness" / "db" / "lancedb", "rag_chunks", rows=2)

        fork = detect_project_local_memory(project)

        assert fork is not None
        assert "rag_chunks" in fork.tables

    def test_none_sin_fork(self, tmp_path: Path) -> None:
        assert detect_project_local_memory(tmp_path / "empty") is None

    def test_none_si_solo_hay_archivos_sueltos(self, tmp_path: Path) -> None:
        project = tmp_path / "proj"
        db_dir = project / "harness" / "db" / "lancedb"
        db_dir.mkdir(parents=True)
        (db_dir / "not_a_table.txt").write_text("x", encoding="utf-8")

        assert detect_project_local_memory(project) is None


class TestMigrateLocalToCentral:
    """Fusión por tablas: append de valor, skip de volátiles/stale."""

    def test_copia_tabla_ausente_en_central(self, tmp_path: Path) -> None:
        local = tmp_path / "local"
        central = tmp_path / "central"
        _mk_table(local, "procedural_skills", rows=4)
        lancedb.connect(str(central))

        report = migrate_local_to_central(local, central)

        assert report.copied == ("procedural_skills",)
        central_db = lancedb.connect(str(central))
        assert central_db.open_table("procedural_skills").count_rows() == 4

    def test_append_tabla_no_volatil_mas_nueva(self, tmp_path: Path) -> None:
        local = tmp_path / "local"
        central = tmp_path / "central"
        _mk_table(local, "session_kpis", rows=3)
        _mk_table(central, "session_kpis", rows=2)

        report = migrate_local_to_central(local, central, force_newer=True)

        assert report.appended == ("session_kpis",)
        db = lancedb.connect(str(central))
        assert db.open_table("session_kpis").count_rows() == 5, "append = 2 + 3"

    def test_nunca_migra_volatiles(self, tmp_path: Path) -> None:
        local = tmp_path / "local"
        central = tmp_path / "central"
        for name in sorted(VOLATILE_COLLECTIONS):
            _mk_table(local, name, rows=2)
        lancedb.connect(str(central))

        report = migrate_local_to_central(local, central)

        assert report.skipped_volatile == tuple(sorted(VOLATILE_COLLECTIONS))
        assert not report.copied and not report.appended

    def test_tabla_mas_vieja_no_se_toca(self, tmp_path: Path) -> None:
        local = tmp_path / "local"
        central = tmp_path / "central"
        _mk_table(local, "iteration_reports", rows=1)
        _mk_table(central, "iteration_reports", rows=5)

        report = migrate_local_to_central(local, central, force_newer=False)

        assert report.skipped_stale == ("iteration_reports",)
        db = lancedb.connect(str(central))
        assert db.open_table("iteration_reports").count_rows() == 5

    def test_comparacion_mtime_real(self, tmp_path: Path) -> None:
        """Sin force_newer, usa mtimes reales: local más viejo => stale."""
        local = tmp_path / "local"
        central = tmp_path / "central"
        _mk_table(local, "iteration_reports", rows=1)
        _mk_table(central, "iteration_reports", rows=5)

        # local mtime = antiguo (epoch 1000), central = reciente
        os.utime(local / "iteration_reports.lance", (1000, 1000))
        os.utime(central / "iteration_reports.lance", (9_999_999_999, 9_999_999_999))

        report = migrate_local_to_central(local, central)

        assert report.skipped_stale == ("iteration_reports",)
        assert lancedb.connect(str(central)).open_table(
            "iteration_reports"
        ).count_rows() == 5


class TestPruneVolatile:
    """Topes duros: caches regenerables > cap se eliminan y regeneran."""

    def test_respeta_coleccion_bajo_cap(self, tmp_path: Path) -> None:
        central = tmp_path / "central"
        _mk_table(central, "semantic_cache", rows=2)

        removed = prune_volatile_collections(central)

        assert removed == []
        assert lancedb.connect(str(central)).list_tables().tables == ["semantic_cache"]

    def test_elimina_coleccion_sobre_cap(self, tmp_path: Path) -> None:
        central = tmp_path / "central"
        _mk_table(central, "semantic_cache", rows=2)

        removed = prune_volatile_collections(central, max_bytes=0)

        assert removed == ["semantic_cache"]
        assert lancedb.connect(str(central)).list_tables().tables == []

    def test_nunca_toca_tablas_de_valor(self, tmp_path: Path) -> None:
        central = tmp_path / "central"
        _mk_table(central, "rag_chunks", rows=2)

        removed = prune_volatile_collections(central, max_bytes=0)

        assert removed == []
        assert lancedb.connect(str(central)).list_tables().tables == ["rag_chunks"]


class TestCapConstante:
    """La política de cap es la del spec (256 MiB por colección volátil).

    Bajado de 1 GiB en el Item 3 (docs/specs/memory-optimality.md): la cache
    regenerable no debe dominar el SSOT (semantic_cache=138MB vs 0.3MB de
    conocimiento de valor).
    """

    def test_cap_es_256mib(self) -> None:
        assert VOLATILE_MAX_BYTES == 268_435_456
        assert VOLATILE_COLLECTIONS == frozenset(
            {"semantic_cache", "agent_workspace_logs"}
        )
