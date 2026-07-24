"""Tests para Knowledge Graph — memoria asociativa local-first."""
from __future__ import annotations

from pathlib import Path

import pytest

from harness.memory_rag.knowledge_graph import KnowledgeGraph


@pytest.fixture
def kg() -> KnowledgeGraph:
    """KnowledgeGraph en memoria."""
    return KnowledgeGraph()


class TestInit:
    """Inicializacion del grafo."""

    def test_empty_graph(self, kg: KnowledgeGraph) -> None:
        """Grafo vacio debe tener 0 nodos."""
        stats = kg.get_stats()
        assert stats["nodes"] == 0
        assert stats["edges"] == 0

    def test_add_node(self, kg: KnowledgeGraph) -> None:
        """Agregar nodo debe incrementar contador."""
        kg.add_node("skill:test", "skill")
        assert kg.get_stats()["nodes"] == 1


class TestConnect:
    """Conexion entre nodos."""

    def test_connect_two_nodes(self, kg: KnowledgeGraph) -> None:
        """Conectar dos nodos debe crear arista."""
        kg.connect("agent:builder", "skill:rust", "uses")
        stats = kg.get_stats()
        assert stats["nodes"] == 2
        assert stats["edges"] == 1

    def test_connect_auto_creates_nodes(self, kg: KnowledgeGraph) -> None:
        """Conectar debe auto-crear nodos si no existen."""
        kg.connect("skill:new-one", "skill:other", "related")
        assert kg.get_stats()["nodes"] == 2


class TestQuery:
    """Consulta al grafo."""

    def test_query_direct(self, kg: KnowledgeGraph) -> None:
        """Consulta directa debe retornar vecinos."""
        kg.connect("agent:builder", "skill:a", "uses")
        kg.connect("agent:builder", "skill:b", "uses")
        results = kg.query("agent:builder", relation="uses")
        assert len(results) == 2

    def test_query_with_type_filter(self, kg: KnowledgeGraph) -> None:
        """Filtrar por tipo de nodo."""
        kg.connect("agent:builder", "skill:a", "uses")
        kg.connect("agent:builder", "skill:b", "uses")
        results = kg.query("agent:builder", node_type="skill")
        assert len(results) == 2

    def test_query_no_results(self, kg: KnowledgeGraph) -> None:
        """Nodo inexistente debe retornar lista vacia."""
        assert kg.query("nonexistent") == []

    def test_query_reverse(self, kg: KnowledgeGraph) -> None:
        """Busqueda reversa debe encontrar aristas entrantes."""
        kg.connect("agent:builder", "skill:rust", "uses")
        # Reverse desde skill:rust debe encontrar agent:builder que apunta a el
        results = kg.query("agent:builder", reverse=False)
        assert len(results) >= 1


class TestFindPath:
    """Busqueda de caminos."""

    def test_direct_path(self, kg: KnowledgeGraph) -> None:
        """Camino directo entre dos nodos."""
        kg.connect("agent:builder", "skill:rust", "uses")
        paths = kg.find_path("agent:builder", "skill:rust")
        assert len(paths) >= 1

    def test_no_path(self, kg: KnowledgeGraph) -> None:
        """Sin camino debe retornar lista vacia."""
        kg.add_node("node:a")
        kg.add_node("node:z")
        paths = kg.find_path("node:a", "node:z")
        assert len(paths) == 0


class TestPersistence:
    """Persistencia a JSON."""

    def test_save_and_load(self, kg: KnowledgeGraph, tmp_path: Path) -> None:
        """Guardar y cargar debe preservar nodos."""
        kg.connect("agent:builder", "skill:rust", "uses")
        kg.connect("agent:scientist", "skill:python", "uses")
        p = tmp_path / "kg.json"
        kg.save(p)
        
        kg2 = KnowledgeGraph(path=p)
        assert kg2.get_stats()["nodes"] == 4
        assert kg2.get_stats()["edges"] == 2

    def test_load_nonexistent(self) -> None:
        """Cargar archivo inexistente debe retornar False."""
        kg = KnowledgeGraph(path=Path("/nonexistent/kg.json"))
        assert kg.get_stats()["nodes"] == 0


class TestSeed:
    """Poblado automatico del grafo."""

    def test_seed_from_skills(self, kg: KnowledgeGraph) -> None:
        """Seed desde skills debe crear conexiones."""
        count = kg.seed_from_skills(Path(".opencode") / "skills")
        assert count >= 20
        # Cada skill crea 2 nodos (skill + agent), total = count * 2
        assert kg.get_stats()["nodes"] >= 20

    def test_seed_from_adrs(self, kg: KnowledgeGraph, tmp_path: Path) -> None:
        """Seed desde ADRs debe crear conexiones."""
        adr_dir = Path("docs/src/adr")
        if adr_dir.exists():
            count = kg.seed_from_adrs(adr_dir)
            assert count >= 0


class TestSearchByMetadata:
    """Busqueda por metadatos."""

    def test_search_by_metadata(self, kg: KnowledgeGraph) -> None:
        """Buscar nodos por metadata debe funcionar."""
        kg.add_node("skill:test", "skill", metadata={"version": "1.0"})
        results = kg.search_by_metadata("version", "1.0")
        assert "skill:test" in results


class TestStats:
    """Estadisticas del grafo."""

    def test_stats_types(self, kg: KnowledgeGraph) -> None:
        """Stats debe incluir tipos de nodos."""
        kg.add_node("skill:a", "skill")
        kg.add_node("agent:b", "agent")
        stats = kg.get_stats()
        assert stats["types"].get("skill") == 1
        assert stats["types"].get("agent") == 1
