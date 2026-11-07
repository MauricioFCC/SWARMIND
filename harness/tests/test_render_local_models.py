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
    _SAFE_CTX_MAX,
    SSOT_PATH,
    _local_ref,
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
    """providers/models y model/agents(title) reflejan la SSOT en forma V2."""
    config = load_config()
    rendered = render_opencode_provider(config)
    exposed = {model.id for model in config.models if model.opencode}

    assert rendered["provider_id"] == config.opencode.provider
    assert rendered["base_url"] == config.opencode.base_url
    assert set(rendered["models"]) == exposed
    assert rendered["model"] == _local_ref(config.opencode.model, config.opencode.provider)
    # small_model V2: el modelo del agente `title` (agents.title.model).
    assert rendered["agents"]["title"] == _local_ref(
        config.opencode.small_model, config.opencode.provider
    )
    assert rendered["agents"]["coordinator"] == config.opencode.cloud_oracle
    for model in config.models:
        if model.opencode:
            # El num_ctx publicado a opencode se capa a la ventana anti-TDR.
            entry = rendered["models"][model.id]
            assert entry["settings"]["num_ctx"] == min(model.ctx, _SAFE_CTX_MAX)
            # Limite de contexto real: sin el, OpenCode asume 200k y la
            # compactacion automatica nunca dispara en un modelo de 8k.
            assert entry["limit"]["context"] == min(model.ctx, _SAFE_CTX_MAX)


def test_model_entry_es_forma_nativa_v2() -> None:
    """Ninguna entrada de modelo usa claves V1 (reasoning/tools/options)."""
    config = load_config()
    rendered = render_opencode_provider(config)

    for name, entry in rendered["models"].items():
        legacy = {"reasoning", "tools", "options"} & set(entry)
        assert not legacy, f"{name}: claves V1 {sorted(legacy)}"
        assert isinstance(entry["capabilities"]["tools"], bool), name
        assert entry["capabilities"]["input"] == ["text"], name
        assert entry["capabilities"]["output"] == ["text"], name
        assert entry["limit"]["context"] > 0, name
        assert entry["settings"]["num_ctx"] > 0, name


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
# merge_opencode_document: migracion V1 -> V2 + preserva claves ajenas
# ---------------------------------------------------------------------------


def _doc_v1_ejemplo() -> dict[str, Any]:
    """Config V1 tipica (la forma que tenia el repo antes de la migracion)."""
    return {
        "$schema": "https://opencode.ai/config.json",
        "skills": {"paths": [".opencode/skills"]},
        "small_model": "llamacpp/mimo-v2-6-distill-qwen-9b-gguf-iq4-xs",
        "provider": {
            "llamacpp": {
                "npm": "@ai-sdk/openai-compatible",
                "name": "llama.cpp (llama-swap local :11434)",
                "options": {"baseURL": "http://127.0.0.1:11434/v1"},
                "models": {
                    "mimo": {
                        "name": "mimo",
                        "reasoning": True,
                        "tools": True,
                        "options": {"num_ctx": 8192},
                    }
                },
            }
        },
        "agent": {
            "coordinator": {
                "mode": "all",
                "model": "viejo/modelo",
                "permission": {
                    "task": {"*": "ask", "builder": "allow"},
                    "bash": "ask",
                },
            },
            "builder": {"mode": "subagent", "model": "viejo/modelo"},
            "ghost": {"mode": "subagent", "model": "fantasma/legacy"},
        },
    }


def test_merge_migra_config_v1_a_nativa_v2() -> None:
    """Un doc V1 existente sale del merge sin claves V1 y con forma V2."""
    config = load_config()

    merged = merge_opencode_document(_doc_v1_ejemplo(), render_opencode_provider(config))

    # V1 de nivel superior eliminada.
    assert "provider" not in merged
    assert "agent" not in merged
    assert "small_model" not in merged
    # providers nativo: package aisdk + settings.baseURL, sin npm/options.
    provider = merged["providers"]["llamacpp"]
    assert provider["package"].startswith("aisdk:"), provider.get("package")
    assert provider["settings"]["baseURL"] == "http://127.0.0.1:11434/v1"
    assert "npm" not in provider and "options" not in provider
    # Los modelos V1 se reemplazan por el render V2 (capabilities/limit).
    for entry in provider["models"].values():
        assert "reasoning" not in entry and "options" not in entry
        assert "capabilities" in entry and "limit" in entry
    # permissions lista con acciones V2 (bash->shell, task->subagent).
    perms = merged["agents"]["coordinator"]["permissions"]
    assert isinstance(perms, list) and perms
    actions = {r["action"] for r in perms}
    assert actions <= {"shell", "subagent", "edit"}, actions
    subagent = [r for r in perms if r["action"] == "subagent"]
    assert subagent[0] == {"action": "subagent", "resource": "*", "effect": "ask"}
    assert {"action": "subagent", "resource": "builder", "effect": "allow"} in subagent
    assert {"action": "shell", "resource": "*", "effect": "ask"} in perms
    # small_model nativo: agents.title.model.
    assert merged["agents"]["title"]["model"].endswith("mimo-v2-6-distill-qwen-9b-gguf-iq4-xs")


def test_migracion_v1_es_idempotente() -> None:
    """Migrar dos veces no cambia el resultado (IDP)."""
    from harness.model_router.local_models import migrate_opencode_v1_to_v2

    once = migrate_opencode_v1_to_v2(_doc_v1_ejemplo())
    twice = migrate_opencode_v1_to_v2(once)

    assert twice == once
    legacy = {"provider", "agent", "small_model"} & set(twice)
    assert legacy == set()


def test_merge_preserves_foreign_keys() -> None:
    """El merge migra a V2, actualiza agentes renderizados y preserva ajenos."""
    config = load_config()
    existing = _doc_v1_ejemplo()

    merged = merge_opencode_document(existing, render_opencode_provider(config))

    assert merged["$schema"] == "https://opencode.ai/config.json"
    # skills.paths V1 migra al array V2 (mapping oficial de la guia).
    assert merged["skills"] == [".opencode/skills"]
    # Claves renderizadas: builder ahora va al oraculo cloud (LOCAL SOLO
    # TRIVIAL); coordinator explicito al cloud_oracle.
    assert merged["agents"]["builder"]["mode"] == "subagent"
    assert merged["agents"]["builder"]["model"] == config.opencode.cloud_oracle
    assert merged["agents"]["coordinator"]["model"] == config.opencode.cloud_oracle
    # Clave ajena NO renderizada: se preserva intacta.
    assert merged["agents"]["ghost"] == {"mode": "subagent", "model": "fantasma/legacy"}
