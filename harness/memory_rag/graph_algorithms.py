"""Algoritmos de grafo para SWARMIND (Spec ruscadb-graph-algorithms).

PageRank, centralidad, shortest path sobre subgrafos extraidos de RuscaDB.
"""

from __future__ import annotations

from collections import deque
from typing import Any


def pagerank(adj: dict[Any, list[Any]], damping: float = 0.85, iterations: int = 20) -> dict[Any, float]:
    """Calcula PageRank sobre un grafo dirigido.

    Args:
        adj: Mapa nodo -> lista de vecinos salientes.
        damping: Factor de amortiguacion (default 0.85).
        iterations: Numero de iteraciones.

    Returns:
        Mapa nodo -> score PageRank.
    """
    nodes = set(adj.keys())
    for neighbors in adj.values():
        nodes.update(neighbors)
    if not nodes:
        return {}
    n = len(nodes)
    rank = {node: 1.0 / n for node in nodes}
    for _ in range(iterations):
        new_rank = {node: (1 - damping) / n for node in nodes}
        for node, neighbors in adj.items():
            if not neighbors:
                continue
            share = rank[node] / len(neighbors)
            for neighbor in neighbors:
                new_rank[neighbor] += damping * share
        rank = new_rank
    return rank


def betweenness_centrality(adj: dict[Any, list[Any]]) -> dict[Any, float]:
    """Centralidad de intermediacion (Brandes).

    Args:
        adj: Mapa nodo -> lista de vecinos salientes (tratado como no dirigido).

    Returns:
        Mapa nodo -> centralidad.
    """
    nodes = set(adj.keys())
    for neighbors in adj.values():
        nodes.update(neighbors)
    # construir grafo no dirigido
    undirected: dict[Any, set[Any]] = {n: set() for n in nodes}
    for node, neighbors in adj.items():
        for nb in neighbors:
            undirected[node].add(nb)
            undirected[nb].add(node)
    centrality = {n: 0.0 for n in nodes}
    for s in nodes:
        # BFS
        stack: list[Any] = []
        pred: dict[Any, list[Any]] = {n: [] for n in nodes}
        sigma = {n: 0 for n in nodes}
        sigma[s] = 1
        dist = {n: -1 for n in nodes}
        dist[s] = 0
        queue: deque[Any] = deque([s])
        while queue:
            v = queue.popleft()
            stack.append(v)
            for w in undirected[v]:
                if dist[w] < 0:
                    dist[w] = dist[v] + 1
                    queue.append(w)
                if dist[w] == dist[v] + 1:
                    sigma[w] += sigma[v]
                    pred[w].append(v)
        delta = {n: 0.0 for n in nodes}
        while stack:
            w = stack.pop()
            for v in pred[w]:
                if sigma[w] > 0:
                    delta[v] += (sigma[v] / sigma[w]) * (1 + delta[w])
            if w != s:
                centrality[w] += delta[w]
    # normalizar
    if len(nodes) > 2:
        factor = 1.0 / ((len(nodes) - 1) * (len(nodes) - 2))
        for n in nodes:
            centrality[n] *= factor
    return centrality


def shortest_path(adj: dict[Any, list[Any]], source: Any, target: Any) -> list[Any]:
    """Camino mas corto (BFS) entre source y target.

    Args:
        adj: Mapa nodo -> vecinos.
        source: Nodo origen.
        target: Nodo destino.

    Returns:
        Lista de nodos del camino (vacia si no hay camino).
    """
    if source == target:
        return [source]
    visited = {source}
    queue: deque[tuple[Any, list[Any]]] = deque([(source, [source])])
    while queue:
        node, path = queue.popleft()
        for nb in adj.get(node, []):
            if nb == target:
                return path + [nb]
            if nb not in visited:
                visited.add(nb)
                queue.append((nb, path + [nb]))
    return []


def connected_components(adj: dict[Any, list[Any]]) -> list[set[Any]]:
    """Componentes conectados (no dirigido).

    Args:
        adj: Mapa nodo -> vecinos.

    Returns:
        Lista de sets de nodos por componente.
    """
    nodes = set(adj.keys())
    for neighbors in adj.values():
        nodes.update(neighbors)
    visited: set[Any] = set()
    components: list[set[Any]] = []
    for start in nodes:
        if start in visited:
            continue
        comp: set[Any] = set()
        queue: deque[Any] = deque([start])
        visited.add(start)
        while queue:
            n = queue.popleft()
            comp.add(n)
            for nb in adj.get(n, []):
                if nb not in visited:
                    visited.add(nb)
                    queue.append(nb)
        components.append(comp)
    return components


__all__ = ["betweenness_centrality", "connected_components", "pagerank", "shortest_path"]
