"""Algoritmos de grafo para SWARMIND (Spec ruscadb-graph-algorithms).

PageRank, centralidad, shortest path sobre subgrafos extraidos de RuscaDB.
"""

from __future__ import annotations

from collections import deque
from typing import Any


def _nodes(adj: dict[Any, list[Any]]) -> set[Any]:
    """Nodos del grafo: claves mas destinos alcanzables.

    Args:
        adj: Mapa nodo -> vecinos salientes.

    Returns:
        Conjunto de nodos (claves y destinos).
    """
    nodes = set(adj.keys())
    for neighbors in adj.values():
        nodes.update(neighbors)
    return nodes


def _undirected(adj: dict[Any, list[Any]], nodes: set[Any]) -> dict[Any, set[Any]]:
    """Adyacencia no dirigida (cada arista cuenta en ambos sentidos).

    Args:
        adj: Mapa nodo -> vecinos salientes.
        nodes: Nodos del grafo.

    Returns:
        Mapa nodo -> conjunto de vecinos sin direccion.
    """
    undirected: dict[Any, set[Any]] = {n: set() for n in nodes}
    for node, neighbors in adj.items():
        for nb in neighbors:
            undirected[node].add(nb)
            undirected[nb].add(node)
    return undirected


def pagerank(adj: dict[Any, list[Any]], damping: float = 0.85, iterations: int = 20) -> dict[Any, float]:
    """Calcula PageRank sobre un grafo dirigido.

    La masa de los nodos sin aristas salientes (dangling) se reparte uniforme
    en cada iteracion, de modo que el ranking suma 1 (formulacion estandar).

    Args:
        adj: Mapa nodo -> lista de vecinos salientes.
        damping: Factor de amortiguacion (default 0.85).
        iterations: Numero de iteraciones.

    Returns:
        Mapa nodo -> score PageRank (suma 1).
    """
    nodes = _nodes(adj)
    if not nodes:
        return {}
    rank = {node: 1.0 / len(nodes) for node in nodes}
    for _ in range(iterations):
        rank = _pagerank_iteration(rank, adj, nodes, damping)
    return rank


def _pagerank_iteration(
    rank: dict[Any, float], adj: dict[Any, list[Any]], nodes: set[Any], damping: float
) -> dict[Any, float]:
    """Una iteracion de PageRank con redistribucion de masa dangling.

    Args:
        rank: Ranking de la iteracion previa.
        adj: Mapa nodo -> vecinos salientes.
        nodes: Nodos del grafo.
        damping: Factor de amortiguacion.

    Returns:
        Ranking actualizado.
    """
    n = len(nodes)
    dangling = sum(rank[node] for node in nodes if not adj.get(node))
    base = ((1.0 - damping) + damping * dangling) / n
    new_rank = dict.fromkeys(nodes, base)
    for node, neighbors in adj.items():
        if not neighbors:
            continue
        share = damping * rank[node] / len(neighbors)
        for neighbor in neighbors:
            new_rank[neighbor] += share
    return new_rank


def betweenness_centrality(adj: dict[Any, list[Any]]) -> dict[Any, float]:
    """Centralidad de intermediacion (Brandes).

    Args:
        adj: Mapa nodo -> lista de vecinos salientes (tratado como no dirigido).

    Returns:
        Mapa nodo -> centralidad.
    """
    nodes = _nodes(adj)
    # construir grafo no dirigido
    undirected = _undirected(adj, nodes)
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
    """Componentes conectados (grafo no dirigido).

    Args:
        adj: Mapa nodo -> vecinos.

    Returns:
        Lista de sets de nodos por componente.
    """
    nodes = _nodes(adj)
    undirected = _undirected(adj, nodes)
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
            for nb in undirected[n]:
                if nb not in visited:
                    visited.add(nb)
                    queue.append(nb)
        components.append(comp)
    return components


__all__ = ["betweenness_centrality", "connected_components", "pagerank", "shortest_path"]
