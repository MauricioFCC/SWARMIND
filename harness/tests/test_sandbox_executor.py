"""Tests del endurecimiento y cableado de SandboxExecutor (CWE-94).

Verifica que el aislamiento de ejecucion de codigo no confiable:
  - Aplica SIEMPRE los flags de endurecimiento docker (red, read-only, caps,
    pids, memoria, tmpfs, usuario sin privilegios).
  - `run_script` monta el workdir read-only en /work y ejecuta python /work/<name>.
  - El backend subprocess NO hereda el entorno completo (allowlist, sin
    secretos) y usa `cwd` = directorio padre del script.
  - La deteccion de backend respeta la prioridad docker > windows-jobobject >
    bwrap > subprocess.
  - El backend `windows-jobobject` fija limites del Job Object, asigna el hijo,
    cierra el handle y degrada a subprocess si la asignacion falla.
  - Un timeout se reporta como returncode 124 (nunca lanza).
  - Los stages pbt/mutation delegan en `SandboxExecutor.run_script`.

Regla: los tests NO ejecutan codigo real de los stages; monkeypatchean la
clase y capturan los argumentos del backend.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

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
    """Fuerza el backend de SandboxExecutor parcheando la deteccion.

    Args:
        monkeypatch: Fixture de pytest.
        backend: "docker", "windows-jobobject" o "subprocess".
    """
    if backend == "docker":
        monkeypatch.setattr(
            sandbox_executor.shutil,
            "which",
            lambda name: "docker" if name == "docker" else None,
        )
    elif backend == "windows-jobobject":
        monkeypatch.setattr(sandbox_executor.shutil, "which", lambda name: None)
        monkeypatch.setattr(sandbox_executor.os, "name", "nt")
        monkeypatch.setattr(sandbox_executor, "_load_kernel32", lambda: object())
    else:
        monkeypatch.setattr(sandbox_executor.shutil, "which", lambda name: None)
        monkeypatch.setattr(sandbox_executor, "_load_kernel32", lambda: None)


class _FakeKernel32:
    """Fake de `kernel32` que registra las llamadas al Job Object.

    Usa funciones planas (no metodos) como atributos para que
    `_configure_kernel32` pueda fijar `argtypes`/`restype` sin fallar.

    Args:
        assign_result: Valor que devuelve `AssignProcessToJobObject`.
    """

    def __init__(self, assign_result: bool = True) -> None:
        self.assign_result = assign_result
        self.created = 0
        self.set_info_calls = 0
        self.assign_calls = 0
        self.close_calls = 0
        self.last_active_limit = None
        self.last_job_memory = None

        def create_job(*_args):
            self.created += 1
            return 0x1234

        def set_info(_job, _info_class, info_ptr, _size):
            self.set_info_calls += 1
            extended = info_ptr._obj
            self.last_active_limit = (
                extended.BasicLimitInformation.ActiveProcessLimit
            )
            self.last_job_memory = extended.JobMemoryLimit
            return True

        def assign_process(*_args):
            self.assign_calls += 1
            return self.assign_result

        def close_handle(*_args):
            self.close_calls += 1
            return True

        self.CreateJobObjectW = create_job
        self.SetInformationJobObject = set_info
        self.AssignProcessToJobObject = assign_process
        self.CloseHandle = close_handle


class _FakeProc:
    """Fake de `subprocess.Popen` con `_handle`, `communicate` y `kill`.

    Args:
        returncode: Codigo de salida reportado.
        stdout: Salida estandar.
        stderr: Salida de error.
        timeout_first: Si True, la primera `communicate(timeout=...)` lanza
            `TimeoutExpired` (simula un proceso colgado).
    """

    def __init__(
        self,
        returncode: int = 0,
        stdout: str = "ok\n",
        stderr: str = "",
        timeout_first: bool = False,
    ) -> None:
        self._handle = 0xBEEF
        self.returncode = returncode
        self._stdout = stdout
        self._stderr = stderr
        self._timeout_first = timeout_first
        self.killed = False
        self.spawned = False

    def communicate(self, timeout=None):
        if self._timeout_first and timeout is not None:
            self._timeout_first = False
            raise subprocess.TimeoutExpired("cmd", timeout)
        return self._stdout, self._stderr

    def kill(self) -> None:
        self.killed = True
        self.returncode = -9


def _install_fake_popen(monkeypatch, proc: _FakeProc) -> dict:
    """Instala un fake de `subprocess.Popen` y captura sus kwargs.

    Args:
        monkeypatch: Fixture de pytest.
        proc: Proceso fake a devolver.

    Returns:
        Dict mutado en sitio con los kwargs de la ultima creacion.
    """
    captured: dict = {}

    def fake_popen(cmd, **kwargs):
        captured["cmd"] = list(cmd)
        captured["kwargs"] = kwargs
        proc.spawned = True
        return proc

    monkeypatch.setattr(sandbox_executor.subprocess, "Popen", fake_popen)
    return captured


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


# ============================================================================
# Deteccion de backend (prioridad)
# ============================================================================


class TestBackendDetection:
    """`_detect_backend` respeta la prioridad docker > jobobject > bwrap > subprocess."""

    def test_docker_has_top_priority(self, monkeypatch) -> None:
        """Con docker disponible se elige `docker` sin mirar lo demas."""
        monkeypatch.setattr(
            sandbox_executor.shutil,
            "which",
            lambda name: "docker" if name == "docker" else None,
        )
        assert sandbox_executor._detect_backend() == "docker"

    def test_nt_without_docker_uses_jobobject(self, monkeypatch) -> None:
        """Sin docker, en Windows con kernel32 se elige `windows-jobobject`."""
        monkeypatch.setattr(sandbox_executor.shutil, "which", lambda name: None)
        monkeypatch.setattr(sandbox_executor.os, "name", "nt")
        monkeypatch.setattr(sandbox_executor, "_load_kernel32", lambda: object())
        assert sandbox_executor._detect_backend() == "windows-jobobject"

    def test_without_docker_nor_jobobject_falls_to_subprocess(
        self, monkeypatch
    ) -> None:
        """Sin docker, sin kernel32 y sin bwrap se cae a `subprocess`."""
        monkeypatch.setattr(sandbox_executor.shutil, "which", lambda name: None)
        monkeypatch.setattr(sandbox_executor.os, "name", "nt")
        monkeypatch.setattr(sandbox_executor, "_load_kernel32", lambda: None)
        assert sandbox_executor._detect_backend() == "subprocess"


# ============================================================================
# Backend windows-jobobject
# ============================================================================


class TestWindowsJobObject:
    """Job Object: limites, asignacion, cierre y degradacion segura."""

    @staticmethod
    def _executor(monkeypatch, kernel32: _FakeKernel32) -> SandboxExecutor:
        """Construye un executor forzado al backend jobobject con fake kernel32.

        Args:
            monkeypatch: Fixture de pytest.
            kernel32: Fake de kernel32 a inyectar.

        Returns:
            Executor con backend `windows-jobobject` y kernel32 fake.
        """
        monkeypatch.setattr(
            sandbox_executor, "_detect_backend", lambda: "windows-jobobject"
        )
        monkeypatch.setattr(sandbox_executor, "_load_kernel32", lambda: kernel32)
        return SandboxExecutor()

    def test_sets_limits_assigns_and_closes(self, monkeypatch) -> None:
        """Fija limites, asigna el hijo al job y cierra el handle (siempre)."""
        kernel32 = _FakeKernel32(assign_result=True)
        proc = _FakeProc()
        captured = _install_fake_popen(monkeypatch, proc)
        ex = self._executor(monkeypatch, kernel32)

        result = ex.run(["python", "-c", "print(1)"])

        assert kernel32.created == 1
        assert kernel32.set_info_calls == 1
        assert kernel32.assign_calls == 1
        assert kernel32.close_calls == 1
        assert kernel32.last_active_limit == sandbox_executor.JOB_OBJECT_ACTIVE_PROCESS
        assert kernel32.last_job_memory == sandbox_executor.JOB_OBJECT_MEMORY_BYTES
        assert captured["kwargs"]["creationflags"] == sandbox_executor.CREATE_NO_WINDOW
        assert result.backend == "windows-jobobject"
        assert result.returncode == 0

    def test_assign_failure_degrades_to_subprocess(self, monkeypatch) -> None:
        """Si `AssignProcessToJobObject` falla, degrada a subprocess sin crashear."""
        kernel32 = _FakeKernel32(assign_result=False)
        proc = _FakeProc()
        _install_fake_popen(monkeypatch, proc)
        ex = self._executor(monkeypatch, kernel32)

        calls: list[list[str]] = []

        def fake_subprocess(cmd, timeout_s, env, workdir=None):
            calls.append(list(cmd))
            return SandboxResult("", "", 0, backend="subprocess")

        monkeypatch.setattr(ex, "_run_subprocess", fake_subprocess)

        result = ex.run(["python", "-c", "print(1)"])

        assert result.backend == "subprocess"
        assert calls == [["python", "-c", "print(1)"]]
        assert proc.killed is True
        assert kernel32.close_calls == 1

    def test_timeout_returns_124_and_kills(self, monkeypatch) -> None:
        """Un timeout del job se reporta como 124 y mata el hijo."""
        kernel32 = _FakeKernel32(assign_result=True)
        proc = _FakeProc(timeout_first=True)
        _install_fake_popen(monkeypatch, proc)
        ex = self._executor(monkeypatch, kernel32)

        result = ex.run(["python", "-c", "import time; time.sleep(99)"], timeout_s=1.0)

        assert result.returncode == 124
        assert result.backend == "windows-jobobject"
        assert "timeout" in result.stderr
        assert proc.killed is True
        assert kernel32.close_calls == 1


# ============================================================================
# Integracion real (Windows-only)
# ============================================================================


@pytest.mark.skipif(os.name != "nt", reason="Windows Job Object es Windows-only")
def test_real_jobobject_runs_script(tmp_path, monkeypatch) -> None:
    """Ejecuta un script real en un Job Object y verifica salida y backend."""
    script = tmp_path / "ok.py"
    script.write_text('print("ok")', encoding="utf-8")
    monkeypatch.setattr(
        sandbox_executor, "_detect_backend", lambda: "windows-jobobject"
    )
    ex = SandboxExecutor()

    result = ex.run_script(script)

    assert result.returncode == 0
    assert "ok" in result.stdout
    assert result.backend == "windows-jobobject"
