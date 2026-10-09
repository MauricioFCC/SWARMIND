"""test_universal_config_fitness.py — Fitness functions SDD + TDD adversarial.

WHAT: valida la refactorizacion "config universal" (ADR-0098) de SWARMIND con
  tres capas: (1) fitness function de portabilidad que falla si aparece una ruta
  personal de la maquina en codigo de produccion, (2) invariantes Property-Based
  Testing (PBT) de ``BackendConfig.from_env`` / ``GpuBudget.from_env`` y
  (3) casos adversariales + boundary value analysis (BVA) de
  ``backend_launcher.build_launch_command`` / ``detached_kwargs``.
WHY: la config debe ser universal (Windows/macOS/Linux) y fail-fast; un test
  decorativo no detecta una ruta personal filtrada, una precedencia invertida ni
  un default intercambiado. Los asserts "mutation-style" matan esos mutantes.
WHERE: SSOT ``harness/model_router/backend_config.py`` y
  ``harness/model_router/backend_launcher.py``.

Referencias: ADR-0098 (Clean Architecture, fail-fast, inmutabilidad, AAA),
ADR-0035 (paths portables), PROBE/AdverTest (loop adversarial), CPD (checklist
de boundaries).
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from urllib.parse import urlsplit

import pytest
from hypothesis import HealthCheck, assume, given, settings
from hypothesis import strategies as st

from harness.model_router import backend_config
from harness.model_router import backend_launcher as bl
from harness.model_router.backend_config import (
    DEFAULT_BASE_URL,
    DEFAULT_CTX_STEP,
    DEFAULT_GPU_BUDGET_MB,
    DEFAULT_MIN_FREE_VRAM_MB,
    DEFAULT_MIN_SAFE_CTX,
    DEFAULT_POLL_INTERVAL_S,
    DEFAULT_RETRY_ATTEMPTS,
    DEFAULT_RETRY_BACKOFF_S,
    DEFAULT_SAFE_CTX_MAX,
    DEFAULT_START_TIMEOUT_S,
    DEFAULT_VRAM_SAFETY,
    BackendConfig,
    GpuBudget,
)
from harness.qa.security_policy import _PERSONAL_PATH_RE


def _fitness_settings(*, max_examples: int = 50) -> settings:
    """Devuelve un decorador de Hypothesis con health checks suprimidos.

    Suprime ``function_scoped_fixture`` (usamos ``monkeypatch`` con ``@given``)
    y ``differing_executors`` (artefacto si el runner de mutacion re-ejecuta).

    Args:
        max_examples: Numero maximo de ejemplos por propiedad.

    Returns:
        Instancia ``Settings`` aplicable como decorador.
    """
    return settings(
        max_examples=max_examples,
        deadline=None,
        suppress_health_check=[
            HealthCheck.differing_executors,
            HealthCheck.function_scoped_fixture,
        ],
    )


# ---------------------------------------------------------------------------
# Fitness function: portabilidad (cero rutas personales en produccion)
# ---------------------------------------------------------------------------

_EXCLUDED_DIR_NAMES = frozenset({
    ".git", ".venv", "venv", "env", "node_modules", "__pycache__",
    ".pytest_cache", ".mypy_cache", ".ruff_cache", ".hypothesis",
    ".idea", ".vscode", "dist", "build", "target", ".tox", ".nox",
    "docs", "tests", "mutants",
})

#: Auto-exclusion: el scanner de la politica contiene los patrones a proposito
#: (docstring + regex de deteccion), por lo que no es una violacion real.
_ALLOWED_SELF_FILES = frozenset({"harness/qa/security_policy.py"})

#: Ruta de Google Drive con estructura personal (revela el layout del usuario).
_MI_UNIDAD_RE = re.compile(r"~[/\\]Mi unidad", re.IGNORECASE)


def _iter_production_python_files(root: Path) -> list[Path]:
    """Itera los ``.py`` de produccion podando directorios excluidos.

    Args:
        root: Raiz del repositorio.

    Returns:
        Lista de rutas a archivos ``.py`` de produccion.
    """
    files: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [name for name in dirnames if name not in _EXCLUDED_DIR_NAMES]
        for filename in filenames:
            if filename.endswith(".py"):
                files.append(Path(dirpath) / filename)
    return files


def test_no_hardcoded_machine_paths_in_production() -> None:
    """Fitness: cero rutas personales de la maquina en codigo de produccion.

    Escanea el repo (excluye tests, docs, ``__pycache__``, ``.git``) y falla si
    encuentra rutas absolutas con nombre de usuario o la estructura personal de
    Google Drive. Reutiliza el patron canonico de ``security_policy`` (ADR-0035).
    """
    # ARRANGE
    repo_root = Path(__file__).resolve().parents[2]
    violations: list[str] = []

    # ACT
    for py_file in _iter_production_python_files(repo_root):
        rel = py_file.relative_to(repo_root).as_posix()
        if rel in _ALLOWED_SELF_FILES:
            continue
        try:
            content = py_file.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for lineno, raw_line in enumerate(content.splitlines(), 1):
            if _PERSONAL_PATH_RE.search(raw_line) or _MI_UNIDAD_RE.search(raw_line):
                violations.append(f"{rel}:{lineno}: {raw_line.strip()[:120]}")

    # ASSERT
    assert not violations, (
        "Rutas de maquina hardcodeadas en produccion (usa env var + Path.home(), "
        "ADR-0035):\n  " + "\n  ".join(violations)
    )


def test_scanner_detects_known_machine_path_leaks() -> None:
    """Control positivo: el detector DEBE marcar leaks sinteticos (test del test).

    Construye las rutas por concatenacion para no auto-marcarse y verifica que
    tanto el patron POSIX/Windows como el de Google Drive detecten el leak.
    """
    # ARRANGE
    windows_leak = "C:" + "\\Users" + "\\" + "dev" + "\\proj"
    mac_leak = "/Users/" + "dev" + "/proj"
    linux_leak = "/home/" + "dev" + "/proj"
    mi_unidad_leak = "~/" + "Mi unidad/proj"

    # ACT + ASSERT
    for leak in (windows_leak, mac_leak, linux_leak):
        assert _PERSONAL_PATH_RE.search(leak), f"no detecto leak: {leak!r}"
    assert _MI_UNIDAD_RE.search(mi_unidad_leak), "no detecto leak de Google Drive"


def test_scanner_ignores_portable_paths() -> None:
    """Control negativo: placeholders portables NO deben marcarse (anti falso positivo)."""
    # ARRANGE
    portable = (
        "Path.home() / 'proj'",
        "~/proyecto/archivo",
        "<HOME>/data/modelo",
        "docs/home/guia.md",
    )

    # ACT + ASSERT
    for text in portable:
        assert not _PERSONAL_PATH_RE.search(text), f"falso positivo: {text!r}"
        assert not _MI_UNIDAD_RE.search(text), f"falso positivo: {text!r}"


# ---------------------------------------------------------------------------
# Estrategias PBT (DRY)
# ---------------------------------------------------------------------------

_ENV_KEYS = (
    "SWARMIND_GPU_BUDGET_MB",
    "SWARMIND_SAFE_CTX_MAX",
    "SWARMIND_MIN_FREE_VRAM_MB",
    "SWARMIND_MIN_SAFE_CTX",
    "SWARMIND_CTX_STEP",
    "SWARMIND_VRAM_SAFETY",
    "SWARMIND_LOCAL_BASE_URL",
    "SWARMIND_LLAMA_BASE_URL",
    "SWARMIND_LLAMA_EXECUTABLE",
    "SWARMIND_LLAMA_CONFIG",
    "SWARMIND_LLAMA_LAUNCHER",
    "SWARMIND_LLAMA_START_TIMEOUT_S",
    "SWARMIND_LLAMA_POLL_INTERVAL_S",
    "SWARMIND_LOCAL_RETRY_ATTEMPTS",
    "SWARMIND_LOCAL_RETRY_BACKOFF_S",
)

_VALID_HOSTS = ("127.0.0.1", "0.0.0.0", "localhost", "192.168.1.10", "example.com")


def _clear_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Borra todas las variables SWARMIND relevantes para partir de entorno limpio."""
    for key in _ENV_KEYS:
        monkeypatch.delenv(key, raising=False)


def _stub_discovery(monkeypatch: pytest.MonkeyPatch) -> None:
    """Desactiva el descubrimiento en disco (tests hermeticos, sin I/O real)."""
    monkeypatch.setattr(backend_config, "discover_executable", lambda: None)
    monkeypatch.setattr(backend_config, "discover_config_file", lambda: None)


@st.composite
def _valid_gpu_env(draw: st.DrawFn) -> dict[str, str]:
    """Estrategia: entorno GpuBudget valido (respeta todas las invariantes)."""
    safe_ctx_max = draw(st.integers(min_value=1, max_value=131072))
    return {
        "SWARMIND_GPU_BUDGET_MB": str(draw(st.integers(min_value=1, max_value=262144))),
        "SWARMIND_SAFE_CTX_MAX": str(safe_ctx_max),
        "SWARMIND_MIN_FREE_VRAM_MB": str(draw(st.integers(min_value=0, max_value=262144))),
        "SWARMIND_MIN_SAFE_CTX": str(draw(st.integers(min_value=1, max_value=safe_ctx_max))),
        "SWARMIND_CTX_STEP": str(draw(st.integers(min_value=1, max_value=8192))),
        "SWARMIND_VRAM_SAFETY": str(
            draw(st.floats(min_value=0.001, max_value=1.0, allow_nan=False, allow_infinity=False))
        ),
    }


@st.composite
def _base_urls(draw: st.DrawFn) -> str:
    """Estrategia: URL base OpenAI-compatible valida (scheme + host + port)."""
    scheme = draw(st.sampled_from(("http", "https")))
    host = draw(st.sampled_from(_VALID_HOSTS))
    port = draw(st.integers(min_value=1, max_value=65535))
    return f"{scheme}://{host}:{port}"


# ---------------------------------------------------------------------------
# PBT: GpuBudget.from_env
# ---------------------------------------------------------------------------


class TestGpuBudgetInvariants:
    """Invariantes PBT de ``GpuBudget.from_env`` (round-trip, defaults, fail-fast)."""

    @_fitness_settings()
    @given(env=_valid_gpu_env())
    def test_env_roundtrip(self, monkeypatch: pytest.MonkeyPatch, env: dict[str, str]) -> None:
        """PBT: un entorno valido se refleja 1:1 en GpuBudget (sin perdida)."""
        # ARRANGE
        _clear_env(monkeypatch)
        for key, value in env.items():
            monkeypatch.setenv(key, value)

        # ACT
        budget = GpuBudget.from_env()

        # ASSERT
        assert budget.budget_mb == int(env["SWARMIND_GPU_BUDGET_MB"])
        assert budget.safe_ctx_max == int(env["SWARMIND_SAFE_CTX_MAX"])
        assert budget.min_free_vram_mb == int(env["SWARMIND_MIN_FREE_VRAM_MB"])
        assert budget.min_safe_ctx == int(env["SWARMIND_MIN_SAFE_CTX"])
        assert budget.ctx_step == int(env["SWARMIND_CTX_STEP"])
        assert budget.vram_safety == float(env["SWARMIND_VRAM_SAFETY"])

    def test_defaults_when_env_absent(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Sin entorno, GpuBudget reproduce el contrato de 8GB (defaults exactos)."""
        # ARRANGE
        _clear_env(monkeypatch)

        # ACT
        budget = GpuBudget.from_env()

        # ASSERT
        assert (budget.budget_mb, budget.safe_ctx_max, budget.min_free_vram_mb,
                budget.min_safe_ctx, budget.ctx_step, budget.vram_safety) == (
            DEFAULT_GPU_BUDGET_MB, DEFAULT_SAFE_CTX_MAX, DEFAULT_MIN_FREE_VRAM_MB,
            DEFAULT_MIN_SAFE_CTX, DEFAULT_CTX_STEP, DEFAULT_VRAM_SAFETY)

    @_fitness_settings()
    @given(safety=st.floats(
        min_value=-1_000_000.0, max_value=1_000_000.0,
        allow_nan=False, allow_infinity=False,
    ))
    def test_vram_safety_out_of_range_raises(
        self, monkeypatch: pytest.MonkeyPatch, safety: float
    ) -> None:
        """PBT fail-fast: ``vram_safety`` fuera de ``(0, 1]`` lanza ValueError."""
        # ARRANGE
        assume(not (0.0 < safety <= 1.0))
        _clear_env(monkeypatch)
        monkeypatch.setenv("SWARMIND_VRAM_SAFETY", repr(safety))

        # ACT + ASSERT
        with pytest.raises(ValueError, match="WHAT"):
            GpuBudget.from_env()

    @_fitness_settings()
    @given(data=st.data())
    def test_min_safe_gt_max_raises(self, monkeypatch: pytest.MonkeyPatch, data: st.DataObject) -> None:
        """PBT fail-fast: piso de contexto mayor que el techo lanza ValueError."""
        # ARRANGE
        safe_max = data.draw(st.integers(min_value=1, max_value=65536))
        min_safe = safe_max + data.draw(st.integers(min_value=1, max_value=65536))
        _clear_env(monkeypatch)
        monkeypatch.setenv("SWARMIND_SAFE_CTX_MAX", str(safe_max))
        monkeypatch.setenv("SWARMIND_MIN_SAFE_CTX", str(min_safe))

        # ACT + ASSERT
        with pytest.raises(ValueError, match="WHAT"):
            GpuBudget.from_env()

    @_fitness_settings()
    @given(value=st.integers(max_value=0))
    def test_non_positive_safe_ctx_raises(
        self, monkeypatch: pytest.MonkeyPatch, value: int
    ) -> None:
        """PBT fail-fast: techo de contexto ``<= 0`` lanza ValueError."""
        # ARRANGE
        _clear_env(monkeypatch)
        monkeypatch.setenv("SWARMIND_SAFE_CTX_MAX", str(value))

        # ACT + ASSERT
        with pytest.raises(ValueError, match="WHAT"):
            GpuBudget.from_env()


# ---------------------------------------------------------------------------
# PBT: BackendConfig.from_env
# ---------------------------------------------------------------------------


class TestBackendConfigInvariants:
    """Invariantes PBT de ``BackendConfig.from_env`` (precedencia, listen, fail-fast)."""

    @_fitness_settings()
    @given(url=_base_urls())
    def test_base_url_roundtrip_and_listen_coherent(
        self, monkeypatch: pytest.MonkeyPatch, url: str
    ) -> None:
        """PBT: ``base_url`` se refleja y ``listen_address`` deriva host:puerto coherente."""
        # ARRANGE
        _clear_env(monkeypatch)
        _stub_discovery(monkeypatch)
        monkeypatch.setenv("SWARMIND_LOCAL_BASE_URL", url)

        # ACT
        config = BackendConfig.from_env()
        parts = urlsplit(url)

        # ASSERT
        assert config.base_url == url
        assert config.listen_address == f"{parts.hostname}:{parts.port}"

    @_fitness_settings()
    @given(new_url=_base_urls(), legacy_url=_base_urls())
    def test_new_url_beats_legacy(
        self, monkeypatch: pytest.MonkeyPatch, new_url: str, legacy_url: str
    ) -> None:
        """PBT precedencia: ``SWARMIND_LOCAL_BASE_URL`` gana al alias legacy."""
        # ARRANGE
        _clear_env(monkeypatch)
        _stub_discovery(monkeypatch)
        monkeypatch.setenv("SWARMIND_LOCAL_BASE_URL", new_url)
        monkeypatch.setenv("SWARMIND_LLAMA_BASE_URL", legacy_url)

        # ACT + ASSERT
        assert BackendConfig.from_env().base_url == new_url

    @_fitness_settings()
    @given(legacy_url=_base_urls())
    def test_legacy_fallback_when_new_absent(
        self, monkeypatch: pytest.MonkeyPatch, legacy_url: str
    ) -> None:
        """PBT precedencia: sin URL nueva, se usa el alias legacy."""
        # ARRANGE
        _clear_env(monkeypatch)
        _stub_discovery(monkeypatch)
        monkeypatch.setenv("SWARMIND_LLAMA_BASE_URL", legacy_url)

        # ACT + ASSERT
        assert BackendConfig.from_env().base_url == legacy_url

    def test_default_url_when_no_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Sin entorno, ``base_url`` es el default local."""
        # ARRANGE
        _clear_env(monkeypatch)
        _stub_discovery(monkeypatch)

        # ACT + ASSERT
        assert BackendConfig.from_env().base_url == DEFAULT_BASE_URL

    @_fitness_settings()
    @given(attempts=st.integers(max_value=0))
    def test_retry_attempts_below_one_raises(
        self, monkeypatch: pytest.MonkeyPatch, attempts: int
    ) -> None:
        """PBT fail-fast: ``retry_attempts < 1`` lanza ValueError."""
        # ARRANGE
        _clear_env(monkeypatch)
        _stub_discovery(monkeypatch)
        monkeypatch.setenv("SWARMIND_LOCAL_RETRY_ATTEMPTS", str(attempts))

        # ACT + ASSERT
        with pytest.raises(ValueError, match="WHAT"):
            BackendConfig.from_env()

    @_fitness_settings()
    @given(timeout=st.floats(max_value=0.0, allow_nan=False, allow_infinity=False))
    def test_non_positive_start_timeout_raises(
        self, monkeypatch: pytest.MonkeyPatch, timeout: float
    ) -> None:
        """PBT fail-fast: ``start_timeout_s <= 0`` lanza ValueError."""
        # ARRANGE
        _clear_env(monkeypatch)
        _stub_discovery(monkeypatch)
        monkeypatch.setenv("SWARMIND_LLAMA_START_TIMEOUT_S", repr(timeout))

        # ACT + ASSERT
        with pytest.raises(ValueError, match="WHAT"):
            BackendConfig.from_env()


# ---------------------------------------------------------------------------
# BVA + mutation-style: limites y defaults (mata mutantes de operadores)
# ---------------------------------------------------------------------------


class TestUniversalConfigBoundaries:
    """BVA + mutation-style: mata mutantes de comparadores (`<=`/`<`) y defaults."""

    def test_vram_safety_boundary_is_open_closed(self) -> None:
        """BVA: ``vram_safety=1.0`` valido (``<=1``); 0.0 y >1.0 invalidos (``>0``)."""
        assert GpuBudget(vram_safety=1.0).vram_safety == 1.0
        with pytest.raises(ValueError, match="WHAT"):
            GpuBudget(vram_safety=0.0)
        with pytest.raises(ValueError, match="WHAT"):
            GpuBudget(vram_safety=1.0000001)

    def test_min_safe_ctx_equal_to_max_is_valid(self) -> None:
        """BVA: ``min_safe_ctx == safe_ctx_max`` es valido (piso no supera techo)."""
        budget = GpuBudget(safe_ctx_max=4096, min_safe_ctx=4096)
        assert budget.min_safe_ctx == budget.safe_ctx_max == 4096

    def test_safe_ctx_max_one_is_valid(self) -> None:
        """BVA: ``safe_ctx_max=1`` es el minimo positivo valido."""
        budget = GpuBudget(safe_ctx_max=1, min_safe_ctx=1, ctx_step=1)
        assert budget.safe_ctx_max == 1

    def test_ctx_step_zero_invalid(self) -> None:
        """BVA: ``ctx_step=0`` invalido; ``1`` valido (mutante ``<=`` vs ``<``)."""
        assert GpuBudget(ctx_step=1).ctx_step == 1
        with pytest.raises(ValueError, match="WHAT"):
            GpuBudget(ctx_step=0)

    def test_retry_attempts_boundary(self) -> None:
        """BVA: ``retry_attempts=1`` valido (minimo); ``0`` invalido (como multi-*)."""
        assert BackendConfig(retry_attempts=1).retry_attempts == 1
        with pytest.raises(ValueError, match="WHAT"):
            BackendConfig(retry_attempts=0)

    def test_retry_backoff_non_negative(self) -> None:
        """BVA: ``retry_backoff_s=0`` valido; negativo invalido (como SMT ``> 0``)."""
        assert BackendConfig(retry_backoff_s=0.0).retry_backoff_s == 0.0
        with pytest.raises(ValueError, match="WHAT"):
            BackendConfig(retry_backoff_s=-0.0001)

    def test_timeouts_strictly_positive(self) -> None:
        """BVA: timeouts estrictamente positivos (0 invalido, epsilon valido)."""
        config = BackendConfig(start_timeout_s=0.001, poll_interval_s=0.001)
        assert config.start_timeout_s == 0.001
        with pytest.raises(ValueError, match="WHAT"):
            BackendConfig(start_timeout_s=0.0)
        with pytest.raises(ValueError, match="WHAT"):
            BackendConfig(poll_interval_s=0.0)

    def test_empty_base_url_invalid(self) -> None:
        """BVA: ``base_url`` vacia/en blanco invalida (fail-fast)."""
        with pytest.raises(ValueError, match="WHAT"):
            BackendConfig(base_url="   ")

    def test_defaults_not_swapped(self) -> None:
        """Mutation-style: los defaults exactos no se intercambian (default swap)."""
        config = BackendConfig()
        assert config.start_timeout_s == DEFAULT_START_TIMEOUT_S == 90.0
        assert config.poll_interval_s == DEFAULT_POLL_INTERVAL_S == 0.5
        assert config.retry_attempts == DEFAULT_RETRY_ATTEMPTS == 3
        assert config.retry_backoff_s == DEFAULT_RETRY_BACKOFF_S == 0.5

    def test_from_env_strips_all_trailing_slashes(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Mutation-style: ``rstrip('/')`` normaliza la URL (sin slash final)."""
        # ARRANGE
        _clear_env(monkeypatch)
        _stub_discovery(monkeypatch)
        monkeypatch.setenv("SWARMIND_LOCAL_BASE_URL", "http://127.0.0.1:9999///")

        # ACT + ASSERT
        assert BackendConfig.from_env().base_url == "http://127.0.0.1:9999"

    @pytest.mark.parametrize(
        ("base_url", "expected"),
        [
            ("http://127.0.0.1:11434", "127.0.0.1:11434"),
            ("http://127.0.0.1", "127.0.0.1:11434"),
            ("https://0.0.0.0:8080", "0.0.0.0:8080"),
            ("http://localhost:65535", "localhost:65535"),
        ],
    )
    def test_listen_address_matches_base_url(self, base_url: str, expected: str) -> None:
        """``listen_address`` deriva host:puerto con fallback de puerto ``11434``."""
        assert BackendConfig(base_url=base_url).listen_address == expected


# ---------------------------------------------------------------------------
# Adversarial + BVA: backend_launcher.build_launch_command / detached_kwargs
# ---------------------------------------------------------------------------


class TestBackendLauncherAdversarial:
    """Adversarial/BVA de ``build_launch_command`` (precedencia, fallback, error)."""

    def test_executable_preferred_over_launcher(self, tmp_path: Path) -> None:
        """Precedencia: si ambos existen, gana el binario (no el launcher)."""
        # ARRANGE
        exe = tmp_path / "llama-swap.exe"
        exe.write_text("x", encoding="utf-8")
        launcher = tmp_path / "start.bat"
        launcher.write_text("@echo off", encoding="utf-8")
        config = BackendConfig(
            base_url="http://127.0.0.1:11434", executable=exe, launcher=launcher
        )

        # ACT
        command = bl.build_launch_command(config)

        # ASSERT
        assert command[0] == str(exe)
        assert str(launcher) not in command

    def test_missing_executable_falls_back_to_launcher(self, tmp_path: Path) -> None:
        """Si el binario no existe pero el launcher si, se usa el launcher."""
        # ARRANGE
        missing = tmp_path / "nope.exe"
        launcher = tmp_path / "start.bat"
        launcher.write_text("@echo off", encoding="utf-8")
        config = BackendConfig(executable=missing, launcher=launcher)

        # ACT + ASSERT
        assert bl.build_launch_command(config) == ["cmd", "/c", str(launcher)]

    def test_executable_without_config_file_omits_config_flag(self, tmp_path: Path) -> None:
        """Sin ``config_file``, el comando NO incluye ``-config`` (solo ``-listen``)."""
        # ARRANGE
        exe = tmp_path / "llama-swap.exe"
        exe.write_text("x", encoding="utf-8")
        config = BackendConfig(base_url="http://127.0.0.1:11434", executable=exe)

        # ACT + ASSERT
        assert bl.build_launch_command(config) == [str(exe), "-listen", "127.0.0.1:11434"]

    @pytest.mark.parametrize("suffix", [".bat", ".cmd"])
    def test_windows_launcher_suffix_is_case_insensitive(
        self, tmp_path: Path, suffix: str
    ) -> None:
        """Un sufijo ``.BAT``/``.CMD`` en mayusculas sigue usando ``cmd /c``."""
        # ARRANGE
        launcher = tmp_path / f"start{suffix.upper()}"
        launcher.write_text("@echo off", encoding="utf-8")
        config = BackendConfig(launcher=launcher)

        # ACT + ASSERT
        assert bl.build_launch_command(config) == ["cmd", "/c", str(launcher)]

    def test_posix_launcher_suffix_is_case_insensitive(self, tmp_path: Path) -> None:
        """Un sufijo ``.SH`` en mayusculas sigue usando ``sh``."""
        # ARRANGE
        launcher = tmp_path / "start.SH"
        launcher.write_text("#!/bin/sh\n", encoding="utf-8")
        config = BackendConfig(launcher=launcher)

        # ACT + ASSERT
        assert bl.build_launch_command(config) == ["sh", str(launcher)]

    def test_missing_executable_and_no_launcher_raises(self, tmp_path: Path) -> None:
        """Sin binario existente ni launcher, lanza ``BackendLaunchError`` (WHAT+WHY+WHERE)."""
        # ARRANGE
        config = BackendConfig(executable=tmp_path / "nope.exe", launcher=None)

        # ACT
        with pytest.raises(bl.BackendLaunchError) as excinfo:
            bl.build_launch_command(config)

        # ASSERT
        message = str(excinfo.value)
        assert "WHAT" in message
        assert "WHY" in message
        assert "WHERE" in message

    def test_none_executable_and_missing_launcher_raises(self, tmp_path: Path) -> None:
        """Con ``executable=None`` y launcher inexistente, lanza ``BackendLaunchError``."""
        # ARRANGE
        config = BackendConfig(executable=None, launcher=tmp_path / "nope.bat")

        # ACT + ASSERT
        with pytest.raises(bl.BackendLaunchError):
            bl.build_launch_command(config)


class TestDetachedKwargsPlatform:
    """Matriz de plataforma y mutantes de ``detached_kwargs``."""

    def test_windows_flag_bits_exact(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Windows: ``creationflags`` = OR exacto de los tres flags, sin new session."""
        # ARRANGE
        monkeypatch.setattr(bl.os, "name", "nt")
        expected = (
            bl._WINDOWS_CREATE_NO_WINDOW
            | bl._WINDOWS_DETACHED_PROCESS
            | bl._WINDOWS_CREATE_NEW_PROCESS_GROUP
        )

        # ACT + ASSERT
        assert bl.detached_kwargs() == {"creationflags": expected}
        assert "start_new_session" not in bl.detached_kwargs()

    def test_windows_each_flag_bit_present(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Windows: cada flag (NO_WINDOW/DETACHED/NEW_GROUP) esta presente."""
        # ARRANGE
        monkeypatch.setattr(bl.os, "name", "nt")

        # ACT
        flags = bl.detached_kwargs()["creationflags"]

        # ASSERT
        assert flags & bl._WINDOWS_CREATE_NO_WINDOW
        assert flags & bl._WINDOWS_DETACHED_PROCESS
        assert flags & bl._WINDOWS_CREATE_NEW_PROCESS_GROUP

    @pytest.mark.parametrize("platform_name", ["linux", "darwin"])
    def test_posix_excludes_creationflags(
        self, monkeypatch: pytest.MonkeyPatch, platform_name: str
    ) -> None:
        """POSIX (Linux/macOS): solo ``start_new_session=True``, sin ``creationflags``."""
        # ARRANGE
        monkeypatch.setattr(bl.os, "name", "posix")
        monkeypatch.setattr(bl.sys, "platform", platform_name)

        # ACT + ASSERT
        assert bl.detached_kwargs() == {"start_new_session": True}
        assert "creationflags" not in bl.detached_kwargs()