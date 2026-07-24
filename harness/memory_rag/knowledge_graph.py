"""
Knowledge Graph — Memoria asociativa para AGENTIC.

Implementa un grafo de conocimiento local-first (similar a LanceDB) que conecta:
- Skills con agentes (que agente usa cada skill)
- Skills con ADRs (que decisiones afectan a cada skill)
- Agentes con decisiones (que agente tomo cada decision)
- Conceptos con skills (que skills cubren cada concepto)

Almacenamiento: NetworkX + JSON local (sin servidor, sin dependencias externas).

Basado en FundaPod (arXiv:2605.27864): knowledge graph "second brain"
que conecta skills, agentes, ADRs y decisiones en un grafo semantico.

Usage:
    kg = KnowledgeGraph()
    kg.connect("skill:rust-lang", "agent:builder", "uses")
    kg.connect("adr:0018", "skill:cache-shape", "implements")
    related = kg.query("skill:rust-lang", relation="uses")
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Tipos de nodos en el grafo
# ---------------------------------------------------------------------------

NODE_TYPES = {
    "agent": "agent",
    "skill": "skill",
    "adr": "adr",
    "concept": "concept",
    "decision": "decision",
    "paper": "paper",
    "project": "project",
}

# ---------------------------------------------------------------------------
# Knowledge Graph
# ---------------------------------------------------------------------------


class KnowledgeGraph:
    """
    Grafo de conocimiento local-first para AGENTIC.
    
    Almacena relaciones entre skills, agentes, ADRs y decisiones
    en un grafo NetworkX persistido como JSON.
    
    Usage:
        kg = KnowledgeGraph()
        kg.connect("skill:rust-lang", "agent:builder", "uses")
        kg.connect("adr:0018", "skill:cache-shape", "implements")
        
        # Consultar
        skills_of_builder = kg.query("agent:builder", relation="uses")
        adrs_for_rust = kg.query("skill:rust-lang", relation="implements", reverse=True)
        
        # Guardar/Cargar
        kg.save("knowledge_graph.json")
        kg.load("knowledge_graph.json")
    """

    def __init__(self, path: Optional[Path] = None):
        """
        Args:
            path: Ruta al archivo JSON para persistencia.
                  Si no se especifica, solo en memoria.
        """
        self._path = path
        self._graph: Any = None
        self._load_networkx()
        if path and path.exists():
            self.load(path)

    def _load_networkx(self) -> None:
        """Cargar NetworkX e inicializar grafo."""
        import networkx as nx
        self._graph = nx.MultiDiGraph()

    # ------------------------------------------------------------------
    # Operaciones del grafo
    # ------------------------------------------------------------------

    def add_node(
        self,
        node_id: str,
        node_type: str = "concept",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        Agregar un nodo al grafo.
        
        Args:
            node_id: Identificador unico (ej: "skill:rust-lang").
            node_type: Tipo de nodo (agent, skill, adr, concept, decision, paper).
            metadata: Metadatos adicionales del nodo.
        """
        if not self._graph.has_node(node_id):
            self._graph.add_node(
                node_id,
                type=node_type,
                metadata=metadata or {},
                created_at=datetime.now(timezone.utc).isoformat(),
            )

    def connect(
        self,
        source: str,
        target: str,
        relation: str,
        weight: float = 1.0,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        Conectar dos nodos con una relacion.
        
        Args:
            source: Nodo origen.
            target: Nodo destino.
            relation: Tipo de relacion (uses, implements, depends, related_to, etc.).
            weight: Peso de la relacion (0-1).
            metadata: Metadatos adicionales.
        """
        # Auto-crear nodos si no existen
        if not self._graph.has_node(source):
            stype = source.split(":")[0] if ":" in source else "concept"
            self.add_node(source, stype)
        if not self._graph.has_node(target):
            ttype = target.split(":")[0] if ":" in target else "concept"
            self.add_node(target, ttype)

        self._graph.add_edge(
            source, target,
            relation=relation,
            weight=weight,
            metadata=metadata or {},
            created_at=datetime.now(timezone.utc).isoformat(),
        )

    def query(
        self,
        node: str,
        relation: Optional[str] = None,
        node_type: Optional[str] = None,
        max_depth: int = 1,
        reverse: bool = False,
    ) -> List[Dict[str, Any]]:
        """
        Consultar el grafo desde un nodo.
        
        Args:
            node: Nodo de inicio.
            relation: Filtrar por tipo de relacion.
            node_type: Filtrar por tipo de nodo destino.
            max_depth: Profundidad maxima de busqueda (1 = solo vecinos directos).
            reverse: Si True, busca aristas entrantes en vez de salientes.
            
        Returns:
            Lista de nodos encontrados con sus relaciones.
        """
        if not self._graph.has_node(node):
            return []

        results = []
        seen: Set[str] = {node}
        current: Set[str] = {node}

        for _ in range(max_depth):
            next_level: Set[str] = set()
            for n in current:
                # Obtener vecinos (salientes o entrantes)
                neighbors = (
                    self._graph.predecessors(n) if reverse
                    else self._graph.successors(n)
                )
                for neighbor in neighbors:
                    if neighbor in seen:
                        continue
                    seen.add(neighbor)

                    # Obtener aristas entre n y neighbor
                    edges = (
                        list(self._graph.in_edges(neighbor, data=True))
                        if reverse
                        else list(self._graph.out_edges(n, data=True))
                    )

                    for _src, _dst, data in edges:
                        if reverse:
                            _src, _dst = _dst, _src
                        if (_src == n or reverse) and _dst == neighbor:
                            if relation and data.get("relation") != relation:
                                continue
                            if node_type:
                                ndata = self._graph.nodes.get(neighbor, {})
                                if ndata.get("type") != node_type:
                                    continue

                            results.append({
                                "node": neighbor,
                                "type": self._graph.nodes.get(neighbor, {}).get("type", "unknown"),
                                "relation": data.get("relation", "unknown"),
                                "weight": data.get("weight", 1.0),
                                "metadata": data.get("metadata", {}),
                            })
                            next_level.add(neighbor)

            current = next_level

        return results

    def find_path(
        self,
        source: str,
        target: str,
        max_length: int = 5,
    ) -> List[List[Dict[str, Any]]]:
        """
        Encontrar caminos entre dos nodos.
        
        Args:
            source: Nodo origen.
            target: Nodo destino.
            max_length: Longitud maxima del camino.
            
        Returns:
            Lista de caminos, cada camino es una lista de aristas.
        """
        import networkx as nx
        
        if not self._graph.has_node(source) or not self._graph.has_node(target):
            return []

        try:
            paths = nx.all_simple_paths(
                self._graph, source=source, target=target,
                cutoff=max_length,
            )
            result = []
            for path in paths:
                edges = []
                for i in range(len(path) - 1):
                    edge_data = self._graph.get_edge_data(path[i], path[i + 1])
                    if edge_data:
                        edges.append({
                            "source": path[i],
                            "target": path[i + 1],
                            "relation": edge_data[0].get("relation", "unknown"),
                        })
                result.append(edges)
            return result
        except (nx.NetworkXNoPath, nx.NodeNotFound):
            return []

    def get_stats(self) -> Dict[str, Any]:
        """Obtener estadisticas del grafo."""
        if not self._graph:
            return {"nodes": 0, "edges": 0, "types": {}}
        
        type_counts: Dict[str, int] = {}
        for _, data in self._graph.nodes(data=True):
            t = data.get("type", "unknown")
            type_counts[t] = type_counts.get(t, 0) + 1

        relation_counts: Dict[str, int] = {}
        for _, _, data in self._graph.edges(data=True):
            r = data.get("relation", "unknown")
            relation_counts[r] = relation_counts.get(r, 0) + 1

        return {
            "nodes": self._graph.number_of_nodes(),
            "edges": self._graph.number_of_edges(),
            "types": type_counts,
            "relations": relation_counts,
        }

    def search_by_metadata(
        self,
        key: str,
        value: Any,
        node_type: Optional[str] = None,
    ) -> List[str]:
        """
        Buscar nodos por metadatos.
        
        Args:
            key: Clave del metadata.
            value: Valor a buscar.
            node_type: Filtrar por tipo de nodo.
            
        Returns:
            Lista de IDs de nodos que coinciden.
        """
        results = []
        for node, data in self._graph.nodes(data=True):
            if node_type and data.get("type") != node_type:
                continue
            if data.get("metadata", {}).get(key) == value:
                results.append(node)
        return results

    # ------------------------------------------------------------------
    # Persistencia
    # ------------------------------------------------------------------

    def save(self, path: Optional[Path] = None) -> None:
        """
        Guardar el grafo a JSON.
        
        Args:
            path: Ruta del archivo. Si no se especifica, usa la del constructor.
        """
        save_path = path or self._path
        if not save_path:
            logger.warning("No save path specified")
            return

        import networkx as nx
        from networkx.readwrite import json_graph

        data = json_graph.node_link_data(self._graph)
        save_path.parent.mkdir(parents=True, exist_ok=True)
        save_path.write_text(
            json.dumps(data, indent=2, ensure_ascii=False, default=str),
            encoding="utf-8",
        )
        logger.info(f"Knowledge graph saved: {save_path} ({self._graph.number_of_nodes()} nodes)")

    def load(self, path: Optional[Path] = None) -> bool:
        """
        Cargar el grafo desde JSON.
        
        Args:
            path: Ruta del archivo.
            
        Returns:
            True si se cargo correctamente.
        """
        load_path = path or self._path
        if not load_path or not load_path.exists():
            return False

        import networkx as nx
        from networkx.readwrite import json_graph

        try:
            data = json.loads(load_path.read_text(encoding="utf-8"))
            self._graph = json_graph.node_link_graph(data, multigraph=True)
            logger.info(f"Knowledge graph loaded: {load_path} ({self._graph.number_of_nodes()} nodes)")
            return True
        except Exception as e:
            logger.warning(f"Failed to load knowledge graph: {e}")
            self._load_networkx()
            return False

    # ------------------------------------------------------------------
    # Metodos de ayuda para poblar el grafo
    # ------------------------------------------------------------------

    def seed_from_skills(self, skills_dir: Path) -> int:
        """
        Poblar el grafo desde los skills en .opencode/skills/.
        
        Conecta cada skill con los agentes que pueden usarlo.
        
        Args:
            skills_dir: Directorio con los skills.
            
        Returns:
            Numero de conexiones creadas.
        """
        # Mapa de skill -> agente primario
        skill_agent = {
            "alpha-research": "scientist",
            "architecture": "scientist",
            "behavioral-economics": "scientist",
            "business-strategy": "coordinator",
            "communication": "builder",
            "creative-design": "builder",
            "data-science": "scientist",
            "devops-infra": "builder",
            "education": "evolve",
            "ethics": "guardian",
            "evolve": "evolve",
            "frontend-uiux": "builder",
            "healthtech": "builder",
            "hedgefund": "scientist",
            "legal-doc": "scientist",
            "linguistics": "scientist",
            "math-doc": "scientist",
            "physical-sciences": "scientist",
            "pos-retail": "builder",
            "project-management": "coordinator",
            "psychology": "scientist",
            "quant-trading": "scientist",
            "responsive-ui": "builder",
            "risk-execution": "guardian",
            "rust-lang": "builder",
            "science-doc": "scientist",
            "security-audit": "guardian",
            "sociology": "scientist",
            "sustainability": "scientist",
        }

        count = 0
        for skill_name, agent in skill_agent.items():
            self.add_node(f"skill:{skill_name}", "skill")
            self.add_node(f"agent:{agent}", "agent")
            self.connect(f"agent:{agent}", f"skill:{skill_name}", "uses")
            count += 1

        return count

    def seed_from_adrs(self, adrs_dir: Path) -> int:
        """
        Poblar el grafo desde los ADRs en docs/src/adr/.
        
        Args:
            adrs_dir: Directorio con los ADRs.
            
        Returns:
            Numero de conexiones creadas.
        """
        count = 0
        if not adrs_dir.exists():
            return 0

        for adr_file in sorted(adrs_dir.glob("ADR-*.md")):
            adr_id = adr_file.stem.lower()
            self.add_node(f"adr:{adr_id}", "adr")
            
            content = adr_file.read_text(encoding="utf-8", errors="replace")
            
            # Conectar con skills mencionados
            for skill in self._extract_skills(content):
                self.add_node(f"skill:{skill}", "skill")
                self.connect(f"adr:{adr_id}", f"skill:{skill}", "references")
                count += 1

        return count

    def _extract_skills(self, text: str) -> List[str]:
        """Extraer nombres de skills mencionados en un texto."""
        known_skills = [
            "alpha-research", "architecture", "data-science", "evolve",
            "frontend-uiux", "healthtech", "hedgefund", "legal-doc",
            "math-doc", "pos-retail", "quant-trading", "responsive-ui",
            "risk-execution", "rust-lang", "science-doc", "security-audit",
            "business-strategy", "communication", "creative-design",
            "devops-infra", "education", "ethics", "linguistics",
            "physical-sciences", "project-management", "psychology",
            "sociology", "sustainability", "behavioral-economics",
            "cache-shape", "structured-compact", "scoped-context",
        ]
        return [s for s in known_skills if s in text.lower()]
