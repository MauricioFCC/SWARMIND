"""Invariantes de la SSOT de flota (specs/local-fleet-ssot.md).

TDD del delta: verifican que ventana y presupuesto DERIVEN del manifiesto
y que el cableado YAML no diverja. Cada test puede fallar si alguien
reintroduce una lista paralela (no son decorativos).
"""

from __future__ import annotations

from pathlib import Path

from harness.model_router.fleet_manifest import (
    FLEET,
    GPU_BUDGET_MB,
    YAML_TIERS,
    model_entry,
    tier_entry,
)
from harness.model_router.gpu_guard import SAFE_CTX_MAX
from harness.model_router.model_windows import recommend_num_ctx
from harness.model_router.vram_guard import footprint_mb

_CONFIG = (
    Path(__file__).resolve().parent.parent.parent
    / ".opencode" / "config" / "ollama_models.yaml"
)


def test_manifest_covers_yaml_tiers() -> None:
    """Todo tier del cableado YAML tiene entrada en el manifiesto (FR1)."""
    for tier in YAML_TIERS:
        entry = tier_entry(tier)
        assert entry is not None, f"tier sin manifiesto: {tier}"
        assert entry.num_ctx > 0
        assert entry.vram_mb > 0


def test_num_ctx_derives_from_manifest() -> None:
    """recommend_num_ctx devuelve el num_ctx del manifiesto (FR2)."""
    for entry in FLEET:
        assert recommend_num_ctx(entry.id) == entry.num_ctx, entry.id


def test_footprint_derives_from_manifest() -> None:
    """footprint_mb devuelve el vram_mb del manifiesto (FR2)."""
    for entry in FLEET:
        assert footprint_mb(entry.id) == entry.vram_mb, entry.id


def test_fleet_ctx_within_safe_ceiling() -> None:
    """Toda la flota respeta el techo anti-TDR de 8192 (post-BSOD 0x116).

    Los 9B (~6.6GB) declaran 4096 para dejar KV headroom en 8GB; el techo
    es un MAXIMO, no un objetivo.
    """
    for entry in FLEET:
        assert entry.num_ctx <= SAFE_CTX_MAX, entry.id
        assert recommend_num_ctx(entry.id) <= SAFE_CTX_MAX, entry.id


def test_windows_and_budget_fit_gpu() -> None:
    """Ventana y VRAM declaradas caben en el presupuesto de 8GB (NF / anti-OOM)."""
    for entry in FLEET:
        assert entry.num_ctx <= SAFE_CTX_MAX, entry.id
        assert entry.vram_mb <= GPU_BUDGET_MB, entry.id


def test_canonical_ids_resolve_to_their_entry() -> None:
    """Cada id canonico de la flota se resuelve a su propia entrada."""
    for entry in FLEET:
        assert model_entry(entry.id) is entry, entry.id


def test_retired_aliases_no_longer_resolve() -> None:
    """Los alias cortos retirados 2026-10-01 ya no matchean (evita deriva)."""
    for retired in ("qwopus-v3-9b-16k", "qwen38-9b-16k",
                    "opus-distill-9b-16k", "minicpm5-2b-32k"):
        assert model_entry(retired) is None, retired


def test_unknown_model_returns_none() -> None:
    """Un modelo ajeno a la flota no tiene entrada (fallback seguro)."""
    assert model_entry("algun-modelo-futuro:99b") is None


def test_yaml_models_match_manifest_ids() -> None:
    """Los ids del YAML de config coinciden con el manifiesto (sin deriva)."""
    text = _CONFIG.read_text(encoding="utf-8")
    for tier in YAML_TIERS:
        entry = tier_entry(tier)
        assert entry is not None
        assert entry.id in text, f"{tier}: {entry.id} ausente del YAML"
