"""test_llm_grep.py — Tests del grep frontera para LLMs (ADR-0067).

Verifica: lexical-first sin escalado, escalado a semantica cuando
lexical vacio, capa estructural condicional, dedup (path,line),
presupuesto max_hits/max_bytes, validacion fail-fast y reporte de
routing con alerta de misrouting semantico.
"""

from pathlib import Path

import pytest

from harness.memory_rag.llm_grep import (
    GrepBudget,
    GrepHit,
    LlmGrep,
    NoopStructuralBackend,
    apply_budget,
    dedup_hits,
    hybrid_to_hits_adapter,
    is_structural_query,
)


class _FakeLexical:
    """Backend lexical falso con hits programados."""

    def __init__(self, hits: list[GrepHit]) -> None:
        self._hits = hits
        self.calls = 0

    def search(self, pattern: str, root: Path, top_k: int) -> list[GrepHit]:
        """Retorna hits programados y cuenta llamadas."""
        self.calls += 1
        return self._hits[:top_k]


class _FakeSemantic:
    """Backend semantico falso con hits programados."""

    def __init__(self, hits: list[GrepHit]) -> None:
        self._hits = hits
        self.calls = 0

    def search(self, query: str, top_k: int) -> list[GrepHit]:
        """Retorna hits programados y cuenta llamadas."""
        self.calls += 1
        return self._hits[:top_k]


def _hit(path: str, line: int, preview: str = "x = 1") -> GrepHit:
    """Crea un GrepHit de prueba."""
    return GrepHit(path=path, line=line, col=1, preview=preview)


def test_lexical_first_no_escalation() -> None:
    """Lexical con hits no escala a semantica."""
    lexical = _FakeLexical([_hit("a.py", 1)])
    semantic = _FakeSemantic([_hit("b.py", 2)])
    grep = LlmGrep(root=Path("."), lexical=lexical, semantic=semantic)
    hits, report = grep.search("x = 1")
    assert report.backend == "lexical"
    assert semantic.calls == 0
    assert len(hits) == 1


def test_escalates_to_semantic_when_lexical_empty() -> None:
    """Lexical vacio escala a semantica (ultimo recurso)."""
    lexical = _FakeLexical([])
    semantic = _FakeSemantic([_hit("b.py", 2)])
    grep = LlmGrep(root=Path("."), lexical=lexical, semantic=semantic)
    hits, report = grep.search("concepto difuso sin literal")
    assert report.backend == "semantic"
    assert semantic.calls == 1
    assert len(hits) == 1


def test_no_semantic_returns_lexical_empty() -> None:
    """Sin backend semantico retorna lexical aunque este vacio."""
    grep = LlmGrep.lexical_only(root=Path("."), budget=GrepBudget())
    grep._lexical = _FakeLexical([])
    hits, report = grep.search("nada")
    assert hits == []
    assert report.backend == "lexical"


def test_structural_only_when_query_structural() -> None:
    """Capa estructural solo se consulta con query estructural."""

    class _Struct:
        def __init__(self) -> None:
            self.calls = 0

        def search(self, pattern: str, root: Path, top_k: int) -> list[GrepHit]:
            """Cuenta llamadas y retorna un hit."""
            self.calls += 1
            return [_hit("c.py", 3)]

    struct = _Struct()
    grep = LlmGrep(
        root=Path("."), lexical=_FakeLexical([]), structural=struct, semantic=None
    )
    _, report = grep.search("class Foo")
    assert struct.calls == 1
    assert report.backend == "structural"
    grep2 = LlmGrep(
        root=Path("."), lexical=_FakeLexical([]), structural=struct, semantic=None
    )
    struct.calls = 0
    _, report2 = grep2.search("texto libre sin keywords")
    assert struct.calls == 0
    assert report2.backend == "lexical"


def test_dedup_by_path_line() -> None:
    """Dedup elimina repetidos (path,line) preservando orden."""
    hits = [_hit("a.py", 1), _hit("a.py", 1, "otro"), _hit("a.py", 2)]
    unique = dedup_hits(hits)
    assert [(h.path, h.line) for h in unique] == [("a.py", 1), ("a.py", 2)]


def test_budget_caps_hits_and_bytes() -> None:
    """Budget recorta por max_hits y max_bytes."""
    hits = [_hit("a.py", i, preview="y" * 10) for i in range(10)]
    capped = apply_budget(hits, GrepBudget(max_hits=3, max_bytes=10**9))
    assert len(capped) == 3
    capped_bytes = apply_budget(hits, GrepBudget(max_hits=10, max_bytes=25))
    assert len(capped_bytes) == 2


def test_empty_query_raises() -> None:
    """Query vacia falla con ValueError accionable."""
    grep = LlmGrep.lexical_only(root=Path("."))
    with pytest.raises(ValueError, match="WHAT"):
        grep.search("   ")


def test_invalid_top_k_raises() -> None:
    """top_k no positivo falla con ValueError accionable."""
    grep = LlmGrep.lexical_only(root=Path("."))
    with pytest.raises(ValueError, match="WHAT"):
        grep.search("x", top_k=0)


def test_is_structural_query() -> None:
    """Detector estructural reconoce definiciones y rechaza texto libre."""
    assert is_structural_query("def retrieve") is True
    assert is_structural_query("class Foo") is True
    assert is_structural_query("donde se usa el login") is False


def test_noop_structural_empty() -> None:
    """Backend no-op retorna vacio siempre."""
    assert NoopStructuralBackend().search("class X", Path("."), 5) == []


def test_hybrid_adapter_normalizes() -> None:
    """Adaptador convierte items hibridos a GrepHit."""
    backend = hybrid_to_hits_adapter(
        lambda q, k: [{"id": "doc1", "metadata": {"path": "m.py", "preview": "hola"}}]
    )
    hits = backend.search("q", 5)
    assert hits[0].path == "m.py"
    assert hits[0].preview == "hola"


def test_semantic_ratio_warning() -> None:
    """Uso semantico repetido activa alerta de misrouting."""
    grep = LlmGrep(
        root=Path("."),
        lexical=_FakeLexical([]),
        semantic=_FakeSemantic([_hit("s.py", 9)]),
    )
    for _ in range(3):
        _, report = grep.search("concepto")
    assert report.semantic_ratio == pytest.approx(1.0)
    assert report.semantic_warning is True
