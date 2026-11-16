"""test_token_budget_router.py — Tests del TokenBudgetRouter (ADR-0048)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from harness.context.token_budget_router import (
    _PR_CONVERGENCE_EPSILON,
    _PR_DAMPING,
    _PR_MAX_ITERATIONS,
    _PR_WEIGHT,
    _TFIDF_WEIGHT,
    DEFAULT_BUDGET_TOKENS,
    SelectionItem,
    SkillGraph,
    SkillNode,
    TokenBudgetRouter,
    _compute_idf,
    _normalize,
    _pagerank,
    _tfidf_scores,
    _tokenize,
    build_skill_graph,
)


def _oracle_pagerank(adjacency: dict[str, list[str]]) -> dict[str, float]:
    """Implementacion de referencia O(iter·n·e) congelada como oraculo."""
    nodes = list(adjacency)
    size = len(nodes)
    if size == 0:
        return {}
    ranks = {node_id: 1.0 / size for node_id in nodes}
    for _ in range(_PR_MAX_ITERATIONS):
        new_ranks: dict[str, float] = {}
        dangling = sum(
            ranks[node_id]
            for node_id, targets in adjacency.items()
            if not targets
        )
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


def _oracle_rank(graph: SkillGraph, query: str) -> dict[str, float]:
    """Rank de referencia sin precomputacion (comportamiento historico)."""
    node_ids = list(graph.nodes)
    if not node_ids:
        return {}
    docs = [_tokenize(graph.nodes[node_id].text) for node_id in node_ids]
    tfidf = _tfidf_scores(_tokenize(query), docs)
    pagerank = _oracle_pagerank(graph.adjacency())
    combined = {
        node_id: (
            _TFIDF_WEIGHT * tfidf[idx]
            + _PR_WEIGHT * pagerank.get(node_id, 0.0)
        )
        for idx, node_id in enumerate(node_ids)
    }
    return _normalize(combined)


@pytest.fixture
def mini_graph() -> SkillGraph:
    """Grafo minimo de 3 skills con aristas ENHANCES."""
    nodes = {
        "security-audit": SkillNode(
            skill_id="security-audit",
            text="auditoria seguridad OWASP threat modeling pentesting",
            tokens=120,
            domain="security",
        ),
        "devops-infra": SkillNode(
            skill_id="devops-infra",
            text="docker kubernetes terraform CI/CD despliegue",
            tokens=130,
            domain="devops",
        ),
        "data-science": SkillNode(
            skill_id="data-science",
            text="pandas numpy scikit-learn pipelines ML",
            tokens=140,
            domain="data",
        ),
    }
    edges = [("security-audit", "devops-infra", "ENHANCES")]
    return SkillGraph(nodes=nodes, edges=edges)


def test_tokenize_lowercases_and_filters() -> None:
    """Tokeniza en minusculas, solo alfanumericos."""
    assert _tokenize("Auditoria OWASP!") == ["auditoria", "owasp"]


def test_compute_idf_smoothing() -> None:
    """IDF usa log suavizado (terminos raros pesan mas)."""
    idf = _compute_idf([["a", "b"], ["a", "c"]])
    assert idf["a"] < idf["b"]
    assert idf["b"] == idf["c"]


def test_tfidf_scores_ranks_relevant_first() -> None:
    """El documento con terminos de la query puntua mas alto."""
    docs = [
        ["seguridad", "owasp"],
        ["docker", "kubernetes"],
        ["pandas", "numpy"],
    ]
    scores = _tfidf_scores(["seguridad", "owasp"], docs)
    assert scores[0] > scores[1]
    assert scores[0] > scores[2]


def test_pagerank_converges_and_normalizes() -> None:
    """PageRank converge, suma 1 y premia nodos con mas conexiones."""
    adjacency = {
        "a": ["b", "c"],
        "b": ["c"],
        "c": [],
    }
    ranks = _pagerank(adjacency)
    assert ranks
    assert abs(sum(ranks.values()) - 1.0) < 1e-6
    assert ranks["c"] > ranks["b"]


def test_pagerank_empty_adjacency() -> None:
    """Sin nodos devuelve dict vacio."""
    assert _pagerank({}) == {}


def test_normalize_maps_to_unit_range() -> None:
    """Normaliza al rango [0, 1] por maximo."""
    normalized = _normalize({"a": 2.0, "b": 1.0})
    assert normalized["a"] == 1.0
    assert normalized["b"] == 0.5


def test_normalize_all_zeros() -> None:
    """Si todos los scores son 0 devuelve 0 para todos."""
    assert _normalize({"a": 0.0, "b": 0.0}) == {"a": 0.0, "b": 0.0}


def test_rank_returns_normalized_scores(mini_graph: SkillGraph) -> None:
    """Rank combina TF-IDF y PageRank normalizados."""
    router = TokenBudgetRouter(mini_graph)
    scores = router.rank("seguridad owasp auditoria")
    assert set(scores) == {"security-audit", "devops-infra", "data-science"}
    assert 0.0 <= scores["security-audit"] <= 1.0
    assert scores["security-audit"] > scores["data-science"]


def test_rank_empty_graph() -> None:
    """Grafo vacio -> scores vacios."""
    router = TokenBudgetRouter(SkillGraph())
    assert router.rank("cualquier cosa") == {}


def test_select_never_exceeds_budget(mini_graph: SkillGraph) -> None:
    """Invariante: la suma de tokens nunca excede el presupuesto."""
    router = TokenBudgetRouter(mini_graph)
    for budget in (50, 120, 200, 400, DEFAULT_BUDGET_TOKENS):
        selected = router.select("seguridad", budget_tokens=budget)
        total = sum(item.tokens for item in selected)
        assert total <= budget


def test_select_returns_rationale(mini_graph: SkillGraph) -> None:
    """Cada item incluye rationale explicable (patron slurp)."""
    router = TokenBudgetRouter(mini_graph)
    selected = router.select("seguridad owasp", budget_tokens=300)
    assert selected
    for item in selected:
        assert isinstance(item, SelectionItem)
        assert "score=" in item.rationale
        assert "tokens=" in item.rationale


def test_select_orders_by_score_desc(mini_graph: SkillGraph) -> None:
    """La seleccion se ordena por score descendente."""
    router = TokenBudgetRouter(mini_graph)
    selected = router.select("seguridad owasp", budget_tokens=500)
    scores = [item.score for item in selected]
    assert scores == sorted(scores, reverse=True)


def test_select_invalid_budget_raises(mini_graph: SkillGraph) -> None:
    """Presupuesto no positivo -> ValueError."""
    router = TokenBudgetRouter(mini_graph)
    with pytest.raises(ValueError, match="WHAT:"):
        router.select("seguridad", budget_tokens=0)


def test_select_empty_graph() -> None:
    """Grafo vacio -> seleccion vacia."""
    router = TokenBudgetRouter(SkillGraph())
    assert router.select("x") == []


def test_graph_to_dict_roundtrip(mini_graph: SkillGraph) -> None:
    """Serializacion a dict y reconstruccion preservan estructura."""
    raw = mini_graph.to_dict()
    assert len(raw["nodes"]) == 3
    assert len(raw["edges"]) == 1
    rebuilt = SkillGraph.from_dict(raw)
    assert set(rebuilt.nodes) == set(mini_graph.nodes)
    assert rebuilt.edges == mini_graph.edges


def test_graph_from_dict_invalid_raises() -> None:
    """Formato invalido -> TypeError (tipo invalido, regla TRY004)."""
    with pytest.raises(TypeError, match="WHAT:"):
        SkillGraph.from_dict({"version": 1})


def test_build_skill_graph_from_disk(tmp_path: Path) -> None:
    """Construye el grafo desde un directorio con skills reales."""
    skills_dir = tmp_path / "skills"
    skills_dir.mkdir()
    skill_a = skills_dir / "alpha-research"
    skill_a.mkdir()
    (skill_a / "SKILL.md").write_text(
        "---\nname: alpha-research\ndomain: quant\nversion: 1.0.0\n---\n"
        "# Alpha Research\n\nfactores alpha ML backtesting",
        encoding="utf-8",
    )
    (skill_a / "SKILL.min.md").write_text(
        "factores alpha ML backtesting feature engineering", encoding="utf-8"
    )
    graph = build_skill_graph(skills_dir)
    assert "alpha-research" in graph.nodes
    assert graph.nodes["alpha-research"].tokens >= 10
    assert graph.nodes["alpha-research"].domain == "quant"


def test_build_skill_graph_invalid_dir(tmp_path: Path) -> None:
    """Directorio inexistente -> ValueError."""
    with pytest.raises(ValueError, match="WHAT:"):
        build_skill_graph(tmp_path / "no-existe")


def test_save_graph_writes_json(tmp_path: Path, mini_graph: SkillGraph) -> None:
    """save_graph persiste JSON portable valido."""
    router = TokenBudgetRouter(mini_graph)
    output = tmp_path / "graph.json"
    router.save_graph(output)
    raw = json.loads(output.read_text(encoding="utf-8"))
    assert len(raw["nodes"]) == 3


@pytest.mark.parametrize(
    "adjacency",
    [
        {"a": ["b", "c"], "b": ["c"], "c": []},
        {"a": ["b", "b"], "b": ["c"], "c": [], "d": ["a"]},
        {
            "a": ["b", "c", "d"],
            "b": ["d"],
            "c": ["a"],
            "d": [],
            "e": ["a", "d"],
        },
    ],
)
def test_pagerank_equivalente_al_oraculo(adjacency: dict[str, list[str]]) -> None:
    """La version O(n+e) reproduce el oraculo O(n·e) (tol 1e-12)."""
    optimized = _pagerank(adjacency)
    oracle = _oracle_pagerank(adjacency)
    assert optimized.keys() == oracle.keys()
    for node_id, value in oracle.items():
        assert optimized[node_id] == pytest.approx(value, abs=1e-12)


def test_rank_equivalente_al_oraculo(mini_graph: SkillGraph) -> None:
    """rank() precomputado reproduce el calculo completo por query."""
    router = TokenBudgetRouter(mini_graph)
    for query in ("seguridad owasp", "docker kubernetes", "pandas ML", "nada"):
        optimized = router.rank(query)
        oracle = _oracle_rank(mini_graph, query)
        assert optimized.keys() == oracle.keys()
        for node_id, value in oracle.items():
            assert optimized[node_id] == pytest.approx(value, abs=1e-12)


def test_pagerank_se_calcula_una_vez(mini_graph: SkillGraph, monkeypatch) -> None:
    """El router precomputa PageRank en __init__ y no lo repite por query."""
    import harness.context.token_budget_router as router_module

    calls = {"n": 0}
    original = router_module._pagerank

    def counting(adjacency):
        calls["n"] += 1
        return original(adjacency)

    monkeypatch.setattr(router_module, "_pagerank", counting)
    router = TokenBudgetRouter(mini_graph)
    assert calls["n"] == 1
    router.rank("seguridad")
    router.rank("docker")
    assert calls["n"] == 1


def test_build_skill_graph_lee_una_vez_por_archivo(
    tmp_path: Path, monkeypatch
) -> None:
    """Cada SKILL.md/SKILL.min.md se lee como maximo una vez por construccion."""
    skills_dir = tmp_path / "skills"
    skills_dir.mkdir()
    for name in ("alpha", "beta", "gamma"):
        skill_dir = skills_dir / name
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text(
            f"---\nname: {name}\ndomain: test\n---\n# {name}\n{name}",
            encoding="utf-8",
        )
        (skill_dir / "SKILL.min.md").write_text(
            f"{name} skill texto", encoding="utf-8"
        )

    reads: list[str] = []
    original = Path.read_text

    def counting(self, *args, **kwargs):
        reads.append(str(self))
        return original(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", counting)
    graph = build_skill_graph(skills_dir)
    assert set(graph.nodes) == {"alpha", "beta", "gamma"}
    assert len(reads) == len(set(reads)), f"lecturas duplicadas: {reads}"
    assert len(reads) == 6