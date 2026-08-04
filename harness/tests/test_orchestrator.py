"""Tests for TaskOrchestrator — Plan-and-Execute orchestration."""

import asyncio
import re
import time
from unittest.mock import patch

import pytest

from harness.memory_rag.lance_vector_store import LanceVectorStore
from harness.orchestrator.task_orchestrator import TaskOrchestrator


class TestTaskOrchestrator:
    """Verify the orchestration pipeline."""

    def setup_method(self):
        # Store in-memory determinista: sin store, TaskOrchestrator crea un
        # LanceDB en disco (harness/db/lancedb) cuyo commit es flaky en CI
        # (Windows: "Acceso denegado" al escribir el version hint). El fallback
        # in-memory hace el bus 100% determinista y los asserts reales.
        with patch.object(
            LanceVectorStore, "_try_import_lancedb", return_value=None
        ):
            store = LanceVectorStore(db_path="/tmp/test_mem", allow_fallback=True)
        self.orch = TaskOrchestrator(vector_store=store)

    @pytest.mark.asyncio
    async def test_process_message_new_task(self):
        """New task → plan created with subtasks."""
        result = await self.orch.process_message("implementa una API REST en Rust")
        assert result is not None
        assert result.session_id is not None
        assert result.is_new_plan is True
        assert len(result.plan.subtasks) >= 3
        assert result.plan.subtasks[0].agent in ("builder", "coordinator")

    @pytest.mark.asyncio
    async def test_process_message_bugfix(self):
        """Bugfix message → scientist + builder plan."""
        result = await self.orch.process_message("fix bug en el login")
        assert result is not None
        assert result.plan.subtasks[0].agent == "scientist"

    @pytest.mark.asyncio
    async def test_process_message_research(self):
        """Research message → scientist plan."""
        result = await self.orch.process_message("investigar patrones de microservicios")
        assert result is not None
        assert result.plan.subtasks[0].agent == "scientist"

    @pytest.mark.asyncio
    async def test_process_message_security(self):
        """Security message → guardian plan."""
        result = await self.orch.process_message("auditar seguridad del sistema")
        assert result is not None
        assert result.plan.subtasks[0].agent == "guardian"

    @pytest.mark.asyncio
    async def test_process_message_current_level(self):
        """New task → current_level has first subtask(s)."""
        result = await self.orch.process_message("implementar API")
        assert len(result.current_level) >= 1
        first = result.current_level[0]
        assert "id" in first
        assert "agent" in first
        assert "description" in first

    @pytest.mark.asyncio
    async def test_process_message_previous_results_empty(self):
        """New task → no previous results."""
        result = await self.orch.process_message("test")
        assert len(result.previous_results) == 0

    @pytest.mark.slow
    @pytest.mark.asyncio
    async def test_process_completion(self):
        """After completing a subtask → next level available."""
        result = await self.orch.process_message("implementar API")
        first_id = result.current_level[0]["id"]

        next_result = await self.orch.process_completion(
            session_id=result.session_id,
            subtask_id=first_id,
            result="API implementada",
        )
        assert next_result is not None
        assert len(next_result.previous_results) >= 1
        assert next_result.previous_results[0]["id"] == first_id

    @pytest.mark.slow
    @pytest.mark.asyncio
    async def test_process_completion_all(self):
        """Complete all subtasks → plan complete."""
        result = await self.orch.process_message("implementar API")
        # Complete all subtasks
        for st in result.plan.subtasks:
            await self.orch.process_completion(
                session_id=result.session_id,
                subtask_id=st.id,
                result="done",
            )

        session = self.orch._session_ctx.get_session(result.session_id)
        assert session is not None
        assert session.completed is True

    @pytest.mark.asyncio
    async def test_get_summary_active(self):
        """Summary of active session."""
        result = await self.orch.process_message("implementar API")
        summary = await self.orch.get_summary(result.session_id)
        assert summary is not None
        assert "implementar API" in summary or "API" in summary

    @pytest.mark.asyncio
    async def test_get_summary_no_session(self):
        """Summary without session → message."""
        summary = await self.orch.get_summary("nonexistent")
        assert summary is not None

    @pytest.mark.asyncio
    async def test_target_agent_builder(self):
        """Implementation task → plan incluye builder y target coordinator (swarm)."""
        result = await self.orch.process_message("implementar API en Rust")
        assert result is not None
        # SWARM: nivel 0 con multiples agentes → dispatcher coordinador
        assert result.target_agent == "coordinator"
        assert len(result.current_level) >= 1
        assert any(st.agent == "builder" for st in result.plan.subtasks), (
            "El plan deberia contener una subtask del builder: "
            f"{[st.agent for st in result.plan.subtasks]}"
        )

    @pytest.mark.slow
    @pytest.mark.asyncio
    async def test_target_agent_scientist(self):
        """Research task → target agent es scientist con subtask propia."""
        result = await self.orch.process_message("investigar patrones")
        assert result is not None
        assert result.target_agent == "scientist"
        assert any(st.agent == "scientist" for st in result.plan.subtasks), (
            f"El plan deberia contener una subtask del scientist: "
            f"{[st.agent for st in result.plan.subtasks]}"
        )
        assert any(i["agent"] == "scientist" for i in result.current_level), (
            f"El nivel 0 deberia despachar al scientist: {result.current_level}"
        )

    @pytest.mark.slow
    @pytest.mark.asyncio
    async def test_target_agent_guardian(self):
        """Security task → target agent es guardian con subtask propia."""
        result = await self.orch.process_message("auditar seguridad")
        assert result is not None
        assert result.target_agent == "guardian"
        assert any(st.agent == "guardian" for st in result.plan.subtasks), (
            f"El plan deberia contener una subtask del guardian: "
            f"[{', '.join(st.agent for st in result.plan.subtasks)}]"
        )
        assert any(i["agent"] == "guardian" for i in result.current_level), (
            f"El nivel 0 deberia despachar al guardian: {result.current_level}"
        )

    @pytest.mark.asyncio
    async def test_orchestrator_result_dict(self):
        """OrchestratorResult can be serialized to dict."""
        result = await self.orch.process_message("test")
        d = result.to_dict()
        assert d["session_id"] == result.session_id
        assert d["target_agent"] == result.target_agent
        assert "plan" in d
        assert "current_level" in d
        assert "previous_results" in d
        assert "is_new_plan" in d
        assert "is_complete" in d

    # ── Tests for bugfix: 3 agentes con mismo request ──

    @pytest.mark.slow
    @pytest.mark.asyncio
    async def test_broadcast_plan_envia_subtask_especifica(self):
        """Cada agente recibe SU subtask especifica (request con SubtaskID), no el generico @all."""
        result = await self.orch.process_message("implementar una API REST en Rust")
        session = self.orch._session_ctx.get_session(result.session_id)
        assert session is not None
        assert session.plan is not None
        assert len(session.plan.subtasks) >= 3

        bus = self.orch._bus
        channel = f"#session-{session.session_id}"
        agents = sorted({f"@{st.agent}" for st in session.plan.subtasks})
        assert agents, "El plan no define agentes"

        # Agentes con subtask "ready" en el nivel actual: el source
        # (_broadcast_plan_async) solo envia 'request' a estos; el resto recibe
        # 'notification' ("Asignado al plan..."). current_level == next_level.
        ready_agents = {f"@{item['agent']}" for item in result.current_level}
        assert ready_agents, (
            f"El nivel actual no despacha a ningun agente: {result.current_level}"
        )
        idle_agents = set(agents) - ready_agents

        # Poll determinista (~50ms x hasta 2s): esperar el broadcast async en el
        # historial del canal. Si el bus nunca entrega los requests, el test FALLA.
        all_msgs: list[dict] = []
        deadline = time.monotonic() + 2.0
        while time.monotonic() < deadline:
            all_msgs = bus.get_channel_history(channel)
            requests = [m for m in all_msgs if m.get("message_type") == "request"]
            received = {m.get("to_agent") for m in requests}
            if ready_agents.issubset(received):
                break
            await asyncio.sleep(0.05)

        requests = [m for m in all_msgs if m.get("message_type") == "request"]
        # Assert incondicional: sin mensajes el test falla (nada de if agent_msgs:)
        assert requests, (
            f"El bus no emitio ningun mensaje 'request' en {channel}: {all_msgs}"
        )

        # 1) El generico @all jamas llega como 'request' (el source lo publica
        #    como 'notification' con "NUEVO PLAN"; el request lleva "TU TAREA").
        for msg in requests:
            assert msg.get("to_agent") != "@all", (
                f"El mensaje generico @all no debe llegar como request: {msg}"
            )

        # 2) Cada agente ready recibe >= 1 request propio con SU SubtaskID.
        #    Contrato ASCII estable del source (_broadcast_plan_async):
        #    "🎯 TU TAREA: {desc}\nOutput: {out}\nSubtaskID: {id}\nPlan: {sid}".
        for agent in sorted(ready_agents):
            agent_requests = [m for m in requests if m.get("to_agent") == agent]
            assert agent_requests, (
                f"Agente {agent} (ready) no recibio ningun request: {requests}"
            )
            for msg in agent_requests:
                body = msg.get("message", "")
                assert body.strip() != "", f"Request vacio a {agent}: {msg}"
                assert "SubtaskID" in body, f"Request a {agent} sin SubtaskID: {msg}"
                # El SubtaskID del request debe existir en el plan y pertenecer
                # al agente destinatario (no a otro agente del plan).
                m = re.search(r"SubtaskID:\s*(\S+)", body)
                assert m, f"Request a {agent} sin SubtaskID parseable: {msg}"
                subtask = next(
                    (st for st in session.plan.subtasks if st.id == m.group(1)),
                    None,
                )
                assert subtask is not None, (
                    f"Request a {agent} referencia SubtaskID inexistente "
                    f"{m.group(1)!r}: {msg}"
                )
                assert subtask.agent == agent.lstrip("@"), (
                    f"Request a {agent} referencia la subtask del agente "
                    f"{subtask.agent} (deberia ser propia): {msg}"
                )

        # 3) Agentes del plan sin trabajo en el nivel actual: jamas 'request'
        #    (reciben 'notification' "Asignado al plan" y esperan turno).
        for agent in sorted(idle_agents):
            idle_requests = [m for m in requests if m.get("to_agent") == agent]
            assert not idle_requests, (
                f"Agente {agent} sin trabajo en el nivel actual no deberia "
                f"recibir request: {idle_requests}"
            )

    @pytest.mark.slow
    @pytest.mark.asyncio
    async def test_broadcast_plan_no_envia_request_sin_subtask(self):
        """Agentes sin trabajo en el nivel actual reciben notification, no request."""
        result = await self.orch.process_message("implementar API")
        bus = self.orch._bus

        # Todos los mensajes de tipo "request" deben tener SubtaskID en el body
        channel = f"#session-{result.session_id}"
        all_msgs = bus.get_channel_history(channel)
        for msg in all_msgs:
            if msg.get("message_type") == "request":
                body = msg.get("message", "")
                assert "SubtaskID" in body, \
                    f"Request sin SubtaskID en body: {msg}"

    @pytest.mark.asyncio
    async def test_process_message_dedup_rechaza_duplicado(self):
        """Mismo mensaje dentro de ventana de 30s → rechazado."""
        msg = "implementar una tarea unica para test de dedup"
        result1 = await self.orch.process_message(msg)
        assert result1.is_new_plan is True

        result2 = await self.orch.process_message(msg)
        # El segundo debe ser rechazado por dedup (mensaje duplicado)
        assert result2.is_new_plan is False, "Debe ser rechazado, no nuevo plan"
        # El session_status debe contener el mensaje de error por duplicado
        status = result2.session_status.lower()
        assert "duplicado" in status or "duplicate" in status, (
            f"Status deberia mencionar duplicado: {result2.session_status}"
        )

    @pytest.mark.slow
    @pytest.mark.asyncio
    async def test_process_message_dedup_permite_diferente(self):
        """Mensajes diferentes NO son rechazados por dedup."""
        r1 = await self.orch.process_message("hacer tarea A")
        assert r1.is_new_plan is True

        r2 = await self.orch.process_message("hacer tarea B")
        assert r2.is_new_plan is True  # mensaje diferente → permitido

    @pytest.mark.asyncio
    async def test_process_message_min_len_respected(self):
        """Mensaje vacio o muy corto no deberia romper dedup."""
        result = await self.orch.process_message("x")
        # No deberia explotar
        assert result is not None


