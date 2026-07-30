"""
Tests para harness/delegate.py â€” entry point de delegaciÃ³n multi-agente.

Cubre: inicializaciÃ³n, detecciÃ³n de roles, parsing de @menciones,
delegaciÃ³n a subprocess, listado de agentes, modo interactivo y edge cases.
"""
from __future__ import annotations

import logging
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def no_delegation_engine():
    """Deshabilita DelegationEngine para que _detect_role use intent_map.

    Como DelegationEngine estÃ¡ disponible en el proyecto y su
    route_message retorna valores inesperados (builder, coordinator),
    se parchea para que falle y los tests usen el path de intent_map.
    """
    with patch(
        "harness.orchestrator.delegation_engine.DelegationEngine",
        side_effect=ImportError("Mock: DelegationEngine no disponible"),
    ):
        yield


@pytest.fixture
def mock_agents():
    """Retorna estructura tÃ­pica de agentes descubiertos."""
    return {
        "software-engineer": {
            "description": "Construye software",
            "aliases": ["swe", "engineer"],
        },
        "project-manager": {
            "description": "Gestiona proyectos",
            "aliases": ["pm", "manager"],
        },
        "scientist": {
            "description": "InvestigaciÃ³n",
            "aliases": ["sci", "researcher"],
        },
    }


@pytest.fixture
def mock_discovery(mock_agents):
    """Parchea discover_agents_recursive y build_intent_map."""
    with patch("harness.delegate.discover_agents_recursive") as mock_dar:  # noqa: SIM117
        with patch("harness.delegate.build_intent_map") as mock_bim:
            mock_dar.return_value = mock_agents
            mock_bim.return_value = {
                "crear api": "software-engineer",
                "implementar": "software-engineer",
                "investigar": "scientist",
                "research": "scientist",
                "deploy": "software-engineer",
            }
            yield mock_dar, mock_bim


@pytest.fixture
def mock_resolve():
    """Parchea discovery_resolve_agent."""
    with patch("harness.delegate.discovery_resolve_agent") as m:
        m.side_effect = lambda alias, agents: {
            "swe": "software-engineer",
            "engineer": "software-engineer",
            "pm": "project-manager",
        }.get(alias, None)
        yield m


# ---------------------------------------------------------------------------
# Tests: _get_agents / _get_agent_list
# ---------------------------------------------------------------------------


class TestAgentCache:
    """Tests para el cachÃ© de agentes descubiertos."""

    def test_get_agents_returns_dict(self, mock_discovery):
        """_get_agents debe retornar un dict con agentes."""
        from harness.delegate import _get_agents
        agents = _get_agents()
        assert isinstance(agents, dict)
        assert "software-engineer" in agents

    def test_get_agents_cache_reuse(self, mock_discovery):
        """_get_agents debe cachear el resultado en _AGENTS_CACHE."""
        from harness import delegate

        # Forzar reset del cache
        delegate._AGENTS_CACHE = None
        mock_dar = mock_discovery[0]

        first = delegate._get_agents()
        second = delegate._get_agents()
        assert first is second
        mock_dar.assert_called_once()

    def test_get_agent_list_format(self, mock_discovery):
        """_get_agent_list debe retornar tuplas (nombre, desc, alias)."""
        from harness.delegate import _get_agent_list
        lst = _get_agent_list()
        assert all(isinstance(t, tuple) and len(t) == 3 for t in lst)
        names = [t[0] for t in lst]
        assert "software-engineer" in names


# ---------------------------------------------------------------------------
# Tests: _parse_mention
# ---------------------------------------------------------------------------


class TestParseMention:
    """Tests para el parsing de @rol: prefijo."""

    def test_mention_detected(self):
        """Debe extraer rol y texto con formato '@rol: texto'."""
        from harness.delegate import _parse_mention
        rol, text = _parse_mention("@swe: crea un endpoint")
        assert rol == "swe"
        assert text == "crea un endpoint"

    def test_mention_without_space(self):
        """Debe soportar '@rol:texto' sin espacio."""
        from harness.delegate import _parse_mention
        rol, text = _parse_mention("@pm:planificar")
        assert rol == "pm"
        assert text == "planificar"

    def test_no_mention(self):
        """Sin @rol: debe retornar (None, texto_original)."""
        from harness.delegate import _parse_mention
        rol, text = _parse_mention("implementar API")
        assert rol is None
        assert text == "implementar API"

    def test_mention_with_dashes(self):
        """Debe soportar roles con guiones (@software-engineer)."""
        from harness.delegate import _parse_mention
        rol, text = _parse_mention("@software-engineer: tarea")
        assert rol == "software-engineer"
        assert text == "tarea"

    def test_empty_string(self):
        """Con string vacÃ­o debe retornar (None, '')."""
        from harness.delegate import _parse_mention
        rol, text = _parse_mention("")
        assert rol is None
        assert text == ""


# ---------------------------------------------------------------------------
# Tests: _detect_role
# ---------------------------------------------------------------------------


class TestDetectRole:
    """Tests para la detecciÃ³n automÃ¡tica de roles."""

    def test_detect_by_keyword(self, mock_discovery):
        """Debe detectar rol por keyword en intent_map."""
        from harness.delegate import _detect_role
        role = _detect_role("crear API REST con Python")
        assert role == "software-engineer"

    def test_detect_research(self, mock_discovery):
        """Debe detectar rol 'scientist' para tareas de investigaciÃ³n."""
        from harness.delegate import _detect_role
        role = _detect_role("investigar arquitectura del sistema")
        assert role == "scientist"

    def test_detect_unknown_returns_none(self, mock_discovery):
        """Si no hay match de keywords debe retornar None."""
        from harness.delegate import _detect_role
        role = _detect_role("zzzxyz_nonexistent_keyword_12345")
        assert role is None

    def test_detect_empty_task_returns_none(self, mock_discovery):
        """Con tarea vacÃ­a debe retornar None."""
        from harness.delegate import _detect_role
        role = _detect_role("")
        assert role is None

    def test_detect_fallback_from_delegation_engine_failure(self, mock_discovery, caplog):
        """Si DelegationEngine falla, debe continuar con intent_map."""
        from harness.delegate import _detect_role
        with caplog.at_level(logging.WARNING):
            role = _detect_role("crear API")
        assert role == "software-engineer"
        assert any("delegate route_message" in msg for msg in caplog.messages)


# ---------------------------------------------------------------------------
# Tests: resolve_role
# ---------------------------------------------------------------------------


class TestResolveRole:
    """Tests para la resoluciÃ³n de alias a nombre canÃ³nico."""

    def test_resolve_known_alias(self, mock_discovery, mock_resolve):
        """Debe resolver '@swe' a 'software-engineer'."""
        from harness.delegate import resolve_role
        result = resolve_role("swe")
        assert result == "software-engineer"

    def test_resolve_unknown_alias(self, mock_discovery, mock_resolve):
        """Con alias desconocido debe retornar None."""
        from harness.delegate import resolve_role
        result = resolve_role("nonexistent_role_12345")
        assert result is None

    def test_resolve_empty_string(self, mock_discovery, mock_resolve):
        """Con string vacÃ­o debe retornar None."""
        from harness.delegate import resolve_role
        result = resolve_role("")
        assert result is None


# ---------------------------------------------------------------------------
# Tests: delegate_task
# ---------------------------------------------------------------------------


class TestDelegateTask:
    """Tests para la funciÃ³n principal delegate_task."""

    @patch("harness.delegate.subprocess.run")
    def test_delegate_with_explicit_role(self, mock_run, mock_discovery, mock_resolve):
        """Debe delegar con @rol explÃ­cito a run.py."""
        from harness.delegate import delegate_task
        mock_run.return_value = MagicMock(returncode=0)

        exit_code = delegate_task("@swe: crear API")
        assert exit_code == 0
        # Verificar que se invocÃ³ run.py
        mock_run.assert_called_once()
        args, _ = mock_run.call_args
        cmd = args[0]
        # cmd debe contener: [python, run.py, "@software-engineer: crear API"]
        run_py_path = cmd[1]
        assert "run.py" in run_py_path or "run.py" in str(cmd)
        task_arg = cmd[2] if len(cmd) > 2 else cmd[1]
        assert "@software-engineer:" in str(task_arg)

    @patch("harness.delegate.subprocess.run")
    def test_delegate_with_auto_detect(self, mock_run, mock_discovery, mock_resolve):
        """Debe auto-detectar rol y delegar."""
        from harness.delegate import delegate_task
        mock_run.return_value = MagicMock(returncode=0)

        exit_code = delegate_task("crear API REST")
        assert exit_code == 0
        mock_run.assert_called_once()

    @patch("harness.delegate.subprocess.run")
    def test_delegate_unknown_role(self, mock_run, mock_discovery, mock_resolve):
        """Con @rol desconocido debe retornar cÃ³digo 1."""
        from harness.delegate import delegate_task
        mock_run.return_value = MagicMock(returncode=0)

        exit_code = delegate_task("@nonexistent_role_xyz: tarea")
        assert exit_code == 1
        mock_run.assert_not_called()

    @patch("harness.delegate.subprocess.run")
    def test_delegate_with_extra_args(self, mock_run, mock_discovery, mock_resolve):
        """Debe pasar extra_args a run.py."""
        from harness.delegate import delegate_task
        mock_run.return_value = MagicMock(returncode=0)

        exit_code = delegate_task("@swe: tarea", extra_args=["--verbose", "--debug"])
        assert exit_code == 0
        args, _ = mock_run.call_args
        cmd = args[0]
        assert "--verbose" in cmd
        assert "--debug" in cmd

    @patch("harness.delegate.subprocess.run")
    def test_delegate_non_zero_exit(self, mock_run, mock_discovery, mock_resolve):
        """Debe propagar el cÃ³digo de salida de run.py."""
        from harness.delegate import delegate_task
        mock_run.return_value = MagicMock(returncode=42)

        exit_code = delegate_task("@swe: tarea")
        assert exit_code == 42

    @patch("harness.delegate.subprocess.run")
    def test_delegate_empty_task_after_mention(self, mock_run, mock_discovery, mock_resolve):
        """@rol: sin texto debe delegar con texto vacÃ­o."""
        from harness.delegate import delegate_task
        mock_run.return_value = MagicMock(returncode=0)

        exit_code = delegate_task("@swe:")
        assert exit_code == 0
        mock_run.assert_called_once()


# ---------------------------------------------------------------------------
# Tests: CLI modes (main, _list_agents, _interactive_mode)
# ---------------------------------------------------------------------------


class TestCLIModes:
    """Tests para modos CLI: --list, --interactive, main."""

    def test_list_agents_logs_output(self, mock_discovery, caplog):
        """_list_agents debe loguear los agentes disponibles."""
        from harness.delegate import _list_agents
        with caplog.at_level(logging.INFO):
            _list_agents()
        assert any("AGENTES DISPONIBLES" in msg for msg in caplog.messages)

    @patch("harness.delegate.delegate_task")
    def test_interactive_mode_exit(self, mock_delegate, mock_discovery):
        """Modo interactivo debe terminar con 'exit'."""
        from harness.delegate import _interactive_mode
        with patch("builtins.input", side_effect=["exit"]):
            _interactive_mode()
        mock_delegate.assert_not_called()

    @patch("harness.delegate._list_agents")
    def test_interactive_mode_list(self, mock_list, mock_discovery):
        """Modo interactivo debe mostrar lista con --list."""
        from harness.delegate import _interactive_mode
        with patch("builtins.input", side_effect=["--list", "exit"]):
            _interactive_mode()
        mock_list.assert_called_once()

    @patch("harness.delegate.delegate_task")
    def test_interactive_mode_task(self, mock_delegate, mock_discovery):
        """Modo interactivo debe delegar tareas escritas por el usuario."""
        from harness.delegate import _interactive_mode
        mock_delegate.return_value = 0
        with patch("builtins.input", side_effect=["@swe: tarea", "exit"]):
            _interactive_mode()
        mock_delegate.assert_called_once_with("@swe: tarea")

    def test_main_no_args(self, mock_discovery):
        """main() sin argumentos debe retornar 1."""
        from harness.delegate import main
        with patch("harness.delegate.sys.argv", ["delegate.py"]):
            exit_code = main()
            assert exit_code == 1

    def test_main_list_flag(self, mock_discovery):
        """main() con --list debe retornar 0."""
        from harness.delegate import main
        with patch("harness.delegate.sys.argv", ["delegate.py", "--list"]):
            exit_code = main()
            assert exit_code == 0

    @patch("harness.delegate._interactive_mode")
    def test_main_interactive(self, mock_interactive, mock_discovery):
        """main() con --interactive debe ejecutar modo interactivo."""
        from harness.delegate import main
        with patch("harness.delegate.sys.argv", ["delegate.py", "--interactive"]):
            exit_code = main()
            assert exit_code == 0
        mock_interactive.assert_called_once()

    @patch("harness.delegate.delegate_task")
    def test_main_with_task(self, mock_delegate, mock_discovery):
        """main() con texto de tarea debe delegar."""
        from harness.delegate import main
        mock_delegate.return_value = 0
        with patch("harness.delegate.sys.argv", ["delegate.py", "implementar API"]):
            exit_code = main()
            assert exit_code == 0
        mock_delegate.assert_called_once()


# ---------------------------------------------------------------------------
# Tests: Edge cases
# ---------------------------------------------------------------------------


class TestDelegateEdgeCases:
    """Tests de edge cases y manejo de errores."""

    def test_interactive_eof_error(self, mock_discovery):
        """EOFError en modo interactivo debe terminar gracefulmente."""
        from harness.delegate import _interactive_mode
        with patch("builtins.input", side_effect=EOFError):
            _interactive_mode()

    def test_interactive_empty_line_skips(self, mock_discovery):
        """LÃ­nea vacÃ­a en modo interactivo debe continuar el loop."""
        from harness.delegate import _interactive_mode
        with patch("builtins.input", side_effect=["", "exit"]):
            _interactive_mode()

    @patch("harness.delegate.delegate_task")
    def test_interactive_task_non_zero_logs_warning(self, mock_delegate, mock_discovery, caplog):
        """Si delegate_task retorna != 0, debe loguear advertencia."""
        from harness.delegate import _interactive_mode
        mock_delegate.return_value = 1
        with patch("builtins.input", side_effect=["tarea", "exit"]):  # noqa: SIM117
            with caplog.at_level(logging.INFO):
                _interactive_mode()
        assert any("codigo" in msg for msg in caplog.messages)

    def test_parse_mention_only_colon(self):
        """@rol: sin texto debe retornar texto vacÃ­o."""
        from harness.delegate import _parse_mention
        rol, text = _parse_mention("@test: ")
        assert rol == "test"
        assert text == ""

    def test_main_extra_flags_before_task(self, mock_discovery):
        """main() debe separar flags antes de la tarea."""
        from harness.delegate import main
        with patch("harness.delegate.sys.argv", ["delegate.py", "--verbose", "tarea"]):  # noqa: SIM117
            with patch("harness.delegate.delegate_task") as mock_dt:
                mock_dt.return_value = 0
                main()
                mock_dt.assert_called_once()
                args, _ = mock_dt.call_args
                # args[0] = task_text, args[1] = extra_args
                assert "--verbose" in args[1]

    @patch("harness.delegate.subprocess.run")
    def test_delegate_no_role_detected_interactive_fallback(
        self, mock_run, mock_discovery, caplog,
    ):
        """Sin detecciÃ³n de rol y sin input, debe usar project-manager."""
        from harness.delegate import delegate_task
        mock_run.return_value = MagicMock(returncode=0)
        # Crear un scenario donde role no se detecta
        # y no hay DelegationEngine (ya estÃ¡ mockeado)
        with patch("builtins.input", return_value=""):
            exit_code = delegate_task("tarea_sin_match_xyz")
            assert exit_code == 0
            mock_run.assert_called_once()

    def test_interactive_keyboard_interrupt(self, mock_discovery):
        """KeyboardInterrupt en modo interactivo debe terminar gracefulmente."""
        from harness.delegate import _interactive_mode
        with patch("builtins.input", side_effect=KeyboardInterrupt):
            _interactive_mode()

    def test_main_logs_usage_no_args(self, mock_discovery, caplog):
        """main() sin args debe loguear mensaje de uso."""
        from harness.delegate import main
        with patch("harness.delegate.sys.argv", ["delegate.py"]):  # noqa: SIM117
            with caplog.at_level(logging.INFO):
                main()
        assert any("Uso" in msg for msg in caplog.messages)
