# Spec: Catálogo de conocimiento (repos, papers, técnicas, arquitecturas, algoritmos)

> **Estado:** accepted + implemented (ciclo 11.94) · **Fecha:** 2026-11-11
> **Research:** `docs/research/frontier-2026-11-11-knowledge-catalog.md`
> **Dueño:** `harness/memory_rag/knowledge_catalog.py` + `scripts/knowledge_catalog.py`
> **Decisión:** H3 — dual-store híbrido (RuscaDB vector+FTS con RRF + grafo
> tipado NetworkX con expansión acotada). H4 (GraphRAG con comunidades LLM)
> queda fuera del camino caliente.

## 1. Problema

La memoria central guarda documentos (`rag_chunks`), skills y ADRs, pero no
mantiene un **catálogo tipado** del conocimiento externo que el equipo reutiliza
al programar: repositorios, papers, artículos, técnicas, arquitecturas óptimas y
algoritmos de estado del arte. Sin él, cada tarea vuelve a investigar desde
cero y el conocimiento no se acumula ni se conecta.

## 2. Objetivos

1. **Ingesta idempotente** de entradas con ID canónico (arXiv, DOI, GitHub, URL).
2. **Dual store:** texto embebido (384-d) + BM25 en una colección RuscaDB, y un
   grafo tipado (`KnowledgeGraph`) con conceptos y relaciones.
3. **Búsqueda híbrida** (densa + léxica + grafo) con filtros por tipo y
   expansión 1-hop, degradando a híbrida si el grafo falta.
4. **Procedencia** (`source`, `retrieved_at`, `trust_tier`) y estado
   (`adopted|evaluated|unverified|rejected`).
5. **Portabilidad:** seed público versionado y export JSON.

### No objetivos

- No hace crawling ni descarga de papers en runtime.
- No usa LLM en la indexación ni en la búsqueda (determinista).
- No sustituye `rag_chunks` (documentos) ni `KnowledgeGraph` de skills/ADRs.

## 3. Esquema

`CatalogEntry` (frozen dataclass):

| Campo | Tipo | Regla |
|---|---|---|
| `catalog_id` | str | `kind:slug` canónico, único |
| `kind` | Enum | `repo\|paper\|article\|technique\|architecture\|algorithm` |
| `title` | str | no vacío |
| `url` | str | `http(s)://` o `doi:`/`arXiv:`; sin rutas personales |
| `authors` | tuple[str, ...] | vacío si se desconoce |
| `year` | int \| None | 1900..2100 |
| `summary` | str | 1-3 frases |
| `tags` | tuple[str, ...] | conceptos normalizados (SKOS-like) |
| `concepts` | tuple[str, ...] | conceptos estructurantes |
| `complexity_before` | str | `O(·)` previa (si aplica) |
| `complexity_after` | str | `O(·)` propuesta (si aplica) |
| `status` | Enum | `adopted\|evaluated\|unverified\|rejected` |
| `source` | str | procedencia legible |
| `retrieved_at` | str | ISO-8601 UTC |

**ID canónico** (`canonical_id`):

- `arXiv:2404.16130` / `https://arxiv.org/abs/2404.16130` → `paper:arxiv-2404.16130`
- `doi:10.1145/1571941.1572114` → `paper:doi-10.1145-1571941.1572114`
- `https://github.com/owner/repo` → `repo:owner/repo`
- URL genérica → `<kind>:<host><path-slug>`

## 4. Arquitectura

```
                 ┌──────────────────────────────┐
  seed JSON ───▶ │ KnowledgeCatalog.index()      │
                 │  normalize → dedupe → embed   │
                 └───────┬──────────────┬────────┘
                         │              │
              ┌──────────▼─────┐   ┌────▼─────────────────┐
              │ RuscaDB        │   │ KnowledgeGraph       │
              │ knowledge_     │   │ (NetworkX MultiDiGraph)│
              │ catalog        │   │ entrada ↔ concepto    │
              │ vector+FTS+RRF │   │ ↔ cita ↔ repo         │
              └──────────┬─────┘   └────┬─────────────────┘
                         │              │
                 ┌───────▼──────────────▼────────┐
                 │ search(): RRF(dense, sparse,  │
                 │ graph-expand) + filtros       │
                 └───────────────┬───────────────┘
                                 ▼
                     resultados listos para contexto
```

### Grafo

- Nodo entrada: `catalog:<catalog_id>` (`type=<kind>`).
- Nodo concepto: `concept:<slug>`.
- Nodo repo: `repo:<owner/name>` (si una técnica lo implementa).
- Aristas: `about` (entrada→concepto), `instance_of` (entrada→kind),
  `implements` (repo→técnica), `cites` (paper→paper), `uses`
  (arquitectura→algoritmo).

## 5. Complejidad

- Ingesta `O(n·(D + t))`, D=384, t=tags/conceptos.
- Búsqueda `O(log n + k log k + b^d)`, d≤2, b acotado por `max_neighbors`.
- Dedupe `O(1)` esperado por entrada (hash del ID canónico).
- Sin catálogo: `O(R)` relectura manual por consulta (R = fuentes).

## 6. Criterios de aceptación (testeables)

- **AC1** `canonical_id` es idempotente y normaliza arXiv/DOI/GitHub; PBT:
  `canonical_id(canonical_id(x)) == canonical_id(x)`.
- **AC2** Ingesta del mismo seed dos veces no duplica filas (dedupe por ID).
- **AC3** `index` inserta vector + texto + metadata en la colección y crea
  nodos/aristas en el grafo.
- **AC4** `search` fusiona dense/sparse/grafo con RRF y respeta `kind`/`top_k`.
- **AC5** Si el grafo no tiene el nodo, `search` sigue devolviendo resultados
  híbridos (degradación H1).
- **AC6** `stats` reporta conteo total y por tipo/estado.
- **AC7** El verificador rechaza URLs con rutas personales y entradas sin
  `title`/`url`.
- **AC8** `export`/`ingest` son round-trip estables (JSON canónico).

## 7. Plan de tests (TDD adversarial)

- Unit: canonicalización, validación, dedupe, filtros, stats, export.
- PBT (hypothesis): idempotencia de ID; longitud de vector = 384; ninguna
  entrada válida produce URL personal.
- Grafo: nodos/aristas esperadas para paper/técnica/repo.
- Mutantes esperados (kill): invertir dedupe, quitar filtro de `kind`,
  ignorar `top_k`, no crear arista `about`.
- Store falso (DI) para no depender del DLL nativo en CI Linux.

## 8. Seguridad y privacidad

- Sin secretos ni rutas personales en seed/export (verificador).
- `trust_tier`/`quarantined` los aplica el store en `insert`.
- El catálogo no ejecuta código de las fuentes: solo texto y metadatos.

## 9. Ciclo de vida (consultar → usar → feedback → alimentar)

El catálogo **no es estático**: sin alimentación pierde efectividad. Cada
consulta deja un registro append-only en
`knowledge_catalog_usage.jsonl` (junto al índice, en `Memory_Proyects/data/`):

- `useful`: la entrada resolvió; cuenta como uso.
- `stale`: quedó obsoleta; se corrige y reingiere (nueva versión).
- `missing`: no había conocimiento; es un **gap** que se añade al seed local y
  se reingiere.

API: `KnowledgeCatalog.record_usage(...)`, `usage_stats()`; CLI:
`feedback` y `gaps`. `stats` reporta `usage.total`, `by_outcome`, `top_ids` y
`gaps`.

## 10. Integración

- `scripts/setup_memory_central.py`: `knowledge_catalog` entra en las
  colecciones canónicas.
- `scripts/knowledge_catalog.py`: CLI `ingest|search|stats|graph|export|verify`.
- Docs: CHANGELOG 11.94, roadmap, MEJORAS, spec y research.
