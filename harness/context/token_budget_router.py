"""token_budget_router.py — Navegacion de grafo consciente del presupuesto (ADR-0048).

Implementa la metodologia ``slurp`` adaptada a SWARMIND: puntua los nodos
del grafo de conocimiento de skills con TF-IDF + PageRank estructural
(cero llamadas LLM en el ranking) y selecciona un subgrafo optimo que
nunca exceda un presupuesto de tokens estricto.

El grafo de skills se serializa en ``swarmind-skills-graph.json`` con
nodos (skills) y aristas tipadas: ``REQUIRED_SUB_SKILL``, ``CONFLICTS_WITH``
y ``ENHANCES``. La divulgacion progresiva inyecta el cuerpo completo del
skill (``--inject-spec``) solo si el nodo supera un umbral de relevancia
y el presupuesto lo permite.

Uso (CLI):
    python -m harness.context.token_budget_router --query "auditoria de seguridad" --budget 4000
    python -m harness.context.token_budget_router --build-graph --output swarmind-skills-graph.json

Referencia: CarlosVallejoRuiz/slurp — ahorros medios 93.3% (hasta 97.1%).
"""

from __future__ import annotations

import argparse
import json
import math
import re
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from harness.common import estimate_tokens

# ---------------------------------------------------------------------------
# Constantes (MAG)
# ---------------------------------------------------------------------------
DEFAULT_BUDGET_TOKENS = 4000
GRAPH_FILENAME = "swarmind-skills-graph.json"
_EDGE_REQUIRED_SUB_SKILL = "REQUIRED_SUB_SKILL"
_EDGE_CONFLICTS_WITH = "CONFLICTS_WITH"
_EDGE_ENHANCES = "ENHANCES"
_EDGE_TYPES = (_EDGE_REQUIRED_SUB_SKILL, _EDGE_CONFLICTS_WITH, _EDGE_ENHANCES)

# PageRank puro (stdlib)
_PR_DAMPING = 0.85
_PR_MAX_ITERATIONS = 100
_PR_CONVERGENCE_EPSILON = 1e-6

# Ponderacion del score combinado
_TFIDF_WEIGHT = 0.5
_PR_WEIGHT = 0.5

# Minimo de tokens que un nodo debe aportar para no descartarse como ruido
_MIN_NODE_TOKENS = 10

_TOKEN_RE = re.compile(r"[a-z0-9]+")
_SKILL_REF_RE = re.compile(r"([a-z0-9]+(?:-[a-z0-9]+)+)")


@dataclass(frozen=True)
class SkillNode:
    """Nodo del grafo de conocimiento de skills.

    Attributes:
        skill_id: Identificador unico del nodo (nombre del skill).
        text: Texto indexable del skill (SKILL.min.md + frontmatter).
        tokens: Costo estimado de inyectar el skill completo.
        domain: Dominio del skill (para agrupar en el grafo).
    """

    skill_id: str
    text: str
    tokens: int
    domain: str = "general"


@dataclass(frozen=True)
class SelectionItem:
    """Item del subgrafo seleccionado (explicable por nodo).

    Attributes:
        skill_id: Identificador del skill seleccionado.
        score: Relevancia combinada (TF-IDF + PageRank normalizados).
        tokens: Tokens estimados del nodo.
        rationale: Justificacion textual de la seleccion.
    """

    skill_id: str
    score: float
    tokens: int
    rationale: str


@dataclass(frozen=True)
class SkillGraph:
    """Grafo de conocimiento de skills.

    Attributes:
        nodes: Mapa skill_id -> SkillNode.
        edges: Lista de aristas tipadas (source, target, edge_type).
    """

    nodes: dict[str, SkillNode] = field(default_factory=dict)
    edges: list[tuple[str, str, str]] = field(default_factory=list)

    def adjacency(self) -> dict[str, list[str]]:
        """Construye lista de adyacencia (source -> targets) para PageRank.

        Returns:
            Dict con una lista de vecinos por nodo presente en el grafo.
        """
        adjacency: dict[str, list[str]] = {node_id: [] for node_id in self.nodes}
        for source, target, _edge_type in self.edges:
            if source in adjacency and target in self.nodes and target != source:
                adjacency[source].append(target)
        return adjacency

    def to_dict(self) -> dict[str, object]:
        """Serializa el grafo a dict JSON portable.

        Returns:
            Dict con nodos, aristas y metadatos.
        """
        return {
            "version": 1,
            "nodes": [
                {
                    "id": node.skill_id,
                    "domain": node.domain,
                    "tokens": node.tokens,
                }
                for node in self.nodes.values()
            ],
            "edges": [
                {"source": source, "target": target, "type": edge_type}
                for source, target, edge_type in self.edges
            ],
        }

    @classmethod
    def from_dict(cls, raw: dict[str, object]) -> SkillGraph:
        """Reconstruye un SkillGraph desde un dict JSON.

        Args:
            raw: Dict producido por ``to_dict``.

        Returns:
            SkillGraph reconstruido (sin textos, solo estructura).

        Raises:
            TypeError: Si el formato no es el esperado (faltan listas nodes/edges).
        """
        if not isinstance(raw.get("nodes"), list) or not isinstance(raw.get("edges"), list):
            raise TypeError(
                "WHAT: formato de grafo invalido"
                "WHY: faltan listas 'nodes'/'edges'"
                "WHERE: SkillGraph.from_dict()"
            )
        nodes = {}
        for node in raw["nodes"]:
            if not isinstance(node, dict) or "id" not in node:
                continue
            nodes[str(node["id"])] = SkillNode(
                skill_id=str(node["id"]),
                text="",
                tokens=int(node.get("tokens", 0)),
                domain=str(node.get("domain", "general")),
            )
        edges = []
        for edge in raw["edges"]:
            if not isinstance(edge, dict):
                continue
            edge_type = str(edge.get("type", _EDGE_ENHANCES))
            if edge_type not in _EDGE_TYPES:
                edge_type = _EDGE_ENHANCES
            edges.append((str(edge["source"]), str(edge["target"]), edge_type))
        return cls(nodes=nodes, edges=edges)


# ---------------------------------------------------------------------------
# Construccion del grafo
# ---------------------------------------------------------------------------


def _skill_text(skill_dir: Path) -> str:
    """Compone el texto indexable de un skill (min.md + frontmatter).

    Args:
        skill_dir: Directorio del skill.

    Returns:
        Texto combinado para TF-IDF (SKILL.min.md si existe, si no SKILL.md).
    """
    min_path = skill_dir / "SKILL.min.md"
    full_path = skill_dir / "SKILL.md"
    source = min_path if min_path.exists() else full_path
    return source.read_text(encoding="utf-8", errors="replace") if source.exists() else ""


def _skill_domain(skill_dir: Path) -> str:
    """Extrae el dominio del frontmatter del skill.

    Args:
        skill_dir: Directorio del skill.

    Returns:
        Dominio declarado o 'general'.
    """
    fm_path = skill_dir / "SKILL.md"
    if not fm_path.exists():
        return "general"
    text = fm_path.read_text(encoding="utf-8", errors="replace")
    match = re.match(r"^---\n(.*?)\n---", text, re.DOTALL)
    if not match:
        return "general"
    for line in match.group(1).splitlines():
        if line.startswith("domain:"):
            return line.partition(":")[2].strip().strip('"').strip("'") or "general"
    return "general"


def _edges_from_text(skill_dir: Path, skill_id: str) -> list[tuple[str, str, str]]:
    """Deriva aristas ENHANCES al detectar menciones de otros skills.

    Args:
        skill_dir: Directorio del skill.
        skill_id: Nombre del skill fuente.

    Returns:
        Aristas (source, target, ENHANCES) para skills mencionados.
    """
    text = _skill_text(skill_dir)
    mentioned = {name for name in _SKILL_REF_RE.findall(text) if name != skill_id}
    return [(skill_id, name, _EDGE_ENHANCES) for name in sorted(mentioned)]


def build_skill_graph(skills_dir: Path) -> SkillGraph:
    """Construye el grafo de conocimiento desde el directorio de skills.

    Args:
        skills_dir: Directorio raiz de skills (.opencode/skills).

    Returns:
        SkillGraph con un nodo por skill y aristas derivadas.

    Raises:
        ValueError: Si el directorio no existe.
    """
    if not skills_dir.is_dir():
        raise ValueError(
            f"WHAT: directorio de skills inexistente: {skills_dir}"
            f"WHY: no se puede construir el grafo sin nodos"
            f"WHERE: build_skill_graph()"
        )
    nodes: dict[str, SkillNode] = {}
    edges: list[tuple[str, str, str]] = []
    for skill_dir in sorted(skills_dir.iterdir()):
        if not skill_dir.is_dir() or skill_dir.name.startswith("_"):
            continue
        text = _skill_text(skill_dir)
        if not text:
            continue
        skill_id = skill_dir.name
        nodes[skill_id] = SkillNode(
            skill_id=skill_id,
            text=text,
            tokens=max(_MIN_NODE_TOKENS, estimate_tokens(text)),
            domain=_skill_domain(skill_dir),
        )
        edges.extend(_edges_from_text(skill_dir, skill_id))
    return SkillGraph(nodes=nodes, edges=edges)


# ---------------------------------------------------------------------------
# Ranking: TF-IDF + PageRank (cero LLM)
# ---------------------------------------------------------------------------


def _tokenize(text: str) -> list[str]:
    """Tokeniza texto en minusculas (palabras alfanumericas).

    Args:
        text: Texto a tokenizar.

    Returns:
        Lista de tokens.
    """
    return _TOKEN_RE.findall(text.lower())


def _compute_idf(docs: list[list[str]]) -> dict[str, float]:
    """Calcula IDF (inverse document frequency) sobre el corpus.

    Args:
        docs: Lista de documentos tokenizados.

    Returns:
        Dict termino -> IDF (log suavizado).
    """
    doc_count = max(1, len(docs))
    df: Counter[str] = Counter()
    for doc in docs:
        df.update(set(doc))
    return {
        term: math.log((1 + doc_count) / (1 + freq)) + 1.0
        for term, freq in df.items()
    }


def _tfidf_scores(query: list[str], docs: list[list[str]]) -> list[float]:
    """Puntua cada documento por similitud coseno TF-IDF con la query.

    Args:
        query: Query tokenizada.
        docs: Documentos tokenizados del corpus.

    Returns:
        Score TF-IDF por documento (0 si sin coincidencia).
    """
    idf = _compute_idf(docs)
    query_tf = Counter(query)
    query_vec = {term: query_tf[term] * idf.get(term, 0.0) for term in query_tf}
    query_norm = math.sqrt(sum(value * value for value in query_vec.values()))
    scores: list[float] = []
    for doc in docs:
        doc_tf = Counter(doc)
        dot = sum(
            query_vec[term] * doc_tf[term] * idf.get(term, 0.0)
            for term in query_vec
            if term in doc_tf
        )
        doc_norm = math.sqrt(
            sum((doc_tf[term] * idf.get(term, 0.0)) ** 2 for term in doc_tf)
        )
        denom = max(query_norm * doc_norm, 1e-9)
        scores.append(dot / denom)
    return scores


def _pagerank(adjacency: dict[str, list[str]]) -> dict[str, float]:
    """PageRank estructural puro (power iteration, stdlib).

    Args:
        adjacency: Lista de adyacencia source -> targets.

    Returns:
        Dict nodo -> PageRank normalizado (suma = 1).
    """
    nodes = list(adjacency)
    size = len(nodes)
    if size == 0:
        return {}
    ranks = {node_id: 1.0 / size for node_id in nodes}
    for _ in range(_PR_MAX_ITERATIONS):
        new_ranks: dict[str, float] = {}
        dangling = sum(ranks[node_id] for node_id, targets in adjacency.items()
                       if not targets)
        for node_id in nodes:
            incoming = sum(
                ranks[source] / max(1, len(targets))
                for source, targets in adjacency.items()
                if node_id in targets
            )
            new_ranks[node_id] = (
                (1 - _PR_DAMPING) / size
                + _PR_DAMPING * (incoming + dangling / size)
            )
        delta = sum(abs(new_ranks[n] - ranks[n]) for n in nodes)
        ranks = new_ranks
        if delta < _PR_CONVERGENCE_EPSILON:
            break
    return ranks


def _normalize(scores: dict[str, float]) -> dict[str, float]:
    """Normaliza scores al rango [0, 1] por maximo.

    Args:
        scores: Dict nodo -> score bruto.

    Returns:
        Dict nodo -> score normalizado (0 si todos son 0).
    """
    max_value = max(scores.values(), default=0.0)
    if max_value <= 0.0:
        return {node_id: 0.0 for node_id in scores}
    return {node_id: value / max_value for node_id, value in scores.items()}


# ---------------------------------------------------------------------------
# Router
# ---------------------------------------------------------------------------


class TokenBudgetRouter:
    """Router de contexto que selecciona un subgrafo bajo presupuesto.

    Args:
        graph: Grafo de conocimiento de skills.
        token_estimator: Funcion de estimacion de tokens (SSOT common).
    """

    def __init__(
        self,
        graph: SkillGraph,
        token_estimator=estimate_tokens,
    ) -> None:
        self._graph = graph
        self._token_estimator = token_estimator

    def rank(self, query: str) -> dict[str, float]:
        """Puntua todos los nodos por relevancia combinada.

        Args:
            query: Consulta del usuario.

        Returns:
            Dict skill_id -> score combinado normalizado [0, 1].
        """
        node_ids = list(self._graph.nodes)
        if not node_ids:
            return {}
        docs = [_tokenize(self._graph.nodes[node_id].text) for node_id in node_ids]
        tfidf = _tfidf_scores(_tokenize(query), docs)
        adjacency = self._graph.adjacency()
        pagerank = _pagerank(adjacency)
        combined = {
            node_id: (
                _TFIDF_WEIGHT * tfidf[idx]
                + _PR_WEIGHT * pagerank.get(node_id, 0.0)
            )
            for idx, node_id in enumerate(node_ids)
        }
        return _normalize(combined)

    def select(self, query: str, budget_tokens: int = DEFAULT_BUDGET_TOKENS) -> list[SelectionItem]:
        """Selecciona el subgrafo optimo sin exceder el presupuesto.

        Algoritmo greedy (patron slurp): ordena nodos por score combinado
        descendente y los añade (con sus vecinos directos) mientras la
        estimacion acumulada no supere el presupuesto.

        Args:
            query: Consulta del usuario.
            budget_tokens: Presupuesto estricto de tokens (default 4000).

        Returns:
            Lista de SelectionItem ordenada por score (invariante: la suma
            de tokens nunca excede budget_tokens).

        Raises:
            ValueError: Si el presupuesto no es positivo.
        """
        if budget_tokens <= 0:
            raise ValueError(
                f"WHAT: presupuesto invalido: {budget_tokens}"
                f"WHY: debe ser un entero positivo"
                f"WHERE: TokenBudgetRouter.select()"
            )
        scores = self.rank(query)
        if not scores:
            return []
        adjacency = self._graph.adjacency()
        ordered = sorted(scores.items(), key=lambda item: item[1], reverse=True)
        selected: list[SelectionItem] = []
        used = 0
        visited: set[str] = set()
        for node_id, score in ordered:
            if node_id in visited:
                continue
            candidates = [node_id] + [
                neighbor for neighbor in adjacency.get(node_id, [])
                if neighbor not in visited
            ]
            for candidate in candidates:
                if candidate in visited:
                    continue
                node = self._graph.nodes[candidate]
                if used + node.tokens > budget_tokens:
                    continue
                neighbors = len(adjacency.get(candidate, []))
                rationale = (
                    f"score={score:.3f} tokens={node.tokens} "
                    f"vecinos={neighbors}"
                )
                selected.append(SelectionItem(
                    skill_id=candidate,
                    score=score,
                    tokens=node.tokens,
                    rationale=rationale,
                ))
                used += node.tokens
                visited.add(candidate)
        return sorted(selected, key=lambda item: item.score, reverse=True)

    def save_graph(self, output_path: Path) -> None:
        """Persiste el grafo como JSON portable.

        Args:
            output_path: Ruta de salida (swarmind-skills-graph.json).
        """
        output_path.write_text(
            json.dumps(self._graph.to_dict(), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )


def _cli() -> None:
    """CLI principal del router de presupuesto de tokens."""
    parser = argparse.ArgumentParser(
        description="Router de contexto con presupuesto de tokens (ADR-0048, metodologia slurp)"
    )
    parser.add_argument("--query", type=str, default="", help="Consulta del usuario")
    parser.add_argument("--budget", type=int, default=DEFAULT_BUDGET_TOKENS,
                        help="Presupuesto estricto de tokens")
    parser.add_argument("--build-graph", action="store_true",
                        help="Construye y guarda swarmind-skills-graph.json")
    parser.add_argument("--skills-dir", type=Path,
                        default=Path(".opencode/skills"),
                        help="Directorio raiz de skills")
    parser.add_argument("--output", type=Path, default=Path(GRAPH_FILENAME),
                        help="Ruta del grafo JSON de salida")
    args = parser.parse_args()

    graph = build_skill_graph(args.skills_dir)
    if args.build_graph:
        router = TokenBudgetRouter(graph)
        router.save_graph(args.output)
        print(f"Grafo guardado: {args.output} ({len(graph.nodes)} nodos, {len(graph.edges)} aristas)")
        return
    router = TokenBudgetRouter(graph)
    selected = router.select(args.query, args.budget)
    total = sum(item.tokens for item in selected)
    print(f"Query: {args.query!r} | Presupuesto: {args.budget} | Seleccion: {len(selected)} skills | Tokens: {total}")
    for item in selected:
        print(f"  - {item.skill_id:<24} score={item.score:.3f} tokens={item.tokens} [{item.rationale}]")


if __name__ == "__main__":
    _cli()