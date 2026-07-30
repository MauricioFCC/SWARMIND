"""
Tests para Refinement Types en AgentBus.

Verifica que las validaciones tipo-refinement (fail-fast con assert)
en post_message, AsyncAgentBus.post_message y AsyncAgentBus.consume
detectan parametros invalidos correctamente.

Regla: NO modificar comportamiento existente, solo agregar validaciones.
"""
from __future__ import annotations

import pytest

from harness.orchestrator.agent_bus import (
    _VALID_MESSAGE_TYPES,
    AgentBus,
    AsyncAgentBus,
)


class TestAgentBusPostMessageRefinement:
    """Refinement-type validations en AgentBus.post_message."""

    def test_refinement_channel_empty(self, agent_bus: AgentBus) -> None:
        """Canal vacio debe lanzar AssertionError."""
        with pytest.raises(AssertionError, match="channel must not be empty"):
            agent_bus.post_message(
                channel="", from_agent="@a", to_agent="@b",
                message="test", message_type="notification",
            )

    def test_refinement_from_agent_empty(self, agent_bus: AgentBus) -> None:
        """from_agent vacio debe lanzar AssertionError."""
        with pytest.raises(AssertionError, match="from_agent must not be empty"):
            agent_bus.post_message(
                channel="#ch", from_agent="", to_agent="@b",
                message="test", message_type="notification",
            )

    def test_refinement_to_agent_empty(self, agent_bus: AgentBus) -> None:
        """to_agent vacio debe lanzar AssertionError."""
        with pytest.raises(AssertionError, match="to_agent must not be empty"):
            agent_bus.post_message(
                channel="#ch", from_agent="@a", to_agent="",
                message="test", message_type="notification",
            )

    def test_refinement_message_empty(self, agent_bus: AgentBus) -> None:
        """message vacio debe lanzar AssertionError."""
        with pytest.raises(AssertionError, match="message must not be empty"):
            agent_bus.post_message(
                channel="#ch", from_agent="@a", to_agent="@b",
                message="", message_type="notification",
            )

    @pytest.mark.parametrize("invalid_type", [
        "invalid", "", "REQUEST", "Error", "escalation ",
    ])
    def test_refinement_invalid_message_type(
        self, agent_bus: AgentBus, invalid_type: str,
    ) -> None:
        """Tipo de mensaje invalido debe lanzar AssertionError."""
        with pytest.raises(AssertionError, match="invalid message_type"):
            agent_bus.post_message(
                channel="#ch", from_agent="@a", to_agent="@b",
                message="test", message_type=invalid_type,
            )

    @pytest.mark.parametrize("valid_type", sorted(_VALID_MESSAGE_TYPES))
    def test_refinement_valid_message_types_pass(
        self, agent_bus: AgentBus, valid_type: str,
    ) -> None:
        """Todos los tipos de mensaje validos deben pasar."""
        msg_id = agent_bus.post_message(
            channel="#ch", from_agent="@a", to_agent="@b",
            message="test", message_type=valid_type,
        )
        assert msg_id is not None
        assert isinstance(msg_id, str)

    def test_refinement_iteration_negative(self, agent_bus: AgentBus) -> None:
        """iteration negativa debe lanzar AssertionError."""
        with pytest.raises(AssertionError, match="iteration must be >= 0"):
            agent_bus.post_message(
                channel="#ch", from_agent="@a", to_agent="@b",
                message="test", message_type="notification",
                iteration=-1,
            )

    def test_refinement_iteration_zero_valid(self, agent_bus: AgentBus) -> None:
        """iteration=0 debe ser valido."""
        msg_id = agent_bus.post_message(
            channel="#ch", from_agent="@a", to_agent="@b",
            message="test", message_type="notification",
            iteration=0,
        )
        assert msg_id is not None

    def test_refinement_iteration_positive_valid(self, agent_bus: AgentBus) -> None:
        """iteration positiva debe ser valido."""
        msg_id = agent_bus.post_message(
            channel="#ch", from_agent="@a", to_agent="@b",
            message="test", message_type="notification",
            iteration=5,
        )
        assert msg_id is not None

    def test_refinement_valid_call_still_works(self, agent_bus: AgentBus) -> None:
        """Una llamada valida debe seguir funcionando exactamente como antes."""
        msg_id = agent_bus.post_message(
            channel="#test", from_agent="@builder", to_agent="@quality-gate",
            message="Hello from refinement test", message_type="request",
            task_id="ref-001",
        )
        assert msg_id is not None
        assert isinstance(msg_id, str)
        assert len(msg_id) > 0
        # Verificar que el mensaje se almaceno correctamente
        msg = agent_bus.get_message_by_id(msg_id)
        assert msg is not None
        assert msg["message"] == "Hello from refinement test"
        assert msg["message_type"] == "request"

    def test_refinement_empty_message_with_valid_validation(self, agent_bus: AgentBus) -> None:
        """El assert de message vacio debe lanzar AssertionError incluso sin llamar a _validate."""
        with pytest.raises(AssertionError, match="message must not be empty"):
            agent_bus.post_message(
                channel="#ch", from_agent="@a", to_agent="@b",
                message="", message_type="notification",
            )


class TestAsyncAgentBusRefinement:
    """Refinement-type validations en AsyncAgentBus."""

    @pytest.mark.asyncio
    async def test_post_message_channel_empty(self) -> None:
        """AsyncAgentBus.post_message con canal vacio debe lanzar AssertionError."""
        bus = AsyncAgentBus()
        with pytest.raises(AssertionError, match="channel must be a non-empty string"):
            await bus.post_message(channel="", message="test")

    @pytest.mark.asyncio
    async def test_post_message_channel_valid(self) -> None:
        """AsyncAgentBus.post_message con canal valido debe funcionar."""
        bus = AsyncAgentBus()
        await bus.post_message(channel="#valid", message="test")
        assert bus.get_queue_size("#valid") == 1

    @pytest.mark.asyncio
    async def test_consume_channel_empty(self) -> None:
        """AsyncAgentBus.consume con canal vacio debe lanzar AssertionError."""
        bus = AsyncAgentBus()
        with pytest.raises(AssertionError, match="channel must be a non-empty string"):
            await bus.consume(channel="", timeout=1.0)

    @pytest.mark.asyncio
    async def test_consume_timeout_zero(self) -> None:
        """AsyncAgentBus.consume con timeout <= 0 debe lanzar AssertionError."""
        bus = AsyncAgentBus()
        with pytest.raises(AssertionError, match="timeout must be > 0"):
            await bus.consume(channel="#ch", timeout=0)

    @pytest.mark.asyncio
    async def test_consume_timeout_negative(self) -> None:
        """AsyncAgentBus.consume con timeout negativo debe lanzar AssertionError."""
        bus = AsyncAgentBus()
        with pytest.raises(AssertionError, match="timeout must be > 0"):
            await bus.consume(channel="#ch", timeout=-5.0)

    @pytest.mark.asyncio
    async def test_consume_timeout_valid(self) -> None:
        """AsyncAgentBus.consume con timeout valido debe funcionar (timeout si no hay mensajes)."""
        bus = AsyncAgentBus()
        with pytest.raises(Exception):  # noqa: B017  # TimeoutError o similares
            await bus.consume(channel="#ch", timeout=0.01)
