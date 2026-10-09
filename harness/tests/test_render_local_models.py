"""Tests del generador de la SSOT de modelos locales (ADR-0101 / local_models).

WHAT: cubre el render de llama-swap y de opencode, la idempotencia de
``build/check/write_targets`` (gate ``--check``) y la validacion de la SSOT
(flags referenciados, ``file`` no vacio e ids unicos).
WHY: sin estos tests, un render desincronizado o una SSOT invalida rompen el
routing local sin que ninguna suite lo note.
WHERE: ``harness/model_router/local_models.yaml`` +
``harness/model_router/local_models.py`` + ``scripts/render_local_models.py``.
"""

from __future__ import annotations

import copy
import dataclasses
from pathlib import Path
from typing import Any

import pytest
import yaml

from harness.model_router.local_models import (
    SSOT_PATH,
    build_targets,
    check_targets,
    load_config,
    merge_opencode_document,
    render_llama_swap,
    render_opencode_provider,
    validate_config,
    write_targets,
)


def _raw_ssot() -> dict[str, Any]:
    """Carga la SSOT cruda (mapping) para mutarla en tests adversariales.

    Returns:
        Documento YAML ya parseado (copia independiente en cada llamada).
    """
    raw = yaml.safe_load(SSOT_PATH.read_text(encoding="utf-8"))
    assert isinstance(raw, dict)
    return raw


# ---------------------------------------------------------------------------
# SSOT valida: flags referenciados, file no vacio, ids unicos
# ---------------------------------------------------------------------------


def test_ssot_is_valid_and_coherent() -> None:
    """La SSOT real carga y cumple las invariantes (flags/file/ids)."""
    config = load_config()

    assert config.models, "la flota no puede estar vacia"
    ids = [model.id for model in config.models]
    assert len(ids) == len(set(ids)), "ids duplicados"
    for model in config.models:
        assert model.flags in config.flags, f"{model.id}: flags '{model.flags}' inexistente"
        assert model.file.strip(), f"{model.id}: file vacio"
        assert model.ctx > 0, f"{model.id}: ctx no positivo"


def test_validate_rejects_unknown_flags_ref() -> None:
    """Un ``flags`` referenciado inexistente se rechaza (WHAT+WHY+WHERE)."""
    raw = _raw_ssot()
    raw["models"][0]["flags"] = "NOPE"

    with pytest.raises(ValueError, match="no definido"):
        validate_config(raw)


def test_validate_rejects_empty_file() -> None:
    """Un ``file`` vacio se rechaza (WHAT+WHY+WHERE)."""
    raw = _raw_ssot()
    raw["models"][0]["file"] = "   "

    with pytest.raises(ValueError, match="file"):
        validate_config(raw)


def test_validate_rejects_duplicate_ids() -> None:
    """Ids duplicados en la flota se rechazan (WHAT+WHY+WHERE)."""
    raw = _raw_ssot()
    raw["models"].append(copy.deepcopy(raw["models"][0]))

    with pytest.raises(ValueError, match="duplicado"):
        validate_config(raw)


# ---------------------------------------------------------------------------
# render_llama_swap
# ---------------------------------------------------------------------------


def test_render_llama_swap_contains_ids_flags_and_ctx() -> None:
    """El YAML de llama-swap tiene todos los ids con su flags y ctx correctos."""
    config = load_config()
    text = render_llama_swap(config)

    assert "models:" in text
    for model in config.models:
        assert f"  {model.id}:" in text, model.id
        assert f'"{model.file}"' in text, model.id
        assert config.flags[model.flags] in text, model.id
        assert f"-c {model.ctx}" in text, model.id
        assert "--port ${PORT}" in text, model.id


def test_render_llama_swap_contains_aliases() -> None:
    """Cada alias de la SSOT aparece citado en el YAML de llama-swap."""
    config = load_config()
    text = render_llama_swap(config)

    for model in config.models:
        for alias in model.aliases:
            assert f'      - "{alias}"' in text, f"{model.id}: {alias}"


# ---------------------------------------------------------------------------
# render_opencode_provider
# ---------------------------------------------------------------------------


def test_render_opencode_provider_is_coherent() -> None:
    """provider/models y model/small_model/agent reflejan la SSOT."""
    config = load_config()
    rendered = render_opencode_provider(config)
    exposed = {model.id for model in config.models if model.opencode}

    assert rendered["provider"] == config.opencode.provider
    assert rendered["base_url"] == config.opencode.base_url
    assert set(rendered["models"]) == exposed
    assert rendered["model"] == f"{config.opencode.provider}/{config.opencode.model}"
    assert rendered["small_model"] == f"{config.opencode.provider}/{config.opencode.small_model}"
    assert rendered["agents"]["coordinator"] == config.opencode.cloud_oracle
    for model in config.models:
        if model.opencode:
            assert rendered["models"][model.id]["options"]["num_ctx"] == model.ctx


def test_render_opencode_provider_excludes_non_exposed() -> None:
    """Un modelo con ``opencode: false`` no entra en provider.models."""
    config = load_config()
    # La SSOT real expone todos; sintetiza uno oculto para probar el mecanismo.
    hidden_id = config.models[0].id
    config = dataclasses.replace(
        config,
        models=tuple(
            dataclasses.replace(m, opencode=(m.id != hidden_id)) for m in config.models
        ),
    )
    rendered = render_opencode_provider(config)
    hidden = {model.id for model in config.models if not model.opencode}

    assert hidden == {hidden_id}
    assert hidden.isdisjoint(rendered["models"])


# ---------------------------------------------------------------------------
# Gate --check: idempotencia render == disco (tmp_path)
# ---------------------------------------------------------------------------


def _targets(config: Any, tmp_path: Path) -> dict[Path, str]:
    """Resuelve destinos temporales para el gate de idempotencia."""
    return build_targets(
        config,
        tmp_path / "llama-swap.yaml",
        tmp_path / "opencode.json",
        tmp_path / "global.jsonc",
    )


def test_check_is_idempotent_after_write(tmp_path: Path) -> None:
    """Tras escribir el render, ``check_targets`` reporta cero deriva."""
    config = load_config()
    targets = _targets(config, tmp_path)

    write_targets(targets)

    assert check_targets(targets) == []


def test_check_detects_drift(tmp_path: Path) -> None:
    """Una mutacion de disco es detectada por ``check_targets``."""
    config = load_config()
    targets = _targets(config, tmp_path)
    write_targets(targets)
    swap = tmp_path / "llama-swap.yaml"
    swap.write_text(swap.read_text(encoding="utf-8") + "# drift\n", encoding="utf-8")

    mismatches = check_targets(targets)

    assert mismatches
    assert any("DESINCRONIZADO" in message for message in mismatches)


# ---------------------------------------------------------------------------
# merge_opencode_document preserva claves ajenas
# ---------------------------------------------------------------------------


def test_merge_preserves_foreign_keys() -> None:
    """El merge de opencode preserva $schema/skills/permisos y setea modelos."""
    config = load_config()
    existing: dict[str, Any] = {
        "$schema": "https://opencode.ai/config.json",
        "skills": {"paths": [".opencode/skills"]},
        "agent": {"builder": {"mode": "subagent", "model": "viejo/modelo"}},
    }

    merged = merge_opencode_document(existing, render_opencode_provider(config))

    assert merged["$schema"] == "https://opencode.ai/config.json"
    assert merged["skills"] == {"paths": [".opencode/skills"]}
    assert merged["agent"]["builder"]["mode"] == "subagent"
    assert merged["agent"]["builder"]["model"].startswith(f"{config.opencode.provider}/")
