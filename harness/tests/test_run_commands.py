"""
Tests para harness/run_commands.py — command handlers del Harness CLI.

Cubre: RAG commands, DB commands, iteration commands, hooks, evolve,
schedule, model routing, HITL, watch mode, hermes, guardrails, ANSI helpers.
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_store():
    """Mock de LanceVectorStore."""
    store = MagicMock()
    store.list_collections.return_value = []
    store.get_collection_stats.return_value = {"item_count": 0, "last_updated": "N/A"}
    return store


@pytest.fixture(autouse=True)
def suppress_logger():
    """Parchea el logger de run_commands para evitar ruido en tests."""
    with patch("harness.run_commands.logger") as mock_log:
        yield mock_log


# ===================================================================
# RAG Commands
# ===================================================================

class TestRagCommands:
    """Tests para comandos RAG: _handle_rag_ingest, _handle_rag_stats."""

    @pytest.fixture(autouse=True)
    def patch_ingest(self):
        """Parchea ingest_project_directory (import lazy dentro de la funcion)."""
        with patch("harness.memory_rag.doc_ingester.ingest_project_directory") as m:
            yield m

    def test_rag_ingest_default(self, mock_store, patch_ingest):
        """!rag ingest sin flags debe ingestar desde project root."""
        patch_ingest.return_value = {"files_processed": 10, "chunks_inserted": 200, "errors": 0}
        from harness.run_commands import _handle_rag_ingest
        _handle_rag_ingest(mock_store, "!rag ingest")

    def test_rag_ingest_with_dir(self, mock_store, patch_ingest, tmp_path):
        """!rag ingest --dir <path> debe ingestar directorio especifico."""
        d = tmp_path / "mi_codigo"
        d.mkdir()
        (d / "test.py").write_text("print('hello')")
        patch_ingest.return_value = {"files_processed": 1, "chunks_inserted": 5, "errors": 0}
        from harness.run_commands import _handle_rag_ingest
        _handle_rag_ingest(mock_store, f"!rag ingest --dir {d}")

    def test_rag_ingest_dir_no_existe(self, mock_store, patch_ingest):
        """!rag ingest --dir <path> con directorio inexistente debe loggear warning."""
        from harness.run_commands import _handle_rag_ingest
        _handle_rag_ingest(mock_store, "!rag ingest --dir /no/existe")

    def test_rag_ingest_error(self, mock_store, patch_ingest):
        """Si ingest_project_directory lanza excepcion, debe loggear error."""
        patch_ingest.side_effect = Exception("Fallo de red")
        from harness.run_commands import _handle_rag_ingest
        _handle_rag_ingest(mock_store, "!rag ingest")

    def test_rag_ingest_con_errores_en_stats(self, mock_store, patch_ingest):
        """Debe loggear warning si stats contiene errores."""
        patch_ingest.return_value = {"files_processed": 5, "chunks_inserted": 20, "errors": 2}
        from harness.run_commands import _handle_rag_ingest
        _handle_rag_ingest(mock_store, "!rag ingest")

    def test_rag_stats_con_chunks(self, mock_store):
        """!rag stats debe mostrar stats si coleccion existe."""
        mock_store.list_collections.return_value = ["rag_chunks"]
        mock_store.get_collection_stats.return_value = {"item_count": 150, "last_updated": "2026-01-01"}
        from harness.run_commands import _handle_rag_stats
        _handle_rag_stats(mock_store)

    def test_rag_stats_sin_chunks(self, mock_store):
        """!rag stats debe indicar que coleccion no existe."""
        mock_store.list_collections.return_value = ["other"]
        from harness.run_commands import _handle_rag_stats
        _handle_rag_stats(mock_store)

    def test_rag_stats_error_get_stats(self, mock_store):
        """Si get_collection_stats lanza excepcion, debe loggear."""
        mock_store.list_collections.return_value = ["rag_chunks"]
        mock_store.get_collection_stats.side_effect = Exception("DB error")
        from harness.run_commands import _handle_rag_stats
        _handle_rag_stats(mock_store)


# ===================================================================
# DB Commands
# ===================================================================

class TestDbCommands:
    """Tests para comandos DB: migrate, list-imports, stats, rollback."""

    @pytest.fixture(autouse=True)
    def patch_migrator(self):
        """Parchea DBMigrator (import lazy dentro de las funciones)."""
        with patch("harness.db.migrate_db.DBMigrator") as m:
            yield m

    def test_db_migrate_sin_path_con_imports(self, mock_store, patch_migrator):
        """!db migrate sin --path debe escanear imports y migrar todos."""
        mock_migrator = MagicMock()
        mock_migrator.scan_imports.return_value = [
            {"name": "db1", "path": "/tmp/db1", "collections": ["a"], "estimated_size_human": "1MB"},
        ]
        mock_migrator.migrate.return_value = {
            "migrated_collections": ["a"], "created": [], "skipped": [], "errors": [],
            "backup_path": "/backup",
        }
        patch_migrator.return_value = mock_migrator
        from harness.run_commands import _handle_db_migrate
        _handle_db_migrate(mock_store, "!db migrate")

    def test_db_migrate_sin_imports(self, mock_store, patch_migrator):
        """!db migrate sin imports debe loggear que no hay bases."""
        mock_migrator = MagicMock()
        mock_migrator.scan_imports.return_value = []
        patch_migrator.return_value = mock_migrator
        from harness.run_commands import _handle_db_migrate
        _handle_db_migrate(mock_store, "!db migrate")

    def test_db_migrate_con_path(self, mock_store, patch_migrator):
        """!db migrate --path <ruta> debe migrar ruta especifica."""
        mock_migrator = MagicMock()
        mock_migrator.migrate.return_value = {
            "migrated_collections": ["a"], "created": ["b"], "skipped": [], "errors": [],
        }
        patch_migrator.return_value = mock_migrator
        from harness.run_commands import _handle_db_migrate
        _handle_db_migrate(mock_store, "!db migrate --path /custom/path")

    def test_db_migrate_path_sin_valor(self, mock_store, patch_migrator):
        """!db migrate --path sin valor debe loggear error."""
        from harness.run_commands import _handle_db_migrate
        _handle_db_migrate(mock_store, "!db migrate --path")

    def test_db_list_imports_vacio(self, patch_migrator):
        """!db list-imports sin imports debe loggear mensaje."""
        mock_migrator = MagicMock()
        mock_migrator.scan_imports.return_value = []
        patch_migrator.return_value = mock_migrator
        from harness.run_commands import _handle_db_list_imports
        _handle_db_list_imports()

    def test_db_list_imports_con_datos(self, patch_migrator):
        """!db list-imports con imports debe mostrar lista."""
        mock_migrator = MagicMock()
        mock_migrator.scan_imports.return_value = [
            {"name": "db1", "collections": ["a", "b"], "estimated_size_human": "2MB"},
        ]
        patch_migrator.return_value = mock_migrator
        from harness.run_commands import _handle_db_list_imports
        _handle_db_list_imports()

    def test_db_stats(self, mock_store, patch_migrator):
        """!db stats debe mostrar estadisticas de BD activa."""
        mock_migrator = MagicMock()
        mock_migrator.get_stats.return_value = {
            "path": "/db", "total_chunks": 100, "size_human": "10MB",
            "last_modified": "2026-01-01", "collections": [
                {"name": "docs", "count": 50},
                {"name": "code", "count": -1, "error": "corrupt"},
            ],
        }
        patch_migrator.return_value = mock_migrator
        from harness.run_commands import _handle_db_stats
        _handle_db_stats(mock_store)

    def test_db_rollback_ok(self, patch_migrator):
        """!db rollback con ruta valida debe restaurar."""
        mock_migrator = MagicMock()
        mock_migrator.rollback.return_value = True
        patch_migrator.return_value = mock_migrator
        from harness.run_commands import _handle_db_rollback
        _handle_db_rollback("!db rollback /backups/2026-01-01")

    def test_db_rollback_fail(self, patch_migrator):
        """!db rollback con error debe loggear fallo."""
        mock_migrator = MagicMock()
        mock_migrator.rollback.return_value = False
        patch_migrator.return_value = mock_migrator
        from harness.run_commands import _handle_db_rollback
        _handle_db_rollback("!db rollback /bad/backup")

    def test_db_rollback_sin_args(self, patch_migrator):
        """!db rollback sin argumentos debe mostrar uso."""
        from harness.run_commands import _handle_db_rollback
        _handle_db_rollback("!db rollback")


# ===================================================================
# Iteration Commands
# ===================================================================

class TestIterationFlags:
    """Tests para _parse_iteration_flags — parsing de flags de iteracion."""

    def test_no_flags(self):
        """Sin flags todos los valores deben ser False."""
        from harness.run_commands import _parse_iteration_flags
        flags = _parse_iteration_flags("!iteration end")
        assert flags == {"skip_bugs": False, "skip_sec": False, "skip_docs": False,
                         "dry_run": False, "quick": False, "auto": False}

    def test_all_flags(self):
        """Con todos los flags presentes deben ser True."""
        from harness.run_commands import _parse_iteration_flags
        cmd = "!iteration end --dry-run --skip-bugs --skip-sec --skip-docs --quick --auto"
        flags = _parse_iteration_flags(cmd)
        assert all(flags.values())

    def test_dry_run_only(self):
        """Solo --dry-run debe ser True."""
        from harness.run_commands import _parse_iteration_flags
        flags = _parse_iteration_flags("!iteration end --dry-run")
        assert flags["dry_run"] is True
        assert flags["skip_bugs"] is False

    def test_skip_combinations(self):
        """Combinacion parcial de flags skip."""
        from harness.run_commands import _parse_iteration_flags
        flags = _parse_iteration_flags("!iteration end --skip-bugs --skip-docs")
        assert flags["skip_bugs"] is True
        assert flags["skip_sec"] is False
        assert flags["skip_docs"] is True


class TestIterationEnd:
    """Tests para _handle_iteration_end."""

    @pytest.fixture(autouse=True)
    def patch_end_iter(self):
        """Parchea run_pipeline importado dentro de la funcion."""
        with patch("harness.scripts.end_of_iteration.run_pipeline") as m:
            yield m

    def test_iteration_end_basic(self, patch_end_iter):
        """!iteration end debe ejecutar pipeline completo."""
        with patch("harness.run_commands.sys.path"):
            from harness.run_commands import _handle_iteration_end
            _handle_iteration_end("!iteration end", Path("/fake/harness"))
        patch_end_iter.assert_called_once_with(
            skip_bugs=False, skip_security=False, skip_docs=False, dry_run=False,
        )

    def test_iteration_end_dry_run(self, patch_end_iter):
        """!iteration end --dry-run debe pasar dry_run=True."""
        with patch("harness.run_commands.sys.path"):
            from harness.run_commands import _handle_iteration_end
            _handle_iteration_end("!iteration end --dry-run", Path("/fake/harness"))
        patch_end_iter.assert_called_once_with(
            skip_bugs=False, skip_security=False, skip_docs=False, dry_run=True,
        )

    def test_iteration_end_skip_flags(self, patch_end_iter):
        """!iteration end con flags skip debe pasarlos correctamente."""
        with patch("harness.run_commands.sys.path"):
            from harness.run_commands import _handle_iteration_end
            cmd = "!iteration end --skip-bugs --skip-sec --skip-docs"
            _handle_iteration_end(cmd, Path("/fake/harness"))
        patch_end_iter.assert_called_once_with(
            skip_bugs=True, skip_security=True, skip_docs=True, dry_run=False,
        )

    def test_iteration_end_quick_redirect(self):
        """!iteration end --quick debe redirigir a _handle_iteration_quick."""
        with patch("harness.run_commands._handle_iteration_quick") as mock_fn:
            from harness.run_commands import _handle_iteration_end
            _handle_iteration_end("!iteration end --quick", Path("/fake/harness"))
        mock_fn.assert_called_once()

    def test_iteration_end_auto_redirect(self):
        """!iteration end --auto debe redirigir a _handle_iteration_auto."""
        with patch("harness.run_commands._handle_iteration_auto") as mock_fn:
            from harness.run_commands import _handle_iteration_end
            _handle_iteration_end("!iteration end --auto", Path("/fake/harness"))
        mock_fn.assert_called_once()


class TestIterationQuick:
    """Tests para _handle_iteration_quick."""

    def test_quick_pipeline(self):
        """!iteration quick debe ejecutar run_quick_pipeline."""
        with patch("harness.scripts.end_of_iteration.run_quick_pipeline") as mock_fn, \
             patch("harness.run_commands.sys.path"):
            from harness.run_commands import _handle_iteration_quick
            _handle_iteration_quick("!iteration quick", Path("/fake/harness"))
        mock_fn.assert_called_once()


class TestIterationAuto:
    """Tests para _handle_iteration_auto."""

    def test_auto_pipeline(self):
        """!iteration auto debe ejecutar run_auto_pipeline."""
        with patch("harness.scripts.end_of_iteration.run_auto_pipeline") as mock_fn, \
             patch("harness.run_commands.sys.path"):
            from harness.run_commands import _handle_iteration_auto
            _handle_iteration_auto("!iteration auto", Path("/fake/harness"))
        mock_fn.assert_called_once()


class TestIterationReport:
    """Tests para _handle_iteration_report."""

    def test_report(self):
        """!iteration report debe llamar a print_last_report."""
        with patch("harness.scripts.end_of_iteration.print_last_report") as mock_fn:
            from harness.run_commands import _handle_iteration_report
            _handle_iteration_report()
        mock_fn.assert_called_once()


class TestIterationHistory:
    """Tests para _handle_iteration_history."""

    def test_history_default(self):
        """!iteration history debe mostrar ultimas 10."""
        with patch("harness.scripts.end_of_iteration.show_iteration_history") as mock_fn:
            from harness.run_commands import _handle_iteration_history
            _handle_iteration_history("!iteration history")
        mock_fn.assert_called_once_with(limit=10)

    def test_history_all(self):
        """!iteration history --all debe mostrar todas."""
        with patch("harness.scripts.end_of_iteration.show_iteration_history") as mock_fn:
            from harness.run_commands import _handle_iteration_history
            _handle_iteration_history("!iteration history --all")
        mock_fn.assert_called_once_with(limit=0)


class TestIterationDiff:
    """Tests para _handle_iteration_diff."""

    def test_diff_default(self):
        """!iteration diff debe mostrar la ultima (n=1)."""
        with patch("harness.scripts.end_of_iteration.show_iteration_diff") as mock_fn:
            from harness.run_commands import _handle_iteration_diff
            _handle_iteration_diff("!iteration diff")
        mock_fn.assert_called_once_with(n=1)

    def test_diff_last(self):
        """!iteration diff --last debe mostrar la ultima."""
        with patch("harness.scripts.end_of_iteration.show_iteration_diff") as mock_fn:
            from harness.run_commands import _handle_iteration_diff
            _handle_iteration_diff("!iteration diff --last")
        mock_fn.assert_called_once_with(n=1)

    def test_diff_n(self):
        """!iteration diff --n 3 debe mostrar la antepenultima."""
        with patch("harness.scripts.end_of_iteration.show_iteration_diff") as mock_fn:
            from harness.run_commands import _handle_iteration_diff
            _handle_iteration_diff("!iteration diff --n 3")
        mock_fn.assert_called_once_with(n=3)

    def test_diff_n_invalido(self):
        """!iteration diff --n con valor invalido debe usar default 1."""
        with patch("harness.scripts.end_of_iteration.show_iteration_diff") as mock_fn:
            from harness.run_commands import _handle_iteration_diff
            _handle_iteration_diff("!iteration diff --n abc")
        mock_fn.assert_called_once_with(n=1)

    def test_diff_n_cero(self):
        """!iteration diff --n 0 debe usar max(1, 0) = 1."""
        with patch("harness.scripts.end_of_iteration.show_iteration_diff") as mock_fn:
            from harness.run_commands import _handle_iteration_diff
            _handle_iteration_diff("!iteration diff --n 0")
        mock_fn.assert_called_once_with(n=1)


# ===================================================================
# Hooks Commands
# ===================================================================

class TestHooksCommands:
    """Tests para comandos hooks: install, uninstall, status."""

    def test_hooks_install(self):
        """!hooks install debe llamar a install_hook."""
        with patch("harness.scripts.install_hooks.install_hook") as mock_fn:
            from harness.run_commands import _handle_hooks_install
            _handle_hooks_install()
        mock_fn.assert_called_once()

    def test_hooks_uninstall(self):
        """!hooks uninstall debe llamar a uninstall_hook."""
        with patch("harness.scripts.install_hooks.uninstall_hook") as mock_fn:
            from harness.run_commands import _handle_hooks_uninstall
            _handle_hooks_uninstall()
        mock_fn.assert_called_once()

    def test_hooks_status(self):
        """!hooks status debe llamar a show_status."""
        with patch("harness.scripts.install_hooks.show_status") as mock_fn:
            from harness.run_commands import _handle_hooks_status
            _handle_hooks_status()
        mock_fn.assert_called_once()


# ===================================================================
# Evolve Commands
# ===================================================================

class TestEvolveCommands:
    """Tests para _handle_evolve_mutate."""

    @pytest.fixture(autouse=True)
    def patch_evolver(self):
        """Parchea PromptEvolver (import lazy dentro de la funcion)."""
        with patch("harness.evolve_loop.prompt_evolver.PromptEvolver") as m:
            yield m

    def test_evolve_mutate_too_few_args(self, mock_store, patch_evolver):
        """!evolve mutate sin suficientes argumentos debe mostrar uso."""
        from harness.run_commands import _handle_evolve_mutate
        _handle_evolve_mutate(mock_store, "!evolve mutate")

    def test_evolve_mutate_agent_not_found(self, mock_store, patch_evolver):
        """!evolve mutate con agente inexistente debe loggear error."""
        with patch("harness.run_commands.os.path.exists", return_value=False):
            from harness.run_commands import _handle_evolve_mutate
            _handle_evolve_mutate(mock_store, '!evolve mutate @ghost "tarea"')

    def test_evolve_mutate_no_mutants(self, mock_store, patch_evolver):
        """Si mutate_prompt no genera mutantes, debe loggear."""
        mock_evolver = MagicMock()
        mock_evolver.mutate_prompt.return_value = []
        patch_evolver.return_value = mock_evolver
        with patch("harness.run_commands.os.path.exists", return_value=True):
            from harness.run_commands import _handle_evolve_mutate
            _handle_evolve_mutate(mock_store, '!evolve mutate @builder "mejora"')

    def test_evolve_mutate_full_flow(self, mock_store, patch_evolver):
        """Flujo completo de evolucion con mutantes y promocion."""
        mock_evolver = MagicMock()
        mock_evolver.mutate_prompt.return_value = ["mutant_v1.md"]
        mock_evolver.evaluate_mutants.return_value = {
            "original": {"score": 50, "tokens": 100, "success": True, "time": 1.0},
            "mutant_v1.md": {"score": 85, "tokens": 120, "success": True, "time": 1.5},
        }
        mock_evolver.promote_winner.return_value = True
        patch_evolver.return_value = mock_evolver
        with patch("harness.run_commands.os.path.exists", return_value=True):
            from harness.run_commands import _handle_evolve_mutate
            _handle_evolve_mutate(mock_store, '!evolve mutate @builder "mejora"')
        mock_evolver.promote_winner.assert_called_once()

    def test_evolve_mutate_original_wins(self, mock_store, patch_evolver):
        """Si el original tiene mejor score, no debe promover."""
        mock_evolver = MagicMock()
        mock_evolver.mutate_prompt.return_value = ["mutant_v1.md"]
        mock_evolver.evaluate_mutants.return_value = {
            "original": {"score": 90, "tokens": 100, "success": True, "time": 1.0},
            "mutant_v1.md": {"score": 50, "tokens": 120, "success": True, "time": 1.5},
        }
        patch_evolver.return_value = mock_evolver
        with patch("harness.run_commands.os.path.exists", return_value=True):
            from harness.run_commands import _handle_evolve_mutate
            _handle_evolve_mutate(mock_store, '!evolve mutate @builder "mejora"')
        mock_evolver.promote_winner.assert_not_called()


# ===================================================================
# Schedule Commands
# ===================================================================

class TestScheduleCommands:
    """Tests para _handle_schedule_add y _handle_schedule_list."""

    @pytest.fixture(autouse=True)
    def patch_scheduler(self):
        """Parchea Scheduler (import lazy dentro de las funciones)."""
        with patch("harness.orchestrator.scheduler.Scheduler") as m:
            yield m

    def test_schedule_add_too_few_args(self, mock_store, patch_scheduler):
        """!schedule add con pocos argumentos debe mostrar uso."""
        from harness.run_commands import _handle_schedule_add
        _handle_schedule_add(mock_store, "!schedule add")

    def test_schedule_add_cron(self, mock_store, patch_scheduler):
        """!schedule add con --cron debe crear job."""
        mock_sched = MagicMock()
        mock_job = MagicMock()
        mock_job.name = "test_job"
        mock_job.trigger = "cron"
        mock_job.trigger_value = "0 * * * *"
        mock_sched.add_job.return_value = mock_job
        patch_scheduler.return_value = mock_sched

        from harness.run_commands import _handle_schedule_add
        _handle_schedule_add(
            mock_store,
            '!schedule add test_job --cron "0 * * * *" --task "echo hello"',
        )
        mock_sched.add_job.assert_called_once_with(
            name="test_job", trigger="cron", trigger_value="0 * * * *",
            command="echo hello",
        )

    def test_schedule_add_interval(self, mock_store, patch_scheduler):
        """!schedule add con --interval debe crear job."""
        mock_sched = MagicMock()
        mock_job = MagicMock()
        mock_job.name = "test"
        mock_job.trigger = "interval"
        mock_job.trigger_value = "30m"
        mock_sched.add_job.return_value = mock_job
        patch_scheduler.return_value = mock_sched

        from harness.run_commands import _handle_schedule_add
        _handle_schedule_add(
            mock_store, '!schedule add test --interval "30m" --task "ping"',
        )

    def test_schedule_add_once(self, mock_store, patch_scheduler):
        """!schedule add con --once debe crear job one-shot."""
        mock_sched = MagicMock()
        mock_job = MagicMock()
        mock_sched.add_job.return_value = mock_job
        patch_scheduler.return_value = mock_sched

        from harness.run_commands import _handle_schedule_add
        _handle_schedule_add(
            mock_store, '!schedule add test --once "2026-12-31T23:59" --task "backup"',
        )

    def test_schedule_add_sin_trigger(self, mock_store, patch_scheduler):
        """!schedule add sin --cron/--interval/--once debe loggear error."""
        from harness.run_commands import _handle_schedule_add
        _handle_schedule_add(mock_store, '!schedule add test --task "cmd"')

    def test_schedule_list_empty(self, mock_store, patch_scheduler):
        """!schedule list sin jobs debe mostrar mensaje."""
        mock_sched = MagicMock()
        mock_sched.list_jobs.return_value = []
        patch_scheduler.return_value = mock_sched
        from harness.run_commands import _handle_schedule_list
        _handle_schedule_list(mock_store)

    def test_schedule_list_with_jobs(self, mock_store, patch_scheduler):
        """!schedule list con jobs debe mostrar lista."""
        mock_job = MagicMock()
        mock_job.name = "daily"
        mock_job.trigger = "cron"
        mock_job.trigger_value = "0 9 * * *"
        mock_job.enabled = True
        mock_job.last_run = "2026-01-01"
        mock_sched = MagicMock()
        mock_sched.list_jobs.return_value = [mock_job]
        patch_scheduler.return_value = mock_sched
        from harness.run_commands import _handle_schedule_list
        _handle_schedule_list(mock_store)


# ===================================================================
# Model Routing
# ===================================================================

class TestModelRouting:
    """Tests para _apply_model_routing."""

    @pytest.fixture(autouse=True)
    def patch_router(self):
        """Parchea ModelRouter (import lazy dentro de la funcion)."""
        with patch("harness.model_router.router.ModelRouter") as m:
            yield m

    def test_force_cloud(self, patch_router):
        """Con force_cloud=True debe retornar 'cloud' inmediatamente."""
        from harness.run_commands import _apply_model_routing
        result = _apply_model_routing("mi tarea", "builder", force_cloud=True)
        assert result == "cloud"

    def test_routing_local(self, patch_router):
        """Si router decide local, debe retornar 'local'."""
        mock_router = MagicMock()
        mock_decision = MagicMock()
        mock_decision.source = "local"
        mock_decision.provider = "ollama"
        mock_decision.model = "llama3"
        mock_decision.reason = "small task"
        mock_router.route.return_value = mock_decision
        mock_router._is_ollama_available.return_value = True
        mock_router.config = {"local": {"fallback_to_cloud": True}}
        patch_router.return_value = mock_router

        from harness.run_commands import _apply_model_routing
        result = _apply_model_routing("mi tarea", "builder")
        assert result == "local"

    def test_routing_local_ollama_no_disponible(self, patch_router):
        """Si router decide local pero Ollama no esta, debe loggear warning."""
        mock_router = MagicMock()
        mock_decision = MagicMock()
        mock_decision.source = "local"
        mock_decision.provider = "ollama"
        mock_decision.model = "llama3"
        mock_decision.reason = "small"
        mock_router.route.return_value = mock_decision
        mock_router._is_ollama_available.return_value = False
        mock_router.config = {"local": {"fallback_to_cloud": False}}
        patch_router.return_value = mock_router

        from harness.run_commands import _apply_model_routing
        result = _apply_model_routing("mi tarea", "builder")
        assert result == "local"

    def test_routing_local_ollama_fallback(self, patch_router):
        """Si router decide local, Ollama no disponible pero fallback activo."""
        mock_router = MagicMock()
        mock_decision = MagicMock()
        mock_decision.source = "local"
        mock_decision.provider = "ollama"
        mock_decision.model = "llama3"
        mock_decision.reason = "small"
        mock_router.route.return_value = mock_decision
        mock_router._is_ollama_available.return_value = False
        mock_router.config = {"local": {"fallback_to_cloud": True}}
        patch_router.return_value = mock_router

        from harness.run_commands import _apply_model_routing
        result = _apply_model_routing("mi tarea", "builder")
        assert result == "local"


# ===================================================================
# HITL Guard
# ===================================================================

class TestCheckHitl:
    """Tests para _check_hitl — Human-in-the-Loop."""

    def test_auto_pilot_aprueba(self):
        """En modo auto_pilot siempre retorna True."""
        guard = MagicMock()
        guard.mode = "auto_pilot"
        from harness.run_commands import _check_hitl
        assert _check_hitl("accion destructiva", "builder", guard) is True
        guard.check_action.assert_not_called()

    def test_hitl_aprueba(self):
        """Si check_action dice approved=True, retorna True."""
        guard = MagicMock()
        guard.mode = "hitl"
        guard.check_action.return_value = {"approved": True}
        from harness.run_commands import _check_hitl
        assert _check_hitl("accion normal", "builder", guard) is True

    def test_hitl_requiere_aprobacion(self):
        """Si check_action no aprueba, delega a request_approval."""
        guard = MagicMock()
        guard.mode = "hitl"
        guard.check_action.return_value = {"approved": False}
        guard.request_approval.return_value = True
        from harness.run_commands import _check_hitl
        assert _check_hitl("accion sensible", "builder", guard) is True
        guard.request_approval.assert_called_once_with("accion sensible", "builder")

    def test_hitl_bloqueado(self):
        """Si request_approval retorna False, la accion es bloqueada."""
        guard = MagicMock()
        guard.mode = "hitl"
        guard.check_action.return_value = {"approved": False}
        guard.request_approval.return_value = False
        from harness.run_commands import _check_hitl
        assert _check_hitl("accion bloqueada", "builder", guard) is False


# ===================================================================
# Watch Mode
# ===================================================================

class TestGetFilesToWatch:
    """Tests para _get_files_to_watch — snapshots de archivos."""

    def test_get_files_to_watch(self, tmp_path):
        """Debe retornar dict con archivos .py/.md/.yaml/.yml/.json."""
        harness_dir = tmp_path / "harness"
        harness_dir.mkdir()
        (harness_dir / "test.py").write_text("x")
        (harness_dir / "readme.md").write_text("x")
        (harness_dir / "data.json").write_text("{}")
        (harness_dir / "ignored.txt").write_text("x")
        (harness_dir / "__pycache__").mkdir()
        (harness_dir / "__pycache__" / "cache.py").write_text("x")
        opencode_dir = tmp_path / ".opencode"
        opencode_dir.mkdir()
        (opencode_dir / "config.yaml").write_text("key: val")
        (opencode_dir / ".git").mkdir()
        (opencode_dir / ".git" / "HEAD").write_text("ref")

        with patch("harness.run_commands.os.path.isdir", return_value=True), \
             patch("harness.run_commands.os.walk") as mock_walk:
            mock_walk.side_effect = [
                iter([
                    (str(harness_dir), ["__pycache__"],
                     ["test.py", "readme.md", "data.json", "ignored.txt"]),
                    (str(harness_dir / "__pycache__"), [], ["cache.py"]),
                ]),
                iter([
                    (str(opencode_dir), [".git"], ["config.yaml"]),
                    (str(opencode_dir / ".git"), [], ["HEAD"]),
                ]),
            ]
            from harness.run_commands import _get_files_to_watch
            result = _get_files_to_watch(harness_dir)

        keys = list(result.keys())
        assert any(k.endswith("test.py") for k in keys)
        assert any(k.endswith("readme.md") for k in keys)
        assert any(k.endswith("data.json") for k in keys)
        assert any(k.endswith("config.yaml") for k in keys)
        assert not any(k.endswith("ignored.txt") for k in keys)

    def test_watch_dir_no_existe(self, tmp_path):
        """Si un directorio no existe, debe omitirlo silenciosamente."""
        with patch("harness.run_commands.os.path.isdir", return_value=False):
            from harness.run_commands import _get_files_to_watch
            result = _get_files_to_watch(tmp_path / "no_existe")
        assert result == {}


class TestHandleWatchMode:
    """Tests para _handle_watch_mode."""

    def test_watch_mode_no_eoi_script(self, tmp_path):
        """Si end_of_iteration.py no existe, debe loggear error y retornar."""
        harness_dir = tmp_path / "harness"
        harness_dir.mkdir()
        with patch("harness.run_commands._safe_print"):
            from harness.run_commands import _handle_watch_mode
            _handle_watch_mode(harness_dir)

    def test_watch_mode_loop_keyboard_interrupt(self, tmp_path):
        """Watch mode debe detenerse con KeyboardInterrupt."""
        harness_dir = tmp_path / "harness"
        harness_dir.mkdir()
        scripts_dir = harness_dir / "scripts"
        scripts_dir.mkdir()
        (scripts_dir / "end_of_iteration.py").write_text("")
        mock_snapshot = {"/fake/file.py": 1000.0}
        with patch("harness.run_commands._get_files_to_watch",
                   return_value=mock_snapshot), \
             patch("harness.run_commands._safe_print"), \
             patch("harness.run_commands.time.sleep", side_effect=KeyboardInterrupt):
            from harness.run_commands import _handle_watch_mode
            _handle_watch_mode(harness_dir)

    def test_watch_mode_detecta_cambios(self, tmp_path):
        """Watch mode debe detectar cambios y ejecutar pipeline."""
        harness_dir = tmp_path / "harness"
        harness_dir.mkdir()
        scripts_dir = harness_dir / "scripts"
        scripts_dir.mkdir()
        (scripts_dir / "end_of_iteration.py").write_text("")
        mock_result = MagicMock()
        mock_result.stdout = "stdout line"
        mock_result.stderr = ""

        call_count = [0]

        def snapshot_side_effect(_path):
            """1ra llamada: vacio, resto: con cambios -> trigger ejecucion -> exit."""
            nonlocal call_count
            call_count[0] += 1
            if call_count[0] == 1:
                return {}
            if call_count[0] >= 4:
                raise KeyboardInterrupt()
            return {"/fake/file.py": float(1000 + call_count[0])}

        with patch("harness.run_commands._get_files_to_watch",
                   side_effect=snapshot_side_effect), \
             patch("harness.run_commands._safe_print"), \
             patch("harness.run_commands.time.sleep"), \
             patch("harness.run_commands.time.time", return_value=100.0):

            from harness.run_commands import _handle_watch_mode
            _handle_watch_mode(harness_dir)


# ===================================================================
# Hermes Commands
# ===================================================================

class TestHermes:
    """Tests para _handle_hermes."""

    @pytest.fixture(autouse=True)
    def patch_hermes(self):
        """Parchea HermesBridge (import lazy dentro de la funcion)."""
        with patch("harness.hermes_bridge.HermesBridge") as m:
            yield m

    def test_hermes_sync(self, patch_hermes):
        """!hermes sync debe ejecutar sync_all."""
        mock_bridge = MagicMock()
        mock_bridge.sync_all.return_value = {"synced": 10}
        patch_hermes.return_value = mock_bridge
        from harness.run_commands import _handle_hermes
        _handle_hermes("!hermes sync")
        mock_bridge.sync_all.assert_called_once()

    def test_hermes_stats(self, patch_hermes):
        """!hermes stats debe ejecutar get_stats."""
        mock_bridge = MagicMock()
        mock_bridge.get_stats.return_value = {"docs": 5}
        patch_hermes.return_value = mock_bridge
        from harness.run_commands import _handle_hermes
        _handle_hermes("!hermes stats")
        mock_bridge.get_stats.assert_called_once()

    def test_hermes_empty(self, patch_hermes):
        """!hermes sin subcomando debe mostrar ayuda."""
        from harness.run_commands import _handle_hermes
        _handle_hermes("!hermes")

    def test_hermes_help(self, patch_hermes):
        """!hermes help debe mostrar ayuda."""
        from harness.run_commands import _handle_hermes
        _handle_hermes("!hermes help")

    def test_hermes_unknown(self, patch_hermes):
        """!hermes <subcomando desconocido> debe loggear warning."""
        from harness.run_commands import _handle_hermes
        _handle_hermes("!hermes invalid_sub")


# ===================================================================
# Guardrails
# ===================================================================

class TestGuardrails:
    """Tests para _run_guardrails."""

    def test_guardrails_no_disponible(self):
        """Si run_full_pipeline es None, debe loggear y retornar."""
        from harness.run_commands import _run_guardrails
        _run_guardrails("tarea", "builder", MagicMock(), "local", run_full_pipeline=None)

    def test_guardrails_ok(self):
        """Si guardrails pasan, debe loggear OK."""
        mock_pipeline = MagicMock()
        mock_pipeline.return_value = {
            "allowed": True,
            "summary": {"passed": 3, "total_checks": 3},
        }
        mock_ctx = MagicMock()
        mock_ctx.relevant_docs = ["d1"]
        mock_ctx.metadata = {"total_tokens_used": 500}
        from harness.run_commands import _run_guardrails
        _run_guardrails("tarea", "builder", mock_ctx, "cloud", mock_pipeline)

    def test_guardrails_blocked(self):
        """Si guardrails bloquean, debe hacer sys.exit(1)."""
        mock_pipeline = MagicMock()
        mock_pipeline.return_value = {
            "allowed": False,
            "blocked_at": "pre",
            "summary": {"failed_rules": ["pii_detected"], "passed": 2, "total_checks": 3},
        }
        mock_ctx = MagicMock()
        mock_ctx.relevant_docs = ["d1"]
        with pytest.raises(SystemExit):
            from harness.run_commands import _run_guardrails
            _run_guardrails("tarea sensible", "builder", mock_ctx, "local", mock_pipeline)

    def test_guardrails_ctx_sin_relevant_docs(self):
        """Si ctx no tiene relevant_docs, debe manejar gracefulmente."""
        mock_pipeline = MagicMock()
        mock_pipeline.return_value = {
            "allowed": True,
            "summary": {"passed": 2, "total_checks": 2},
        }
        mock_ctx = MagicMock(spec=[])
        with patch("harness.run_commands.hasattr", return_value=False):
            from harness.run_commands import _run_guardrails
            _run_guardrails("tarea", "builder", mock_ctx, "local", mock_pipeline)


# ===================================================================
# ANSI Helpers
# ===================================================================

class TestAnsiHelpers:
    """Tests para helpers ANSI: _ok, _warn, _err, _bold, _cyan, _safe_print."""

    def test_ok(self):
        """_ok debe devolver string con codigo verde."""
        from harness.run_commands import _ok
        result = _ok("mensaje")
        assert "\033[92m" in result
        assert "\033[0m" in result

    def test_warn(self):
        """_warn debe devolver string con codigo amarillo."""
        from harness.run_commands import _warn
        result = _warn("warning")
        assert "\033[93m" in result

    def test_err(self):
        """_err debe devolver string con codigo rojo."""
        from harness.run_commands import _err
        result = _err("error")
        assert "\033[91m" in result

    def test_bold(self):
        """_bold debe devolver string con codigo bold."""
        from harness.run_commands import _bold
        result = _bold("importante")
        assert "\033[1m" in result

    def test_cyan(self):
        """_cyan debe devolver string con codigo cyan."""
        from harness.run_commands import _cyan
        result = _cyan("info")
        assert "\033[96m" in result

    def test_safe_print_ok(self, capsys):
        """_safe_print debe imprimir normalmente si no hay UnicodeEncodeError."""
        from harness.run_commands import _safe_print
        _safe_print("texto normal")
        captured = capsys.readouterr()
        assert captured.out.strip() == "texto normal"

    def test_safe_print_unicode_fallback(self):
        """_safe_print debe reemplazar caracteres no-ASCII si hay error."""
        import builtins

        from harness.run_commands import _safe_print
        original_print = builtins.print

        call_count = 0

        def mock_print(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise UnicodeEncodeError("codec", "message", 0, 1, "cannot encode")
            original_print(*args, **kwargs)

        with patch.object(builtins, "print", mock_print):
            _safe_print("texto con \u2014 em\u2014dash")

        # Debe haber invocado print dos veces (fallo + reintento)
        assert call_count >= 2
