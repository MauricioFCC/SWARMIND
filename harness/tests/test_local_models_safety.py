"""Tests de seguridad de la flota local (margen VRAM + seriado).

WHAT: verifica que el render emite ``concurrencyLimit: 1`` y ``ttl`` por
    modelo, que un ``ctx`` sobre el techo seguro es rechazado y que el gate
    ``--check`` es idempotente (render == disco tras escribir).
WHY: sin estos gates la flota podria encolar inferencias, retener VRAM o
    pedir un ctx que dispara TDR en 8GB sin que ninguna suite lo note.
WHERE: ``harness/model_router/local_models.yaml`` +
    ``harness/model_router/local_models.py``.
"""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

import pytest
import yaml

from harness.model_router.local_models import (
    SSOT_PATH,
    build_targets,
    check_targets,
    load_config,
    render_llama_swap,
    validate_config,
    write_targets,
)


def _raw_ssot() -> dict[str, Any]:
    """Carga la SSOT cruda para mutarla en tests adversariales.

    Returns:
        Documento YAML ya parseado (copia independiente).
    """
    raw = yaml.safe_load(SSOT_PATH.read_text(encoding="utf-8"))
    assert isinstance(raw, dict)
    return copy.deepcopy(raw)


def test_render_emite_concurrency_y_ttl() -> None:
    """Cada bloque del render trae ``concurrencyLimit: 1`` y ``ttl``."""
    config = load_config()
    text = render_llama_swap(config)
    assert config.concurrency_limit == 1
    assert config.default_ttl == 180
    for model in config.models:
        assert f"  {model.id}:" in text
        assert "    concurrencyLimit: 1" in text
        assert f"    ttl: {config.default_ttl}" in text


def test_rechaza_ctx_sobre_techo_seguro() -> None:
    """Un ``ctx`` de 40960 (causo TDR) es rechazado con WHAT+WHY+WHERE."""
    raw = _raw_ssot()
    raw["models"][0]["ctx"] = 40960
    raw["models"][0]["max_prompt_tokens"] = 40960 - int(raw.get("reserved_tokens", 2048))
    with pytest.raises(ValueError, match="WHAT.*WHY.*WHERE"):
        validate_config(raw)


def test_rechaza_prompt_que_no_cabe() -> None:
    """``max_prompt_tokens`` incoherente con ``ctx - reserved`` se rechaza."""
    raw = _raw_ssot()
    raw["models"][0]["max_prompt_tokens"] = int(raw["models"][0]["ctx"]) + 1
    with pytest.raises(ValueError, match="WHAT.*WHY.*WHERE"):
        validate_config(raw)


def test_rechaza_vram_sin_margen() -> None:
    """Huella + margen sobre 8000MB no genera config insegura."""
    raw = _raw_ssot()
    raw["safety_margin_mb"] = 7900
    with pytest.raises(ValueError, match="WHAT.*WHY.*WHERE"):
        validate_config(raw)


def test_check_idempotente_tras_write(tmp_path: Path) -> None:
    """Tras escribir, ``check_targets`` reporta cero deriva (idempotente)."""
    config = load_config()
    targets = build_targets(
        config,
        tmp_path / "llama-swap.yaml",
        tmp_path / "opencode.json",
        tmp_path / "global.jsonc",
    )
    write_targets(targets)
    assert check_targets(targets) == []
    second = build_targets(
        config,
        tmp_path / "llama-swap.yaml",
        tmp_path / "opencode.json",
        tmp_path / "global.jsonc",
    )
    assert check_targets(second) == []
