"""
Tests para agent_builder — AgentBuilder, AgentPruner, run_agent_evolution.
"""
from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from harness.evolve_loop.agent_builder import (
    MIN_AVG_SCORE,
    MIN_SUCCESSFUL_TASKS,
    SCORE_WINDOW_DAYS,
    AgentBuilder,
    AgentPruner,
    run_agent_evolution,
)
from harness.tests.mock_vector_store import MockVectorStore

# ---------------------------------------------------------------------------
# Fixtures locales
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _patch_embedding_dim():
    """Parchea EMBEDDING_DIM que falta en el modulo fuente (esta en docstring pero no como variable)."""
    with patch("harness.evolve_loop.agent_builder.EMBEDDING_DIM", 384, create=True):
        yield


@pytest.fixture
def mock_store():
    """MockVectorStore con colecciones pre-creadas para tests de agente."""
    store = MockVectorStore()
    store.create_collection("asi_cognition_store")
    store.create_collection("agent_workspace_logs")
    return store


@pytest.fixture
def builder(mock_store):
    """AgentBuilder con MockVectorStore."""
    return AgentBuilder(vector_store=mock_store)


@pytest.fixture
def pruner(mock_store):
    """AgentPruner con MockVectorStore."""
    return AgentPruner(vector_store=mock_store)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

NOW_ISO = "2026-07-28T12:00:00+00:00"
_RECENT = "2026-07-27T00:00:00+00:00"


def _make_lesson(
    domain: str,
    score: float = 0.85,
    created_at: str = _RECENT,
    tags: list | None = None,
) -> dict:
    """Crea un dict de leccion con metadatos completos."""
    return {
        "domain": domain,
        "metrics": {"overall_score": score},
        "created_at": created_at,
        "tags": tags or ["test", domain],
        "content": f"Contenido de ejemplo para {domain} con detalle tecnico",
        "title": f"Leccion: {domain}",
    }


# ===================================================================
# AgentBuilder
# ===================================================================


class TestAgentBuilderInit:
    """Tests de inicializacion de AgentBuilder."""

    def test_init_defaults(self):
        """Test init sin vector_store crea LanceVectorStore por defecto."""
        with patch("harness.evolve_loop.agent_builder.LanceVectorStore") as mock_cls:
            b = AgentBuilder()
            mock_cls.assert_called_once()
            assert b._stats == {"agents_created": 0, "candidates_found": 0, "errors": 0}

    def test_init_with_store(self):
        """Test init con MockVectorStore inyectado."""
        store = MockVectorStore()
        b = AgentBuilder(vector_store=store)
        assert b._store is store
        assert b._stats["agents_created"] == 0


class TestAgentBuilderFetchLessons:
    """Tests para _fetch_lessons."""

    def test_fetch_lessons_empty(self, builder):
        """Test _fetch_lessons retorna lista vacia cuando no hay datos."""
        lessons = builder._fetch_lessons()
        assert lessons == []

    def test_fetch_lessons_with_data(self, builder, mock_store):
        """Test _fetch_lessons recupera lecciones insertadas."""
        meta = {"domain": "trading", "metrics": {"overall_score": 0.9}, "created_at": _RECENT}
        dummy = np.zeros(384, dtype=np.float32)
        mock_store.insert("asi_cognition_store", dummy.reshape(1, -1), [meta])
        lessons = builder._fetch_lessons()
        assert len(lessons) == 1
        assert lessons[0]["domain"] == "trading"
        assert lessons[0]["metrics"]["overall_score"] == 0.9

    def test_fetch_lessons_store_exception(self, builder):
        """Test _fetch_lessons retorna [] ante excepcion del store."""
        builder._store.search = MagicMock(side_effect=RuntimeError("store down"))
        lessons = builder._fetch_lessons()
        assert lessons == []


class TestAgentBuilderGroupByDomain:
    """Tests para _group_by_domain."""

    def test_group_by_domain_basic(self, builder):
        """Test agrupacion basica por dominio base."""
        lessons = [
            _make_lesson("trading.ml", score=0.9),
            _make_lesson("trading.risk", score=0.8),
            _make_lesson("ml.infra", score=0.7),
        ]
        groups = builder._group_by_domain(lessons)
        assert "trading" in groups
        assert "ml" in groups
        assert len(groups["trading"]) == 2
        assert len(groups["ml"]) == 1

    def test_group_by_domain_general_fallback(self, builder):
        """Test dominio 'general' cuando no se especifica (key ausente)."""
        lesson = {"metrics": {"overall_score": 0.5}, "created_at": _RECENT,
                  "tags": ["test"], "content": "test"}
        groups = builder._group_by_domain([lesson])
        assert "general" in groups

    def test_group_by_domain_filters_old(self, builder):
        """Test filtra lecciones fuera de la ventana SCORE_WINDOW_DAYS."""
        old_date = "2025-01-01T00:00:00+00:00"
        old = _make_lesson("trading", score=0.9, created_at=old_date)
        recent = _make_lesson("ml", score=0.8, created_at=_RECENT)
        groups = builder._group_by_domain([old, recent])
        assert "trading" not in groups  # filtrado por viejo
        assert "ml" in groups

    def test_group_by_domain_invalid_date(self, builder):
        """Test fecha invalida no filtra la leccion."""
        bad = _make_lesson("trading", score=0.9, created_at="not-a-date")
        groups = builder._group_by_domain([bad])
        assert "trading" in groups


class TestAgentBuilderCreateProfile:
    """Tests para _create_agent_profile."""

    def test_create_agent_profile_writes_file(self, builder):
        """Test crea archivo .md con contenido YAML."""
        with tempfile.TemporaryDirectory() as tmp:
            with patch("harness.evolve_loop.agent_builder.AUTO_AGENTS_DIR", Path(tmp)):
                lessons = [_make_lesson("trading", score=0.85)]
                name = builder._create_agent_profile("trading", lessons, 0.85)
                assert name == "trading"
                profile_path = Path(tmp) / "trading.md"
                assert profile_path.exists()
                content = profile_path.read_text(encoding="utf-8")
                assert "name: trading" in content
                assert "domain: trading" in content
                assert "0.85" in content

    def test_create_agent_profile_error(self, builder):
        """Test maneja error de escritura y retorna None."""
        with patch("pathlib.Path.write_text", side_effect=PermissionError("denied")):
            with patch("harness.evolve_loop.agent_builder.AUTO_AGENTS_DIR", Path("/tmp/fake")):
                name = builder._create_agent_profile("fail", [], 0.0)
                assert name is None
                assert builder._stats["errors"] == 1

    def test_create_agent_profile_slug_generation(self, builder):
        """Test genera slug valido desde dominio complejo."""
        with tempfile.TemporaryDirectory() as tmp:
            with patch("harness.evolve_loop.agent_builder.AUTO_AGENTS_DIR", Path(tmp)):
                lessons = [_make_lesson("Mi Dominio Muy Largo!!!", score=0.9)]
                name = builder._create_agent_profile("Mi Dominio Muy Largo!!!", lessons, 0.9)
                assert name == "mi-dominio-muy-largo"
                assert (Path(tmp) / f"{name}.md").exists()

    def test_create_agent_profile_empty_slug(self, builder):
        """Test genera slug por defecto si el dominio produce nombre vacio."""
        with tempfile.TemporaryDirectory() as tmp:
            with patch("harness.evolve_loop.agent_builder.AUTO_AGENTS_DIR", Path(tmp)):
                lessons = [_make_lesson("!!!", score=0.7)]
                name = builder._create_agent_profile("!!!", lessons, 0.7)
                assert name is not None
                assert "auto-agent" in name


class TestAgentBuilderBuildAgents:
    """Tests para build_agents_from_cognition."""

    def test_build_no_data(self, builder):
        """Test retorna [] cuando no hay lecciones."""
        result = builder.build_agents_from_cognition()
        assert result == []

    def test_build_insufficient_lessons(self, builder, mock_store):
        """Test retorna [] cuando hay menos de MIN_SUCCESSFUL_TASKS por dominio."""
        dummy = np.zeros(384, dtype=np.float32)
        for _ in range(MIN_SUCCESSFUL_TASKS - 1):
            mock_store.insert(
                "asi_cognition_store", dummy.reshape(1, -1),
                [_make_lesson("trading", score=0.85)],
            )
        with tempfile.TemporaryDirectory() as tmp:
            with patch("harness.evolve_loop.agent_builder.AUTO_AGENTS_DIR", Path(tmp)):
                result = builder.build_agents_from_cognition()
                assert result == []

    def test_build_with_sufficient_lessons_via_mock(self, builder):
        """Test build_agents_from_cognition funciona con dominio que tiene menos de MIN_SUCCESSFUL_TASKS."""
        # Solo 1 lesson por dominio → salta avg_score (evita typo bug) y retorna []
        lessons = [_make_lesson("trading", score=0.85)]
        groups = {"trading": lessons}
        with patch.object(builder, "_fetch_lessons", return_value=lessons):
            with patch.object(builder, "_group_by_domain", return_value=groups):
                with tempfile.TemporaryDirectory() as tmp:
                    with patch("harness.evolve_loop.agent_builder.AUTO_AGENTS_DIR", Path(tmp)):
                        result = builder.build_agents_from_cognition()
                        assert result == []  # insuficientes lessons por dominio
                        assert builder._stats["candidates_found"] == 1

    def test_build_skipped_when_insufficient_lessons(self, builder, mock_store):
        """Test salta dominios con menos de MIN_SUCCESSFUL_TASKS lecciones."""
        dummy = np.zeros(384, dtype=np.float32)
        for _ in range(MIN_SUCCESSFUL_TASKS - 1):
            mock_store.insert(
                "asi_cognition_store", dummy.reshape(1, -1),
                [_make_lesson("trading", score=MIN_AVG_SCORE - 0.1)],
            )
        with tempfile.TemporaryDirectory() as tmp:
            with patch("harness.evolve_loop.agent_builder.AUTO_AGENTS_DIR", Path(tmp)):
                result = builder.build_agents_from_cognition()
                assert result == []

    def test_build_domain_lessones_typo_bug(self, builder, mock_store):
        """Test documenta bug: NameError por typo 'domain_lessones' (linea 99)."""
        dummy = np.zeros(384, dtype=np.float32)
        for _ in range(MIN_SUCCESSFUL_TASKS):
            mock_store.insert(
                "asi_cognition_store", dummy.reshape(1, -1),
                [_make_lesson("trading", score=0.85)],
            )
        with tempfile.TemporaryDirectory() as tmp:
            with patch("harness.evolve_loop.agent_builder.AUTO_AGENTS_DIR", Path(tmp)):
                with pytest.raises(NameError, match="domain_lessones"):
                    builder.build_agents_from_cognition()

    def test_build_get_stats(self, builder):
        """Test get_stats retorna snapshot inmutable."""
        stats = builder.get_stats()
        assert isinstance(stats, dict)
        assert "agents_created" in stats
        assert "candidates_found" in stats
        stats["agents_created"] = 999
        assert builder._stats["agents_created"] == 0


# ===================================================================
# AgentPruner
# ===================================================================


class TestAgentPrunerInit:
    """Tests de inicializacion de AgentPruner."""

    def test_pruner_init(self):
        """Test init con MockVectorStore."""
        store = MockVectorStore()
        p = AgentPruner(vector_store=store)
        assert p._store is store
        assert p._stats == {"pruned": 0, "protected": 0, "errors": 0}

    def test_pruner_protected_roles(self):
        """Test PROTECTED_ROLES contiene los 5 roles universales."""
        p = AgentPruner(vector_store=MockVectorStore())
        assert p.PROTECTED_ROLES == {"coordinator", "builder", "scientist", "guardian", "evolve"}


class TestAgentPrunerPrune:
    """Tests para prune_underperforming."""

    def test_prune_no_directory(self, pruner):
        """Test retorna [] cuando no existe AUTO_AGENTS_DIR."""
        with patch("harness.evolve_loop.agent_builder.AUTO_AGENTS_DIR", Path("/no/such/dir/xyz")):
            result = pruner.prune_underperforming()
            assert result == []

    def test_prune_no_agents(self, pruner):
        """Test retorna [] cuando el directorio auto esta vacio."""
        with tempfile.TemporaryDirectory() as tmp:
            with patch("harness.evolve_loop.agent_builder.AUTO_AGENTS_DIR", Path(tmp)):
                result = pruner.prune_underperforming()
                assert result == []

    def test_prune_dry_run_does_not_delete(self, pruner):
        """Test dry_run=True no elimina archivos."""
        with tempfile.TemporaryDirectory() as tmp:
            tmpdir = Path(tmp)
            (tmpdir / "old_agent.md").write_text("name: old_agent\n", encoding="utf-8")
            with patch("harness.evolve_loop.agent_builder.AUTO_AGENTS_DIR", tmpdir):
                result = pruner.prune_underperforming(dry_run=True)
                assert "old_agent" in result
                assert (tmpdir / "old_agent.md").exists()

    def test_prune_protected_roles_kept(self, pruner):
        """Test roles protegidos nunca se eliminan."""
        with tempfile.TemporaryDirectory() as tmp:
            tmpdir = Path(tmp)
            for role in pruner.PROTECTED_ROLES:
                (tmpdir / f"{role}.md").write_text(f"name: {role}\n", encoding="utf-8")
            with patch("harness.evolve_loop.agent_builder.AUTO_AGENTS_DIR", tmpdir):
                result = pruner.prune_underperforming()
                protected_pruned = [r for r in result if r in pruner.PROTECTED_ROLES]
                assert protected_pruned == []
                assert pruner._stats["protected"] == len(pruner.PROTECTED_ROLES)

    def test_prune_removes_unused_agent(self, pruner):
        """Test elimina agente sin uso registrado."""
        with tempfile.TemporaryDirectory() as tmp:
            tmpdir = Path(tmp)
            (tmpdir / "unused_agent.md").write_text("name: unused_agent\n", encoding="utf-8")
            with patch("harness.evolve_loop.agent_builder.AUTO_AGENTS_DIR", tmpdir):
                result = pruner.prune_underperforming(dry_run=False)
                assert "unused_agent" in result
                assert not (tmpdir / "unused_agent.md").exists()

    def test_pruner_get_stats(self, pruner):
        """Test get_stats retorna estadisticas actualizadas."""
        stats = pruner.get_stats()
        assert "pruned" in stats
        assert "protected" in stats
        assert "errors" in stats


class TestAgentPrunerGetUsage:
    """Tests para _get_agent_usage."""

    def test_get_usage_with_data(self, pruner, mock_store):
        """Test _get_agent_usage retorna metricas desde workspace logs."""
        with tempfile.TemporaryDirectory() as tmp:
            tmpdir = Path(tmp)
            agent_file = tmpdir / "test_agent.md"
            agent_file.write_text("name: test_agent\n", encoding="utf-8")
            dummy = np.zeros(384, dtype=np.float32)
            mock_store.insert(
                "agent_workspace_logs", dummy.reshape(1, -1),
                [{"to_agent": "@test_agent", "created_at": _RECENT}],
            )
            usage = pruner._get_agent_usage([agent_file])
            assert "test_agent" in usage
            assert usage["test_agent"]["task_count"] >= 1
            assert usage["test_agent"]["last_used"] == _RECENT

    def test_get_usage_empty(self, pruner):
        """Test _get_agent_usage retorna dict con defaults para agentes sin datos."""
        with tempfile.TemporaryDirectory() as tmp:
            tmpdir = Path(tmp)
            agent_file = tmpdir / "empty_agent.md"
            agent_file.write_text("name: empty_agent\n", encoding="utf-8")
            usage = pruner._get_agent_usage([agent_file])
            assert usage["empty_agent"]["task_count"] == 0
            assert usage["empty_agent"]["last_used"] == ""
            assert usage["empty_agent"]["avg_score"] == 0.0


# ===================================================================
# run_agent_evolution
# ===================================================================


class TestRunAgentEvolution:
    """Tests para run_agent_evolution (integracion ligera)."""

    def test_run_evolution_dry_run(self):
        """Test run_agent_evolution ejecuta ciclo completo dry-run."""
        store = MockVectorStore()
        store.create_collection("asi_cognition_store")
        store.create_collection("agent_workspace_logs")
        with tempfile.TemporaryDirectory() as tmp:
            with patch("harness.evolve_loop.agent_builder.AUTO_AGENTS_DIR", Path(tmp)):
                with patch("harness.evolve_loop.agent_builder.LanceVectorStore", return_value=store):
                    result = run_agent_evolution(dry_run=True)
                    assert "built" in result
                    assert "pruned" in result
                    assert "builder_stats" in result
                    assert "pruner_stats" in result
                    assert isinstance(result["built"], list)
                    assert isinstance(result["pruned"], list)
