"""Tests para vram_guard + keep_alive por tier (anti-OOM GPU).

Causa de 2 OOMs: keep_alive 5m en todos los tiers (Qwen3.8 5.8GB +
un 9B coding 6.6GB residentes = 12.4GB > 8GB) + Unsloth concurrente. Fix:
vram_guard antes de ejecutar + keep_alive "0" (descarga inmediata)
en tiers grandes.
"""

import subprocess
from pathlib import Path

import pytest

from harness.model_router import vram_guard
from harness.model_router.vram_guard import (
    MODEL_FOOTPRINT_MB,
    _parse_free_mb,
    fits_in_vram,
    free_vram_mb,
)


def test_footprints_documented() -> None:
    """Footprints conocidos de la flota 2026-10-01 (MB en VRAM con Q4/Q8)."""
    assert MODEL_FOOTPRINT_MB["qwen3.5-4b"] == 3600
    assert MODEL_FOOTPRINT_MB["mimo"] == 6100
    assert MODEL_FOOTPRINT_MB["jackod"] == 5800
    assert MODEL_FOOTPRINT_MB["ornith"] == 6700
    assert MODEL_FOOTPRINT_MB["gemma-4"] == 16000
    assert MODEL_FOOTPRINT_MB["26b"] == 16000
    assert MODEL_FOOTPRINT_MB["bonsai"] == 6000
    # Familias retiradas 2026-10-01: ya no tienen clave propia.
    assert "minicpm5" not in MODEL_FOOTPRINT_MB
    assert "qwen3.8" not in MODEL_FOOTPRINT_MB


def test_unsloth_model_ids_resolve() -> None:
    """IDs largos de Unsloth matchean por substring (case-insensitive)."""
    from harness.model_router.vram_guard import footprint_mb

    assert footprint_mb("unsloth:unsloth/gemma-4-26B") == 16000
    assert footprint_mb("unsloth:qwen3.5-4b-UD-Q4_K_XL") == 3600
    assert footprint_mb("unsloth:ornith-1.5-9b") == 6700


def test_26b_never_fits_8gb() -> None:
    """Clase 26B (~16GB) jamas cabe en 8GB: el guard la bloquea siempre."""
    assert fits_in_vram(16000, free_mb=8188) is False
    assert fits_in_vram(16000, free_mb=8188, safety=1.0) is False


def test_fits_rejects_overload() -> None:
    """12.4GB necesarios en 8GB no caben (el escenario del OOM)."""
    assert fits_in_vram(12400, free_mb=8188) is False
    assert fits_in_vram(2700, free_mb=8188) is True


def test_fits_applies_safety_margin() -> None:
    """Margen de seguridad 0.85 por defecto."""
    assert fits_in_vram(7000, free_mb=8188) is False  # 7000 > 8188*0.85
    assert fits_in_vram(7000, free_mb=8188, safety=1.0) is True


def test_fits_invalid_raises() -> None:
    """Valores no positivos fallan accionable."""
    with pytest.raises(ValueError, match="WHAT"):
        fits_in_vram(0, free_mb=100)
    with pytest.raises(ValueError, match="WHAT"):
        fits_in_vram(100, free_mb=-5)


def test_free_vram_returns_none_without_gpu(monkeypatch) -> None:
    """Sin nvidia-smi retorna None (graceful, no crash)."""
    import shutil

    monkeypatch.setattr(shutil, "which", lambda _: None)
    assert free_vram_mb() is None


def test_keep_alive_for_tier() -> None:
    """El router expone keep_alive por tier (del YAML)."""
    from harness.model_router.ollama_tiers import (
        CapabilityTier,
        OllamaTierRouter,
    )

    router = OllamaTierRouter.load_from_yaml(
        __import__("pathlib").Path(".opencode/config/ollama_models.yaml")
    )
    assert router.keep_alive_for(CapabilityTier.FAST) == "0"
    assert router.keep_alive_for(CapabilityTier.QUALITY) == "0"
    assert router.keep_alive_for(CapabilityTier.CODING) == "0"


# ---------------------------------------------------------------------------
# Lectura multi-vendor (NVIDIA/AMD/Metal) — helper puro + despacho.
# ---------------------------------------------------------------------------


def _completed(stdout: str, returncode: int = 0) -> subprocess.CompletedProcess[str]:
    """CompletedProcess falso con stdout controlado (sin shell real).

    Args:
        stdout: Salida simulada del comando.
        returncode: Codigo de salida simulado.

    Returns:
        Proceso completado listo para inyectar como mock.
    """
    return subprocess.CompletedProcess([], returncode, stdout, "")


def _which_only(present: str):
    """Devuelve un ``shutil.which`` que solo reconoce un binario.

    Args:
        present: Binario que ``which`` debe resolver (los demas -> None).

    Returns:
        Callable compatible con ``shutil.which(name)``.
    """
    return lambda name: f"/usr/bin/{name}" if name == present else None


def test_parse_free_mb_nvidia_pure() -> None:
    """Formato NVIDIA: entero MiB por linea; toma el maximo (multi-GPU)."""
    assert _parse_free_mb("8188\n") == 8188
    assert _parse_free_mb("1000\n8188\n") == 8188
    assert _parse_free_mb("") is None
    assert _parse_free_mb("no gpu\n") is None


def test_parse_free_mb_rocm_pure() -> None:
    """Formato AMD: device,total_bytes,used_bytes -> libre = (total-usado)/MiB."""
    out = (
        "device,VRAM Total Memory (B),VRAM Total Used Memory (B)\n"
        "card0,8573157376,329121792\n"
    )
    assert _parse_free_mb(out) == (8573157376 - 329121792) // (1024 * 1024)


def test_free_vram_nvidia_smi_ok(monkeypatch: pytest.MonkeyPatch) -> None:
    """nvidia-smi presente -> parsea memory.free (MiB)."""
    monkeypatch.setattr(vram_guard.shutil, "which", _which_only("nvidia-smi"))
    calls: list[list[str]] = []

    def fake_run(cmd, **_kwargs):
        calls.append(cmd)
        return _completed("8188\n")

    monkeypatch.setattr(vram_guard.subprocess, "run", fake_run)
    assert free_vram_mb() == 8188
    assert calls[0][0] == "nvidia-smi"


def test_free_vram_rocm_smi_ok(monkeypatch: pytest.MonkeyPatch) -> None:
    """Sin nvidia-smi pero con rocm-smi -> parsea VRAM AMD."""
    monkeypatch.setattr(vram_guard.shutil, "which", _which_only("rocm-smi"))
    out = (
        "device,VRAM Total Memory (B),VRAM Total Used Memory (B)\n"
        "card0,8573157376,329121792\n"
    )
    monkeypatch.setattr(
        vram_guard.subprocess, "run", lambda cmd, **_kw: _completed(out)
    )
    assert free_vram_mb() == (8573157376 - 329121792) // (1024 * 1024)


def test_free_vram_none_when_no_tools(monkeypatch: pytest.MonkeyPatch) -> None:
    """Ni NVIDIA ni AMD ni CLI -> None (macOS/Metal, graceful)."""
    monkeypatch.setattr(vram_guard.shutil, "which", lambda _name: None)
    assert free_vram_mb() is None


def test_free_vram_none_when_command_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    """returncode != 0 -> None (no lanza, no inventa VRAM)."""
    monkeypatch.setattr(vram_guard.shutil, "which", _which_only("nvidia-smi"))
    monkeypatch.setattr(
        vram_guard.subprocess, "run", lambda cmd, **_kw: _completed("", returncode=1)
    )
    assert free_vram_mb() is None


def test_free_vram_command_error_returns_none(monkeypatch: pytest.MonkeyPatch) -> None:
    """OSError de subprocess -> None (binario desaparecio entre which y run)."""
    monkeypatch.setattr(vram_guard.shutil, "which", _which_only("nvidia-smi"))

    def boom(_cmd, **_kwargs):
        raise OSError("driver ausente")

    monkeypatch.setattr(vram_guard.subprocess, "run", boom)
    assert free_vram_mb() is None


def test_free_vram_env_override(monkeypatch: pytest.MonkeyPatch) -> None:
    """SWARMIND_VRAM_CMD fuerza el comando y evita el descubrimiento."""
    monkeypatch.setenv("SWARMIND_VRAM_CMD", "mytool --free")
    monkeypatch.setattr(
        vram_guard.shutil, "which",
        lambda _name: pytest.fail("no debe descubrir con override"),
    )
    calls: list[list[str]] = []

    def fake_run(cmd, **_kwargs):
        calls.append(cmd)
        return _completed("4096\n")

    monkeypatch.setattr(vram_guard.subprocess, "run", fake_run)
    assert free_vram_mb() == 4096
    assert calls == [["mytool", "--free"]]


def test_vram_guard_has_no_personal_path_literals() -> None:
    """Sin rutas personales hardcodeadas: portabilidad multi-OS."""
    source = Path(vram_guard.__file__).read_text(encoding="utf-8")
    for forbidden in ("C:\\Users", "C:/Users", "/home/", "USUARIO"):
        assert forbidden not in source
