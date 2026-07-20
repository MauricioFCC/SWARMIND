"""Tests para AsyncAgentBus (PaCoRe — ADR-0017)."""
from __future__ import annotations

import asyncio
from typing import Any

import pytest

from harness.orchestrator.agent_bus import AsyncAgentBus


class TestAsyncAgentBus:
    """Suite de tests para AsyncAgentBus con canales asincronos."""

    @pytest.mark.asyncio
    async def test_post_and_consume(self) -> None:
        """
        Post de un mensaje seguido de consume en el mismo canal.

        Verifica que el mensaje publicado se recibe correctamente
        por el consumidor en el mismo canal.
        """
        bus = AsyncAgentBus()
        expected = {"data": "hello_pacore"}

        await bus.post_message("test-channel", expected)
        result = await bus.consume("test-channel", timeout=5.0)

        assert result == expected

    @pytest.mark.asyncio
    async def test_consume_timeout(self) -> None:
        """
        Consume sin mensaje disponible lanza asyncio.TimeoutError.

        Verifica que al intentar consumir de un canal vacio
        con timeout corto se lance la excepcion correspondiente.
        """
        bus = AsyncAgentBus()

        with pytest.raises(asyncio.TimeoutError):
            await bus.consume("empty-channel", timeout=0.1)

    @pytest.mark.asyncio
    async def test_multiple_channels(self) -> None:
        """
        Canales independientes no interfieren entre si.

        Verifica que post/consume en un canal no afecta
        los mensajes de otro canal.
        """
        bus = AsyncAgentBus()
        msg_a = "mensaje_A"
        msg_b = "mensaje_B"

        await bus.post_message("canal-a", msg_a)
        await bus.post_message("canal-b", msg_b)

        result_a = await bus.consume("canal-a", timeout=5.0)
        result_b = await bus.consume("canal-b", timeout=5.0)

        assert result_a == msg_a
        assert result_b == msg_b

    @pytest.mark.asyncio
    async def test_get_queue_size(self) -> None:
        """
        Queue size refleja la cantidad de mensajes en cola.

        Verifica que get_queue_size retorna 0 para canales vacios
        y el tamano correcto tras posts.
        """
        bus = AsyncAgentBus()

        assert bus.get_queue_size("metrics") == 0

        await bus.post_message("metrics", "alpha")
        assert bus.get_queue_size("metrics") == 1

        await bus.post_message("metrics", "beta")
        assert bus.get_queue_size("metrics") == 2

        await bus.consume("metrics", timeout=5.0)
        assert bus.get_queue_size("metrics") == 1

    @pytest.mark.asyncio
    async def test_concurrent_post(self) -> None:
        """
        Post desde multiples corrutinas concurrentes.

        Verifica que asyncio.gather con N posts concurrentes
        encola todos los mensajes correctamente sin condicion de carrera.
        """
        bus = AsyncAgentBus()
        num_messages = 10
        channel = "concurrent-test"

        async def _post(msg_id: int) -> None:
            await bus.post_message(channel, f"msg-{msg_id}")

        await asyncio.gather(*[_post(i) for i in range(num_messages)])

        assert bus.get_queue_size(channel) == num_messages

        received: list[Any] = []
        for _ in range(num_messages):
            msg = await bus.consume(channel, timeout=5.0)
            received.append(msg)

        assert len(received) == num_messages
        assert all("msg-" in str(r) for r in received)
