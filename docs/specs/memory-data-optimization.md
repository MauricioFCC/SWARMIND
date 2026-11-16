# Spec — Optimizacion de Memoria y Datos (RuscaDB + Token Economics)

> Estado: **implementado parcial** (ciclo 11.99, 2026-11-16) — Dueño: harness/memory_rag — Frontera: 2026-10.
> Referencias: Adaptive-RAG (arXiv:2403.14403), LightRAG (arXiv:2410.05779),
> GraphRAG (arXiv:2404.16130), Summary-based communication (arXiv:2607.27942),
> RRF (Cormack 2009).

## 0. Estado de implementacion (evidencia)

| Item | Estado | Evidencia / motivo |
|---|---|---|
| Embeddings float32 | implementado | `insert()` normaliza a `np.float32` |
| Metadata JSON compacto (2.1) | implementado 11.99 | `_JSON_COMPACT` → `{"separators": (",", ":")}` en los 4 puntos de escritura de metadata |
| Timestamps epoch-int (2.1) | descartado | `created_at` ISO es contrato del esquema y de `_age_days`; migrar rompe filas existentes sin ganancia medible (el coste dominante es el JSON, no la fecha) |
| IDs ULID (2.1) | descartado | `_looks_like_ulid` y la resolucion de aristas (`_find_rid`) asumen ULID fisico del motor; el `id` logico es UUID por contrato de `insert()` |
| Cache de clasificacion por query hash (3) | descartado | `classify_complexity` es O(len(query)) con `split()`; hashear + dict + eviction cuesta mas que recalcular |
| Retrieval adaptativo (3) | implementado | `AdaptiveRetriever` en `adaptive_retriever.py` |
| Fusion RRF k=60 (4) | implementado | `hybrid_search()` |
| Token economics (5) | implementado | `structured_compact`, `observation_masking`, `failure_spend` |
| Limpieza proactiva (6) | implementado | TTL sweep, `gc_blobs`, `reap` |

Pendiente declarado: indice sobre `created_at` e indice configurable sobre
metadata (2.2) no existen; no hay medicion que los justifique todavia.

## 1. Objetivo

Maximizar la eficiencia de la memoria central (RuscaDB) y minimizar el consumo
de tokens: tipos de datos optimos, indices estrategicos, retrieval adaptativo,
fusion hibrida, compresion de contexto, y limpieza proactiva.

## 2. Optimizaciones de datos

### 2.1 Tipos de datos
- Embeddings en float32 (ya implementado).
- Metadata como JSON compacto (sin espacios, claves cortas).
- Timestamps como Int (epoch ms) en vez de ISO strings donde sea posible.
- IDs: ULID (ordenables, compactos) en vez de UUID v4.

### 2.2 Indices
- Indice secundario sobre `id` (ya creado).
- Indice sobre `created_at` para time-range queries.
- Indice sobre columnas de metadata frecuentes (configurable).
- HNSW para KNN (ya en RuscaDB).

### 2.3 Compresion
- Zstd para WAL (SPEC-0121, feature `compression`).
- Compresion de metadata JSON en reposo (futuro).

## 3. Retrieval adaptativo (ya implementado parcialmente)

- `AdaptiveRetriever`: simple → sparse, medium → hybrid, complex → iterative.
- Mejora: clasificador basado en LLM (opcional) para mayor precision.
- Cache de clasificacion por query hash.

## 4. Fusion hibrida

- RRF con k=60 (estandar).
- Pesos configurables por dominio (dense vs sparse).
- Reranking opcional con cross-encoder (futuro, requiere ONNX).

## 5. Token economics

- `SummaryCommunication`: solo resumenes relevantes (ya implementado).
- Observation masking: truncar outputs largos a N tokens.
- Cache-shape: prefijos estables para cache de prompt.
- Failure-spend: no reintentar sin cambio de estrategia.

## 6. Limpieza proactiva

- TTL sweep cada N inserts (ya implementado en SemanticCache).
- Reap de versiones MVCC muertas (RuscaDB `reap`).
- GC de blobs sin referencias (ya implementado).
- Compactacion periodica del WAL (checkpoint).

## 7. Outcome medible

- Latencia de search p95 < 50ms.
- Tokens por query reducidos en >= 40% vs historial completo.
- Hit rate de cache >= 60%.

## 8. Esfuerzo estimado

- Fase 1 (tipos + indices): 2 dias.
- Fase 2 (retrieval adaptativo mejorado): 3 dias.
- Fase 3 (token economics): 2 dias.
- Fase 4 (limpieza proactiva): 1 dia.
