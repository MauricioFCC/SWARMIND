# Spec — Algoritmos de Grafo en SWARMIND (GraphRAG mejorado)

> Estado: proposed — Dueño: harness/memory_rag — Frontera: 2026-10.
> RuscaDB spec: `graph_algorithms.md`, `graph_store.md`.

## 1. Objetivo
Usar PageRank, centralidad y shortest path sobre el grafo RuscaDB para rankear
nodos por importancia en GraphRAG.

## 2. Algoritmos
- PageRank: importancia de nodos.
- Betweenness centrality: nodos puente.
- Shortest path: distancia entre entidades.
- Connected components: comunidades.

## 3. Integracion
- `GraphRAGRetriever`: usar PageRank para ordenar el nivel global.
- Exponer `graph_stats(collection)` en RuscaDBStore.

## 4. RQL
```sql
SELECT * FROM t TRAVERSE edges DEPTH 3
```
(los algoritmos se computan en Python sobre el subgrafo extraido).

## 5. Outcome medible
- Relevancia del nivel global mejora >= 15%.
- Latencia p95 < 200ms para grafos de 10k nodos.

## 6. Esfuerzo: 4 dias.
