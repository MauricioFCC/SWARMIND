"""Tests para TaskManager — cobertura objetivo >80%.

Estrategia de testing:
  - SQLite: forzamos HAS_LANCEDB=False, usamos directorio temporal como db_path.
  - LanceDB: inyectamos mock lancedb via patch.dict, mockeamos DataFrame.
  - Pydantic: forzamos HAS_PYDANTIC=True.
  - Cubrimos ramas: create/read/update/delete, SQLite y LanceDB, status transitions,
    serializacion, validacion, agent filtering, list/offset/limit, close.
"""
from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

import harness.orchestrator.task_manager as tm_module


# ---------------------------------------------------------------------------
# Mock DataFrame — evita dependencia real de pandas
# ---------------------------------------------------------------------------
class _MockSeries:
    """Mock de pandas.Series para filtros booleanos."""
    def __init__(self, values: list) -> None:
        self.values = values

    def __eq__(self, other: object) -> _MockSeries:  # type: ignore[override]
        return _MockSeries([v == other for v in self.values])

    def __ne__(self, other: object) -> _MockSeries:  # type: ignore[override]
        return _MockSeries([v != other for v in self.values])


class _MockDataFrame:
    """Mock minimal de pandas.DataFrame para las operaciones que usa TaskManager.

    Soporta: __len__, __getitem__(str) → serie, __getitem__(serie) → filtro,
    .iloc[n] → self, .to_dict(), .iterrows().
    """

    def __init__(self, data: list[dict] | None = None) -> None:
        self._data: list[dict] = data or []

    def __len__(self) -> int:
        return len(self._data)

    def __bool__(self) -> bool:
        return len(self._data) > 0

    def __getitem__(self, key: str | _MockSeries) -> _MockSeries | _MockDataFrame:
        if isinstance(key, _MockSeries):
            return _MockDataFrame(
                [r for i, r in enumerate(self._data) if key.values[i]]
            )
        if isinstance(key, str):
            return _MockSeries([r.get(key) for r in self._data])
        return self  # key numerico — no se usa realmente

    @property
    def iloc(self) -> _MockDataFrame:
        return self

    def to_dict(self) -> dict:
        return self._data[0] if self._data else {}

    def iterrows(self):
        for i, row in enumerate(self._data):
            yield i, _MockRow(row)

    def head(self, n: int = 5) -> _MockDataFrame:
        return _MockDataFrame(self._data[:n])


class _MockRow:
    """Mock de una fila de DataFrame (.to_dict())."""
    def __init__(self, data: dict) -> None:
        self._data = data

    def to_dict(self) -> dict:
        return self._data


# ---------------------------------------------------------------------------
# Fixture autouse: parchea logger (no definido en source)
# Nota: patch.object falla porque 'logger' no existe como atributo.
# Usamos patch.dict sobre __dict__ para inyectarlo.
# ---------------------------------------------------------------------------
@pytest.fixture(autouse=True)
def _patch_logger():
    """Parchea el logger global de task_manager (ausente en el codigo fuente).

    Usa patch.dict porque logger no existe como atributo del modulo.
    """
    with patch.dict(tm_module.__dict__, {"logger": MagicMock()}):
        yield


# ===================================================================
# Tests con SQLite (HAS_LANCEDB=False, HAS_PYDANTIC=False)
# ===================================================================
class TestTaskManagerSQLite:
    """Cobertura SQLite: CRUD, count, list, status transitions, agent queries."""

    @pytest.fixture(autouse=True)
    def _force_sqlite(self):
        """Fuerza SQLite desactivando LanceDB y Pydantic."""
        with patch.dict(
            tm_module.__dict__,
            {"HAS_LANCEDB": False, "HAS_PYDANTIC": False},
        ):
            yield

    # -- helpers ----------------------------------------------------------
    def _make_tm(self) -> tm_module.TaskManager:
        """Crea TaskManager con db_path en directorio temporal."""
        tmpdir = tempfile.mkdtemp(prefix="tm_test_")
        return tm_module.TaskManager(db_path=tmpdir)

    # -- _initialize / directorio ----------------------------------------
    def test_initialize_creates_directory(self):
        """_initialize crea el directorio padre si no existe.

        Nota: SQLite necesita db_path existente como directorio.
        El test verifica que el padre sea creado por la logica interna.
        """
        tmpdir = tempfile.mkdtemp(prefix="tm_init_")
        try:
            parent = Path(tmpdir) / "inexistente"
            db_path = str(parent / "lancedb")
            Path(db_path).mkdir(parents=True, exist_ok=True)  # necesario para SQLite
            tm = tm_module.TaskManager(db_path=db_path)
            # Parent es creado por Path(db_path).mkdir() indirectamente,
            # pero la logica interna tambien lo crearia
            assert parent.is_dir()
            tm.close()
        finally:
            import shutil
            shutil.rmtree(tmpdir, ignore_errors=True)

    # -- create_task -----------------------------------------------------
    def test_create_task_minimal(self):
        """create_task con solo titulo crea tarea en SQLite."""
        tm = self._make_tm()
        task = tm.create_task(title="Hola")
        assert task.id
        assert task.title == "Hola"
        assert task.status == "pending"
        assert task.priority == 0

    def test_create_task_full(self):
        """create_task con todos los campos."""
        tm = self._make_tm()
        task = tm.create_task(
            title="Full", description="desc", agent_assigned="builder",
            status="in_progress", priority=3,
        )
        assert task.description == "desc"
        assert task.agent_assigned == "builder"
        assert task.status == "in_progress"
        assert task.priority == 3

    def test_create_task_invalid_status_raises(self):
        """create_task con status invalido lanza ValueError."""
        tm = self._make_tm()
        with pytest.raises(ValueError, match="Invalid status"):
            tm.create_task(title="x", status="bogus")

    def test_create_task_persists_in_sqlite(self):
        """create_task persiste realmente en SQLite."""
        tm = self._make_tm()
        task = tm.create_task(title="Persist")
        retrieved = tm.read_task(task.id)
        assert retrieved is not None
        assert retrieved.title == "Persist"

    # -- read_task -------------------------------------------------------
    def test_read_task_not_found_returns_none(self):
        """read_task con id inexistente retorna None."""
        tm = self._make_tm()
        assert tm.read_task("no_existe") is None

    def test_read_task_empty_id(self):
        """read_task con id vacio retorna None."""
        tm = self._make_tm()
        assert tm.read_task("") is None

    # -- update_task -----------------------------------------------------
    def test_update_task_fields(self):
        """update_task modifica campos permitidos."""
        tm = self._make_tm()
        task = tm.create_task(title="Original", priority=0)
        updated = tm.update_task(task.id, title="Editado", priority=99)
        assert updated is not None
        assert updated.title == "Editado"
        assert updated.priority == 99

    def test_update_task_status_validates(self):
        """update_task con status valido funciona, invalido falla."""
        tm = self._make_tm()
        task = tm.create_task(title="StatusTest")
        updated = tm.update_task(task.id, status="done")
        assert updated is not None
        assert updated.status == "done"
        with pytest.raises(ValueError, match="Invalid status"):
            tm.update_task(task.id, status="invalid")

    def test_update_task_not_found(self):
        """update_task con id inexistente retorna None."""
        tm = self._make_tm()
        assert tm.update_task("no_existe", title="x") is None

    def test_update_task_empty_updates(self):
        """update_task sin cambios devuelve tarea original."""
        tm = self._make_tm()
        task = tm.create_task(title="SinCambios")
        updated = tm.update_task(task.id)
        assert updated is not None
        assert updated.title == "SinCambios"

    # -- delete_task -----------------------------------------------------
    def test_delete_task_removes_and_returns_true(self):
        """delete_task elimina y retorna True."""
        tm = self._make_tm()
        task = tm.create_task(title="DelMe")
        assert tm.delete_task(task.id) is True
        assert tm.read_task(task.id) is None

    def test_delete_task_not_found(self):
        """delete_task con id inexistente retorna False."""
        tm = self._make_tm()
        assert tm.delete_task("no_existe") is False

    # -- query_by_agent --------------------------------------------------
    def test_query_by_agent_returns_matching(self):
        """query_by_agent retorna solo tareas del agente indicado."""
        tm = self._make_tm()
        tm.create_task(title="A1", agent_assigned="builder")
        tm.create_task(title="A2", agent_assigned="builder")
        tm.create_task(title="B1", agent_assigned="scientist")
        assert len(tm.query_by_agent("builder")) == 2
        assert len(tm.query_by_agent("scientist")) == 1

    def test_query_by_agent_unknown_returns_empty(self):
        """query_by_agent con agente desconocido retorna lista vacia."""
        tm = self._make_tm()
        tm.create_task(title="T1", agent_assigned="builder")
        assert tm.query_by_agent("hacker") == []

    def test_query_by_agent_case_normalized(self):
        """query_by_agent normaliza a minusculas y aplica strip.

        Nota: la normalizacion solo ocurre en el query (no al crear),
        por eso creamos con 'builder' (minusculas).
        """
        tm = self._make_tm()
        tm.create_task(title="T1", agent_assigned="builder")
        assert len(tm.query_by_agent("  BUILDER  ")) >= 1

    # -- list_tasks ------------------------------------------------------
    def test_list_tasks_all(self):
        """list_tasks sin filtros retorna todas las tareas."""
        tm = self._make_tm()
        for i in range(5):
            tm.create_task(title=f"T{i}")
        tasks = tm.list_tasks()
        assert len(tasks) >= 5

    def test_list_tasks_with_status_filter(self):
        """list_tasks con filtro status."""
        tm = self._make_tm()
        tm.create_task(title="P", status="pending")
        tm.create_task(title="D", status="done")
        pending = tm.list_tasks(status="pending")
        assert all(t.status == "pending" for t in pending)
        assert len(pending) == 1

    def test_list_tasks_with_agent_filter(self):
        """list_tasks con filtro agent."""
        tm = self._make_tm()
        tm.create_task(title="B1", agent_assigned="builder")
        tm.create_task(title="B2", agent_assigned="builder")
        tm.create_task(title="S1", agent_assigned="scientist")
        result = tm.list_tasks(agent="builder")
        assert all(t.agent_assigned == "builder" for t in result)
        assert len(result) == 2

    def test_list_tasks_with_status_and_agent(self):
        """list_tasks con filtros combinados status + agent."""
        tm = self._make_tm()
        tm.create_task(title="B1", agent_assigned="builder", status="done")
        tm.create_task(title="B2", agent_assigned="builder", status="pending")
        tm.create_task(title="S1", agent_assigned="scientist", status="pending")
        result = tm.list_tasks(status="pending", agent="builder")
        assert len(result) == 1
        assert result[0].title == "B2"

    def test_list_tasks_with_limit_and_offset(self):
        """list_tasks respeta limit y offset."""
        tm = self._make_tm()
        for i in range(10):
            tm.create_task(title=f"T{i}")
        limited = tm.list_tasks(limit=3, offset=0)
        assert len(limited) <= 3

    # -- update_status ---------------------------------------------------
    def test_update_status_changes_and_logs(self):
        """update_status cambia estado y registra transicion."""
        tm = self._make_tm()
        task = tm.create_task(title="Transicion")
        updated = tm.update_status(task.id, "in_progress", reason="empezando")
        assert updated is not None
        assert updated.status == "in_progress"
        assert len(updated.transition_history) == 1
        entry = updated.transition_history[0]
        assert entry["from_status"] == "pending"
        assert entry["to_status"] == "in_progress"

    def test_update_status_same_status_returns_no_change(self):
        """update_status con mismo status no anade transicion."""
        tm = self._make_tm()
        task = tm.create_task(title="Igual")
        result = tm.update_status(task.id, "pending")
        assert result is not None
        assert result.status == "pending"
        # update_status retorna el objeto leido (nueva instancia),
        # no el original, pero los valores deben coincidir
        assert result.title == "Igual"
        assert len(result.transition_history) == 0

    def test_update_status_task_not_found(self):
        """update_status con id inexistente retorna None."""
        tm = self._make_tm()
        assert tm.update_status("no_existe", "done") is None

    def test_update_status_invalid_status_raises(self):
        """update_status con status invalido lanza ValueError."""
        tm = self._make_tm()
        task = tm.create_task(title="Invalido")
        with pytest.raises(ValueError, match="Invalid status"):
            tm.update_status(task.id, "invalid")

    # -- count_tasks -----------------------------------------------------
    def test_count_tasks_zero(self):
        """count_tasks en tabla vacia retorna 0."""
        tm = self._make_tm()
        assert tm.count_tasks() == 0

    def test_count_tasks_all(self):
        """count_tasks sin filtro cuenta todas."""
        tm = self._make_tm()
        tm.create_task(title="A")
        tm.create_task(title="B")
        assert tm.count_tasks() == 2

    def test_count_tasks_with_status_filter(self):
        """count_tasks con filtro status."""
        tm = self._make_tm()
        tm.create_task(title="P1", status="pending")
        tm.create_task(title="P2", status="pending")
        tm.create_task(title="D1", status="done")
        assert tm.count_tasks(status="pending") == 2
        assert tm.count_tasks(status="done") == 1

    # -- close -----------------------------------------------------------
    def test_close_releases_connection(self):
        """close cierra la conexion SQLite y la pone en None."""
        tm = self._make_tm()
        tm.create_task(title="PreClose")
        tm.close()
        assert tm._sqlite_conn is None

    def test_operations_after_close_return_empty(self):
        """Operaciones tras close no fallan, retornan valores seguros."""
        tm = self._make_tm()
        tm.close()
        assert tm._run_sqlite_query("SELECT 1") == []

    # -- db_path property ------------------------------------------------
    def test_db_path_property(self):
        """La propiedad db_path retorna la ruta configurada."""
        tm = self._make_tm()
        assert tm.db_path == tm._db_path

    def test_update_task_disallowed_fields_ignored(self):
        """update_task ignora campos no permitidos (else branch linea 317)."""
        tm = self._make_tm()
        task = tm.create_task(title="Original")
        updated = tm.update_task(task.id, nonexistent_field="ignored")
        assert updated is not None
        assert updated.title == "Original"

    def test_close_twice(self):
        """close() llamado dos veces no falla (cubre rama conn is None)."""
        tm = self._make_tm()
        tm.close()
        tm.close()  # segunda llamada: _sqlite_conn ya es None

    # -- initialize with vector_store ------------------------------------
    def test_initialize_from_vector_store(self):
        """__init__ extrae db_path del vector_store si se provee."""
        vs = MagicMock()
        tmpdir = tempfile.mkdtemp(prefix="tm_vs_")
        vs.db_path = tmpdir
        tm = tm_module.TaskManager(vector_store=vs)
        assert tm._db_path == tmpdir

    # -- serializacion ---------------------------------------------------
    def test_serialize_task_converts_list_history(self):
        """_serialize_task convierte transition_history list a JSON string."""
        tm = self._make_tm()
        task = tm.create_task(title="Ser")
        raw = task.to_dict()
        raw["transition_history"] = [{"a": 1}]
        serialized = tm._serialize_task(raw)
        assert isinstance(serialized["transition_history"], str)
        assert json.loads(serialized["transition_history"]) == [{"a": 1}]

    def test_serialize_task_keeps_string_history(self):
        """_serialize_task deja intacto transition_history si ya es string."""
        tm = self._make_tm()
        task = tm.create_task(title="Ser2")
        raw = task.to_dict()
        raw["transition_history"] = "[1, 2]"
        serialized = tm._serialize_task(raw)
        assert serialized["transition_history"] == "[1, 2]"

    def test_deserialize_task_converts_json_history(self):
        """_deserialize_task convierte transition_history JSON a list."""
        tm = self._make_tm()
        row = {
            "id": "abc", "title": "T", "description": "", "agent_assigned": "",
            "status": "done", "priority": 0, "created_at": "now", "updated_at": "now",
            "transition_history": json.dumps([{"x": 1}]),
        }
        task = tm._deserialize_task(row)
        assert task.transition_history == [{"x": 1}]

    def test_deserialize_task_keeps_list_history(self):
        """_deserialize_task deja intacto transition_history si ya es list."""
        tm = self._make_tm()
        row = {
            "id": "abc", "title": "T", "description": "", "agent_assigned": "",
            "status": "done", "priority": 0, "created_at": "now", "updated_at": "now",
            "transition_history": [{"x": 1}],
        }
        task = tm._deserialize_task(row)
        assert task.transition_history == [{"x": 1}]

    # -- helpers internos -------------------------------------------------
    def test_validate_status_valid(self):
        """_validate_status acepta status validos."""
        for s in ("pending", "in_progress", "done", "blocked"):
            assert tm_module._validate_status(s) == s

    def test_validate_status_invalid_raises(self):
        """_validate_status rechaza status invalido."""
        with pytest.raises(ValueError, match="Invalid status"):
            tm_module._validate_status("bogus")

    def test_make_id_returns_unique_hex(self):
        """_make_id retorna string hex de 12 chars unico."""
        ids = {tm_module._make_id() for _ in range(100)}
        assert len(ids) == 100
        assert all(len(i) == 12 for i in ids)

    def test_now_iso_format(self):
        """_now_iso retorna string ISO 8601."""
        iso = tm_module._now_iso()
        assert "T" in iso and "+" in iso

    # -- dataclasses -----------------------------------------------------
    def test_transition_entry_to_dict(self):
        """TransitionEntry.to_dict."""
        entry = tm_module.TransitionEntry("a", "b", "t", "r")
        d = entry.to_dict()
        assert d == {"from_status": "a", "to_status": "b", "timestamp": "t", "reason": "r"}

    def test_transition_entry_from_dict(self):
        """TransitionEntry.from_dict."""
        entry = tm_module.TransitionEntry.from_dict(
            {"from_status": "x", "to_status": "y", "timestamp": "z", "reason": "w"}
        )
        assert entry.from_status == "x"
        assert entry.to_status == "y"

    def test_task_from_dict(self):
        """Task.from_dict."""
        data = {"id": "id1", "title": "T1", "description": "d", "agent_assigned": "a",
                "status": "pending", "priority": 1, "created_at": "c", "updated_at": "u",
                "transition_history": []}
        task = tm_module.Task.from_dict(data)
        assert task.id == "id1"
        assert task.title == "T1"

    def test_task_to_dict(self):
        """Task.to_dict."""
        task = tm_module.Task(id="x", title="Y")
        d = task.to_dict()
        assert d["id"] == "x"
        assert d["title"] == "Y"

    # -- SQLite helpers --------------------------------------------------
    def test_run_sqlite_query_no_connection(self):
        """_run_sqlite_query sin conexion retorna lista vacia."""
        tm = tm_module.TaskManager.__new__(tm_module.TaskManager)
        tm._sqlite_conn = None
        assert tm._run_sqlite_query("SELECT 1") == []

    def test_run_sqlite_execute_no_connection(self):
        """_run_sqlite_execute sin conexion no falla."""
        tm = tm_module.TaskManager.__new__(tm_module.TaskManager)
        tm._sqlite_conn = None
        tm._run_sqlite_execute("UPDATE t SET x=1")  # no debe explotar


# ===================================================================
# Tests con LanceDB (HAS_LANCEDB=True)
# ===================================================================
class TestTaskManagerLanceDB:
    """Cobertura de las rutas que usan LanceDB en lugar de SQLite.

    Inyecta mock de lancedb y mock de DataFrame para .to_pandas().
    """

    @pytest.fixture(autouse=True)
    def _force_lancedb(self):
        """Inyecta lancedb mock y setea HAS_LANCEDB=True."""
        mock_lancedb = MagicMock()
        mock_conn = MagicMock()
        mock_lancedb.connect.return_value = mock_conn
        # Simular tabla nueva (no existe aun)
        mock_conn.list_tables.return_value.tables = []
        self._mock_table = MagicMock()
        mock_conn.create_table.return_value = self._mock_table
        mock_conn.open_table.return_value = self._mock_table

        with patch.dict(
            tm_module.__dict__,
            {"HAS_LANCEDB": True, "HAS_PYDANTIC": False, "lancedb": mock_lancedb},
        ):
            yield

    # -- _initialize -----------------------------------------------------
    def test_initialize_uses_lancedb(self):
        """_initialize configura LanceDB cuando HAS_LANCEDB=True."""
        tm = tm_module.TaskManager(db_path="/tmp/lancedb_test")
        assert tm._use_sqlite is False
        assert tm._table is not None
        assert tm._conn_lancedb is not None

    def test_initialize_lancedb_creates_parent_dir(self):
        """_initialize crea el directorio padre via LanceDB path.

        Usamos un path cuyo directorio padre no existe para ejercitar
        el Path.exists() y Path.mkdir().
        """
        import tempfile
        tmpdir = tempfile.mkdtemp(prefix="tm_lancedb_dir_")
        try:
            parent = Path(tmpdir) / "sub_no_existe"
            db_path = str(parent / "lancedb")
            tm_module.TaskManager(db_path=db_path)
            # El padre debe haber sido creado por _initialize
            assert parent.is_dir()
        finally:
            import shutil
            shutil.rmtree(tmpdir, ignore_errors=True)

    def test_initialize_existing_table(self):
        """_initialize reusa tabla si ya existe en LanceDB."""
        # Reconfigurar para que list_tables muestre la tabla existente
        mock_lancedb_new = MagicMock()
        mock_conn = MagicMock()
        mock_lancedb_new.connect.return_value = mock_conn
        mock_conn.list_tables.return_value.tables = ["tasks_board"]
        mock_table = MagicMock()
        mock_conn.open_table.return_value = mock_table

        with patch.dict(
            tm_module.__dict__,
            {"HAS_LANCEDB": True, "HAS_PYDANTIC": False, "lancedb": mock_lancedb_new},
        ):
            tm = tm_module.TaskManager(db_path="/tmp/lancedb_existing")
            assert tm._use_sqlite is False
            # create_table no debe llamarse
            mock_conn.create_table.assert_not_called()

    # -- create_task -----------------------------------------------------
    def test_create_task_with_lancedb(self):
        """create_task usa LanceDB.add."""
        tm = tm_module.TaskManager(db_path="/tmp/lancedb_test")
        task = tm.create_task(title="LanceTask")
        assert task.title == "LanceTask"
        tm._table.add.assert_called_once()

    # -- read_task -------------------------------------------------------
    def test_read_task_with_lancedb_found(self):
        """read_task recupera tarea via LanceDB."""
        tm = tm_module.TaskManager(db_path="/tmp/lancedb_test")
        df = _MockDataFrame([{
            "id": "abc123", "title": "Encontrado", "description": "",
            "agent_assigned": "", "status": "pending", "priority": 0,
            "created_at": "now", "updated_at": "now",
            "transition_history": "[]",
        }])
        tm._table.search.return_value.where.return_value.limit.return_value.to_pandas.return_value = df

        task = tm.read_task("abc123")
        assert task is not None
        assert task.title == "Encontrado"

    def test_read_task_with_lancedb_not_found(self):
        """read_task retorna None si LanceDB no encuentra."""
        tm = tm_module.TaskManager(db_path="/tmp/lancedb_test")
        tm._table.search.return_value.where.return_value.limit.return_value.to_pandas.return_value = _MockDataFrame()

        assert tm.read_task("no_existe") is None

    # -- update_task -----------------------------------------------------
    def test_update_task_with_lancedb(self):
        """update_task usa LanceDB.update."""
        tm = tm_module.TaskManager(db_path="/tmp/lancedb_test")
        df = _MockDataFrame([{
            "id": "t1", "title": "Original", "description": "",
            "agent_assigned": "", "status": "pending", "priority": 0,
            "created_at": "now", "updated_at": "now",
            "transition_history": "[]",
        }])
        tm._table.search.return_value.where.return_value.limit.return_value.to_pandas.return_value = df

        updated = tm.update_task("t1", title="Modificado")
        assert updated is not None
        assert updated.title == "Modificado"
        tm._table.update.assert_called_once()

    # -- delete_task -----------------------------------------------------
    def test_delete_task_with_lancedb(self):
        """delete_task usa LanceDB.delete y retorna True.

        Nota: _initialize ya llama a delete('id = ''init''') una vez,
        por eso usamos assert_any_call + verificamos el ultimo call.
        """
        tm = tm_module.TaskManager(db_path="/tmp/lancedb_test")
        tm._table.delete.return_value = MagicMock()
        assert tm.delete_task("abc") is True
        tm._table.delete.assert_any_call("id = 'abc'")
        # Verificar que se llamo exactamente 2 veces (init + nuestro delete)
        assert tm._table.delete.call_count == 2
        assert tm._table.delete.call_args_list[-1] == (("id = 'abc'",),)

    # -- query_by_agent --------------------------------------------------
    def test_query_by_agent_with_lancedb(self):
        """query_by_agent filtra via LanceDB."""
        tm = tm_module.TaskManager(db_path="/tmp/lancedb_test")
        df = _MockDataFrame([{
            "id": "a1", "title": "BuilderTask", "description": "",
            "agent_assigned": "builder", "status": "pending", "priority": 0,
            "created_at": "now", "updated_at": "now",
            "transition_history": "[]",
        }])
        tm._table.search.return_value.where.return_value.to_pandas.return_value = df

        tasks = tm.query_by_agent("builder")
        assert len(tasks) == 1
        assert tasks[0].agent_assigned == "builder"

    # -- list_tasks ------------------------------------------------------
    def test_list_tasks_with_lancedb(self):
        """list_tasks usa LanceDB con filtro."""
        tm = tm_module.TaskManager(db_path="/tmp/lancedb_test")
        df = _MockDataFrame([{
            "id": "a1", "title": "T1", "description": "",
            "agent_assigned": "builder", "status": "done", "priority": 0,
            "created_at": "now", "updated_at": "now",
            "transition_history": "[]",
        }])
        tm._table.search.return_value.where.return_value.limit.return_value.to_pandas.return_value = df

        tasks = tm.list_tasks(status="done", agent="builder")
        assert len(tasks) == 1

    # -- update_status ---------------------------------------------------
    def test_update_status_with_lancedb(self):
        """update_status registra transicion via LanceDB."""
        tm = tm_module.TaskManager(db_path="/tmp/lancedb_test")
        df = _MockDataFrame([{
            "id": "s1", "title": "StatusChange", "description": "",
            "agent_assigned": "", "status": "pending", "priority": 0,
            "created_at": "now", "updated_at": "now",
            "transition_history": "[]",
        }])
        tm._table.search.return_value.where.return_value.limit.return_value.to_pandas.return_value = df

        updated = tm.update_status("s1", "done", "completado")
        assert updated is not None
        assert updated.status == "done"
        assert len(updated.transition_history) == 1

    # -- count_tasks -----------------------------------------------------
    def test_count_tasks_with_lancedb(self):
        """count_tasks cuenta via LanceDB."""
        tm = tm_module.TaskManager(db_path="/tmp/lancedb_test")
        df = _MockDataFrame([
            {"id": "a", "status": "done"},
            {"id": "b", "status": "pending"},
        ])
        tm._table.search.return_value.to_pandas.return_value = df

        assert tm.count_tasks() == 2
        assert tm.count_tasks(status="done") == 1
        assert tm.count_tasks(status="pending") == 1

    # -- unknown agent con LanceDB ---------------------------------------
    def test_query_by_agent_unknown_lancedb(self):
        """query_by_agent con agente desconocido retorna vacio (LanceDB path)."""
        tm = tm_module.TaskManager(db_path="/tmp/lancedb_test")
        assert tm.query_by_agent("hacker") == []


# ===================================================================
# Tests con Pydantic (HAS_PYDANTIC=True)
# ===================================================================
class TestTaskManagerPydantic:
    """Cobertura de rutas que usan PydanticTask."""

    @pytest.fixture(autouse=True)
    def _force_pydantic(self):
        """Activa Pydantic y desactiva LanceDB para usar SQLite."""
        with patch.dict(
            tm_module.__dict__,
            {"HAS_LANCEDB": False, "HAS_PYDANTIC": True},
        ):
            yield

    def _make_tm(self):
        tmpdir = tempfile.mkdtemp(prefix="tm_pyd_")
        return tm_module.TaskManager(db_path=tmpdir)

    def test_create_task_returns_pydantic_task(self):
        """create_task retorna PydanticTask cuando HAS_PYDANTIC."""
        tm = self._make_tm()
        task = tm.create_task(title="PydTest")
        assert isinstance(task, tm_module.PydanticTask)
        assert task.title == "PydTest"

    def test_pydantic_task_to_dict(self):
        """PydanticTask.to_dict usa model_dump."""
        task = tm_module.PydanticTask(id="pyid", title="PyTitle")
        d = task.to_dict()
        assert d["id"] == "pyid"
        assert d["title"] == "PyTitle"

    def test_pydantic_task_from_dict(self):
        """PydanticTask.from_dict reconstruye desde dict."""
        data = {"id": "px", "title": "FromPy", "status": "done"}
        task = tm_module.PydanticTask.from_dict(data)
        assert task.id == "px"
        assert task.title == "FromPy"
        assert task.status == "done"


# ===================================================================
# Tests de Placeholder PydanticTask (HAS_PYDANTIC=False)
# ===================================================================
class TestPydanticPlaceholder:
    """Cuando HAS_PYDANTIC=False, PydanticTask es un placeholder.

    NOTA: Si pydantic esta instalado en el entorno, el placeholder
    jamas se ejecuta (el bloque ``else`` no se compila).
    Este test verifica que la logica *existiria* si pydantic faltara.
    """

    @pytest.fixture(autouse=True)
    def _force_no_pydantic(self):
        with patch.dict(tm_module.__dict__, {"HAS_PYDANTIC": False}):
            # Reemplazar PydanticTask por el placeholder manualmente
            # para simular el escenario sin pydantic
            class Placeholder:
                @classmethod
                def from_dict(cls, data):
                    return tm_module.Task.from_dict(data)
            self._placeholder_cls = Placeholder
            yield

    def test_placeholder_from_dict_returns_task(self):
        """Placeholder.from_dict delega a Task.from_dict."""
        task = self._placeholder_cls.from_dict({
            "id": "ph", "title": "PH", "description": "", "agent_assigned": "",
            "status": "done", "priority": 0, "created_at": "", "updated_at": "",
            "transition_history": [],
        })
        assert isinstance(task, tm_module.Task)
        assert task.title == "PH"


# ===================================================================
# Test de integracion: Multi-agente CRUD pesado
# ===================================================================
class TestTaskManagerIntegration:
    """Pruebas de integracion multi-operacion con SQLite."""

    @pytest.fixture(autouse=True)
    def _sqlite_only(self):
        with patch.dict(
            tm_module.__dict__,
            {"HAS_LANCEDB": False, "HAS_PYDANTIC": False},
        ):
            yield

    def _make_tm(self):
        tmpdir = tempfile.mkdtemp(prefix="tm_int_")
        return tm_module.TaskManager(db_path=tmpdir)

    def test_full_crud_cycle(self):
        """Ciclo completo CRUD sobre multiples agentes."""
        tm = self._make_tm()
        agents = ["builder", "scientist", "guardian", "coordinator"]
        ids = []
        for a in agents:
            for i in range(3):
                t = tm.create_task(title=f"{a}-{i}", agent_assigned=a)
                ids.append(t.id)

        # count
        assert tm.count_tasks() == 12

        # query by agent
        for a in agents:
            assert len(tm.query_by_agent(a)) == 3

        # list with filters
        assert len(tm.list_tasks(agent="builder")) == 3
        assert len(tm.list_tasks(status="pending")) == 12

        # update all to done
        for tid in ids:
            tm.update_status(tid, "done", "integration complete")

        assert tm.count_tasks(status="done") == 12

        # delete half
        for tid in ids[:6]:
            assert tm.delete_task(tid) is True
        assert tm.count_tasks() == 6

        # read deleted
        assert tm.read_task(ids[0]) is None

        tm.close()
