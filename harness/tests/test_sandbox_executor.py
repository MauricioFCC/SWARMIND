"""Tests del endurecimiento y cableado de SandboxExecutor (CWE-94).

Verifica que el aislamiento de ejecucion de codigo no confiable:
  - Aplica SIEMPRE los flags de endurecimiento docker (red, read-only, caps,
    pids, memoria, tmpfs, usuario sin privilegios).
  - `run_script` monta el workdir read-only en /work y ejecuta python /work/<name>.
  - El backend subprocess NO hereda el entorno completo (allowlist, sin
    secretos) y usa `cwd` = directorio padre del script.
  - Un timeout se reporta como returncode 124 (nunca lanza).
  - Los stages pbt/mutation delegan en `SandboxExecutor.run_script`.

Regla: los tests NO ejecutan codigo real de los stages; monkeypatchean la
clase y capturan los argumentos del backend.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from harness.validation import sandbox_executor
from harness.validation.mutation_stage import run_mutation_stage
from harness.validation.pbt_stage import run_pbt_stage
from harness.validation.sandbox_executor import (
    SandboxExecutor,
    SandboxResult,
)

# ============================================================================
# Helpers
# ============================================================================


def _capture_run(monkeypatch) -> dict:
    """Instala un fake de `subprocess.run` que captura cmd y kwargs.

    Args:
        monkeypatch: Fixture de pytest para parchear atributos.

    Returns:
        Dict mutado en sitio con "cmd" y "kwargs" de la ultima llamada.
    """
    captured: dict = {}

    def fake_run(cmd, **kwargs):
        captured["cmd"] = list(cmd)
        captured["kwargs"] = kwargs
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr(sandbox_executor.subprocess, "run", fake_run)
    return captured


def _force_backend(monkeypatch, backend: str) -> None:
    """Fuerza el backend de SandboxExecutor parcheando `shutil.which`.

    Args:
        monkeypatch: Fixture de pytest.
        backend: "docker" o "subprocess".
    """
    if backend == "docker":
        monkeypatch.setattr(
            sandbox_executor.shutil,
            "which",
            lambda name: "docker" if name == "docker" else None,
        )
    else:
        monkeypatch.setattr(sandbox_executor.shutil, "which", lambda name: None)


# ============================================================================
# Endurecimiento docker
# ============================================================================


class TestDockerHardening:
    """Flags de aislamiento aplicados SIEMPRE al `docker run`."""

    def test_docker_cmd_contains_all_hardening_flags(self, monkeypatch) -> None:
        """El comando docker incluye red/caps/read-only/pids/memoria/tmpfs."""
        _force_backend(monkeypatch, "docker")
        captured = _capture_run(monkeypatch)
        ex = SandboxExecutor()
        assert ex.backend == "docker"
        result = ex.run(["python", "-c", "print(1)"])
        joined = " ".join(captured["cmd"])
        assert "--network none" in joined
        assert "--read-only" in joined
        assert "--cap-drop ALL" in joined
        assert "--security-opt no-new-privileges" in joined
        assert "--pids-limit" in joined
        assert "--memory" in joined
        assert "--tmpfs" in joined
        assert result.backend == "docker"

    def test_run_script_mounts_workdir_readonly(self, monkeypatch, tmp_path) -> None:
        """`run_script` monta el padre en /work:ro y ejecuta python /work/<name>."""
        _force_backend(monkeypatch, "docker")
        captured = _capture_run(monkeypatch)
        script = tmp_path / "gen.py"
        script.write_text("print('hi')", encoding="utf-8")
        ex = SandboxExecutor()
        ex.run_script(script)
        joined = " ".join(captured["cmd"])
        assert f"-v {tmp_path}:{sandbox_executor.SANDBOX_WORKDIR}:ro" in joined
        assert f"--workdir {sandbox_executor.SANDBOX_WORKDIR}" in joined
        assert "python /work/gen.py" in joined


# ============================================================================
# Backend subprocess (allowlist + cwd)
# ============================================================================


class TestSubprocessBackend:
    """Entorno limpio, cwd acotado y timeout accionable."""

    def test_env_allowlist_excludes_secrets(self, monkeypatch) -> None:
        """Un secreto del padre (OPENAI_API_KEY) NO llega al subproceso."""
        _force_backend(monkeypatch, "subprocess")
        monkeypatch.setenv("OPENAI_API_KEY", "super-secret")
        captured = _capture_run(monkeypatch)
        ex = SandboxExecutor()
        assert ex.backend == "subprocess"
        ex.run(["python", "-c", "print(1)"])
        env = captured["kwargs"]["env"]
        assert "OPENAI_API_KEY" not in env
        assert "PATH" in env
        assert env["PYTHONDONTWRITEBYTECODE"] == "1"
        assert env["PYTHONNOUSERSITE"] == "1"

    def test_run_script_uses_parent_cwd(self, monkeypatch, tmp_path) -> None:
        """El subproceso corre con cwd = directorio padre del script."""
        _force_backend(monkeypatch, "subprocess")
        captured = _capture_run(monkeypatch)
        script = tmp_path / "mutant_check.py"
        script.write_text("print('hi')", encoding="utf-8")
        SandboxExecutor().run_script(script)
        assert captured["kwargs"]["cwd"] == str(tmp_path)
        assert captured["cmd"][0] == sys.executable

    def test_timeout_returns_124(self, monkeypatch, tmp_path) -> None:
        """Un timeout del subproceso se reporta como returncode 124."""
        _force_backend(monkeypatch, "subprocess")

        def fake_run(cmd, **kwargs):
            raise subprocess.TimeoutExpired(cmd, kwargs.get("timeout", 1.0))

        monkeypatch.setattr(sandbox_executor.subprocess, "run", fake_run)
        script = tmp_path / "slow.py"
        script.write_text("import time; time.sleep(10)", encoding="utf-8")
        result = SandboxExecutor().run_script(script, timeout_s=1.0)
        assert result.returncode == 124
        assert "timeout" in result.stderr


# ============================================================================
# Cableado de los stages (sin ejecutar codigo real)
# ============================================================================


class TestStagesWired:
    """pbt_stage y mutation_stage delegan en SandboxExecutor.run_script."""

    def test_pbt_stage_delegates_to_run_script(self, monkeypatch) -> None:
        """`run_pbt_stage` invoca `run_script` (no subprocess crudo)."""
        calls: list[Path] = []

        def fake_run_script(self, script_path, **kwargs):
            calls.append(Path(script_path))
            return SandboxResult(stdout="", stderr="", returncode=0, backend="subprocess")

        monkeypatch.setattr(SandboxExecutor, "run_script", fake_run_script)
        source = (
            "def add(a, b):\n"
            '    """Suma dos numeros y devuelve el resultado."""\n'
            "    return a + b\n"
        )
        report = run_pbt_stage(source, "agent", max_examples=5)
        assert calls
        assert report["passed"] is True

    def test_mutation_stage_delegates_to_run_script(self, monkeypatch) -> None:
        """`run_mutation_stage` invoca `run_script` (no subprocess crudo)."""
        calls: list[Path] = []

        def fake_run_script(self, script_path, **kwargs):
            calls.append(Path(script_path))
            return SandboxResult(stdout="out", stderr="", returncode=0, backend="subprocess")

        monkeypatch.setattr(SandboxExecutor, "run_script", fake_run_script)
        source = "def add(a, b):\n    return a + b\nprint(add(2, 3))\n"
        report = run_mutation_stage(source, "agent", num_mutants=3)
        assert calls
        assert report["total_mutants"] >= 1
