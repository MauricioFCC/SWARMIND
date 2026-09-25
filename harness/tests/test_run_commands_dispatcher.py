"""Tests de run_command — despachador con late-binding (parcheable).

Verifica que CUALQUIER handler del paquete pueda parchearse con
``unittest.mock.patch("harness.run_commands.<fn>")`` y que run_command
resuelva el Mock en tiempo de ejecucion (patron sys.modules).
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from harness.run_commands import (
    _COMMAND_TABLE,
    _get_pkg_attr,
    run_command,
)
from harness.run_commands import (
    sys as pkg_sys,
)
from harness.run_commands import (
    time as pkg_time,
)


class TestLateBinding:
    """_get_pkg_attr: Mock si el paquete esta parcheado, fallback si no."""

    def test_returns_mock_when_patched(self) -> None:
        fallback = lambda: None
        with patch("harness.run_commands._handle_hermes") as mock_fn:
            resolved = _get_pkg_attr("_handle_hermes", fallback)
        assert resolved is mock_fn

    def test_returns_fallback_without_patch(self) -> None:
        from harness.run_commands import _handle_hermes

        assert _get_pkg_attr("_handle_hermes", _handle_hermes) is _handle_hermes


class TestRunCommandDispatch:
    """run_command enruta cada comando al handler correcto (mockeado)."""

    @pytest.mark.parametrize(
        ("cmd", "handler_name"),
        [
            # handlers_extra
            ("!evolve mutate x", "_handle_evolve_mutate"),
            ("!schedule add cron", "_handle_schedule_add"),
            ("!schedule list", "_handle_schedule_list"),
            ("!hermes sync", "_handle_hermes"),
            # handlers_iteration
            ("!iteration end --quick", "_handle_iteration_end"),
            ("!iteration quick", "_handle_iteration_quick"),
            ("!iteration auto", "_handle_iteration_auto"),
            ("!iteration history 3", "_handle_iteration_history"),
            ("!iteration diff", "_handle_iteration_diff"),
            ("!iteration report", "_handle_iteration_report"),
            # handlers_other
            ("!db migrate up", "_handle_db_migrate"),
            ("!db list-imports", "_handle_db_list_imports"),
            ("!db stats", "_handle_db_stats"),
            ("!db rollback 2", "_handle_db_rollback"),
            ("!hooks install", "_handle_hooks_install"),
            ("!hooks uninstall", "_handle_hooks_uninstall"),
            ("!hooks status", "_handle_hooks_status"),
            ("!rag ingest docs/", "_handle_rag_ingest"),
            ("!rag stats", "_handle_rag_stats"),
        ],
    )
    def test_routes_to_patched_handler(
        self, cmd: str, handler_name: str
    ) -> None:
        # Se aísla la construcción del store: bajo test aquí solo importa
        # que el DESPACHO resuelva el mock vía late-binding.
        with patch(f"harness.run_commands.{handler_name}") as mock_fn, \
             patch("harness.run_commands._create_store",
                   return_value=MagicMock()):
            run_command(cmd, harness_root=None)
        mock_fn.assert_called_once()

    def test_store_signature_receives_injected_store(self) -> None:
        store = MagicMock()
        with patch("harness.run_commands._handle_rag_stats") as mock_fn:
            run_command("!rag stats", store=store)
        mock_fn.assert_called_once_with(store)

    def test_store_cmd_creates_store_lazily(self) -> None:
        fake_store = MagicMock()
        with patch("harness.run_commands._handle_evolve_mutate") as mock_fn, \
             patch("harness.run_commands._create_store",
                   return_value=fake_store):
            run_command("!evolve mutate --dry-run")
        mock_fn.assert_called_once_with(fake_store, "!evolve mutate --dry-run")

    def test_root_signature_receives_cmd_and_root(self, tmp_path) -> None:
        with patch("harness.run_commands._handle_iteration_end") as mock_fn:
            run_command("!iteration end", harness_root=tmp_path)
        mock_fn.assert_called_once_with("!iteration end", tmp_path)

    def test_none_signature_no_args(self) -> None:
        with patch("harness.run_commands._handle_hooks_status") as mock_fn:
            run_command("!hooks status")
        mock_fn.assert_called_once_with()

    def test_unknown_command_raises_value_error(self) -> None:
        with pytest.raises(ValueError, match="no reconocido"):
            run_command("!comando-inexistente")

    def test_case_and_whitespace_insensitive_routing(self) -> None:
        with patch("harness.run_commands._handle_hooks_status") as mock_fn:
            run_command("  !HOOKS STATUS ")
        mock_fn.assert_called_once_with()


class TestBackwardCompatExports:
    """Los patches legacy de test_run_commands siguen funcionando."""

    def test_colors_and_stdlib_exports_present(self) -> None:
        import harness.run_commands as rc

        for attr in (
            "_safe_print", "_bold", "_cyan", "_err", "_ok", "_warn",
            "_BOLD", "_CYAN", "_GREEN", "_RED", "_RESET", "_YELLOW",
            "logger", "sys", "time",
        ):
            assert hasattr(rc, attr), f"falta export {attr}"

    def test_sys_time_are_same_modules(self) -> None:
        assert pkg_sys is __import__("sys")
        assert pkg_time is __import__("time")


class TestCommandTable:
    """Invariantes de la tabla canonica."""

    def test_all_handlers_exist_in_package(self) -> None:
        import harness.run_commands as rc

        for _, handler_name, _ in _COMMAND_TABLE:
            assert hasattr(rc, handler_name), f"falta {handler_name}"

    def test_signatures_are_valid(self) -> None:
        valid = {"store_cmd", "store", "cmd", "none", "root"}
        for _, _, signature in _COMMAND_TABLE:
            assert signature in valid

    def test_prefixes_unique(self) -> None:
        prefixes = [p for p, _, _ in _COMMAND_TABLE]
        assert len(prefixes) == len(set(prefixes))
