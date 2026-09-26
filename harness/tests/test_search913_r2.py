"""Tests para session_snapshot + docs_gate + wiring affinity (Search 9-13 R2, ADR-0082).

Frontera: Scroll (arXiv 2608.21690: estado completo fuera del contexto,
working view acotada) + ACM (manage_context: resume + offload raw a disco;
query_memory). Fase 2 del doc: task_planner exige PLAN.md/AGENTS.md/ADR
actualizados antes de aprobar codigo. Y session_affinity enchufado en
ModelRouter (antes sin callers productivos).
"""


import pytest

from harness.memory_rag.session_snapshot import (
    ESSENTIAL_MAX_CHARS,
    SessionSnapshotter,
    save_snapshot,
)
from harness.model_router.router import ModelRouter
from harness.validation.docs_gate import (
    DOC_LIVING_FILES,
    check_docs_fresh,
)


def _big_state(n_turns: int = 40) -> dict:
    """Fabrica un estado de sesion grande (>5KB)."""
    return {
        "task": "implementar endpoint",
        "turns": [
            {"i": i, "tool": "bash", "output": "x" * 400, "summary": f"turno {i}"}
            for i in range(n_turns)
        ],
        "facts": [f"hecho {i}" for i in range(10)],
    }


def test_save_returns_handle_and_bounded_view() -> None:
    """save() persiste el estado completo y retorna vista acotada ≤5KB."""
    snap = SessionSnapshotter(cache_dir=None)
    out = snap.save(_big_state())
    assert out.handle
    assert len(out.view.encode("utf-8")) <= ESSENTIAL_MAX_CHARS
    assert "implementar endpoint" in out.view


def test_restore_roundtrip(tmp_path) -> None:
    """restore(handle) devuelve el estado byte-exacto."""
    snap = SessionSnapshotter(cache_dir=tmp_path)
    state = _big_state()
    out = snap.save(state)
    assert snap.restore(out.handle) == state


def test_restore_unknown_handle_raises() -> None:
    """Handle inexistente falla accionable."""
    snap = SessionSnapshotter(cache_dir=None)
    with pytest.raises(FileNotFoundError, match="WHAT"):
        snap.restore("no-existe-0000")


def test_essential_max_documented() -> None:
    """La vista esencial esta acotada a 5KB (context-mode)."""
    assert ESSENTIAL_MAX_CHARS == 5 * 1024


def test_save_function_convenience(tmp_path) -> None:
    """La funcion save_snapshot() es atajo con dir default."""
    out = save_snapshot({"a": 1})
    assert out.handle


def test_docs_gate_passes_with_plan_updated(tmp_path) -> None:
    """Repo con PLAN.md modificado -> PASS (docs vivas)."""
    import subprocess

    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.email", "t@t"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=tmp_path, check=True)
    (tmp_path / "PLAN.md").write_text("plan", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-qm", "init"], cwd=tmp_path, check=True)
    (tmp_path / "PLAN.md").write_text("plan v2", encoding="utf-8")
    report = check_docs_fresh(tmp_path)
    assert report.passed is True
    assert "PLAN.md" in report.updated


def test_docs_gate_fails_without_docs_update(tmp_path) -> None:
    """Solo codigo modificado sin docs -> FAIL listando que falta."""
    import subprocess

    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.email", "t@t"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=tmp_path, check=True)
    (tmp_path / "code.py").write_text("x=1", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-qm", "init"], cwd=tmp_path, check=True)
    (tmp_path / "code.py").write_text("x=2", encoding="utf-8")
    report = check_docs_fresh(tmp_path)
    assert report.passed is False
    assert len(report.missing) > 0


def test_docs_gate_not_a_repo_ok() -> None:
    """Directorio sin git -> SKIP pass (no bloquea fuera de repos)."""
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        from pathlib import Path

        report = check_docs_fresh(Path(tmp))
        assert report.passed is True
        assert report.skipped is True


def test_living_files_cover_plan_agents_adr() -> None:
    """Los archivos vivos incluyen PLAN/AGENTS/SPECS/ADR (docs vivas)."""
    joined = " ".join(DOC_LIVING_FILES)
    for name in ("PLAN.md", "AGENTS.md", "SPECS.md", "ADR"):
        assert name in joined


def test_router_affinity_sticky(tmp_path=None) -> None:
    """ModelRouter con affinity: 2da tarea misma sesion reusa sin re-decidir."""
    from harness.model_router.session_affinity import SessionAffinityRouter

    calls: list[str] = []

    def decide(task: str) -> str:
        calls.append(task)
        return "small"

    router = ModelRouter()
    router.attach_affinity(SessionAffinityRouter(decide))
    r1 = router.route("resume esto", session_id="s1")
    r2 = router.route("otra tarea simple", session_id="s1")
    assert r1.model_route.route == r2.model_route.route == "small"
    assert len(calls) == 1  # segunda servida por afinidad


def test_router_without_affinity_unchanged() -> None:
    """Sin attach_affinity el comportamiento no cambia (compat)."""
    router = ModelRouter()
    assert not hasattr(router, "_affinity") or router._affinity is None
    r = router.route("resume esto")
    assert r.model_route.route == "small"
