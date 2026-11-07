# Spec — ColBERT Reranking en SWARMIND

> Estado: proposed — Dueño: harness/memory_rag — Frontera: 2026-10.
> RuscaDB spec: `colbert_rerank.md`. Feature: `onnx` (SPEC-0111).

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
