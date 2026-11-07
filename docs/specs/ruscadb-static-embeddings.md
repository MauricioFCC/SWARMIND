# Spec — Static Embeddings (model2vec) en SWARMIND

> Estado: proposed — Dueño: harness/memory_rag — Frontera: 2026-10.
> RuscaDB spec: `static_embeddings.md`, `ai_embed.md`, `ai_embedder.md`.

## 1. Objetivo
Usar embeddings estaticos (model2vec) para generar embeddings locales sin
dependencia de red ni GPU, acelerando la ingesta.

## 2. Diseno
- Modelo: model2vec (static-embeddings, SPEC-0083).
- Dimension: 256-768 segun modelo.
- Inferencia: CPU, < 1ms por texto.

## 3. Integracion
- `EmbeddingPort` implementacion `StaticEmbeddingAdapter`.
- `RuscaDBStore.insert` usa static embeddings por defecto si no se provee vector.
- Configurable via env `EMBEDDING_MODEL`.

## 4. Outcome medible
- Throughput de embedding >= 1000 docs/s (CPU).
- Sin dependencia de red.

## 5. Esfuerzo: 3 dias.
