"""
Tests para MCPExecutor — cobertura completa de mcp_executor.py.

Cubre:
- Inicialización del executor (default_timeout, allowed_commands, workdir)
- Resolución de comandos (_resolve_command: pytest, python, shell, echo, unknown)
- Ejecución de subprocesos (_run_subprocess: éxito, timeout, FileNotFoundError, excepción)
- Ejecución pública (execute_tool: comando permitido/no permitido, tool desconocida)
- Validación de esquemas (validate_output: tipos, keys requeridas, propiedades anidadas)
- run_test (pytest, python, limpieza temp files)
- Logging (get_execution_log, clear_log)
- Edge cases (código vacío, comandos inválidos, resultados nulos)
"""
from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List
from unittest.mock import ANY, MagicMock, patch

import pytest

from harness.tools_sandbox.mcp_executor import (
    MCPExecutor,
    SandboxResult,
)


@pytest.fixture
def real_tmp_dir(tmp_path: Path) -> Path:
    """Crea un directorio temporal real para tests de run_test."""
    d = tmp_path / "mcp_sandbox_real"
    d.mkdir(parents=True, exist_ok=True)
    return d


# ===========================================================================
# Fixtures
# ===========================================================================


@pytest.fixture
def executor() -> MCPExecutor:
    """Fixture: MCPExecutor con valores por defecto."""
    return MCPExecutor()


@pytest.fixture
def executor_with_allowed() -> MCPExecutor:
    """Fixture: MCPExecutor con lista de comandos permitidos."""
    return MCPExecutor(allowed_commands=["pytest", "echo"])


# ===========================================================================
# Tests: Inicialización
# ===========================================================================


class TestInit:
    """Tests de inicialización del MCPExecutor."""

    def test_default_timeout(self) -> None:
        """Debe usar timeout por defecto de 30 segundos."""
        exe = MCPExecutor()
        assert exe.default_timeout == 30

    def test_custom_timeout(self) -> None:
        """Debe aceptar timeout personalizado."""
        exe = MCPExecutor(default_timeout=60)
        assert exe.default_timeout == 60

    def test_allowed_commands_none(self) -> None:
        """allowed_commands=None debe permitir todos los comandos."""
        exe = MCPExecutor()
        assert exe.allowed_commands is None

    def test_allowed_commands_list(self) -> None:
        """Debe aceptar lista de comandos permitidos."""
        exe = MCPExecutor(allowed_commands=["pytest", "python"])
        assert exe.allowed_commands == ["pytest", "python"]

    def test_workdir_default(self) -> None:
        """workdir debe ser None por defecto."""
        exe = MCPExecutor()
        assert exe.workdir is None

    def test_workdir_custom(self) -> None:
        """Debe aceptar workdir personalizado."""
        exe = MCPExecutor(workdir="/tmp/test")
        assert exe.workdir == "/tmp/test"

    def test_execution_log_empty(self) -> None:
        """El log de ejecución debe comenzar vacío."""
        exe = MCPExecutor()
        assert exe._execution_log == []
        assert exe.get_execution_log() == []

    def test_sandbox_result_to_dict(self) -> None:
        """SandboxResult.to_dict debe retornar dict con todos los campos."""
        result = SandboxResult(
            success=True,
            output="ok",
            error="",
            execution_time=1.5,
            trace_id="abc123",
            exit_code=0,
        )
        d = result.to_dict()
        assert d["success"] is True
        assert d["output"] == "ok"
        assert d["error"] == ""
        assert d["execution_time"] == 1.5
        assert d["trace_id"] == "abc123"
        assert d["exit_code"] == 0


# ===========================================================================
# Tests: _resolve_command
# ===========================================================================


class TestResolveCommand:
    """Tests del método _resolve_command."""

    def test_pytest_command(self, executor: MCPExecutor) -> None:
        """_resolve_command con tool_name='pytest' debe retornar comando pytest."""
        cmd = executor._resolve_command("pytest", {"test_path": "tests/", "args": ["-v"]})
        assert cmd[0] == "pytest"
        assert cmd[1] == "tests/"
        assert "-v" in cmd

    def test_pytest_default_path(self, executor: MCPExecutor) -> None:
        """_resolve_command pytest sin test_path debe usar 'tests' por defecto."""
        cmd = executor._resolve_command("pytest", {})
        assert cmd[1] == "tests"

    def test_python_command(self, executor: MCPExecutor) -> None:
        """_resolve_command con tool_name='python' debe retornar comando python."""
        cmd = executor._resolve_command("python", {"script": "script.py", "args": ["--flag"]})
        assert cmd[0] == "python"
        assert cmd[1] == "script.py"
        assert "--flag" in cmd

    def test_shell_command_win32(self, executor: MCPExecutor) -> None:
        """_resolve_command shell en win32 debe usar cmd /c."""
        with patch.object(sys, "platform", "win32"):
            cmd = executor._resolve_command("shell", {"command": "echo hello"})
        assert cmd == ["cmd", "/c", "echo hello"]

    def test_shell_command_unix(self, executor: MCPExecutor) -> None:
        """_resolve_command shell en Unix debe usar sh -c."""
        with patch.object(sys, "platform", "linux"):
            cmd = executor._resolve_command("shell", {"command": "echo hello"})
        assert cmd == ["sh", "-c", "echo hello"]

    def test_shell_missing_command(self, executor: MCPExecutor) -> None:
        """_resolve_command shell sin 'command' debe lanzar ValueError."""
        with pytest.raises(ValueError, match="'command' parameter is required"):
            executor._resolve_command("shell", {})

    def test_echo_command_win32(self, executor: MCPExecutor) -> None:
        """_resolve_command echo en win32 debe usar cmd /c echo."""
        with patch.object(sys, "platform", "win32"):
            cmd = executor._resolve_command("echo", {"msg": "hi"})
        assert cmd[0:3] == ["cmd", "/c", "echo"]

    def test_echo_command_unix(self, executor: MCPExecutor) -> None:
        """_resolve_command echo en Unix debe usar echo directo."""
        with patch.object(sys, "platform", "linux"):
            cmd = executor._resolve_command("echo", {"msg": "hi"})
        assert cmd[0] == "echo"

    def test_echo_no_params(self, executor: MCPExecutor) -> None:
        """_resolve_command echo sin params debe pasar 'no params'."""
        with patch.object(sys, "platform", "win32"):
            cmd = executor._resolve_command("echo", {})
        assert "no params" in cmd

    def test_unknown_tool(self, executor: MCPExecutor) -> None:
        """_resolve_command con tool desconocida debe lanzar ValueError."""
        with pytest.raises(ValueError, match="Unknown tool: 'invalid_tool'"):
            executor._resolve_command("invalid_tool", {})

    def test_tool_name_case_insensitive(self, executor: MCPExecutor) -> None:
        """_resolve_command debe ignorar mayúsculas/minúsculas en tool_name."""
        cmd = executor._resolve_command("PYTEST", {"test_path": "tests"})
        assert cmd[0] == "pytest"


# ===========================================================================
# Tests: _run_subprocess
# ===========================================================================


class TestRunSubprocess:
    """Tests del método _run_subprocess."""

    def test_success(self, executor: MCPExecutor) -> None:
        """_run_subprocess exitoso debe retornar SandboxResult con éxito."""
        mock_proc = MagicMock()
        mock_proc.communicate.return_value = ("output OK", "")
        mock_proc.returncode = 0

        with patch.object(subprocess, "Popen", return_value=mock_proc) as mock_popen:
            result = executor._run_subprocess(["echo", "hi"], 10, "trace123")

        assert result.success is True
        assert result.output == "output OK"
        assert result.error == ""
        assert result.trace_id == "trace123"
        assert result.exit_code == 0
        assert result.execution_time >= 0
        mock_popen.assert_called_once_with(
            ["echo", "hi"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=None,
            text=True,
        )

    def test_failure_nonzero_exit(self, executor: MCPExecutor) -> None:
        """_run_subprocess con exit_code != 0 debe marcar success=False."""
        mock_proc = MagicMock()
        mock_proc.communicate.return_value = ("", "error occurred")
        mock_proc.returncode = 1

        with patch.object(subprocess, "Popen", return_value=mock_proc):
            result = executor._run_subprocess(["false"], 10, "t2")

        assert result.success is False
        assert result.output == ""
        assert "error occurred" in result.error
        assert result.exit_code == 1

    def test_timeout(self, executor: MCPExecutor) -> None:
        """_run_subprocess con timeout debe retornar error de timeout."""
        mock_proc = MagicMock()
        # Primer communicate lanza TimeoutExpired, segundo (en except) retorna vacío
        mock_proc.communicate.side_effect = [
            subprocess.TimeoutExpired(cmd="test", timeout=5),
            ("", ""),
        ]

        with patch.object(subprocess, "Popen", return_value=mock_proc):
            result = executor._run_subprocess(["sleep", "10"], 5, "t3")

        assert result.success is False
        assert "timed out" in result.error.lower()
        assert result.exit_code == -1
        mock_proc.kill.assert_called_once()

    def test_file_not_found(self, executor: MCPExecutor) -> None:
        """_run_subprocess con FileNotFoundError debe retornar error."""
        with patch.object(subprocess, "Popen", side_effect=FileNotFoundError("no such command")):
            result = executor._run_subprocess(["nonexistent"], 10, "t4")

        assert result.success is False
        assert "not found" in result.error.lower()
        assert result.exit_code == -1

    def test_unexpected_exception(self, executor: MCPExecutor) -> None:
        """_run_subprocess con excepción inesperada debe retornar error."""
        with patch.object(subprocess, "Popen", side_effect=PermissionError("access denied")):
            result = executor._run_subprocess(["cmd"], 10, "t5")

        assert result.success is False
        assert "unexpected" in result.error.lower()
        assert result.exit_code == -1

    def test_output_truncation(self, executor: MCPExecutor) -> None:
        """_run_subprocess debe truncar output si excede _MAX_OUTPUT_BYTES."""
        mock_proc = MagicMock()
        # Generate output > 1MB
        large_output = "x" * (1_048_576 + 100)
        mock_proc.communicate.return_value = (large_output, "")
        mock_proc.returncode = 0

        with patch.object(subprocess, "Popen", return_value=mock_proc):
            result = executor._run_subprocess(["cat"], 10, "t6")

        assert result.success is True
        assert "(truncated)" in result.output
        assert len(result.output) <= 1_048_576 + 50  # + suffix len

    def test_stderr_truncation(self, executor: MCPExecutor) -> None:
        """_run_subprocess debe truncar stderr si excede _MAX_OUTPUT_BYTES."""
        mock_proc = MagicMock()
        large_error = "e" * (1_048_576 + 100)
        mock_proc.communicate.return_value = ("", large_error)
        mock_proc.returncode = 1

        with patch.object(subprocess, "Popen", return_value=mock_proc):
            result = executor._run_subprocess(["bad"], 10, "t7")

        assert result.success is False
        assert "(truncated)" in result.error
        assert len(result.error) <= 1_048_576 + 50

    def test_run_with_workdir(self) -> None:
        """_run_subprocess debe usar workdir configurado."""
        mock_proc = MagicMock()
        mock_proc.communicate.return_value = ("ok", "")
        mock_proc.returncode = 0

        exe = MCPExecutor(workdir="/custom/path")
        with patch.object(subprocess, "Popen", return_value=mock_proc) as mock_popen:
            exe._run_subprocess(["cmd"], 10, "t8")

        assert mock_popen.call_args[1]["cwd"] == "/custom/path"

    def test_communicate_with_timeout(self, executor: MCPExecutor) -> None:
        """_run_subprocess debe pasar timeout a communicate."""
        mock_proc = MagicMock()
        mock_proc.communicate.return_value = ("ok", "")
        mock_proc.returncode = 0

        with patch.object(subprocess, "Popen", return_value=mock_proc) as mock_popen:
            executor._run_subprocess(["cmd"], 15, "t9")

        mock_popen.return_value.communicate.assert_called_once_with(timeout=15)


# ===========================================================================
# Tests: execute_tool (public API)
# ===========================================================================


class TestExecuteTool:
    """Tests del método execute_tool."""

    def test_execute_allowed_command(self, executor_with_allowed: MCPExecutor) -> None:
        """execute_tool con comando permitido debe ejecutarse."""
        mock_proc = MagicMock()
        mock_proc.communicate.return_value = ("tests passed", "")
        mock_proc.returncode = 0

        with patch.object(subprocess, "Popen", return_value=mock_proc):
            result = executor_with_allowed.execute_tool("pytest", {"test_path": "tests/"})

        assert result.success is True
        assert result.output == "tests passed"

    def test_execute_disallowed_command(self, executor_with_allowed: MCPExecutor) -> None:
        """execute_tool con comando NO permitido debe retornar error sin ejecutar."""
        result = executor_with_allowed.execute_tool("python", {"script": "bad.py"})

        assert result.success is False
        assert "not in the allowed list" in result.error
        assert result.exit_code == -1

    def test_allowed_commands_none_means_all(self, executor: MCPExecutor) -> None:
        """execute_tool con allowed_commands=None debe ejecutar comandos conocidos sin restricción."""
        mock_proc = MagicMock()
        mock_proc.communicate.return_value = ("ok", "")
        mock_proc.returncode = 0

        with patch.object(subprocess, "Popen", return_value=mock_proc):
            result = executor.execute_tool("echo", {})

        assert result.success is True

    def test_unknown_tool_returns_error(self, executor: MCPExecutor) -> None:
        """execute_tool con tool desconocida debe retornar error sin ejecutar subprocess."""
        with patch.object(subprocess, "Popen") as mock_popen:
            result = executor.execute_tool("nonexistent_tool", {})

        assert result.success is False
        assert "Unknown tool" in result.error
        mock_popen.assert_not_called()

    def test_execute_logs_entry(self, executor: MCPExecutor) -> None:
        """execute_tool debe registrar una entrada en el log interno."""
        mock_proc = MagicMock()
        mock_proc.communicate.return_value = ("ok", "")
        mock_proc.returncode = 0

        with patch.object(subprocess, "Popen", return_value=mock_proc):
            executor.execute_tool("echo", {"message": "test"})

        assert len(executor._execution_log) == 1
        entry = executor._execution_log[0]
        assert entry["tool_name"] == "echo"
        assert entry["success"] is True
        assert entry["params"] == {"message": "test"}
        assert "trace_id" in entry
        assert "timestamp" in entry

    def test_execute_failure_logs_error(self, executor: MCPExecutor) -> None:
        """execute_tool fallido debe registrar el error en el log."""
        with patch.object(subprocess, "Popen", side_effect=FileNotFoundError("no file")):
            result = executor.execute_tool("echo", {})

        assert result.success is False
        assert len(executor._execution_log) == 1
        assert executor._execution_log[0]["success"] is False

    def test_execute_custom_timeout(self, executor: MCPExecutor) -> None:
        """execute_tool debe usar timeout personalizado si se pasa."""
        mock_proc = MagicMock()
        mock_proc.communicate.return_value = ("ok", "")
        mock_proc.returncode = 0

        with patch.object(subprocess, "Popen", return_value=mock_proc) as mock_popen:
            executor.execute_tool("echo", {}, timeout=5)

        mock_popen.return_value.communicate.assert_called_once_with(timeout=5)

    def test_execute_empty_params(self, executor: MCPExecutor) -> None:
        """execute_tool con params vacío debe manejar graceful."""
        mock_proc = MagicMock()
        mock_proc.communicate.return_value = ("ok", "")
        mock_proc.returncode = 0

        with patch.object(subprocess, "Popen", return_value=mock_proc):
            result = executor.execute_tool("echo", {})

        assert result.trace_id != ""
        assert isinstance(result.execution_time, float)

    def test_execute_subprocess_exception(self, executor: MCPExecutor) -> None:
        """execute_tool debe capturar excepciones de subprocess."""
        with patch.object(subprocess, "Popen", side_effect=PermissionError("denied")):
            result = executor.execute_tool("echo", {})

        assert result.success is False
        assert "unexpected error" in result.error.lower()


# ===========================================================================
# Tests: validate_output
# ===========================================================================


class TestValidateOutput:
    """Tests del método validate_output."""

    def test_validates_type_string(self, executor: MCPExecutor) -> None:
        """validate_output debe validar tipo string."""
        valid, msg = executor.validate_output("hello", {"type": "string"})
        assert valid is True

    def test_validates_type_mismatch(self, executor: MCPExecutor) -> None:
        """validate_output debe detectar tipo incorrecto."""
        valid, msg = executor.validate_output(123, {"type": "string"})
        assert valid is False
        assert "Expected type 'string'" in msg

    def test_validates_type_number(self, executor: MCPExecutor) -> None:
        """validate_output debe aceptar int o float para tipo 'number'."""
        assert executor.validate_output(42, {"type": "number"})[0] is True
        assert executor.validate_output(3.14, {"type": "number"})[0] is True

    def test_validates_type_boolean(self, executor: MCPExecutor) -> None:
        """validate_output debe validar tipo boolean."""
        assert executor.validate_output(True, {"type": "boolean"})[0] is True
        assert executor.validate_output("yes", {"type": "boolean"})[0] is False

    def test_validates_type_list(self, executor: MCPExecutor) -> None:
        """validate_output debe validar tipo list/array."""
        assert executor.validate_output([1, 2], {"type": "list"})[0] is True
        assert executor.validate_output([1, 2], {"type": "array"})[0] is True

    def test_validates_type_dict(self, executor: MCPExecutor) -> None:
        """validate_output debe validar tipo dict/object."""
        assert executor.validate_output({"a": 1}, {"type": "dict"})[0] is True
        assert executor.validate_output({"a": 1}, {"type": "object"})[0] is True

    def test_validates_type_null(self, executor: MCPExecutor) -> None:
        """validate_output debe validar tipo null."""
        assert executor.validate_output(None, {"type": "null"})[0] is True
        assert executor.validate_output(0, {"type": "null"})[0] is False

    def test_validates_type_any(self, executor: MCPExecutor) -> None:
        """validate_output con tipo 'any' debe aceptar cualquier valor."""
        assert executor.validate_output("cualquier", {"type": "any"})[0] is True
        assert executor.validate_output(42, {"type": "any"})[0] is True
        assert executor.validate_output(None, {"type": "any"})[0] is True

    def test_required_keys(self, executor: MCPExecutor) -> None:
        """validate_output debe detectar keys requeridas faltantes."""
        valid, msg = executor.validate_output(
            {"name": "test"}, {"type": "dict", "required": ["name", "version"]}
        )
        assert valid is False
        assert "Missing required keys" in msg

    def test_required_keys_present(self, executor: MCPExecutor) -> None:
        """validate_output debe pasar si todas las keys requeridas existen."""
        valid, _ = executor.validate_output(
            {"name": "test", "version": 1}, {"type": "dict", "required": ["name", "version"]}
        )
        assert valid is True

    def test_nested_properties(self, executor: MCPExecutor) -> None:
        """validate_output debe validar propiedades anidadas."""
        schema = {
            "type": "dict",
            "properties": {
                "data": {
                    "type": "list",
                }
            },
        }
        valid, msg = executor.validate_output({"data": [1, 2]}, schema)
        assert valid is True

    def test_nested_properties_fail(self, executor: MCPExecutor) -> None:
        """validate_output debe fallar en propiedades anidadas inválidas."""
        schema = {
            "type": "dict",
            "properties": {
                "data": {
                    "type": "list",
                }
            },
        }
        valid, msg = executor.validate_output({"data": "not_a_list"}, schema)
        assert valid is False
        assert "Key 'data'" in msg

    def test_no_schema_type_skips_check(self, executor: MCPExecutor) -> None:
        """validate_output sin 'type' en schema debe saltar verificación de tipo."""
        valid, msg = executor.validate_output("anything", {})
        assert valid is True
        assert msg == "Validation passed."

    def test_empty_dict_valid(self, executor: MCPExecutor) -> None:
        """validate_output con dict vacío sin required debe pasar."""
        valid, _ = executor.validate_output({}, {"type": "dict"})
        assert valid is True

    def test_nested_required_in_property(self, executor: MCPExecutor) -> None:
        """validate_output debe verificar keys requeridas en sub-objetos."""
        schema = {
            "type": "dict",
            "properties": {
                "meta": {
                    "type": "dict",
                    "required": ["id"],
                }
            },
        }
        valid, msg = executor.validate_output({"meta": {"name": "x"}}, schema)
        assert valid is False
        assert "Key 'meta'" in msg


# ===========================================================================
# Tests: run_test
# ===========================================================================


class TestRunTest:
    """Tests del método run_test."""

    def test_run_pytest(
        self, executor: MCPExecutor, real_tmp_dir: Path
    ) -> None:
        """run_test con test_type='pytest' debe escribir temp file y ejecutar pytest."""
        with patch.object(tempfile, "mkdtemp", return_value=str(real_tmp_dir)):
            mock_proc = MagicMock()
            mock_proc.communicate.return_value = ("tests passed", "")
            mock_proc.returncode = 0

            with patch.object(subprocess, "Popen", return_value=mock_proc) as mock_popen:
                with patch("shutil.rmtree"):
                    result = executor.run_test("def test_foo(): pass", test_type="pytest")

        assert result.success is True
        call_args = mock_popen.call_args[0][0]
        assert call_args[0] == "pytest"

    def test_run_python(
        self, executor: MCPExecutor, real_tmp_dir: Path
    ) -> None:
        """run_test con test_type='python' debe ejecutar python script."""
        with patch.object(tempfile, "mkdtemp", return_value=str(real_tmp_dir)):
            mock_proc = MagicMock()
            mock_proc.communicate.return_value = ("hello", "")
            mock_proc.returncode = 0

            with patch.object(subprocess, "Popen", return_value=mock_proc) as mock_popen:
                with patch("shutil.rmtree"):
                    result = executor.run_test("print('hello')", test_type="python")

        assert result.success is True
        call_args = mock_popen.call_args[0][0]
        assert call_args[0] == "python"

    def test_run_test_empty_code(
        self, executor: MCPExecutor, real_tmp_dir: Path
    ) -> None:
        """run_test con código vacío debe ejecutarse sin error."""
        with patch.object(tempfile, "mkdtemp", return_value=str(real_tmp_dir)):
            mock_proc = MagicMock()
            mock_proc.communicate.return_value = ("", "")
            mock_proc.returncode = 0

            with patch.object(subprocess, "Popen", return_value=mock_proc):
                with patch("shutil.rmtree"):
                    result = executor.run_test("", test_type="python")

        assert result is not None

    def test_run_test_cleanup_on_failure(
        self, executor: MCPExecutor, real_tmp_dir: Path
    ) -> None:
        """run_test debe limpiar temp files incluso si falla."""
        with patch.object(tempfile, "mkdtemp", return_value=str(real_tmp_dir)):
            with patch.object(subprocess, "Popen", side_effect=FileNotFoundError("no pytest")):
                with patch("shutil.rmtree") as mock_rmtree:
                    result = executor.run_test("def test_fail(): pass")

        assert result.success is False
        mock_rmtree.assert_called_once()

    def test_run_test_cleanup_error_swallowed(
        self, executor: MCPExecutor, real_tmp_dir: Path
    ) -> None:
        """run_test debe tragar errores de limpieza (best-effort)."""
        with patch.object(tempfile, "mkdtemp", return_value=str(real_tmp_dir)):
            mock_proc = MagicMock()
            mock_proc.communicate.return_value = ("ok", "")
            mock_proc.returncode = 0

            with patch.object(subprocess, "Popen", return_value=mock_proc):
                with patch("shutil.rmtree") as mock_rmtree:
                    mock_rmtree.side_effect = PermissionError("cannot delete")
                    result = executor.run_test("pass")

        assert result.success is True

    def test_run_test_pytest_with_timeout(
        self, executor: MCPExecutor, real_tmp_dir: Path
    ) -> None:
        """run_test debe pasar timeout a execute_tool."""
        with patch.object(tempfile, "mkdtemp", return_value=str(real_tmp_dir)):
            mock_proc = MagicMock()
            mock_proc.communicate.return_value = ("", "")
            mock_proc.returncode = 0

            with patch.object(subprocess, "Popen", return_value=mock_proc) as mock_popen:
                with patch("shutil.rmtree"):
                    executor.run_test("pass", test_type="pytest", timeout=3)

        mock_popen.return_value.communicate.assert_called_once_with(timeout=3)


# ===========================================================================
# Tests: get_execution_log / clear_log
# ===========================================================================


class TestExecutionLog:
    """Tests de get_execution_log y clear_log."""

    def test_get_log_empty(self, executor: MCPExecutor) -> None:
        """get_execution_log debe retornar lista vacía si no hay ejecuciones."""
        assert executor.get_execution_log() == []

    def test_get_log_with_entries(self, executor: MCPExecutor) -> None:
        """get_execution_log debe retornar entradas en orden reverso."""
        mock_proc = MagicMock()
        mock_proc.communicate.return_value = ("ok", "")
        mock_proc.returncode = 0

        with patch.object(subprocess, "Popen", return_value=mock_proc):
            executor.execute_tool("echo", {"n": 1})
            executor.execute_tool("echo", {"n": 2})

        log = executor.get_execution_log()
        assert len(log) == 2
        assert log[0]["params"]["n"] == 2  # newest first

    def test_get_log_limit(self, executor: MCPExecutor) -> None:
        """get_execution_log debe respetar el límite de entradas."""
        mock_proc = MagicMock()
        mock_proc.communicate.return_value = ("ok", "")
        mock_proc.returncode = 0

        with patch.object(subprocess, "Popen", return_value=mock_proc):
            for i in range(10):
                executor.execute_tool("echo", {"n": i})

        log = executor.get_execution_log(limit=3)
        assert len(log) == 3

    def test_clear_log(self, executor: MCPExecutor) -> None:
        """clear_log debe vaciar el log de ejecución."""
        mock_proc = MagicMock()
        mock_proc.communicate.return_value = ("ok", "")
        mock_proc.returncode = 0

        with patch.object(subprocess, "Popen", return_value=mock_proc):
            executor.execute_tool("echo", {})

        assert len(executor._execution_log) == 1
        executor.clear_log()
        assert executor._execution_log == []
        assert executor.get_execution_log() == []


# ===========================================================================
# Tests: Edge Cases Adicionales
# ===========================================================================


class TestEdgeCases:
    """Tests de casos borde del MCPExecutor."""

    def test_sandbox_result_defaults(self) -> None:
        """SandboxResult debe tener valores por defecto adecuados."""
        r = SandboxResult(success=False, output="", error="", execution_time=0.0)
        assert r.trace_id == ""
        assert r.exit_code == -1

    def test_sandbox_result_to_dict_roundtrip(self) -> None:
        """SandboxResult.to_dict debe incluir todos los campos."""
        r = SandboxResult(
            success=True,
            output="out",
            error="err",
            execution_time=2.5,
            trace_id="t1",
            exit_code=0,
        )
        d = r.to_dict()
        r2 = SandboxResult(**d)
        assert r2.success == r.success
        assert r2.output == r.output
        assert r2.execution_time == r.execution_time

    def test_execute_tool_creates_trace_id(self, executor: MCPExecutor) -> None:
        """execute_tool debe generar un trace_id único."""
        mock_proc = MagicMock()
        mock_proc.communicate.return_value = ("ok", "")
        mock_proc.returncode = 0

        with patch.object(subprocess, "Popen", return_value=mock_proc):
            r1 = executor.execute_tool("echo", {})
            r2 = executor.execute_tool("echo", {})

        assert r1.trace_id != r2.trace_id
        assert len(r1.trace_id) == 12

    def test_log_execution_entry_structure(self, executor: MCPExecutor) -> None:
        """Cada entrada del log debe tener la estructura correcta."""
        mock_proc = MagicMock()
        mock_proc.communicate.return_value = ("output", "err")
        mock_proc.returncode = 1

        with patch.object(subprocess, "Popen", return_value=mock_proc):
            executor.execute_tool("echo", {"test": 1})

        entry = executor._execution_log[0]
        assert "timestamp" in entry
        assert "trace_id" in entry
        assert "tool_name" in entry
        assert "params" in entry
        assert "success" in entry
        assert "execution_time" in entry
        assert "exit_code" in entry
        assert entry["tool_name"] == "echo"
        assert entry["success"] is False

    def test_multiple_allowed_commands_filter(self) -> None:
        """Executor con lista permitida debe rechazar tools fuera de lista."""
        exe = MCPExecutor(allowed_commands=["pytest"])
        result = exe.execute_tool("shell", {"command": "rm -rf /"})
        assert result.success is False
        assert "not in the allowed list" in result.error

    def test_validate_output_unknown_type(self, executor: MCPExecutor) -> None:
        """validate_output con tipo desconocido debe ignorarlo."""
        valid, msg = executor.validate_output("x", {"type": "unknown_type"})
        assert valid is True  # py_type is None, so check is skipped
