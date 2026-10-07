"""Invariante de deriva declarado-vs-instalado (ADR-0101, specs/local-fleet-ssot.md).

Compara la flota DECLARADA (`fleet_manifest.FLEET` + tiers de
`.opencode/config/ollama_models.yaml`) con lo que Ollama tiene instalado
(`http://localhost:11434/v1/models`, API OpenAI-compatible). Objetivo: cazar en esta maquina los
modelos retirados que reaparecen, los instalados ajenos a la flota o los
tiers que se desdeclaran. No rompe CI: si Ollama no responde hace `skip`.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
import requests
import yaml

from harness.model_router.fleet_manifest import FLEET, FleetModel, model_entry
from harness.model_router.model_windows import recommend_num_ctx
from harness.model_router.vram_guard import footprint_mb

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
_CONFIG_YAML = _PROJECT_ROOT / ".opencode" / "config" / "ollama_models.yaml"
_OPENCODE_JSON = _PROJECT_ROOT / ".opencode" / "opencode.json"
_MODELS_URL = "http://localhost:11434/v1/models"
_TIMEOUT_SECONDS = 3

#: Familias retiradas 2026-09-30: no deben volver a estar instaladas.
_RETIRED = (
    "bonsai", "olmoe", "lfm2.5", "llama3.2", "qwen3:4b",
    "qwen2.5-coder", "deepseek-r1", "glm-z1", "deepseek-v4-flash",
)

#: Retirados 2026-10-01 (BSOD TDR): el coordinador borrara sus blobs DESPUES
#: de este cambio, asi que durante la transicion se toleran en `ollama list`
#: sin que el test de huerfanos falle. Una vez borrados, esta lista sobra.
_TRANSITIONAL: tuple[str, ...] = ()


def _is_transitional(name: str) -> bool:
    """True si el instalado es un retirado 2026-10-01 pendiente de borrado.

    Args:
        name: Nombre/tag instalado en Ollama.

    Returns:
        True si contiene alguna clave de `_TRANSITIONAL`.
    """
    lowered = name.lower()
    return any(key in lowered for key in _TRANSITIONAL)


def _fetch_installed() -> tuple[str, ...] | None:
    """Nombres instalados via /v1/models (None si Ollama no responde).

    Returns:
        Tupla de ids de modelo, o None si el daemon no esta disponible.
    """
    try:
        resp = requests.get(_MODELS_URL, timeout=_TIMEOUT_SECONDS)
        resp.raise_for_status()
        payload: dict[str, Any] = resp.json()
    except (requests.RequestException, ValueError):
        return None
    models = payload.get("data", [])
    return tuple(str(item.get("id", "")) for item in models if item.get("id"))


def _yaml_tiers() -> dict[str, dict[str, Any]]:
    """Tiers declarados en el YAML de config (model/auto_pull).

    Returns:
        Mapa tier -> definicion (vacio si el YAML no tiene `tiers`).
    """
    data = yaml.safe_load(_CONFIG_YAML.read_text(encoding="utf-8")) or {}
    tiers = data.get("ollama", {}).get("tiers", {})
    return tiers if isinstance(tiers, dict) else {}


def _declared_aliases() -> frozenset[str]:
    """Ids declarados en el `opencode.json` del repo (aliases de flota).

    Returns:
        Conjunto de ids de `provider.ollama.models`.
    """
    data: dict[str, Any] = json.loads(_OPENCODE_JSON.read_text(encoding="utf-8"))
    models = data.get("provider", {}).get("ollama", {}).get("models", {})
    return frozenset(models) if isinstance(models, dict) else frozenset()


@pytest.fixture(scope="module")
def installed_models() -> tuple[str, ...]:
    """Modelos instalados; `skip` si Ollama no esta disponible (CI)."""
    models = _fetch_installed()
    if models is None:
        pytest.skip("Ollama no disponible en http://localhost:11434")
    return models


@pytest.mark.local_only
def test_installed_models_belong_to_fleet(installed_models: tuple[str, ...]) -> None:
    """Todo modelo instalado pertenece a la flota o a un alias declarado."""
    aliases = _declared_aliases()
    orphans = [
        name for name in installed_models
        if model_entry(name) is None
        and name not in aliases
        and not _is_transitional(name)
    ]
    assert not orphans, f"instalados sin declarar: {orphans}"


@pytest.mark.local_only
def test_no_retired_models_installed(installed_models: tuple[str, ...]) -> None:
    """Ninguna familia retirada sigue instalada (deriva inversa)."""
    lowered = [name.lower() for name in installed_models]
    hits = [key for key in _RETIRED if any(key in name for name in lowered)]
    assert not hits, f"modelos retirados aun instalados: {hits}"


@pytest.mark.local_only
def test_declared_fleet_installed(installed_models: tuple[str, ...]) -> None:
    """Cada modelo de la flota declarada tiene un blob instalado.

    La familia se resuelve por `model_entry` (canonico o alias): si no hay
    ningun instalado que resuelva a la entrada, es deriva declarado-vs-real.
    """
    missing = [
        entry.id for entry in FLEET
        if not any(model_entry(name) is entry for name in installed_models)
    ]
    assert not missing, f"flota declarada sin instalar: {missing}"


def test_declared_tiers_resolve_to_fleet() -> None:
    """Cada tier declarado en el YAML resuelve a una entrada de flota."""
    unresolved = [
        str(tier["model"]) for tier in _yaml_tiers().values()
        if isinstance(tier, dict) and "model" in tier
        and model_entry(str(tier["model"])) is None
    ]
    assert not unresolved, f"tiers sin manifiesto: {unresolved}"


@pytest.mark.local_only
def test_installed_models_have_measured_window(installed_models: tuple[str, ...]) -> None:
    """Cada instalado declarado tiene ventana y VRAM coherentes (> 0)."""
    for name in installed_models:
        entry: FleetModel | None = model_entry(name)
        if entry is None:
            continue
        assert recommend_num_ctx(name) > 0, name
        assert footprint_mb(name) == entry.vram_mb, name
