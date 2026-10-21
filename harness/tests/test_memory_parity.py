"""Tests del health-check de paridad de memoria (Item 4 — memoria-optimality).

Cubre los contratos 11-15 de docs/specs/memory-optimality.md:
  - audit_parity() con caches grandes vs colecciones de valor vacias
  - is_imbalanced con umbral documentado (cache > 4x valor + >=3 vacias)
  - degradacion suave si el path no existe (no lanza)
"""

from __future__ import annotations

from pathlib import Path

from harness.memory_rag.memory_parity import ParityReport, audit_parity


def _mk_collection(root: Path, name: str, data_files: int, bytes_each: int) -> None:
    """Crea una coleccion .lance simulada con N fragments de datos.

    Args:
        root: Directorio raiz de la base (db_path).
        name: Nombre de la coleccion (sin sufijo .lance).
        data_files: Numero de fragments en el subdir data/.
        bytes_each: Tamano de cada fragment.
    """
    data_dir = root / f"{name}.lance" / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    for i in range(data_files):
        (data_dir / f"frag-{i:04d}.lance").write_bytes(b"x" * bytes_each)


class TestAuditParity:
    def test_returns_report_dataclass(self, tmp_path: Path) -> None:
        """audit_parity devuelve un ParityReport con los 4 campos."""
        report = audit_parity(tmp_path)
        assert isinstance(report, ParityReport)
        assert report.cache_bytes == 0
        assert report.value_bytes == 0
        assert report.value_collections_empty == ()
        assert report.is_imbalanced is False

    def test_balanced_when_value_dominates(self, tmp_path: Path) -> None:
        """Valor grande y caches pequeñas => no imbalance."""
        _mk_collection(tmp_path, "semantic_cache", 1, 100)       # cache
        _mk_collection(tmp_path, "procedural_skills", 5, 100000)  # valor poblado
        _mk_collection(tmp_path, "skill_effectiveness", 5, 100000)
        report = audit_parity(tmp_path)
        assert report.is_imbalanced is False
        assert report.value_collections_empty == ()

    def test_imbalanced_when_cache_dominates_and_value_empty(self, tmp_path: Path) -> None:
        """Cache >> valor Y >=3 colecciones de valor vacias => imbalance."""
        # Cache grande
        _mk_collection(tmp_path, "semantic_cache", 1, 500_000)
        _mk_collection(tmp_path, "agent_workspace_logs", 1, 200_000)
        # 3+ colecciones de valor VACIAS (solo schema: <=2 fragments)
        _mk_collection(tmp_path, "procedural_skills", 1, 100)
        _mk_collection(tmp_path, "skill_effectiveness", 1, 100)
        _mk_collection(tmp_path, "agent_performance", 1, 100)
        _mk_collection(tmp_path, "session_kpis", 1, 100)
        report = audit_parity(tmp_path)
        assert report.is_imbalanced is True
        assert "procedural_skills" in report.value_collections_empty
        assert report.cache_bytes > 4 * report.value_bytes

    def test_not_imbalanced_if_few_empty_collections(self, tmp_path: Path) -> None:
        """Cache domina pero <3 colecciones de valor vacias => no imbalance."""
        _mk_collection(tmp_path, "semantic_cache", 1, 500_000)
        _mk_collection(tmp_path, "procedural_skills", 5, 100)
        _mk_collection(tmp_path, "skill_effectiveness", 5, 100)
        _mk_collection(tmp_path, "agent_performance", 5, 100)
        report = audit_parity(tmp_path)
        assert report.is_imbalanced is False

    def test_missing_path_degrades_to_empty_report(self, tmp_path: Path) -> None:
        """Path inexistente => report vacio, NO lanza (contrato 13)."""
        report = audit_parity(tmp_path / "no_existe")
        assert report.cache_bytes == 0
        assert report.value_bytes == 0
        assert report.is_imbalanced is False

    def test_volatile_collections_counted_as_cache(self, tmp_path: Path) -> None:
        """Las 2 colecciones volatiles cuentan como cache, no como valor."""
        _mk_collection(tmp_path, "semantic_cache", 1, 1000)
        _mk_collection(tmp_path, "agent_workspace_logs", 1, 1000)
        report = audit_parity(tmp_path)
        assert report.cache_bytes == 2000
        assert report.value_bytes == 0
