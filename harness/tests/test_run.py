"""
Tests para harness/run.py — entry point CLI del Harness.

Cubre: _parse_args, _show_usage, _handle_gateway_mode, _handle_daemon_mode,
_handle_command, _display_plan, _dispatch_task, _resolve_hitl_mode,
_ensure_rag_context, _create_task_and_lesson, _display_final_output,
_start_sandbox_if_needed, _check_lancedb_or_exit, main.
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def patch_harness_imports():
    """Parchea importaciones de modulo top-level y variables globales de run.py.

    run.py ejecuta codigo a nivel de modulo: inserts en sys.path, imports
    condicionales (lancedb, guardrails) y asignacion de HARNESS_ROOT.
    Parcheamos todo para que los tests sean deterministicos.
    """
    patches = [
        # Evita que sys.path.insert falle o modifique el path real
        patch("harness.run.get_project_root", return_value=Path("/fake/project")),
        patch("harness.run.get_harness_root", return_value=Path("/fake/harness")),
        # HAS_LANCEDB = True para que main() no haga sys.exit(1)
        patch("harness.run.HAS_LANCEDB", True),
        # run_full_pipeline disponible por defecto
        patch("harness.run.run_full_pipeline", MagicMock()),
        # Parchea loggers para evitar ruido
        patch("harness.run.logger"),
        patch("harness.run._safe_print"),
    ]
    for p in patches:
        p.start()
    yield
    for p in patches:
        p.stop()


@pytest.fixture
def mock_store():
    """Mock de LanceVectorStore."""
    return MagicMock()


@pytest.fixture
def mock_orch_result():
    """Mock de resultado de TaskOrchestrator."""
    from types import SimpleNamespace

    mock_plan = MagicMock()
    mock_plan.get_levels.return_value = []
    mock_plan.subtasks = []
    mock_plan.errors = []

    result = SimpleNamespace(
        is_new_plan=True,
        session_id="test-session-001",
        target_agent="builder",
        session_status="plan-ready",
        current_level=[],
        previous_results=[],
        communication_log=[],
        is_complete=False,
        plan=mock_plan,
    )
    return result


# ===================================================================
# _parse_args
# ===================================================================

class TestParseArgs:
    """Tests para _parse_args — parsing de argumentos CLI."""

    def test_sin_argumentos(self):
        """Debe retornar task=None y command=None sin argumentos."""
        with patch("harness.run.sys.argv", ["run.py"]):
            from harness.run import _parse_args
            parsed = _parse_args()
        assert parsed["task"] is None
        assert parsed["command"] is None
        assert parsed["help"] is False
        assert parsed["daemon"] is False

    def test_task_simple(self):
        """Debe extraer la tarea como string."""
        with patch("harness.run.sys.argv", ["run.py", "implementa API REST"]):
            from harness.run import _parse_args
            parsed = _parse_args()
        assert parsed["task"] == "implementa API REST"

    def test_flag_help(self):
        """Debe detectar --help."""
        with patch("harness.run.sys.argv", ["run.py", "--help"]):
            from harness.run import _parse_args
            parsed = _parse_args()
        assert parsed["help"] is True

    def test_flag_daemon(self):
        """Debe detectar --daemon."""
        with patch("harness.run.sys.argv", ["run.py", "--daemon"]):
            from harness.run import _parse_args
            parsed = _parse_args()
        assert parsed["daemon"] is True

    def test_flag_watch(self):
        """Debe detectar --watch."""
        with patch("harness.run.sys.argv", ["run.py", "--watch"]):
            from harness.run import _parse_args
            parsed = _parse_args()
        assert parsed["watch"] is True

    def test_flag_gateway(self):
        """Debe detectar --gateway con valor."""
        with patch("harness.run.sys.argv", ["run.py", "--gateway", "slack"]):
            from harness.run import _parse_args
            parsed = _parse_args()
        assert parsed["gateway"] == "slack"

    def test_flag_gateway_sin_valor(self):
        """Si --gateway es el ultimo arg, gateway=None."""
        with patch("harness.run.sys.argv", ["run.py", "--gateway"]):
            from harness.run import _parse_args
            parsed = _parse_args()
        assert parsed["gateway"] is None

    def test_force_cloud(self):
        """Debe detectar --force-cloud."""
        with patch("harness.run.sys.argv", ["run.py", "--force-cloud", "@builder: crea API"]):
            from harness.run import _parse_args
            parsed = _parse_args()
        assert parsed["force_cloud"] is True
        assert parsed["task"] == "@builder: crea API"

    def test_auto_pilot(self):
        """Debe detectar --auto-pilot."""
        with patch("harness.run.sys.argv", ["run.py", "--auto-pilot", "tarea"]):
            from harness.run import _parse_args
            parsed = _parse_args()
        assert parsed["auto_pilot"] is True

    def test_hitl_sensitive(self):
        """Debe detectar --hitl-sensitive."""
        with patch("harness.run.sys.argv", ["run.py", "--hitl-sensitive", "tarea"]):
            from harness.run import _parse_args
            parsed = _parse_args()
        assert parsed["hitl_sensitive"] is True

    def test_comando(self):
        """Debe detectar comandos !command."""
        with patch("harness.run.sys.argv", ["run.py", "!db stats"]):
            from harness.run import _parse_args
            parsed = _parse_args()
        assert parsed["command"] == "!db stats"

    def test_flags_combinaos(self):
        """Debe combinar multiples flags correctamente."""
        with patch("harness.run.sys.argv", [
            "run.py", "--force-cloud", "--auto-pilot",
            "@builder: crea endpoint",
        ]):
            from harness.run import _parse_args
            parsed = _parse_args()
        assert parsed["force_cloud"] is True
        assert parsed["auto_pilot"] is True
        assert parsed["task"] == "@builder: crea endpoint"


# ===================================================================
# _show_usage
# ===================================================================

class TestShowUsage:
    """Tests para _show_usage — muestra ayuda."""

    def test_show_usage_llama_logger(self):
        """Debe llamar a logger.info varias veces."""
        with patch("harness.run.logger") as mock_log:
            from harness.run import _show_usage
            _show_usage()
        assert mock_log.info.call_count > 5


# ===================================================================
# _handle_gateway_mode
# ===================================================================

class TestHandleGatewayMode:
    """Tests para _handle_gateway_mode — modo gateway interactivo."""

    def test_gateway_activo(self):
        """Debe inicializar GatewayManager y procesar input."""
        mock_gm = MagicMock()
        mock_gm.list_active_gateways.return_value = ["cli"]
        mock_cli = MagicMock()
        mock_cli.is_active.return_value = True
        mock_gm.get_gateway.return_value = mock_cli

        with patch("harness.gateway.gateway.GatewayManager", return_value=mock_gm), \
             patch("harness.gateway.gateway.load_gateway_config",
                   return_value={"active_gateways": ["cli"]}), \
             patch("builtins.input", side_effect=["mensaje test", "exit"]):

            from harness.run import _handle_gateway_mode
            _handle_gateway_mode({"gateway": "cli"})

        assert mock_gm.send_all.call_count == 1

    def test_gateway_inactivo_sin_input(self):
        """Si CLI gateway no esta activa, no debe pedir input."""
        mock_gm = MagicMock()
        mock_cli = MagicMock()
        mock_cli.is_active.return_value = False
        mock_gm.get_gateway.return_value = mock_cli

        with patch("harness.gateway.gateway.GatewayManager", return_value=mock_gm), \
             patch("harness.gateway.gateway.load_gateway_config",
                   return_value={"active_gateways": []}):

            from harness.run import _handle_gateway_mode
            _handle_gateway_mode({"gateway": "telegram"})


# ===================================================================
# _handle_daemon_mode
# ===================================================================

class TestHandleDaemonMode:
    """Tests para _handle_daemon_mode — modo daemon."""

    def test_daemon_inicia_scheduler(self):
        """Debe crear LanceVectorStore y Scheduler, luego esperar Ctrl+C."""
        mock_sched = MagicMock()
        with patch("harness.run.LanceVectorStore"), \
             patch("harness.orchestrator.scheduler.Scheduler",
                   return_value=mock_sched), \
             patch("time.sleep", side_effect=KeyboardInterrupt):

            from harness.run import _handle_daemon_mode
            _handle_daemon_mode()

        mock_sched.run_scheduler.assert_called_once()
        mock_sched.stop.assert_called_once()


# ===================================================================
# _handle_command
# ===================================================================

class TestHandleCommand:
    """Tests para _handle_command — dispatch de !commands."""

    @pytest.fixture(autouse=True)
    def patch_store(self):
        """Parchea LanceVectorStore para todos los tests de handle_command."""
        with patch("harness.run.LanceVectorStore", return_value=MagicMock()):
            yield

    def test_evolve_mutate(self):
        """Debe llamar _handle_evolve_mutate para !evolve mutate."""
        with patch("harness.run._handle_evolve_mutate") as mock_fn:
            from harness.run import _handle_command
            _handle_command("!evolve mutate @builder \"mejora\"")
        mock_fn.assert_called_once()

    def test_schedule_add(self):
        """Debe llamar _handle_schedule_add para !schedule add."""
        with patch("harness.run._handle_schedule_add") as mock_fn:
            from harness.run import _handle_command
            _handle_command("!schedule add test --cron '0 * * * *' --task 'cmd'")
        mock_fn.assert_called_once()

    def test_schedule_list(self):
        """Debe llamar _handle_schedule_list para !schedule list."""
        with patch("harness.run._handle_schedule_list") as mock_fn:
            from harness.run import _handle_command
            _handle_command("!schedule list")
        mock_fn.assert_called_once()

    def test_db_migrate(self):
        """Debe llamar _handle_db_migrate para !db migrate."""
        with patch("harness.run._handle_db_migrate") as mock_fn:
            from harness.run import _handle_command
            _handle_command("!db migrate")
        mock_fn.assert_called_once()

    def test_db_list_imports(self):
        """Debe llamar _handle_db_list_imports para !db list-imports."""
        with patch("harness.run._handle_db_list_imports") as mock_fn:
            from harness.run import _handle_command
            _handle_command("!db list-imports")
        mock_fn.assert_called_once()

    def test_db_stats(self):
        """Debe llamar _handle_db_stats para !db stats."""
        with patch("harness.run._handle_db_stats") as mock_fn:
            from harness.run import _handle_command
            _handle_command("!db stats")
        mock_fn.assert_called_once()

    def test_db_rollback(self):
        """Debe llamar _handle_db_rollback para !db rollback."""
        with patch("harness.run._handle_db_rollback") as mock_fn:
            from harness.run import _handle_command
            _handle_command("!db rollback /path/backup")
        mock_fn.assert_called_once()

    def test_iteration_end(self):
        """Debe llamar _handle_iteration_end para !iteration end."""
        with patch("harness.run._handle_iteration_end") as mock_fn:
            from harness.run import _handle_command
            _handle_command("!iteration end")
        mock_fn.assert_called_once()

    def test_iteration_quick(self):
        """Debe llamar _handle_iteration_quick para !iteration quick."""
        with patch("harness.run._handle_iteration_quick") as mock_fn:
            from harness.run import _handle_command
            _handle_command("!iteration quick")
        mock_fn.assert_called_once()

    def test_iteration_auto(self):
        """Debe llamar _handle_iteration_auto para !iteration auto."""
        with patch("harness.run._handle_iteration_auto") as mock_fn:
            from harness.run import _handle_command
            _handle_command("!iteration auto")
        mock_fn.assert_called_once()

    def test_iteration_history(self):
        """Debe llamar _handle_iteration_history para !iteration history."""
        with patch("harness.run._handle_iteration_history") as mock_fn:
            from harness.run import _handle_command
            _handle_command("!iteration history")
        mock_fn.assert_called_once()

    def test_iteration_diff(self):
        """Debe llamar _handle_iteration_diff para !iteration diff."""
        with patch("harness.run._handle_iteration_diff") as mock_fn:
            from harness.run import _handle_command
            _handle_command("!iteration diff --last")
        mock_fn.assert_called_once()

    def test_iteration_report(self):
        """Debe llamar _handle_iteration_report para !iteration report."""
        with patch("harness.run._handle_iteration_report") as mock_fn:
            from harness.run import _handle_command
            _handle_command("!iteration report")
        mock_fn.assert_called_once()

    def test_hooks_install(self):
        """Debe llamar _handle_hooks_install para !hooks install."""
        with patch("harness.run._handle_hooks_install") as mock_fn:
            from harness.run import _handle_command
            _handle_command("!hooks install")
        mock_fn.assert_called_once()

    def test_hooks_uninstall(self):
        """Debe llamar _handle_hooks_uninstall para !hooks uninstall."""
        with patch("harness.run._handle_hooks_uninstall") as mock_fn:
            from harness.run import _handle_command
            _handle_command("!hooks uninstall")
        mock_fn.assert_called_once()

    def test_hooks_status(self):
        """Debe llamar _handle_hooks_status para !hooks status."""
        with patch("harness.run._handle_hooks_status") as mock_fn:
            from harness.run import _handle_command
            _handle_command("!hooks status")
        mock_fn.assert_called_once()

    def test_rag_ingest(self):
        """Debe llamar _handle_rag_ingest para !rag ingest."""
        with patch("harness.run._handle_rag_ingest") as mock_fn:
            from harness.run import _handle_command
            _handle_command("!rag ingest")
        mock_fn.assert_called_once()

    def test_rag_stats(self):
        """Debe llamar _handle_rag_stats para !rag stats."""
        with patch("harness.run._handle_rag_stats") as mock_fn:
            from harness.run import _handle_command
            _handle_command("!rag stats")
        mock_fn.assert_called_once()

    def test_agent_evolve(self):
        """Debe ejecutar run_agent_evolution para !agent evolve."""
        with patch("harness.evolve_loop.agent_builder.run_agent_evolution",
                   return_value={"built": 2, "pruned": 1, "builder_stats": {}}):
            from harness.run import _handle_command
            _handle_command("!agent evolve")

    def test_agent_evolve_dry_run(self):
        """Debe pasar dry_run=True si --dry-run esta presente."""
        with patch("harness.evolve_loop.agent_builder.run_agent_evolution",
                   return_value={"built": 0, "pruned": 0, "builder_stats": {}}) as mock_fn:
            from harness.run import _handle_command
            _handle_command("!agent evolve --dry-run")
        mock_fn.assert_called_once_with(dry_run=True)

    def test_agent_build(self):
        """Debe ejecutar AgentBuilder para !agent build."""
        mock_builder = MagicMock()
        mock_builder.build_agents_from_cognition.return_value = ["agent1"]
        with patch("harness.evolve_loop.agent_builder.AgentBuilder", return_value=mock_builder):
            from harness.run import _handle_command
            _handle_command("!agent build")

    def test_agent_prune(self):
        """Debe ejecutar AgentPruner para !agent prune."""
        mock_pruner = MagicMock()
        mock_pruner.prune_underperforming.return_value = ["old_agent"]
        with patch("harness.evolve_loop.agent_builder.AgentPruner", return_value=mock_pruner):
            from harness.run import _handle_command
            _handle_command("!agent prune")
        mock_pruner.prune_underperforming.assert_called_once_with(dry_run=False)

    def test_hermes(self):
        """Debe llamar _handle_hermes para !hermes."""
        with patch("harness.run._handle_hermes") as mock_fn:
            from harness.run import _handle_command
            _handle_command("!hermes sync")
        mock_fn.assert_called_once_with("!hermes sync")

    def test_comando_desconocido(self):
        """Debe loggear warning para comandos desconocidos."""
        with patch("harness.run.logger") as mock_log:
            from harness.run import _handle_command
            _handle_command("!comando-inexistente")
        mock_log.info.assert_called_with(
            "[Harness] Comando desconocido: %s", "!comando-inexistente"
        )


# ===================================================================
# _resolve_hitl_mode
# ===================================================================

class TestResolveHitlMode:
    """Tests para _resolve_hitl_mode — determina modo HITL."""

    def test_auto_pilot(self):
        """Debe retornar 'auto_pilot' si auto_pilot=True."""
        from harness.run import _resolve_hitl_mode
        assert _resolve_hitl_mode({"auto_pilot": True}) == "auto_pilot"

    def test_hitl_sensitive(self):
        """Debe retornar 'hitl_sensitive' si hitl_sensitive=True."""
        from harness.run import _resolve_hitl_mode
        assert _resolve_hitl_mode({"hitl_sensitive": True}) == "hitl_sensitive"

    def test_default_hitl(self):
        """Debe retornar 'hitl' si no hay flags especiales."""
        from harness.run import _resolve_hitl_mode
        assert _resolve_hitl_mode({}) == "hitl"

    def test_auto_pilot_priority(self):
        """Auto-pilot tiene prioridad sobre hitl-sensitive."""
        from harness.run import _resolve_hitl_mode
        result = _resolve_hitl_mode({"auto_pilot": True, "hitl_sensitive": True})
        assert result == "auto_pilot"


# ===================================================================
# _check_lancedb_or_exit
# ===================================================================

class TestCheckLancedbOrExit:
    """Tests para _check_lancedb_or_exit — verifica disponibilidad de LanceDB."""

    def test_has_lancedb_ok(self):
        """No debe hacer sys.exit si HAS_LANCEDB es True."""
        with patch("harness.run.HAS_LANCEDB", True), \
             patch("harness.run.sys.exit") as mock_exit:
            from harness.run import _check_lancedb_or_exit
            _check_lancedb_or_exit()
        mock_exit.assert_not_called()

    def test_no_lancedb_exit(self):
        """Debe hacer sys.exit(1) si HAS_LANCEDB es False."""
        with patch("harness.run.HAS_LANCEDB", False), \
             patch("harness.run.sys.exit") as mock_exit:
            from harness.run import _check_lancedb_or_exit
            _check_lancedb_or_exit()
        mock_exit.assert_called_once_with(1)


# ===================================================================
# main()
# ===================================================================

class TestMain:
    """Tests para main() — entry point completo."""

    @pytest.fixture(autouse=True)
    def patch_main_deps(self):
        """Parchea dependencias pesadas de main()."""
        with patch("harness.run.check_first_run"), \
             patch("harness.run.LanceVectorStore"), \
             patch("harness.orchestrator.task_orchestrator.TaskOrchestrator"), \
             patch("harness.run.HITLGuard"), \
             patch("harness.run.os.path.exists", return_value=True):
            yield

    def test_main_help(self):
        """main() con --help debe mostrar ayuda y retornar."""
        with patch("harness.run._parse_args",
                   return_value={"help": True, "daemon": False, "watch": False,
                                 "gateway": None, "force_cloud": False,
                                 "auto_pilot": False, "hitl_sensitive": False,
                                 "task": None, "command": None}), \
             patch("harness.run._show_usage") as mock_usage, \
             patch("harness.run.sys.exit") as mock_exit:
            from harness.run import main
            main()
        mock_usage.assert_called_once()
        mock_exit.assert_not_called()

    def test_main_gateway(self):
        """main() con --gateway debe delegar a _handle_gateway_mode."""
        with patch("harness.run._parse_args",
                   return_value={"help": False, "daemon": False, "watch": False,
                                 "gateway": "cli", "force_cloud": False,
                                 "auto_pilot": False, "hitl_sensitive": False,
                                 "task": None, "command": None}), \
             patch("harness.run._handle_gateway_mode") as mock_fn:
            from harness.run import main
            main()
        mock_fn.assert_called_once()

    def test_main_daemon(self):
        """main() con --daemon debe delegar a _handle_daemon_mode."""
        with patch("harness.run._parse_args",
                   return_value={"help": False, "daemon": True, "watch": False,
                                 "gateway": None, "force_cloud": False,
                                 "auto_pilot": False, "hitl_sensitive": False,
                                 "task": None, "command": None}), \
             patch("harness.run._handle_daemon_mode") as mock_fn:
            from harness.run import main
            main()
        mock_fn.assert_called_once()

    def test_main_watch(self):
        """main() con --watch debe delegar a _handle_watch_mode."""
        with patch("harness.run._parse_args",
                   return_value={"help": False, "daemon": False, "watch": True,
                                 "gateway": None, "force_cloud": False,
                                 "auto_pilot": False, "hitl_sensitive": False,
                                 "task": None, "command": None}), \
             patch("harness.run._handle_watch_mode") as mock_fn:
            from harness.run import main
            main()
        mock_fn.assert_called_once()

    def test_main_command(self):
        """main() con !command debe delegar a _handle_command."""
        with patch("harness.run._parse_args",
                   return_value={"help": False, "daemon": False, "watch": False,
                                 "gateway": None, "force_cloud": False,
                                 "auto_pilot": False, "hitl_sensitive": False,
                                 "task": None, "command": "!db stats"}), \
             patch("harness.run._handle_command") as mock_fn:
            from harness.run import main
            main()
        mock_fn.assert_called_once_with("!db stats")

    def test_main_sin_tarea_exit(self):
        """main() sin tarea debe mostrar ayuda y hacer sys.exit(1)."""
        with patch("harness.run._parse_args",
                   return_value={"help": False, "daemon": False, "watch": False,
                                 "gateway": None, "force_cloud": False,
                                 "auto_pilot": False, "hitl_sensitive": False,
                                 "task": None, "command": None}), \
             patch("harness.run._show_usage") as mock_usage:
            from harness.run import main
            with pytest.raises(SystemExit):
                main()
        mock_usage.assert_called_once()

    def test_main_task_flow(self, mock_store, mock_orch_result):
        """main() con tarea debe ejecutar el flujo completo de orquestacion."""
        mock_orch = MagicMock()
        mock_orch.process_message.return_value = mock_orch_result

        with patch("harness.run._parse_args",
                   return_value={"help": False, "daemon": False, "watch": False,
                                 "gateway": None, "force_cloud": False,
                                 "auto_pilot": False, "hitl_sensitive": False,
                                 "task": "@builder: crear API", "command": None}), \
             patch("harness.orchestrator.task_orchestrator.TaskOrchestrator",
                   return_value=mock_orch), \
             patch("harness.run.LanceVectorStore", return_value=mock_store), \
             patch("harness.run._dispatch_task", return_value="builder"), \
             patch("harness.run._apply_model_routing", return_value="local"), \
             patch("harness.run._check_hitl", return_value=True), \
             patch("harness.run._ensure_rag_context"), \
             patch("harness.run._run_guardrails"), \
             patch("harness.run._create_task_and_lesson"), \
             patch("harness.run._display_final_output"), \
             patch("harness.run._start_sandbox_if_needed"), \
             patch("harness.run.HITLGuard"):

            from harness.run import main
            main()

        mock_orch.process_message.assert_called_once_with(
            message="@builder: crear API", force_agent=None
        )

    def test_main_hitl_rechazado(self):
        """main() con HITL bloqueado debe hacer sys.exit(1)."""
        mock_store = MagicMock()
        mock_orch = MagicMock()
        mock_orch_result = MagicMock()
        mock_orch_result.target_agent = "builder"
        mock_orch.process_message.return_value = mock_orch_result

        with patch("harness.run._parse_args",
                   return_value={"help": False, "daemon": False, "watch": False,
                                 "gateway": None, "force_cloud": False,
                                 "auto_pilot": False, "hitl_sensitive": False,
                                 "task": "tarea sensible", "command": None}), \
             patch("harness.orchestrator.task_orchestrator.TaskOrchestrator",
                   return_value=mock_orch), \
             patch("harness.run.LanceVectorStore", return_value=mock_store), \
             patch("harness.run._dispatch_task", return_value="builder"), \
             patch("harness.run._apply_model_routing", return_value="cloud"), \
             patch("harness.run._check_hitl", return_value=False):

            from harness.run import main
            with pytest.raises(SystemExit):
                main()


# ===================================================================
# Funciones auxiliares
# ===================================================================

class TestDisplayPlan:
    """Tests para _display_plan — muestra plan de ejecucion."""

    def test_no_display_if_not_new_plan(self):
        """No debe mostrar nada si orch_result.is_new_plan es False."""
        mock_orch = MagicMock()
        mock_orch.is_new_plan = False
        with patch("harness.run._safe_print") as mock_print:
            from harness.run import _display_plan
            _display_plan(mock_orch, "tarea")
        mock_print.assert_not_called()

    def test_display_with_levels(self):
        """Debe mostrar niveles del plan."""
        mock_s = MagicMock()
        mock_s.agent = "builder"
        mock_s.description = "crear endpoint"
        mock_s.dependencies = []

        mock_orch = MagicMock()
        mock_orch.is_new_plan = True
        mock_orch.plan.get_levels.return_value = [[mock_s]]
        mock_orch.current_level = None
        mock_orch.previous_results = []

        with patch("harness.run._safe_print"):
            from harness.run import _display_plan
            _display_plan(mock_orch, "tarea")

    def test_display_with_current_level(self):
        """Debe mostrar el nivel actual si existe."""
        mock_orch = MagicMock()
        mock_orch.is_new_plan = True
        mock_orch.plan.get_levels.return_value = []
        mock_orch.current_level = [{"agent": "builder", "description": "haciendo"}]
        mock_orch.previous_results = []

        with patch("harness.run._safe_print"):
            from harness.run import _display_plan
            _display_plan(mock_orch, "tarea")

    def test_display_with_previous_results(self):
        """Debe mostrar resultados previos si existen."""
        mock_orch = MagicMock()
        mock_orch.is_new_plan = True
        mock_orch.plan.get_levels.return_value = []
        mock_orch.current_level = None
        mock_orch.previous_results = [{"agent": "builder", "description": "completado"}]

        with patch("harness.run._safe_print"):
            from harness.run import _display_plan
            _display_plan(mock_orch, "tarea")


class TestDispatchTask:
    """Tests para _dispatch_task — despacha tarea al agente."""

    def test_dispatch_async(self, mock_store):
        """Debe ejecutar dispatch_async a traves de AgentDispatcher."""
        mock_orch = MagicMock()
        mock_orch.target_agent = "builder"
        mock_orch.session_id = "s1"
        mock_orch.session_status = "ok"
        mock_orch.current_level = []
        mock_orch.previous_results = []
        mock_orch.communication_log = []
        mock_orch.is_complete = False

        mock_dispatcher = MagicMock()

        async def fake_dispatch(target, task, plan_context=None):
            return {"used_skill": "builder", "rag_context": {}, "execution_plan": None}

        mock_dispatcher.dispatch_async = fake_dispatch

        with patch("harness.orchestrator.agent_dispatcher.AgentDispatcher",
                   return_value=mock_dispatcher):
            from harness.run import _dispatch_task
            result = _dispatch_task(mock_store, mock_orch, "mi tarea")
        assert result == "builder"


class TestEnsureRagContext:
    """Tests para _ensure_rag_context — ensambla contexto RAG."""

    def test_con_chunks(self, mock_store):
        """Debe loggear cuando hay chunks relevantes."""
        mock_ctx = MagicMock()
        mock_ctx.relevant_docs = [{"id": "doc1"}]
        mock_ctx.metadata = {"total_tokens_used": 500}

        with patch("harness.run.ContextAssembler") as mock_asm_cls:
            mock_asm = MagicMock()
            mock_asm.assemble.return_value = mock_ctx
            mock_asm_cls.return_value = mock_asm

            from harness.run import _ensure_rag_context
            result = _ensure_rag_context(mock_store, "mi tarea", "builder")

        assert result.relevant_docs == [{"id": "doc1"}]

    def test_sin_chunks_auto_ingesta(self, mock_store):
        """Debe auto-ingestar si no hay chunks."""
        mock_ctx_empty = MagicMock()
        mock_ctx_empty.relevant_docs = []
        mock_ctx_empty.metadata = {}
        mock_ctx_after = MagicMock()
        mock_ctx_after.relevant_docs = [{"id": "doc2"}]
        mock_ctx_after.metadata = {"total_tokens_used": 300}

        with patch("harness.run.ContextAssembler") as mock_asm_cls, \
             patch("harness.run.DocumentChunker"), \
             patch("harness.run.ingest_directory",
                   return_value={"files_processed": 10, "chunks_inserted": 50}):

            mock_asm = MagicMock()
            mock_asm.assemble.side_effect = [mock_ctx_empty, mock_ctx_after]
            mock_asm_cls.return_value = mock_asm

            from harness.run import _ensure_rag_context
            result = _ensure_rag_context(mock_store, "mi tarea", "builder")

        assert result.relevant_docs == [{"id": "doc2"}]

    def test_ingesta_sin_chunks(self, mock_store):
        """Si incluso tras ingesta no hay chunks, debe retornar ctx vacio."""
        mock_ctx_empty = MagicMock()
        mock_ctx_empty.relevant_docs = []
        mock_ctx_empty.metadata = {}

        with patch("harness.run.ContextAssembler") as mock_asm_cls, \
             patch("harness.run.DocumentChunker"), \
             patch("harness.run.ingest_directory",
                   return_value={"files_processed": 5, "chunks_inserted": 0}):

            mock_asm = MagicMock()
            mock_asm.assemble.return_value = mock_ctx_empty
            mock_asm_cls.return_value = mock_asm

            from harness.run import _ensure_rag_context
            result = _ensure_rag_context(mock_store, "mi tarea", "builder")

        assert result.relevant_docs == []


class TestCreateTaskAndLesson:
    """Tests para _create_task_and_lesson — crea tarea y leccion de cognicion."""

    def test_creates_task_and_lesson(self, mock_store, mock_orch_result):
        """Debe crear una tarea en TaskManager y registrar una leccion."""
        mock_task = MagicMock()
        mock_task.id = "task-001"
        mock_task.status = "pending"

        mock_tm = MagicMock()
        mock_tm.create_task.return_value = mock_task

        mock_ctx = MagicMock()
        mock_ctx.relevant_docs = [{"id": "d1"}]
        mock_ctx.metadata = {"total_tokens_used": 200}

        with patch("harness.run.TaskManager", return_value=mock_tm), \
             patch("harness.run.CognitionSync") as mock_cog_cls:

            mock_cog = MagicMock()
            mock_cog_cls.return_value = mock_cog

            from harness.run import _create_task_and_lesson
            result = _create_task_and_lesson(
                mock_store, "@builder: crear API", "builder",
                "local", mock_orch_result, mock_ctx,
            )

        assert result == mock_task
        mock_tm.create_task.assert_called_once()
        mock_cog.add_lesson.assert_called_once()

    def test_cognition_error_no_raise(self, mock_store, mock_orch_result):
        """Si CognitionSync.add_lesson falla, debe loggear y no propagar."""
        mock_tm = MagicMock()
        mock_tm.create_task.return_value = MagicMock()

        mock_ctx = MagicMock()
        mock_ctx.relevant_docs = []
        mock_ctx.metadata = {}

        with patch("harness.run.TaskManager", return_value=mock_tm), \
             patch("harness.run.CognitionSync") as mock_cog_cls:

            mock_cog = MagicMock()
            mock_cog.add_lesson.side_effect = Exception("DB error")
            mock_cog_cls.return_value = mock_cog

            from harness.run import _create_task_and_lesson
            result = _create_task_and_lesson(
                mock_store, "tarea", "builder", "cloud", mock_orch_result, mock_ctx,
            )

        assert result is not None


class TestDisplayFinalOutput:
    """Tests para _display_final_output — muestra resultado final."""

    def test_plan_completo(self):
        """Debe mostrar mensaje de plan completo si is_complete=True."""
        mock_orch = MagicMock()
        mock_orch.is_complete = True
        mock_orch.current_level = []

        with patch("harness.run._safe_print") as mock_print:
            from harness.run import _display_final_output
            _display_final_output(mock_orch, "builder", "local")
        assert any("PLAN COMPLETO" in str(c) for c in mock_print.call_args_list)

    def test_pendientes(self):
        """Debe mostrar subtareas pendientes si las hay."""
        mock_subtask = MagicMock()
        mock_subtask.completed = False
        mock_orch = MagicMock()
        mock_orch.is_complete = False
        mock_orch.plan.subtasks = [mock_subtask]
        mock_orch.current_level = []

        with patch("harness.run._safe_print"):
            from harness.run import _display_final_output
            _display_final_output(mock_orch, "builder", "cloud")

    def test_current_level(self):
        """Debe mostrar el nivel actual si existe."""
        mock_orch = MagicMock()
        mock_orch.is_complete = False
        mock_orch.plan.subtasks = []
        mock_orch.current_level = [{"agent": "builder", "description": "test"}]

        with patch("harness.run._safe_print"):
            from harness.run import _display_final_output
            _display_final_output(mock_orch, "builder", "cloud")


class TestStartSandboxIfNeeded:
    """Tests para _start_sandbox_if_needed — inicia SandboxLoop."""

    def test_no_builder_agent(self, mock_store, mock_orch_result):
        """No debe iniciar SandboxLoop si el agente no es builder."""
        with patch("harness.orchestrator.sandbox_loop.SandboxLoop") as mock_sb, \
             patch("harness.orchestrator.agent_bus.AgentBus"):
            from harness.run import _start_sandbox_if_needed
            _start_sandbox_if_needed(
                "scientist", MagicMock(), mock_store,
                "task", mock_orch_result, "local",
            )
        mock_sb.assert_not_called()

    def test_no_new_task(self, mock_store, mock_orch_result):
        """No debe iniciar SandboxLoop si no hay new_task."""
        with patch("harness.orchestrator.sandbox_loop.SandboxLoop") as mock_sb:
            from harness.run import _start_sandbox_if_needed
            _start_sandbox_if_needed(
                "builder", None, mock_store,
                "task", mock_orch_result, "local",
            )
        mock_sb.assert_not_called()

    def test_starts_sandbox(self, mock_store, mock_orch_result):
        """Debe iniciar SandboxLoop y enviar mensaje al bus."""
        mock_task = MagicMock()
        mock_task.id = "task-42"

        with patch("harness.orchestrator.sandbox_loop.SandboxLoop") as mock_sb, \
             patch("harness.orchestrator.agent_bus.AgentBus") as mock_bus_cls:

            mock_bus = MagicMock()
            mock_bus_cls.return_value = mock_bus

            from harness.run import _start_sandbox_if_needed
            _start_sandbox_if_needed(
                "builder", mock_task, mock_store,
                "tarea importante", mock_orch_result, "cloud",
            )

        mock_sb.assert_called_once_with(vector_store=mock_store)
        mock_bus.post_message.assert_called_once()
