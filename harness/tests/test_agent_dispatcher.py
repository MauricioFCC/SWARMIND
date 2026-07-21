"""
Tests para AgentDispatcher — skill-aware task routing.

Cubre: dispatch síncrono, búsqueda en YAML registry, búsqueda LanceDB,
lectura de skill .md, stats, dispatch_async y dispatch_batch.
"""

from __future__ import annotations

import asyncio
from typing import Any, Dict
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from harness.orchestrator.agent_dispatcher import (
    SIMILARITY_THRESHOLD,
    AgentDispatcher,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_vector_store():
    """Vector store simulado con search."""
    store = MagicMock()
    store.search.return_value = []
    return store


@pytest.fixture
def dispatcher(mock_vector_store):
    """AgentDispatcher con vector store mockeado."""
    return AgentDispatcher(vector_store=mock_vector_store)


@pytest.fixture
def sample_skill() -> Dict[str, Any]:
    """Skill de ejemplo."""
    return {
        "name": "test-skill",
        "path": "/fake/path/test-skill.md",
        "domain": "testing",
        "agent": "software-engineer",
        "trigger": "test",
        "content": "# Test Skill\n\nSome content.",
        "similarity": 0.85,
    }


# ---------------------------------------------------------------------------
# __init__
# ---------------------------------------------------------------------------


class TestInit:
    """Tests del constructor."""

    def test_default_vector_store(self):
        """Debe crear un dispatcher sin vector store si no se pasa."""
        d = AgentDispatcher()
        assert d._vector_store is None
        assert d._stats == {
            "total_dispatches": 0,
            "skill_matches": 0,
            "no_skill_matches": 0,
        }

    def test_with_vector_store(self, mock_vector_store):
        """Debe almacenar el vector store recibido."""
        d = AgentDispatcher(vector_store=mock_vector_store)
        assert d._vector_store is mock_vector_store


# ---------------------------------------------------------------------------
# find_skill_for_task
# ---------------------------------------------------------------------------


class TestFindSkillForTask:
    """Tests para find_skill_for_task."""

    def test_yaml_registry_match(self, dispatcher):
        """Debe retornar skill si hay match en YAML registry."""
        mock_skill = {"name": "my-skill", "path": "/fake/path/my-skill.md",
                      "domain": "dev", "agent": "se", "trigger": "code"}
        with patch.object(dispatcher.__class__, '_read_skill_md',
                          return_value="# My Skill") as mock_read:
            with patch("harness.orchestrator.agent_dispatcher.SkillGenerator.find_in_registry",
                       return_value=mock_skill):
                result = dispatcher.find_skill_for_task("implement a test")

        assert result is not None
        assert result["name"] == "my-skill"
        assert result["content"] == "# My Skill"
        assert result["similarity"] == 0.80
        mock_read.assert_called_once_with("/fake/path/my-skill.md")

    def test_yaml_registry_match_no_path(self, dispatcher):
        """Debe retornar skill con content vacio si no hay path."""
        mock_skill = {"name": "no-path-skill", "domain": "dev"}
        with patch("harness.orchestrator.agent_dispatcher.SkillGenerator.find_in_registry",
                   return_value=mock_skill):
            with patch.object(dispatcher, '_read_skill_md') as mock_read:
                result = dispatcher.find_skill_for_task("test")

        assert result is not None
        assert result["content"] == ""
        mock_read.assert_not_called()

    def test_lancedb_match(self, dispatcher, mock_vector_store, sample_skill):
        """Debe buscar en LanceDB si YAML no matchea."""
        with patch("harness.orchestrator.agent_dispatcher.SkillGenerator.find_in_registry",
                   return_value=None):
            with patch.object(dispatcher, '_search_lancedb_skills',
                              return_value=sample_skill):
                result = dispatcher.find_skill_for_task("build a rest api")

        assert result is sample_skill

    def test_lancedb_match_below_threshold(self, dispatcher, mock_vector_store):
        """Debe retornar None si el match de LanceDB está por debajo del threshold."""
        low_skill = {"name": "low", "similarity": SIMILARITY_THRESHOLD - 0.05}
        with patch("harness.orchestrator.agent_dispatcher.SkillGenerator.find_in_registry",
                   return_value=None):
            with patch.object(dispatcher, '_search_lancedb_skills',
                              return_value=low_skill):
                result = dispatcher.find_skill_for_task("hello")

        assert result is None

    def test_no_match(self, dispatcher, mock_vector_store):
        """Debe retornar None si no hay match en ninguna fuente."""
        with patch("harness.orchestrator.agent_dispatcher.SkillGenerator.find_in_registry",
                   return_value=None):
            with patch.object(dispatcher, '_search_lancedb_skills',
                              return_value=None):
                result = dispatcher.find_skill_for_task("something obscure")

        assert result is None

    def test_no_vector_store_skip_lancedb(self, dispatcher):
        """Debe saltar LanceDB si no hay vector store."""
        d = AgentDispatcher()
        with patch("harness.orchestrator.agent_dispatcher.SkillGenerator.find_in_registry",
                   return_value=None):
            with patch.object(d, '_search_lancedb_skills') as mock_search:
                result = d.find_skill_for_task("test")

        assert result is None
        mock_search.assert_not_called()


# ---------------------------------------------------------------------------
# dispatch
# ---------------------------------------------------------------------------


class TestDispatch:
    """Tests para dispatch síncrono."""

    def test_dispatch_with_skill(self, dispatcher, sample_skill):
        """Debe incluir skill context cuando hay match."""
        with patch.object(dispatcher, 'find_skill_for_task',
                          return_value=sample_skill):
            result = dispatcher.dispatch("software-engineer", "build a test")

        assert result["agent"] == "software-engineer"
        assert result["task"] == "build a test"
        assert result["used_skill"] is True
        assert result["skill_context"] == "# Test Skill\n\nSome content."
        assert result["reasoning_mode"] == "guided_by_skill"
        assert result["skill_name"] == "test-skill"
        assert dispatcher._stats["total_dispatches"] == 1
        assert dispatcher._stats["skill_matches"] == 1

    def test_dispatch_without_skill(self, dispatcher):
        """Debe usar from_scratch cuando no hay match."""
        with patch.object(dispatcher, 'find_skill_for_task',
                          return_value=None):
            result = dispatcher.dispatch("software-engineer", "say hello")

        assert result["agent"] == "software-engineer"
        assert result["used_skill"] is False
        assert result["skill_context"] == ""
        assert result["reasoning_mode"] == "from_scratch"
        assert dispatcher._stats["no_skill_matches"] == 1
        assert "skill_name" not in result

    def test_dispatch_skill_below_threshold(self, dispatcher):
        """Debe ignorar skill si su similitud está por debajo del threshold."""
        low_skill = {"name": "low", "content": "x", "similarity": SIMILARITY_THRESHOLD - 0.01}
        with patch.object(dispatcher, 'find_skill_for_task',
                          return_value=low_skill):
            result = dispatcher.dispatch("se", "test")

        assert result["used_skill"] is False
        assert result["reasoning_mode"] == "from_scratch"
        assert dispatcher._stats["no_skill_matches"] == 1

    def test_dispatch_multiple_updates_stats(self, dispatcher, sample_skill):
        """Las estadísticas deben acumularse correctamente."""
        with patch.object(dispatcher, 'find_skill_for_task') as mock_find:
            mock_find.side_effect = [sample_skill, None, sample_skill, None]

            dispatcher.dispatch("a", "t1")
            dispatcher.dispatch("b", "t2")
            dispatcher.dispatch("c", "t3")
            dispatcher.dispatch("d", "t4")

        assert dispatcher._stats["total_dispatches"] == 4
        assert dispatcher._stats["skill_matches"] == 2
        assert dispatcher._stats["no_skill_matches"] == 2


# ---------------------------------------------------------------------------
# _search_lancedb_skills
# ---------------------------------------------------------------------------


class TestSearchLanceDBSkills:
    """Tests para _search_lancedb_skills."""

    def test_no_vector_store(self, dispatcher):
        """Debe retornar None si no hay vector store."""
        d = AgentDispatcher()
        assert d._search_lancedb_skills("test") is None

    def test_exception_during_search(self, dispatcher, mock_vector_store):
        """Debe manejar excepción en vector_store.search."""
        mock_vector_store.search.side_effect = RuntimeError("DB down")
        result = dispatcher._search_lancedb_skills("test query")
        assert result is None

    def test_empty_results(self, dispatcher, mock_vector_store):
        """Debe retornar None si no hay resultados."""
        mock_vector_store.search.return_value = []
        result = dispatcher._search_lancedb_skills("test")
        assert result is None

    def test_score_below_threshold(self, dispatcher, mock_vector_store):
        """Debe retornar None si el score está por debajo del threshold."""
        mock_vector_store.search.return_value = [
            {"metadata": {"name": "x"}, "score": SIMILARITY_THRESHOLD - 0.1}
        ]
        result = dispatcher._search_lancedb_skills("test")
        assert result is None

    def test_successful_match(self, dispatcher, mock_vector_store):
        """Debe retornar skill cuando hay match suficiente."""
        mock_vector_store.search.return_value = [
            {
                "metadata": {
                    "name": "my-skill",
                    "domain": "dev",
                    "agent": "se",
                    "trigger": "code",
                },
                "score": SIMILARITY_THRESHOLD + 0.1,
            }
        ]
        with patch.object(dispatcher, '_read_skill_md', return_value="content"):
            result = dispatcher._search_lancedb_skills("test query")

        assert result is not None
        assert result["name"] == "my-skill"
        assert result["domain"] == "dev"
        assert result["agent"] == "se"
        assert result["trigger"] == "code"
        assert result["content"] == "content"
        assert result["similarity"] == SIMILARITY_THRESHOLD + 0.1

    def test_embedding_generation(self, dispatcher, mock_vector_store):
        """El embedding debe ser un vector 384D normalizado."""
        mock_vector_store.search.return_value = []
        dispatcher._search_lancedb_skills("hi")
        call_vec = mock_vector_store.search.call_args[0][1]
        assert call_vec.shape == (384,)
        assert call_vec.dtype == np.float32
        norm = np.linalg.norm(call_vec)
        assert abs(norm - 1.0) < 1e-6


# ---------------------------------------------------------------------------
# _read_skill_md
# ---------------------------------------------------------------------------


class TestReadSkillMd:
    """Tests para _read_skill_md.

    NOTA: _read_skill_md tiene @lru_cache, por lo que cada test usa
    un path diferente para evitar contaminacion entre tests.
    """

    def _setup_path_mocks(self, path_str: str):
        """Helper: crea mocks para Path con control sobre exists/read_text."""
        mock_path = MagicMock()
        mock_min_path = MagicMock()
        mock_path.with_suffix.return_value = mock_min_path
        # Hacer que el str() del mock devuelva el path para que lru_cache
        # use diferentes claves
        mock_path.__str__ = MagicMock(return_value=path_str)
        return mock_path, mock_min_path

    def test_prefer_min_md(self):
        """Debe preferir el archivo .min.md si existe."""
        mock_path, mock_min_path = self._setup_path_mocks("/fake/a.md")
        mock_min_path.exists.return_value = True
        mock_min_path.read_text.return_value = "min content"
        with patch("harness.orchestrator.agent_dispatcher.Path",
                   return_value=mock_path):
            content = AgentDispatcher._read_skill_md("/fake/a.md")
        assert content == "min content"
        mock_min_path.read_text.assert_called_once_with(encoding='utf-8')

    def test_fallback_to_md(self):
        """Debe caer en .md si .min.md no existe."""
        mock_path, mock_min_path = self._setup_path_mocks("/fake/b.md")
        mock_min_path.exists.return_value = False
        mock_path.exists.return_value = True
        mock_path.read_text.return_value = "original content"
        with patch("harness.orchestrator.agent_dispatcher.Path",
                   return_value=mock_path):
            content = AgentDispatcher._read_skill_md("/fake/b.md")
        assert content == "original content"
        mock_path.read_text.assert_called_once_with(encoding='utf-8')

    def test_no_file_exists(self):
        """Debe retornar string vacio si no existe ningun archivo."""
        mock_path, mock_min_path = self._setup_path_mocks("/fake/c.md")
        mock_min_path.exists.return_value = False
        mock_path.exists.return_value = False
        with patch("harness.orchestrator.agent_dispatcher.Path",
                   return_value=mock_path):
            content = AgentDispatcher._read_skill_md("/fake/c.md")
        assert content == ""

    def test_exception_handling(self):
        """Debe retornar string vacio si hay una excepción."""
        mock_path, mock_min_path = self._setup_path_mocks("/fake/d.md")
        mock_min_path.exists.side_effect = OSError("permission denied")
        with patch("harness.orchestrator.agent_dispatcher.Path",
                   return_value=mock_path):
            content = AgentDispatcher._read_skill_md("/fake/d.md")
        assert content == ""


# ---------------------------------------------------------------------------
# Stats
# ---------------------------------------------------------------------------


class TestStats:
    """Tests para get_stats y reset_stats."""

    def test_get_stats(self, dispatcher):
        """Debe retornar copia del dict de estadísticas."""
        dispatcher._stats["skill_matches"] = 5
        stats = dispatcher.get_stats()
        assert stats["skill_matches"] == 5
        stats["skill_matches"] = 99
        assert dispatcher._stats["skill_matches"] == 5

    def test_reset_stats(self, dispatcher):
        """Debe resetear todos los contadores a cero."""
        dispatcher._stats["total_dispatches"] = 10
        dispatcher._stats["skill_matches"] = 7
        dispatcher._stats["no_skill_matches"] = 3
        dispatcher.reset_stats()
        assert dispatcher._stats == {
            "total_dispatches": 0,
            "skill_matches": 0,
            "no_skill_matches": 0,
        }


# ---------------------------------------------------------------------------
# dispatch_async
# ---------------------------------------------------------------------------


class TestDispatchAsync:
    """Tests para dispatch_async (sync wrapper via asyncio.run)."""

    def test_async_with_skill(self, dispatcher):
        """Debe retornar resultado con skill context."""
        skill = {"name": "sk", "content": "skill content"}
        with patch.object(dispatcher, 'find_skill_for_task',
                          return_value=skill):
            with patch("harness.memory_rag.context_assembler.ContextAssembler"):
                with patch("harness.orchestrator.agent_bus.AgentBus"):
                    with patch("harness.orchestrator.agent_dispatcher.LanceVectorStore"):
                        result = asyncio.run(dispatcher.dispatch_async(
                            "se", "build api"
                        ))

        assert result["agent"] == "se"
        assert result["task"] == "build api"
        assert result["used_skill"] is True
        assert result["skill_context"] == "skill content"
        assert result["reasoning_mode"] == "guided_by_skill"

    def test_async_without_skill(self, dispatcher):
        """Debe retornar resultado con from_scratch."""
        with patch.object(dispatcher, 'find_skill_for_task',
                          return_value=None):
            with patch("harness.memory_rag.context_assembler.ContextAssembler"):
                with patch("harness.orchestrator.agent_bus.AgentBus"):
                    with patch("harness.orchestrator.agent_dispatcher.LanceVectorStore"):
                        result = asyncio.run(dispatcher.dispatch_async(
                            "se", "say hello"
                        ))

        assert result["used_skill"] is False
        assert result["skill_context"] == ""
        assert result["reasoning_mode"] == "from_scratch"

    def test_async_with_plan_context(self, dispatcher):
        """Debe incluir execution_plan cuando se pasa plan_context."""
        plan = {
            "session_id": "sess-1",
            "plan_summary": "test plan",
            "current_level": ["level1"],
            "previous_results": [],
            "communication_log": [],
            "is_complete": False,
        }
        with patch.object(dispatcher, 'find_skill_for_task',
                          return_value=None):
            with patch("harness.memory_rag.context_assembler.ContextAssembler"):
                with patch("harness.orchestrator.agent_bus.AgentBus"):
                    with patch("harness.orchestrator.agent_dispatcher.LanceVectorStore"):
                        result = asyncio.run(dispatcher.dispatch_async(
                            "se", "complex task",
                            plan_context=plan,
                        ))

        assert result["reasoning_mode"] == "guided_by_plan"
        assert result["execution_plan"]["session_id"] == "sess-1"
        assert result["execution_plan"]["plan_summary"] == "test plan"
        assert result["execution_plan"]["is_complete"] is False


# ---------------------------------------------------------------------------
# dispatch_batch
# ---------------------------------------------------------------------------


class TestDispatchBatch:
    """Tests para dispatch_batch (sync wrapper via asyncio.run)."""

    def test_batch_multiple_tasks(self, dispatcher):
        """Debe despachar multiples tareas en paralelo."""
        tasks = [("se", "task1"), ("qa", "task2")]
        with patch.object(dispatcher, 'dispatch_async') as mock_da:
            mock_da.side_effect = [
                {"agent": "se", "task": "task1"},
                {"agent": "qa", "task": "task2"},
            ]
            results = asyncio.run(dispatcher.dispatch_batch(tasks))

        assert len(results) == 2
        assert results[0]["agent"] == "se"
        assert results[1]["agent"] == "qa"

    def test_empty_batch(self, dispatcher):
        """Debe retornar lista vacia para batch vacio."""
        results = asyncio.run(dispatcher.dispatch_batch([]))
        assert results == []
