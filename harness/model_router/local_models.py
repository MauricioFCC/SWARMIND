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

import json
import os
import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from harness.model_router.backend_config import GpuBudget, RamBudget

#: Ventana anti-TDR (SSOT `GpuBudget`). El `num_ctx` que se publica a opencode se
#: capa a este techo (lo que opencode SOLICITA); llama-swap conserva el ctx de la
#: SSOT (capacidad del server). WHY: el answer guard anti-TDR de deploy_all
#: bloquea re-propagar `num_ctx=16384` (BSOD 0x116); opencode nunca debe pedir
#: mas que la ventana segura. WHERE: local_models._opencode_model_entry.
_SAFE_CTX_MAX = GpuBudget().safe_ctx_max

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
#: Paquete del provider en forma NATIVA V2: V1 usaba ``npm`` sin prefijo; V2
#: exige ``package`` y las librerias AI SDK llevan el prefijo ``aisdk:``.
OPENCODE_PACKAGE = f"aisdk:{OPENCODE_NPM}"
OPENCODE_PROVIDER_NAME = "llama.cpp (llama-swap local :11434)"
#: Referencia simbolica al oraculo cloud en la SSOT de agentes.
CLOUD_ALIAS = "cloud_oracle"
#: Etiqueta de UI por rol de capacidad.
ROLE_LABELS: Mapping[str, str] = {
    "coding": "coding",
    "reasoning": "reasoning/general",
    "fast": "fast",
    "deep": "deep",
    "data": "data/signals",
    "embedding": "embeddings/RAG",
}
#: Roles que NO exponen tool-calling (embeddings).
TOOLLESS_ROLES = frozenset({"embedding"})
#: Techo VRAM total de la GPU (RTX 4060 8GB; anti-saturacion).
VRAM_BUDGET_MB = 8000
#: Techo de RAM del sistema (16GB fisicos - SO; anti-volcado/OOM).
RAM_BUDGET_MB = 14000
#: Techo seguro de contexto (40960 causo TDR; 36864 medido seguro en 8GB:
#: phi-4-mini 5948MiB, qwen3.5-4b 4925MiB, deepseek-7b 5223MiB, coder-3b 3707MiB).
SAFE_CTX_MAX = 36864
#: Techo de contexto con la KV cache en RAM (perfil CAPACITY, flag `-nkvo`).
#: Sin KV en VRAM el TDR por VRAM no aplica: el limite pasa a ser la RAM
#: (16 GB en esta maquina), no los 8 GB de la GPU.
SAFE_CTX_MAX_RAM_KV = 131072
#: Perfiles de flags que mueven la KV cache a RAM -> habilitan ctx mayor.
RAM_KV_FLAGS = frozenset({"CAPACITY"})
#: Reserva fija para respuesta/sistema (ctx - reserved = max_prompt_tokens).
RESERVED_TOKENS = 2048
#: Concurrencia seriada (1 inferencia a la vez; 2 encolaba y saturaba).
EXPECTED_CONCURRENCY = 1
#: TTL maximo para liberar VRAM rapido (antes 300).
MAX_TTL_S = 180
#: Huella VRAM estimada por modelo (espejo de fleet_manifest/test_opencode).
FALLBACK_VRAM_MB: Mapping[str, int] = {
    #: Con CAPACITY (-nkvo) la KV cache vive en RAM, no en VRAM: la huella de
    #: GPU es solo pesos + buffers de computo.
    "phi-4-mini-reasoning-q4-k-m": 2600,
    "qwen3-4b-thinking-2507-q4-k-m": 2600,
    "mimo-v2-6-distill-qwen-9b-gguf-iq4-xs": 6400,
    "qwen3-embedding-0-6b": 3800,
    #: Ternario 27B: 5700 MB MEDIDO con las flags reales de CAPACITY (-nkvo
    #: mueve la KV a RAM y baja la VRAM de 7789 a 5594 MB netos). 5700+1500 =
    #: 7200 <= 8000 -> CABE con 800 MB de colchon. Reproducir con
    #: CLI_TOOLS/verify_footprints.py (mide y compara declarado vs real).
    #: OJO: sin -nkvo el mismo modelo pide 7789 MB y NO cabe -> el guard lo
    #: rechaza, como debe.
    "ternary-bonsai-2-27b-ptq1-0": 5700,
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
        ram_mb: Huella de RAM del sistema (pesos + KV si CAPACITY) anti-OOM.
        flags: Referencia a una clave de ``flags`` (SAFE|SMALL|CAPACITY).
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
    ram_mb: int = 0
    aliases: tuple[str, ...] = ()
    #: Binario propio del modelo (opcional). Los pesos ternarios requieren el
    #: fork de PrismML; el resto usa el `backend.server_exe` por defecto.
    server_exe: str | None = None
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
    ram_budget_mb: int = RAM_BUDGET_MB


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
    ram = RamBudget.from_env()
    reserved = _optional_int(raw, "reserved_tokens", RESERVED_TOKENS)
    budget = _optional_int(raw, "vram_budget_mb", VRAM_BUDGET_MB)
    ram_budget = _optional_int(raw, "ram_budget_mb", ram.budget_mb)
    safe_max = _optional_int(raw, "safe_ctx_max", SAFE_CTX_MAX)
    margin = _optional_int(raw, "safety_margin_mb", ram.margin_mb)
    concurrency = _optional_int(raw, "concurrency_limit", EXPECTED_CONCURRENCY)
    default_ttl = _require_int(raw, "default_ttl")
    models = tuple(_parse_model(entry, flags, reserved) for entry in _require_sequence(raw, "models"))
    _check_unique_ids(models)
    _check_concurrency(concurrency)
    _check_ttl(default_ttl)
    _check_ctx_ceiling(models, safe_max, ram.safe_ctx_max_ram_kv)
    _check_prompt_window(models, reserved)
    _check_vram_safety(models, margin, budget)
    _check_ram_safety(models, margin, ram_budget)
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
        ram_budget_mb=ram_budget,
    )


def _err(what: str, why: str) -> ValueError:
    """Construye un ValueError accionable (WHAT+WHY+WHERE)."""
    return ValueError(f"WHAT: {what}. WHY: {why}. WHERE: local_models.validate_config")


#: Plantilla ``${VAR}`` aceptada en rutas de la SSOT (portable multi-SO).
_ENV_TEMPLATE_RE = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}")


def _expand_path(value: str, context: str) -> str:
    """Resuelve plantillas ``${VAR}`` de entorno en rutas de la SSOT.

    Permite una SSOT portable (Windows/macOS/Linux): se declara
    ``${SWARMIND_LLAMA_DIR}/bin/llama-server`` y cada maquina aporta su raiz
    via variable de entorno. Si la variable no esta definida, se conserva la
    plantilla literal (fail-soft: no rompe la carga sin env; el render queda
    pendiente de resolver en la maquina destino).

    Args:
        value: Valor crudo de la SSOT (puede contener ``${VAR}``).
        context: Contexto del campo (backend/model <id>) para errores.

    Returns:
        Ruta con las plantillas resueltas via ``os.environ``.
    """
    return _ENV_TEMPLATE_RE.sub(
        lambda m: os.getenv(m.group(1), m.group(0)), value
    )


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
        server_exe=_expand_path(_require_str(raw, "server_exe", "backend"), "backend"),
        host=_require_str(raw, "host", "backend"),
        port=_require_int(raw, "port"),
        swap_exe=_expand_path(_require_str(raw, "swap_exe", "backend"), "backend"),
        swap_config=_expand_path(_require_str(raw, "swap_config", "backend"), "backend"),
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
        file=_expand_path(_require_str(entry, "file", f"model {model_id}"), f"model {model_id}"),
        ctx=ctx_value,
        flags=flags_ref,
        role=_require_str(entry, "role", f"model {model_id}"),
        max_prompt_tokens=prompt_max,
        ram_mb=_optional_int(entry, "ram_mb", 0),
        aliases=_parse_aliases(entry),
        server_exe=_expand_path(str(entry["server_exe"]), f"model {model_id}")
        if entry.get("server_exe")
        else None,
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
    """Parsea el bloque ``opencode`` y valida sus referencias a la flota.

    ``model`` (default del runtime) puede ser el cloud_oracle (politica LOCAL
    TRIVIAL: el oraculo resuelve, el local atiende small_model); ``small_model``
    SIEMPRE debe ser un modelo local declarado.
    """
    ids = {model.id for model in models}
    cloud_oracle = _require_str(raw, "cloud_oracle", "opencode")
    model_id = _require_str(raw, "model", "opencode")
    small_id = _require_str(raw, "small_model", "opencode")
    if model_id != cloud_oracle:
        _check_flota_ref("model", model_id, ids)
    _check_flota_ref("small_model", small_id, ids)
    agents_raw = _require_mapping(raw, "agents")
    agents = {str(key): str(value) for key, value in agents_raw.items()}
    return OpencodeSSOT(
        provider=_require_str(raw, "provider", "opencode"),
        base_url=_require_str(raw, "base_url", "opencode"),
        model=model_id,
        small_model=small_id,
        cloud_oracle=cloud_oracle,
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


def _check_ctx_ceiling(models: tuple[LocalModel, ...], safe_max: int, safe_max_ram_kv: int) -> None:
    """Rechaza ctx sobre el techo seguro, segun DONDE vive la KV cache.

    WHY: el techo de 36864 existe porque la KV cache en VRAM dispara TDR en
    8 GB con WDDM (40960 lo causo). Los perfiles de `RAM_KV_FLAGS` mueven la
    KV a RAM con `-nkvo`: ahi ese limite no aplica, lo pone la RAM del equipo
    (`safe_max_ram_kv`, seteable por ``SWARMIND_SAFE_CTX_MAX_RAM_KV``).
    """
    for model in models:
        tope = safe_max_ram_kv if model.flags in RAM_KV_FLAGS else safe_max
        if model.ctx > tope:
            raise _err(
                f"ctx={model.ctx} > techo={tope} (modelo {model.id}, perfil {model.flags})",
                "el KV en VRAM dispara TDR en 8GB con WDDM; para contextos mayores "
                "usa el perfil CAPACITY (mueve el KV a RAM con -nkvo)",
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


def _check_ram_safety(models: tuple[LocalModel, ...], margin: int, budget: int) -> None:
    """Rechaza config que pueda volcar RAM (anti-OOM/cuelgue del sistema).

    Con CAPACITY (-nkvo) el KV cache vive en RAM del sistema: cada modelo debe
    declarar ``ram_mb`` (pesos + KV) y ``ram_mb + margen <= budget`` (16GB con
    margen). Un modelo sin ``ram_mb`` es rechazado (fail-fast: medir y declarar).
    """
    for model in models:
        if model.ram_mb <= 0:
            raise _err(
                f"modelo {model.id!r} sin huella RAM (ram_mb)",
                "con CAPACITY/-nkvo el KV vive en RAM; medir con bench_profiles "
                "y declarar ram_mb para verificar el margen anti-volcado",
            )
        if model.ram_mb + margin > budget:
            raise _err(
                f"ram_mb={model.ram_mb} + margen={margin} > {budget} "
                f"(modelo {model.id}, perfil {model.flags})",
                "el KV en RAM + pesos no debe arriesgar un volcado/OOM del sistema",
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
    """Exige small_model entre los chats locales (politica LOCAL TRIVIAL).

    Antes "el mas pequeno por VRAM"; ahora el adecuado para tareas triviales
    con calidad (benchmark data/signals: phi-4-mini gana al 3B). Cualquier
    chat local expuesto es valido; el oraculo cloud nunca es small_model.
    """
    chats = [m for m in models if m.role not in TOOLLESS_ROLES and m.opencode]
    if not chats:
        return
    if oc.small_model not in {m.id for m in chats}:
        raise _err(
            f"small_model={oc.small_model!r} no es un chat local {sorted(m.id for m in chats)}",
            "small_model debe ser un modelo local de chat (trivial); el oraculo no cuenta",
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
        f'{model.server_exe or config.backend.server_exe} -m "{model.file}" {config.flags[model.flags]} '
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
    """Renderiza el cableado de provider/modelos de opencode (forma V2).

    Args:
        config: SSOT validada.

    Returns:
        Dict con ``provider_id``, ``base_url``, ``models`` (solo los expuestos,
        forma nativa V2), ``model`` y ``agents`` (referencias resueltas; el
        modelo pequeno entra como ``title`` = ``agents.title.model`` V2, el
        reemplazo nativo del top-level ``small_model``).
    """
    oc = config.opencode
    models = {model.id: _opencode_model_entry(model) for model in config.models if model.opencode}
    agents = {name: _resolve_agent_ref(ref, oc) for name, ref in oc.agents.items()}
    agents["title"] = _local_ref(oc.small_model, oc.provider)
    return {
        "provider_id": oc.provider,
        "base_url": oc.base_url,
        "models": models,
        "model": _local_ref(oc.model, oc.provider),
        "agents": agents,
    }


def _opencode_model_entry(model: LocalModel) -> dict[str, Any]:
    """Entrada ``providers.<p>.models.<id>`` NATIVA V2 de un modelo local.

    V2 no acepta los campos V1 ``reasoning``/``tools``/``options`` (los ignora
    con warning). En su lugar: ``capabilities`` (tools/input/output),
    ``limit.context`` (sin el, OpenCode asume 200k y la compactacion automatica
    no dispara en modelos de 8k) y ``settings.num_ctx`` (mapping oficial
    ``options`` -> ``settings``; el ctx efectivo lo fija ademas llama-swap con
    ``-c`` en el server).

    Args:
        model: Modelo local de la SSOT.

    Returns:
        Entrada de modelo en forma V2.
    """
    label = ROLE_LABELS.get(model.role, model.role)
    ctx = min(model.ctx, _SAFE_CTX_MAX)
    return {
        "name": f"{model.id} ({label})",
        "capabilities": {
            "tools": model.role not in TOOLLESS_ROLES,
            "input": ["text"],
            "output": ["text"],
        },
        "limit": {"context": ctx},
        "settings": {"num_ctx": ctx},
    }


def _local_ref(model_id: str, provider: str) -> str:
    """Referencia ``provider/modelo`` (idempotente si ya trae prefijo)."""
    return model_id if "/" in model_id else f"{provider}/{model_id}"


def _resolve_agent_ref(ref: str, oc: OpencodeSSOT) -> str:
    """Resuelve la referencia de un agente (``cloud_oracle`` o id local)."""
    if ref in (CLOUD_ALIAS, oc.cloud_oracle):
        return oc.cloud_oracle
    return _local_ref(ref, oc.provider)


#: Acciones V1 de agentes -> acciones V2 (`bash`->`shell`, `task`->`subagent`).
_V1_ACTION_ALIASES: Mapping[str, str] = {
    "bash": "shell",
    "task": "subagent",
    "write": "edit",
    "patch": "edit",
}


def _permissions_from_v1(permission: Mapping[str, Any]) -> list[dict[str, str]]:
    """Convierte un mapa V1 ``permission`` a la lista ordenada V2.

    V1: ``{"bash": "ask", "task": {"*": "ask", "builder": "allow"}}``.
    V2: ``[{"action": "shell", "resource": "*", "effect": "ask"}, ...]``.

    El orden importa en V2 (ultima regla que matchea gana): el comodin ``*``
    se emite PRIMERO dentro de cada accion y las reglas especificas despues,
    replicando la prioridad del lookup exacto de V1.

    Args:
        permission: Mapa V1 de permisos de un agente.

    Returns:
        Lista de reglas V2 ``{action, resource, effect}``.
    """
    rules: list[dict[str, str]] = []
    for key, value in permission.items():
        action = _V1_ACTION_ALIASES.get(str(key), str(key))
        if isinstance(value, Mapping):
            ordered = sorted(
                ((str(res), str(eff)) for res, eff in value.items()),
                key=lambda kv: kv[0] != "*",
            )
            rules.extend(
                {"action": action, "resource": res, "effect": eff}
                for res, eff in ordered
            )
        else:
            rules.append({"action": action, "resource": "*", "effect": str(value)})
    return rules


def _model_entry_v1_to_v2(entry: Mapping[str, Any]) -> dict[str, Any]:
    """Convierte una entrada de modelo V1 (``reasoning``/``tools``/``options``)
    a la forma nativa V2 (``capabilities``/``limit``/``settings``).

    Args:
        entry: Entrada de modelo en forma V1.

    Returns:
        Entrada en forma V2 (campos desconocidos se conservan).
    """
    converted: dict[str, Any] = {
        k: v for k, v in entry.items() if k not in {"reasoning", "tools", "options"}
    }
    options = entry.get("options")
    num_ctx = options.get("num_ctx") if isinstance(options, Mapping) else None
    capabilities = dict(entry.get("capabilities") or {})
    capabilities.setdefault("tools", bool(entry.get("tools", True)))
    capabilities.setdefault("input", ["text"])
    capabilities.setdefault("output", ["text"])
    converted["capabilities"] = capabilities
    if isinstance(num_ctx, int):
        limit = dict(entry.get("limit") or {})
        limit.setdefault("context", num_ctx)
        converted["limit"] = limit
        settings = dict(entry.get("settings") or {})
        settings.setdefault("num_ctx", num_ctx)
        converted["settings"] = settings
    return converted


def _provider_entry_v1_to_v2(entry: Mapping[str, Any]) -> dict[str, Any]:
    """Convierte un provider V1 (``npm``/``options``/``models``) a forma V2.

    Args:
        entry: Entrada de provider en forma V1.

    Returns:
        Entrada V2 con ``package``/``settings``/``models`` convertidos.
    """
    converted: dict[str, Any] = {
        k: v for k, v in entry.items() if k not in {"npm", "options", "models"}
    }
    converted["package"] = str(entry.get("npm") or OPENCODE_PACKAGE)
    options = entry.get("options")
    if isinstance(options, Mapping):
        settings = dict(entry.get("settings") or {})
        settings.update({str(k): v for k, v in options.items()})
        converted["settings"] = settings
    models = entry.get("models")
    if isinstance(models, Mapping):
        converted["models"] = {
            str(name): _model_entry_v1_to_v2(model) if isinstance(model, Mapping) else model
            for name, model in models.items()
        }
    return converted


def migrate_opencode_v1_to_v2(document: Mapping[str, Any]) -> dict[str, Any]:
    """Normaliza un documento de config de opencode de V1 a la forma nativa V2.

    Mapea las claves V1 deprecadas segun la guia oficial de migracion:
    ``provider`` -> ``providers`` (``npm``->``package``, ``options``->
    ``settings``), ``agent`` -> ``agents``,
    ``permission`` (mapa) -> ``permissions`` (lista con acciones
    ``bash``->``shell``/``task``->``subagent``) y ``small_model`` top-level ->
    ``agents.title.model``. Si una clave V2 ya existe, PREVALECE sobre la V1
    (regla de precedencia del propio runtime) y las claves ajenas se
    preservan intactas. Idempotente: migrar dos veces no cambia el resultado.

    WHY: V2 acepta las claves V1 normalizandolas en memoria, pero varios
    campos se ignoran con warning y el operador cree que siguen activos;
    ademas ``nested mixing`` no se infiere dentro de entradas individuales.

    Args:
        document: Documento de config (V1, V2 o mixto).

    Returns:
        Documento en forma V2 (copia nueva; no muta ``document``).

    Raises:
        TypeError: Si ``document`` no es un mapping.
    """
    if not isinstance(document, Mapping):
        raise TypeError(
            f"WHAT: document tipo {type(document).__name__} no es mapping. "
            "WHY: migrate_opencode_v1_to_v2 espera un documento de config. "
            "WHERE: local_models.migrate_opencode_v1_to_v2."
        )
    doc: dict[str, Any] = dict(document)

    # 1) provider (V1) -> providers (V2); el bloque V2 ya existente gana.
    v1_provider = doc.pop("provider", None)
    if isinstance(v1_provider, Mapping):
        providers = {
            str(pid): _provider_entry_v1_to_v2(entry) if isinstance(entry, Mapping) else entry
            for pid, entry in v1_provider.items()
        }
        providers.update(doc.get("providers") or {})
        doc["providers"] = providers

    # 2) agent (V1) -> agents (V2) + permission (mapa) -> permissions (lista).
    v1_agents = doc.pop("agent", None)
    if isinstance(v1_agents, Mapping):
        agents: dict[str, Any] = {}
        for name, entry in v1_agents.items():
            converted: dict[str, Any] = dict(entry or {})
            permission = converted.pop("permission", None)
            if isinstance(permission, Mapping):
                converted["permissions"] = _permissions_from_v1(permission)
            agents[str(name)] = converted
        agents.update(doc.get("agents") or {})
        doc["agents"] = agents

    # 3) small_model (V1) -> agents.title.model (V2); el title V2 gana.
    small_model = doc.pop("small_model", None)
    if small_model and not (((doc.get("agents") or {}).get("title")) or {}).get("model"):
        agents_block = dict(doc.get("agents") or {})
        title = dict(agents_block.get("title") or {})
        title["model"] = small_model
        agents_block["title"] = title
        doc["agents"] = agents_block

    # 4) compaction V1 -> V2 (prune/tail_turns no tienen equivalente: se
    #    eliminan; reserved/preserve_recent_tokens -> buffer/keep.tokens).
    compaction = doc.get("compaction")
    if isinstance(compaction, Mapping):
        converted_compaction: dict[str, Any] = {
            k: v for k, v in compaction.items() if k not in {"prune", "tail_turns"}
        }
        keep = dict(converted_compaction.get("keep") or {})
        if "reserved" in compaction:
            converted_compaction["buffer"] = compaction["reserved"]
        if "preserve_recent_tokens" in compaction:
            keep.setdefault("tokens", compaction["preserve_recent_tokens"])
        if keep:
            converted_compaction["keep"] = keep
        doc["compaction"] = converted_compaction

    # 5) skills V1 {paths, urls} -> array V2 (solo si existe la forma V1).
    skills = doc.get("skills")
    if isinstance(skills, Mapping):
        combined = [str(p) for p in (skills.get("paths") or [])]
        combined += [str(u) for u in (skills.get("urls") or [])]
        doc["skills"] = combined

    return doc


def merge_opencode_document(
    existing: Mapping[str, Any], rendered: Mapping[str, Any]
) -> dict[str, Any]:
    """Fusiona el render de opencode en un documento existente (forma V2).

    Migra de paso cualquier clave V1 del documento existente a la forma nativa
    V2 (ver :func:`migrate_opencode_v1_to_v2`) y preserva todas las claves
    ajenas (skills, compaction, permisos de agentes).

    Args:
        existing: Documento de config actual (vacio si no existe).
        rendered: Resultado de ``render_opencode_provider``.

    Returns:
        Documento fusionado en forma V2 (copia nueva; no muta ``existing``).
    """
    document = migrate_opencode_v1_to_v2(existing)
    provider_id = str(rendered["provider_id"])
    providers = dict(document.get("providers") or {})
    entry = dict(providers.get(provider_id) or {})
    entry["package"] = OPENCODE_PACKAGE
    entry["name"] = OPENCODE_PROVIDER_NAME
    settings = dict(entry.get("settings") or {})
    settings["baseURL"] = rendered["base_url"]
    entry["settings"] = settings
    entry["models"] = rendered["models"]
    providers[provider_id] = entry
    document["providers"] = providers
    document["model"] = rendered["model"]
    agents = dict(document.get("agents") or {})
    for name, model_ref in rendered["agents"].items():
        agent_entry = dict(agents.get(name) or {})
        agent_entry["model"] = model_ref
        agents[name] = agent_entry
    document["agents"] = agents
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
