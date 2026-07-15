"""Tests para AgentBus."""
from __future__ import annotations
import pytest


class TestAgentBus:
    def test_post_message(self, agent_bus):
        msg_id = agent_bus.post_message("#test", "@a", "@b", "hello", "notification")
        assert msg_id is not None
        assert isinstance(msg_id, str)
        assert len(msg_id) > 0

    def test_invalid_channel(self, agent_bus):
        with pytest.raises(Exception):
            agent_bus.post_message("bad", "@a", "@b", "x", "notification")

    def test_poll_channel(self, agent_bus):
        agent_bus.post_message("#ch", "@a", "@b", "msg1", "notification")
        agent_bus.post_message("#ch", "@a", "@b", "msg2", "notification")
        msgs = agent_bus.poll_channel("#ch", "@b")
        assert len(msgs) >= 1

    def test_count_iterations(self, agent_bus):
        tid = "task-001"
        agent_bus.post_message("#t", "@a", "@b", "e1", "error", task_id=tid)
        agent_bus.post_message("#t", "@a", "@b", "e2", "error", task_id=tid)
        assert agent_bus.count_iterations(tid) >= 2

    def test_circuit_breaker(self, agent_bus):
        tid = "cb-001"
        for i in range(5):
            agent_bus.post_message("#t", "@a", "@b", f"e{i}", "error", task_id=tid)
        assert agent_bus.check_circuit_breaker(tid, max_iterations=5) is True
        assert agent_bus.check_circuit_breaker(tid, max_iterations=10) is False

    def test_message_by_id(self, agent_bus):
        mid = agent_bus.post_message("#t", "@a", "@b", "test", "notification")
        msg = agent_bus.get_message_by_id(mid)
        assert msg is not None
        assert msg["message"] == "test"

    # ── New tests for refactored methods ──

    def test_update_message_status(self, agent_bus):
        """update_message_status reemplaza mark_delivered/mark_acknowledged."""
        mid = agent_bus.post_message("#t", "@a", "@b", "status test", "notification")
        assert agent_bus.update_message_status(mid, "delivered") is True

    def test_update_message_status_invalid(self, agent_bus):
        """Estado invalido debe retornar False."""
        mid = agent_bus.post_message("#t", "@a", "@b", "bad status", "notification")
        assert agent_bus.update_message_status(mid, "invalid_status") is False

    def test_mark_delivered_backward_compat(self, agent_bus):
        """mark_delivered debe seguir funcionando (delega en update_message_status)."""
        mid = agent_bus.post_message("#t", "@a", "@b", "delivered test", "notification")
        assert agent_bus.mark_delivered(mid) is True

    def test_mark_acknowledged_backward_compat(self, agent_bus):
        """mark_acknowledged debe seguir funcionando."""
        mid = agent_bus.post_message("#t", "@a", "@b", "ack test", "notification")
        assert agent_bus.mark_acknowledged(mid) is True

    def test_post_message_batch(self, agent_bus):
        """post_message_batch con multiples mensajes."""
        ids = agent_bus.post_message_batch([
            {"channel": "#batch", "from_agent": "@a", "to_agent": "@b",
             "message": "batch1", "message_type": "notification"},
            {"channel": "#batch", "from_agent": "@b", "to_agent": "@c",
             "message": "batch2", "message_type": "request"},
        ])
        assert len(ids) == 2
        assert all(isinstance(i, str) for i in ids)

    def test_post_message_batch_empty(self, agent_bus):
        """Batch vacio debe retornar lista vacia."""
        assert agent_bus.post_message_batch([]) == []

    def test_get_thread(self, agent_bus):
        """get_thread debe retornar mensajes del mismo thread."""
        mid = agent_bus.post_message("#t", "@a", "@b", "thread msg", "request")
        # Get thread by the auto-generated thread_id
        msg = agent_bus.get_message_by_id(mid)
        thread = agent_bus.get_thread(msg["thread_id"])
        assert len(thread) >= 1

    def test_get_channel_history(self, agent_bus):
        """get_channel_history debe retornar historial del canal."""
        agent_bus.post_message("#history", "@a", "@b", "hist1", "notification")
        agent_bus.post_message("#history", "@a", "@b", "hist2", "notification")
        history = agent_bus.get_channel_history("#history")
        assert len(history) >= 2

    def test_escalate(self, agent_bus):
        """escalate debe crear un mensaje de escalacion."""
        mid = agent_bus.escalate(task_id="esc-001", message="Urgent help needed")
        assert mid is not None
        msg = agent_bus.get_message_by_id(mid)
        assert msg["message_type"] == "escalation"

    def test_get_channel_list(self, agent_bus):
        """get_channel_list debe listar canales unicos."""
        agent_bus.post_message("#chanA", "@a", "@b", "test", "notification")
        agent_bus.post_message("#chanB", "@a", "@b", "test", "notification")
        channels = agent_bus.get_channel_list()
        assert "#chanA" in channels
        assert "#chanB" in channels

    def test_get_tasks_with_errors(self, agent_bus):
        """get_tasks_with_errors debe listar task_id con errores."""
        agent_bus.post_message("#t", "@a", "@b", "err", "error", task_id="err-task")
        tasks = agent_bus.get_tasks_with_errors()
        assert "err-task" in tasks

    def test_build_message_payload(self, agent_bus):
        """_build_message_payload debe generar metadata completa."""
        payload = agent_bus._build_message_payload(
            channel="#test", from_agent="@a", to_agent="@b",
            message="payload test", message_type="request",
            msg_id="custom-id",
        )
        assert payload["id"] == "custom-id"
        assert payload["channel"] == "#test"
        assert payload["message"] == "payload test"
        assert payload["message_type"] == "request"
        assert payload["status"] == "sent"

    def test_search_messages(self, agent_bus):
        """_search_messages debe manejar busquedas con filtros."""
        agent_bus.post_message("#search", "@x", "@y", "searchable msg", "notification")
        results = agent_bus._search_messages(
            filters={"channel": "#search"},
            top_k=10,
        )
        assert len(results) >= 1

    # ── Tests for bugfix: poll_channel debe incluir @all ──

    def test_poll_channel_incluye_atall(self, agent_bus):
        """poll_channel para un agente debe incluir mensajes @all del mismo canal."""
        agent_bus.post_message("#swarm", "@coordinator", "@all",
                               "📋 NUEVO PLAN: tarea X", "notification")
        agent_bus.post_message("#swarm", "@coordinator", "@builder",
                               "🎯 TU TAREA: codificar modulo", "request")

        msgs = agent_bus.poll_channel("#swarm", "@builder")
        # Debe encontrar AMBOS mensajes (el @all + el directo)
        messages_text = " || ".join(m["message"] for m in msgs)
        assert "NUEVO PLAN" in messages_text, (
            f"Mensaje @all no aparecio en poll de @builder: {messages_text}"
        )
        assert "TU TAREA" in messages_text, (
            f"Mensaje directo no aparecio: {messages_text}"
        )

    def test_poll_channel_atall_dedup(self, agent_bus):
        """poll_channel no debe duplicar mensajes @all si ya llegaron como directos."""
        agent_bus.post_message("#dedup", "@coordinator", "@all",
                               "PLAN: tarea Y", "notification")
        # El mismo mensaje conceptual llega como @all y luego como directo
        msgs = agent_bus.poll_channel("#dedup", "@coordinator")
        messages = [m["message"] for m in msgs]
        assert "PLAN: tarea Y" in messages
        # Contar ocurrencias exactas
        count = sum(1 for m in messages if m == "PLAN: tarea Y")
        assert count == 1, f"Mensaje duplicado {count} veces en poll de @coordinator"

    def test_poll_channel_only_own_channel(self, agent_bus):
        """poll_channel solo debe retornar mensajes del canal solicitado."""
        agent_bus.post_message("#canal-A", "@c", "@all", "msg en A", "notification")
        agent_bus.post_message("#canal-B", "@c", "@builder", "msg en B", "notification")

        msgs_a = agent_bus.poll_channel("#canal-A", "@builder")
        msgs_b = agent_bus.poll_channel("#canal-B", "@builder")

        msgs_a_text = [m["message"] for m in msgs_a]
        msgs_b_text = [m["message"] for m in msgs_b]

        assert "msg en A" in msgs_a_text
        assert "msg en B" not in msgs_a_text, "Mensaje de otro canal filtro incorrecto"
        assert "msg en B" in msgs_b_text
