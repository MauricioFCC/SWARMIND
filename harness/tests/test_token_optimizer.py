"""Tests para TokenOptimizer — optimizacion de tokens y velocidad."""
from __future__ import annotations

import pytest

from harness.orchestrator.token_optimizer import (
    OutputFormat,
    PipelineTask,
    TokenBudgetManager,
    build_dag,
    estimate_speedup,
    structured_prompt,
)


class TestStructuredPrompt:
    """Prompt con formato estructurado."""
    
    def test_json_schema(self) -> None:
        """JSON Schema debe incluir schema en el prompt."""
        schema = {"type": "object", "properties": {"name": {"type": "string"}}}
        prompt = structured_prompt("Analiza esto", schema=schema)
        assert "```json" in prompt
        assert "name" in prompt
        assert "NO incluyas explicaciones" in prompt
    
    def test_markdown_format(self) -> None:
        """Markdown debe especificar formato markdown."""
        prompt = structured_prompt("Analiza esto", format=OutputFormat.MARKDOWN)
        assert "## para secciones" in prompt
    
    def test_free_text(self) -> None:
        """Free text debe ser conciso."""
        prompt = structured_prompt("Analiza esto", format=OutputFormat.FREE_TEXT)
        assert "concisa" in prompt
    
    def test_max_tokens(self) -> None:
        """Debe incluir max tokens en el prompt."""
        prompt = structured_prompt("test", max_tokens=300)
        assert "300" in prompt


class TestPipelineDAG:
    """Pipeline DAG con ejecucion paralela."""

    def test_simple_sequential(self) -> None:
        """Tareas secuenciales deben producir un nivel por tarea."""
        tasks = [
            PipelineTask("1", "builder", "Task 1"),
            PipelineTask("2", "builder", "Task 2", depends_on=["1"]),
            PipelineTask("3", "builder", "Task 3", depends_on=["2"]),
        ]
        schedule = build_dag(tasks)
        assert len(schedule.levels) == 3

    def test_parallel_tasks(self) -> None:
        """Tareas independientes deben estar en el mismo nivel."""
        tasks = [
            PipelineTask("1", "builder", "Task 1"),
            PipelineTask("2", "scientist", "Task 2"),
            PipelineTask("3", "guardian", "Task 3"),
        ]
        schedule = build_dag(tasks)
        assert len(schedule.levels) == 1
        assert len(schedule.levels[0]) == 3

    def test_complex_dag(self) -> None:
        """DAG complejo debe respetar dependencias."""
        tasks = [
            PipelineTask("1", "builder", "API Design"),
            PipelineTask("2", "scientist", "Research", depends_on=["1"]),
            PipelineTask("3", "guardian", "Security", depends_on=["1"]),
            PipelineTask("4", "builder", "Implementation", depends_on=["2", "3"]),
        ]
        schedule = build_dag(tasks)
        assert len(schedule.levels) >= 2  # Nivel 1: [1], Nivel 2: [2,3], Nivel 3: [4]

    def test_empty_tasks(self) -> None:
        """Lista vacia debe retornar schedule vacio."""
        schedule = build_dag([])
        assert len(schedule.levels) == 0
        assert schedule.total_tokens == 0

    def test_priority_ordering(self) -> None:
        """Tareas con mayor prioridad deben ir primero."""
        tasks = [
            PipelineTask("1", "builder", "Low", priority=1),
            PipelineTask("2", "builder", "High", priority=10),
        ]
        schedule = build_dag(tasks)
        assert schedule.levels[0][0].id == "2"  # High priority first


class TestSpeedupEstimate:
    """Estimacion de speedup."""

    def test_sequential_no_speedup(self) -> None:
        """Pipeline secuencial debe tener speedup 1.0."""
        tasks = [
            PipelineTask("1", "builder", "T1"),
            PipelineTask("2", "builder", "T2", depends_on=["1"]),
        ]
        schedule = build_dag(tasks)
        assert estimate_speedup(schedule) == 1.0

    def test_parallel_speedup(self) -> None:
        """Pipeline paralelo debe tener speedup >1."""
        tasks = [
            PipelineTask("1", "builder", "T1"),
            PipelineTask("2", "scientist", "T2"),
            PipelineTask("3", "guardian", "T3"),
        ]
        schedule = build_dag(tasks)
        assert estimate_speedup(schedule) >= 2.0


class TestTokenBudget:
    """Gestion de presupuesto de tokens."""

    def test_register_agent(self) -> None:
        """Registrar agente debe asignar presupuesto."""
        mgr = TokenBudgetManager(total_budget=1000)
        mgr.register_agent("builder", priority=5)
        stats = mgr.get_stats()
        assert "builder" in stats["agents"]

    def test_spend_tokens(self) -> None:
        """Gastar tokens debe reducir remaining."""
        mgr = TokenBudgetManager(total_budget=1000)
        mgr.register_agent("builder", priority=5)
        assert mgr.spend("builder", 100) is True
        assert mgr.get_stats()["agents"]["builder"]["remaining"] > 0

    def test_insufficient_budget(self) -> None:
        """Gastar mas del presupuesto debe fallar."""
        mgr = TokenBudgetManager(total_budget=100)
        mgr.register_agent("builder", priority=5)
        assert mgr.spend("builder", 200) is False

    def test_stats_usage(self) -> None:
        """Stats debe reflejar uso correcto."""
        mgr = TokenBudgetManager(total_budget=1000)
        mgr.register_agent("builder", priority=10)
        mgr.spend("builder", 100)
        stats = mgr.get_stats()
        assert stats["agents"]["builder"]["used"] == 100
        # budget = 1000 * 1.0 / 10 = 100, usage = 100/100 = 100%
        assert stats["agents"]["builder"]["usage_pct"] == 100.0
