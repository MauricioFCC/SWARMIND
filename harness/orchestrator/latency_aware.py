"""
CriticalPath — Latency-Aware Orchestration (LAMaS-lite, ADR-0034).

Analiza el DAG de subtasks para identificar la RUTA CRÍTICA (camino más largo)
y reordenar la ejecución priorizando los nodos críticos sin romper
dependencias. Basado en LAMaS (UCF, arXiv 2601.10560): -38-46% de reducción
del critical path al optimizar explícitamente por latencia.

Propiedad clave: optimize() preserva el orden topológico. Nunca invalida
dependencias.
"""

from __future__ import annotations

from collections import defaultdict, deque


class CriticalPath:
    """
    Analizador de ruta crítica sobre un plan de subtasks.

    Uso:
        cp = CriticalPath()
        result = cp.compute(plan.subtasks)
        ordered = cp.optimize(plan.subtasks)
        pairs = cp.parallelizable_pairs(plan.subtasks)
    """

    # ------------------------------------------------------------------
    # Longest path
    # ------------------------------------------------------------------

    def longest_path(self, subtasks: list) -> tuple[list[str], float]:
        """Calcula el camino más largo del DAG (ruta crítica).

        Peso de cada nodo: `estimated_latency_ms` si existe, si no 1.0.

        Args:
            subtasks: lista de subtasks con .id, .dependencies y
                opcionalmente .estimated_latency_ms.

        Returns:
            (lista de ids en la ruta crítica, longitud total estimada).
        """
        if not subtasks:
            return [], 0.0

        by_id = {s.id: s for s in subtasks}
        # Dependencias externas (fuera del subconjunto) ya estan completadas:
        # se ignoran para el DP de ruta critica dentro del subconjunto.
        deps: dict[str, list[str]] = {
            s.id: [d for d in s.dependencies if d in by_id]
            for s in subtasks
        }
        # Orden topológico (Kahn).
        indegree = {s.id: len(deps[s.id]) for s in subtasks}
        adj: dict[str, list[str]] = defaultdict(list)
        for s in subtasks:
            for dep in deps[s.id]:
                adj[dep].append(s.id)

        queue = deque([s.id for s in subtasks if indegree[s.id] == 0])
        topo: list[str] = []
        while queue:
            node = queue.popleft()
            topo.append(node)
            for nxt in adj[node]:
                indegree[nxt] -= 1
                if indegree[nxt] == 0:
                    queue.append(nxt)

        # Si hay ciclo, procesar los restantes igualmente.
        if len(topo) < len(subtasks):
            for s in subtasks:
                if s.id not in topo:
                    topo.append(s.id)

        # DP: dist[i] = peso(i) + max(dist[dep]).
        dist: dict[str, float] = {}
        parent: dict[str, str | None] = {s.id: None for s in subtasks}
        for node in topo:
            weight = self._weight(by_id[node])
            best = weight
            best_parent = None
            for dep in deps[node]:
                if dist[dep] + weight > best:
                    best = dist[dep] + weight
                    best_parent = dep
            dist[node] = best
            parent[node] = best_parent

        end = max(subtasks, key=lambda s: dist[s.id]).id
        path: list[str] = []
        cur: str | None = end
        while cur is not None:
            path.append(cur)
            cur = parent[cur]
        path.reverse()
        return path, dist[end]

    # ------------------------------------------------------------------
    # API pública
    # ------------------------------------------------------------------

    def compute(self, subtasks: list) -> dict:
        """Computa la ruta crítica y la expone como dict.

        Args:
            subtasks: lista de subtasks.

        Returns:
            Dict con critical_path (list[str]), critical_ids (set serializable
            como list) y estimated_latency_ms (float).
        """
        path, length = self.longest_path(subtasks)
        return {
            "critical_path": path,
            "critical_ids": path,
            "estimated_latency_ms": length,
        }

    def optimize(self, subtasks: list) -> list:
        """Reordena los subtasks priorizando la ruta crítica.

        Implementa ordenamiento topológico (Kahn) con prioridad por ruta
        crítica: en cada paso, entre los nodos disponibles (indegree 0), se
        eligen primero los que pertenecen a la ruta crítica. Esto acelera el
        critical path SIN violar nunca el orden topológico.

        Args:
            subtasks: lista de subtasks.

        Returns:
            Nueva lista con el mismo conjunto de subtasks (orden priorizado).
        """
        if not subtasks:
            return []
        critical, _ = self.longest_path(subtasks)
        critical_set = set(critical)
        by_id = {s.id: s for s in subtasks}

        indegree = {s.id: len(s.dependencies) for s in subtasks}
        adj: dict[str, list[str]] = defaultdict(list)
        for s in subtasks:
            for dep in s.dependencies:
                adj[dep].append(s.id)

        # Orden estable: nodos listos = [ruta crítica primero, luego original].
        ready = [s.id for s in subtasks if indegree[s.id] == 0]
        ready.sort(key=lambda n: (0 if n in critical_set else 1,
                                  subtasks.index(by_id[n])))

        ordered: list = []
        while ready:
            node = ready.pop(0)
            ordered.append(by_id[node])
            for nxt in adj[node]:
                indegree[nxt] -= 1
                if indegree[nxt] == 0:
                    ready.append(nxt)
            ready.sort(key=lambda n: (0 if n in critical_set else 1,
                                      subtasks.index(by_id[n])))

        # Ciclos residuales: añadir los que quedaron al final (orden original).
        appended = {s.id for s in ordered}
        ordered.extend(s for s in subtasks if s.id not in appended)
        return ordered

    # ------------------------------------------------------------------
    # Parallelismo
    # ------------------------------------------------------------------

    def parallelizable_pairs(self, subtasks: list) -> list[tuple[str, str]]:
        """Pares de subtasks independientes (ejecutables en paralelo).

        Dos subtasks son independientes si ninguno depende del otro (directa
        o transitivamente).

        Args:
            subtasks: lista de subtasks.

        Returns:
            Lista de tuplas (id_a, id_b) ordenadas, sin duplicados invertidos.
        """
        pairs: list[tuple[str, str]] = []
        by_id = {s.id: s for s in subtasks}
        ids = [s.id for s in subtasks]
        for i, a in enumerate(ids):
            for b in ids[i + 1:]:
                if not self._depends(by_id, a, b) and not self._depends(by_id, b, a):
                    pairs.append((a, b))
        return pairs

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _weight(subtask) -> float:
        """Peso del nodo: estimated_latency_ms o 1.0 por defecto."""
        value = getattr(subtask, "estimated_latency_ms", None)
        return float(value) if value is not None else 1.0

    @staticmethod
    def _depends(by_id: dict, a: str, b: str) -> bool:
        """True si a depende (transitivamente) de b."""
        seen: set[str] = set()
        stack = list(by_id[a].dependencies)
        while stack:
            dep = stack.pop()
            if dep == b:
                return True
            if dep in seen:
                continue
            seen.add(dep)
            stack.extend(by_id[dep].dependencies)
        return False
