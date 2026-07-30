"""ThoughtGraph — Grafo de pensamientos para razonamiento multi-paso.

Define las estructuras de datos centrales para Graph-of-Thought:
- Thought: Nodo individual de razonamiento
- ThoughtGraph: Grafo DAG de pensamientos con navegacion, path finding
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class Thought:
    """Nodo individual en el grafo de pensamientos.

    Representa un paso de razonamiento atomico dentro del GoT.
    Cada Thought tiene un padre (excepto la raiz), una puntuacion de
    calidad, y metadatos para trazabilidad.

    Attributes:
        id: Identificador unico del nodo.
        content: Contenido textual del paso de razonamiento.
        parent_id: ID del Thought padre. None para el nodo raiz.
        score: Puntuacion de calidad [0, 1].
        depth: Profundidad desde la raiz (0-indexed).
        metadata: Metadatos adicionales.
    """
    id: str
    content: str
    parent_id: Optional[str]
    score: float = 0.0
    depth: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Serializa el pensamiento a diccionario.

        Returns:
            Dict con id, content, parent_id, score, depth, metadata.
        """
        return {
            "id": self.id,
            "content": self.content,
            "parent_id": self.parent_id,
            "score": round(self.score, 4),
            "depth": self.depth,
            "metadata": dict(self.metadata),
        }


@dataclass
class ThoughtGraph:
    """Grafo aciclico dirigido (DAG) de pensamientos.

    Almacena todos los nodos (thoughts) y aristas (edges) que conforman
    el espacio de razonamiento explorado por GoTPlanner.

    Attributes:
        thoughts: Mapa de id -> Thought.
        edges: Mapa de parent_id -> lista de children_ids.
        root_id: ID del nodo raiz.
        metrics: Metricas de exploracion.
    """

    thoughts: Dict[str, Thought] = field(default_factory=dict)
    edges: Dict[str, List[str]] = field(default_factory=dict)
    root_id: str = ""
    metrics: Dict[str, Any] = field(default_factory=dict)

    def add_thought(self, thought: Thought) -> None:
        """Agrega un nodo al grafo.

        Args:
            thought: Pensamiento a insertar.

        Raises:
            ValueError: Si el id ya existe en el grafo.
        """
        if thought.id in self.thoughts:
            raise ValueError(
                f"[ThoughtGraph] Thought id '{thought.id}' ya existe. "
                f"WHERE: add_thought."
            )
        self.thoughts[thought.id] = thought
        if thought.parent_id:
            self.edges.setdefault(thought.parent_id, []).append(thought.id)

    def get_children(self, thought_id: str) -> List[Thought]:
        """Retorna los hijos directos de un nodo.

        Args:
            thought_id: ID del nodo padre.

        Returns:
            Lista de Thoughts hijos ordenada por score descendente.
        """
        child_ids: List[str] = self.edges.get(thought_id, [])
        children: List[Thought] = [
            self.thoughts[cid] for cid in child_ids if cid in self.thoughts
        ]
        children.sort(key=lambda t: t.score, reverse=True)
        return children

    def get_parent(self, thought_id: str) -> Optional[Thought]:
        """Retorna el padre de un nodo.

        Args:
            thought_id: ID del nodo hijo.

        Returns:
            Thought padre o None si es raiz o no existe.
        """
        thought: Optional[Thought] = self.thoughts.get(thought_id)
        if thought is None or thought.parent_id is None:
            return None
        return self.thoughts.get(thought.parent_id)

    def get_path_to_root(self, thought_id: str) -> List[Thought]:
        """Obtiene el camino desde la raiz hasta el nodo dado.

        Args:
            thought_id: ID del nodo destino.

        Returns:
            Lista ordenada [raiz, ..., nodo_destino].
        """
        path: List[Thought] = []
        current: Optional[str] = thought_id
        while current is not None and current in self.thoughts:
            path.append(self.thoughts[current])
            current = self.thoughts[current].parent_id
        path.reverse()
        return path

    def get_leaves(self) -> List[Thought]:
        """Retorna todos los nodos hoja (sin hijos).

        Returns:
            Lista de Thoughts hoja ordenada por score descendente.
        """
        all_ids: set = set(self.thoughts.keys())
        parent_ids: set = set(self.edges.keys())
        leaf_ids = all_ids - parent_ids
        leaves: List[Thought] = [
            self.thoughts[tid] for tid in leaf_ids if tid in self.thoughts
        ]
        leaves.sort(key=lambda t: t.score, reverse=True)
        return leaves

    def max_depth(self) -> int:
        """Retorna la profundidad maxima del grafo.

        Returns:
            Profundidad maxima (0 si esta vacio).
        """
        if not self.thoughts:
            return 0
        return max(t.depth for t in self.thoughts.values())

    def node_count(self) -> int:
        """Retorna el numero total de nodos.

        Returns:
            Cantidad de nodos.
        """
        return len(self.thoughts)

    def to_dict(self) -> Dict[str, Any]:
        """Serializa el grafo completo a diccionario.

        Returns:
            Dict con root_id, thoughts, edges, metrics.
        """
        return {
            "root_id": self.root_id,
            "node_count": self.node_count(),
            "max_depth": self.max_depth(),
            "thoughts": {k: v.to_dict() for k, v in self.thoughts.items()},
            "edges": dict(self.edges),
            "metrics": dict(self.metrics),
        }
