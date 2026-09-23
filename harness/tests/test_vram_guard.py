"""Tests para vram_guard + keep_alive por tier (anti-OOM GPU).

Causa de 2 OOMs: keep_alive 5m en todos los tiers (Qwen3.8 5.8GB +
Qwopus 6.6GB residentes = 12.4GB > 8GB) + Unsloth concurrente. Fix:
vram_guard antes de ejecutar + keep_alive "0" (descarga inmediata)
en tiers grandes.
"""

import pytest

from harness.model_router.vram_guard import (
    MODEL_FOOTPRINT_MB,
    fits_in_vram,
    free_vram_mb,
)


def test_footprints_documented() -> None:
    """Footprints conocidos (MB en VRAM con Q4/Q8)."""
    assert MODEL_FOOTPRINT_MB["qwen3.8"] == 5800
    assert MODEL_FOOTPRINT_MB["qwopus"] == 6600
    assert MODEL_FOOTPRINT_MB["minicpm5"] == 2700


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
    assert router.keep_alive_for(CapabilityTier.FAST) == "5m"
    assert router.keep_alive_for(CapabilityTier.QUALITY) == "0"
    assert router.keep_alive_for(CapabilityTier.CODING) == "0"
