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


def _capacity_model(raw: dict[str, Any]) -> dict[str, Any]:
    """Devuelve el primer modelo con perfil CAPACITY (KV en RAM)."""
    for model in raw["models"]:
        if model["flags"] == "CAPACITY":
            return model
    raise AssertionError("la SSOT debe declarar un modelo con perfil CAPACITY")


def test_permite_ctx_capacity_hasta_techo_ram() -> None:
    """Perfil CAPACITY (-nkvo, KV en RAM) admite ctx 131072 (techo RAM)."""
    raw = _raw_ssot()
    model = _capacity_model(raw)
    model["ctx"] = 131072
    model["max_prompt_tokens"] = 131072 - int(raw.get("reserved_tokens", 2048))
    validate_config(raw)  # no debe lanzar


def test_rechaza_ctx_capacity_sobre_techo_ram() -> None:
    """Perfil CAPACITY con ctx 131073 (sobre RAM KV) se rechaza."""
    raw = _raw_ssot()
    model = _capacity_model(raw)
    model["ctx"] = 131073
    model["max_prompt_tokens"] = 131073 - int(raw.get("reserved_tokens", 2048))
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


def test_rechaza_modelo_sin_huella_ram() -> None:
    """Un modelo sin ``ram_mb`` (KV en RAM no medido) se rechaza."""
    raw = _raw_ssot()
    raw["models"][0]["ram_mb"] = 0
    with pytest.raises(ValueError, match="ram_mb"):
        validate_config(raw)


def test_rechaza_ram_sobre_presupuesto() -> None:
    """``ram_mb + margen`` sobre el presupuesto RAM se rechaza (anti-volcado)."""
    raw = _raw_ssot()
    budget = int(raw.get("ram_budget_mb", 14000))
    raw["models"][0]["ram_mb"] = budget  # + margen => sobre techo
    with pytest.raises(ValueError, match="WHAT.*WHY.*WHERE"):
        validate_config(raw)


def test_permite_ram_con_margen() -> None:
    """``ram_mb + margen <= presupuesto`` genera config segura."""
    raw = _raw_ssot()
    budget = int(raw.get("ram_budget_mb", 14000))
    raw["models"][0]["ram_mb"] = budget - 1500 - 1  # 1MB dentro del margen
    validate_config(raw)  # no debe lanzar


def test_env_baja_presupuesto_ram_rechaza(monkeypatch) -> None:
    """``SWARMIND_RAM_BUDGET_MB`` bajo rechaza un ``ram_mb`` que antes cabia."""
    raw = _raw_ssot()
    budget = int(raw.get("ram_budget_mb", 14000))
    raw["models"][0]["ram_mb"] = budget - 1500 - 1  # valido por defecto
    validate_config(raw)  # baseline ok
    monkeypatch.setenv("SWARMIND_RAM_BUDGET_MB", str(budget - 5000))
    with pytest.raises(ValueError, match="WHAT.*WHY.*WHERE"):
        validate_config(raw)


def test_env_margin_alto_endurece(monkeypatch) -> None:
    """``SWARMIND_SAFETY_MARGIN_MB`` alto rechaza ``ram_mb`` que antes cabia."""
    raw = _raw_ssot()
    model = _capacity_model(raw)
    assert model["ram_mb"] + 1500 <= int(raw.get("ram_budget_mb", 14000))
    monkeypatch.setenv("SWARMIND_SAFETY_MARGIN_MB", "9000")
    with pytest.raises(ValueError, match="WHAT.*WHY.*WHERE"):
        validate_config(raw)


def test_env_baja_techo_ram_kv_rechaza(monkeypatch) -> None:
    """``SWARMIND_SAFE_CTX_MAX_RAM_KV`` bajo rechaza ctx que antes cabia."""
    raw = _raw_ssot()
    model = _capacity_model(raw)
    model["ctx"] = 131072
    model["max_prompt_tokens"] = 131072 - int(raw.get("reserved_tokens", 2048))
    validate_config(raw)  # baseline ok (techo default 131072)
    monkeypatch.setenv("SWARMIND_SAFE_CTX_MAX_RAM_KV", "65536")
    with pytest.raises(ValueError, match="WHAT.*WHY.*WHERE"):
        validate_config(raw)


def test_yaml_gana_sobre_env_ram(monkeypatch) -> None:
    """Un ``ram_budget_mb`` declarado en YAML prevalece sobre el env."""
    raw = _raw_ssot()
    raw["ram_budget_mb"] = 16000
    monkeypatch.setenv("SWARMIND_RAM_BUDGET_MB", "100")  # env restrictivo
    validate_config(raw)  # no debe lanzar: el YAML (16000) gana


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
