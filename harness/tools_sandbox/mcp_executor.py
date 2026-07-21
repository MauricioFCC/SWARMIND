"""
Secure execution environment for MCP (Model Context Protocol) tools.

Provides a sandboxed executor that runs tools via subprocess with timeouts,
validates outputs against schemas, and logs every execution with a trace_id.
"""
from __future__ import annotations

import json
import logging
import subprocess
import tempfile
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_DEFAULT_TIMEOUT = 30  # seconds
_MAX_OUTPUT_BYTES = 1_048_576  # 1 MB


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------


@dataclass
class SandboxResult:
    """Result of a sandboxed tool execution."""

    success: bool
    output: str
    error: str
    execution_time: float  # seconds
    trace_id: str = ""
    exit_code: int = -1

    def to_dict(self) -> Dict[str, Any]:
        """To dict."""
        return {
            "success": self.success,
            "output": self.output,
            "error": self.error,
            "execution_time": self.execution_time,
            "trace_id": self.trace_id,
            "exit_code": self.exit_code,
        }


# ---------------------------------------------------------------------------
# MCPExecutor
# ---------------------------------------------------------------------------


class MCPExecutor:
    """
    Sandboxed executor for MCP tools.

    Tools are run as isolated subprocesses with configurable timeouts,
    output limits, and optional schema validation.

    Typical usage::

        executor = MCPExecutor()
        result = executor.execute_tool(
            "pytest",
            {"test_path": "tests/test_foo.py", "args": ["-v"]},
        )
        if result.success:
            logger.info(result.output)
    """

    def __init__(
        self,
        default_timeout: int = _DEFAULT_TIMEOUT,
        allowed_commands: Optional[List[str]] = None,
        workdir: Optional[str] = None,
    ) -> None:
        """
        Args:
            default_timeout: Default timeout in seconds (default 30).
            allowed_commands: Optional whitelist of allowed tool commands.
                If ``None``, all commands are allowed (use with caution).
            workdir: Working directory for subprocess execution.  If ``None``,
                the current working directory is used.
        """
        self.default_timeout = default_timeout
        self.allowed_commands = allowed_commands
        self.workdir = workdir
        self._execution_log: List[Dict[str, Any]] = []

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def execute_tool(
        self,
        tool_name: str,
        params: Dict[str, Any],
        timeout: Optional[int] = None,
    ) -> SandboxResult:
        """
        Execute a tool in a sandboxed subprocess.

        The tool is resolved to a system command and invoked via
        ``subprocess.Popen`` with a timeout.

        Built-in tool mappings:

        - ``"pytest"``  → ``pytest <test_path> [args]``
        - ``"python"``  → ``python <script> [args]``
        - ``"shell"``   → ``<command>``  (use with extreme caution)
        - ``"echo"``   → echo the params (safe testing)

        Args:
            tool_name: Name / identifier of the tool.
            params: Parameters dict passed to the tool.
            timeout: Optional per-call timeout (overrides default).

        Returns:
            ``SandboxResult`` with execution details.
        """
        trace_id = uuid.uuid4().hex[:12]
        start = time.perf_counter()

        # Security check: whitelist
        if (
            self.allowed_commands is not None
            and tool_name not in self.allowed_commands
        ):
            elapsed = time.perf_counter() - start
            result = SandboxResult(
                success=False,
                output="",
                error=f"Command '{tool_name}' is not in the allowed list.",
                execution_time=round(elapsed, 4),
                trace_id=trace_id,
                exit_code=-1,
            )
            self._log_execution(tool_name, params, result)
            return result

        # Resolve command
        try:
            cmd = self._resolve_command(tool_name, params)
        except ValueError as exc:
            elapsed = time.perf_counter() - start
            result = SandboxResult(
                success=False,
                output="",
                error=str(exc),
                execution_time=round(elapsed, 4),
                trace_id=trace_id,
                exit_code=-1,
            )
            self._log_execution(tool_name, params, result)
            return result

        # Execute
        result = self._run_subprocess(cmd, timeout or self.default_timeout, trace_id)

        self._log_execution(tool_name, params, result)
        return result

    def validate_output(
        self,
        output: Any,
        schema: Dict[str, Any],
    ) -> Tuple[bool, str]:
        """
        Validate that an output value conforms to a JSON-like schema.

        The schema is a dict with optional keys:

        - ``"type"``: expected Python type name (e.g. ``"dict"``, ``"list"``, ``"str"``)
        - ``"required"``: list of required keys (for dict type)
        - ``"properties"``: dict of key -> sub-schema (for nested validation)

        Args:
            output: The value to validate.
            schema: Schema definition dict.

        Returns:
            ``(is_valid, message)`` tuple.
        """
        # Type check
        expected_type = schema.get("type")
        if expected_type:
            type_map = {
                "string": str,
                "integer": int,
                "number": (int, float),
                "boolean": bool,
                "list": list,
                "dict": dict,
                "array": list,
                "object": dict,
                "null": type(None),
                "any": object,
            }
            py_type = type_map.get(expected_type)
            if py_type is not None and not isinstance(output, py_type):
                return False, (
                    f"Expected type '{expected_type}', "
                    f"got '{type(output).__name__}'"
                )

        # Required keys check (for dicts)
        if isinstance(output, dict):
            required = schema.get("required", [])
            missing = [k for k in required if k not in output]
            if missing:
                return (
                    False,
                    f"Missing required keys: {missing}",
                )

            # Nested property validation
            properties = schema.get("properties", {})
            for key, sub_schema in properties.items():
                if key in output:
                    valid, msg = self.validate_output(
                        output[key], sub_schema
                    )
                    if not valid:
                        return False, f"Key '{key}': {msg}"

        return True, "Validation passed."

    def run_test(
        self,
        code: str,
        test_type: str = "pytest",
        timeout: Optional[int] = None,
    ) -> SandboxResult:
        """
        Run a test snippet in the sandbox.

        This is a convenience wrapper around ``execute_tool`` that writes
        the code to a temporary file and runs the selected test runner.

        Args:
            code: The test code as a string.
            test_type: Test runner type (``"pytest"``, ``"python"``).
            timeout: Optional per-call timeout.

        Returns:
            ``SandboxResult`` with execution details.
        """
        # SECURITY: Use temp files instead of eval/exec to prevent code injection.
        # This also enables pytest discovery and proper tracebacks.
        try:
            tmp_dir = Path(tempfile.mkdtemp(prefix="mcp_sandbox_"))
            tmp_file = tmp_dir / "test_code.py"
            tmp_file.write_text(code, encoding="utf-8")

            if test_type == "pytest":
                return self.execute_tool("pytest", {
                    "test_path": str(tmp_file),
                    "args": ["-x", "--tb=short"],
                }, timeout=timeout)

            # Default: run as plain Python
            return self.execute_tool("python", {
                "script": str(tmp_file),
                "args": [],
            }, timeout=timeout)
        finally:
            # Clean up temp file (best-effort)
            try:
                import shutil
                shutil.rmtree(str(tmp_dir), ignore_errors=True)
            except Exception as _exc:
                logger.warning("mcp_executor: %s", _exc)

    def get_execution_log(
        self,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """
        Return recent execution log entries.

        Args:
            limit: Maximum number of entries to return (newest first).

        Returns:
            List of log entry dicts.
        """
        return list(reversed(self._execution_log[-limit:]))

    def clear_log(self) -> None:
        """Clear the execution log."""
        self._execution_log.clear()
        logger.info("MCPExecutor execution log cleared.")

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _resolve_command(
        self, tool_name: str, params: Dict[str, Any]
    ) -> List[str]:
        """
        Convert a tool name + params into a subprocess command list.

        Raises ``ValueError`` if the tool cannot be resolved.
        """
        import sys  # noqa: PLC0415  — platform detection

        tool_name = tool_name.strip().lower()

        if tool_name == "pytest":
            test_path = params.get("test_path", "tests")
            args = params.get("args", [])
            return ["pytest", test_path, *args]

        if tool_name == "python":
            script = params.get("script", "")
            args = params.get("args", [])
            return ["python", script, *args]

        if tool_name == "shell":
            command = params.get("command", "")
            if not command:
                raise ValueError("'command' parameter is required for shell tool.")
            # Use cmd /c on Windows, sh -c on Unix
            if sys.platform == "win32":
                return ["cmd", "/c", command]
            return ["sh", "-c", command]

        if tool_name == "echo":
            text = json.dumps(params) if params else "no params"
            # Windows: echo is a shell built-in; use cmd /c
            if sys.platform == "win32":
                return ["cmd", "/c", "echo", text]
            return ["echo", text]

        raise ValueError(f"Unknown tool: '{tool_name}'")

    def _run_subprocess(
        self,
        cmd: List[str],
        timeout: int,
        trace_id: str,
    ) -> SandboxResult:
        """Execute a command and return the SandboxResult."""
        start = time.perf_counter()
        logger.debug(
            "Executing [trace_id=%s]: %s (timeout=%ds)",
            trace_id,
            " ".join(str(c) for c in cmd),
            timeout,
        )

        try:
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=self.workdir,
                text=True,
            )
            stdout, stderr = proc.communicate(timeout=timeout)

            elapsed = time.perf_counter() - start
            exit_code = proc.returncode or 0

            # Truncate output if too large
            if len(stdout) > _MAX_OUTPUT_BYTES:
                stdout = stdout[:_MAX_OUTPUT_BYTES] + "\n... (truncated)"
            if len(stderr) > _MAX_OUTPUT_BYTES:
                stderr = stderr[:_MAX_OUTPUT_BYTES] + "\n... (truncated)"

            return SandboxResult(
                success=exit_code == 0,
                output=stdout.strip(),
                error=stderr.strip(),
                execution_time=round(elapsed, 4),
                trace_id=trace_id,
                exit_code=exit_code,
            )

        except subprocess.TimeoutExpired:
            proc.kill()
            proc.communicate()
            elapsed = time.perf_counter() - start
            return SandboxResult(
                success=False,
                output="",
                error=f"Execution timed out after {timeout}s.",
                execution_time=round(elapsed, 4),
                trace_id=trace_id,
                exit_code=-1,
            )

        except FileNotFoundError as exc:
            elapsed = time.perf_counter() - start
            return SandboxResult(
                success=False,
                output="",
                error=f"Command not found: {exc}",
                execution_time=round(elapsed, 4),
                trace_id=trace_id,
                exit_code=-1,
            )

        except Exception as exc:
            elapsed = time.perf_counter() - start
            logger.exception(
                "Unexpected subprocess error [trace_id=%s]", trace_id
            )
            return SandboxResult(
                success=False,
                output="",
                error=f"Unexpected error: {exc}",
                execution_time=round(elapsed, 4),
                trace_id=trace_id,
                exit_code=-1,
            )

    def _log_execution(
        self,
        tool_name: str,
        params: Dict[str, Any],
        result: SandboxResult,
    ) -> None:
        """Record an execution entry in the internal log."""
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "trace_id": result.trace_id,
            "tool_name": tool_name,
            "params": params,
            "success": result.success,
            "execution_time": result.execution_time,
            "exit_code": result.exit_code,
        }
        self._execution_log.append(entry)

        if result.success:
            logger.info(
                "Tool '%s' OK [trace_id=%s, time=%.2fs]",
                tool_name,
                result.trace_id,
                result.execution_time,
            )
        else:
            logger.warning(
                "Tool '%s' FAILED [trace_id=%s, time=%.2fs, error=%s]",
                tool_name,
                result.trace_id,
                result.execution_time,
                result.error[:200],
            )
