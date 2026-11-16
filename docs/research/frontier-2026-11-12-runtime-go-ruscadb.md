# Research frontera — runtime Go-simplicity, RuscaDB real y tokens (2026-11-12)

> Estado: cerrado — Dueño: `harness/memory_rag` + `harness/context`.
> Disparador: auditoría post-merge FDD. Pregunta: ¿qué más optimizar en el
> runtime real, no en el papel?
> Alcance: uso de RuscaDB, coste de tokens en superficies de uso constante y
> simplicidad de diseño (escuela Go). No cambia el motor Rust ni añade deps.

## 1. Método

1. Auditar llamadas reales a RuscaDB en producción (`git grep` sin tests).
2. Reproducir el comportamiento con benchmarks desechables en `%TEMP%`.
3. Leer fuentes primarias (Go, contexto de agentes) y contrastar con el código.
4. Comparar ≥3 hipótesis con criterios medibles y elegir una.

## 2. Evidencia medida (antes)

### 2.1 Inserciones fila a fila y buffer pool

Escenario: `RuscaDBStore.insert()` una fila por llamada, 300 filas, dim 64.

| `pool_capacity` | filas persistidas | tiempo |
|---|---|---|
| 8 (actual, hardcodeado) | **231/300 (23 % perdido)** | 2.85 s |
| 32 | 300/300 | 3.25 s |
| 64 | 300/300 | 3.20 s |
| 256 | 300/300 | 3.23 s |

Con N=1000 y pool ≥32: 1000/1000 (12.1–12.5 s). Con N=100 y pool 8 no se
manifiesta la pérdida: el umbral depende de páginas vivas, no del tiempo.

Mensaje real del motor:

```
ruscadb: codigo 3: ruscadb_insert_record: buffer pool lleno:
capacidad 8, sin paginas desalojables
```

Causa raíz: `rdb_open_opts(..., pool_capacity=8)` hardcodeado en
`ruscadb_store.py`. El error se capturaba con `logger.warning` y se seguía;
peor aún, `insert()` añadía el id lógico **antes** de insertar, así que devolvía
ids de filas que nunca persistieron (falso éxito).

### 2.2 Batching no es la palanca

Con pool suficiente:

| modo | tiempo 300 filas | filas |
|---|---|---|
| fila a fila | 3.177 s | 300/300 |
| lote único | 3.425 s | 300/300 |

`speedup = 0.93x`: agrupar no mejora. La mejora real es **capacidad del pool +
corrección de errores**, no batching. Se descarta batching como optimización.

### 2.3 Coste del router de tokens

`TokenBudgetRouter.rank()` sobre 50 skills reales, 200 queries:

```
p50_ms=19.703  p95_ms=24.020  total_ms=4081.6
```

Cada `rank()` tokeniza los 50 documentos, recalcula IDF, recolcula normas y
ejecuta PageRank. Nada de eso depende de la query.

### 2.4 Llamadas FFI redundantes

- `insert()` llama `list_collections()` → FFI `list_tables` en **cada** insert.
- `build_skill_graph()` lee cada skill **3 veces** (min, SKILL.md para dominio,
  min otra vez para aristas).
- `_pagerank()` recorre la adyacencia completa por cada nodo: O(iter·n·e).

### 2.5 Inventario de uso RuscaDB

Llamadas en producción (sin tests): `search=191`, `insert=79`, `execute=58`,
`delete=20`, `full_text_search=8`, `update_records=8`, `get_record=5`,
`hybrid_search=4`, `graph_traverse=2`. Sin uso: `record_access=0`,
`cached_execute=0`, `attach_blob=0`, `semantic_cache_set=0`.

Lectura: el valor está en `search`/`insert`; las capacidades exóticas no son el
cuello de botella y no se justifica adoptarlas ahora.

## 3. Fuentes primarias (leídas)

| Fuente | URL | Qué aporta |
|---|---|---|
| Go Proverbs | https://go-proverbs.github.io/ | "Clear is better than clever", "Errors are values", "Don't just check errors, handle them gracefully", "A little copying is better than a little dependency" |
| Go Blog — Errors are values | https://go.dev/blog/errors-are-values | Errores como datos manejables, no excepciones silenciadas |
| Effective Go | https://go.dev/doc/effective_go | Simplicidad, nombres cortos, cero magia |
| gofmt | https://go.dev/blog/gofmt | Una sola forma canónica reduce debate y diff |
| Anthropic — Effective context engineering | https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents | Contexto mínimo suficiente; recuperar por demanda, no precargar |
| arXiv 2508.21433 — The Complexity Trap | https://arxiv.org/abs/2508.21433 | Más contexto/iteración no es gratis: coste y degradación |
| "Simplicity is Complicated" (Rob Pike, Gopherfest 2015) | vídeo, sin transcripción consultada | `[UNVERIFIED]` — se cita solo por título |

## 4. Hipótesis comparadas

| Hipótesis | Qué cambia | Accuracy/correctitud | Latencia | Escalabilidad | Robustez | Reproducibilidad | Veredicto |
|---|---|---|---|---|---|---|---|
| H1 — solo documentar | nada | 0 | 0 | 0 | 0 | alta | Descartada: deja el bug de pérdida silenciosa |
| H2 — elevar pool y logging | pool + warning | corrige pérdida | ~0 | O(1) | media: sigue devolviendo ids fantasma | alta | Insuficiente |
| H3 — bundle Go-simplicity | pool explícito + fail-fast + caché de catálogo + precomputación + superficies tersas | corrige pérdida y falso éxito | −99 % en PageRank/rank; −1 FFI por insert | O(n·e)→O(n+e); O(n) lecturas→O(1) por insert | alta: error visible y tipado | alta: tests de equivalencia con oráculo | **Elegida** |

## 5. Gap analysis

| Hueco | Antes | Después | Δ |
|---|---|---|---|
| Pérdida de inserts | 231/300 con pool 8 | 300/300 con pool configurable | correctitud |
| Falso éxito | ids añadidos antes del insert | id solo tras persistir; fallo agregado lanza `RuscadbError` | correctitud |
| FFI por insert | `list_tables` siempre | 1 vez (caché; `refresh=True` explícito) | O(n)→O(1) |
| PageRank | O(iter·n·e) | O(iter·(n+e)) con adyacencia inversa | hasta ~n× menos trabajo |
| `rank()` | tokeniza/IDF/normas/PageRank por query | precomputado en `__init__`; por query solo TF-IDF de la query | −1 recálculo completo |
| `build_skill_graph` | 3 lecturas/skill | ≤2 lecturas/skill (min + frontmatter), aristas reutilizan texto | −33 % I/O |
| `/frontera` + AGENTS | duplican las 6 fases | versión terse; skill = SSOT | menos tokens por sesión |

## 6. Decisión

Adoptar **H3** en dos frentes:

1. **Corrección primero**: pool explícito (default 64, env
   `RUSCADB_POOL_CAPACITY`) y `insert()` fail-fast con error agregado.
2. **Simplicidad medible**: caché de catálogo, PageRank O(n+e), precomputación
   del router, lectura única de skills y superficies de comando tersas.

Fórmulas:

- PageRank: `r_{t+1}(v) = (1-d)/N + d·(Σ_{u→v} r_t(u)/outdeg(u) + dangling/N)`.
  Antes: `Σ_v Σ_u` por iteración → O(iter·n·e). Después: adyacencia inversa
  construida una vez → O(iter·(n+e)).
- Coste de `rank()`: antes O(n·L + n + iter·n·e); después
  O(q·L + n) por consulta, con precomputación O(n·L + iter·(n+e)) una vez.

## 7. Lo NO aplicado (y por qué)

- **Batching de inserts**: medido 0.93x; no mejora y añade complejidad.
- **Cambiar el motor Rust / pool dinámico**: fuera de alcance; se configura,
  no se reescribe.
- **`record_access`, `cached_execute`, `attach_blob`, `semantic_cache_set`**:
  sin uso real; adoptarlos sería optimización especulativa.
- **`tiktoken`**: no está instalado en este entorno; no se afirman ganancias de
  conteo exacto. La estimación sigue siendo `len//4`.

## 8. Reproducibilidad

Scripts desechables de la medición en `%TEMP%/opencode/bench_{insert,pool,
pool2,pool3,insert_clean,router}.py`. Los tests permanentes viven en
`harness/tests/test_ruscadb_store.py` y `harness/tests/test_token_budget_router.py`.
