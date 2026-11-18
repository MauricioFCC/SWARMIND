"""Tests de los algoritmos de grafo (oráculos congelados a mano)."""

from __future__ import annotations

import pytest

from harness.memory_rag.graph_algorithms import (
    betweenness_centrality,
    connected_components,
    pagerank,
    shortest_path,
)


def test_pagerank_suma_uno_y_destaca_el_nodo_apuntado() -> None:
    """En una cadena a->b->c, c recibe mas masa que a."""
    ranks = pagerank({"a": ["b"], "b": ["c"], "c": []})

    assert sum(ranks.values()) == pytest.approx(1.0)
    assert ranks["c"] > ranks["b"] > ranks["a"]


def test_pagerank_grafo_vacio() -> None:
    """Sin nodos no hay ranking."""
    assert pagerank({}) == {}


def test_pagerank_ciclo_simetrico() -> None:
    """Un ciclo de dos nodos reparte la masa por igual."""
    ranks = pagerank({"a": ["b"], "b": ["a"]})

    assert ranks["a"] == pytest.approx(ranks["b"])


def test_betweenness_centro_de_estrella_maximo() -> None:
    """El centro de una estrella es el unico nodo puente."""
    centrality = betweenness_centrality(
        {"a": ["c"], "b": ["c"], "c": ["a", "b"], "d": ["c"]}
    )

    assert centrality["c"] > 0.0
    assert centrality["a"] == pytest.approx(0.0)
    assert centrality["c"] == max(centrality.values())


def test_shortest_path_encuentra_cadena_minima() -> None:
    """BFS devuelve el camino de menor numero de saltos."""
    adj = {"a": ["b", "d"], "b": ["c"], "c": ["a"], "d": []}

    assert shortest_path(adj, "a", "c") == ["a", "b", "c"]
    assert shortest_path(adj, "d", "c") == []
    assert shortest_path(adj, "a", "a") == ["a"]


def test_connected_components_separa_islas() -> None:
    """Dos pares sin conexion entre si son dos componentes."""
    components = connected_components({"a": ["b"], "b": ["a"], "c": ["d"], "d": []})

    assert sorted(sorted(component) for component in components) == [["a", "b"], ["c", "d"]]
