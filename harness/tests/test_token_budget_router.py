"""test_token_budget_router.py — Tests del TokenBudgetRouter (ADR-0048)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from harness.context.token_budget_router import (
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
    """Formato invalido -> ValueError."""
    with pytest.raises(ValueError, match="WHAT:"):
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