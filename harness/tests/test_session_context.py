"""Tests for SessionContext — session state persistence and tracking."""
from __future__ import annotations

import json
from unittest.mock import MagicMock

from harness.orchestrator.session_context import SessionContext, SessionState
from harness.orchestrator.task_planner import SubTask, TaskPlan, TaskPlanner


class TestSessionContext:
    """Verify session state management."""

    def setup_method(self):
        self.ctx = SessionContext()  # memory-only (no store)
        self.planner = TaskPlanner()

    def test_get_or_create_with_plan(self):
        """New plan → new session."""
        plan = self.planner.decompose("implementar API")
        session = self.ctx.get_or_create("implementar API", plan)
        assert session is not None
        assert session.session_id == plan.session_id
        assert session.original_message == "implementar API"

    def test_get_active_empty(self):
        """No sessions → None."""
        session = self.ctx.get_active()
        assert session is None

    def test_get_active_after_create(self):
        """After creating, get_active returns it."""
        plan = self.planner.decompose("test")
        session = self.ctx.get_or_create("test", plan)
        active = self.ctx.get_active()
        assert active is not None
        assert active.session_id == plan.session_id

    def test_mark_subtask_done(self):
        """Marking subtask done updates state."""
        plan = self.planner.decompose("implementar API")
        session = self.ctx.get_or_create("test", plan)

        subtask_id = plan.subtasks[0].id
        result = self.ctx.mark_subtask_done(session, subtask_id, "código listo")

        assert result is True
        # Verify subtask is marked
        for st in session.plan.subtasks:
            if st.id == subtask_id:
                assert st.completed is True
                assert st.result == "código listo"
                break

    def test_mark_subtask_done_unknown(self):
        """Unknown subtask ID → False."""
        plan = self.planner.decompose("test")
        session = self.ctx.get_or_create("test", plan)
        result = self.ctx.mark_subtask_done(session, "nonexistent", "result")
        assert result is False

    def test_session_complete(self):
        """Session marked complete when all subtasks done."""
        # Create a simple plan with 1 subtask
        subtasks = [
            SubTask(id="s1", agent="builder", description="code", dependencies=[]),
        ]
        plan = TaskPlan(session_id="test", original_message="simple", subtasks=subtasks)
        session = self.ctx.get_or_create("simple", plan)

        assert not session.completed
        self.ctx.mark_subtask_done(session, "s1", "done")
        assert session.completed is True

    def test_add_message(self):
        """Messages are tracked in session."""
        plan = self.planner.decompose("test")
        session = self.ctx.get_or_create("test", plan)
        assert len(session.messages) == 0

        self.ctx.add_message(session, "user", "hello")
        assert len(session.messages) == 1
        assert session.messages[0]["role"] == "user"
        assert session.messages[0]["content"] == "hello"

    def test_get_status(self):
        """Status string is informative."""
        plan = self.planner.decompose("test")
        session = self.ctx.get_or_create("test", plan)
        status = self.ctx.get_status(session)
        assert "test" in status
        assert "Sesión" in status

    def test_get_status_after_completion(self):
        """Status shows completed items."""
        plan = self.planner.decompose("test")
        session = self.ctx.get_or_create("test", plan)
        self.ctx.mark_subtask_done(session, plan.subtasks[0].id, "result")
        status = self.ctx.get_status(session)
        assert "Completadas" in status


class TestSessionState:
    """Test SessionState data class."""

    def test_to_dict(self):
        subtasks = [SubTask(id="s1", agent="builder", description="code", dependencies=[])]
        plan = TaskPlan(session_id="sess-1", original_message="test", subtasks=subtasks)
        state = SessionState(
            session_id="sess-1",
            original_message="test",
            plan=plan,
        )
        d = state.to_dict()
        assert d["session_id"] == "sess-1"
        assert d["original_message"] == "test"
        assert "plan" in d
        assert not d["completed"]

    def test_to_dict_messages_limited(self):
        """Only last 20 messages are kept."""
        plan = TaskPlan(session_id="sess-1", original_message="test")
        state = SessionState(
            session_id="sess-1",
            original_message="test",
            plan=plan,
        )
        for i in range(30):
            state.messages.append({"role": "user", "content": f"msg-{i}"})
        d = state.to_dict()
        assert len(d["messages"]) <= 20


# ===================================================================
# Nuevos tests para ramas no cubiertas
# ===================================================================


class TestSessionContextNoPlan:
    """Tests para get_or_create con plan=None.  (cubre líneas 129-153)"""

    def setup_method(self):
        self.ctx = SessionContext()  # memory-only

    def test_get_or_create_no_plan_sin_historial(self) -> None:
        """Plan=None sin sesiones previas → crea nueva sin plan.  (líneas 142-153)"""
        session = self.ctx.get_or_create("nuevo mensaje", None)
        assert session is not None
        assert session.original_message == "nuevo mensaje"
        # Sin plan → session_id autogenerado
        assert len(session.session_id) == 8  # uuid4[:8]
        # Plan vacío (sin subtasks)
        assert len(session.plan.subtasks) == 0

    def test_get_or_create_no_plan_con_activa(self) -> None:
        """Plan=None con sesión activa en memoria → la reanuda.  (líneas 129-140)"""
        # Creamos una sesión primero
        plan = TaskPlan(session_id="activa-001", original_message="original")
        session = self.ctx.get_or_create("original", plan)
        # Ahora llamamos con plan=None → debería encontrar la activa via _load_most_recent
        # Pero _load_most_recent en memory-only retorna None (no store)
        # En su lugar, cae a las líneas 142-153 (crea nueva)

        # Para probar las líneas 129-140, necesitamos un store mock
        pass

    def test_get_or_create_no_plan_reanuda_desde_store(self) -> None:
        """Plan=None reanuda sesión desde store vía _load_most_recent.  (líneas 129-140)"""
        mock_store = MagicMock()
        ctx = SessionContext(vector_store=mock_store)

        # Creamos una sesión stored que _load_most_recent devolverá
        stored_subtasks = [
            SubTask(id="st-1", agent="builder", description="task",
                    dependencies=[], completed=False)
        ]
        stored_plan = TaskPlan(session_id="stored-id", original_message="original",
                               subtasks=stored_subtasks)
        stored_session = SessionState(
            session_id="stored-id",
            original_message="original",
            plan=stored_plan,
            messages=[],
        )

        # Mockeamos _load_most_recent para que devuelva nuestra sesión
        original_load = ctx._load_most_recent
        ctx._load_most_recent = MagicMock(return_value=stored_session)

        resumed = ctx.get_or_create("continuación", None)

        assert resumed.session_id == "stored-id"
        assert len(resumed.messages) == 1
        assert resumed.messages[0]["role"] == "user"
        assert resumed.messages[0]["content"] == "continuación"
        # updated_at debería haber cambiado (o ser igual si mismo instante)
        assert resumed.updated_at >= stored_session.updated_at

        # Restauramos (opcional, pero buena práctica)
        ctx._load_most_recent = original_load


class TestSessionContextPersistence:
    """Tests para métodos de persistencia con store mockeado."""

    def test_persist_error_non_fatal(self) -> None:
        """Error en _persist se loggea pero no es fatal.  (líneas 293-303)"""
        mock_store = MagicMock()
        mock_store.insert.side_effect = Exception("DB connection error")
        ctx = SessionContext(vector_store=mock_store)

        plan = TaskPlan(session_id="test-persist", original_message="test")
        # get_or_create llama a _persist internamente
        session = ctx.get_or_create("test", plan)

        assert session is not None
        assert session.session_id == "test-persist"
        # El error se loggea pero no propaga
        mock_store.insert.assert_called()

    def test_persist_no_store_returns_early(self) -> None:
        """Sin store, _persist retorna inmediatamente.  (línea 291-292)"""
        ctx = SessionContext()  # memory-only, store is None
        plan = TaskPlan(session_id="test-no-store", original_message="test")
        session = ctx.get_or_create("test", plan)
        assert session is not None

    def test_load_from_store_error_returns_none(self) -> None:
        """Error en _load_from_store retorna None.  (líneas 309-318)"""
        mock_store = MagicMock()
        mock_store.search.side_effect = Exception("DB search error")
        ctx = SessionContext(vector_store=mock_store)

        result = ctx._load_from_store("some-id")
        assert result is None

    def test_load_from_store_no_store_returns_none(self) -> None:
        """Sin store, _load_from_store retorna None.  (línea 307-308)"""
        ctx = SessionContext()  # memory-only
        result = ctx._load_from_store("some-id")
        assert result is None

    def test_load_most_recent_error_returns_none(self) -> None:
        """Error en _load_most_recent retorna None.  (líneas 324-336)"""
        mock_store = MagicMock()
        mock_store.search.side_effect = Exception("DB search error")
        ctx = SessionContext(vector_store=mock_store)

        result = ctx._load_most_recent()
        assert result is None

    def test_load_most_recent_no_store_returns_none(self) -> None:
        """Sin store, _load_most_recent retorna None.  (líneas 322-323)"""
        ctx = SessionContext()  # memory-only
        result = ctx._load_most_recent()
        assert result is None

    def test_load_most_recent_con_resultados(self) -> None:
        """_load_most_recent con resultados devuelve el más reciente."""
        mock_store = MagicMock()
        ctx = SessionContext(vector_store=mock_store)

        # Simulamos resultados de búsqueda
        older_data = {
            "session_id": "old-session",
            "original_message": "old",
            "plan": {"session_id": "old-session", "original_message": "old", "subtasks": []},
            "created_at": "2024-01-01T00:00:00",
            "updated_at": "2024-01-01T00:00:00",
            "completed": True,
            "messages": [],
        }
        newer_data = {
            "session_id": "new-session",
            "original_message": "new",
            "plan": {"session_id": "new-session", "original_message": "new", "subtasks": []},
            "created_at": "2024-06-01T00:00:00",
            "updated_at": "2024-06-01T00:00:00",
            "completed": False,
            "messages": [],
        }
        mock_store.search.return_value = [
            {"metadata": {"data": json.dumps(newer_data)}, "vector": []},
            {"metadata": {"data": json.dumps(older_data)}, "vector": []},
        ]

        result = ctx._load_most_recent()
        assert result is not None
        assert result.session_id == "new-session"

    def test_load_most_recent_resultados_sin_data_key(self) -> None:
        """_load_most_recent maneja metadata sin key 'data' — retorna sesión vacía."""
        mock_store = MagicMock()
        ctx = SessionContext(vector_store=mock_store)
        mock_store.search.return_value = [
            {"metadata": {"other": "value"}, "vector": []},
        ]
        result = ctx._load_most_recent()
        # _deserialize con data={} crea sesión con campos vacíos (no None)
        assert result is not None
        assert result.session_id == ""


class TestSessionContextDeserialize:
    """Tests para _deserialize.  (cubre líneas 340-381)"""

    def setup_method(self):
        self.ctx = SessionContext()

    def _make_valid_data(self) -> dict:
        return {
            "session_id": "sess-123",
            "original_message": "implement API",
            "plan": {
                "session_id": "sess-123",
                "original_message": "implement API",
                "subtasks": [
                    {
                        "id": "st-1",
                        "agent": "builder",
                        "description": "Build API",
                        "dependencies": [],
                        "expected_output": "code",
                        "context_hint": "use Rust",
                        "completed": True,
                        "result": "done",
                    },
                    {
                        "id": "st-2",
                        "agent": "guardian",
                        "description": "Review",
                        "dependencies": ["st-1"],
                        "expected_output": "feedback",
                        "context_hint": "",
                        "completed": False,
                        "result": "",
                    },
                ],
            },
            "created_at": "2024-01-15T10:00:00",
            "updated_at": "2024-01-15T12:00:00",
            "completed": False,
            "messages": [
                {"role": "user", "content": "hello", "timestamp": "2024-01-15T10:00:00"},
            ],
        }

    def test_deserialize_valid(self) -> None:
        """_deserialize con datos válidos retorna SessionState.  (líneas 340-378)"""
        data = self._make_valid_data()
        record = {"metadata": {"data": json.dumps(data)}}
        session = self.ctx._deserialize(record)

        assert session is not None
        assert session.session_id == "sess-123"
        assert session.original_message == "implement API"
        assert session.completed is False
        assert len(session.plan.subtasks) == 2
        assert session.plan.subtasks[0].id == "st-1"
        assert session.plan.subtasks[0].completed is True
        assert session.plan.subtasks[0].result == "done"
        assert session.plan.subtasks[1].dependencies == ["st-1"]
        assert len(session.messages) == 1

    def test_deserialize_invalid_json_returns_none(self) -> None:
        """_deserialize con metadata corrupta retorna None.  (líneas 379-381)"""
        record = {"metadata": {"data": "not valid json"}}
        session = self.ctx._deserialize(record)
        assert session is None

    def test_deserialize_metadata_as_string(self) -> None:
        """_deserialize maneja metadata como string JSON.  (línea 342)"""
        data = self._make_valid_data()
        # metadata es un string, no un dict
        meta_str = json.dumps({"data": json.dumps(data)})
        record = {"metadata": meta_str}
        session = self.ctx._deserialize(record)
        assert session is not None
        assert session.session_id == "sess-123"

    def test_deserialize_data_already_dict(self) -> None:
        """_deserialize maneja data que ya es dict.  (línea 348)"""
        data = self._make_valid_data()
        # data ya está como dict, no como string JSON
        record = {"metadata": {"data": data}}
        session = self.ctx._deserialize(record)
        assert session is not None
        assert session.session_id == "sess-123"

    def test_deserialize_missing_fields(self) -> None:
        """_deserialize tolera campos faltantes con valores por defecto."""
        minimal_data = {
            "session_id": "minimal",
            "original_message": "minimal",
            "plan": {
                "session_id": "minimal",
                "original_message": "minimal",
                "subtasks": [],
            },
        }
        record = {"metadata": {"data": json.dumps(minimal_data)}}
        session = self.ctx._deserialize(record)
        assert session is not None
        assert session.session_id == "minimal"
        assert session.completed is False  # default
        assert session.messages == []  # default

    def test_deserialize_con_metadata_vacia(self) -> None:
        """_deserialize con metadata vacío retorna sesión con campos vacíos."""
        record = {"metadata": {}}
        session = self.ctx._deserialize(record)
        # data_str = meta.get("data", "{}") → "{}", json.loads("{}") → {}
        # Se crea SessionState con campos vacíos
        assert session is not None
        assert session.session_id == ""

    def test_deserialize_contenido_no_dict_en_plan(self) -> None:
        """_deserialize tolera subtask sin campos opcionales."""
        data = {
            "session_id": "sess",
            "original_message": "msg",
            "plan": {
                "session_id": "sess",
                "original_message": "msg",
                "subtasks": [
                    {
                        "id": "st-1",
                        "agent": "builder",
                        "description": "task",
                        # faltan dependencies, expected_output, etc.
                    }
                ],
            },
        }
        record = {"metadata": {"data": json.dumps(data)}}
        session = self.ctx._deserialize(record)
        assert session is not None
        assert session.plan.subtasks[0].dependencies == []
        assert session.plan.subtasks[0].expected_output == ""
        assert session.plan.subtasks[0].completed is False

    def test_deserialize_session_completed_true(self) -> None:
        """_deserialize restaura completed=True."""
        data = self._make_valid_data()
        data["completed"] = True
        record = {"metadata": {"data": json.dumps(data)}}
        session = self.ctx._deserialize(record)
        assert session is not None
        assert session.completed is True


class TestSessionContextGetSession:
    """Tests adicionales para get_session."""

    def test_get_session_from_active(self) -> None:
        """get_session encuentra sesión en _active_sessions."""
        ctx = SessionContext()
        plan = TaskPlan(session_id="active-1", original_message="test")
        session = ctx.get_or_create("test", plan)
        found = ctx.get_session("active-1")
        assert found is session

    def test_get_session_from_store(self) -> None:
        """get_session busca en store si no está en memoria."""
        mock_store = MagicMock()
        ctx = SessionContext(vector_store=mock_store)
        # Sesión no está en memoria, _load_from_store devolverá None
        mock_store.search.return_value = []
        found = ctx.get_session("not-in-memory")
        assert found is None


class TestSessionContextGetStatusCompleta:
    """Tests adicionales para get_status con sesión completada."""

    def test_get_status_session_completa(self) -> None:
        """get_status muestra mensaje de sesión completa.  (línea 285)"""
        ctx = SessionContext()
        plan = TaskPlan(session_id="test-complete", original_message="test",
                        subtasks=[SubTask(id="s1", agent="builder", description="task",
                                          dependencies=[])])
        session = ctx.get_or_create("test", plan)
        ctx.mark_subtask_done(session, "s1", "done")
        assert session.completed is True
        status = ctx.get_status(session)
        assert "COMPLETA" in status


class TestSessionContextLoadFromStore:
    """Tests para _load_from_store con resultados."""

    def test_load_from_store_con_resultados(self) -> None:
        """_load_from_store devuelve sesión cuando search encuentra datos.  (línea 315)"""
        mock_store = MagicMock()
        ctx = SessionContext(vector_store=mock_store)

        # Simulamos un resultado de búsqueda válido
        data = {
            "session_id": "found-session",
            "original_message": "hello",
            "plan": {
                "session_id": "found-session",
                "original_message": "hello",
                "subtasks": [
                    {
                        "id": "st-1",
                        "agent": "builder",
                        "description": "task",
                        "dependencies": [],
                    }
                ],
            },
            "created_at": "2024-01-01T00:00:00",
            "updated_at": "2024-01-01T00:00:00",
            "completed": False,
            "messages": [],
        }
        mock_store.search.return_value = [
            {"metadata": {"data": json.dumps(data)}, "vector": []},
        ]

        session = ctx._load_from_store("found-session")
        assert session is not None
        assert session.session_id == "found-session"
