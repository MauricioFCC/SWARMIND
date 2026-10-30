# Spec — IVF-PQ / RaBitQ Cuantizacion de Vectores

> Estado: implemented-parcial (ciclo 11.56: RaBitQ + rescore) — Dueño: harness/memory_rag — Frontera: 2026-10.
> RuscaDB spec: `ivf_pq.md`, `ivf_clustering.md`, `rabitq_quantization.md`, `hnsw_budget_pq.md`.

## 1. Objetivo
Reducir la memoria de embeddings en 4-8x usando cuantizacion IVF-PQ y RaBitQ,
manteniendo recall >= 90%.

## 2. Diseno
- IVF: particionar el espacio en clusters (coarse quantizer).
- PQ: cuantizar cada subvector a un codigo de 8 bits.
- RaBitQ: cuantizacion 1-bit para busqueda rapida (recall ~85%).

## 3. Integracion
- Configurar RuscaDB HNSW con PQ (feature `ivf-pq`).
- `RuscaDBStore` expone `quantization_mode` (none/pq/rabitq).

## 4. Outcome medible
- Memoria de embeddings reducida en >= 4x.
- Recall@10 >= 90% (PQ) / >= 85% (RaBitQ).
- Latencia de search p95 < 20ms.

## 5. Esfuerzo: 1 semana.

## 6. Contrato ABI implementado (ciclo 11.56)

> Estado del bloqueo: `RabitqQuantizer` ya existe en RuscaDB
> (`crates/ruscadb/src/rabitq.rs`: `encode`, `estimate_dot`, `estimate_l2`,
> `code_len`) pero NO cruza el C-ABI. Estas dos funciones son el primer gap
> upstream y desbloquean el KNN binario + rescore en SWARMIND.
>
> Trigger (cuando el consumidor lo requiera): memoria de colecciones vectoriales
> > 256 MiB o latencia p95 de `search` > 50 ms en la coleccion `memory`; o flag
> explicito `RUSCADB_BQ=1`.

### 6.1 Firmas C (crates/ruscadb-ffi/src/lib.rs)

```c
/* Codifica n vectores f32 (row-major) a codigos 1-bit empaquetados.
 * out_codes: n * ceil(dim/8) bytes; out_norms: n floats.
 * Devuelve RC_OK, RC_NULL_POINTER o RC_BUFFER_INSUFICIENTE. */
int ruscadb_quantize(const float *vectors, size_t n, size_t dim,
                     uint8_t *out_codes, size_t out_codes_len,
                     float *out_norms, size_t out_norms_len);

/* KNN aproximado con codigos 1-bit + rescore exacto float32.
 * Escribe JSON (mismo shape que ruscadb_execute) en out_json.
 * oversample >= 1 (recomendado 3): candidatos = top_k * oversample antes del
 * rescore. Devuelve RC_OK, RC_NULL_POINTER, RC_INVALID_HANDLE,
 * RC_DOMAIN_ERROR (dim distinta) o RC_BUFFER_INSUFICIENTE. */
int ruscadb_search_bq(void *handle, const char *table, const float *query,
                      size_t dim, size_t top_k, size_t oversample,
                      char *out_json, size_t buf_len);
```

Notas de implementacion Rust:
- Reusar `RabitqQuantizer::{encode, estimate_dot, estimate_l2, code_len}`.
- `search_bq`: escanear los embeddings de la tabla, estimar `estimate_dot`
  contra `query` normalizada, conservar `top_k * oversample` por heap, y
  **rescore exacto L2** con los float32 originales antes de ordenar.
- `write_string_out` + `guard_ffi` para el contrato de errores existente.
- Determinismo: desempate por `id` ascendente.

### 6.2 Cableado en SWARMIND (cuando exista el simbolo)

1. `harness/memory_rag/ruscadb.py`: bind opcional de ambos simbolos y claves
   nuevas en `capabilities()` (`ruscadb_quantize`, `ruscadb_search_bq`).
2. `RuscaDBStore.search_binary(collection, query_vector, top_k=10,
   oversample=3, rerank=True)`: usa el simbolo si `capabilities()` lo confirma;
   si no, degrada a `search()` con warning (nunca falla en silencio).
3. Puerto opcional (ISP): `BinarySearchPort` en `harness/domain/ports.py`; NO se
   agrega a `VectorStorePort` (no todos los backends lo ofrecen).
4. `AsyncRuscaDBStore.search_binary` (thread offload) + telemetria
   `binary_search_stats()` (codificaciones, candidatos, recall estimado).
5. `RUSCADB_BQ=1` activa `search_binary` como ruta por defecto en
   `HybridRetriever` solo si `capabilities()` lo reporta.

### 6.3 Criterios de aceptacion (medibles)

- Recall@10 >= 0.90 vs KNN exacto sobre 2 000 vectores gaussianos de 384 dims
  (seed fija), con `oversample=3`.
- Determinismo: misma query -> mismos ids en 20 ejecuciones.
- Compresion de codigos: `code_len(384) = 48` bytes (32x vs float32).
- Errores: NULL_POINTER, INVALID_HANDLE, DOMAIN_ERROR (dim) y
  BUFFER_INSUFICIENTE cubiertos por tests Rust (`crates/ruscadb-ffi/tests`).
- SWARMIND: `capabilities()` reporta ambos simbolos; tests de degradacion sin
  simbolo (skip honesto) y de paridad `search_binary` vs `search` con
  `rerank=True` (mismos vecinos exactos cuando `oversample` cubre la tabla).
- Gates: ruff 0, vulture 0, `check_architecture --gate --ratchet` 0, sin
  regresiones en los 7.2k tests.

### 6.4 Fuera de alcance (fase 2)

- Indice IVF/HNSW persistente sobre codigos binarios (el escaneo actual es
  O(n) por query; el ahorro de memoria llega al no retener float32 en RAM).
- Persistencia de codigos en una columna `embedding_bq` (requiere `ALTER TABLE`,
  no expuesto en el ABI).

## 7. Evidencia (ciclo 11.56)

- RuscaDB expone `ruscadb_quantize` + `ruscadb_search_bq` (commit 91ecb36)
  y SWARMIND los importa (DLL 5.2 MB, 32 simbolos).
- `RuscaDBStore.search_binary(...)` usa el ABI: candidatos 1-bit +
  oversampling y rescore exacto float32; degrada a KNN exacto sin simbolo.
- `OversampleTuner` ajusta el factor por carga real (recall muestreado vs
  KNN exacto, EWMA + persistencia).
- Tests: `harness/tests/test_binary_search.py` (12) cubren code_len(16)=2 B,
  recall con oversample completo, determinismo, fallback y calibracion.
- LIMITE: el motor escanea y cuantiza en la query (no hay indice IVF/HNSW
  persistente de codigos); el ahorro de RAM llega al no retener float32 en
  el heap del indice. `nprobe` no existe en este build: el control es
  `oversample` (equivalente funcional al rerank factor).
