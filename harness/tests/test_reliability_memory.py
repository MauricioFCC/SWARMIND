"""Tests de ReliabilityMemory (Sigma-Mem, ADR-0039 #6).

Cobertura obligatoria: cold-start, suavizado Laplace, ranking de agentes,
persistencia (tmp_path) y escritura atomica. Extras: estado corrupto,
fallo de escritura no fatal y escritura solo bajo mutacion.
"""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from harness.memory_rag.reliability_memory import ReliabilityMemory


@pytest.fixture
def mem(tmp_path: Path) -> ReliabilityMemory:
    """Instancia aislada con persistencia en tmp_path (nunca toca data/ real)."""
    return ReliabilityMemory(path=tmp_path / "reliability_memory.json")


class TestColdStart:
    """Comportamiento sin evidencia registrada."""

    def test_unknown_agent_reliability_is_neutral(self, mem: ReliabilityMemory) -> None:
        """Sin datos el score es 0.5 (Laplace cold-start neutro)."""
        assert mem.get_reliability("agente_inexistente") == 0.5

    def test_unknown_agent_per_task_type_is_neutral(self, mem: ReliabilityMemory) -> None:
        """Cold-start tambien por tipo de tarea."""
        assert mem.get_reliability("ghost", task_type="code_gen") == 0.5

    def test_ranked_agents_empty(self, mem: ReliabilityMemory) -> None:
        """Sin agentes el ranking es vacio."""
        assert mem.get_ranked_agents() == []

    def test_stats_empty_state(self, mem: ReliabilityMemory) -> None:
        """Stats de estado vacio: 0 agentes, 0 eventos, version del storage."""
        stats = mem.get_stats()
        assert stats["agents"] == 0
        assert stats["events"] == 0
        assert stats["version"] == 1

    def test_missing_file_yields_empty_state_no_error(self, tmp_path: Path) -> None:
        """Archivo inexistente -> estado vacio sin excepcion ni archivo creado."""
        path = tmp_path / "nunca_existe.json"
        instance = ReliabilityMemory(path=path)
        assert instance.get_stats()["agents"] == 0
        assert not path.exists()


class TestLaplaceSmoothing:
    """Formula (successes + 1) / (total + 2)."""

    def test_one_success(self, mem: ReliabilityMemory) -> None:
        """1 exito / 1 evento -> 2/3."""
        mem.record_outcome("builder", "code_gen", success=True)
        assert mem.get_reliability("builder") == pytest.approx(2 / 3)

    def test_mixed_outcomes(self, mem: ReliabilityMemory) -> None:
        """3 exitos + 1 fallo -> 4/6."""
        for _ in range(3):
            mem.record_outcome("builder", "code_gen", success=True)
        mem.record_outcome("builder", "code_gen", success=False)
        assert mem.get_reliability("builder") == pytest.approx(4 / 6)

    def test_poor_performer(self, mem: ReliabilityMemory) -> None:
        """9 exitos + 10 fallos -> 10/21 (~0.476)."""
        for _ in range(9):
            mem.record_outcome("worker", "docs", success=True)
        for _ in range(10):
            mem.record_outcome("worker", "docs", success=False)
        assert mem.get_reliability("worker") == pytest.approx(10 / 21)

    def test_per_task_type_isolation(self, mem: ReliabilityMemory) -> None:
        """La confiabilidad por tarea no mezcla evidencia de otras tareas."""
        mem.record_outcome("builder", "code_gen", success=True)
        for _ in range(4):
            mem.record_outcome("builder", "docs", success=False)
        assert mem.get_reliability("builder", task_type="code_gen") == pytest.approx(2 / 3)
        assert mem.get_reliability("builder", task_type="docs") == pytest.approx(1 / 6)
        assert mem.get_reliability("builder") == pytest.approx(2 / 7)


class TestRankedAgents:
    """Ordenamiento descendente por score, determinista."""

    def _seed(self, mem: ReliabilityMemory) -> None:
        """Agente alfa 5/0, beta 1/0, gamma 0/5 (solo gamma falla)."""
        for _ in range(5):
            mem.record_outcome("alfa", "code_gen", success=True)
        mem.record_outcome("beta", "code_gen", success=True)
        for _ in range(5):
            mem.record_outcome("gamma", "code_gen", success=False)

    def test_ranked_order_desc(self, mem: ReliabilityMemory) -> None:
        """alfa (6/7) > beta (2/3) > gamma (1/7)."""
        self._seed(mem)
        ranked = mem.get_ranked_agents()
        assert [name for name, _ in ranked] == ["alfa", "beta", "gamma"]
        assert ranked[0][1] == pytest.approx(6 / 7)
        assert ranked[2][1] == pytest.approx(1 / 7)

    def test_ranked_by_task_type(self, mem: ReliabilityMemory) -> None:
        """El filtro por tarea solo usa evidencia de esa tarea."""
        for _ in range(5):
            mem.record_outcome("alfa", "code_gen", success=True)
        for _ in range(5):
            mem.record_outcome("alfa", "docs", success=False)
        mem.record_outcome("beta", "code_gen", success=True)
        ranked = mem.get_ranked_agents(task_type="code_gen")
        assert [name for name, _ in ranked] == ["alfa", "beta"]
        ranked_docs = mem.get_ranked_agents(task_type="docs")
        # beta sin evidencia en docs puntua cold-start 0.5 > alfa (1/7 en docs).
        assert [name for name, _ in ranked_docs] == ["beta", "alfa"]

    def test_tie_broken_by_name(self, mem: ReliabilityMemory) -> None:
        """Empate exacto -> orden alfabetico (estable)."""
        mem.record_outcome("zeta", "t", success=True)
        mem.record_outcome("alfa", "t", success=True)
        assert [name for name, _ in mem.get_ranked_agents()] == ["alfa", "zeta"]


class TestPersistence:
    """Roundtrip JSON + escritura atomica."""

    def test_roundtrip_reload(self, tmp_path: Path) -> None:
        """Nueva instancia sobre el mismo path recupera toda la evidencia."""
        path = tmp_path / "mem.json"
        first = ReliabilityMemory(path=path)
        first.record_outcome("builder", "code_gen", success=True, meta={"ms": 1200})
        first.record_outcome("builder", "code_gen", success=True)
        first.record_outcome("builder", "docs", success=False)
        second = ReliabilityMemory(path=path)
        # Agregado: 2 exitos + 1 fallo -> Laplace (2+1)/(3+2) = 0.6
        assert second.get_reliability("builder") == pytest.approx(3 / 5)
        assert second.get_reliability("builder", task_type="docs") == pytest.approx(1 / 3)
        assert second.get_stats()["agents"] == 1

    def test_file_is_valid_json_with_version(self, tmp_path: Path) -> None:
        """El archivo persistido es JSON valido y versionado."""
        path = tmp_path / "mem.json"
        instance = ReliabilityMemory(path=path)
        instance.record_outcome("a", "t", success=True)
        payload = json.loads(path.read_text(encoding="utf-8"))
        assert payload["version"] == 1
        assert payload["agents"]["a"]["successes"]["t"] == 1

    def test_meta_preserved_in_events(self, tmp_path: Path) -> None:
        """El meta del outcome sobrevive la persistencia (provenance)."""
        path = tmp_path / "mem.json"
        instance = ReliabilityMemory(path=path)
        instance.record_outcome("a", "t", success=True, meta={"agent": "a", "ms": 42})
        reloaded = ReliabilityMemory(path=path)
        stats = reloaded.get_stats()
        assert stats["per_agent"]["a"]["successes"] == 1
        assert reloaded.get_stats()["events"] == 1

    def test_no_tmp_leftovers_after_save(self, tmp_path: Path) -> None:
        """Tras guardar no quedan archivos .tmp (escritura atomica limpia)."""
        path = tmp_path / "mem.json"
        instance = ReliabilityMemory(path=path)
        for _ in range(3):
            instance.record_outcome("a", "t", success=True)
        assert not list(tmp_path.glob("*.tmp"))
        assert path.exists()

    def test_atomic_write_uses_os_replace(self, tmp_path: Path) -> None:
        """Cada mutacion escribe via os.replace (reemplazo atomico)."""
        path = tmp_path / "mem.json"
        instance = ReliabilityMemory(path=path)
        with patch(
            "harness.memory_rag.reliability_memory.os.replace",
            wraps=__import__("os").replace,
        ) as mock_replace:
            instance.record_outcome("a", "t", success=True)
            instance.record_outcome("a", "t", success=False)
            # Lecturas puras NO mutan el estado -> no escriben.
            instance.get_reliability("a")
            instance.get_ranked_agents()
            instance.get_stats()
            assert mock_replace.call_count == 2

    def test_clear_persists_empty_state(self, tmp_path: Path) -> None:
        """clear() borra evidencia y deja el archivo con estado vacio."""
        path = tmp_path / "mem.json"
        instance = ReliabilityMemory(path=path)
        instance.record_outcome("a", "t", success=True)
        instance.clear()
        assert instance.get_stats()["agents"] == 0
        payload = json.loads(path.read_text(encoding="utf-8"))
        assert payload["agents"] == {}


class TestHardening:
    """Errores de archivo y argumentos no deben crashear el flujo principal."""

    def test_corrupt_file_warns_and_starts_empty(self, tmp_path: Path, caplog) -> None:
        """JSON corrupto -> warning con WHAT/WHY/WHERE y estado vacio."""
        path = tmp_path / "mem.json"
        path.write_text("{esto no es json", encoding="utf-8")
        instance = ReliabilityMemory(path=path)
        assert instance.get_stats()["agents"] == 0
        assert any("WHAT=carga_fallida" in rec.message for rec in caplog.records)

    def test_write_failure_logs_warning_but_keeps_ram(self, tmp_path: Path, caplog) -> None:
        """OSError al guardar -> warning (no crash) y la memoria sigue en RAM."""
        path = tmp_path / "mem.json"
        instance = ReliabilityMemory(path=path)
        with patch(
            "harness.memory_rag.reliability_memory.os.replace",
            side_effect=OSError("disco lleno"),
        ):
            instance.record_outcome("a", "t", success=True)  # No debe lanzar.
        assert instance.get_reliability("a") == pytest.approx(2 / 3)
        warnings = [rec for rec in caplog.records if rec.levelname == "WARNING"]
        assert any("WHAT=escritura_fallida" in rec.message for rec in warnings)

    def test_invalid_arguments_raise(self, mem: ReliabilityMemory) -> None:
        """Agent/task vacios o success no-bool -> ValueError/TypeError."""
        with pytest.raises(ValueError, match="WHAT=argumento_invalido"):
            mem.record_outcome("", "t", success=True)
        with pytest.raises(ValueError, match="WHAT=argumento_invalido"):
            mem.record_outcome("a", "", success=True)
        with pytest.raises(TypeError, match="WHAT=argumento_invalido"):
            mem.record_outcome("a", "t", success=1)  # type: ignore[arg-type]
        with pytest.raises(ValueError, match="WHAT=argumento_invalido"):
            mem.get_reliability("   ")

    def test_relative_path_resolves_to_repo_data(self) -> None:
        """Path relativo -> se resuelve contra la raiz del repositorio."""
        instance = ReliabilityMemory(path="data/reliability_memory.json")
        assert str(instance._path).replace("\\", "/").endswith("data/reliability_memory.json")
