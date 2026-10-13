"""Tests de wiring de debate — cierre de gaps de integracion (TDD RED->GREEN).

Cubre el gap 1: ``MinoritySentinel`` existe pero ``DebateRunner`` construia
``DebateOrchestrator`` sin sentinel (revision de minoria INACTIVA), y el flag
``is_debate`` del planner quedaba sin efecto (nadie invocaba el debate).

Casos:
  (a) ``DebateRunner`` inyecta ``MinoritySentinel`` por defecto (spy del
      constructor de ``DebateOrchestrator``).
  (b) ``SWARMIND_MINORITY_SENTINEL=0`` desactiva el sentinel; DI explicita gana.
  (c) El flujo ``is_debate`` invoca ``run_debate_async`` (spy); las tareas
      normales NO lo invocan.
  (f) Mutacion del flag de sentinel rompe el contrato (test discriminante).

Sin LLM real: sesion y dispatch mockeados.
"""

from __future__ import annotations

from typing import Any, ClassVar
from unittest.mock import MagicMock

import pytest

from harness.orchestrator import debate_runner as dr
from harness.orchestrator.minority_sentinel import MinoritySentinel

# ---------------------------------------------------------------------------
# Dobles de prueba
# ---------------------------------------------------------------------------


class _FakeSubtask:
    """Subtask minima con solo el atributo ``agent``."""

    def __init__(self, agent: str) -> None:
        self.agent = agent


class _FakePlan:
    """Plan minimo con la lista de subtasks."""

    def __init__(self, agents: list[str]) -> None:
        self.subtasks = [_FakeSubtask(a) for a in agents]


class _FakeSession:
    """Sesion minima con un plan de subtasks."""

    def __init__(self, agents: list[str]) -> None:
        self.plan = _FakePlan(agents)


def _session_ctx(agents: tuple[str, ...] = ("builder", "scientist")) -> MagicMock:
    """SessionContext mock que resuelve una sesion con los agentes dados."""
    ctx = MagicMock()
    ctx.get_session.return_value = _FakeSession(list(agents))
    return ctx


class _FakeDebateResult:
    """Resultado de debate minimo para ``_log_completed`` (sin LLM)."""

    confidence = 0.5
    agent_agreement = 0.5
    rounds: tuple[Any, ...] = ()


class _OrchSpy:
    """Spy del constructor de ``DebateOrchestrator`` (registra el ``sentinel``)."""

    created: ClassVar[list[_OrchSpy]] = []

    def __init__(
        self,
        vector_store: Any | None = None,
        *,
        failure_registry: Any | None = None,
        sentinel: MinoritySentinel | None = None,
    ) -> None:
        """Registra la instancia y captura el ``sentinel`` inyectado."""
        self.vector_store = vector_store
        self.failure_registry = failure_registry
        self.sentinel = sentinel
        _OrchSpy.created.append(self)

    def debate(self, **kwargs: Any) -> _FakeDebateResult:
        """Ruta sync falsa (no ejecuta debate real)."""
        return _FakeDebateResult()

    async def debate_async(self, **kwargs: Any) -> _FakeDebateResult:
        """Ruta async falsa (no ejecuta debate real)."""
        return _FakeDebateResult()


def _build_runner() -> dr.DebateRunner:
    """Construye un ``DebateRunner`` con sesion/bus mockeados."""
    return dr.DebateRunner(None, _session_ctx(), MagicMock())


def _run(runner: dr.DebateRunner) -> None:
    """Ejecuta un debate sync con dispatch determinista (sin LLM)."""
    runner.run_debate(
        "sess-1", "tarea de prueba",
        agents=["builder", "scientist"],
        dispatch_fn=lambda agent, task, context: "respuesta",
    )


# ---------------------------------------------------------------------------
# (a) sentinel por defecto
# ---------------------------------------------------------------------------


class TestSentinelDefault:
    """El DebateRunner inyecta MinoritySentinel por defecto."""

    def test_inyecta_sentinel_por_defecto(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """(a) Sin env, el orquestador recibe un MinoritySentinel (spy)."""
        monkeypatch.delenv(dr.ENV_MINORITY_SENTINEL, raising=False)
        _OrchSpy.created = []
        monkeypatch.setattr(dr, "DebateOrchestrator", _OrchSpy)

        _run(_build_runner())

        assert len(_OrchSpy.created) == 1
        assert isinstance(_OrchSpy.created[0].sentinel, MinoritySentinel)

    async def test_inyecta_sentinel_en_ruta_async(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """(a) La ruta async tambien inyecta el sentinel por defecto (spy)."""
        monkeypatch.delenv(dr.ENV_MINORITY_SENTINEL, raising=False)
        _OrchSpy.created = []
        monkeypatch.setattr(dr, "DebateOrchestrator", _OrchSpy)

        runner = _build_runner()
        await runner.run_debate_async(
            "sess-1", "tarea de prueba",
            agents=["builder", "scientist"],
            dispatch_fn=lambda agent, task, context: "respuesta",
        )

        assert isinstance(_OrchSpy.created[0].sentinel, MinoritySentinel)


# ---------------------------------------------------------------------------
# (b) flag de entorno + DI
# ---------------------------------------------------------------------------


class TestSentinelFlag:
    """SWARMIND_MINORITY_SENTINEL=0 desactiva; DI explicita manda."""

    def test_flag_off_desactiva_sentinel(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """(b) Con el flag en 0, el sentinel NO se inyecta (None)."""
        monkeypatch.setenv(dr.ENV_MINORITY_SENTINEL, "0")
        _OrchSpy.created = []
        monkeypatch.setattr(dr, "DebateOrchestrator", _OrchSpy)

        _run(_build_runner())

        assert _OrchSpy.created[0].sentinel is None

    def test_flag_false_desactiva_sentinel(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """(b) Valores falsy adicionales (``false``) tambien desactivan."""
        monkeypatch.setenv(dr.ENV_MINORITY_SENTINEL, "false")
        assert dr._sentinel_enabled() is False

    def test_di_explicita_gana_al_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """(b) Un sentinel inyectado por DI prevalece aunque el flag este off."""
        monkeypatch.setenv(dr.ENV_MINORITY_SENTINEL, "0")
        custom = MinoritySentinel()

        runner = dr.DebateRunner(None, _session_ctx(), MagicMock(), sentinel=custom)

        assert runner._sentinel is custom

    def test_di_none_desactiva_explicito(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """(b) Pasar ``sentinel=None`` desactiva explicitamente (backward-compat)."""
        monkeypatch.delenv(dr.ENV_MINORITY_SENTINEL, raising=False)
        runner = dr.DebateRunner(None, _session_ctx(), MagicMock(), sentinel=None)
        assert runner._sentinel is None


# ---------------------------------------------------------------------------
# (c) el flujo is_debate invoca el debate
# ---------------------------------------------------------------------------


class TestDebateFlow:
    """``run_debate_for_task`` materializa el debate cuando ``is_debate``."""

    async def test_flujo_debate_invoca_run_debate(self) -> None:
        """(c) Una tarea de debate invoca ``run_debate_async`` (spy) con agentes."""
        from harness.orchestrator.task_orchestrator import TaskOrchestrator

        orch = TaskOrchestrator()
        calls: list[dict[str, Any]] = []
        fake = object()

        async def spy(**kwargs: Any) -> object:
            calls.append(kwargs)
            return fake

        orch.run_debate_async = spy  # type: ignore[method-assign]

        result = await orch.run_debate_for_task("debate sobre arquitectura del sistema")

        assert result is fake
        assert len(calls) == 1
        assert set(calls[0]["agents"]) >= {"builder", "scientist"}
        assert calls[0]["strategy"] == "consensus"

    async def test_flujo_normal_no_invoca_debate(self) -> None:
        """(c) Una tarea normal NO invoca el debate (retorna None)."""
        from harness.orchestrator.task_orchestrator import TaskOrchestrator

        orch = TaskOrchestrator()
        calls: list[Any] = []

        async def spy(**kwargs: Any) -> object:
            calls.append(kwargs)
            return object()

        orch.run_debate_async = spy  # type: ignore[method-assign]

        result = await orch.run_debate_for_task(
            "implementa una API REST en Rust con tests y docs"
        )

        assert result is None
        assert calls == []


# ---------------------------------------------------------------------------
# (f) mutacion del flag de sentinel
# ---------------------------------------------------------------------------


class TestMutationFlag:
    """Sentinela de mutacion: el flag de entorno es observable."""

    def test_mutacion_del_flag_rompe_el_contrato(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """(f) Un ``_sentinel_enabled`` mutante que ignora el env rompe (b).

        Mutacion: si ``_sentinel_enabled`` devolviera siempre True sin leer
        ``SWARMIND_MINORITY_SENTINEL``, el contrato (b) fallaria (se inyectaria
        el sentinel con el flag off). Aqui se demuestra la diferencia.
        """
        monkeypatch.setenv(dr.ENV_MINORITY_SENTINEL, "0")

        # Comportamiento correcto: el flag OFF desactiva el sentinel.
        assert dr._resolve_sentinel(dr._UNSET) is None

        # Mutante: `_sentinel_enabled` que ignora el env reintroduce el sentinel.
        monkeypatch.setattr(dr, "_sentinel_enabled", lambda: True)
        assert dr._resolve_sentinel(dr._UNSET) is not None
