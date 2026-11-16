# Spec — Runtime Go-simplicity: RuscaDB correcto y tokens precomputados

> Estado: `accepted → implemented` — Dueño: `harness/memory_rag` +
> `harness/context` — Frontera: 2026-11.
> Research: `docs/research/frontier-2026-11-12-runtime-go-ruscadb.md`.
> Principios: RSF, IDP, ERR, FST, GATE.

## 1. Objetivo

Corregir la pérdida silenciosa de filas en RuscaDB, eliminar el falso éxito de
`insert()` y reducir trabajo repetido en el router de tokens y en las
superficies de uso constante (`/frontera`, `AGENTS.md`), sin cambiar el motor
ni añadir dependencias.

## 2. Alcance

### 2.1 RuscaDB

- `MemoryConfig.ruscadb_pool_capacity: int = 64` (env `RUSCADB_POOL_CAPACITY`).
- `RuscaDBStore(..., pool_capacity: int | None = None)`; resuelve config →
  env → default 64; valida `>= 1` con `ValueError` WHAT/WHY/WHERE.
- `insert()`: el id lógico se añade **solo** si la fila persistió; los fallos
  se agregan y, si hubo alguno, se lanza `RuscadbError(RC_DOMAIN_ERROR)`
  después de `commit()` con WHAT/WHY/WHERE y el primer detalle.
- `list_collections(refresh: bool = False)`: devuelve la caché si ya está
  poblada; `refresh=True` fuerza FFI. `create_collection` mantiene la caché.

### 2.2 Router de tokens

- `_pagerank`: adyacencia inversa precomputada; complejidad
  O(iter·(n+e)); equivalencia numérica con el oráculo O(iter·n·e) (tolerancia
  1e-12).
- `_tfidf_scores(query, docs, *, idf=None, doc_tfs=None, doc_norms=None)`:
  permite reutilizar IDF/TF/normas precomputados; misma salida que la versión
  completa.
- `TokenBudgetRouter.__init__`: precomputa `node_ids`, tokens de documentos,
  IDF, `Counter` por documento, normas y PageRank. `rank(query)` solo
  tokeniza la query y calcula TF-IDF con lo precomputado.
- `build_skill_graph`: lee como máximo una vez `SKILL.min.md` y una vez
  `SKILL.md` por skill; aristas reutilizan el texto ya leído.

### 2.3 Superficies de uso

- `.opencode/commands/frontera.md`: versión terse (≤1200 bytes) que conserva
  `$ARGUMENTS`, `frontier-engineering`, las 6 fases, `publish.py` y
  `docs/research/frontier-`.
- Sección "Ciclo Frontera" de `AGENTS.md`: ≤1200 bytes con los mismos
  marcadores; la skill `frontier-engineering` es la SSOT.

## 3. Fuera de alcance

- Batching de inserts (medido 0.93x: no mejora).
- Cambios al motor Rust, pool dinámico o nuevas dependencias.
- Adopción de `record_access`/`cached_execute`/`attach_blob`/`semantic_cache_set`
  (sin uso real).

## 4. Criterios de aceptación (testeables)

| ID | Criterio | Test |
|---|---|---|
| AC-1 | 300 inserts fila a fila persisten 300/300 con el default | `test_insert_many_rows_no_pierde_filas` |
| AC-2 | `insert()` devuelve solo ids de filas persistidas y falla explícito si el motor rechaza | `test_insert_falla_explicito_sin_ids_fantasma` |
| AC-3 | `pool_capacity < 1` lanza `ValueError` con WHAT/WHY/WHERE | `test_pool_capacity_invalido_raises` |
| AC-4 | `RUSCADB_POOL_CAPACITY` configura el pool | `test_pool_capacity_desde_env` |
| AC-5 | `list_collections()` no llama FFI si la caché está poblada; `refresh=True` sí | `test_list_collections_usa_cache` |
| AC-6 | `_pagerank` nuevo == oráculo en 3 grafos (incluye duplicados y dangling) | `test_pagerank_equivalente_al_oraculo` |
| AC-7 | `rank()` precomputado == oráculo por query | `test_rank_equivalente_al_oraculo` |
| AC-8 | PageRank se calcula una sola vez por router | `test_pagerank_se_calcula_una_vez` |
| AC-9 | `build_skill_graph` no lee el mismo archivo dos veces | `test_build_skill_graph_lee_una_vez_por_archivo` |
| AC-10 | `/frontera` y AGENTS conservan contrato y son tersos | `TestFrontierCommand`, `TestAgentsHook` |

## 5. Plan de migración

1. **Expand**: añadir parámetro/opcional y precomputación manteniendo firmas
   públicas y defaults compatibles.
2. **Migrate**: `insert()` estricto; ningún caller de producción espera ids
   fantasma (verificado con `git grep`), y los fallos ya no se silencian.
3. **Contract**: los tests de equivalencia fijan el oráculo; no se puede
   "optimizar" cambiando resultados.

Rollback: revertir el commit; no hay migración de datos ni cambio de formato en
disco.

## 6. Riesgos

| Riesgo | Mitigación |
|---|---|
| Un fallo puntual del motor ahora aborta el lote | El error es agregado y visible; antes se perdían filas en silencio |
| `list_collections` no ve tablas creadas por otro proceso | `refresh=True` explícito; el store es single-writer |
| Diferencias de punto flotante en PageRank | Test de equivalencia con tolerancia 1e-12 |
| Superficies tersas pierden instrucciones | Contrato ejecutable con marcadores y cota de tamaño |

## 7. Evidencia de cierre

- Medición antes/después: research §2 y §5.
- Gates: `pytest` de los módulos tocados, `ruff`, `vulture`, `xtask check`.
- Sin datos privados ni rutas personales en el diff.
