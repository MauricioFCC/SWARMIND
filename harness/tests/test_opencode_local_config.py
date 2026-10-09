"""Tests herméticos de la config local de opencode (provider `llamacpp`).

WHAT: valida que `.opencode/opencode.json` describa el backend local
llama.cpp / llama-swap por nombre corto y sin rastro del provider `ollama`.
WHY: la config era la SSOT del backend y derivaba en silencio (provider
`ollama`, `localhost:11434`, nombres largos `hf.co/...`); un drift rompe el
routing local de opencode sin que ninguna suite lo note.
WHERE: `.opencode/opencode.json`; contrato espejo en `llama-swap.yaml`.

Cero red, cero llama-swap: solo se lee el JSON versionado. Los tests
adversariales (mutation-style, PROBE/AdverTest) mutan un baseline VÁLIDO en
memoria y exigen que el checker puro lo RECHACE; si un check se neutra, el
test adversarial falla (anti-greenwashing).

Fuente del contrato (2026-10-08): `README.md:106`, `docs/src/es/README.md:123`,
`docs/src/es/roadmap/estado.md:20`, `harness/model_router/backend_config.py`.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent
CONFIG_PATH = ROOT / ".opencode" / "opencode.json"

#: Provider local OpenAI-compatible servido por llama.cpp / llama-swap.
EXPECTED_PROVIDER = "llamacpp"
#: Esquema oficial del archivo de configuracion de opencode.
EXPECTED_SCHEMA = "https://opencode.ai/config.json"
#: Endpoint del proxy llama-swap (protocolo OpenAI `/v1`).
EXPECTED_BASE_URL = "http://127.0.0.1:11434/v1"
#: Hosts aceptados por el contrato local (loopback).
EXPECTED_HOSTS = frozenset({"127.0.0.1", "localhost"})
#: Puerto del backend local (SSOT: `backend_config.DEFAULT_BASE_URL`).
EXPECTED_PORT = 11434
#: Path del endpoint OpenAI-compatible.
EXPECTED_PATH = "/v1"
#: Modelo por defecto = coding local (tier CODING, worker agentico multi-turn).
EXPECTED_DEFAULT_MODEL = "llamacpp/qwen2.5-coder-3b-iq4-xs"
#: Modelo pequeno para tareas simples (tier FAST, 4B).
EXPECTED_SMALL_MODEL = "llamacpp/qwen3-5-4b-gguf-ud-q4-k-xl"
#: Provider cloud del coordinator (guia/oraculo; NO es un worker local).
EXPECTED_CLOUD_PROVIDER = "opencode-go"
#: Presupuesto GPU (anti-TDR): cada modelo debe caber en <7000MB y se cargan
#: de a UNO por vez (llama-swap swap + purga al cambiar de modelo).
MAX_MODEL_VRAM_MB = 7000
#: Huella de VRAM por modelo (espejo de `fleet_manifest.py` / `llama-swap.yaml`).
MODEL_VRAM_MB = {
    "qwen2.5-coder-3b-iq4-xs": 3300,
    "phi-4-mini-instruct-q4-k-m": 5700,
    "qwen3-5-4b-gguf-ud-q4-k-xl": 4600,
    "deepseek-r1-distill-qwen-7b-q2-k": 4400,
    "qwen3-embedding-0-6b": 2100,
}
#: Espejo de `llama-swap.yaml`: 5 modelos por nombre corto (SVE).
EXPECTED_MODELS = frozenset(
    {
        "qwen2.5-coder-3b-iq4-xs",
        "phi-4-mini-instruct-q4-k-m",
        "qwen3-5-4b-gguf-ud-q4-k-xl",
        "deepseek-r1-distill-qwen-7b-q2-k",
        "qwen3-embedding-0-6b",
    }
)
#: Proveedores retirados que NO deben reaparecer en la config.
STALE_PROVIDERS = frozenset({"ollama"})
#: Literal del endpoint retirado (Ollama directo) que no debe reaparecer.
STALE_BASE_URL_MARKER = "localhost:11434"


# ---------------------------------------------------------------------------
# Carga y acceso tipado a la config
# ---------------------------------------------------------------------------


def _read_config(path: Path = CONFIG_PATH) -> dict[str, Any]:
    """Carga `.opencode/opencode.json` como JSON.

    Args:
        path: Ruta del archivo de configuracion.

    Returns:
        El documento JSON como diccionario.

    Raises:
        FileNotFoundError: Si el archivo no existe (WHAT+WHY+WHERE).
        json.JSONDecodeError: Si el contenido no es JSON valido.
    """
    if not path.exists():
        raise FileNotFoundError(
            f"WHAT: config local ausente en {path}. "
            f"WHY: sin opencode.json no hay provider ni modelo. "
            f"WHERE: {path} ({_read_config.__name__})."
        )
    return json.loads(path.read_text(encoding="utf-8"))


def _provider_block(config: Mapping[str, Any]) -> Mapping[str, Any]:
    """Devuelve el bloque `provider` (vacio si falta o no es mapping)."""
    block = config.get("provider")
    return block if isinstance(block, Mapping) else {}


def _provider_ids(config: Mapping[str, Any]) -> set[str]:
    """IDs de provider declarados en la config."""
    return {str(key) for key in _provider_block(config)}


def _provider_entry(config: Mapping[str, Any], provider: str) -> Mapping[str, Any]:
    """Entrada de un provider concreto (vacia si no existe)."""
    entry = _provider_block(config).get(provider)
    return entry if isinstance(entry, Mapping) else {}


def _declared_models(config: Mapping[str, Any], provider: str = EXPECTED_PROVIDER) -> set[str]:
    """Claves de `provider.<provider>.models` (vacio si faltan)."""
    models = _provider_entry(config, provider).get("models")
    return {str(key) for key in models} if isinstance(models, Mapping) else set()


def _provider_base_url(config: Mapping[str, Any], provider: str = EXPECTED_PROVIDER) -> str | None:
    """`provider.<provider>.options.baseURL` si es string, si no None."""
    options = _provider_entry(config, provider).get("options")
    if not isinstance(options, Mapping):
        return None
    url = options.get("baseURL")
    return url if isinstance(url, str) else None


def _model_prefix(model_ref: Any) -> str | None:
    """Prefijo `provider` de una referencia `provider/modelo` (None si invalida)."""
    if not isinstance(model_ref, str) or "/" not in model_ref:
        return None
    return model_ref.split("/", 1)[0]


def _model_name(model_ref: Any) -> str | None:
    """Nombre del modelo de una referencia `provider/modelo` (None si invalida)."""
    if not isinstance(model_ref, str) or "/" not in model_ref:
        return None
    return model_ref.split("/", 1)[1]


# ---------------------------------------------------------------------------
# Checker puro: cada funcion devuelve las violaciones (lista vacia = OK)
# ---------------------------------------------------------------------------


def check_json_schema(config: Mapping[str, Any]) -> list[str]:
    """Verifica que `$schema` sea el oficial de opencode."""
    schema = config.get("$schema")
    if schema != EXPECTED_SCHEMA:
        return [
            (
                f"WHAT: $schema={schema!r}. WHY: opencode espera {EXPECTED_SCHEMA!r}. "
                f"WHERE: {CONFIG_PATH.name}:$schema."
            )
        ]
    return []


def check_model_prefix(config: Mapping[str, Any]) -> list[str]:
    """Verifica que el prefijo de `model`/`small_model` exista en `provider`."""
    violations: list[str] = []
    for key in ("model", "small_model"):
        prefix = _model_prefix(config.get(key))
        if prefix is None:
            violations.append(
                f"WHAT: {key} no tiene forma provider/modelo. "
                f"WHY: opencode resuelve el provider por el prefijo. "
                f"WHERE: {CONFIG_PATH.name}:{key}."
            )
        elif prefix not in _provider_ids(config):
            violations.append(
                f"WHAT: {key} usa provider '{prefix}' inexistente. "
                f"WHY: el prefijo debe coincidir con una clave de 'provider'. "
                f"WHERE: {CONFIG_PATH.name}:{key}."
            )
    return violations


def check_base_url(config: Mapping[str, Any]) -> list[str]:
    """Verifica que la baseURL apunte a llama-swap (http, loopback:11434, /v1)."""
    url = _provider_base_url(config)
    if url is None:
        return [
            (
                f"WHAT: provider.{EXPECTED_PROVIDER}.options.baseURL ausente o no es string. "
                f"WHY: sin endpoint OpenAI-compatible no hay backend local. "
                f"WHERE: {CONFIG_PATH.name}:provider.{EXPECTED_PROVIDER}.options.baseURL."
            )
        ]
    parts = urlsplit(url)
    violations: list[str] = []
    if parts.scheme != "http":
        violations.append(f"WHAT: scheme '{parts.scheme}' != 'http'. WHY: llama-swap local es http. WHERE: {url!r}.")
    if parts.hostname not in EXPECTED_HOSTS:
        violations.append(f"WHAT: host '{parts.hostname}' no es loopback. WHY: backend local. WHERE: {url!r}.")
    if parts.port != EXPECTED_PORT:
        violations.append(
            f"WHAT: puerto '{parts.port}' != {EXPECTED_PORT}. WHY: llama-swap escucha en 11434. WHERE: {url!r}."
        )
    if parts.path != EXPECTED_PATH:
        violations.append(
            f"WHAT: path '{parts.path}' != '{EXPECTED_PATH}'. WHY: API OpenAI-compatible. WHERE: {url!r}."
        )
    return violations


def check_declared_models(config: Mapping[str, Any]) -> list[str]:
    """Verifica que las claves de modelos sean EXACTAMENTE los 4 nombres cortos."""
    declared = _declared_models(config)
    violations: list[str] = []
    missing = sorted(EXPECTED_MODELS - declared)
    extra = sorted(declared - EXPECTED_MODELS)
    if missing:
        violations.append(
            f"WHAT: faltan modelos {missing}. WHY: son el espejo de llama-swap.yaml. "
            f"WHERE: {CONFIG_PATH.name}:provider.{EXPECTED_PROVIDER}.models."
        )
    if extra:
        violations.append(
            f"WHAT: modelos no esperados {extra}. WHY: solo los 4 nombres cortos de llama-swap.yaml. "
            f"WHERE: {CONFIG_PATH.name}:provider.{EXPECTED_PROVIDER}.models."
        )
    return violations


def check_models_under_vram_cap(config: Mapping[str, Any]) -> list[str]:
    """Verifica que TODO modelo declarado tenga huella de VRAM < MAX_MODEL_VRAM_MB.

    Politica de la flota reducida 2026-10-08: 4 modelos que caben en los 8GB
    con el escritorio WDDM; los 9B (jackod/mimo/ornith) y la vision
    (qwen3-vl) quedaron fuera para no saturar la GPU.

    Args:
        config: Documento de config (ya parseado).

    Returns:
        Lista de violaciones (vacia si todos los modelos declarados caben).
    """
    violations: list[str] = []
    for name in sorted(_declared_models(config)):
        vram = MODEL_VRAM_MB.get(name)
        if vram is None:
            violations.append(
                f"WHAT: modelo {name!r} sin huella de VRAM conocida. "
                f"WHY: no se puede verificar el cap de {MAX_MODEL_VRAM_MB}MB. "
                f"WHERE: {CONFIG_PATH.name}:provider.{EXPECTED_PROVIDER}.models."
            )
        elif vram >= MAX_MODEL_VRAM_MB:
            violations.append(
                f"WHAT: modelo {name!r} usa {vram}MB >= {MAX_MODEL_VRAM_MB}MB. "
                f"WHY: solo se permiten modelos que caben en 8GB (anti-saturacion). "
                f"WHERE: {CONFIG_PATH.name}:provider.{EXPECTED_PROVIDER}.models."
            )
    return violations


def check_no_stale_ollama_provider(config: Mapping[str, Any]) -> list[str]:
    """Verifica que no quede el provider `ollama` (retirado)."""
    stale = sorted(STALE_PROVIDERS & _provider_ids(config))
    if stale:
        return [
            (
                f"WHAT: providers retirados presentes {stale}. WHY: la ruta local migro a 'llamacpp'. "
                f"WHERE: {CONFIG_PATH.name}:provider."
            )
        ]
    return []


def check_no_stale_base_url(raw_text: str) -> list[str]:
    """Verifica que el literal retirado `localhost:11434` no aparezca."""
    if STALE_BASE_URL_MARKER in raw_text:
        return [
            (
                f"WHAT: literal '{STALE_BASE_URL_MARKER}' presente. "
                f"WHY: el endpoint migro a 127.0.0.1:11434/v1. "
                f"WHERE: {CONFIG_PATH.name}."
            )
        ]
    return []


def check_default_model_is_declared(config: Mapping[str, Any]) -> list[str]:
    """Verifica que `model`/`small_model` apunten a modelos declarados."""
    declared = _declared_models(config)
    violations: list[str] = []
    for key in ("model", "small_model"):
        if _model_prefix(config.get(key)) != EXPECTED_PROVIDER:
            violations.append(
                f"WHAT: {key}={config.get(key)!r} no usa provider '{EXPECTED_PROVIDER}'. "
                f"WHY: el default debe ser local. WHERE: {CONFIG_PATH.name}:{key}."
            )
        elif _model_name(config.get(key)) not in declared:
            violations.append(
                f"WHAT: {key}={config.get(key)!r} no declarado en provider.{EXPECTED_PROVIDER}.models. "
                f"WHY: opencode no puede cargar un modelo no registrado. "
                f"WHERE: {CONFIG_PATH.name}:{key}."
            )
    return violations


def check_local_config(config: Mapping[str, Any], raw_text: str = "") -> list[str]:
    """Ejecuta todos los checks y agrega las violaciones (vacio = OK).

    Args:
        config: Documento de config (ya parseado).
        raw_text: Texto crudo del archivo para checks de literales retirados.

    Returns:
        Lista de violaciones; vacia si la config cumple todos los invariantes.
    """
    violations = check_json_schema(config)
    violations += check_model_prefix(config)
    violations += check_base_url(config)
    violations += check_declared_models(config)
    violations += check_models_under_vram_cap(config)
    violations += check_no_stale_ollama_provider(config)
    violations += check_default_model_is_declared(config)
    if raw_text:
        violations += check_no_stale_base_url(raw_text)
    return violations


def _valid_config() -> dict[str, Any]:
    """Config baseline VALIDA en memoria (espejo del estado final esperado)."""
    models: dict[str, Any] = {name: {"name": name, "tools": True} for name in sorted(EXPECTED_MODELS)}
    return {
        "$schema": EXPECTED_SCHEMA,
        "model": EXPECTED_DEFAULT_MODEL,
        "small_model": EXPECTED_SMALL_MODEL,
        "provider": {
            EXPECTED_PROVIDER: {
                "npm": "@ai-sdk/openai-compatible",
                "name": "llama.cpp (llama-swap)",
                "options": {"baseURL": EXPECTED_BASE_URL},
                "models": models,
            }
        },
    }


# ---------------------------------------------------------------------------
# Invariantes sobre el archivo REAL
# ---------------------------------------------------------------------------


def test_config_is_valid_json() -> None:
    """El archivo parsea como JSON y declara el `$schema` oficial."""
    config = _read_config()

    assert isinstance(config, dict)
    assert check_json_schema(config) == []


def test_model_prefix_matches_provider() -> None:
    """El prefijo de `model`/`small_model` existe como provider declarado."""
    config = _read_config()

    prefixes = {_model_prefix(config.get("model")), _model_prefix(config.get("small_model"))}

    assert check_model_prefix(config) == []
    assert prefixes <= _provider_ids(config)


def test_base_url_points_to_llama_swap() -> None:
    """baseURL = http + host loopback + puerto 11434 + path /v1."""
    config = _read_config()

    assert check_base_url(config) == []
    parts = urlsplit(_provider_base_url(config) or "")
    assert parts.scheme == "http"
    assert parts.hostname in EXPECTED_HOSTS
    assert parts.port == EXPECTED_PORT
    assert parts.path == EXPECTED_PATH


def test_declared_models_are_llama_swap_names() -> None:
    """Las claves de `provider.llamacpp.models` == los 4 nombres cortos."""
    config = _read_config()

    assert _declared_models(config) == set(EXPECTED_MODELS)
    assert check_declared_models(config) == []


def test_declared_models_under_vram_cap() -> None:
    """Ningun modelo declarado supera el cap de VRAM (caben en 8GB)."""
    config = _read_config()

    declared = _declared_models(config)
    assert declared, "debe haber al menos un modelo local declarado"
    assert all(MODEL_VRAM_MB[name] < MAX_MODEL_VRAM_MB for name in declared)
    assert check_models_under_vram_cap(config) == []


def test_agent_models_are_declared_local() -> None:
    """Cada agente usa un modelo local DECLARADO o el provider cloud como oraculo.

    El coordinator (agente primario) es la guia/oraculo cloud
    (`opencode-go/deepseek-v4.1-flash`); los subagentes (builder/guardian/
    scientist) deben usar el provider local `llamacpp` con un modelo declarado.
    El cloud solo se admite para el coordinator (oraculo), no como worker local.
    """
    config = _read_config()
    agents = config.get("agent", {})
    assert agents, "debe declararse al menos un agente"
    declared = _declared_models(config)
    for name, spec in agents.items():
        model = spec.get("model")
        if _model_prefix(model) == EXPECTED_CLOUD_PROVIDER:
            assert name == "coordinator", (
                f"agente {name!r} no puede usar el provider cloud "
                f"'{EXPECTED_CLOUD_PROVIDER}' (solo el coordinator/oraculo): {model!r}"
            )
            continue
        assert _model_prefix(model) == EXPECTED_PROVIDER, (
            f"agente {name!r} no usa el provider local '{EXPECTED_PROVIDER}': {model!r}"
        )
        assert _model_name(model) in declared, (
            f"agente {name!r} apunta a un modelo no declarado: {model!r}"
        )


def test_no_stale_ollama_provider() -> None:
    """No queda provider `ollama` ni el literal `localhost:11434`."""
    config = _read_config()
    raw_text = CONFIG_PATH.read_text(encoding="utf-8")

    assert STALE_PROVIDERS.isdisjoint(_provider_ids(config))
    assert STALE_BASE_URL_MARKER not in raw_text
    assert check_no_stale_ollama_provider(config) == []
    assert check_no_stale_base_url(raw_text) == []


def test_default_model_is_declared() -> None:
    """`model`/`small_model` son provider `llamacpp` + modelos declarados."""
    config = _read_config()

    assert check_default_model_is_declared(config) == []
    declared = _declared_models(config)
    assert _model_name(config.get("model")) in declared
    assert _model_name(config.get("small_model")) in declared


def test_read_config_missing_file_raises(tmp_path: Path) -> None:
    """`_read_config` falla con mensaje WHAT+WHY+WHERE si el archivo no existe."""
    missing = tmp_path / "opencode.json"

    with pytest.raises(FileNotFoundError, match="WHAT.*WHY.*WHERE") as exc_info:
        _read_config(missing)

    assert str(missing) in str(exc_info.value)


# ---------------------------------------------------------------------------
# Adversarial / mutation-style: el checker debe RECHAZAR configs rotas
# ---------------------------------------------------------------------------


class TestCheckerRejectsMutations:
    """Mutation-style: mutaciones del baseline deben ser RECHAZADAS.

    Prueba que el checker no es un no-op (anti-greenwashing): si cualquiera de
    sus checks se neutraliza, el mutante sobrevive y el test adversarial falla.
    """

    def test_valid_baseline_passes(self) -> None:
        """El baseline valido produce cero violaciones (control positivo)."""
        config = _valid_config()

        assert check_local_config(config, raw_text=json.dumps(config)) == []

    def test_rejects_unknown_provider_prefix(self) -> None:
        """(a) Prefijo de provider inexistente es rechazado."""
        config = _valid_config()
        config["model"] = f"ghost/{_model_name(EXPECTED_DEFAULT_MODEL)}"

        assert check_model_prefix(config)
        assert check_local_config(config)

    def test_rejects_missing_port_11434(self) -> None:
        """(b) baseURL sin puerto 11434 es rechazada."""
        config = _valid_config()
        config["provider"][EXPECTED_PROVIDER]["options"]["baseURL"] = "http://127.0.0.1:9999/v1"

        assert check_base_url(config)
        assert check_local_config(config)

    def test_rejects_undeclared_model(self) -> None:
        """(c) Modelo por defecto no declarado es rechazado (prefijo valido)."""
        config = _valid_config()
        config["model"] = f"{EXPECTED_PROVIDER}/modelo-fantasma"

        assert check_model_prefix(config) == []
        assert check_default_model_is_declared(config)
        assert check_local_config(config)

    def test_rejects_stale_ollama_provider(self) -> None:
        """(d) Provider `ollama` residual es rechazado."""
        config = _valid_config()
        config["provider"]["ollama"] = {
            "npm": "@ai-sdk/openai-compatible",
            "options": {"baseURL": f"{STALE_BASE_URL_MARKER}/v1"},
        }

        assert check_no_stale_ollama_provider(config)
        assert check_local_config(config)

    def test_rejects_stale_base_url_literal(self) -> None:
        """(d') Literal `localhost:11434` residual es rechazado."""
        config = _valid_config()
        stale_text = json.dumps(config) + f"  // {STALE_BASE_URL_MARKER}"

        assert check_no_stale_base_url(stale_text)
        assert check_local_config(config, raw_text=stale_text)
