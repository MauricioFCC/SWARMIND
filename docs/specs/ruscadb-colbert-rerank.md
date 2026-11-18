# Spec — ColBERT Reranking en SWARMIND

> Estado: **implementado parcial** (ciclo 11.100, 2026-11-17) — Dueño: harness/memory_rag — Frontera: 2026-10.
> RuscaDB spec: `colbert_rerank.md`. Feature: `onnx` (SPEC-0111).

## 0. Estado de implementación (evidencia)

| Item | Estado | Evidencia / motivo |
|---|---|---|
| `rerank(collection, query, candidates)` (§3) | implementado | `RuscaDBStore.rerank` delega en `colbert_rerank.rerank` |
| `HybridRetriever.retrieve(rerank=True)` (§3) | implementado 11.100 | Stage 2 sobre el top-50 fusionado; reordena por `rerank_score` con orden estable (empates conservan RRF) |
| `aretrieve(rerank=...)` | implementado 11.100 | Pasa el flag al hilo del executor |
| Inferencia ONNX de ColBERTv2 | pendiente | el repo no tiene modelo ni dependencia ONNX; se usa el proxy MaxSim por overlap de tokens (sin descarga nueva) |
| Precision@5 +20 % (AC) | no medido | requiere un set etiquetado; no se declara alcanzado |

Fallback visible: si el `full_text_search` del store falla, se registra un
warning y se usa el `FTSSearch` inyectado (antes se tragaba la excepción).

Tests: `test_hybrid_retriever.py::test_retrieve_con_rerank_reordena_por_maxsim`
y `::test_retrieve_rerank_sin_candidatos_devuelve_vacio`.

## 1. Objetivo
Rerankear los top-k resultados de hybrid_search con ColBERT (late interaction,
MaxSim) para mejorar la precision de retrieval.

## 2. Diseno
- Stage 1: retrieval rapido (KNN + FTS) → top-50.
- Stage 2: ColBERT rerank (MaxSim por token) → top-5.
- Modelo: colbertv2 o similar, inferencia ONNX (feature `onnx`).

## 3. Integracion
- `HybridRetriever.retrieve` agrega stage de rerank si `rerank=True`.
- `RuscaDBStore` expone `rerank(collection, query, candidates)`.

## 4. Outcome medible
- Precision@5 mejora >= 20% vs RRF solo.
- Latencia rerank p95 < 100ms (top-50).

## 5. Esfuerzo: 1 semana.
