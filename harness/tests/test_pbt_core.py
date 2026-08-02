"""
Tests de propiedad (Property-Based Testing) para modulos core.

Usa Hypothesis para verificar invariantes de:
  - semantic_cache.py (CacheEntry, SemanticCache, ShapedCache)
  - token_optimizer.py (build_dag, estimate_speedup, structured_prompt)

Technicas: TDAD (Test-Driven AI Agent Definition), PaCoRe (parallel reasoning),
           PROBE/AdverTest (adversarial loop), Cache-Shape Discipline.

Regla: Cada test explora el espacio de entrada con Hypothesis para encontrar
       contraejemplos que violen las propiedades declaradas.
"""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from hypothesis import given
from hypothesis import strategies as st
from hypothesis.stateful import RuleBasedStateMachine, invariant, rule

from harness.memory_rag.semantic_cache import (
    DEFAULT_TTL_SECONDS,
    CacheEntry,
    SemanticCache,
    ShapedCache,
)
from harness.orchestrator.token_optimizer import (
    OutputFormat,
    PipelineTask,
    TokenBudgetManager,
    build_dag,
    estimate_speedup,
    structured_prompt,
)

# ============================================================================
# Estrategias compartidas (DRY)
# ============================================================================

_text_strategy = st.text(min_size=1, max_size=200, alphabet=st.characters(
    whitelist_categories=("Lu", "Ll", "Nd", "Zs", "P"),
))
_non_empty_text = st.text(min_size=1, max_size=200, alphabet=st.characters(
    whitelist_categories=("Lu", "Ll", "Nd", "Zs", "P"),
))
_prompt_strategy = st.text(min_size=1, max_size=100)
_response_strategy = st.text(min_size=1, max_size=200)  # >=1 porque el cache rechaza respuestas vacias
_agent_role_strategy = st.sampled_from(["*", "builder", "scientist", "guardian", "quality-gate"])
_threshold_strategy = st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False)
_positive_int = st.integers(min_value=1, max_value=1000)
_task_id_list = st.lists(
    st.integers(min_value=1, max_value=100), min_size=1, max_size=10,
)

# ============================================================================
# PROPIEDADES: SemanticCache + CacheEntry
# ============================================================================


class TestCacheEntryProperties:
    """Propiedades de CacheEntry (invariantes de estructura de datos)."""

    @given(
        prompt_hash=st.text(min_size=1, max_size=64),
        prompt_text=st.text(min_size=0, max_size=500),
        response=st.text(min_size=0, max_size=500),
        agent_role=st.text(min_size=0, max_size=50),
        hit_count=_positive_int,
    )
    def test_cache_entry_to_dict_roundtrip(
        self,
        prompt_hash: str,
        prompt_text: str,
        response: str,
        agent_role: str,
        hit_count: int,
    ) -> None:
        """CacheEntry.to_dict() contiene todos los campos esperados y no pierde informacion."""
        entry = CacheEntry(
            prompt_hash=prompt_hash,
            prompt_text=prompt_text,
            response=response,
            agent_role=agent_role,
            hit_count=hit_count,
            created_at=datetime.now(UTC).isoformat(),
            last_accessed=datetime.now(UTC).isoformat(),
            ttl_seconds=DEFAULT_TTL_SECONDS,
        )
        d = entry.to_dict()
        assert d["prompt_hash"] == prompt_hash
        assert d["response"] == response
        assert d["agent_role"] == agent_role
        assert d["hit_count"] == hit_count
        assert isinstance(d["created_at"], str)
        assert isinstance(d["last_accessed"], str)
        assert d["ttl_seconds"] == DEFAULT_TTL_SECONDS

    @given(
        prompt_hash=st.text(min_size=1, max_size=64),
        prompt_text=st.text(min_size=0, max_size=500),
        response=st.text(min_size=0, max_size=500),
    )
    def test_cache_entry_is_expired_no_created_at(
        self,
        prompt_hash: str,
        prompt_text: str,
        response: str,
    ) -> None:
        """CacheEntry sin created_at debe aparecer como expirado."""
        entry = CacheEntry(
            prompt_hash=prompt_hash,
            prompt_text=prompt_text,
            response=response,
            agent_role="*",
            created_at="",
        )
        assert entry.is_expired()

    @given(
        prompt_hash=st.text(min_size=1, max_size=64),
        prompt_text=st.text(min_size=0, max_size=500),
        response=st.text(min_size=0, max_size=500),
        ttl=_positive_int,
    )
    def test_cache_entry_fresh_not_expired(
        self,
        prompt_hash: str,
        prompt_text: str,
        response: str,
        ttl: int,
    ) -> None:
        """CacheEntry recien creado no debe estar expirado."""
        entry = CacheEntry(
            prompt_hash=prompt_hash,
            prompt_text=prompt_text,
            response=response,
            agent_role="*",
            created_at=datetime.now(UTC).isoformat(),
            ttl_seconds=max(ttl, 1),
        )
        assert not entry.is_expired()


class TestSemanticCacheProperties:
    """Propiedades del SemanticCache usando Hypothesis."""

    @given(prompt=_prompt_strategy, response=_response_strategy)
    def test_cache_roundtrip(self, prompt: str, response: str) -> None:
        """Set -> Get debe retornar el mismo valor.
        
        Propiedad fundamental: el cache es determinista y mantiene
        la relacion uno-a-uno entre prompt y respuesta.
        """
        from harness.tests.conftest import _mock_store_with_defaults
        store = _mock_store_with_defaults()
        cache = SemanticCache(vector_store=store)
        cache.set(prompt, response, agent_role="*")
        result = cache.get(prompt, agent_role="*")
        assert result == response, (
            f"Cache roundtrip fallo: set({prompt!r}) = {response!r}, "
            f"get() = {result!r}"
        )

    @given(prompt=_prompt_strategy)
    def test_cache_miss_returns_none(self, prompt: str) -> None:
        """Get para prompt no cacheado debe ser None.
        
        Propiedad: el cache nunca debe retornar un falso positivo
        para un prompt que nunca se almaceno.
        """
        from harness.tests.conftest import _mock_store_with_defaults
        store = _mock_store_with_defaults()
        cache = SemanticCache(vector_store=store)
        result = cache.get(prompt, agent_role="*")
        assert result is None

    @given(
        prompt=_prompt_strategy,
        response=_response_strategy,
        agent_role=_agent_role_strategy,
    )
    def test_set_get_different_agent_role_miss(
        self,
        prompt: str,
        response: str,
        agent_role: str,
    ) -> None:
        """Get con rol distinto al del set debe fallar (miss).
        
        Propiedad: el filtro por agent_role debe ser estricto:
        solo roles exactos o '*' deben hacer match.
        """
        if agent_role == "*":
            return  # '*'' matchea todo, no podemos probar miss
        from harness.tests.conftest import _mock_store_with_defaults
        store = _mock_store_with_defaults()
        cache = SemanticCache(vector_store=store)
        other_role = "scientist" if agent_role == "builder" else "builder"
        cache.set(prompt, response, agent_role=agent_role)
        result = cache.get(prompt, agent_role=other_role)
        assert result is None

    @given(
        prompt1=_prompt_strategy,
        prompt2=_prompt_strategy,
        response1=_response_strategy,
        response2=_response_strategy,
    )
    def test_cache_independence(
        self,
        prompt1: str,
        prompt2: str,
        response1: str,
        response2: str,
    ) -> None:
        """Dos prompts distintos no deben interferir entre si.
        
        Propiedad: el cache debe mantener independencia entre entradas.
        Si los prompts son iguales, el segundo set() pisa al primero
        (comportamiento esperado del cache por diseno).
        """
        if prompt1 == prompt2:
            return  # mismo prompt -> overwrite esperado, no aplica
        from harness.tests.conftest import _mock_store_with_defaults
        store = _mock_store_with_defaults()
        cache = SemanticCache(vector_store=store)
        cache.set(prompt1, response1, agent_role="*")
        cache.set(prompt2, response2, agent_role="*")
        r1 = cache.get(prompt1, agent_role="*")
        r2 = cache.get(prompt2, agent_role="*")
        assert r1 == response1
        assert r2 == response2

    @given(
        prompt=_prompt_strategy,
        response=_response_strategy,
        threshold=_threshold_strategy,
    )
    def test_stats_hits_misses_monotonic(
        self,
        prompt: str,
        response: str,
        threshold: float,
    ) -> None:
        """Las estadisticas de cache deben ser monotonicas.
        
        Propiedad: hits + misses = total_requests en todo momento.
        """
        from harness.tests.conftest import _mock_store_with_defaults
        store = _mock_store_with_defaults()
        cache = SemanticCache(vector_store=store, threshold=threshold)
        cache.set(prompt, response, agent_role="*")
        cache.get(prompt, agent_role="*")
        stats = cache.get_stats()
        assert stats["hits"] + stats["misses"] == stats["total_requests"]
        assert stats["hit_rate"] >= 0.0
        assert stats["hit_rate"] <= 100.0

    @given(
        prompt=_prompt_strategy,
        response=_response_strategy,
    )
    def test_hash_determinism(self, prompt: str, response: str) -> None:
        """El hash de un prompt debe ser deterministico.
        
        Propiedad: mismo prompt -> mismo hash SHA-256.
        """
        h1 = SemanticCache._hash_prompt(prompt)
        h2 = SemanticCache._hash_prompt(prompt)
        assert h1 == h2
        assert len(h1) == 64  # SHA-256 hex


class TestShapedCacheProperties:
    """Propiedades del ShapedCache (Cache-Shape Discipline)."""

    @given(
        prompt=_prompt_strategy,
        response=_response_strategy,
        token_cost=_positive_int,
    )
    def test_shaped_hit_rate_bounds(
        self,
        prompt: str,
        response: str,
        token_cost: int,
    ) -> None:
        """Hit rate de ShapedCache debe estar entre 0 y 1.
        
        Propiedad: invariant matematico del hit rate como proporcion.
        """
        from unittest.mock import MagicMock
        mock_cache = MagicMock()
        mock_cache.get.return_value = {
            "response": response,
            "timestamp": datetime.now(UTC).isoformat(),
        }
        shaped = ShapedCache(mock_cache)
        shaped.set_shaped(prompt, response, token_cost=token_cost)
        shaped.get_shaped(prompt)
        assert 0.0 <= shaped.hit_rate <= 1.0


# ============================================================================
# PROPIEDADES: Token Optimizer (DAG + Scheduling)
# ============================================================================


class TestDAGProperties:
    """Propiedades del DAG pipeline scheduler."""

    @given(task_ids=_task_id_list)
    def test_dag_no_cycles_and_all_tasks_present(self, task_ids: list[int]) -> None:
        """build_dag nunca debe crear ciclos e incluir todas las tareas.
        
        Propiedad: el schedule resultante debe contener exactamente
        todas las tareas de entrada en sus niveles.
        """
        tasks = [
            PipelineTask(str(i), "agent", f"task {i}")
            for i in task_ids
        ]
        schedule = build_dag(tasks)
        total_tasks = sum(len(level) for level in schedule.levels)
        assert total_tasks == len(task_ids), (
            f"Expected {len(task_ids)} tasks, got {total_tasks}"
        )

    @given(task_ids=_task_id_list)
    def test_dag_total_tokens_is_sum(self, task_ids: list[int]) -> None:
        """PipelineSchedule.total_tokens debe ser la suma de estimated_tokens.
        
        Propiedad: la metrica de tokens totales es aditiva.
        """
        tasks = [
            PipelineTask(str(i), "agent", f"task {i}", estimated_tokens=i * 10 + 1)
            for i in task_ids
        ]
        schedule = build_dag(tasks)
        expected = sum(t.estimated_tokens for t in tasks)
        assert schedule.total_tokens == expected, (
            f"Expected total_tokens={expected}, got {schedule.total_tokens}"
        )

    @given(task_ids=_task_id_list)
    def test_estimate_speedup_at_least_one(self, task_ids: list[int]) -> None:
        """estimate_speedup debe ser >= 1.0 para cualquier schedule no-vacio.
        
        Propiedad: el speedup del pipeline paralelo nunca es peor que
        el secuencial (bound inferior = 1.0).
        """
        tasks = [
            PipelineTask(str(i), "agent", f"task {i}")
            for i in task_ids
        ]
        schedule = build_dag(tasks)
        speedup = estimate_speedup(schedule)
        assert speedup >= 1.0

    @given(task_ids=_task_id_list)
    def test_dag_topological_ordering(self, task_ids: list[int]) -> None:
        """Las dependencias en el DAG deben aparecer antes que sus dependientes.
        
        Propiedad (invariante topologico): si A depende de B, B debe estar
        en un nivel anterior al nivel de A.
        """
        if len(task_ids) < 2:
            return
        # Crear tareas con una cadena de dependencias: 0 <- 1 <- 2 <- ...
        tasks = [
            PipelineTask(
                str(i), "agent", f"task {i}",
                depends_on=[str(i - 1)] if i > 0 else [],
            )
            for i in task_ids
        ]
        schedule = build_dag(tasks)
        # Verificar que el id de la tarea aparece en el nivel correcto
        level_of: dict[str, int] = {}
        for level_idx, level in enumerate(schedule.levels):
            for t in level:
                level_of[t.id] = level_idx
        for t in tasks:
            for dep in t.depends_on:
                if dep in level_of and t.id in level_of:
                    assert level_of[dep] < level_of[t.id], (
                        f"Task {t.id} (level {level_of[t.id]}) depends on "
                        f"{dep} (level {level_of[dep]}): violacion topologica"
                    )


class TestStructuredPromptProperties:
    """Propiedades del structured_prompt generator."""

    @given(
        instruction=_non_empty_text,
        max_tokens=_positive_int,
    )
    def test_structured_prompt_contains_instruction(
        self,
        instruction: str,
        max_tokens: int,
    ) -> None:
        """structured_prompt debe incluir la instruccion original.
        
        Propiedad: la funcion es un wrapper que preserva la instruccion
        del usuario sin alterarla.
        """
        prompt = structured_prompt(instruction, max_tokens=max_tokens)
        assert instruction in prompt

    @given(instruction=_non_empty_text)
    def test_structured_prompt_max_tokens_included(self, instruction: str) -> None:
        """El parametro max_tokens debe aparecer en el prompt generado."""
        prompt = structured_prompt(instruction, max_tokens=500)
        assert "500" in prompt

    @given(
        instruction=_non_empty_text,
        schema_key=st.text(min_size=1, max_size=20, alphabet=st.characters(
            whitelist_categories=("Lu", "Ll", "Nd"),
        )),
        schema_value=st.sampled_from(["string", "number", "boolean"]),
    )
    def test_structured_prompt_json_schema_included(
        self,
        instruction: str,
        schema_key: str,
        schema_value: str,
    ) -> None:
        """Con formato JSON_SCHEMA, el schema debe incluirse en el prompt."""
        schema: dict[str, Any] = {
            "type": "object",
            "properties": {schema_key: {"type": schema_value}},
        }
        prompt = structured_prompt(instruction, schema=schema)
        assert "```json" in prompt
        assert schema_key in prompt

    @given(
        instruction=_non_empty_text,
    )
    def test_structured_prompt_formats_are_distinct(self, instruction: str) -> None:
        """Los diferentes formatos deben producir prompts distinguibles.
        
        Propiedad: JSON_SCHEMA, MARKDOWN y FREE_TEXT deben tener
        estructuras de salida diferentes.
        """
        schema = {"type": "object", "properties": {"name": {"type": "string"}}}
        json_prompt = structured_prompt(instruction, schema=schema, format=OutputFormat.JSON_SCHEMA)
        md_prompt = structured_prompt(instruction, format=OutputFormat.MARKDOWN)
        free_prompt = structured_prompt(instruction, format=OutputFormat.FREE_TEXT)
        # JSON debe tener bloque de codigo
        assert "```json" in json_prompt
        # MARKDOWN debe mencionar secciones
        assert "## para secciones" in md_prompt
        # FREE_TEXT debe mencionar concisa
        assert "concisa" in free_prompt
        # Todos deben ser diferentes
        assert json_prompt != md_prompt
        assert md_prompt != free_prompt
        assert json_prompt != free_prompt

    @given(
        instruction=_non_empty_text,
        max_tokens=_positive_int,
    )
    def test_structured_prompt_always_returns_string(
        self,
        instruction: str,
        max_tokens: int,
    ) -> None:
        """structured_prompt siempre debe retornar un string no vacio.
        
        Propiedad: la funcion nunca falla para entradas validas.
        """
        prompt = structured_prompt(instruction, max_tokens=max_tokens)
        assert isinstance(prompt, str)
        assert len(prompt) > 0


# ============================================================================
# Stateful testing: TokenBudgetManager como maquina de estados
# ============================================================================


class TokenBudgetMachine(RuleBasedStateMachine):
    """
    Maquina de estados para TokenBudgetManager.
    
    Modela el ciclo de vida: registrar agentes, gastar tokens,
    verificar que el presupuesto nunca sea negativo.
    """

    def __init__(self) -> None:
        super().__init__()
        self.mgr = TokenBudgetManager(total_budget=10_000)
        self._agents: list[str] = []

    @rule(agent_name=st.text(min_size=1, max_size=20), priority=st.integers(min_value=1, max_value=10))
    def register_agent(self, agent_name: str, priority: int) -> None:
        """Registrar un agente con prioridad."""
        self.mgr.register_agent(agent_name, priority=priority)
        self._agents.append(agent_name)

    @rule(
        agent_name=st.text(min_size=1, max_size=20),
        tokens=st.integers(min_value=1, max_value=500),
    )
    def spend_tokens(self, agent_name: str, tokens: int) -> None:
        """Gastar tokens de un agente."""
        self.mgr.spend(agent_name, tokens)

    @invariant()
    def never_negative_remaining(self) -> None:
        """Invariante: remaining nunca debe ser negativo para ningun agente."""
        stats = self.mgr.get_stats()
        for agent_name, data in stats["agents"].items():
            assert data["remaining"] >= 0, (
                f"Agent {agent_name} tiene remaining negativo: {data['remaining']}"
            )

    @invariant()
    def usage_pct_never_exceeds_100(self) -> None:
        """Invariante: usage_pct nunca debe exceder 100%."""
        stats = self.mgr.get_stats()
        for agent_name, data in stats["agents"].items():
            assert data["usage_pct"] <= 100.0, (
                f"Agent {agent_name} tiene usage_pct={data['usage_pct']} > 100"
            )

    @invariant()
    def total_usage_in_bounds(self) -> None:
        """Invariante: total_used <= total_budget."""
        stats = self.mgr.get_stats()
        assert stats["total_used"] <= stats["total_budget"], (
            f"total_used={stats['total_used']} > total_budget={stats['total_budget']}"
        )


TestTokenBudgetMachine = TokenBudgetMachine.TestCase
