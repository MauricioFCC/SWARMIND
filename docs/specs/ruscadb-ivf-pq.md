# Spec — IVF-PQ / RaBitQ Cuantizacion de Vectores

> Estado: blocked-upstream — Dueño: harness/memory_rag — Frontera: 2026-10.
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
