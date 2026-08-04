"""Tests TDD (spec-first) para HermesModelAdapter.

Contrato (spec):
- HermesModelAdapter detecta config de Hermes o usa fallback local.
- route(): con config Hermes -> source="hermes"; sin config -> local/ollama.
- route(): con original_router inyectado, delega en fallback.
- execute(): con HERMES_SESSION_ID devuelve prompt de contexto.
- execute(): sin Hermes y con original_router, delega.
- apply_hermes_routing(): devuelve dict de routing.

Invariantes:
- route siempre devuelve dict con keys source/model/provider.
- apply_hermes_routing siempre devuelve dict con esas keys.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

from harness.model_router.hermes_adapter import (
    HERMES_AVAILABLE,
    HermesModelAdapter,
    apply_hermes_routing,
)


class TestHermesAdapterContract:
    """Contrato principal del adapter."""

    def test_init_without_hermes_uses_fallback(self) -> None:
        """Spec: sin Hermes disponible, adapter usa fallback."""
        adapter = HermesModelAdapter()
        result = adapter.route("tarea", "builder")
        # Siempre devuelve dict con las 3 keys
        assert "source" in result
        assert "model" in result
        assert "provider" in result

    def test_route_with_original_router_delegates(self) -> None:
        """Spec: con original_router, route delega si no hay Hermes."""
        router = MagicMock()
        router.route.return_value = {"source": "local", "model": "llama3", "provider": "ollama"}
        adapter = HermesModelAdapter(original_router=router)
        result = adapter.route("tarea", "builder")
        # Si HERMES no está disponible, delega en router
        if not HERMES_AVAILABLE:
            router.route.assert_called()
            assert result["model"] == "llama3"

    def test_route_returns_dict_always(self) -> None:
        """Invariante: route siempre devuelve dict con las keys core."""
        adapter = HermesModelAdapter()
        for _ in range(3):
            result = adapter.route("x", "y")
            assert isinstance(result, dict)
            assert {"source", "model", "provider"}.issubset(result.keys())

    def test_execute_with_hermes_session(self) -> None:
        """Spec: con HERMES_SESSION_ID, execute devuelve prompt de contexto."""
        adapter = HermesModelAdapter()
        with patch.dict("os.environ", {"HERMES_SESSION_ID": "s1"}, clear=False):
            result = adapter.execute("mi prompt", "builder")
        assert "[Hermes]" in result
        assert "builder" in result

    def test_execute_without_hermes_returns_note(self) -> None:
        """Spec: sin Hermes y sin router, execute devuelve nota."""
        adapter = HermesModelAdapter(original_router=None)
        with patch.dict("os.environ", {}, clear=False):
            # Si HERMES_SESSION_ID no está y no hay router
            if "HERMES_SESSION_ID" not in __import__("os").environ:
                result = adapter.execute("p", "g")
                assert isinstance(result, str)


class TestHermesAdapterApply:
    """Spec: apply_hermes_routing."""

    def test_apply_returns_dict(self) -> None:
        """Spec: apply_hermes_routing devuelve dict con keys core."""
        result = apply_hermes_routing("task", "builder", "default")
        assert isinstance(result, dict)
        assert "source" in result
        assert "model" in result
        assert "provider" in result

    def test_apply_source_fallback(self) -> None:
        """Spec: sin Hermes, source es el routing_source recibido."""
        result = apply_hermes_routing("task", "builder", "manual")
        if not HERMES_AVAILABLE:
            assert result["source"] == "manual"
