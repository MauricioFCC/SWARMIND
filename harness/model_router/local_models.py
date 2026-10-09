"""local_models.py — SSOT y render de la flota de modelos locales.

WHAT: carga ``harness/model_router/local_models.yaml`` (SSOT versionada) en
dataclasses tipadas y renderiza los artefactos derivados: el YAML de
llama-swap y el cableado de provider/modelos de opencode. Las funciones de
render son puras (sin I/O); las de ``build/check/write_targets`` resuelven el
I/O de los destinos para el CLI.
WHY: la config de la flota vivia duplicada en cinco archivos
(``llama-swap.yaml``, ``.opencode/opencode.json``, ``~/.config/opencode/
opencode.jsonc``, ``fleet_manifest.py`` y ``.opencode/config/
ollama_models.yaml``); actualizar un modelo obligaba a editarlos todos a mano
y la deriva pasaba inadvertida. Una SSOT + generador idempotente la elimina.
WHERE: ``scripts/render_local_models.py`` (CLI) y su test
``harness/tests/test_render_local_models.py``.
"""

from __future__ import annotations

import copy
import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

#: Ruta por defecto de la SSOT (junto a este modulo).
SSOT_PATH = Path(__file__).resolve().parent / "local_models.yaml"

#: Cabecera del YAML de llama-swap generado (marca de artefacto derivado).
LLAMA_SWAP_HEADER = (
    "# GENERADO por scripts/render_local_models.py desde local_models.yaml.\n"
    "# NO editar a mano: editar la SSOT y regenerar (uv run python scripts/render_local_models.py)."
)
#: Valores fijos del proxy llama-swap.
HEALTH_CHECK_TIMEOUT = 300
LOG_LEVEL = "info"
INCLUDE_ALIASES_IN_LIST = True
#: Metadatos npm/servidor del provider local en la config de opencode.
OPENCODE_NPM = "@ai-sdk/openai-compatible"
OPENCODE_PROVIDER_NAME = "llama.cpp (llama-swap local :11434)"
#: Referencia simbolica al oraculo cloud en la SSOT de agentes.
CLOUD_ALIAS = "cloud_oracle"
#: Etiqueta de UI por rol de capacidad.
ROLE_LABELS: Mapping[str, str] = {
    "coding": "coding",
    "reasoning": "reasoning/general",
    "fast": "fast",
    "deep": "deep",
    "embedding": "embeddings/RAG",
}
#: Roles que opencode marca como reasoning.
REASONING_ROLES = frozenset({"reasoning", "fast", "deep"})
#: Roles que NO exponen tool-calling (embeddings).
TOOLLESS_ROLES = frozenset({"embedding"})
#: Techo VRAM total de la GPU (RTX 4060 8GB; anti-saturacion).
VRAM_BUDGET_MB = 8000
#: Techo seguro de contexto (40960 causo TDR VIDEO_TDR_FAILURE 0x116).
SAFE_CTX_MAX = 32768
#: Reserva fija para respuesta/sistema (ctx - reserved = max_prompt_tokens).
RESERVED_TOKENS = 2048
#: Concurrencia seriada (1 inferencia a la vez; 2 encolaba y saturaba).
EXPECTED_CONCURRENCY = 1
#: TTL maximo para liberar VRAM rapido (antes 300).
MAX_TTL_S = 180
#: Huella VRAM estimada por modelo (espejo de fleet_manifest/test_opencode).
FALLBACK_VRAM_MB: Mapping[str, int] = {
    "qwen2.5-coder-3b-iq4-xs": 3300,
    "phi-4-mini-instruct-q4-k-m": 5700,
    "qwen3-5-4b-gguf-ud-q4-k-xl": 4600,
    "deepseek-r1-distill-qwen-7b-q2-k": 4400,
    "qwen3-embedding-0-6b": 2100,
}


@dataclass(frozen=True)
class LocalBackend:
    """Backend local llama.cpp/llama-swap (rutas y puertos).

    Attributes:
        server_exe: Ruta al binario ``llama-server``.
        host: Host de escucha (loopback).
        port: Puerto del proxy OpenAI (llama-swap).
        swap_exe: Ruta al binario ``llama-swap``.
        swap_config: Ruta del YAML de config de llama-swap (destino del render).
        start_port: Puerto base para los ``llama-server`` hijos.
    """

    server_exe: str
    host: str
    port: int
    swap_exe: str
    swap_config: str
    start_port: int


@dataclass(frozen=True)
class LocalModel:
    """Un modelo de la flota local.

    Attributes:
        id: Nombre corto servido por llama-swap (canonico).
        file: Ruta absoluta al archivo ``.gguf``.
        ctx: Ventana de contexto real (``-c``).
        max_prompt_tokens: Techo de prompt (= ctx - reserved).
        flags: Referencia a una clave de ``flags`` (SAFE|SMALL).
        role: Rol de capacidad (coding|reasoning|fast|deep|embedding).
        aliases: Nombres alternos que llama-swap expone.
        opencode: True (default) para publicar en opencode; False = solo swap.
    """

    id: str
    file: str
    ctx: int
    flags: str
    role: str
    max_prompt_tokens: int = 0
    aliases: tuple[str, ...] = ()
    opencode: bool = True


@dataclass(frozen=True)
class OpencodeSSOT:
    """Cableado de opencode derivado de la SSOT.

    Attributes:
        provider: Id del provider local (p.ej. ``llamacpp``).
        base_url: Base URL OpenAI-compatible del proxy.
        model: Id del modelo por defecto (local, sin prefijo).
        small_model: Id del modelo pequeno (local, sin prefijo).
        cloud_oracle: Referencia completa del oraculo cloud.
        agents: Mapa agente -> id local o ``cloud_oracle``.
    """

    provider: str
    base_url: str
    model: str
    small_model: str
    cloud_oracle: str
    agents: Mapping[str, str]


@dataclass(frozen=True)
class LocalModelsConfig:
    """SSOT completa de la flota local.

    Attributes:
        backend: Backend local llama.cpp/llama-swap.
        flags: Mapa nombre -> cadena de flags de ``llama-server``.
        default_ctx: Contexto por defecto de la flota.
        default_ttl: TTL por defecto del proxy (segundos).
        concurrency_limit: Inferencias simultaneas (1 = seriado).
        safety_margin_mb: VRAM libre que debe quedar siempre.
        reserved_tokens: Reserva para respuesta (ctx - reserved = prompt).
        vram_budget_mb: Techo VRAM total de la GPU.
        safe_ctx_max: Techo seguro de contexto (anti-TDR).
        models: Modelos de la flota.
        opencode: Cableado de opencode.
    """

    backend: LocalBackend
    flags: Mapping[str, str]
    default_ctx: int
    default_ttl: int
    models: tuple[LocalModel, ...]
    opencode: OpencodeSSOT
    concurrency_limit: int = EXPECTED_CONCURRENCY
    safety_margin_mb: int = 1500
    reserved_tokens: int = RESERVED_TOKENS
    vram_budget_mb: int = VRAM_BUDGET_MB
    safe_ctx_max: int = SAFE_CTX_MAX


# ---------------------------------------------------------------------------
# Carga y validacion
# ---------------------------------------------------------------------------


def load_config(path: Path = SSOT_PATH) -> LocalModelsConfig:
    """Carga y valida la SSOT desde disco.

    Args:
        path: Ruta del YAML de la SSOT.

    Returns:
        La configuracion tipada y validada.

    Raises:
        TypeError: Si el documento de la SSOT no es un mapping.
        ValueError: Si el archivo no existe, no es YAML valido o viola las
            invariantes de la SSOT (WHAT+WHY+WHERE).
    """
    if not path.exists():
        raise ValueError(
            f"WHAT: SSOT ausente en {path}. "
            "WHY: sin local_models.yaml no hay fuente para renderizar. "
            f"WHERE: local_models.load_config ({path})"
        )
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise ValueError(
            f"WHAT: YAML invalido en {path} ({exc}). "
            "WHY: la SSOT debe parsear como mapping. "
            f"WHERE: local_models.load_config ({path})"
        ) from exc
    if not isinstance(raw, Mapping):
        raise TypeError(
            f"WHAT: la SSOT no es un mapping ({type(raw).__name__}). "
            "WHY: se esperaba un documento con backend/flags/models/opencode. "
            f"WHERE: local_models.load_config ({path})"
        )
    return validate_config(raw)


def validate_config(raw: Mapping[str, Any]) -> LocalModelsConfig:
    """Construye y valida la config desde el mapping crudo de la SSOT.

    Args:
        raw: Documento YAML ya parseado.

    Returns:
        La configuracion tipada y validada.

    Raises:
        ValueError: Si falta un campo, un ``flags`` referenciado no existe,
            un ``file`` esta vacio, hay ids duplicados o se viola el margen
            de seguridad VRAM/ctx (WHAT+WHY+WHERE).
    """
    backend = _parse_backend(_require_mapping(raw, "backend"))
    flags = _parse_flags(_require_mapping(raw, "flags"))
    reserved = _optional_int(raw, "reserved_tokens", RESERVED_TOKENS)
    budget = _optional_int(raw, "vram_budget_mb", VRAM_BUDGET_MB)
    safe_max = _optional_int(raw, "safe_ctx_max", SAFE_CTX_MAX)
    margin = _optional_int(raw, "safety_margin_mb", 1500)
    concurrency = _optional_int(raw, "concurrency_limit", EXPECTED_CONCURRENCY)
    default_ttl = _require_int(raw, "default_ttl")
    models = tuple(_parse_model(entry, flags, reserved) for entry in _require_sequence(raw, "models"))
    _check_unique_ids(models)
    _check_concurrency(concurrency)
    _check_ttl(default_ttl)
    _check_ctx_ceiling(models, safe_max)
    _check_prompt_window(models, reserved)
    _check_vram_safety(models, margin, budget)
    opencode = _parse_opencode(_require_mapping(raw, "opencode"), models)
    _check_agents_declared(opencode, models)
    _check_smallest_model(opencode, models)
    return LocalModelsConfig(
        backend=backend,
        flags=flags,
        default_ctx=_require_int(raw, "default_ctx"),
        default_ttl=default_ttl,
        models=models,
        opencode=opencode,
        concurrency_limit=concurrency,
        safety_margin_mb=margin,
        reserved_tokens=reserved,
        vram_budget_mb=budget,
        safe_ctx_max=safe_max,
    )


def _err(what: str, why: str) -> ValueError:
    """Construye un ValueError accionable (WHAT+WHY+WHERE)."""
    return ValueError(f"WHAT: {what}. WHY: {why}. WHERE: local_models.validate_config")


def _require_mapping(raw: Mapping[str, Any], key: str) -> Mapping[str, Any]:
    """Devuelve ``raw[key]`` como mapping o lanza (WHAT+WHY+WHERE)."""
    value = raw.get(key)
    if not isinstance(value, Mapping):
        raise _err(f"'{key}' ausente o no es mapping (got {type(value).__name__})", "estructura requerida")
    return value


def _require_sequence(raw: Mapping[str, Any], key: str) -> list[Any]:
    """Devuelve ``raw[key]`` como lista no vacia o lanza (WHAT+WHY+WHERE)."""
    value = raw.get(key)
    if not isinstance(value, (list, tuple)) or not value:
        raise _err(f"'{key}' ausente o vacio", "se requiere una lista no vacia")
    return list(value)


def _require_str(raw: Mapping[str, Any], key: str, context: str) -> str:
    """Devuelve ``raw[key]`` como string no vacio o lanza (WHAT+WHY+WHERE)."""
    value = raw.get(key)
    if not isinstance(value, str) or not value.strip():
        raise _err(f"'{key}' ausente o vacio en {context}", "campo obligatorio")
    return value


def _require_int(raw: Mapping[str, Any], key: str) -> int:
    """Devuelve ``raw[key]`` como entero positivo o lanza (WHAT+WHY+WHERE)."""
    value = raw.get(key)
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise _err(f"'{key}' invalido ({value!r})", "debe ser entero positivo")
    return value


def _optional_int(raw: Mapping[str, Any], key: str, default: int) -> int:
    """Devuelve ``raw[key]`` o el defecto si ausente (valida si presente)."""
    value = raw.get(key, default)
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise _err(f"'{key}' invalido ({value!r})", "debe ser entero positivo")
    return value


def _parse_backend(raw: Mapping[str, Any]) -> LocalBackend:
    """Parsea el bloque ``backend`` a ``LocalBackend``."""
    return LocalBackend(
        server_exe=_require_str(raw, "server_exe", "backend"),
        host=_require_str(raw, "host", "backend"),
        port=_require_int(raw, "port"),
        swap_exe=_require_str(raw, "swap_exe", "backend"),
        swap_config=_require_str(raw, "swap_config", "backend"),
        start_port=_require_int(raw, "start_port"),
    )


def _parse_flags(raw: Mapping[str, Any]) -> dict[str, str]:
    """Parsea el bloque ``flags`` (nombre -> cadena no vacia)."""
    flags: dict[str, str] = {}
    for name, value in raw.items():
        if not isinstance(value, str) or not value.strip():
            raise _err(f"flag '{name}' vacio", "cada flags debe ser string no vacio")
        flags[str(name)] = value
    return flags


def _parse_model(entry: Any, flags: Mapping[str, str], reserved: int = RESERVED_TOKENS) -> LocalModel:
    """Parsea una entrada de ``models`` y valida flags y ventana de prompt."""
    if not isinstance(entry, Mapping):
        raise _err(f"entrada de modelo invalida ({entry!r})", "cada modelo debe ser mapping")
    model_id = _require_str(entry, "id", "model")
    flags_ref = _require_str(entry, "flags", f"model {model_id}")
    if flags_ref not in flags:
        raise _err(
            f"flags '{flags_ref}' no definido (modelo {model_id})",
            "la referencia debe existir en 'flags'",
        )
    ctx_value = _require_int(entry, "ctx")
    prompt_max = _optional_int(entry, "max_prompt_tokens", ctx_value - reserved)
    return LocalModel(
        id=model_id,
        file=_require_str(entry, "file", f"model {model_id}"),
        ctx=ctx_value,
        flags=flags_ref,
        role=_require_str(entry, "role", f"model {model_id}"),
        max_prompt_tokens=prompt_max,
        aliases=_parse_aliases(entry),
        opencode=bool(entry.get("opencode", True)),
    )


def _parse_aliases(entry: Mapping[str, Any]) -> tuple[str, ...]:
    """Parsea ``aliases`` a tupla de strings (vacia si ausente/None)."""
    raw = entry.get("aliases", [])
    if raw is None:
        return ()
    if not isinstance(raw, (list, tuple)):
        raise _err(f"aliases no es lista ({raw!r})", "debe ser lista de strings")
    return tuple(str(item) for item in raw)


def _check_unique_ids(models: tuple[LocalModel, ...]) -> None:
    """Exige ids unicos en la flota (anti-colision de swap)."""
    seen: set[str] = set()
    for model in models:
        if model.id in seen:
            raise _err(f"id duplicado '{model.id}'", "los ids de la flota deben ser unicos")
        seen.add(model.id)


def _parse_opencode(raw: Mapping[str, Any], models: tuple[LocalModel, ...]) -> OpencodeSSOT:
    """Parsea el bloque ``opencode`` y valida sus referencias a la flota."""
    ids = {model.id for model in models}
    model_id = _require_str(raw, "model", "opencode")
    small_id = _require_str(raw, "small_model", "opencode")
    _check_flota_ref("model", model_id, ids)
    _check_flota_ref("small_model", small_id, ids)
    agents_raw = _require_mapping(raw, "agents")
    agents = {str(key): str(value) for key, value in agents_raw.items()}
    return OpencodeSSOT(
        provider=_require_str(raw, "provider", "opencode"),
        base_url=_require_str(raw, "base_url", "opencode"),
        model=model_id,
        small_model=small_id,
        cloud_oracle=_require_str(raw, "cloud_oracle", "opencode"),
        agents=agents,
    )


def _check_flota_ref(field: str, model_id: str, ids: set[str]) -> None:
    """Exige que ``opencode.<field>`` apunte a un modelo de la flota."""
    if model_id not in ids:
        raise _err(
            f"opencode.{field}={model_id!r} no esta en la flota",
            "debe apuntar a un modelo declarado",
        )


def footprint_mb(model_id: str) -> int | None:
    """Huella VRAM estimada de un modelo (fleet_manifest o fallback)."""
    try:
        from harness.model_router import fleet_manifest as _fleet
    except ImportError:
        _fleet = None  # type: ignore[assignment]
    if _fleet is not None:
        entry = _fleet.model_entry(model_id)
        if entry is not None:
            return int(entry.vram_mb)
    value = FALLBACK_VRAM_MB.get(model_id)
    return int(value) if value is not None else None


def _check_concurrency(concurrency: int) -> None:
    """Exige seriado (1 inferencia a la vez; anti-encolado)."""
    if concurrency != EXPECTED_CONCURRENCY:
        raise _err(
            f"concurrency_limit={concurrency} != {EXPECTED_CONCURRENCY}",
            "la flota va seriada en 8GB (2 encolaba y saturaba VRAM)",
        )


def _check_ttl(default_ttl: int) -> None:
    """Exige TTL corto para liberar VRAM rapido (<=180s)."""
    if default_ttl > MAX_TTL_S:
        raise _err(
            f"default_ttl={default_ttl} > {MAX_TTL_S}",
            "el TTL largo retiene VRAM y bloquea el swap",
        )


def _check_ctx_ceiling(models: tuple[LocalModel, ...], safe_max: int) -> None:
    """Rechaza ctx sobre el techo seguro (40960 causo TDR)."""
    for model in models:
        if model.ctx > safe_max:
            raise _err(
                f"ctx={model.ctx} > safe_ctx_max={safe_max} (modelo {model.id})",
                "subir el ctx dispara TDR en 8GB con WDDM",
            )


def _check_prompt_window(models: tuple[LocalModel, ...], reserved: int) -> None:
    """Exige prompt que quepa (ctx - reserved >= 1 y coherente)."""
    for model in models:
        usable = model.ctx - reserved
        if usable < 1:
            raise _err(
                f"ctx={model.ctx} - reserved={reserved} < 1 (modelo {model.id})",
                "el prompt debe caber en la ventana util",
            )
        if model.max_prompt_tokens != usable:
            raise _err(
                f"max_prompt_tokens={model.max_prompt_tokens} != {usable} (modelo {model.id})",
                "debe ser ctx - reserved_tokens para que el prompt quepa",
            )


def _check_vram_safety(models: tuple[LocalModel, ...], margin: int, budget: int) -> None:
    """Rechaza config insegura (huella + margen > presupuesto)."""
    for model in models:
        footprint = footprint_mb(model.id)
        if footprint is None:
            raise _err(
                f"modelo {model.id!r} sin huella VRAM conocida",
                "sin huella no se puede verificar el margen de seguridad",
            )
        if footprint + margin > budget:
            raise _err(
                f"huella={footprint} + margen={margin} > {budget} (modelo {model.id})",
                "la flota no puede saturar los 8GB ni con un modelo residente",
            )


def _check_agents_declared(oc: OpencodeSSOT, models: tuple[LocalModel, ...]) -> None:
    """Exige agentes locales sobre modelos declarados (u oraculo cloud)."""
    ids = {model.id for model in models}
    for name, ref in oc.agents.items():
        if ref in (CLOUD_ALIAS, oc.cloud_oracle):
            continue
        short = ref.split("/", 1)[-1] if "/" in ref else ref
        if short not in ids:
            raise _err(
                f"agent {name}={ref!r} no declarado",
                "los agentes locales deben apuntar a modelos de la flota",
            )


def _check_smallest_model(oc: OpencodeSSOT, models: tuple[LocalModel, ...]) -> None:
    """Exige small_model = el modelo chat mas pequeno (por VRAM)."""
    chats = [m for m in models if m.role not in TOOLLESS_ROLES and m.opencode]
    if not chats:
        return
    smallest = min(chats, key=lambda m: footprint_mb(m.id) or 10**9)
    if oc.small_model != smallest.id:
        raise _err(
            f"small_model={oc.small_model!r} != {smallest.id!r} (mas pequeno)",
            "small_model debe ser el chat mas pequeno para tareas simples",
        )


# ---------------------------------------------------------------------------
# Render
# ---------------------------------------------------------------------------


def render_llama_swap(config: LocalModelsConfig) -> str:
    """Renderiza el YAML de config de llama-swap desde la SSOT.

    Args:
        config: SSOT validada.

    Returns:
        Texto YAML completo (terminado en salto de linea) para llama-swap.
    """
    lines = [
        LLAMA_SWAP_HEADER,
        f"healthCheckTimeout: {HEALTH_CHECK_TIMEOUT}",
        f"logLevel: {LOG_LEVEL}",
        f"startPort: {config.backend.start_port}",
        f"includeAliasesInList: {str(INCLUDE_ALIASES_IN_LIST).lower()}",
        "models:",
    ]
    for model in config.models:
        lines.extend(_render_model_block(model, config))
    return "\n".join(lines) + "\n"


def _render_model_block(model: LocalModel, config: LocalModelsConfig) -> list[str]:
    """Bloque YAML (ttl/concurrencyLimit/aliases/cmd) de llama-swap."""
    cmd = (
        f'{config.backend.server_exe} -m "{model.file}" {config.flags[model.flags]} '
        f"-c {model.ctx} --host {config.backend.host} --port ${{PORT}}"
    )
    block = [
        f"  {model.id}:",
        f"    ttl: {config.default_ttl}",
        f"    concurrencyLimit: {config.concurrency_limit}",
        "    aliases:",
    ]
    block.extend(f'      - "{alias}"' for alias in model.aliases)
    block.extend(["    cmd: >-", f"      {cmd}"])
    return block


def render_opencode_provider(config: LocalModelsConfig) -> dict[str, Any]:
    """Renderiza el cableado de provider/modelos de opencode.

    Args:
        config: SSOT validada.

    Returns:
        Dict con ``provider``, ``base_url``, ``models`` (solo los expuestos),
        ``model``, ``small_model`` y ``agents`` (referencias resueltas).
    """
    oc = config.opencode
    models = {model.id: _opencode_model_entry(model) for model in config.models if model.opencode}
    agents = {name: _resolve_agent_ref(ref, oc) for name, ref in oc.agents.items()}
    return {
        "provider": oc.provider,
        "base_url": oc.base_url,
        "models": models,
        "model": _local_ref(oc.model, oc.provider),
        "small_model": _local_ref(oc.small_model, oc.provider),
        "agents": agents,
    }


def _opencode_model_entry(model: LocalModel) -> dict[str, Any]:
    """Entrada ``provider.<p>.models.<id>`` de opencode para un modelo local."""
    label = ROLE_LABELS.get(model.role, model.role)
    return {
        "name": f"{model.id} ({label})",
        "reasoning": model.role in REASONING_ROLES,
        "tools": model.role not in TOOLLESS_ROLES,
        "options": {"num_ctx": model.ctx},
    }


def _local_ref(model_id: str, provider: str) -> str:
    """Referencia ``provider/modelo`` (idempotente si ya trae prefijo)."""
    return model_id if "/" in model_id else f"{provider}/{model_id}"


def _resolve_agent_ref(ref: str, oc: OpencodeSSOT) -> str:
    """Resuelve la referencia de un agente (``cloud_oracle`` o id local)."""
    if ref in (CLOUD_ALIAS, oc.cloud_oracle):
        return oc.cloud_oracle
    return _local_ref(ref, oc.provider)


def merge_opencode_document(
    existing: Mapping[str, Any], rendered: Mapping[str, Any]
) -> dict[str, Any]:
    """Fusiona el render de opencode en un documento existente.

    Preserva todas las claves ajenas (skills, compaction, permisos de agentes).

    Args:
        existing: Documento de config actual (vacio si no existe).
        rendered: Resultado de ``render_opencode_provider``.

    Returns:
        Documento fusionado (copia nueva; no muta ``existing``).
    """
    document: dict[str, Any] = copy.deepcopy(existing) if existing else {}
    provider_id = str(rendered["provider"])
    entry = document.setdefault("provider", {}).setdefault(provider_id, {})
    entry["npm"] = OPENCODE_NPM
    entry["name"] = OPENCODE_PROVIDER_NAME
    entry.setdefault("options", {})["baseURL"] = rendered["base_url"]
    entry["models"] = rendered["models"]
    document["model"] = rendered["model"]
    document["small_model"] = rendered["small_model"]
    agents = document.setdefault("agent", {})
    for name, model_ref in rendered["agents"].items():
        agents.setdefault(name, {})["model"] = model_ref
    return document


def dump_opencode_document(document: Mapping[str, Any]) -> str:
    """Serializa un documento de opencode a JSON estable (indent=2).

    Args:
        document: Documento a serializar.

    Returns:
        Texto JSON terminado en salto de linea.
    """
    return json.dumps(document, indent=2, ensure_ascii=False) + "\n"


# ---------------------------------------------------------------------------
# Destinos (I/O de los artefactos derivados)
# ---------------------------------------------------------------------------


def build_targets(
    config: LocalModelsConfig, swap_path: Path, repo_path: Path, global_path: Path
) -> dict[Path, str]:
    """Resuelve el mapa ``destino -> contenido`` derivado de la SSOT.

    Args:
        config: SSOT validada.
        swap_path: Destino del YAML de llama-swap.
        repo_path: Destino del ``.opencode/opencode.json`` del repo.
        global_path: Destino del ``opencode.jsonc`` global del usuario.

    Returns:
        Dict ordenado destino -> texto esperado.
    """
    rendered = render_opencode_provider(config)
    return {
        swap_path: render_llama_swap(config),
        repo_path: _render_opencode_file(repo_path, rendered),
        global_path: _render_opencode_file(global_path, rendered),
    }


def _render_opencode_file(path: Path, rendered: Mapping[str, Any]) -> str:
    """Renderiza el documento de opencode fusionado con el archivo existente."""
    return dump_opencode_document(merge_opencode_document(_load_opencode_file(path), rendered))


def _load_opencode_file(path: Path) -> dict[str, Any]:
    """Carga un documento de opencode (``{}`` si no existe o no es JSON objeto).

    Raises:
        ValueError: Si el archivo existe pero no se puede leer (WHAT+WHY+WHERE).
    """
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ValueError(
            f"WHAT: no se pudo leer {path} ({exc}). "
            "WHY: la config de opencode debe ser JSON valido. "
            f"WHERE: local_models._load_opencode_file ({path})"
        ) from exc
    return data if isinstance(data, dict) else {}


def check_targets(targets: Mapping[Path, str]) -> list[str]:
    """Inconsistencias entre el render y disco (vacio = sincronizado).

    Args:
        targets: Mapa destino -> contenido esperado.

    Returns:
        Lista de mensajes ``AUSENTE``/``DESINCRONIZADO``; vacia si todo coincide.
    """
    mismatches: list[str] = []
    for path, expected in targets.items():
        if not path.exists():
            mismatches.append(f"AUSENTE: {path}")
            continue
        if path.read_text(encoding="utf-8") != expected:
            mismatches.append(f"DESINCRONIZADO: {path}")
    return mismatches


def write_targets(targets: Mapping[Path, str]) -> list[Path]:
    """Escribe los destinos (creando directorios padre) con fin de linea LF.

    Args:
        targets: Mapa destino -> contenido a escribir. El contenido debe usar
            ``\\n`` (se escribe con ``newline="\\n"`` para no introducir CRLF).

    Returns:
        Lista de rutas escritas, en orden de iteracion.
    """
    written: list[Path] = []
    for path, content in targets.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8", newline="\n")
        written.append(path)
    return written
