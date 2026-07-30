"""
Tests para Agent Capsules — Token-Aware Agent Fusion.

Cubre: 8 escenarios clave incluyendo empty calls, tres estrategias de fusion,
ahorro de tokens, quality floor, dispatch personalizado y multiples llamadas.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from harness.orchestrator.agent_capsules import (
    AgentCall,
    AgentCapsule,
    CapsuleResult,
    FusionStrategy,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def capsule() -> AgentCapsule:
    """AgentCapsule con dispatch mockeado por defecto."""
    return AgentCapsule(quality_floor=0.85)


@pytest.fixture
def sample_calls() -> list[AgentCall]:
    """Lista de 3 llamadas de ejemplo para pruebas."""
    return [
        AgentCall(
            agent="builder",
            prompt="Construye un modulo de autenticacion",
            priority=8,
            expected_tokens=400,
        ),
        AgentCall(
            agent="scientist",
            prompt="Analiza rendimiento de la cola de mensajes",
            priority=6,
            expected_tokens=600,
        ),
        AgentCall(
            agent="reviewer",
            prompt="Revisa el cumplimiento de guias de estilo",
            priority=5,
            expected_tokens=300,
        ),
    ]


@pytest.fixture
def mock_dispatch() -> MagicMock:
    """Dispatch function mockeada para verificar llamadas."""
    mock = MagicMock()
    mock.side_effect = lambda agent, prompt: (
        f"[{agent}] Resultado: {agent}-{hash(prompt) % 1000}"
    )
    return mock


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestAgentCapsule:
    """Suite de tests para AgentCapsule."""

    # -- test 1: empty calls -----------------------------------------------

    def test_empty_calls(self, capsule: AgentCapsule) -> None:
        """
        Ejecutar con lista vacia retorna resultado vacio sin errores.

        Verifica que:
        - results es dict vacio
        - tokens_saved es 0
        - quality_score es 1.0
        """
        result = capsule.execute([], strategy=FusionStrategy.COMPOUND)
        assert isinstance(result, CapsuleResult)
        assert result.results == {}
        assert result.tokens_saved == 0
        assert result.quality_score == 1.0
        assert result.fusion_strategy == FusionStrategy.COMPOUND

    # -- test 2: compound strategy -----------------------------------------

    def test_compound_strategy(
        self, capsule: AgentCapsule, sample_calls: list[AgentCall]
    ) -> None:
        """
        Fusion COMPOUND ejecuta un solo dispatch y distribuye resultado.

        Verifica que:
        - Todos los agentes tienen el mismo resultado (fusionado).
        - El compound_prompt se genera correctamente.
        - tokens_saved es >= 0.
        """
        result = capsule.execute(sample_calls, strategy=FusionStrategy.COMPOUND)

        assert isinstance(result, CapsuleResult)
        assert len(result.results) == len(sample_calls)
        # Todos los agentes comparten el mismo resultado
        unique_results = set(result.results.values())
        assert len(unique_results) == 1
        # compound_prompt debe existir
        assert result.compound_prompt is not None
        assert "Tareas Multi-Agente" in result.compound_prompt
        # Verificar que cada agente aparece en results
        for call in sample_calls:
            assert call.agent in result.results
        # tokens_saved no debe ser negativo
        assert result.tokens_saved >= 0
        assert result.fusion_strategy == FusionStrategy.COMPOUND

    # -- test 3: two_phase strategy ----------------------------------------

    def test_two_phase_strategy(
        self, capsule: AgentCapsule, sample_calls: list[AgentCall]
    ) -> None:
        """
        Fusion TWO_PHASE ejecuta exploracion + detalle individual.

        Verifica que:
        - Cada agente tiene su propio resultado.
        - compound_prompt contiene la fase exploratoria.
        - quality_score es 0.92.
        """
        result = capsule.execute(sample_calls, strategy=FusionStrategy.TWO_PHASE)

        assert isinstance(result, CapsuleResult)
        assert len(result.results) == len(sample_calls)
        # Cada agente tiene resultado distinto (fase detalle)
        for call in sample_calls:
            assert call.agent in result.results
            assert result.results[call.agent].startswith(f"[{call.agent}]")
        # compound_prompt contiene la exploracion
        assert result.compound_prompt is not None
        assert "Exploracion Multi-Agente" in result.compound_prompt
        assert result.quality_score == 0.92
        assert result.fusion_strategy == FusionStrategy.TWO_PHASE

    # -- test 4: sequential strategy ---------------------------------------

    def test_sequential_strategy(
        self, capsule: AgentCapsule, sample_calls: list[AgentCall]
    ) -> None:
        """
        Fusion SEQUENTIAL ejecuta cada llamada individualmente.

        Verifica que:
        - Cada agente tiene su resultado propio.
        - tokens_saved es 0.
        - quality_score es 1.0.
        - compound_prompt es None.
        """
        result = capsule.execute(sample_calls, strategy=FusionStrategy.SEQUENTIAL)

        assert isinstance(result, CapsuleResult)
        assert len(result.results) == len(sample_calls)
        for call in sample_calls:
            assert call.agent in result.results
            assert result.results[call.agent].startswith(f"[{call.agent}]")
        assert result.tokens_saved == 0
        assert result.quality_score == 1.0
        assert result.compound_prompt is None
        assert result.fusion_strategy == FusionStrategy.SEQUENTIAL

    # -- test 5: tokens saved compound -------------------------------------

    def test_tokens_saved_compound(
        self, capsule: AgentCapsule, sample_calls: list[AgentCall]
    ) -> None:
        """
        Compound ahorra mas tokens que las otras estrategias.

        Verifica que tokens_saved de COMPOUND es estrictamente positivo.
        """
        compound_result = capsule.execute(
            sample_calls, strategy=FusionStrategy.COMPOUND
        )
        sequential_result = capsule.execute(
            sample_calls, strategy=FusionStrategy.SEQUENTIAL
        )

        assert compound_result.tokens_saved > 0
        assert sequential_result.tokens_saved == 0
        # Compound ahorra vs secuencial
        assert compound_result.tokens_saved > sequential_result.tokens_saved

    # -- test 6: quality floor ---------------------------------------------

    def test_quality_floor(self) -> None:
        """
        Quality floor se respeta: capsule con threshold alto.

        Verifica que:
        - No hay error en ejecucion con threshold normal.
        - COMPOUND tiene quality 0.85 (default ok con floor 0.85).
        - SEQUENTIAL tiene quality 1.0 siempre cumple.
        """
        strict_capsule = AgentCapsule(quality_floor=0.90)
        calls = [
            AgentCall(agent="builder", prompt="Tarea A", priority=5, expected_tokens=100),
            AgentCall(agent="scientist", prompt="Tarea B", priority=5, expected_tokens=100),
        ]

        # Compound (0.85) esta por debajo del floor 0.90 pero no falla
        result = strict_capsule.execute(calls, strategy=FusionStrategy.COMPOUND)
        assert result.quality_score < 0.90  # 0.85 < 0.90, warning log

        # Secuencial (1.0) supera cualquier floor
        result_seq = strict_capsule.execute(calls, strategy=FusionStrategy.SEQUENTIAL)
        assert result_seq.quality_score >= 0.90

    def test_quality_floor_invalid(self) -> None:
        """
        Quality floor invalido (<0 o >1) lanza ValueError.
        """
        with pytest.raises(ValueError, match="quality_floor debe estar entre 0 y 1"):
            AgentCapsule(quality_floor=-0.1)

        with pytest.raises(ValueError, match="quality_floor debe estar entre 0 y 1"):
            AgentCapsule(quality_floor=1.5)

    # -- test 7: custom dispatch -------------------------------------------

    def test_custom_dispatch(self, mock_dispatch: MagicMock) -> None:
        """
        Dispatch personalizado es invocado correctamente.

        Verifica que:
        - La funcion dispatch se llama con los argumentos correctos.
        - El resultado contiene lo que retorna el dispatch.
        """
        custom_capsule = AgentCapsule(dispatch_fn=mock_dispatch)
        calls = [
            AgentCall(
                agent="custom-agent",
                prompt="Haz algo",
                priority=5,
                expected_tokens=50,
            ),
        ]

        result = custom_capsule.execute(calls, strategy=FusionStrategy.SEQUENTIAL)

        # Verificar que se llamo al dispatch con los argumentos correctos
        mock_dispatch.assert_called_once_with("custom-agent", "Haz algo")
        # Verificar formato del resultado (hash puede variar entre ejecuciones)
        assert result.results["custom-agent"].startswith("[custom-agent] Resultado: ")

    def test_custom_dispatch_compound(self, mock_dispatch: MagicMock) -> None:
        """
        Dispatch personalizado con estrategia COMPOUND.

        Verifica que dispatch se llama solo una vez para N calls.
        """
        custom_capsule = AgentCapsule(dispatch_fn=mock_dispatch)
        calls = [
            AgentCall(agent="a1", prompt="Tarea 1", priority=5, expected_tokens=100),
            AgentCall(agent="a2", prompt="Tarea 2", priority=5, expected_tokens=100),
        ]

        custom_capsule.execute(calls, strategy=FusionStrategy.COMPOUND)

        # Solo una llamada al dispatch (compound fusion)
        assert mock_dispatch.call_count == 1
        # El unico call fue al agente de mayor prioridad (a1, ambos tienen 5, usa primero)
        args, _ = mock_dispatch.call_args
        assert args[0] in ("a1", "a2")
        assert "Tareas Multi-Agente" in args[1]

    # -- test 8: multiple calls --------------------------------------------

    def test_multiple_calls(self, capsule: AgentCapsule) -> None:
        """
        Multiples llamadas (N>5) con estrategia COMPOUND.

        Verifica que:
        - Todas las N llamadas se ejecutan sin error.
        - compound_prompt contiene todas las tareas.
        - Se ahorran tokens.
        """
        n_calls = 10
        calls: list[AgentCall] = [
            AgentCall(
                agent=f"agent-{i}",
                prompt=f"Tarea prioritaria numero {i} con detalle de ejemplo",
                priority=(i % 5) + 1,
                expected_tokens=200 + i * 10,
            )
            for i in range(n_calls)
        ]

        result = capsule.execute(calls, strategy=FusionStrategy.COMPOUND)

        assert len(result.results) == n_calls
        for i in range(n_calls):
            assert f"agent-{i}" in result.results
        # compound_prompt contiene todas las tareas
        assert result.compound_prompt is not None
        for i in range(n_calls):
            assert f"Tarea {i+1} (agent-{i})" in result.compound_prompt
        assert result.tokens_saved > 0
        assert result.fusion_strategy == FusionStrategy.COMPOUND

    def test_multiple_calls_two_phase(self, capsule: AgentCapsule) -> None:
        """
        Multiples llamadas con estrategia TWO_PHASE.

        Verifica que cada agente recibe resultado individual con contexto.
        """
        calls: list[AgentCall] = [
            AgentCall(
                agent=f"worker-{i}",
                prompt=f"Procesa el lote {i}",
                priority=5,
                expected_tokens=150,
            )
            for i in range(6)
        ]

        result = capsule.execute(calls, strategy=FusionStrategy.TWO_PHASE)

        assert len(result.results) == 6
        for i in range(6):
            assert f"worker-{i}" in result.results
            assert result.results[f"worker-{i}"].startswith("[worker-")

    # -- Bonus: auto strategy selection -----------------------------------

    def test_auto_strategy_selection(self) -> None:
        """
        Seleccion automatica de estrategia segun N calls.

        Verifica que:
        - 1 call -> SEQUENTIAL
        - 5+ calls -> COMPOUND
        - 2-4 calls con prioridad normal -> TWO_PHASE
        """
        capsule = AgentCapsule()

        # 1 call -> SEQUENTIAL
        r1 = capsule.execute([AgentCall(agent="a", prompt="x", priority=5)])
        assert r1.fusion_strategy == FusionStrategy.SEQUENTIAL

        # 3 calls -> TWO_PHASE (default)
        r2 = capsule.execute([
            AgentCall(agent="a", prompt="x", priority=5),
            AgentCall(agent="b", prompt="y", priority=5),
            AgentCall(agent="c", prompt="z", priority=5),
        ])
        assert r2.fusion_strategy == FusionStrategy.TWO_PHASE

        # 5 calls -> COMPOUND
        r3 = capsule.execute([
            AgentCall(agent=f"a{i}", prompt=f"x{i}", priority=5)
            for i in range(5)
        ])
        assert r3.fusion_strategy == FusionStrategy.COMPOUND

    # -- Edge cases --------------------------------------------------------

    def test_invalid_strategy(self, capsule: AgentCapsule) -> None:
        """
        Strategy invalido lanza TypeError.
        """
        with pytest.raises(TypeError, match="strategy debe ser miembro de FusionStrategy"):
            capsule.execute(
                [AgentCall(agent="a", prompt="test")],
                strategy="invalid_strategy",  # type: ignore[arg-type]
            )

    def test_invalid_call_type(self, capsule: AgentCapsule) -> None:
        """
        Elemento en calls que no es AgentCall lanza TypeError.
        """
        with pytest.raises(TypeError, match="no es AgentCall"):
            capsule.execute(
                [{"agent": "a", "prompt": "test"}],  # type: ignore[list-item]
                strategy=FusionStrategy.SEQUENTIAL,
            )

    def test_empty_agent_name(self, capsule: AgentCapsule) -> None:
        """
        AgentCall con agent vacio lanza ValueError.
        """
        with pytest.raises(ValueError, match="agent o prompt vacio"):
            capsule.execute(
                [AgentCall(agent="", prompt="test")],
                strategy=FusionStrategy.SEQUENTIAL,
            )

    def test_cache_hit(self) -> None:
        """
        Cache de prompts evita dispatch duplicado.

        Verifica que prompts identicos solo ejecutan dispatch una vez.
        """
        mock_fn = MagicMock(return_value="cached-result")
        capsule = AgentCapsule(dispatch_fn=mock_fn)

        calls = [AgentCall(agent="a", prompt="Mismo prompt", priority=5)]
        capsule.execute(calls, strategy=FusionStrategy.SEQUENTIAL)
        capsule.execute(calls, strategy=FusionStrategy.SEQUENTIAL)

        # Solo una llamada al dispatch (segunda debe ser cache hit)
        mock_fn.assert_called_once()

    def test_clear_cache(self) -> None:
        """
        clear_cache limpia el cache interno.
        """
        mock_fn = MagicMock(return_value="result")
        capsule = AgentCapsule(dispatch_fn=mock_fn)

        calls = [AgentCall(agent="a", prompt="test", priority=5)]
        capsule.execute(calls, strategy=FusionStrategy.SEQUENTIAL)
        capsule.clear_cache()
        capsule.execute(calls, strategy=FusionStrategy.SEQUENTIAL)

        # Dos llamadas porque el cache se limpio
        assert mock_fn.call_count == 2
