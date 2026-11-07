# Spec — SSOT de la flota local + ventana real (ADR-0092 / ADR-0099)

## Outcome medible

Una sola fuente de verdad para los hechos de la flota local (modelo, tier,
`num_ctx`, `vram_mb`, `keep_alive`) que **deriva** en `model_windows`,
`vram_guard` y `local_executor`; y la ruta local pide a Ollama la ventana
declarada en vez de quedarse en el default 4096.

Criterio de exito: `recommend_num_ctx(tier.model) == tier.num_ctx`,
`footprint_mb(tier.model) == tier.vram_mb`, y `LocalExecutor` envia
`options.num_ctx` al generate. Cero colisiones de substring.

## Contexto (medido 2026-09-30, RTX 4060 8GB, Ollama 0.34.4)

- Tiers canonicos (`hf.co/...`) corren con el default **4096** (no 8192).
- El servidor fija `OLLAMA_CONTEXT_LENGTH=16384` (`scripts/enable_gpu.py`) +
  el harness envia `num_ctx` explicito por `options`: las variantes con ctx
  horneado quedaron **retiradas 2026-09-30** (liberan ~17.4 GB de disco).
- `num_ctx` via `options` sobre el nombre canonico FUNCIONA (verificado en
  servidor temporal): 16384 -> 5.15GB, 8192 -> 4.98GB (con KV comprimida).
- KV comprimida (`OLLAMA_FLASH_ATTENTION=1` + `OLLAMA_KV_CACHE_TYPE=q8_0`)
  baja el 9B de 5.7GB (16k) a 5.15GB: ~0.55GB de headroom anti-OOM.
- Alias `onyx-*` = mismo digest que los `hf.co/...` (no ocupan disco extra,
  pero son deriva de nombres).

## Requisitos funcionales

- FR1: manifiesto unico de flota con `model`, `tier`, `num_ctx`, `vram_mb`,
  `keep_alive`.
- FR2: `recommend_num_ctx` y `footprint_mb` derivan del manifiesto.
- FR3: `LocalExecutor` envia `num_ctx` del manifiesto via `options`.
- FR4: los topes de servidor incluyen KV comprimida (proteccion anti-OOM).

## Requisitos no funcionales

- NF1: sin sobre-ingenieria — manifiesto en Python (importable, tipado), no
  parser YAML propio.
- NF2: portable: nombres canonicos pullables (no dependen de builds locales).
- NF3: fallback seguro si el modelo no esta en el manifiesto.

## Invariantes (tests TDD)

1. Todo tier del YAML de config tiene entrada en el manifiesto y coincide.
2. `recommend_num_ctx(model)` devuelve el `num_ctx` del manifiesto (no default).
3. `footprint_mb(model)` devuelve el `vram_mb` del manifiesto (no default).
4. Ningun modelo del manifiesto cae en `DEFAULT_NUM_CTX`.
5. `num_ctx` declarado * KV por token <= presupuesto de 8GB (sin OOM).
6. `local_executor` pasa `options.num_ctx` en toda generacion local.

## Fuera de alcance

- Descargar modelos nuevos (se documenta recomendacion, no se fuerza pull).
- Borrar alias `onyx-*` (requiere confirmacion del usuario).
- Cambiar modelos por benchmark (requiere validacion en la maquina).

## Rollback

Revert del commit; `fits_in_window`/`recommend_num_ctx` conservan la tabla
medida como fallback, asi que un manifiesto ausente no rompe la ruta local.
