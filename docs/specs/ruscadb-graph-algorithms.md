# Spec — Algoritmos de Grafo en SWARMIND (GraphRAG mejorado)

> Estado: **implementado parcial** (ciclo 11.100, 2026-11-17) — Dueño: harness/memory_rag — Frontera: 2026-10.
> RuscaDB spec: `graph_algorithms.md`, `graph_store.md`.

## 0. Estado de implementación (evidencia)

| Item | Estado | Evidencia / motivo |
|---|---|---|
| PageRank | implementado 11.100 | `graph_algorithms.pagerank` con redistribución de masa dangling: el ranking suma 1 (antes perdía 73 % de la masa en una cadena) |
| Betweenness centrality | implementado | Brandes sobre grafo no dirigido |
| Shortest path | implementado | BFS por número de saltos |
| Connected components | implementado 11.100 | Une aristas en ambos sentidos (antes trataba el grafo como dirigido pese a documentarlo no dirigido) |
| `graph_stats(collection)` (§3) | implementado 11.100 | Lee `edges.out` reales vía `_rid_map` + `get_record`; antes leía `metadata["edges"]` (inexistente) y devolvía ranking uniforme falso. Devuelve `{}` si no hay aristas |
| PageRank para ordenar el nivel global de `GraphRAGRetriever` | pendiente | requiere medir relevancia (AC: +15 %); cambiar el ranking sin benchmark viola EDV |

Coste medido: 300 nodos → **15,4 ms** de escaneo FFI (0,05 ms/nodo); tope
`_GRAPH_STATS_LIMIT = 10 000` con warning de análisis parcial.

Tests: `harness/tests/test_graph_algorithms.py` (oráculos a mano) y
`test_ruscadb_store.py::test_graph_stats_usa_aristas_reales`,
`::test_graph_stats_sin_aristas_devuelve_vacio`.

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
