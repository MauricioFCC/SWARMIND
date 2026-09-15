"""Tests para rag_evaluator + action-first + sandbox_executor + turbovec (ADR-0081).

Search 9-13-2026: regla de las 20 preguntas (clasifica retrieval/modelo/
tool), formato Action-First (1ra linea = accion, max 5 pasos, 0 relleno),
sandbox efimero (Docker si existe, subprocess si no; credenciales nunca en
contexto) y adapter turbovec experimental (graceful si falta el binario).
"""


from harness.memory_rag.rag_evaluator import (
    RAG_QUESTIONS,
    FailureKind,
    evaluate_question,
    evaluate_suite,
)
from harness.memory_rag.turbovec_adapter import (
    TurboVecAdapter,
)
from harness.memory_rag.turbovec_adapter import (
    is_available as turbovec_available,
)
from harness.orchestrator.structured_enforcer import action_first_instruction
from harness.validation.sandbox_executor import (
    SandboxExecutor,
    SandboxResult,
)


def _fake_retriever(docs):
    """Retriever fake con docs programados."""

    def _fn(query: str) -> list[str]:
        return docs

    return _fn


def test_suite_has_20_questions() -> None:
    """La suite fija tiene 20 preguntas representativas del dominio."""
    assert len(RAG_QUESTIONS) == 20
    assert all(isinstance(q, str) and q.strip() for q in RAG_QUESTIONS)


def test_evaluate_retrieval_failure() -> None:
    """Sin docs relevantes -> FailureKind.RETRIEVAL."""
    out = evaluate_question("quien creo el router", _fake_retriever([]))
    assert out.failure is FailureKind.RETRIEVAL
    assert out.retrieved == ()


def test_evaluate_ok_when_relevant() -> None:
    """Con docs relevantes y respuesta que los cita -> OK."""
    out = evaluate_question(
        "quien creo el router",
        _fake_retriever(["el router lo creo el coordinator"]),
        model_answer="el coordinator creo el router",
    )
    assert out.failure is FailureKind.NONE


def test_evaluate_model_ignored_evidence() -> None:
    """Respuesta que ignora la evidencia -> MODEL_IGNORED."""
    out = evaluate_question(
        "quien creo el router",
        _fake_retriever(["el router lo creo el coordinator"]),
        model_answer="no tengo informacion al respecto",
    )
    assert out.failure is FailureKind.MODEL_IGNORED


def test_evaluate_suite_aggregates() -> None:
    """La suite agrega conteos por tipo de fallo."""
    summary = evaluate_suite(
        RAG_QUESTIONS[:4],
        _fake_retriever([]),
    )
    assert summary.total == 4
    assert summary.by_kind[FailureKind.RETRIEVAL] == 4


def test_action_first_instruction_format() -> None:
    """La instruccion exige: 1ra linea accion, max 5 pasos, 0 relleno."""
    text = action_first_instruction()
    lowered = text.lower()
    assert "primera" in lowered and "acci" in lowered
    assert "5" in text
    assert "relleno" in lowered or "pre" in lowered


def test_sandbox_fallback_without_docker(monkeypatch) -> None:
    """Sin docker usa subprocess aislado (nunca crashea el harness)."""
    import shutil

    monkeypatch.setattr(shutil, "which", lambda _: None)
    ex = SandboxExecutor()
    assert ex.backend == "subprocess"
    out = ex.run(["python", "-c", "print(41+1)"])
    assert isinstance(out, SandboxResult)
    assert "42" in out.stdout
    assert out.returncode == 0


def test_sandbox_detects_docker(monkeypatch) -> None:
    """Con docker disponible el backend es docker."""
    import shutil

    monkeypatch.setattr(shutil, "which", lambda name: "/usr/bin/docker" if name == "docker" else None)
    ex = SandboxExecutor()
    assert ex.backend == "docker"


def test_sandbox_timeout_actionable() -> None:
    """Timeout accionable sin colgar (comando rapido que falla)."""
    ex = SandboxExecutor()
    out = ex.run(["python", "-c", "import sys; sys.exit(3)"], timeout_s=30.0)
    assert out.returncode == 3


def test_turbovec_unavailable_graceful(monkeypatch) -> None:
    """Sin binario turbovec: adapter no disponible, search retorna vacio."""
    import shutil

    monkeypatch.setattr(shutil, "which", lambda _: None)
    adapter = TurboVecAdapter()
    assert adapter.available is False
    assert turbovec_available() is False
    assert adapter.search("router", top_k=5) == []


def test_turbovec_allowlist_filters() -> None:
    """La allowlist restringe paths (documentos recientes/objetivo)."""
    from harness.memory_rag.turbovec_adapter import filter_allowlist

    paths = ["specs/a.md", "docs/viejo.md", "plan/b.md"]
    out = filter_allowlist(paths, allow=("specs/", "plan/"))
    assert out == ["specs/a.md", "plan/b.md"]
