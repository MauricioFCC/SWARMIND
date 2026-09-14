"""Tests para tool_pruner + cross_review (Search 9-13-2026, ADR-0081).

Frontera: eliminar el 80% de herramientas sube exito 80->100%, tokens a la
mitad, latencia 724s->141s. El task_planner genera allowed_tools (max 3-4)
por tipo de tarea. Y revision cruzada forzada: el revisor DEBE ser de
familia distinta al escritor (Claude->GPT/Ollama: perspectivas distintas).
"""

import pytest

from harness.orchestrator.tool_pruner import (
    MAX_TOOLS,
    ToolPruner,
    prune_tools,
)
from harness.validation.cross_review import (
    CrossReviewer,
    assign_reviewer,
)


def test_prune_limits_to_max_tools() -> None:
    """La poda deja como maximo MAX_TOOLS (3-4) herramientas."""
    pruner = ToolPruner()
    out = pruner.prune("implementa el endpoint", ["read", "edit", "bash", "grep", "web", "db"])
    assert len(out.allowed) <= MAX_TOOLS
    assert out.pruned_count == 6 - len(out.allowed)


def test_prune_keeps_task_relevant() -> None:
    """Tarea de codigo conserva edit/read; tarea de investigacion conserva web/grep."""
    pruner = ToolPruner()
    code = pruner.prune("implementa el modulo", ["read", "edit", "bash", "web"])
    assert "edit" in code.allowed
    research = pruner.prune("investiga papers de RL", ["read", "edit", "bash", "web"])
    assert "web" in research.allowed


def test_prune_empty_task_raises() -> None:
    """Tarea vacia falla accionable."""
    with pytest.raises(ValueError, match="WHAT"):
        prune_tools("", ["read"])


def test_max_tools_constant() -> None:
    """MAX_TOOLS documentado en 3-4."""
    assert 3 <= MAX_TOOLS <= 4


def test_family_map_covers_main_families() -> None:
    """El mapa cubre claude/gpt/ollama/qwen/deepseek/llama/mistral."""
    from harness.validation.cross_review import model_family

    assert model_family("claude-opus") == "claude"
    assert model_family("gpt-4o") == "gpt"
    assert model_family("qwen3:4b") == "ollama"
    assert model_family("deepseek-r1:8b") == "ollama"
    assert model_family("llama3.2:3b") == "ollama"
    assert model_family("mistral-large") == "ollama"


def test_assign_reviewer_forces_different_family() -> None:
    """Escritor claude -> revisor NO claude (gpt u ollama)."""
    reviewer = assign_reviewer("claude-opus", available=["claude-haiku", "gpt-4o", "qwen3:4b"])
    assert reviewer != "claude-haiku"
    assert reviewer in ("gpt-4o", "qwen3:4b")


def test_assign_reviewer_prefers_local() -> None:
    """Entre familias distintas prefiere local (0 tokens cloud)."""
    reviewer = assign_reviewer("gpt-4o", available=["claude-opus", "qwen2.5-coder:7b"])
    assert reviewer == "qwen2.5-coder:7b"


def test_assign_reviewer_no_alternative_raises() -> None:
    """Sin revisor de otra familia falla accionable (no auto-revision)."""
    with pytest.raises(ValueError, match="WHAT"):
        assign_reviewer("claude-opus", available=["claude-haiku"])


def test_cross_reviewer_records_pair() -> None:
    """CrossReviewer registra el par escritor->revisor con familias."""
    rev = CrossReviewer()
    pair = rev.assign("claude-opus", ["gpt-4o", "qwen3:4b"])
    assert pair.writer_family == "claude"
    assert pair.reviewer_family in ("gpt", "ollama")
    assert pair.reviewer_family != "claude"
