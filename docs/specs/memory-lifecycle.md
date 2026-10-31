# Spec: Ciclo de vida de la memoria colectiva (memory lifecycle)

> Estado: implemented (ciclo 11.20) · Dueño: harness/memory_rag ·
> Frontera: 2026-10 · Reemplaza el modelo "store estático" por política de ciclo de vida.

## 1. Objetivo

Que toda instalación de SWARMIND (Windows/Linux/macOS, primera vez o existente)
use la **memoria colectiva** (`~/Documents/Memory_Proyects`, override
`MEMORY_ROOT`) como SSOT, detecte y migre memorias locales de proyecto
(`harness/db/lancedb`), y **no almacene lo que no aporta valor restaurable**
(caches/logs regenerables) con topes duros.

## 2. Research frontera anexada (FRS)

- **arXiv:2607.21503 — "Agentic Context Management" (2026)**: la memoria de
  agentes es un **ciclo de vida**, no un store: deciding what to remember →
  extracting → choosing the right store for the right data-type →
  **forgetting stale information while maintaining provenance** → compacting.
  Cinco primitivas: *architecting, ingesting, scoping, anticipating,
  compacting & consolidation*. Coste: acumulación naïve de contexto crece
  **cuadráticamente** con la longitud de la conversación; solo la compactación
  validada mantiene coste lineal con fidelidad. LongMemEval 92% / LoCoMo 93.2%.
- **Capas cognitivas (2026)**: producción combina *episodic + semantic +
  procedural*; el gap no es storage sino **gestión de qué está en contexto**.
  La memoria semántica necesita **staleness management** (TTL + provenance).
- **Caches LLM 2026** (Redis/digitalapplied/neuraltrust): prompt cache (KV
  tensors) ≠ semantic cache (embeddings de prompts); ambos requieren
  **invalidación/TTL**; una cache sin política es deuda — nunca se preserva
  como respaldo porque es **regenerable por diseño**.

## 3. Decisiones (qué guardar / qué NO guardar)

| Colección | Clase | Política |
|---|---|---|
| `rag_chunks`, `asi_cognition_store`, `procedural_skills`, `prompt_evolution_log`, KPIs, `iteration_reports`, `tasks_board`, `hitl_approval_log`, `agent_interactions`, `agent_performance`, `scheduler_log`, `telemetry_events` | **valor** | Migrar/preservar. Fusionar por filas (append) si la local es más nueva. |
| `semantic_cache`, `agent_workspace_logs` | **regenerable** | Jamás respaldar (doctrina backup_memory.py) ni migrar; **topes**: > 1 GB por colección ⇒ se elimina y regenera. |

**NO guardar nunca** (SEG/ERR): secretos crudos (mask), PII en logs,
salidas de herramientas > 4K chars (ya las maneja `artifact_store`), ni
duplicados de chunks (dedup).

## 4. Arquitectura (nuevo módulo)

`harness/memory_rag/memory_bootstrap.py` (funciones puras + DI de paths):

- `default_memory_root()` — `MEMORY_ROOT` env > `~/Documents/Memory_Proyects`
  (pathlib, cross-platform win/linux/mac).
- `bootstrap_memory(root)` — crea `<root>/{data/lancedb,backups}` +
  `.swarmind_config.json` (idempotente; shape compatible con
  `backup_memory._DEFAULTS`).
- `detect_project_local_memory(project_root)` — tablas `*.lance` de
  `harness/db/lancedb` con tamaño/mtime (None si no hay fork local).
- `migrate_local_to_central(local_db, central_db)` — por tabla: ausente en
  central ⇒ copiar filas; no volátil + más nueva localmente ⇒ `add` (append);
  volátil ⇒ skipped (regenerable); más vieja ⇒ skipped (central gana).
- `prune_volatile_collections(central_db)` — elimina colecciones volátiles
  que exceden `VOLATILE_MAX_BYTES` (1 GB), reportando filas/liberado.

Cableado: `scripts/setup_swarmind.py` paso `_bootstrap_memory()`
(bootstrap → detect → migrar → prune). `memory_config.__post_init__` avisa
con `logger.warning` cuando cae al fallback legacy (visibilidad ERR).

## 5. Contratos (TDD)

`harness/tests/test_memory_bootstrap.py`:
bootstrap crea estructura+config · idempotente · respeta `MEMORY_ROOT` ·
detect encuentra tablas .lance · migrate copia ausentes · migrate append
tabla no volátil más nueva · migrate nunca migra volátiles · migrate no
toca tablas más viejas · prune respeta cap y elimina exceso · config
mergeable con `backup_memory._load_config`.

## 6. Verificación

RED→GREEN + kill-check mutador AST + suite completa + ejecución real en
esta máquina (migración del fork local de 4.8 GB + prune de volátiles).

## 7. Anti-patrones

- Borrar datos de valor sin fusión previa (append + verificación de filas).
- Respaldar caches volátiles (doctrina: regenerables).
- Hardcodear `C:\...` — siempre `Path.home()` + env override.
