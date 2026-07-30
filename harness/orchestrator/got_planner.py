"""
GoTPlanner — Graph-of-Thought para razonamiento complejo multi-paso.

Implementa exploracion en grafo de pensamientos con:
- Ramificacion: Generar multiples caminos de razonamiento
- Evaluacion: Puntuar cada nodo por calidad/coherencia
- Poda: Eliminar ramas debiles
- Backtracking: Volver a nodos anteriores si una rama falla
- Consolidacion: Sintetizar la mejor solucion desde multiples caminos

Basado en:
- RouteGoT (Liu et al., 2026): Routing node-adaptive, 79% menos tokens
- KGoT (Besta et al., 2025): Knowledge Graph of Thoughts, +29% GAIA
- RL-of-Thoughts (Hao et al., 2026): RL navigator para topologia dinamica
- SOLAR (Li et al., 2025): Optimizacion dinamica CoT/ToT/GoT

WHY: Graph-of-Thought supera a Chain/Tree-of-Thought en tareas que requieren
exploracion no lineal, backtracking y sintesis multi-camino. Esencial para
razonamiento cientifico, depuracion compleja y planificacion estrategica.

WHERE: Utilizado por el orquestador para tareas de alta complejidad donde
un solo camino de razonamiento es insuficiente.
"""

from __future__ import annotations

import hashlib
import json
import logging
import math
import random
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, AsyncGenerator, Dict, List, Optional, Set, Tuple

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Evaluacion
EVAL_COHERENCE_WEIGHT = 0.35    # Peso de coherencia interna
EVAL_RELEVANCE_WEIGHT = 0.35    # Peso de relevancia a la tarea
EVAL_DEPTH_WEIGHT = 0.15        # Peso de profundidad de razonamiento
EVAL_NOVELTY_WEIGHT = 0.15      # Peso de novedad respecto a otros nodos

# Poda
PRUNE_DEFAULT_THRESHOLD = 0.3   # Umbral default de poda
PRUNE_MAX_CROWD_DENSITY = 0.3   # Fraccion maxima de nodos en mismo nivel

# Expansion
EXPAND_DEFAULT_BRANCHES = 2     # Ramas default por expansion
EXPAND_MAX_BRANCHES = 5         # Limite superior de ramas

# Consolidacion
CONSOLIDATE_TOP_K = 3           # Top-K caminos para sintesis
CONSOLIDATE_MIN_PATH_LENGTH = 1 # Longitud minima de camino valido

# Metricas
METRICS_WINDOW = 100            # Ventana de metricas recientes
MAX_GRAPH_NODES = 200           # Limite de nodos totales para evitar OoM


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class ExpandStrategy(str, Enum):
    """Estrategia de expansion de pensamiento."""
    BFS = "bfs"             # Breadth-first: expande nivel completo antes de profundizar
    DFS = "dfs"             # Depth-first: profundiza en rama prometedora
    BEAM = "beam"           # Beam search: top-K nodos por nivel
    RANDOM = "random"       # Seleccion aleatoria de nodo a expandir
    BEST_FIRST = "best_first"  # Greedy: siempre expande el mejor puntuado


class ConsolidateMethod(str, Enum):
    """Metodo de consolidacion de caminos."""
    BEST_PATH = "best_path"         # Mejor camino individual
    WEIGHTED_FUSION = "weighted_fusion"  # Fusion ponderada de top-K
    MAJORITY_ENSEMBLE = "majority_ensemble"  # Votacion entre caminos
    MERGE_AND_REFINE = "merge_and_refine"   # Merge y refinamiento


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------

@dataclass
class Thought:
    """
    Nodo individual en el grafo de pensamientos.

    Representa un paso de razonamiento atómico dentro del GoT.
    Cada Thought tiene un padre (excepto la raíz), una puntuación de
    calidad, y metadatos para trazabilidad.

    WHY: Estructura inmutable que permite navegación, evaluación y poda
    del grafo sin efectos colaterales.

    WHERE: Usado como unidad mínima de razonamiento en GoTPlanner.
    Cada llamada a expand() produce instancias de Thought.
    """

    id: str
    """Identificador único del nodo (hash de contenido + timestamp)."""

    content: str
    """Contenido textual del paso de razonamiento."""

    parent_id: Optional[str]
    """ID del Thought padre. None para el nodo raíz."""

    score: float = 0.0
    """Puntuación de calidad [0, 1] asignada por evaluate()."""

    depth: int = 0
    """Profundidad desde la raíz (0-indexed)."""

    metadata: Dict[str, Any] = field(default_factory=dict)
    """Metadatos adicionales: timestamp, tokens_usados, estrategia, etc."""

    def to_dict(self) -> Dict[str, Any]:
        """Serializa el pensamiento a diccionario."""
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
    """
    Grafo acíclico dirigido (DAG) de pensamientos.

    Almacena todos los nodos (thoughts) y aristas (edges) que conforman
    el espacio de razonamiento explorado por GoTPlanner.

    WHY: Estructura de datos central que permite navegación, poda,
    backtracking y consolidación sobre el grafo completo.

    WHERE: Instanciado por GoTPlanner.plan() y mutado por expand(),
    prune() y backtrack().
    """

    thoughts: Dict[str, Thought] = field(default_factory=dict)
    """Mapa de id → Thought con todos los nodos del grafo."""

    edges: Dict[str, List[str]] = field(default_factory=dict)
    """Mapa de parent_id → lista de children_ids. Representa aristas."""

    root_id: str = ""
    """ID del nodo raíz (punto de entrada del razonamiento)."""

    metrics: Dict[str, Any] = field(default_factory=dict)
    """Métricas de exploración: nodos_total, profundidad_max, etc."""

    def add_thought(self, thought: Thought) -> None:
        """
        Agrega un nodo al grafo.

        Args:
            thought: Pensamiento a insertar.

        Raises:
            ValueError: Si el id ya existe en el grafo.
        """
        if thought.id in self.thoughts:
            raise ValueError(
                f"Thought id '{thought.id}' ya existe en el grafo. "
                f"WHAT: Duplicado en add_thought | "
                f"WHY: Cada nodo debe tener id único | "
                f"WHERE: ThoughtGraph.add_thought()"
            )
        self.thoughts[thought.id] = thought

        # Registrar arista si tiene padre
        if thought.parent_id:
            self.edges.setdefault(thought.parent_id, []).append(thought.id)

    def get_children(self, thought_id: str) -> List[Thought]:
        """
        Retorna los hijos directos de un nodo.

        Args:
            thought_id: ID del nodo padre.

        Returns:
            Lista de Thoughts hijos (ordenada por score descendente).
        """
        child_ids = self.edges.get(thought_id, [])
        children = [self.thoughts[cid] for cid in child_ids if cid in self.thoughts]
        children.sort(key=lambda t: t.score, reverse=True)
        return children

    def get_parent(self, thought_id: str) -> Optional[Thought]:
        """
        Retorna el padre de un nodo.

        Args:
            thought_id: ID del nodo hijo.

        Returns:
            Thought padre o None si es raíz o no existe.
        """
        thought = self.thoughts.get(thought_id)
        if thought is None or thought.parent_id is None:
            return None
        return self.thoughts.get(thought.parent_id)

    def get_path_to_root(self, thought_id: str) -> List[Thought]:
        """
        Obtiene el camino desde la raíz hasta el nodo dado.

        Args:
            thought_id: ID del nodo destino.

        Returns:
            Lista ordenada [raíz, ..., nodo_destino].
        """
        path: List[Thought] = []
        current_id: Optional[str] = thought_id
        while current_id is not None and current_id in self.thoughts:
            path.append(self.thoughts[current_id])
            current_id = self.thoughts[current_id].parent_id
        path.reverse()
        return path

    def get_leaves(self) -> List[Thought]:
        """
        Retorna todos los nodos hoja (sin hijos).

        WHAT: Nodos que no aparecen como padres en edges, es decir,
        no tienen descendientes en el grafo.

        WHY: Las hojas son los puntos de frontera del razonamiento;
        desde ellas se puede expandir hacia nuevas direcciones.

        WHERE: Usado por _select_nodes_for_expansion() y get_best_path().

        Returns:
            Lista de Thoughts hoja (ordenada por score descendente).
        """
        all_ids = set(self.thoughts.keys())
        parent_ids = set(self.edges.keys())
        leaf_ids = all_ids - parent_ids
        leaves = [self.thoughts[tid] for tid in leaf_ids if tid in self.thoughts]
        leaves.sort(key=lambda t: t.score, reverse=True)
        return leaves

    def max_depth(self) -> int:
        """
        Retorna la profundidad máxima del grafo.

        Returns:
            Profundidad máxima (0 si está vacío).
        """
        if not self.thoughts:
            return 0
        return max(t.depth for t in self.thoughts.values())

    def node_count(self) -> int:
        """Retorna el número total de nodos."""
        return len(self.thoughts)

    def to_dict(self) -> Dict[str, Any]:
        """Serializa el grafo completo a diccionario."""
        return {
            "root_id": self.root_id,
            "node_count": self.node_count(),
            "max_depth": self.max_depth(),
            "thoughts": {k: v.to_dict() for k, v in self.thoughts.items()},
            "edges": dict(self.edges),
            "metrics": dict(self.metrics),
        }


# ---------------------------------------------------------------------------
# GoTPlanner
# ---------------------------------------------------------------------------

class GoTPlanner:
    """
    Planificador Graph-of-Thought para razonamiento complejo multi-paso.

    Explora un espacio de razonamiento en forma de grafo, generando
    múltiples caminos de pensamiento, evaluándolos, podando ramas
    débiles y consolidando la mejor solución.

    WHY: GoT supera a Chain/ToT en problemas que requieren exploración
    no lineal, backtracking y síntesis multi-camino (ej: investigación
    científica, depuración compleja, planificación estratégica).

    WHERE: Integrado en el orquestador para tareas clasificadas como
    'complex_reasoning' por el difficulty_router.

    Uso:
        planner = GoTPlanner()
        graph = planner.plan("Analizar impacto de arquitectura microservicios")
        mejor = planner.consolidate(graph)
        stats = planner.get_stats()
    """

    def __init__(
        self,
        storage_path: Optional[str] = None,
        seed: Optional[int] = None,
    ) -> None:
        """
        Inicializa el planificador GoT.

        Args:
            storage_path: Ruta opcional para persistir métricas.
            seed: Semilla para reproducibilidad en expansiones aleatorias.
        """
        self._storage_path = storage_path
        self._rng = random.Random(seed)

        # Contadores y métricas internas
        self._stats: Dict[str, Any] = {
            "total_plans": 0,
            "total_nodes_created": 0,
            "total_nodes_pruned": 0,
            "total_expansions": 0,
            "total_backtracks": 0,
            "avg_graph_size": 0.0,
            "avg_max_depth": 0.0,
            "avg_success_score": 0.0,
            "plans_created": 0,
        }

        # Historial de grafos recientes (para análisis)
        self._recent_graphs: List[Dict[str, Any]] = []
        self._max_history = METRICS_WINDOW

        logger.info(
            "GoTPlanner inicializado | "
            "WHAT: Planificador Graph-of-Thought creado | "
            "WHY: Soportar razonamiento multi-camino | "
            "WHERE: GoTPlanner.__init__()"
        )

    # ------------------------------------------------------------------
    # Public API: Planificación
    # ------------------------------------------------------------------

    def plan(
        self,
        task: str,
        max_branches: int = 3,
        max_depth: int = 5,
        strategy: ExpandStrategy = ExpandStrategy.BEAM,
    ) -> ThoughtGraph:
        """
        Construye un grafo de pensamientos para resolver una tarea.

        Proceso:
          1. Crear nodo raíz con la tarea original
          2. Expandir iterativamente hasta max_depth o convergencia
          3. Evaluar cada nodo generado
          4. Podar ramas por debajo del umbral
          5. Registrar métricas del grafo resultante

        Args:
            task: Descripción de la tarea a resolver.
            max_branches: Máximo de ramas por expansión (default: 3).
            max_depth: Profundidad máxima del grafo (default: 5).
            strategy: Estrategia de expansión (default: BEAM).

        Returns:
            ThoughtGraph poblado con nodos, aristas y métricas.

        Raises:
            ValueError: Si task está vacío.
        """
        if not task or not task.strip():
            raise ValueError(
                "La tarea no puede estar vacía. "
                "WHAT: plan() recibió task vacío | "
                "WHY: Se requiere contenido para generar pensamientos | "
                "WHERE: GoTPlanner.plan()"
            )

        # Limitar parámetros
        branches = max(1, min(max_branches, EXPAND_MAX_BRANCHES))
        depth = max(1, min(max_depth, 20))

        # Inicializar grafo
        graph = ThoughtGraph()
        root = self._create_root_thought(task)
        graph.root_id = root.id
        graph.add_thought(root)

        logger.info(
            "GoTPlanner.plan: inicio | task=%s..., max_branches=%s, "
            "max_depth=%s, strategy=%s",
            task[:60], branches, depth, strategy.value,
        )

        # Expansión iterativa
        for level in range(1, depth + 1):
            # Seleccionar nodos a expandir según estrategia
            nodes_to_expand = self._select_nodes_for_expansion(
                graph, strategy, branches, level,
            )

            if not nodes_to_expand:
                logger.debug(
                    "GoTPlanner.plan: sin nodos expandibles en nivel %s",
                    level,
                )
                break

            # Expandir cada nodo seleccionado
            new_nodes: List[Thought] = []
            for node in nodes_to_expand:
                if graph.node_count() >= MAX_GRAPH_NODES:
                    logger.warning(
                        "GoTPlanner.plan: límite de nodos alcanzado (%s)",
                        MAX_GRAPH_NODES,
                    )
                    break

                children = self.expand(node, branches=branches)
                for child in children:
                    try:
                        graph.add_thought(child)
                        new_nodes.append(child)
                        self._stats["total_nodes_created"] += 1
                    except ValueError:
                        # Nodo duplicado (raro pero seguro)
                        continue

                self._stats["total_expansions"] += 1

            # Evaluar todos los nodos nuevos
            for node in new_nodes:
                node.score = self.evaluate(node, task=task, graph=graph)

            # Podar después de cada nivel (excepto el último)
            if level < depth and new_nodes:
                before = graph.node_count()
                graph = self.prune(graph, threshold=PRUNE_DEFAULT_THRESHOLD)
                pruned = before - graph.node_count()
                self._stats["total_nodes_pruned"] += pruned

            # Si no se generaron nodos, detener
            if not new_nodes:
                break

        # Registrar métricas en el grafo
        elapsed = time.time()
        graph.metrics = {
            "task": task[:100],
            "strategy": strategy.value,
            "max_branches": branches,
            "max_depth": depth,
            "node_count": graph.node_count(),
            "max_depth_actual": graph.max_depth(),
            "leaf_count": len(graph.get_leaves()),
            "total_expansions": self._stats["total_expansions"],
            "created_at": datetime.now(timezone.utc).isoformat(),
        }

        # Actualizar estadísticas del planner
        self._update_stats(graph)

        # Persistir si está configurado
        if self._storage_path:
            self._save_metrics()

        logger.info(
            "GoTPlanner.plan: completo | nodos=%s, profundidad=%s, "
            "hojas=%s",
            graph.node_count(), graph.max_depth(), len(graph.get_leaves()),
        )

        return graph

    def expand(
        self,
        thought: Thought,
        branches: int = 2,
    ) -> List[Thought]:
        """
        Genera pensamientos hijos a partir de uno existente.

        Crea `branches` variantes de razonamiento que continúan desde
        el pensamiento dado. Cada variante explora una dirección
        diferente: profundización, cuestionamiento, alternativa, etc.

        WHY: La ramificación es el mecanismo central de GoT para
        explorar múltiples hipótesis en paralelo.

        Args:
            thought: Pensamiento padre a expandir.
            branches: Número de hijos a generar (default: 2).

        Returns:
            Lista de Thoughts hijos generados.
        """
        n = max(1, min(branches, EXPAND_MAX_BRANCHES))
        children: List[Thought] = []

        # Estrategias de expansión sintética (simula razonamiento)
        strategies = [
            "profundizar: desarrollar implicaciones de la idea anterior",
            "cuestionar: identificar suposiciones o puntos débiles",
            "alternativa: proponer un enfoque diferente",
            "evidenciar: buscar sustento o contraejemplos",
            "sintetizar: conectar con otros conceptos del grafo",
            "descomponer: dividir en subproblemas más manejables",
            "aplicar: mostrar cómo se aplica a un caso concreto",
            "generalizar: extraer un principio más abstracto",
        ]

        # Sesgo hacia estrategias según profundidad
        if thought.depth < 2:
            # Niveles tempranos: descomposición y alternativas
            pool = strategies[:4]
        elif thought.depth < 4:
            # Niveles medios: profundizar y evidenciar
            pool = strategies[2:6]
        else:
            # Niveles profundos: sintetizar y generalizar
            pool = strategies[4:]

        # Seleccionar n estrategias (con reposición si es necesario)
        selected = self._rng.choices(pool, k=n) if len(pool) < n else self._rng.sample(pool, k=n)

        for i, strat in enumerate(selected):
            child_id = self._make_thought_id(thought.id, i)
            child = Thought(
                id=child_id,
                content=self._simulate_reasoning(
                    thought.content, strat, thought.depth + 1,
                ),
                parent_id=thought.id,
                score=0.0,  # Se evaluará después
                depth=thought.depth + 1,
                metadata={
                    "strategy": strat,
                    "parent_score": thought.score,
                    "created_at": datetime.now(timezone.utc).isoformat(),
                    "index": i,
                },
            )
            children.append(child)

        logger.debug(
            "GoTPlanner.expand: padre=%s, %d hijos generados | "
            "WHAT: Ramificación desde %s | "
            "WHY: Explorar variantes de razonamiento | "
            "WHERE: GoTPlanner.expand()",
            thought.id[:8], len(children), thought.id[:8],
        )

        return children

    def evaluate(
        self,
        thought: Thought,
        task: str = "",
        graph: Optional[ThoughtGraph] = None,
    ) -> float:
        """
        Evalúa la calidad de un pensamiento en [0, 1].

        Considera:
        - Coherencia interna (longitud, estructura lógica)
        - Relevancia a la tarea original
        - Profundidad de razonamiento
        - Novedad respecto a otros nodos (si se proporciona el grafo)

        WHY: La evaluación permite podar ramas débiles y guiar la
        expansión hacia caminos prometedores.

        Args:
            thought: Pensamiento a evaluar.
            task: Tarea original para medir relevancia.
            graph: Grafo completo para medir novedad (opcional).

        Returns:
            Puntuación [0, 1] donde 1 = máxima calidad.
        """
        score = 0.0

        # --- Coherencia (peso: EVAL_COHERENCE_WEIGHT) ---
        coherence = self._eval_coherence(thought)
        score += coherence * EVAL_COHERENCE_WEIGHT

        # --- Relevancia (peso: EVAL_RELEVANCE_WEIGHT) ---
        if task:
            relevance = self._eval_relevance(thought.content, task)
        else:
            relevance = 0.5  # Neutro si no hay tarea
        score += relevance * EVAL_RELEVANCE_WEIGHT

        # --- Profundidad (peso: EVAL_DEPTH_WEIGHT) ---
        depth_score = self._eval_depth_quality(thought)
        score += depth_score * EVAL_DEPTH_WEIGHT

        # --- Novedad (peso: EVAL_NOVELTY_WEIGHT) ---
        if graph is not None and graph.thoughts:
            novelty = self._eval_novelty(thought, graph)
        else:
            novelty = 0.5
        score += novelty * EVAL_NOVELTY_WEIGHT

        # Normalizar y asegurar rango
        final_score = max(0.0, min(1.0, score))

        logger.debug(
            "GoTPlanner.evaluate: id=%s, score=%.4f "
            "(coh=%.2f, rel=%.2f, dep=%.2f, nov=%.2f) | "
            "WHAT: Evaluación de nodo | "
            "WHY: Determinar calidad para poda/selección | "
            "WHERE: GoTPlanner.evaluate()",
            thought.id[:8], final_score,
            coherence, relevance, depth_score, novelty,
        )

        return final_score

    def prune(
        self,
        graph: ThoughtGraph,
        threshold: float = 0.3,
    ) -> ThoughtGraph:
        """
        Elimina ramas débiles del grafo recursivamente.

        Un nodo se poda si su score está por debajo del umbral Y
        no tiene hijos de alta calidad que lo justifiquen.
        La poda es recursiva: si un nodo se poda, también se podan
        todos sus descendientes.

        WHY: La poda controla el crecimiento del grafo y elimina
        caminos de razonamiento improductivos, reduciendo costo
        computacional y manteniendo calidad.

        Args:
            graph: Grafo a podar (no mutado, se crea copia).
            threshold: Umbral de score mínimo (default: 0.3).

        Returns:
            Nuevo ThoughtGraph con nodos podados.
        """
        if graph.node_count() <= 1:
            return graph

        threshold = max(0.0, min(1.0, threshold))

        # Identificar nodos a podar (hojas con score bajo primero)
        to_prune: Set[str] = set()
        leaves = graph.get_leaves()

        # Ordenar hojas por score ascendente (peores primero)
        leaves.sort(key=lambda t: t.score)

        for leaf in leaves:
            if leaf.score < threshold:
                # Poda hoja
                to_prune.add(leaf.id)
                # Propagar hacia arriba: si todos los hijos de un padre
                # serán podados, también podar el padre
                parent = graph.get_parent(leaf.id)
                while parent is not None:
                    siblings = graph.get_children(parent.id)
                    remaining = [s for s in siblings if s.id not in to_prune]
                    if not remaining and parent.id != graph.root_id:
                        to_prune.add(parent.id)
                        parent = graph.get_parent(parent.id)
                    else:
                        break

        # También considerar nodos internos con score bajo
        for tid, thought in graph.thoughts.items():
            if tid not in to_prune and tid != graph.root_id:
                if thought.score < threshold * 0.5:  # Umbral más bajo para internos
                    children = graph.get_children(tid)
                    if not children:  # Solo si no tiene hijos valiosos
                        to_prune.add(tid)

        # Si se podaría todo, mantener al menos raíz
        if len(to_prune) >= graph.node_count():
            to_prune = {tid for tid in to_prune if tid != graph.root_id}

        # Construir nuevo grafo sin nodos podados
        new_graph = ThoughtGraph(root_id=graph.root_id)

        for tid, thought in graph.thoughts.items():
            if tid not in to_prune:
                new_graph.add_thought(thought)

        # Preservar métricas del grafo original
        new_graph.metrics = dict(graph.metrics)
        new_graph.metrics["pruned_nodes"] = len(to_prune)
        new_graph.metrics["prune_threshold"] = threshold

        logger.info(
            "GoTPlanner.prune: %d nodos podados (umbral=%.2f) | "
            "WHAT: Poda de ramas débiles | "
            "WHY: Controlar crecimiento y mantener calidad | "
            "WHERE: GoTPlanner.prune()",
            len(to_prune), threshold,
        )

        return new_graph

    def backtrack(
        self,
        graph: ThoughtGraph,
        thought_id: str,
    ) -> Optional[Thought]:
        """
        Navega hacia atrás desde un nodo hasta encontrar un padre válido.

        Sube por la jerarquía del grafo hasta encontrar un nodo con
        score >= threshold o hasta llegar a la raíz. Útil cuando una
        rama no progresa y se necesita retomar desde un punto anterior.

        WHY: El backtracking permite recuperarse de caminos sin salida
        sin reiniciar todo el razonamiento, ahorrando cómputo.

        Args:
            graph: Grafo actual.
            thought_id: ID del nodo desde el cual retroceder.

        Returns:
            Thought del ancestro válido más cercano, o None si no existe.
        """
        if thought_id not in graph.thoughts:
            logger.warning(
                "GoTPlanner.backtrack: thought_id %s no encontrado | "
                "WHAT: Intento de backtrack a nodo inexistente | "
                "WHY: El nodo pudo haber sido podado | "
                "WHERE: GoTPlanner.backtrack()",
                thought_id[:8],
            )
            return None

        current_id: Optional[str] = thought_id
        visited: Set[str] = set()

        while current_id is not None and current_id in graph.thoughts:
            if current_id in visited:
                logger.error(
                    "GoTPlanner.backtrack: ciclo detectado en %s | "
                    "WHAT: Grafo con ciclo en backtrack | "
                    "WHY: Inconsistencia en estructura del grafo | "
                    "WHERE: GoTPlanner.backtrack()",
                    current_id[:8],
                )
                return None
            visited.add(current_id)

            thought = graph.thoughts[current_id]

            # Si encontramos un nodo con buena puntuación (o raíz), usarlo
            if thought.score >= 0.5 or current_id == graph.root_id:
                self._stats["total_backtracks"] += 1
                logger.debug(
                    "GoTPlanner.backtrack: %s → %s (score=%.2f) | "
                    "WHAT: Backtrack exitoso | "
                    "WHY: Rama sin progreso, retornando a nodo válido | "
                    "WHERE: GoTPlanner.backtrack()",
                    thought_id[:8], current_id[:8], thought.score,
                )
                return thought

            # Subir al padre
            current_id = thought.parent_id

        # Si no encontramos nada, retornar raíz
        if graph.root_id in graph.thoughts:
            self._stats["total_backtracks"] += 1
            return graph.thoughts[graph.root_id]

        return None

    def consolidate(
        self,
        graph: ThoughtGraph,
        method: ConsolidateMethod = ConsolidateMethod.WEIGHTED_FUSION,
    ) -> str:
        """
        Sintetiza la mejor solución desde múltiples caminos del grafo.

        Dependiendo del método:
        - BEST_PATH: Retorna el contenido del mejor camino individual.
        - WEIGHTED_FUSION: Fusiona ponderadamente los top-K caminos.
        - MAJORITY_ENSEMBLE: Votación entre caminos para consenso.
        - MERGE_AND_REFINE: Merge de segmentos y refinamiento.

        WHY: La consolidación es el paso final que extrae valor del
        grafo explorado, combinando fortalezas de múltiples caminos.

        Args:
            graph: Grafo con pensamientos explorados.
            method: Método de consolidación (default: WEIGHTED_FUSION).

        Returns:
            Texto consolidado con la mejor solución encontrada.
        """
        if graph.node_count() == 0:
            return ""

        # Obtener los mejores caminos
        paths = self._get_top_paths(graph, k=CONSOLIDATE_TOP_K)
        if not paths:
            # Fallback: contenido de la raíz
            root = graph.thoughts.get(graph.root_id)
            return root.content if root else ""

        if method == ConsolidateMethod.BEST_PATH:
            return paths[0][-1].content if paths[0] else ""

        if method == ConsolidateMethod.WEIGHTED_FUSION:
            return self._weighted_fusion(paths, graph)

        if method == ConsolidateMethod.MAJORITY_ENSEMBLE:
            return self._majority_ensemble(paths)

        if method == ConsolidateMethod.MERGE_AND_REFINE:
            return self._merge_and_refine(paths, graph)

        # Fallback
        return paths[0][-1].content if paths[0] else ""

    def get_best_path(self, graph: ThoughtGraph) -> List[Thought]:
        """
        Retorna el camino de mayor puntuación en el grafo.

        El mejor camino se determina por el score promedio de sus nodos,
        priorizando caminos más largos (mayor profundidad de razonamiento).

        WHY: Identificar la línea de razonamiento más prometedora para
        extracción o presentación al usuario.

        Args:
            graph: Grafo de pensamientos.

        Returns:
            Lista ordenada de Thoughts [raíz, ..., hoja_mejor].
        """
        if graph.node_count() == 0:
            return []

        leaves = graph.get_leaves()
        if not leaves:
            # Si no hay hojas, retornar toda la cadena desde raíz
            root = graph.thoughts.get(graph.root_id)
            return [root] if root else []

        best_leaf = max(leaves, key=lambda t: self._path_score(graph, t.id))
        return graph.get_path_to_root(best_leaf.id)

    def get_stats(self) -> Dict[str, Any]:
        """
        Retorna estadísticas acumuladas del planificador.

        WHY: Proporcionar visibilidad sobre el rendimiento y uso del
        planificador para monitoreo y optimización.

        Returns:
            Dict con métricas del planificador.
        """
        stats = dict(self._stats)
        stats["recent_graphs_count"] = len(self._recent_graphs)
        return stats

    # ------------------------------------------------------------------
    # Internal: Expansión y selección
    # ------------------------------------------------------------------

    def _create_root_thought(self, task: str) -> Thought:
        """
        Crea el nodo raíz del grafo a partir de la tarea.

        WHY: La raíz es el punto de entrada único que define el problema
        a resolver. Todos los caminos de razonamiento parten de aquí.

        Args:
            task: Descripción de la tarea.

        Returns:
            Thought raíz.
        """
        root_id = self._make_thought_id("root", 0)
        return Thought(
            id=root_id,
            content=task.strip(),
            parent_id=None,
            score=1.0,  # La raíz siempre tiene score máximo
            depth=0,
            metadata={
                "type": "root",
                "created_at": datetime.now(timezone.utc).isoformat(),
                "tokens_estimate": max(1, len(task) // 4),
            },
        )

    def _select_nodes_for_expansion(
        self,
        graph: ThoughtGraph,
        strategy: ExpandStrategy,
        branches: int,
        level: int,
    ) -> List[Thought]:
        """
        Selecciona qué nodos expandir en el nivel actual según estrategia.

        WHY: La selección estratégica dirige el crecimiento del grafo
        hacia regiones prometedoras del espacio de razonamiento.

        Args:
            graph: Grafo actual.
            strategy: Estrategia de expansión.
            branches: Número de ramas a expandir.
            level: Nivel actual de profundidad.

        Returns:
            Lista de Thoughts a expandir.
        """
        leaves = graph.get_leaves()
        if not leaves:
            return []

        if strategy == ExpandStrategy.BFS:
            # Expandir todas las hojas del nivel más superficial
            min_depth = min(t.depth for t in leaves)
            return [t for t in leaves if t.depth == min_depth]

        elif strategy == ExpandStrategy.DFS:
            # Expandir la hoja más profunda con mejor score
            if not leaves:
                return []
            best = max(leaves, key=lambda t: (t.depth, t.score))
            return [best]

        elif strategy == ExpandStrategy.BEAM:
            # Top-K hojas por score, limitado por branches
            leaves_sorted = sorted(leaves, key=lambda t: t.score, reverse=True)
            k = min(branches, len(leaves_sorted))
            return leaves_sorted[:k]

        elif strategy == ExpandStrategy.RANDOM:
            # Selección aleatoria ponderada por score
            if not leaves:
                return []
            scores = [max(t.score, 0.01) for t in leaves]
            total = sum(scores)
            if total <= 0:
                return self._rng.sample(leaves, k=min(1, len(leaves)))
            weights = [s / total for s in scores]
            k = min(branches, len(leaves))
            selected = self._rng.choices(leaves, weights=weights, k=k)
            return list(selected)

        elif strategy == ExpandStrategy.BEST_FIRST:
            # Siempre expandir la hoja con mejor score
            if not leaves:
                return []
            best = max(leaves, key=lambda t: t.score)
            return [best]

        return leaves[:branches]

    def _make_thought_id(self, parent_id: str, index: int) -> str:
        """
        Genera un ID único para un nuevo pensamiento.

        WHY: IDs determinísticos basados en contenido permiten
        deduplicación y trazabilidad.

        Args:
            parent_id: ID del padre.
            index: Índice entre hermanos.

        Returns:
            ID único en formato hex.
        """
        raw = f"{parent_id}:{index}:{time.time_ns()}:{self._rng.randint(0, 2**32)}"
        return hashlib.sha256(raw.encode()).hexdigest()[:16]

    def _simulate_reasoning(
        self,
        parent_content: str,
        strategy: str,
        depth: int,
    ) -> str:
        """
        Simula un paso de razonamiento sintético.

        En producción, esto sería reemplazado por una llamada a un LLM.
        La simulación genera texto coherente basado en la estrategia
        y el contenido del padre.

        WHY: Permite testear el planificador sin depender de un LLM
        externo, facilitando desarrollo y pruebas unitarias.

        Args:
            parent_content: Contenido del pensamiento padre.
            strategy: Estrategia de razonamiento a simular.
            depth: Profundidad del nuevo nodo.

        Returns:
            Texto simulando un paso de razonamiento.
        """
        # Extraer palabras clave del contenido padre
        words = parent_content.split()
        keywords = [w for w in words if len(w) > 4][:5]

        # Frases de relleno según estrategia
        templates = {
            "profundizar": (
                "Analizando en profundidad: {kw}. "
                "Las implicaciones de este concepto incluyen impacto en "
                "arquitectura, rendimiento y mantenibilidad. "
                "Se requiere considerar trade-offs entre acoplamiento "
                "y cohesión en la implementación concreta."
            ),
            "cuestionar": (
                "Examinando críticamente: {kw}. "
                "¿Es esta suposición válida en todos los contextos? "
                "Existen contraejemplos donde este enfoque falla. "
                "Sería necesario validar con datos empíricos antes "
                "de generalizar esta conclusión."
            ),
            "alternativa": (
                "Explorando alternativa a: {kw}. "
                "Un enfoque diferente podría basarse en first-principles "
                "thinking, descomponiendo el problema en fundamentos "
                "y reconstruyendo la solución desde cero. "
                "Esto evitaría sesgos de la solución inicial."
            ),
            "evidenciar": (
                "Buscando evidencia para: {kw}. "
                "La literatura reciente (2024-2026) muestra que "
                "este enfoque tiene respaldo en papers de alto impacto. "
                "Sin embargo, también existen estudios que cuestionan "
                "su efectividad en escenarios específicos."
            ),
            "sintetizar": (
                "Sintetizando conceptos: {kw}. "
                "Conexión con otros nodos del grafo revela un patrón "
                "emergente. La intersección entre estos conceptos "
                "sugiere una arquitectura híbrida que combina "
                "lo mejor de ambos mundos."
            ),
            "descomponer": (
                "Descomponiendo: {kw}. "
                "Este problema puede dividirse en: (1) análisis de "
                "requisitos, (2) diseño de solución, (3) implementación, "
                "(4) validación, (5) despliegue. Cada subproblema "
                "requiere un enfoque específico."
            ),
            "aplicar": (
                "Aplicando: {kw} a caso concreto. "
                "En un escenario real con alto volumen de datos, "
                "la solución debe priorizar escalabilidad horizontal. "
                "Las métricas de rendimiento serían el factor decisivo "
                "para validar este enfoque."
            ),
            "generalizar": (
                "Generalizando desde: {kw}. "
                "El principio subyacente es aplicable a múltiples "
                "dominios: sistemas distribuidos, procesamiento de "
                "datos, y optimización de recursos. "
                "Este patrón emerge consistentemente en sistemas "
                "complejos bien diseñados."
            ),
        }

        template = templates.get(
            strategy.split(":")[0].strip(),
            "Considerando: {kw}. Este aspecto requiere atención "
            "detallada en el contexto del problema planteado.",
        )

        kw_str = ", ".join(keywords) if keywords else "el concepto planteado"
        result = template.format(kw=kw_str)

        # Añadir marcador de profundidad para diferenciar niveles
        depth_marker = ">" * min(depth, 5)
        return f"{depth_marker} {result}"

    # ------------------------------------------------------------------
    # Internal: Evaluación
    # ------------------------------------------------------------------

    def _eval_coherence(self, thought: Thought) -> float:
        """
        Evalúa la coherencia interna del pensamiento.

        Mide: longitud mínima, presencia de estructura lógica
        (marcadores, conectores), y diversidad léxica.

        Args:
            thought: Pensamiento a evaluar.

        Returns:
            Score de coherencia [0, 1].
        """
        content = thought.content.strip()
        if not content:
            return 0.0

        # Longitud mínima para ser coherente
        words = content.split()
        if len(words) < 5:
            return 0.1

        # Presencia de marcadores lógicos
        logical_markers = [
            "porque", "ya que", "debido a", "por lo tanto",
            "sin embargo", "además", "en consecuencia",
            "por ejemplo", "es decir", "en resumen",
            "therefore", "however", "because", "consequently",
            "furthermore", "moreover", "in addition",
        ]
        marker_count = sum(1 for m in logical_markers if m in content.lower())
        marker_score = min(1.0, marker_count / 3.0)

        # Diversidad léxica (unique words / total words)
        unique_ratio = len(set(w.lower() for w in words)) / max(len(words), 1)
        diversity_score = min(1.0, unique_ratio * 2.0)  # Penalizar repetición

        # Score final: promedio ponderado
        return 0.4 * marker_score + 0.6 * diversity_score

    def _eval_relevance(self, content: str, task: str) -> float:
        """
        Evalúa la relevancia del pensamiento respecto a la tarea.

        Mide solapamiento de términos clave entre el pensamiento
        y la tarea original. Mayor solapamiento = mayor relevancia.

        Args:
            content: Contenido del pensamiento.
            task: Tarea original.

        Returns:
            Score de relevancia [0, 1].
        """
        if not task:
            return 0.5

        # Tokenizar y normalizar
        task_tokens = set(task.lower().split())
        content_tokens = set(content.lower().split())

        if not task_tokens:
            return 0.5

        # Jaccard similarity entre conjuntos
        intersection = task_tokens & content_tokens
        union = task_tokens | content_tokens

        if not union:
            return 0.0

        jaccard = len(intersection) / len(union)

        # Bonus por contener palabras clave largas (más significativas)
        long_keywords = {w for w in intersection if len(w) > 6}
        bonus = min(0.2, len(long_keywords) * 0.05)

        return min(1.0, jaccard * 1.5 + bonus)

    def _eval_depth_quality(self, thought: Thought) -> float:
        """
        Evalúa la calidad del razonamiento según la profundidad.

        Los nodos más profundos obtienen bonus por elaboración,
        pero con rendimientos decrecientes para evitar profundidad
        excesiva sin sustancia.

        Args:
            thought: Pensamiento a evaluar.

        Returns:
            Score de profundidad [0, 1].
        """
        depth = thought.depth

        # Bonus logarítmico por profundidad
        if depth == 0:
            return 0.7  # Raíz: buena pero no excepcional
        if depth <= 2:
            return 0.5 + depth * 0.15  # 0.65 - 0.8
        if depth <= 5:
            return 0.8 + (depth - 2) * 0.05  # 0.85 - 0.95
        # Más allá: rendimiento decreciente
        return min(0.95, 0.8 + math.log(depth) * 0.1)

    def _eval_novelty(self, thought: Thought, graph: ThoughtGraph) -> float:
        """
        Evalúa la novedad del pensamiento respecto al grafo existente.

        Mide la distancia semántica entre el nuevo pensamiento y
        los existentes. Mayor distancia = mayor novedad.

        WHY: Penalizar pensamientos redundantes fomenta diversidad
        en la exploración.

        Args:
            thought: Pensamiento a evaluar.
            graph: Grafo completo.

        Returns:
            Score de novedad [0, 1].
        """
        if graph.node_count() <= 1:
            return 0.7  # Primeros nodos: siempre novedosos

        content_tokens = set(thought.content.lower().split())
        if not content_tokens:
            return 0.0

        max_similarity = 0.0
        for existing in graph.thoughts.values():
            if existing.id == thought.id:
                continue
            existing_tokens = set(existing.content.lower().split())
            if not existing_tokens:
                continue

            # Jaccard entre pensamientos
            intersection = content_tokens & existing_tokens
            union = content_tokens | existing_tokens
            similarity = len(intersection) / max(len(union), 1)

            max_similarity = max(max_similarity, similarity)

        # Novedad = 1 - similitud máxima
        novelty = 1.0 - max_similarity

        # Penalizar si es casi idéntico a algún nodo
        if max_similarity > 0.85:
            novelty *= 0.3

        return max(0.0, min(1.0, novelty))

    # ------------------------------------------------------------------
    # Internal: Caminos y consolidación
    # ------------------------------------------------------------------

    def _path_score(self, graph: ThoughtGraph, leaf_id: str) -> float:
        """
        Calcula el score promedio de un camino desde raíz hasta hoja.

        WHY: Evaluar caminos completos permite comparar líneas de
        razonamiento, no solo nodos individuales.

        Args:
            graph: Grafo de pensamientos.
            leaf_id: ID de la hoja destino.

        Returns:
            Score promedio del camino [0, 1].
        """
        path = graph.get_path_to_root(leaf_id)
        if not path:
            return 0.0

        # Promedio ponderado: más peso a nodos profundos
        total_weight = 0.0
        weighted_sum = 0.0

        for i, thought in enumerate(path):
            weight = 1.0 + i * 0.2  # Más peso a mayor profundidad
            weighted_sum += thought.score * weight
            total_weight += weight

        return weighted_sum / total_weight if total_weight > 0 else 0.0

    def _get_top_paths(
        self,
        graph: ThoughtGraph,
        k: int = 3,
    ) -> List[List[Thought]]:
        """
        Obtiene los K mejores caminos del grafo.

        Args:
            graph: Grafo de pensamientos.
            k: Número de caminos a retornar.

        Returns:
            Lista de caminos, cada camino es List[Thought].
        """
        leaves = graph.get_leaves()
        if not leaves:
            return []

        # Filtrar hojas con profundidad mínima
        valid_leaves = [
            t for t in leaves
            if t.depth >= CONSOLIDATE_MIN_PATH_LENGTH
        ]
        if not valid_leaves:
            valid_leaves = leaves

        # Ordenar por score del camino
        scored = [
            (self._path_score(graph, t.id), t.id)
            for t in valid_leaves
        ]
        scored.sort(key=lambda x: x[0], reverse=True)

        # Top-K
        top_k = min(k, len(scored))
        paths = []
        for _, leaf_id in scored[:top_k]:
            path = graph.get_path_to_root(leaf_id)
            if path:
                paths.append(path)

        return paths

    def _weighted_fusion(
        self,
        paths: List[List[Thought]],
        graph: ThoughtGraph,
    ) -> str:
        """
        Fusiona ponderadamente los contenidos de múltiples caminos.

        Cada camino aporta sus nodos con peso proporcional al score
        del camino. Los nodos se concatenan en orden, eliminando
        redundancias.

        Args:
            paths: Lista de caminos (cada camino es List[Thought]).
            graph: Grafo original (para contexto).

        Returns:
            Texto fusionado.
        """
        if not paths:
            return ""

        # Calcular pesos de cada camino
        path_scores = [self._path_score(graph, p[-1].id) for p in paths]
        total_score = sum(path_scores) or 1.0
        weights = [s / total_score for s in path_scores]

        # Fusionar: intercalar segmentos únicos ordenados por profundidad
        seen_contents: Set[str] = set()
        segments: List[str] = []

        # Recolectar nodos únicos de todos los caminos
        all_nodes: List[Tuple[Thought, float]] = []
        for path, weight in zip(paths, weights):
            for thought in path:
                if thought.id not in seen_contents:
                    seen_contents.add(thought.id)
                    all_nodes.append((thought, weight))

        # Ordenar por profundidad y score
        all_nodes.sort(key=lambda x: (x[0].depth, x[0].score), reverse=False)

        for thought, _ in all_nodes:
            segments.append(thought.content)

        return "\n\n".join(segments)

    def _majority_ensemble(
        self,
        paths: List[List[Thought]],
    ) -> str:
        """
        Genera un consenso por votación entre caminos.

        Identifica las ideas/frases que aparecen en la mayoría de
        los caminos y las combina en una respuesta coherente.

        Args:
            paths: Lista de caminos.

        Returns:
            Texto de consenso.
        """
        if not paths:
            return ""

        # Recolectar oraciones de cada camino
        path_sentences: List[List[str]] = []
        for path in paths:
            sentences = []
            for thought in path:
                # Dividir en oraciones simples
                parts = thought.content.replace("! ", "!|").replace("? ", "?|").split("|")
                for part in parts:
                    part = part.strip()
                    if part and len(part) > 10:
                        sentences.append(part)
            path_sentences.append(sentences)

        if not path_sentences:
            return paths[0][-1].content if paths[0] else ""

        # Votación: frases que aparecen en al menos 2 caminos
        from collections import Counter
        all_sentences = []
        for sentences in path_sentences:
            all_sentences.extend(sentences)

        # Normalizar para comparación
        normalized = {}
        for s in all_sentences:
            key = s.lower().strip()
            normalized[key] = s

        counter = Counter(normalized.keys())
        consensus_keys = [k for k, count in counter.most_common() if count >= max(2, len(paths) // 2)]

        if not consensus_keys:
            # Fallback: mejor camino
            return paths[0][-1].content if paths[0] else ""

        # Construir respuesta con frases de consenso
        consensus_sentences = [normalized[k] for k in consensus_keys]
        return "\n".join(consensus_sentences[:10])  # Limitar a 10 frases

    def _merge_and_refine(
        self,
        paths: List[List[Thought]],
        graph: ThoughtGraph,
    ) -> str:
        """
        Mergea y refina los caminos en una solución coherente.

        Estrategia: tomar la estructura del mejor camino y enriquecerla
        con contenido único de los otros caminos.

        Args:
            paths: Lista de caminos ordenados por calidad.
            graph: Grafo original.

        Returns:
            Texto refinado.
        """
        if not paths:
            return ""

        # Mejor camino como base
        best_path = paths[0]
        best_contents = [t.content for t in best_path]

        # Enriquecer con nodos adicionales de otros caminos no cubiertos
        covered_ids = {t.id for t in best_path}
        extra_contents: List[str] = []

        for path in paths[1:]:
            for thought in path:
                if thought.id not in covered_ids:
                    covered_ids.add(thought.id)
                    if thought.score >= 0.5:  # Solo nodos de calidad
                        extra_contents.append(thought.content)

        # Intercalar: contenido base + extras al final como "consideraciones adicionales"
        result_parts = list(best_contents)
        if extra_contents:
            result_parts.append("\n--- Consideraciones adicionales ---")
            result_parts.extend(extra_contents[:5])  # Limitar extras

        return "\n\n".join(result_parts)

    # ------------------------------------------------------------------
    # Internal: Métricas y persistencia
    # ------------------------------------------------------------------

    def _update_stats(self, graph: ThoughtGraph) -> None:
        """
        Actualiza estadísticas internas del planificador.

        WHY: Mantener métricas actualizadas permite monitorear
        rendimiento y detectar anomalías en la planificación.

        Args:
            graph: Grafo recién generado.
        """
        n = graph.node_count()

        # Running average del tamaño del grafo
        prev_avg = self._stats["avg_graph_size"]
        prev_count = self._stats["total_plans"]
        self._stats["avg_graph_size"] = (
            (prev_avg * prev_count + n) / (prev_count + 1)
            if prev_count > 0 else float(n)
        )

        # Running average de profundidad máxima
        prev_depth_avg = self._stats["avg_max_depth"]
        self._stats["avg_max_depth"] = (
            (prev_depth_avg * prev_count + graph.max_depth()) / (prev_count + 1)
            if prev_count > 0 else float(graph.max_depth())
        )

        # Score promedio de nodos hoja (como proxy de éxito)
        leaves = graph.get_leaves()
        if leaves:
            avg_leaf_score = sum(t.score for t in leaves) / len(leaves)
            prev_success = self._stats["avg_success_score"]
            self._stats["avg_success_score"] = (
                (prev_success * prev_count + avg_leaf_score) / (prev_count + 1)
                if prev_count > 0 else float(avg_leaf_score)
            )

        self._stats["total_plans"] += 1

        # Guardar en historial
        if len(self._recent_graphs) >= self._max_history:
            self._recent_graphs.pop(0)
        self._recent_graphs.append(graph.metrics)

    def _save_metrics(self) -> None:
        """Persiste métricas a disco si hay storage_path configurado."""
        if not self._storage_path:
            return

        import os
        try:
            os.makedirs(os.path.dirname(self._storage_path), exist_ok=True)
            data = {
                "stats": self._stats,
                "recent_graphs": self._recent_graphs[-50:],  # Últimos 50
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
            with open(self._storage_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except (OSError, json.JSONEncodeError) as e:
            logger.warning(
                "GoTPlanner._save_metrics: error persistendo métricas: %s | "
                "WHAT: Fallo en persistencia | "
                "WHY: Storage path inaccesible o datos no serializables | "
                "WHERE: GoTPlanner._save_metrics()",
                str(e),
            )


# ---------------------------------------------------------------------------
# GoTExecutor
# ---------------------------------------------------------------------------

class GoTExecutor:
    """
    Ejecutor de Graph-of-Thought que orquesta planificación y ejecución.

    WHY: Separa la responsabilidad de planificar (GoTPlanner) de la
    de ejecutar, permitiendo diferentes estrategias de ejecución
    (síncrona, streaming) sobre el mismo plan.

    WHERE: Utilizado por el orquestador como interfaz de alto nivel
    para tareas que requieren GoT.
    """

    def __init__(self, planner: Optional[GoTPlanner] = None) -> None:
        """
        Inicializa el ejecutor GoT.

        Args:
            planner: Instancia de GoTPlanner. Si es None, crea una default.
        """
        self._planner = planner or GoTPlanner()
        self._last_graph: Optional[ThoughtGraph] = None
        self._last_result: str = ""

        logger.info(
            "GoTExecutor inicializado | "
            "WHAT: Ejecutor GoT creado | "
            "WHY: Orquestar planificación+ejecución GoT | "
            "WHERE: GoTExecutor.__init__()"
        )

    def execute(
        self,
        task: str,
        max_branches: int = 3,
        max_depth: int = 5,
        strategy: ExpandStrategy = ExpandStrategy.BEAM,
        consolidate_method: ConsolidateMethod = ConsolidateMethod.WEIGHTED_FUSION,
    ) -> str:
        """
        Ejecuta el pipeline completo de Graph-of-Thought.

        Pipeline:
          1. Planificar: construir grafo de pensamientos
          2. Podar: eliminar ramas débiles
          3. Consolidar: sintetizar mejor solución
          4. Retornar resultado

        WHY: Interfaz simple para casos de uso que solo necesitan
        el resultado final sin preocuparse por el proceso.

        Args:
            task: Tarea a resolver.
            max_branches: Máximo de ramas por expansión.
            max_depth: Profundidad máxima del grafo.
            strategy: Estrategia de expansión.
            consolidate_method: Método de consolidación.

        Returns:
            Texto con la mejor solución encontrada.
        """
        start = time.time()

        # 1. Planificar
        graph = self._planner.plan(
            task=task,
            max_branches=max_branches,
            max_depth=max_depth,
            strategy=strategy,
        )

        # 2. Podar (si hay suficientes nodos)
        if graph.node_count() > 3:
            graph = self._planner.prune(graph, threshold=PRUNE_DEFAULT_THRESHOLD)

        # 3. Consolidar
        result = self._planner.consolidate(graph, method=consolidate_method)

        # Almacenar para consulta posterior
        self._last_graph = graph
        self._last_result = result

        elapsed = time.time() - start
        logger.info(
            "GoTExecutor.execute: completo en %.2fs | "
            "WHAT: Ejecución GoT finalizada | "
            "WHY: Pipeline completo ejecutado | "
            "WHERE: GoTExecutor.execute() | "
            "task=%s..., nodos=%d, resultado_len=%d",
            elapsed, task[:40], graph.node_count(), len(result),
        )

        return result

    async def execute_stream(
        self,
        task: str,
        max_branches: int = 3,
        max_depth: int = 5,
        strategy: ExpandStrategy = ExpandStrategy.BEAM,
    ) -> AsyncGenerator[str, None]:
        """
        Ejecuta GoT en modo streaming, yieldiando resultados parciales.

        WHY: Para tareas largas, el streaming permite al usuario ver
        progreso y caminos intermedios antes del resultado final.

        Args:
            task: Tarea a resolver.
            max_branches: Máximo de ramas por expansión.
            max_depth: Profundidad máxima del grafo.
            strategy: Estrategia de expansión.

        Yields:
            Fragmentos de texto con el progreso del razonamiento.
        """
        yield f"[GoT] Iniciando planificación para: {task[:80]}...\n"

        # Planificar paso a paso
        graph = self._planner.plan(
            task=task,
            max_branches=max_branches,
            max_depth=max_depth,
            strategy=strategy,
        )

        yield f"[GoT] Grafo generado: {graph.node_count()} nodos, "
        yield f"{graph.max_depth()} niveles de profundidad.\n"

        # Yield cada camino hoja
        leaves = graph.get_leaves()
        leaves.sort(key=lambda t: t.score, reverse=True)

        for i, leaf in enumerate(leaves[:5]):  # Top 5 hojas
            path = graph.get_path_to_root(leaf.id)
            path_score = self._planner._path_score(graph, leaf.id)

            yield f"\n[Camino {i + 1}] Score: {path_score:.3f}\n"
            for thought in path:
                if thought.id == graph.root_id:
                    continue  # Saltar raíz en streaming
                yield f"  └─ [{thought.id[:8]}][{thought.score:.2f}] "
                yield f"{thought.content[:120]}...\n"

        # Consolidar
        yield "\n[GoT] Consolidando mejor solución...\n"
        result = self._planner.consolidate(graph)

        # Yield resultado final
        yield "\n" + "=" * 40 + "\n"
        yield "[RESULTADO FINAL]\n"
        yield result + "\n"
        yield "=" * 40 + "\n"

        self._last_graph = graph
        self._last_result = result

    def get_planner(self) -> GoTPlanner:
        """Retorna el planificador interno."""
        return self._planner

    def get_last_graph(self) -> Optional[ThoughtGraph]:
        """Retorna el último grafo generado."""
        return self._last_graph

    def get_last_result(self) -> str:
        """Retorna el último resultado generado."""
        return self._last_result
