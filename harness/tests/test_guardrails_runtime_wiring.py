"""Tests TDD (RED->GREEN) del wiring de guardrails en runtime.

GAP DE SEGURIDAD CERRADO:
    ``harness/run_commands/handlers_extra.py::_run_guardrails`` importaba
    ``opencode.core.guardrails`` (EXTERNO); si faltaba, emitia un WARNING y
    CONTINUABA SIN guardrails (fallaba ABIERTO). El engine LOCAL
    (``harness/guardrails``) existia pero no estaba cableado.

WHAT: verifican el nuevo contrato fail-closed.
WHY: Forge 2026 - los guardrails cierran el gap de reliability; fallar
     abierto es un riesgo inaceptable.
WHERE: ``harness/run_commands/handlers_extra.py`` (fallback local + hooks) y
       ``harness/orchestrator/parallel_executor.py`` (FR-0007, pipeline_guard).

Cubre:
    (a) externo ausente -> usa engine LOCAL (spy) y NO continua sin guardrails.
    (b) ambos ausentes -> fail-closed (bloquea con SystemExit).
    (c) ``register_builtin_hooks`` se llama una sola vez (idempotente).
    (d) mutacion: revertir a "warning y continuar" hace fallar el test.
    Regresion: pipeline_guard sigue conectado (FR-0007).
"""
from __future__ import annotations

import sys
from unittest.mock import MagicMock

import pytest

from harness.guardrails.guardrail_types import GuardrailResult
from harness.run_commands import handlers_extra as he


class _SpyEngine:
    """Engine local falso que registra sus invocaciones (spy).

    Se inyecta via monkeypatch de ``harness.guardrails.GuardrailEngine`` para
    verificar que ``_run_guardrails`` realmente usa el engine LOCAL cuando el
    externo (``opencode.core.guardrails``) no esta disponible.
    """

    def __init__(self, *args: object, **kwargs: object) -> None:
        """Inicializa spies de las capas INPUT/CONTENT/POLICY (todas PASS)."""
        self.check_input = MagicMock(
            return_value=GuardrailResult.pass_result({"layer": "input"})
        )
        self.check_content = MagicMock(
            return_value=GuardrailResult.pass_result({"layer": "content"})
        )
        self.check_policy = MagicMock(
            return_value=GuardrailResult.pass_result({"layer": "policy"})
        )


@pytest.fixture
def opencode_guardrails_absent(monkeypatch: pytest.MonkeyPatch) -> None:
    """Simula la ausencia de ``opencode.core.guardrails`` en ``sys.modules``."""
    monkeypatch.setitem(sys.modules, "opencode.core.guardrails", None)
    monkeypatch.delitem(sys.modules, "opencode.core.guardrails", raising=False)
    # Reinstala el None para que cualquier import lance ImportError.
    monkeypatch.setitem(sys.modules, "opencode.core.guardrails", None)


def _mock_ctx() -> MagicMock:
    """Crea un contexto RAG minimo compatible con ``_run_guardrails``."""
    ctx = MagicMock()
    ctx.relevant_docs = []
    ctx.metadata = {"total_tokens_used": 0}
    return ctx


# ---------------------------------------------------------------------------
# (a) Fallback al engine LOCAL cuando el externo esta ausente
# ---------------------------------------------------------------------------


def test_fallback_usa_engine_local(
    monkeypatch: pytest.MonkeyPatch, opencode_guardrails_absent: None
) -> None:
    """(a) Externo ausente -> ``_run_guardrails`` usa el engine LOCAL (spy).

    WHAT: con ``opencode.core.guardrails`` ausente y ``run_full_pipeline=None``,
    el engine LOCAL de ``harness.guardrails`` DEBE ejecutarse.
    WHY: no puede continuar sin guardrails (fallar abierto es inaceptable).
    WHERE: ``handlers_extra._run_guardrails``.
    """
    monkeypatch.setattr("harness.guardrails.GuardrailEngine", _SpyEngine)

    # No debe salir del proceso: el engine local pasa la tarea benigna.
    he._run_guardrails("tarea benigna", "builder", _mock_ctx(), "local",
                       run_full_pipeline=None)

    engine = he._get_local_guardrail_engine()
    assert isinstance(engine, _SpyEngine)


def test_fallback_invoca_check_input(
    monkeypatch: pytest.MonkeyPatch, opencode_guardrails_absent: None
) -> None:
    """(a) El engine LOCAL recibe la tarea (``check_input`` invocado).

    Assert discriminante: si se revierte a "warning y continuar", el engine
    local NO se invoca y este test falla.
    """
    created: list[_SpyEngine] = []

    def _factory(*args: object, **kwargs: object) -> _SpyEngine:
        engine = _SpyEngine()
        created.append(engine)
        return engine

    monkeypatch.setattr("harness.guardrails.GuardrailEngine", _factory)

    he._run_guardrails("tarea benigna", "builder", _mock_ctx(), "local",
                       run_full_pipeline=None)

    assert created, "El engine LOCAL no fue instanciado (revertido a fail-open)."
    assert created[0].check_input.call_count >= 1, (
        "El engine LOCAL no evaluo la tarea (revertido a fail-open)."
    )


# ---------------------------------------------------------------------------
# (b) Fail-closed cuando AMBOS engines estan ausentes
# ---------------------------------------------------------------------------


def test_fail_closed_cuando_ambos_ausentes(monkeypatch: pytest.MonkeyPatch) -> None:
    """(b) Sin engine externo ni local -> fail-closed (SystemExit).

    WHAT: si el externo no esta y el engine local tampoco carga, se BLOQUEA.
    WHY: operar sin validar seguridad es inaceptable (failing-open prohibido).
    WHERE: ``handlers_extra._fail_closed_no_engine``.
    """
    assert he.FAIL_CLOSED_ON_NO_ENGINE is True

    def _boom(*args: object, **kwargs: object) -> object:
        raise ImportError("engine local no disponible (simulado)")

    monkeypatch.setattr(he, "_get_local_guardrail_engine", _boom)

    with pytest.raises(SystemExit):
        he._run_guardrails("tarea", "builder", _mock_ctx(), "local",
                           run_full_pipeline=None)


def test_fail_closed_puede_desactivarse(monkeypatch: pytest.MonkeyPatch) -> None:
    """(b) Con ``FAIL_CLOSED_ON_NO_ENGINE=False`` degrada con WARNING (no sale).

    Documenta el unico camino de degradacion explicito y consciente.
    """
    monkeypatch.setattr(he, "FAIL_CLOSED_ON_NO_ENGINE", False)

    def _boom(*args: object, **kwargs: object) -> object:
        raise ImportError("engine local no disponible (simulado)")

    monkeypatch.setattr(he, "_get_local_guardrail_engine", _boom)

    # No debe lanzar SystemExit cuando el fail-closed esta desactivado.
    he._run_guardrails("tarea", "builder", _mock_ctx(), "local",
                       run_full_pipeline=None)


# ---------------------------------------------------------------------------
# (c) Registro idempotente de hooks builtin (audit_logger)
# ---------------------------------------------------------------------------


def test_register_builtin_hooks_idempotente(monkeypatch: pytest.MonkeyPatch) -> None:
    """(c) ``_ensure_builtin_hooks_registered`` registra audit_logger una vez.

    WHAT: 2 invocaciones -> 1 registro (la segunda no re-registra).
    WHY: el runtime debe activar audit_logger sin duplicar hooks.
    WHERE: ``handlers_extra._ensure_builtin_hooks_registered``.
    """
    from harness.hooks.hook_registry import HookRegistry

    reg = HookRegistry.get_instance()
    reg.clear()
    monkeypatch.setattr(he, "_BUILTIN_HOOKS_REGISTERED", False)

    first = he._ensure_builtin_hooks_registered()
    second = he._ensure_builtin_hooks_registered()

    assert first == 4, f"Se esperaban 4 hooks builtin, got {first}"
    assert second == 0, "La segunda invocacion no debe re-registrar hooks"
    assert reg.get_hook("audit_logger") is not None


def test_run_guardrails_registra_hooks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """(c) ``_run_guardrails`` activa los hooks builtin en runtime."""
    from harness.hooks.hook_registry import HookRegistry

    reg = HookRegistry.get_instance()
    reg.clear()
    monkeypatch.setattr(he, "_BUILTIN_HOOKS_REGISTERED", False)
    monkeypatch.setattr("harness.guardrails.GuardrailEngine", _SpyEngine)

    he._run_guardrails("tarea benigna", "builder", _mock_ctx(), "local",
                       run_full_pipeline=None)

    assert reg.get_hook("audit_logger") is not None


# ---------------------------------------------------------------------------
# (d) Mutacion: el antiguo "warning y continuar" ya no es aceptable
# ---------------------------------------------------------------------------


def test_mutacion_fail_open_es_detectada(monkeypatch: pytest.MonkeyPatch) -> None:
    """(d) Revertir a "warning y continuar" hace fallar la suite.

    El comportamiento legal hoy es fail-closed. Si alguien reintroduce el
    camino fail-open (return silencioso) este test NO lanzaria SystemExit.
    """
    def _boom(*args: object, **kwargs: object) -> object:
        raise ImportError("engine local no disponible (simulado)")

    monkeypatch.setattr(he, "_get_local_guardrail_engine", _boom)

    with pytest.raises(SystemExit):
        he._run_guardrails("tarea de riesgo", "builder", _mock_ctx(), "local",
                           run_full_pipeline=None)


# ---------------------------------------------------------------------------
# Regresion: pipeline_guard (FR-0007) sigue conectado
# ---------------------------------------------------------------------------


def test_pipeline_guard_sigue_conectado() -> None:
    """FR-0007: ``ParallelExecutor`` sigue cableando ``PipelineGuard``."""
    from harness.guardrails.pipeline_guard import PipelineGuard
    from harness.orchestrator.parallel_executor import ParallelExecutor

    executor = ParallelExecutor(provider=MagicMock(), router=MagicMock())
    assert isinstance(executor._guard, PipelineGuard)
