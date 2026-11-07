# Spec — Optimización de memoria para mejores decisiones (ciclo 11.22)

> Estado: `proposed → accepted + implemented`
> Mandato: los 4 items de la auditoría de memoria (ciclo 11.21 diagnóstico).

## 0. Diagnóstico que motiva el spec (evidencia, 2026-10-18)

Conteo real de fragments en `Memory_Proyects/data/lancedb`:

| colección | fragments | estado |
|---|---|---|
| `semantic_cache` (volátil) | 5201 | poblada (138.8 MB en disco) |
| `agent_workspace_logs` (volátil) | 913 | poblada (48.7 MB) |
| las 13 colecciones de **valor** | 0–8 | cableadas en producción pero **vacías** |

**99.7 % del almacenamiento son caches regenerables; el conocimiento que
informa decisiones está vacío.** Las 13 colecciones de valor sí están
cableadas en producción (3–11 refs cada una) — el hueco es de *disparo*,
no de *wiring* muerto. `semantic_cache` tiene TTL (1 h) pero **sin sweeper
proactivo** (`_is_expired`/`_delete_entry` existen; no hay `purge_expired`),
por eso crece sin cota efectiva.

## 1. Items a implementar

### Item 1 — Cablear feedback post-ejecución (skill_effectiveness / agent_performance)
Corrección de diseño tras investigar (IDP + FRS): `dispatch()` **no** puede
puntuar éxito (en dispatch aún no se conoce). Ya existe el hook post-run
`AgentDispatcher.record_skill_outcome(skill_name, success)` — su docstring
dice explícitamente que el outcome se conoce DESPUÉS y que el caller lo
invoca para cerrar el ciclo (hoy delega en `LibraryDriftManager` → JSONL,
NO en las colecciones LanceDB). El seam correcto es **ese hook**.

Módulo nuevo `harness/evolve_loop/feedback_scorer.py` (SRP, DI con vector
store inyectado — `LanceVectorStore(backend="memory")` en tests, sin
`lancedb`). Se cablea en `record_skill_outcome`, que gana un parámetro
opcional `agent_role` (backward-compatible).

**Contratos:**
1. `score_outcome(store, skill_name, success, agent_role=None, metrics=None)
   -> bool`: escribe 1 fila en `skill_effectiveness` (si `skill_name`) y 1 en
   `agent_performance` (solo si `agent_role` provisto). `store is None` ⇒
   no-op que devuelve `False` (sin lanza).
2. Fila `agent_performance`: `agent_role`, `success` (bool), `ts` (ISO-8601
   UTC), `metrics` (dict serializable). Fila `skill_effectiveness`:
   `skill_name`, `success`, `ts`. Vectores = embedding determinista
   (fallback) de un texto identificador.
3. `create_collection` idempotente antes de insertar (no falle si existe).
4. **Degradación suave**: si el store lanza, `score_outcome` NO propaga
   — `logger.warning` WHAT+WHY+WHERE y devuelve `False`.
5. `AgentDispatcher.record_skill_outcome(skill_name, *, success,
   agent_role=None)`: además de la delegación existente en LibraryDrift,
   llama `score_outcome(self._vector_store, ...)` **una sola vez**,
   best-effort. 0 regresión: si el store o el scorer faltan/fallan, el
   comportamiento de `record_skill_outcome` es idéntico al actual.
6. Verificación **end-to-end**: test que invoca
   `dispatcher.record_skill_outcome("skill-x", success=True,
   agent_role="builder")` con store de memoria inyectado y afirma que
   **ambas** colecciones de valor reciben filas (prueba de que el pipeline
   escribe conocimiento, no solo caché). Usa `store.search(...)` para
   contar filas.

### Item 2 — Verificar pipeline end-to-end (instrumentación)
Cubierto por el contrato 6 del Item 1 (integración dispatch→score→colecciones
de valor). Adicional: `feedback_scorer` expone `run_report(store)` que cuenta
filas por colección de valor para poder **verificar en runtime** que el
conocimiento se está poblando (alimenta el health-check del Item 4).

### Item 3 — Cota efectiva de caches (TTL proactivo + cap)
`SemanticCache.clear_expired()` **ya existe y ya es proactivo** (recorre
todas las entradas en LanceDB e in-memory, retorna count — IDP: no se
reimplementa). La brecha real es que **nadie lo invoca como sweeper**: la
colección `semantic_cache` en disco crece sin cota (138 MB / 5201 fragments)
pese a tener TTL. Fix: cablear un barrido probabilístico en `set()` +
bajar la cota volátil.

**Contratos (revisados tras descubrir `clear_expired` existente):**
7. ~~`purge_expired`~~ → **`clear_expired()` ya existe y se reusa** (IDP).
    En `SemanticCache.set()`, tras insertar con éxito, se invoca
    `clear_expired()` de forma **probabilística** (cada
    `_SWEEP_EVERY_N_SETS = 100` inserts, contador interno) para acotar la
    colección sin escanear en cada insert. El barrido es **best-effort**:
    si `clear_expired` lanza, `set()` NO se rompe (log `warning`).
8. Idempotencia del barrido: si no hay entradas expiradas, `clear_expired`
    retorna 0 y `set()` sigue comportándose igual (0 regresión).
9. `VOLATILE_MAX_BYTES` baja de `1_073_741_824` (1 GiB) a **268_435_456**
   (256 MiB). Docstring con WHY: cota efectiva — la caché regenerable no
   debe dominar el SSOT (hoy semantic_cache=138MB vs 0.3MB de conocimiento
   de valor).
10. `prune_volatile_collections` sigue igual (0 regresión) y su test se
    mantiene en verde con el nuevo valor (actualiza aserción en
    `test_memory_bootstrap.py` ~línea 222).

### Item 4 — Health-check de paridad de memoria
Nuevo `harness/memory_rag/memory_parity.py`: audita el central y **alerta**
cuando caches grandes conviven con colecciones de valor vacías (el patrón
de hoy). Se integra en `scripts/verify_swarmind_setup.py` como sección
**no fatal** (warning, no rompe el health-check).

**Contratos:**
11. `audit_parity(db_path) -> ParityReport` con `cache_bytes`,
    `value_bytes`, `value_collections_empty: tuple[str,...]`,
    `is_imbalanced: bool`.
12. `is_imbalanced == True` **iff** `cache_bytes > 4 * value_bytes` y al
    menos 3 colecciones de valor están vacías (umbral documentado).
13. `audit_parity` **no lanza** si el path no existe (degrada a report vacío
    con `is_imbalanced=False`).
14. `verify_swarmind_setup.py` incluye la sección `memory_parity` con
    severity `warning` (no fatal); el health-check sigue en `SETUP OK`
    aunque haya desbalance (solo avisa).
15. El reporte cita WHAT+WHY+WHERE (doctrina ERR) y sugiere la acción
    (poblar colecciones de valor / barer caches).

## 2. Frontera aplicada (FRS)
- Doctrina del propio repo (arXiv:2607.21503, memoria como ciclo de vida):
  caches regenerables jamás dominan el SSOT; el valor es lo que persiste.
- TTL **proactivo** vs perezoso: en caches LLM la invalidación debe correr
  sin depender de reads (frontera 2026 de caches); un sweeper acota el
  footprint de forma determinista.
- DI + backend `memory` del `LanceVectorStore` ⇒ testable sin `lancedb`
  (mismo patrón que el fake-git del 11.21): evidencia sin red/DB real.

## 3. Alcance y no-regresión
- Todo **aditivo**: 0 cambios de comportamiento en dispatch salvo el scoring
  best-effort (degradación suave). Si el scorer falla, dispatch es idéntico.
- Colecciones de valor importan **vacías** al start (auto_create) — se
  escribe solo en runtime.
- Suite completa debe quedar en **0 failed**; los módulos nuevos pasan
  kill-check mutante (como el 11.21).
