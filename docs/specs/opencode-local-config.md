# Spec — Config local de opencode (provider `llamacpp` + llama-swap)

> Autor: guardian (rol calidad/seguridad/riesgo) · Fecha: 2026-10-08 · Estado: done
> Patrón: Spec-First (Proof-or-Stop, Huang 2026) + SDD/TDD adversarial (ADR-0077).

## Outcome medible

`.opencode/opencode.json` describe el backend local como provider `llamacpp`
sobre llama.cpp / llama-swap en `http://127.0.0.1:11434/v1` (OpenAI-compatible),
con `model` por defecto `llamacpp/jackod-9b-coder-iq4-xs`, `small_model`
`llamacpp/qwen3-5-4b-gguf-ud-q4-k-xl` y **6 modelos registrados por nombre
corto** que son espejo 1:1 de las claves de `llama-swap.yaml`.

Criterio de éxito: el checker hermético `harness/tests/test_opencode_local_config.py`
valida JSON + `$schema`, prefijo de provider, baseURL (scheme/host:11434/path
`/v1`), set exacto de 6 nombres cortos, ausencia de proveedor `ollama` residual
y que `model`/`small_model` apunten a modelos declarados. Cero red, cero
llama-swap requerido.

## Contexto (medido 2026-10-08)

- El estado vigente de `.opencode/opencode.json` usa provider `ollama` +
  `http://localhost:11434/v1` con nombres largos (`hf.co/...`, `mannix/...`).
  Esa forma queda **retirada**: llama-swap sirve los modelos por nombre corto.
- `README.md:106`, `docs/src/es/README.md:123` y
  `docs/src/es/roadmap/estado.md:20` ya documentan el estado FINAL.
- `harness/tests/test_llama_swap_manager.py:268` ya usa el nombre corto
  `jackod-9b-coder-iq4-xs` (warm), confirmando el contrato de nombres.
- `harness/tests/test_ollama_client.py:209` usa
  `qwen3-5-4b-gguf-ud-q4-k-xl` (generate).
- `harness/model_router/backend_config.py` fija `DEFAULT_BASE_URL =
  http://127.0.0.1:11434` (SSOT del puerto) y `mutation.yml` documenta que
  mutmut 3.x requiere fork y **no corre en Windows nativo** (issue #397).

## Requisitos funcionales

- FR1: `provider.llamacpp.options.baseURL` == `http://127.0.0.1:11434/v1`.
- FR2: `model` == `llamacpp/jackod-9b-coder-iq4-xs` y `small_model` ==
  `llamacpp/qwen3-5-4b-gguf-ud-q4-k-xl` (prefijo = provider declarado).
- FR3: `provider.llamacpp.models` tiene EXACTAMENTE las 6 claves cortas:
  `qwen3-5-4b-gguf-ud-q4-k-xl`, `mimo-v2-6-distill-qwen-9b-gguf-iq4-xs`,
  `jackod-9b-coder-iq4-xs`, `ornith-1-5-9b-gguf-q4-k-m`,
  `qwen3-embedding-0-6b`, `qwen3-vl-4b`.
- FR4: no existe el provider `ollama` ni el literal `localhost:11434` en el
  archivo.
- FR5: `model` y `small_model` apuntan a modelos declarados en el provider.

## Requisitos no funcionales

- NF1 (seguridad/aislamiento): tests **herméticos** — sin red, sin llama-swap,
  sin GPU; solo lectura del JSON versionado.
- NF2 (calidad): docstrings ES, patrón AAA, type hints, `ruff` 0 errores.
- NF3 (portabilidad): válido en Windows/Linux/macOS; no depende de rutas de
  usuario ni de mayúsculas del filesystem.
- NF4 (mantenibilidad): la constante de nombres cortos se documenta como espejo
  de `llama-swap.yaml`; si cambia el YAML, cambia el test (SVE).

## Diseño de verificación (checker puro)

Un checker puro `check_local_config(config) -> list[str]` (lista de violaciones,
vacía = OK) descompuesto en funciones puras por invariante. Cada test de archivo
real lo invoca; los tests adversariales mutan un baseline VÁLIDO en memoria y
exigen que el checker RECHACE (mutation-style, PROBE/AdverTest):

| Ataque | Checker que debe rechazar |
|--------|---------------------------|
| prefijo de provider inexistente | `check_model_prefix` |
| baseURL sin puerto 11434 | `check_base_url` |
| modelo no declarado | `check_default_model_is_declared` |
| provider `ollama` residual | `check_no_stale_ollama_provider` |

## Invariantes (tests TDD)

1. `test_config_is_valid_json` — parsea y `$schema` == `https://opencode.ai/config.json`.
2. `test_model_prefix_matches_provider` — prefijo de `model`/`small_model` ∈ `provider`.
3. `test_base_url_points_to_llama_swap` — scheme http, host 127.0.0.1|localhost, puerto 11434, path /v1.
4. `test_declared_models_are_llama_swap_names` — set exacto de 6 nombres cortos.
5. `test_no_stale_ollama_provider` — sin provider `ollama`, sin `localhost:11434`.
6. `test_default_model_is_declared` — `model`/`small_model` declarados.
7. Adversariales: 4 mutaciones del baseline deben ser rechazadas por el checker.
8. Baseline válido: `check_local_config(_valid_config()) == []` (anti-greenwashing).

## Fuera de alcance

- Editar `.opencode/opencode.json` (lo hace otro agente; guardian solo spec+tests).
- Validar que llama-swap esté corriendo o que los GGUF existan en disco.
- Parsear `llama-swap.yaml` (vive en la máquina del usuario, no en el repo).

## Sandbox (aislamiento)

- **Crea**: `specs/opencode-local-config.md`, `harness/tests/test_opencode_local_config.py`.
- **NO toca**: `.opencode/opencode.json` ni ningún archivo de producción.
- **Rollback**: `Remove-Item` de los dos archivos nuevos; sin impacto en runtime.

## Exit criteria (gates)

- [x] `uv run ruff check harness/tests/test_opencode_local_config.py` → 0 errores.
- [x] `uv run python -m pytest harness/tests/test_opencode_local_config.py -q` → verde
      (o RED documentado si el otro agente aún no escribe el JSON final).
- [x] Sin `except: pass`; errores con WHAT+WHY+WHERE.
- [x] Docstrings ES en toda función; helpers puros reutilizados por los adversariales.

## Mutación

- Intento: `uvx mutmut --version` / `uv run mutmut run`.
- Motivo de no-viabilidad local: mutmut 3.x requiere `os.fork` y **no corre en
  Windows nativo** (issue #397), confirmado en `.github/workflows/mutation.yml`
  (el job corre en `ubuntu-latest`).
- Compensación: asserts mutation-style (checker puro + mutaciones del baseline)
  que matan mutantes lógicos sin necesidad de fork.


## Evidencia (2026-10-08)

- `uv run ruff check harness/tests/test_opencode_local_config.py` → `All checks passed!`
- `uv run python -m pytest harness/tests/test_opencode_local_config.py -q` → `13 passed in 0.69s`
- Estado REAL del JSON tras el cierre del agente paralelo: provider único
  `llamacpp`, `baseURL` `http://127.0.0.1:11434/v1`, `model`
  `llamacpp/jackod-9b-coder-iq4-xs`, `small_model`
  `llamacpp/qwen3-5-4b-gguf-ud-q4-k-xl`, 6 modelos por nombre corto, sin
  `ollama` ni `localhost:11434`. → GREEN (no fue necesario el RED previsto).
- Auditoría guardian: 0 funciones sin docstring (`ast.get_docstring`), 0
  `except` silenciosos.

### Mutación

- Comando intentado: `uvx mutmut --version` y `uvx mutmut run`.
- Resultado: exit code 1 — `To run mutmut on Windows, please use the WSL.
  Native windows support is tracked in issue #397`. Confirmado por
  `.github/workflows/mutation.yml` (el job corre en `ubuntu-latest`).
- Compensación mutation-style ejecutada (baseline válido en memoria):
  `baseline -> OK`; mutante (a) prefijo inexistente -> KILLED; (b) baseURL sin
  11434 -> KILLED; (c) modelo no declarado -> KILLED; (d) provider `ollama`
  residual -> KILLED. El checker puro no es un no-op.