"""Runtime SSOT del tier frugal de edits (spec ``model-free-edits.md``).

Resuelve la **escalera frugal de OpenCode** para los edits y delegaciones que
no requieren razonamiento profundo, con precedencia:

1. env ``SWARMIND_EDITS_MODEL`` (id del modelo frugal, tier top).
2. SSOT ``.opencode/config/model_runtime.yaml`` (ladder + flag).
3. Constantes :data:`DEFAULT_EDITS_MODEL` / :data:`DEFAULT_FALLBACK_MODEL`.

El flag de routing frugal usa la misma precedencia con env
``SWARMIND_FRUGAL_ROUTING`` (``=0`` apaga, ``=1`` fuerza).

Prioridad de costo (N9): los models **gratis** van primero
(``free_models`` default + ``frugal_ladder.free``), despues los **de pago**
ordenados por la lista de pago del SSOT (la barata primero). El resolver la
valida, descarta ids malformados y devuelve una cadena de candidatos en
orden determinista.

Modulo puro: path + env + YAML; 0 red, 0 side-effects (N8).
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

from .edit_constants import (
    DEFAULT_EDITS_MODEL,
    DEFAULT_FALLBACK_MODEL,
    EDIT_AGENT_ID,
    EDIT_COMMAND_ID,
    ENV_EDITS_MODEL,
    ENV_FRUGAL_ROUTING,
    RUNTIME_YAML_RELPATH,
    YAML_DEFAULTS_BLOCK,
    YAML_KEY_AGENT_ID,
    YAML_KEY_COMMAND_ID,
    YAML_KEY_FALLBACK_MODEL,
    YAML_KEY_FREE,
    YAML_KEY_FRUGAL_ENABLED,
    YAML_KEY_PAID,
    YAML_LADDER_BLOCK,
)

ROOT = Path(__file__).resolve().parents[2]
RUNTIME_YAML_PATH = ROOT / RUNTIME_YAML_RELPATH

try:
    import yaml  # type: ignore[import-untyped]
except ImportError:  # pragma: no cover - yaml es base dep
    yaml = None  # type: ignore[assignment]

_TRUTHY = frozenset({"1", "true", "yes", "on"})
_FALSY = frozenset({"0", "false", "no", "off"})


@dataclass(frozen=True, slots=True)
class RuntimeEditTier:
    """Estado seteable del tier frugal (inmutable, sin Any).

    Attributes:
        free_models: Ids verificados gratuitos (prioridad 1, N9).
        paid_models: Ids de pago ordenados de la barata a la mas cara (N9).
        agent_id: Agente OpenCode del tier (`beam-patcher`).
        command_id: Comando OpenCode ligado (`/patch-free`).
        routing_enabled: True si el coordinador puede delegar frugal.
        fallback_model: Modelo default del proveedor (non-frugal).
    """

    free_models: tuple[str, ...] = field(default=())
    paid_models: tuple[str, ...] = field(default=())
    agent_id: str = EDIT_AGENT_ID
    command_id: str = EDIT_COMMAND_ID
    routing_enabled: bool = True
    fallback_model: str = ""


@dataclass(frozen=True, slots=True)
class EditLadder:
    """Cadena ordenada de candidatos: UNA lista determinista (N9).

    Attributes:
        primary: Primer id valido (el gratis si existe; de lo contrario
            la barata de pago; de lo contrario ``""``).
        candidates: Orden completo deduplicado y validado.
    """

    primary: str
    candidates: tuple[str, ...]


def model_id_is_valid(model_id: str) -> bool:
    """True si un ``provider/model`` esta bien formado (sin espacios)."""
    if not model_id or model_id.strip() != model_id:
        return False
    parts = model_id.split("/")
    return len(parts) == 2 and all(parts) and all(" " not in part for part in parts)


def _load_runtime_yaml(path: Path | None = None) -> dict[str, Any]:
    """Carga el SSOT runtime (``{}`` si falta o el YAML rompe)."""
    target = Path(path or RUNTIME_YAML_PATH)
    if yaml is None or not target.is_file():
        return {}
    try:
        payload = yaml.safe_load(target.read_text(encoding="utf-8")) or {}
    except (OSError, ValueError):
        return {}
    return payload if isinstance(payload, dict) else {}


@lru_cache(maxsize=1)
def yaml_parts(path: str | None = None) -> tuple[dict[str, Any], dict[str, Any]]:
    """Defaults y ladder del SSOT (memoized; override por test)."""
    data = _load_runtime_yaml(Path(path) if path else None)
    defaults = data.get(YAML_DEFAULTS_BLOCK)
    ladder = data.get(YAML_LADDER_BLOCK)
    return (
        defaults if isinstance(defaults, dict) else {},
        ladder if isinstance(ladder, dict) else {},
    )


def _env_flag(env: Mapping[str, str] | None, key: str) -> bool | None:
    """Convierte `SWARMIND_*` env en flag; None si unset o vacio."""
    source = env if env is not None else os.environ
    raw = source.get(key, "").strip().lower()
    if raw in _TRUTHY:
        return True
    if raw in _FALSY:
        return False
    return None


def frugal_enabled(
    env: Mapping[str, str] | None = None, yaml_path: str | None = None
) -> bool:
    """Env `SWARMIND_FRUGAL_ROUTING` > yaml > default ``True`` (ahorro GANADO)."""
    flag = _env_flag(env, ENV_FRUGAL_ROUTING)
    if flag is not None:
        return flag
    return bool(yaml_parts(yaml_path)[0].get(YAML_KEY_FRUGAL_ENABLED, True))


def _str_ids(raw: Any) -> tuple[str, ...]:
    """Lista de ids validos deduplicada (mantiene el orden del YAML)."""
    ids: list[str] = []
    if not isinstance(raw, list):
        return ()
    for raw_id in raw:
        candidate = str(raw_id or "").strip()
        if candidate and model_id_is_valid(candidate) and candidate not in ids:
            ids.append(candidate)
    return tuple(ids)


def resolve_edit_ladder(
    env: Mapping[str, str] | None = None, yaml_path: str | None = None
) -> EditLadder:
    """Candidates frugal en orden: gratis primero, pago despues (N9).

    Args:
        env: Mapping del entorno (tests puro sin mutar os.environ). Si la env
            ``SWARMIND_EDITS_MODEL`` trae un id valido, se pinta como
            **primary** (top de la escalera) conservando el resto.
        yaml_path: Override del SSOT yaml (tests hermeticos).

    Returns:
        :class:`EditLadder` con ``primary`` y ``candidates`` validados.
    """
    ordered = _ladder_order(yaml_path)
    if not ordered:
        return EditLadder(primary="", candidates=())
    override = _env_override(env)
    if override:
        rest = [candidate for candidate in ordered if candidate != override]
        return EditLadder(primary=override, candidates=(override, *rest))
    return EditLadder(primary=ordered[0], candidates=tuple(ordered))


def _ladder_order(yaml_path: str | None) -> list[str]:
    """Orden base de la escalera: gratis del yaml/default, luego pago."""
    defaults, ladder = yaml_parts(yaml_path)
    free = _str_ids(ladder.get(YAML_KEY_FREE))
    if not free:
        free = (DEFAULT_EDITS_MODEL,) if model_id_is_valid(DEFAULT_EDITS_MODEL) else ()
    paid = _str_ids(ladder.get(YAML_KEY_PAID))
    fallback = str(defaults.get(YAML_KEY_FALLBACK_MODEL, "") or "").strip()
    if fallback and model_id_is_valid(fallback) and fallback not in paid:
        paid = (*paid, fallback)
    if not paid and model_id_is_valid(DEFAULT_FALLBACK_MODEL):
        paid = (DEFAULT_FALLBACK_MODEL,)
    ordered: list[str] = []
    for candidate in (*free, *paid):
        if candidate not in ordered:
            ordered.append(candidate)
    return ordered


def _env_override(env: Mapping[str, str] | None) -> str | None:
    """Id valido de `SWARMIND_EDITS_MODEL`, None si unset o invalido."""
    source = env if env is not None else os.environ
    override = source.get(ENV_EDITS_MODEL, "").strip()
    if override and model_id_is_valid(override):
        return override
    return None


def resolve_edits_model(env=None, yaml_path: str | None = None) -> str:
    """Compat de SSOT: primer id valido de la escalera (gratis > pago)."""
    return resolve_edit_ladder(env=env, yaml_path=yaml_path).primary


def resolve_edit_tier(env=None, yaml_path: str | None = None) -> RuntimeEditTier:
    """Fachada frozen del tier completo (ladder+agent+cmd+flag)."""
    defaults, ladder = yaml_parts(yaml_path)
    free = _str_ids(ladder.get(YAML_KEY_FREE))
    if not free and model_id_is_valid(DEFAULT_EDITS_MODEL):
        free = (DEFAULT_EDITS_MODEL,)
    paid = [c for c in resolve_edit_ladder(env=env, yaml_path=yaml_path).candidates]
    return RuntimeEditTier(
        free_models=tuple(c for c in paid if c in free),
        paid_models=tuple(c for c in paid if c not in free),
        agent_id=str(defaults.get(YAML_KEY_AGENT_ID, EDIT_AGENT_ID)),
        command_id=str(defaults.get(YAML_KEY_COMMAND_ID, EDIT_COMMAND_ID)),
        routing_enabled=frugal_enabled(env=env, yaml_path=yaml_path),
        fallback_model=paid[0] if paid else "",
    )


def frugal_dispatch_model(
    task_text: str,
    *,
    is_deep_task: bool,
    env: Mapping[str, str] | None = None,
    yaml_path: str | None = None,
) -> str:
    """Id frugal para ``task_text``; ``""`` si no aplica (N9).

    Args:
        task_text: Descriptor; el caller YA clasifico la tarea.
        is_deep_task: True si el classify/`decide()` solto ``frontier``
            (tarea de razonamiento profundo; nunca frugal).
        env: Mapping del entorno (tests puros).
        yaml_path: Override del SSOT yaml.

    Returns:
        Primer id valido de la escalera (gratis primero) si el routing esta
        activo y la tarea no es profunda; ``""`` en otro caso.
    """
    if task_text.strip() == "":
        return ""
    if is_deep_task or not frugal_enabled(env=env, yaml_path=yaml_path):
        return ""
    return resolve_edit_ladder(env=env, yaml_path=yaml_path).primary
