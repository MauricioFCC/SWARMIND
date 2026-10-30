# Roadmap y Estado del Proyecto

> Estado actual del sistema Swarmind Harness a 2026-10-15.
> Documento vivo que refleja el progreso, hitos y proximos objetivos.
> **Regla RSV (base_principles v3.6.0)**: se relee este roadmap cada N refactors (>=5)
> y se actualiza con las tecnicas frontera del momento — features SIEMPRE de estado del arte.

## Estado Actual (2026-10-30i)

### Estado 2026-10-30 (Ciclo 11.64 — cierre de pendientes de implementación)
- Pendientes de código cerrados: concurrencia de `EvalSuite`, borrado/refuerzo
  de `CognitionSync`, `stop()` de embeddings, gates M5/M6 de skills.
- Routing: filtro por lenguaje, skill del agente, verbo primario, negaciones,
  typos, guiones y acentos; thresholds de `DifficultyRouter` aplicados.
- Mutación nocturna del core (job `mutation-nightly`).
- Specs de auditoría y arquitectura cerradas con estado explícito.
- Único pendiente de producto: ninguno en `xfail`; quedan decisiones P2 de
  endurecimiento (preview ratchet y Aho-Corasick condicionado a corpus).

## Estado Actual (2026-10-30h)

### Estado 2026-10-30 (Ciclo 11.63 — cierre P2: preview, mutación scoped, PEP 649)
- Allowlist de reglas Ruff preview (10 códigos) con gate propio; `preview=true`
  global descartado por activar 138 reglas ajenas en Ruff 0.16.6.
- Mutación scoped por `git diff` con umbrales por paquete (kernel 90 %,
  domain 75 %, memory_rag 70 %) y job CI adaptado.
- Auditoría PEP 649 con baseline justificado (3 usos de `inspect.signature`) y
  tests de contrato de anotaciones del kernel/domain.
- Pendientes: mutación nocturna completa y endurecer la allowlist preview
  (mover códigos del ratchet cuando lleguen a cero).

## Estado Actual (2026-10-30g)

### Estado 2026-10-30 (Ciclo 11.62 — ola P1/P2 + algoritmos O(n²)→O(n))
- AC-KN5 cerrado: `RequestTracker` (trace_id + timeout tipado) y wiring en
  `agent_dispatcher` y `run_commands` (start/end/error correlacionados).
- mypy strict bloqueante en `harness.kernel` y `harness.domain`; global con
  `-n auto` informativo.
- Ratchet de Ruff preview (baseline 1 272 hallazgos / 20 reglas) + 54 fixes
  seguros aplicados; job CI `ruff-ratchet`.
- Algoritmos: `ts_rank` con Fenwick O(T log m); dedup exacto O(1) en AlphaZoo;
  gate de complejidad con 8N y benchmark `alpha.ts_rank`.
- Investigación de frontera documentada (fórmulas + reglas de decisión):
  `docs/research/frontier-2026-10-30-algorithms.md`.
- Pendientes P2: allowlist de preview en lint, mutación scoped por `git diff`,
  auditoría PEP 649, Aho-Corasick si crece el corpus de reglas.

## Estado Actual (2026-10-30f)

### Estado 2026-10-30 (Ciclo 11.61 — kernel + gate de complejidad + algoritmos)
- Kernel event-driven implementado (`harness/kernel/`) y adoptado por el
  orchestrator vía `KernelBus` (single-loop FIFO, backpressure tipado, replay).
- Gate de complejidad N/2N/4N con baseline portable (`check_complexity.py`);
  job CI bloqueante. 7 benchmarks medidos ≈2.0 (lineales).
- Algoritmos: índice invertido tool→server en MCPManager y dedupe O(1) en
  servers_for_task; hotspot O(n·m) eliminado.
- Arquitectura: contrato F8 `kernel-agnostico` + contratos por paquete.
- Pendientes: AC-KN5 (run_commands/agent_dispatcher al KernelBus), mypy strict
  incremental (P1), ruff preview con ratchet (P2), escala 8N en el gate (P2).

## Estado Actual (2026-10-30e)

### Estado 2026-10-30 (Ciclo 11.60 — Validación E2E + prácticas Python 3.14)
- Flujo end-to-end verificado (smoke, setup, skills, gates, suite).
- Memoria central: cache 2250 MB -> 110 MB (TTL + reclaim de fragments).
- asyncio 3.16-safe + scopes pytest-asyncio + perfiles hypothesis ci/dev.
- Specs: python-314-practices y tdd-mutation-gate.
- Pendientes: mypy strict incremental (P1), ruff preview con ratchet (P2),
  auditoría PEP 649 de get_type_hints, mutación nocturna ampliada.

## Estado Actual (2026-10-30d)

### Estado 2026-10-30 (Ciclo 11.57 — Onboarding validado en Docker)
- Instalación limpia reproducida en `python:3.12-slim` desde el remoto.
- Core sin torch/CUDA (extras `[gpu]`/`[docs]`); instala en ~15 s.
- `new_user_smoke.py` + job CI `fresh-install` + Dockerfile.
- Degradación correcta sin DLL de RuscaDB ni LanceDB (backend memory).
- Suite Linux: 7137 passed / 162 skipped / 0 failed.
- Gate F5 corregido (BOM); baseline 70/929.

## Estado Actual (2026-10-30c)

### Estado 2026-10-30 (Ciclo 11.56 — RaBitQ cableado + tuning por carga)
- `ruscadb_quantize` + `ruscadb_search_bq` importados y usados por
  `RuscaDBStore.search_binary` (KNN 1-bit + oversample + rescore float32).
- `OversampleTuner` ajusta el factor con recall medido vs KNN exacto.
- Migracion de tablas legacy via `ALTER TABLE ADD COLUMN`; indices de
  gobernanza opt-in.
- `--list-contracts` para auditar los contratos F8.
- Limite: sin indice IVF persistente ni `nprobe` (fase 2 upstream).
- Ruff 0, Vulture 0, gate F1/F2/F4/F6/F7/F8 OK.

## Estado Actual (2026-10-30b)

### Estado 2026-10-30 (Ciclo 11.55 — Cierre de gaps parciales)
- Gobernanza indexada: columnas `source/trust_tier/session_id/derived_from/
  write_gate_verdict` (fallback metadata en tablas legacy).
- Reconciliacion SSGM programable (`reconcile_every`) con tamper/duplicados.
- Eviccion por calor STM/MTM/LTM + vida media por coleccion.
- Umbral adaptativo por prompt (vCache) con feedback y persistencia.
- Contratos declarativos de dependencias (F8, `architecture_contracts.toml`).
- Batching de inserts (`WriteBatcher`) y lecturas opcionales por actor.
- Unico gap restante: RaBitQ/IVF-PQ (bloqueado por el C-ABI de RuscaDB;
  contrato en `docs/specs/ruscadb-ivf-pq.md` §6).
- Ruff 0, Vulture 0, gate F1/F2/F4/F6/F7/F8 OK.

## Estado Actual (2026-10-30)

- **Siguiente accion concreta (gap upstream #1)**: exponer `ruscadb_quantize` + `ruscadb_search_bq` en el C-ABI de RuscaDB (`docs/specs/ruscadb-ivf-pq.md` §6) para habilitar KNN binario + rescore. Trigger: memoria vectorial > 256 MiB, p95 > 50 ms o `RUSCADB_BQ=1`.

### Estado 2026-10-30 (Ciclo 11.54 — Cierre de gaps del research)
- Write gate SSGM (`MemoryGuard` inyectable, cuarentena / strict) y refuerzo
  por uso (`record_access`, `last_accessed`).
- Cache semantico version-keyed (`dataset_version`, `invalidate_version`) y
  fail-closed (`verified=True`).
- Actor de escritura single-writer con cola bounded y `MemoryBackpressureError`.
- Gate de arquitectura con ratchet de deuda (F7) y baseline congelado.
- Gaps restantes: RaBitQ/IVF-PQ (bloqueado por FFI de RuscaDB), columnas de
  gobernanza, eviccion por calor, umbral aprendido, reconciliacion programada.
- Ruff 0, Vulture 0, gates verdes.

## Estado Actual (2026-10-29)

### Estado 2026-10-29 (Ciclo 11.53 — Puertos/adaptadores y memoria gobernada)
- **Clean Architecture real**: `LanceVectorStore.__new__` devuelve el adaptador
  RuscaDB (sin `setattr`); `VectorStorePort`/`TextSearchPort` con conformance en
  CI y `get_vector_store()` como único punto de construcción.
- **Retrieval gobernado (OWASP ASI06 / SSGM)**: cuarentena deny-by-default,
  `min_trust`, decaimiento temporal (`half_life_days`, default 30 d) y
  anotaciones de confianza en `search`/FTS/hybrid.
- **Cache semántico persistente** con métricas y purga delegada al store.
- **Async I/O**: `AsyncRuscaDBStore` completo + `HybridRetriever.aretrieve`.
- **Gate de arquitectura**: F1/F2/F4 bloqueantes en pre-commit y CI; 2 ciclos
  reales corregidos; deuda de tamaño (824) declarada advisory.
- Ruff 0, Vulture 0, 7236 tests recolectados, lotes afectados verdes.
- Docs: ADR-0104, research frontier 2026-10-29, auditoría 2026-10-29.

## Estado Actual (2026-10-25)

### Estado 2026-10-25 (Ciclo 11.45 — Potencial completo de RuscaDB)
- RuscaDB: extension del C-ABI (open_opts, create_index, update/delete/get por RecordId, blob CAS, integrity, backup, last_lsn, explain).
- RuscaDBStore: FTS sobre columna text, indices, RRF hibrido, grafo BFS, blob attach, operacional.
- Frontier: AdaptiveRetriever (arXiv:2403.14403), GraphRAGRetriever (arXiv:2410.05779 / 2404.16130), SummaryCommunication (arXiv:2607.27942).
- Comando !rag search (dual-level).
- Ruff 0, Vulture 0, tests verdes.

## Estado Actual (2026-10-17)

### Estado 2026-10-17 (Ciclo 11.22 — Optimalidad de memoria: feedback + TTL proactivo + paridad)

- **Diagnóstico con evidencia**: 99.7% del almacenamiento de la memoria central
  eran caches regenerables (`semantic_cache` 138 MB/5201 fragments +
  `agent_workspace_logs` 48 MB) y las 13 colecciones de **valor** (información
  que sostiene las decisiones) sumaban ~0.3 MB, casi todas schema-only.
- **2 correcciones de diseño por IDP** (no reimplementar):
  - `SemanticCache.clear_expired()` **ya existía y era proactivo** — la brecha
    era que **nadie lo invocaba** ⇒ fix: barrido probabilístico en `set()` cada
    `SWEEP_EVERY_N_SETS=100` inserts (no un `purge_expired()` duplicado).
  - `dispatch()` no puede puntuar éxito; ya existía el hook post-run
    `record_skill_outcome(skill_name, success)` ⇒ el seam correcto era ese hook.
- **Entregables (4 items, 15 contratos)**: `feedback_scorer.py`
  (`score_outcome` → `skill_effectiveness` + `agent_performance`, DI +
  degradación suave, cableado backward-compatible en `record_skill_outcome`) ·
  `memory_parity.py` (`audit_parity` → `ParityReport`, umbral `is_imbalanced`,
  no lanza con path inexistente) · sección **no fatal** `memory_parity` en
  `verify_swarmind_setup.py` (sigue `SETUP OK`) · `VOLATILE_MAX_BYTES`
  **1 GiB → 256 MiB**.
- **TDD + verificación**: RED observado en cada check; kill-check **5 killed /
  0 survived**; test end-to-end puebla **AMBAS** colecciones de valor;
  `ruff` 0, archivos tocados 114 passed / 0 failed.

## Estado Actual (2026-10-15)

### Estado 2026-10-15 (Auditoria del acople OpenCode: agentes lanzables, plugin V2, MCP y doctrina global)

- **Acople 1:1 con OpenCode verificado con evidencia runtime** (`opencode debug agents`,
  `opencode mcp list`, `opencode plugin list`, `opencode.log`) y reparado en 4 puntos:
  1. **Agentes lanzables** — 22 de 24 agentes no declaraban `mode` y caian al default V2
     `primary` (fuera del catalogo de subagentes): solo 7 de 24 eran lanzables y
     **8 skills de 40** enrutaban a agentes inalcanzables (`architect` x2,
     `product-manager`, `platform-engineer`, `security-engineer`, `evolve-engineer`,
     `evolve`, `coordinator`). Hoy: 24 agentes en `mode: subagent`, `coordinator` en
     `all` (primario + lanzable) y `permission.task` del coordinator por ID exacto
     (antes `builder-*` no matcheaba ningun ID). Runtime: **25 `subagent` + 1 `all`**.
  2. **Plugin V2** — `compaction-context.js` seguia en la API de plugins V1 y OpenCode lo
     rechazaba (`PluginModule.LoadError`) en TODOS los proyectos: el hook de compactacion
     estaba muerto. Portado a `export default { id, setup }` + `ctx.session.hook("compaction")`
     (sin dependencias npm). Runtime: `swarmind.compaction-context` cargado con su ID.
  3. **MCP `DEFAULT_ACTIVE` 3/3** — `sequentialthinking` moria con
     `failed: Request timed out` (npx en frio vs 30 s). SSOT fija
     `@modelcontextprotocol/server-sequential-thinking@1.0.0` y
     `mcp_opencode.merge_into_config` garantiza `experimental.mcp_timeout >= 90000`.
     Runtime: `fetch`/`time`/`sequentialthinking` **connected**.
  4. **Doctrina AGENTS.md universal** — antes solo existia dentro de SWARMIND.
     `sync_opencode_global` la copia al global (`~/.config/opencode/AGENTS.md`, inyectada
     en cada sesion) y `deploy_all.deploy_agents_md` genera un AGENTS.md delgado en la raiz
     de cada proyecto (marca `SWARMIND:generated`, NUNCA pisa un AGENTS.md ajeno).
     Como `AGENTS.md` es el estandar compartido por OpenCode, Claude Code y Codex, la
     doctrina viaja a cualquier harness sin duplicar SSOT.
  5. **Comandos de OpenCode** — `.opencode/commands/` (`/mcp`, `/dispatch`, `/ver`)
     sincronizados al global.
- **Capa modular**: lo especifico de OpenCode (`mode`, plugin API, `opencode.json`) vive
  cableado a su runtime; lo portable (AGENTS.md, agentes con frontmatter estandar) se
  exporta por los mismos caminos que ya usan `claude_adapter`/`codex_adapter`.
- **Contratos TDD**: `test_opencode_runtime_contract.py` (13: agentes lanzables,
  `SKILL_TO_AGENT` alcanzable, forma V2 del plugin, comandos) + 4 de `mcp_timeout` +
  6 de `deploy_agents_md`; ruff 0. Detalle completo: `docs/.MEJORAS_SWARMIND.md` 11.12.
- **Refactor 11.13 (este ciclo)**: capa universal multi-harness reparada
  (`converter_base` filtra `*.agent.min.md` y descubre `SKILL.md` reales;
  `_copy_agents`/`_copy_skills` eliminan 4 loops duplicados; índice Claude
  idempotente), flota del coordinator como contrato SSOT, pins
  `mcp-server-fetch/time@2026.10.10`, `mcp_timeout: 90000` en template + 11
  configs, AGENTS.md con números reales. Suite **6745 passed** + gates en verde.
  Detalle: `docs/.MEJORAS_SWARMIND.md` 11.13.
- **Refactor 11.14 (este ciclo)**: acople migrado a **config NATIVA OpenCode V2**
  (guía oficial `migrate-v1/`): `providers`+`package aisdk`+`settings`,
  `agents`+`permissions` lista (acciones `shell`/`subagent`), `agents.title.model`
  (reemplazo de `small_model`), `mcp.timeout.{catalog,execution}`, modelos con
  `capabilities`/`limit.context`, plugin en `.opencode/plugins/` + limpieza del
  legado en los 10 espejos. **Fix del error de compactación en 200K**: el
  `buffer: 2000` absoluto (1% de holgura) se retiró para heredar el default
  proporcional 10% del límite (2K locales / 20K cloud) — `compaction.model` NO
  existe en V2 (la sesión compacta con su propio modelo). Features de frontera
  nuevas: `permissions` globales (push→ask, sudo→deny), `policies` sudo
  hard-deny, `watcher.ignore` anti-ruido. Checkers duales V2+V1; `formatter`
  evaluado y rechazado con evidencia (277/325 tests se reescribirían).
  Detalle: `docs/.MEJORAS_SWARMIND.md` 11.14.
- **Frontera 11.15 (este ciclo)**: 2 capacidades del estado del arte 2026
  ausentes en el harness, verificadas con TDD adversarial mutante.
  (1) **Ejecución durable con Resume Contract** (`harness/orchestrator/
  durable_run.py`, arXiv 2608.03836 — LangGraph/CrewAI medidos INCUMPLENDOLO):
  `DurableRunStore` con transiciones atómicas, claim consume-once
  **cross-process** (un solo racer gana el efecto), `resume_plan` determinista
  (PENDING→re-ejecuta, RUNNING→`indeterminate` nunca re-ejecución ciega,
  COMPLETED→prefix jamás repetido) y respuestas HITL consume-once.
  (2) **Graduación de evals a regresión** (`harness/evals/regression_tracker.py`,
  Anthropic "Demystifying evals" 2026): baseline histórica por tarea, alerta
  nombrando la tarea que cayó >1.0pp, saturación al 100%, historial JSONL
  append-only. Kill-check con el mutador AST propio: **6/6 mutantes
  semánticos muertos** (el superviviente inicial expuso `mkdir(parents=False)`
  → test nuevo). Detalle: `docs/.MEJORAS_SWARMIND.md` 11.15.
- **Frontera 11.16 (este ciclo)**: **minería alpha de frontera (0 capacidad →
  paquete `harness/alpha_mining/`)** con los 5 sistemas alpha del estado del
  arte, verificada con TDD adversarial mutante. (1) **DSL total** (`factor_dsl`:
  Hubble — el LLM solo emite JSON reconstruido a AST validado, evaluador sin
  crashes con ceros/NaN/división; AlphaAgent — complejidad `MAX_NODES=32` +
  Jaccard de genes abstractos; AlphaMCTS — FSA con `abstract_gene` y forbidden
  top-k). (2) **Evaluador con umbrales NVIDIA** (`factor_eval`: IC dual
  Pearson+RankIC, `p < 0.05` estricto, score acotado [0,1] con input hostil).
  (3) **Zoo family-aware** (`alpha_zoo`: JSONL estricto, KB de fallos por modo,
  `is_similar` pre-eval, top-k con `per_family_cap`). (4) **Loop
  signal→code→eval + MCTS-UCT con branching real** (`mining_loop`: hermanos
  compitientes y exploración observable — la cadena lineal era código muerto —,
  `crossover`/`mutate`/`evolve_pool` por recompensa, determinista sin rng).
  **Kill-check 2 rondas**: ronda 1 6/14 → 6 fugas reales de spec + 1 corrección
  de source donde el mutador tenía razón (p-value al canon) → ronda 2
  **13/16 + 3 equivalentes = 100% mutantes semánticos**; 81 contratos nuevos.
  Detalle: `docs/.MEJORAS_SWARMIND.md` 11.16.
- **Frontera 11.17 (este ciclo)**: **sistemas del milenio →
  `harness/complex_problems/`** (AlphaProof Nature 2025-11, AlphaEvolve
  PNAS 2026-09, AlphaProof Nexus arXiv 2605.22763 9/353 Erdős): los 5
  mecanismos "rompe-límites" de su configuración, con DI completa y sin
  rng. (1) **Escalera de presupuesto** (`budget`: rungs monotonamente
  crecientes + cap global 3000 episodios — más compute cuando la dirección
  ya se afinó, failure-spend acotado). (2) **Verificador formal inyectado
  + anti-malformalización** (`verifier`: Protocol duck-typed; el statement
  real debe conservar sus marcadores o verificar NO cuenta). (3) **Elo
  suma-cero** (`sketch_store`: población compartida de sketches, `top(k)`
  con empate determinista). (4) **P-UCB** (`p_ucb`: cobertura garantizada
  antes de explotar, `MappingProxyType` externo). (5) **Ledger monotono**
  (`progress`: idempotente, rollback siempre error, JSONL append-only con
  `linea N` en corrupción). (6) **AttackLoop integrador** (`attack`:
  grant → hook → integridad → verificación → gasto; re-ataque = 0
  episodios; cap corta antes de `max_attempts`). **Kill-check 2 rondas**:
  ronda 1 13/17 → 4 fugas de spec en los CONTRATOS (top por rating,
  exploración fraccional, default `cost_per_attempt` nunca ejercitado,
  `spent` del re-ataque) → ronda 2 **17/17 + 2/2 = 19/19 (100%)**; 75
  contratos nuevos (RED: 6 ModuleNotFoundError).
  Detalle: `docs/.MEJORAS_SWARMIND.md` 11.17.
- **Frontera 11.18 (este ciclo)**: **round skills/agentes/MCP** —
  auditoría determinista de la capa MCP y defensa anti inyección en
  prosa de skills (OWASP MCP Top-10 2025 + arXiv 2608.29596).
  (1) `harness/security/mcp_security_scan.py`: parser JSONC real +
  5 categorías OWASP (shell crudo, pin ausente = rug-pull, secretos en
  env con masking, http sin TLS, endpoints internos = superficie SSRF);
  spec corregida contra la config real (argv-list, `environment`,
  `mcp.servers`). (2) `harness/security/skill_guard.py`: frontmatter
  obligatorio + 7 patrones de prosa hostil; **dogfood en las 42 skills:
  0 hostiles + 5 `domain` faltantes de skills preexistentes corregidos**.
  (3) Skills `mcp-security` + `alpha-mining` (SKILL.min + registry sha256
  + routing a agentes). (4) Agente **`alpha-miner`** con contrato de
  flota completo (mode, min variante, permisos del coordinator,
  delegation policy). Kill-check 5/5 (100%); 34 contratos nuevos
  (RED: 2 ModuleNotFoundError). Detalle:
  `docs/.MEJORAS_SWARMIND.md` 11.18.
- **Frontera 11.19**: **ADR fr-0001 — politica de costos de routeo**
  (STEER-lite cost-aware, mandato del usuario). `cost_policy.py`:
  escalera free→small→standard→frontier; escalación por costo
  INCREMENTAL (umbral $0.05) con escalón intermedio `standard`; tier
  `free` para complejidad <= 2 + output <= 2000; veto de presupuesto de
  salida (> 4000 tokens => vetar modelos ultra-caros salvo `force_tier`);
  voting k-in-1 con el tier de menor input cuando gate >= 70 y
  confidence < 0.7. **Acoplamiento aditivo 0-regresión**:
  `CascadeRouter.plan_cost_aware_escalation` +
  `session_affinity.should_switch_on_cache_health` (umbral 0.60
  alineado con `TokenUsageTracker.cache_health`). 28 contratos (RED);
  kill-check 11/11 muertos + 5 equivalentes = 100% efectivo. Detalle:
  `docs/.MEJORAS_SWARMIND.md` 11.19.
- **Frontera 11.20**: **memoria colectiva en 1ª instalación** (spec
  `specs/memory-lifecycle.md`, research anexada: arXiv:2607.21503
  memoria-ciclo-de-vida + políticas de caches 2026 — qué NO guardar).
  `memory_bootstrap.py`: `bootstrap_memory` (SSOT
  `~/Documents/Memory_Proyects` + `.swarmind_config.json` idempotente,
  override `MEMORY_ROOT`, cross-platform), detección y migración de forks
  locales (append por mtime, volátiles jamás), `prune_volatile_collections`
  (cap 1 GB/caché regenerable). Cableado en `setup_swarmind.py` paso 4 +
  warning de fallback en `memory_config` (bug raíz: config SSOT ausente ⇒
  fork de 4.7 GB). **Ejecución real: -14.29 GB** (prune 9.59 GB +
  fork 4.70 GB); INCIDENTE: 13 tablas locales sin `_versions/*.manifest`
  (pérdida externa) ⇒ recuperación con pylance leyendo fragments ⇒
  parquet ⇒ fusión al central 13/13 (65 filas de valor, 41 de cognición
  que se habrían perdido) + archivo de seguridad en `backups/`. 17
  contratos (RED: ModuleNotFoundError), cobertura 100% del módulo;
  kill-check 2/2 reales (100%) con no-ops excluidos honestamente.
  Detalle: `docs/.MEJORAS_SWARMIND.md` 11.20.
- **Frontera 11.21 (este ciclo)**: **auto-actualización anti-reversión
  implementada** (`specs/self-update.md` → accepted+implemented). Research
  anexada: **ADR-0010 anti-rollback** (`max_seen_version` monotónico en el
  journal + downgrade solo deliberado `allow_downgrade`+`justification` ⇒
  `downgrade_forced` auditable) y journaling *roll forward* con **prefix
  property** = el invariante de `merge --ff-only` (InterSystems/SQLite WAL;
  `branch.*.mergeoptions --ff-only` como defense-in-depth). Módulo
  `harness/self_update/` en 3 piezas SRP (`core` 451 LC + `journal` 108 +
  `versions` 33), CLI `scripts/self_update.py` (`--check/--apply/--audit`)
  y **paso 7 del setup** con degradación suave que nunca bloquea. Gate
  central: `floor = max(local, max_seen_journal)` y `remote < floor` ⇒
  bloqueado aunque `remote > local`; `max_seen` **nunca baja**. Solo mutan
  worktree `updated`/`downgrade_forced` vía ff-only, con intento WAL
  registrado antes del merge. 20 contratos git reales (bare locales, sin
  red) + **6 tests fake-git** (runner en memoria: 4.2 s vs 171 s) que
  cubren todos los guards. **Kill-check en 3 rondas** (ronda 1 reportó
  100% pero era engañoso: el harness numeraba posiciones en BFS y mutaba
  en DFS ⇒ mal etiquetado) → ronda 2 expuso **7 gaps reales de aserción**
  → ronda 3 tras reforzar 6 contratos + añadir 3: **44/44 = 100%**
  (core 33 + versions 2 + journal 9, 0 supervivientes, 2 equivalentes
  por construcción documentados). Cobertura **100% del paquete** (273
  stmts) con los 24 tests rápidos (2.9 s); marker `slow` solo en los 15
  de integración git. RED: ModuleNotFoundError. Detalle:
  `docs/.MEJORAS_SWARMIND.md` 11.21. **Gate 11.21:** suite completa
  **7075 passed, 0 failed** (527s; base 7036 + 39); kill-check **44/44 =
  100%**; cobertura **100%** del paquete (273 stmts) con los 24 tests
  rápidos; `ruff` 0 · `vulture` 0.
- **Gate 11.21:** suite completa **7075 passed, 38 skipped, 16 xfailed,
  0 failed** (527s; base 7036 + 39 de `test_self_update.py`). Kill-check
  **44/44 = 100%**. Cobertura **100%** del paquete `harness/self_update/`
  (273 stmts) con los 24 tests rápidos (2.9s). `ruff` 0 · `vulture` 0.
- **Propagación 11.21 (fix de drift SSOT):** `_HARNESS_INCLUDE` es lista
  blanca estática ⇒ el módulo nuevo no viajaba al global (mismo bug del
  fix precedent `ea092dc0`). Auditoría: `failure_registry` lo importa
  `evolve_loop/failure_distiller.py` (ya propagado) ⇒ **ImportError real
  en el global**; `alpha_mining` lo referencian 3 skills. Añadidos
  `self_update` + `failure_registry` + `alpha_mining` + **2 contratos**
  (explícito + `test_harness_include_sin_drift_de_dependencias`
  auto-detectable, RED acusó `['failure_registry']`). Sync 912 archivos,
  import con provenencia global verificada, `SETUP OK`.
- **Pendiente (evals de frontera)**: LLM-as-judge con escape "Unknown" +
  scorecards por corrida (Anthropic 2026); ACP lo cubre `packages/acp` de
  OpenCode (el harness Python no necesita implementarlo — validar `opencode
  acp` cuando el binario esté en PATH).

## Estado Actual (2026-10-14)

### Estado 2026-10-14 (Restauracion post-reinstalacion de SO + Python 3.14 + oraculo PBT cross-platform)

- **Python 3.14 acoplado** — `.python-version` = 3.14; `.venv` a 3.14.7 (uv); PATH de usuario apunta a `Python314` + `Scripts` (eliminado el `Python312` stale que caia al stub de Microsoft Store); classifier 3.14 en `pyproject.toml`; CI (`ci`/`mutation`/`security-scan`/`skills-quality`/`release`) alineado a 3.14 sin drift con el pin; `requires-python >=3.12` se mantiene como piso.
- **Oraculo PBT funcional en Windows** — `SandboxExecutor.run_script(require_project_deps=True)`: cuando el backend docker no puede aportar las deps del proyecto (no-POSIX: el site-packages trae extensiones nativas `.pyd`, p. ej. `hypothesis._native`), el script corre en el interprete host con sandbox nativo (Job Object / subprocess). `pbt_stage` lo activa; +5 tests. Evidencia: `run_pbt_stage(good).passed=True`, `(buggy).passed=False`. Mutation sigue en docker (no requiere deps).
- **Agentes `.agent.min` ocultos (OpenCode V2)** — 24 artefactos minificados aparecian como agentes duplicados en V2 (`<rol>.agent.min`); `hidden: true` en el frontmatter + inyeccion en `compile_agents.minify_agent` (el harness los sigue leyendo como prompt pre-compilado).
- **Pre-commit re-activado** — `install_hooks.py` ahora resuelve `core.hooksPath` (`.githooks`); el pre-commit (QA + sync del opencode global) vuelve a ejecutarse de verdad en cada commit.
- **Entorno restaurado (reinstalacion de SO)** — `uv` 0.13.1 + `uv sync --extra dev`; GPU CUDA (torch 2.13.0+cu126, RTX 4060 via `enable_gpu.py`); Docker daemon; cerebro+motor sincronizados al opencode global.
- **Flota local alineada a lo INSTALADO (2026-10-14)** — regenerado desde la SSOT `local_models.yaml` (`render_local_models.py`): `llama-swap.yaml`, `.opencode/opencode.json` y `~/.config/opencode/opencode.jsonc` en sync (gate `--check` verde). `fleet_manifest.FLEET` + `.opencode/config/ollama_models.yaml` alineados a los 5 modelos instalados: fast `phi-4-mini-reasoning-q4-k-m`, coding `qwen3-4b-thinking-2507-q4-k-m`, quality `mimo-v2-6-distill-qwen-9b-gguf-iq4-xs`, embedding `qwen3-embedding-0-6b`, deep `ternary-bonsai-2-27b-ptq1-0`. RETIRADOS qwen3.5-4b / phi-4-mini-instruct / qwen2.5-coder-3b / deepseek-r1-distill (no instalados). `test_fleet_config_drift` **5 passed** contra el server real (antes rojo).
- **Router de targets RE — filosofia REA ("la herramienta correcta")** — `harness/reverse_engineering/target_router.py`: dado un target (ruta/URL) elige el METODO REA + el PROVIDER (hopper|ghidra|ida, override `REA_ANALYSIS_PROVIDER`) + la EVIDENCIA esperada, por tipo detectado con magic bytes/ext/URL (nativa PE/ELF/Mach-O, Go, .NET/CLR, JS/Electron `.asar`, website, captura HAR, SQLite). Guardrail etico HARD (solo targets propios/autorizados) y `unknown` -> rechazo (0 claims sin artefacto; no adivina). 25 tests (deteccion, provider env, adversarial guardrail). Wire con el skill `reverse-engineering` + server MCP `rea`.
- **Catalogo MCP ampliado (la herramienta correcta por dominio)** — `harness/tools_sandbox/mcp_servers.yaml` **8 → 23 servers** con comandos/tools VERIFICADOS contra cada repo oficial (regla del propio archivo): RE (`rea` con tools afinadas segun la SSOT del skill; `rc_devtools`, `ghidra_mcp`, `radare2`), proposito general (`fetch`, `time`, `git`, `sequentialthinking`, `playwright`, `firecrawl`, `notion`, `kubernetes`) y FRONTERA (`chrome_devtools`, `sentry`, `supabase`, `browserbase`). Catalogo de candidatos por dominio documentado (cloudflare, huggingface, figma, stripe, exa, tavily, aws, datadog, qdrant, dbt...). `target_router` mapea `target -> mcp_servers`.
- **Cableado skills + agentes + HERRAMIENTAS (siguiente nivel)** — `harness/tools_sandbox/mcp_catalog.py` (tarea -> servers MCP por keyword, sin inventar) + `DispatchPlan.tools` (el dispatch aplica agente + skills + **herramientas**); `harness/tools_sandbox/mcp_opencode.py` traduce la SSOT MCP a `mcp.servers` de OpenCode y el **acople oficial `deploy_all.py --sync-global`** lo registra en el global (23 servers; 3 activos). Wiring e2e probado (`test_harness_wiring_e2e`: skills dual, agentes, SSOT->opencode, router->servers, dispatch con tools). opencode ya expone `fetch`/`time`/`sequentialthinking`.
- **Organizacion de herramientas + skill `mcp-toolkit`** — cada server en su categoria (`mcp_servers.yaml: categories` + `mcp_catalog.CATEGORIES`, espejo) y cableado skill<->herramienta (`SKILL_TO_TOOLS`/`servers_for_skill`); nueva skill **`mcp-toolkit`** (PEC) que documenta el catalogo por categoria y la regla de seleccion ("la herramienta correcta"). Registro + routing actualizados (`skills_registry.yaml` + `SKILL_TO_AGENT`/`DOMAIN_SKILLS`/`DOMAIN_KEYWORDS`), digests regenerados. Propagado con `deploy_all --sync-global`.
- **`!mcp` — catalogo de herramientas en el CLI** — `!mcp list` (catalogo por categoria), `!mcp for <tarea>` (herramientas aplicables via `servers_for_task`), `!mcp skill <nombre>` (`servers_for_skill`); +4 tests. Ademas, validacion E2E de imports de los 22 subpaquetes del harness (todos OK) + gates de CI corridas en local (ruff/bandit/safety/compile).

## Estado Actual (2026-10-12)

### Estado 2026-10-12 (ADR-0103 Frontera Simple: enrutamiento aprendido + coordinador minimo + token economics medido)

- **ADR-0103 + spec SDD** (`docs/adr/adr-0103-frontera-simple-2026.md`, `specs/adr0103-frontera-roadmap.md`) — investigacion frontera 4 frentes (harness engineering arXiv:2609.00006, skill routing arXiv:2603.22455, token economics arXiv:2508.21433/2607.15516, coordinador next-gen) + 8 acciones priorizadas por ROI.
- **Cierre del refactor (tecnicas frontera)** — `PipelineRouter` (`harness/orchestrator/pipeline_router.py`): cascada SLM→fallback en complejidad timida→frontier (RouteLLM/cascade), integra TriageSLM + cache-shape + `TelemetryGate` (hit-rate 0.80); telemetria cableada en `agent_dispatcher` (R10 medido); **veto duro de anti-triggers** en el router (`hard_veto_score`/`apply_hard_veto`, Codex #34712: el routing ignora prosa negativa); MAG cleanup (`SHORT/MEDIUM/LONG_TEXT_THRESHOLD_CHARS`); `coordinator.agent.min.md` regenerado consumiendo `coordinator_policy.yaml`; 4 skills restantes a PD (atdd-spec 133→85, process-over-tools 139→88, frontend-uiux 174→113, diagram-design 198→120). 98 tests nuevos/regresion green.
- **WS-A token economics** — `TokenTelemetry` (`harness/observability/token_telemetry.py`: record_usage por rol, hit_rate, gate_ok 0.80, report/to_json) + `build_cache_shaped_prompt` (orden canonico tools>system>static>dynamic con breakpoint de cache, `harness/orchestrator/prompt_cache_shape.py`) + **observation masking DEFAULT ON** (env `SWARMIND_OBS_MASKING_DISABLE`). 33 tests.
- **WS-B coordinador minimo** — `coordinator.md` 273→**54 lineas** + `coordinator_policy.yaml` (SSOT: delegation/budget/verification/memory/output_contract/token_economics/antipatterns/tdd_authority + doctrina preservada). 8 tests.
- **WS-C routing aprendido** — `TriageSLM` (small_model→JSON intent/complexity con cascada fallback al DifficultyRouter, `harness/orchestrator/triage_slm.py`) + **hidden-body router** (puntuar leyendo el cuerpo de skills/agent .md, `hidden_body.py` pesos 0.5/0.5) + **fan-out cap 5** (`SWARMIND_MAX_FANOUT`, XLarge 11 solo explicito). 72 tests.
- **WS-D seguridad skills** — digests `sha256` en `skills_registry.yaml` (36/36) via `scripts/hash_skills_registry.py`; `validate_skills.py` verifica content drift (supply-chain hardening, SkillsMP/CVE-2025-59536). 11 tests.
- **WS-E principios** — regla N1 **`RSV`** (Roadmap Sync & Retrospectiva: cada N refactors leer roadmap + retrospectiva de calidad + features de frontera; roadmap vivo) en base_principles v3.6.0 + min + full. 33 tests de integridad.
- **Skills a progressive disclosure (SkillsBench arXiv:2602.12670 "focused beats comprehensive")** — risk-execution 236→71, alpha-research 218→48, con `references/` (6 modulos); doctrina 0 lineas perdidas.
- **Agent-Native Documentation Engineering** — `INDEX.md` con frontmatter parseable en architecture/development/technical; README.md ES con indice por capas; "explicit beats implicit"; 61 links OK.
- Suite completa: **6268 passed, 34 skipped, 13 xfailed** (3 fallos ambientales `test_fleet_config_drift` = local_only, skip en CI).

## Estado 2026-09-30 (hito anterior)

### Estado 2026-09-30 (flota frontera 2026 + ctx 16K + escalado por verificación)

- **Flota local frontera 2026** — SSOT medida en `harness/model_router/fleet_manifest.py` (6 modelos con id/tier/`num_ctx`/`vram_mb`/`keep_alive`): fast `Qwen3.5-4B UD-Q4_K_XL` (8K), quality `MiMo-V2.6-Distill-Qwen-9B IQ4_XS` (4K), coding `JackOD-9B-Coder IQ4_XS` (4K), reasoning `Ornith-1.5-9B Q4_K_M` (4K), embedding `qwen3-embedding:0.6b`, vision `qwen3-vl:4b`. `recommend_num_ctx`/`footprint_mb` derivan del manifiesto; `.opencode/config/ollama_models.yaml` es el cableado de runtime validado por `test_fleet_manifest.py`.
- **Ventana 16K por servidor (libera 17.4 GB)** — `scripts/enable_gpu.py` persiste cinco topes anti-OOM: `OLLAMA_CONTEXT_LENGTH=8192`, `OLLAMA_MAX_LOADED_MODELS=1`, `OLLAMA_NUM_PARALLEL=1`, `OLLAMA_FLASH_ATTENTION=1`, `OLLAMA_KV_CACHE_TYPE=q8_0` (9B a 16K baja de 5.7GB a 5.15GB con KV comprimida). Elimina las variantes "16k baked"; el cliente igual envía `options.num_ctx`.
- **Escalado por verificación (ADR-0102)** — `harness/model_router/escalation_policy.py`: verificador estructural barato + confianza verbalizada → `accept`/`escalate` (fast→quality→coding→reasoning)/`cloud`; infra prerequisito para calibrar por isotonic con el journal etiquetado (verificar > clasificar, MetaRoute; UCCI small→large).

### Estado 2026-09-08/09 (ADRs 0074-0083 + agent-rigor + merge a main)
- **PR #16 mergeado a `main`** (`d3934fe`): required {lint, test, security} verdes; CodeQL v4; 2 hilos resueltos (ellipsis→NotImplementedError + falso positivo Enum).
- **5276 tests** (211 archivos), **35 skills** (nueva `agent-rigor`), **23 agentes**
(nuevo `platform-engineer`), principios v3.3.0 (ADV verificación adversarial).
- **ADR-0083 Roles/procesos élite (APLICADO)** — agente `platform-engineer` (thinnest viable platform, DORA SLO) + `FeatureFlags` (`SWARMIND_FF_*=1`, merge≠release) + spec como pitch (`appetite`/`boundaries`/RFC en template) + postmortem blameless (`specs/postmortem_template.md`) + principios v3.3.0 (ADV atacante/steelman/juez, SWE-ABS, RvB) + **limpieza de 7 monolitos sombreados** (~4500 líneas muertas; la migración a paquetes nunca borró los originales; 433+68 tests verdes; resta `agent_kpi_tracker.py` 713L).
- **ADR-0076 Tooling Linux-first (APLICADO)** — `tool_output_filter.py` (wrapper rtk −90% output bash, opt-in) + `idempotency_guard.py` (dedup por key+hash, replay cache) + `structured_enforcer` strict keys (anti-troyanos) + `TgrepBackend` (Microsoft, opt-in); principios TOOLING (Python/bash, PowerShell prohibido por mojibake UTF-8); dump `Randon search 9-8-2026.md` destilado (rtk 79K★, tgrep, agentic=distributed systems, K2 Horizon diferido).
- **opencode local por defecto** — `"model": "llamacpp/jackod-9b-coder-iq4-xs"` + `"small_model": "llamacpp/qwen3-5-4b-gguf-ud-q4-k-xl"` vía provider `llamacpp` (llama.cpp / llama-swap en `http://127.0.0.1:11434/v1`, OpenAI-compatible) + 6 modelos registrados (nombres cortos: 4B fast, MiMo quality, JackOD coding, Ornith reasoning, embedding y vision) + `agent.*.permission.task` granular (coordinator primary; builder/guardian/scientist least-privilege).

### Estado 2026-09-06 (ADRs frontera 0065-0067 + llm-grep + gitignore ADRs)

- **ADR-0065 Segundo Cerebro (PROPUESTO)** — overlay `graph_overlay.py` SurrealDB solo aristas, LanceDB sigue SSOT; router local-first → nube solo `is_heavy()`.
- **ADR-0066 Prompt-cache TTL (PROPUESTO)** — prefijo estable + prohibido cambio modelo mid-sesión + `time_to_live_s` (chat 3600 / API-subagente 300) + métrica Effective-Input-Price.
- **ADR-0067 LLM-grep frontera (APLICADO)** — `harness/memory_rag/llm_grep.py`: ripgrep-first → ast-grep condicional → `HybridRetriever` último recurso; salida `ruta:linea` + 2 líneas, dedup `(path,line)`, `GrepBudget`, `RouteReport` con alerta `semantic_ratio>20%`. Tests `test_llm_grep.py` **12 passed**; regresión hybrid **22 passed**; ruff 0.
- **.gitignore**: `docs/src/es/adr/` local-only (segunda capa junto a `.githooks/pre-push`); versionado local explícito con `git add -f`.
- **Deuda doc detectada**: `docs/src/es/adr/README.md` indexa hasta 0041, existen 0042-0067 (26 ADRs sin índice); `docs/src/en/adr/` vacío; `estado.md` cabecera anclada a 2026-08-11.
- **ADR-0068 Cascada STEER + salud cache (APLICADO)** — `harness/model_router/cascade_router.py` (small→frontier si confianza<0.7, escape_hatch, costo por intento) + `TokenUsageTracker.cache_health` (flag bug estructural si hit<60% con volumen≥10K). TDD: `test_cascade_router.py` 10 + tracker 44; mutante M-gate verificado muerto; ruff 0. Personal auditado: `deploy_local.json` ignorado, 0 secretos/paths en `harness/`.
- **ADR-0070/0077 Re-anclaje + taxonomía + TDD adversarial (APLICADO)** — `harness/memory_rag/reanchor.py` (bloque `<<RE-ANCHOR>>` post-compaction: N1+rol+skills+estado, SC-aware; summary retiene 17%, bloque restaura >90%) + `base_principles.md` v3.1.0 (RPA re-pin post-compaction, CPD checklist competición 28.6%+15.5% design/boundary, taxonomía CHECK/GUIDE 8 categorías con IDs estables; TST+PBT ampliados: AdverTest, mutantes MS≥70/85, pairwise t=2→6, BVA, PROBE, MR metamórficas, fuzz). TDD: `test_reanchor.py` 7; research 3 tracks + testing frontera (AdverTest +8.56%, PROBE +9.79pp).
- **ADR-0072 PEC universal (APLICADO)** — las 35 skills con persona-experta + canon frontera por especialidad (`scripts/apply_pec.py` SSOT, 176 tests `test_skill_pec.py`); supersede ADR-0071 (3 skills estéticas); nueva `agent-rigor` (PEC-35, 2026-09-08).
- **ADR-0073 Quality/Latency/Tokens (APLICADO)** — `batch_vote.py` (votación k-en-1 con parámetro n: input 1× vs k×, fallback, arXiv 2604.13717) + `session_affinity.py` (sticky por sesión, SAAR −79% switches) + `structured_enforcer.py` (99.9% schema adherence, retries con feedback). 21 tests, mutante verificado muerto.
- **ADR-0074 Optimización de contexto (APLICADO)** — `artifact_store.py` (tool result >4K chars → disco + handle/offset, acceso preservado) + `cue_ledger.py` (índice cue-anchored con dedup de inyecciones y staleness, arXiv 2607.20972 −42% tokens) + `compaction_calibration.py` (zonas warn 0.75/critical 0.90 AgeMem, dedup de repetidos) + `model_efficiency_report()` (tokens/llamada por modelo, gap 40% Copilot). 25 tests, mutante de frontera muerto.
- **Delegación Ollama corregida** — `task_uses_local` era no-op (texto vs tipos de tarea); filtro `is_frontier_only()` por keywords en `tier_for_task` (None → cloud justificado). End-to-end: 5/8 tareas a local (0 tokens cloud), 3 frontier-only a cloud.
- **ADR-0079 Verify-Replan + Trace Viewer + permisos + rigor (APLICADO)** — `verify_replan_gate.py` (umbrales VMAO: STOP ≥80% o 75%+50%; mutante muerto) + `trace_viewer.py` (export trace.jsonl + replay sin LLM, OMA) + `opencode.json:agent.*` (coordinator primary con task allow/deny por glob; builder/guardian/scientist least-privilege) + skill `agent-rigor` (PEC-35: gates pre-merge, anti-pintar-verde). 8 tests; PEC 176 verdes; 35 skills válidas.
- **ADR-0080 Competición aplicada (APLICADO)** — `cp_spec_gate.py` (gate de 4 pilares pre-código: edges/invariants/complexity/io_constraints; ataca el 44% design+boundary en la puerta) + `dual_verify.py` (fast vs brute-force con mismatches indexados; excepción = mismatch). 9 tests, mutante muerto; ruff/vulture 0.
- **ADR-0085 Creativo frontera (APLICADO)** — `stake_weighted_vote` (wagering: pocos calibrados > muchos dudosos; sin debate sycophant) + `trajectory_audit.py` (veto a oracle/tests, auto-zero) + TTL en `cue_ledger` (anti-stale CL-Bench). 8 tests, mutante muerto.
- **ADR-0086 Destilados + NT8 (APLICADO)** — canon NT8/NinjaScript/MQL5-Rithmic en `quant-trading` (dominio Onyx-Quan-AIBot: 100 matches) + 3 destilados evaluados pendientes (Qwimi Kimi+Opus, Nemotron-Cascade-8B, Phi-4-mini-flash) + monitoreo Hub (qwen3.5, gemma4 edge, kimi-k2.6); Cerebro+Secretario ya cubierto (cascade/supervisor/LocalExecutor).
- **ADR-0087 Mesa adversarial + BUSEV (APLICADO)** — `adversarial_table.py` (triaje→R0→R1-R2 con rotación→juez 66%→stakes, acta con minoría) + `evidence_search.py` (1+1 ciegas, escala a 4, matriz converge/condiciona) + `antivenom_filter.py` (4 cortes V1-V4) + `sprt_governor.py` (umbral+cap) + WIP-2/TTL/tripwire en postmortem. 20 tests, 2 mutantes muertos.
- **ADR-0088 Search 9-17 (APLICADO)** — `task_quad.py` (Que/Hasta-cuándo/Estándar/Impacto + 1 dueño) + bitemporal en cues (`valid_from/valid_to` + `valid_at`) + `content_restrictor.py` (JSON→orgánico −74%) + `read_guard.py` (shunt 8K a artifacts) + `misbehavior_guard.py` (pre-tool-call: creds/uploads/destructivos) + `dream_replay.py` (offline ok/fail). 19 tests, 2 mutantes muertos; roundtrip artifact byte-exacto.
- **ADR-0089 Search 9-17 2ª pasada (APLICADO)** — `vibe_review_gate.py` (Deep Scan perf/sec + 2º agente filtro; 8x/2.7x) + `skill_audit_pipeline.py` (6 fases, bloqueo con fase) + `canon_audit.py` (https+200 por URL del canon) + `transcribe_discipline.py` (verbatim + entidades exactas) + `governance_checks.py` (pausa/log/watcher/vocero). 15 tests, mutante muerto.
- **ADR-0090 Pulido skills/agentes (APLICADO)** — `SKILL_TO_AGENT` 15→35 + dominio `quality` + `skill_collision_probe.py` (shadow test) + splits (data-science 398→69L, hedgefund, architecture, quant) + agentes normalizados (coordinator sin catch-all, test-writer.min, evolve-analyzer.min).
- **ADR-0091 Especialistas rendimiento (APLICADO)** — fusiones mecánicas (`mcp_client/_types.py`, errores en `agent_bus/core.py`, `scheduler/models.py`, `semantic.py`/`gateway.py` planos, `failure_registry/registry.py`; −9 archivos) + `_parse_meta()` + 2 vars muertas + cache TTL 60s de tags Ollama + splits verificados. Rechazos documentados (example_tool load-bearing, conftest, run.py split, torch-optional). **5383 tests**.
- **ADR-0092 Ratio local ≥60% (APLICADO)** — `capability_profiles.py` (13 perfiles: coding/reasoning/math/multilingual/agentic/vision + trust; score dot×trust normalizado; conf ≥0.65 → local) + clasificador por keywords + `ollama_local.yaml` gitignored (plantilla versionada) + calibración EWMA lista. Verificación: **19/20 = 95% local** con mejor modelo por función (código→Qwopus, diseño→GLM, visión→qwen3-vl).
- **ADR-0093 OTP lite (APLICADO)** — `bounded_executor.py` (pool por dominio + cola acotada con shed drop-newest/oldest + deadline por tarea + métricas executed/shed/timeouts); diferidos supervision-tree full y error-kernel (hasta multiprocess real). 7 tests, mutante de cotas muerto.
- **ADR-0094 Librería compartida (APLICADO)** — veredicto: NO librería separada (overhead packaging, cero ganancia); crecer `harness/common.py` con `short_hash` + `utc_now_iso` + `safe_json_loads` + 6 migraciones (artifact/cue/snapshot/cache/tracer/planner).
- **ADR-0095 Benchmarks competitivos (APLICADO)** — calibración math (GLM/Qwen3.8 → 0.85, thinking>size) + `stale` en `dual_verify` (540d, backward-compat, mutante muerto) + global sincronizado (13 modelos, default flash local) + GSM8K deprecado como gate.
- **ADR-0096 Mesa competitiva (APLICADO)** — `timeout_s` en `dual_verify` (anti-hang con shutdown sin espera; mutante performance no-matable documentado) + `check_reasoning` 5º pilar opcional (verdict+pasos) + `math_gate.py` (20 casos exactos). 10 tests.
- **ADR-0097 99% local + oráculo 1% (APLICADO)** — auditoría: 8 tags = 4 únicos instalados (9 configurados ausentes); tiers a instalados (MiniCPM5/Qwen3.8/Qwopus) + opencode.json 4 modelos con default Qwen3.8 + `local_first` 0.99/0.01; verificación 19/20 = 95% local.
- **ADR-0098 Deep-docs (APLICADO)** — `credential_ref.py` (by-name, resolve per-op, UI-safe) + `tool_pipeline.py` (guards→approval→around→post inmutable) + `op_sec.py` (scrub + tmp 0700) + `attachment_gate.py` (admit + verify fail-closed) + `delegation_scope.py` (frozen parent-owned). 16 tests, mutante muerto.
- **ADR-0099 Unsloth Desktop (APLICADO)** — `unsloth_client.py` (discovery dinámico por /health, sin auth local, content/reasoning_content) + `check_unsloth.py`; verificado en vivo :61767 con onyx-coder (comparte blobs Ollama). 11 tests, mutante muerto.
- **Veredicto Ollama vs Unsloth (2026-09-22, evidencia)** — gana **Ollama como único activo**: daemon persistente (:11434 estable), keep_alive gestionado, embeddings, API estable, tiers/capabilities construidos encima; MiniCPM5 responde en ~11s. Unsloth queda on-demand (puerto dinámico: 61767→54960 entre sesiones; sin él, discovery falla graceful y el orden Unsloth→Ollama→cloud sigue intacto).
- **ADR-0100 Dispatch obligatorio (APLICADO)** — `coordinator_dispatch.py`: plan frozen por tarea (agente + skills topadas + backend local-first + contrato JSON + flag oráculo); cerradas a path determinístico sin LLM. 7 tests, mutante muerto.
- **ADR-0081 Search 9-13 (APLICADO)** — `tool_pruner.py` (allowed ≤4 por tarea) + `cross_review.py` (revisor de familia distinta, prefiere local) + `rag_evaluator.py` (20 preguntas, clasifica RETRIEVAL/MODEL_IGNORED) + `action_first_instruction` (1ª línea = acción, ≤5 pasos) + `sandbox_executor.py` (docker o subprocess, nunca lanza) + `turbovec_adapter.py` (graceful + allowlist) + SDD explícito en SPE. 27 tests, mutante muerto.
- **ADR-0082 Search 9-13 R2 (APLICADO)** — `session_snapshot.py` (estado a disco + vista ≤5KB, restore byte-exacto; Scroll/ACM) + `docs_gate.py` (PLAN/AGENTS/SPECS/ADR actualizados en working tree; SKIP fuera de repos) + affinity enchufada en `ModelRouter` (`attach_affinity` + `session_id`, sin callers antes) + 7 dimensiones IA en business-strategy. K2 Horizon evaluado (no instalado → diferido). 11 tests, mutante del gate muerto.
- **ADR-0078 DeepSeek + ejecución local real (APLICADO)** — auditoría: la decisión trivial→local era correcta (10/10, run.py:420) pero `OllamaClient.generate` no tenía callers productivos (routing = telemetría). `LocalExecutor` cierra el loop (allowlist cerrada + fallback cloud, 0 tokens cloud en triviales) + `pressure()` determinista + `prune_then_summarize` (evict tool-lines + structured_compact) + disciplina R1 en WFP. 14 tests, mutante del gate muerto. deepseek-harness-master auditado (token-meter, 2-fases, prefix-cache discipline transferidas; GRPO-voting y kv_efficiency como futuro).
- **ADR-0075 Skills/Agentes frontera (APLICADO + WIRING)** — `skill_composition.py` (calls lazy + anti-ciclos + tiers invocation + poda set-compatibility, Pocock −63%) + `competence_model.py` (Beta posterior por agente×skill + Thompson anti-collapse + imp@k) + `fanout_gate.py` (anti-sobre-descomposición: baseline ≥80% → single, evita amplificación ×17.2). **Wiring**: piloto `swarm-release-ops → calls:[security-audit]`; AgentSelector con `competence` DI (re-rank Thompson con evidencia); `vote_on_task(baseline_success=)` (probe ≥0.8 → sin voting); `adaptive_planner._degrade_if_strong` (baseline single ≥0.8 con evidencia → degrada multi, en atajo y flujo). 9 tests wiring (302 passed en suite tocada); 2 mutantes de frontera muertos. Diferidos: SkillRouter-embeddings (YAGNI a 34 skills), GDE sub-goals verificables (refactor planner, ADR futuro).
- **CI verdes** — required {lint, test, security} PASS en PR #16: fix extras-dev (ruff/mypy/vulture), formato ruff 0.16, vulture 2.16, SDO+presupuesto skills 320 chars, progressive disclosure restaurado, safety con ignore CVE-2025-33228 (falso positivo cuda-toolkit, no es paquete pip). Deps UPG check-web: ruff/mypy/hypothesis/lancedb/numpy/torch.
- **ADR-0076 Tooling + guards (APLICADO)** — `tool_output_filter.py` (wrapper rtk), `idempotency_guard.py` (dedup por key+hash), `structured_enforcer` strict keys, `TgrepBackend`, principios TOOLING (Python/bash).
- **ADR-0078/0080/0081/0085/0087/0088 (APLICADO)** — `local_executor.py` + `pressure()` + `prune_then_summarize` + R1; `cp_spec_gate.py` + `dual_verify.py`; `tool_pruner.py` + `cross_review.py` + `rag_evaluator.py` + `sandbox_executor.py` + `turbovec_adapter.py`; `stake_weighted_vote` + `trajectory_audit.py` + TTL cues; `adversarial_table.py` + `evidence_search.py` + `antivenom_filter.py` + `sprt_governor.py`; `task_quad.py` + bitemporal + `content_restrictor.py` + `read_guard.py` + `misbehavior_guard.py` + `dream_replay.py`.

### Estado 2026-08-18 (arquitecturas RAG frontier + integraciones anydoc + deepseek-harness)

- **Arquitecturas RAG 2026 (5 evaluadas, FRS)**:
  - **Hibrido (dense + sparse) IMPLEMENTADO** — `harness/memory_rag/hybrid_retriever.py`:
    `HybridRetriever` fusiona vector denso (LanceDB embeddings) y BM25 disperso
    (SQLite FTS5) con **Reciprocal Rank Fusion** (k=60, Cormack 2009); DI sobre
    `FTSSearch` + `LanceVectorStore`; `HybridResult` frozen.
  - **Correctivo (CRAG) IMPLEMENTADO** — `harness/memory_rag/corrective_retriever.py`:
    valida calidad de recuperacion pre-generacion (arXiv:2401.15884); evaluador
    heuristico cero-LLM (score medio + cobertura de terminos); si calidad < 0.30 →
    query rewrite o fallback; reporta `corrective_action`.
  - **GraphRAG CUBIERTO** — `knowledge_graph.py` (grafo metadatos) +
    TokenBudgetRouter (PageRank + TF-IDF); pipeline LLM de entidades = YAGNI.
  - **Agentic RAG CUBIERTO** — orchestrator multi-agente (fan-out + votacion
    gobernada + tools) ya es la capa agentica.
  - **Multimodal PARCIAL** — anydoc convierte binarios (21 extensiones) → Markdown;
    embeddings multimodales nativos = YAGNI.
  - Tests: `test_hybrid_retriever.py` (12) + `test_corrective_retriever.py` (10);
    regresion memory_rag **191 passed**; ruff 0.

### Estado 2026-08-18 (integraciones anydoc + patrones deepseek-harness)

- **Integración anydoc — binarios → Markdown → RAG** (commit 983f93c):
  `harness/memory_rag/doc_converter.py` con Protocol `DocumentConverter` +
  `AnyDocConverter` (lazy, `firecrawl-anydoc>=0.1.9`) y `DOC_EXTENSIONS` con
  **21 extensiones** (pdf, docx, doc, pptx, ppt, xlsx, xls, odt, odp, ods, rtf,
  epub, csv, tsv, html, htm, md, txt, json, yaml, yml). `DocumentChunker` acepta
  converter inyectado (DI) y propaga `DocumentConversionError(path, reason)`.
  Ingesta con `rag_ingest.py --include-docs` o `!rag ingest --docs`.
- **Patrones deepseek-harness — plugin lifecycle + session replay**:
  `PluginBase` con `on_load()`/`on_unload()`/`events` (no-op), `ToolRegistry`
  con `event_bus` DI y suscripción automática `on_{event}`,
  `load_all()`/`unload_all()` idempotentes; `SessionReplay`
  (`harness/observability/session_replay.py`) export markdown/json +
  `SessionNotFoundError`. Demo: `GreeterTool`.
- Suite: **4722 tests** collected; **35 skills** validos
  (`validate_skills.py --strict`); 59 tests nuevos (30 plugin + 29 replay);
  coverage registry 94%, session_replay 100%.

### Estado 2026-08-11 (deuda AGR 0 + GPU CUDA 12.6 + oraculos reales)

Sesion de cierre de deuda estructural. Deuda AGR a 0: 32 modulos >500 lineas
convertidos a paquetes con `__init__.py` re-export backward-compatible, SOL de
herencia corregido en 9 clases, mixins con <=2 bases, lookup dinamico `_rc.` en
run_commands, baseline de tests identico tras el refactor.

- **GPU CUDA 12.6 activa** en RTX 4060 8GB (torch 2.13.0+cu126): speedups
  vector search x10.9 (10k) / x9.2 (100k) y embeddings batch 41us/msg.
- **Fase 1 TDD con oraculos reales**: `pbt_stage.py` con oraculo Hypothesis
  REAL en subprocess (5 invariantes, sin exec()) y `mutation_stage.py` con
  mutacion AST en subprocess aislado.
- **ParallelExecutor**: fan-out nativo (ThreadPoolExecutor max_workers=3) +
  voting gobernado (gate score>=70 y confidence<0.7, N=3, presupuesto
  MAX_TOKENS_BY_AGENTx3) con metricas fan_out_factor/tokens_per_parallel_agent/
  voting_events (aportacion ORCA 2026 evaluada y descartada como herramienta).
- **Memoria central SSOT** (Memory_Proyects, memory_config.py 3 niveles
  LANCEDB_PATH > .swarmind_config.json > legacy, `_safe_home()` resiliente):
  7.5GB de DBs duplicadas eliminadas, portabilidad Linux/Mac/Windows.
- Suite: **4465 passed, 37 skipped, 4 xfailed**, Ruff all checks passed,
  Vulture 0 muerto.

Las metricas principales del sistema (tests, cobertura, agentes, skills, modulos) estan en la [pagina principal](../README.md#estado-actual-julio-2026).

**Resumen ejecutivo:** 4722 tests, 23 agentes, 35 skills, 19 paquetes orchestrator, 14 paquetes memory/rag, RTX 4060 CUDA 12.6 (x10.9 search), 15 papers 2026 implementados, **Opción A SSOT global implementada + memoria central portable (v3.x)**.

**Actualización 2026-08-04 :** IMPLEMENTADO — plugin compaction-context.js (hook experimental.session.compacting), steps:8 en release-ops/token-budget-auditor, Σ-Mem MVP (reliability_memory.py + 22 tests), memoria gobernada MVP (memory_guard.py + 22 tests), abstention_policy en token_budgets.yaml (stop rules CONVOLVE), regla subagentes condensados en coordinator.md; diferidos justificados: setCacheKey/small_model/provider options. Implementados H1-H8 completos — H1 (10 SKILL.min.md con YAML roto reparados + test TestSkillMinFiles), H2 (5 mins API densos recompactados con compile_skills.py: 58-88% → 35-54%), H3 (routing 45 rutas, universal 10→2 agentes), H4 (release-ops deduplicado), H5 (triada evolve -59.9%), H6 (token_budgets.yaml conectado al runtime, 23 tests nuevos), H7 (base_principles N3 bajo demanda, -6.2K tokens/agente), H8 (opencode.json: compaction.prune + tool_output + mcp_timeout). 22/22 agentes con role_budget. PR #7 mergado: CI con checks requeridos lint/test/security, python 3.12, auto-merge funcional.

**Metricas adicionales no incluidas en README:** 196+ commits, 258 archivos Python, suite completa ~100s (sin slow ~45s), 30+ tecnicas 2026 integradas.

### Resumen de Cobertura por Modulo

| Modulo | Archivos | Cobertura | Estado |
|--------|----------|-----------|--------|
| Orchestrator | 48 | ~80% | Robusto |
| Memory/RAG | 30 | ~60% | Estable |
| Tests | 52+ | N/A | Base solida |
| Evolve Loop | 10 | ~70% | Estable |
| Tools Sandbox | 4 | ~80% | Cubierto (MCP client+manager) |
| Scheduler | 1 | 95% | Robusto |
| Run Commands | 1 | 92% | Robusto |
| Reset State | 1 | ~60% | Mejorado |
| GPU Acceleration | 2 | 100% | Cubierto |

## Hitos Alcanzados

| Hito | Fecha | Logro |
|------|-------|-------|
| **Fundacion del Sistema** | 2026-04 | Creacion del harness, decisiones de arquitectura fundacionales, agentes base (coordinator, builder, scientist, guardian) |
| **Memoria y RAG** | 2026-05 | Federated Memory con LanceDB, incrustaciones semanticas |
| **Skill Router** | 2026-05 | Enrutamiento de skills por similitud semantica, registro YAML |
| **Context Injector** | 2026-05 | Inyeccion de contexto estructurado |
| **Estandares Automaticos** | 2026-05 | DocStrings ES-UTF8 obligatorios, ERR_ACTION |
| **Idempotencia Principle** | 2026-05 | IDP: no reimplementar si ya existe |
| **Competitive Programming 2026** | 2026-06 | Tecnicas CP: Two Pointers, DP, Segment Tree, Trie, KMP, etc. |
| **Token Economy v1** | 2026-06 | Gestion de presupuesto de tokens, cache semantico |
| **Lazy Loading PEP 562** | 2026-06 | Cold start 2800ms -> 39ms (72x mas rapido) |
| **6 Nuevas Tecnicas** | 2026-06 | WFP + PBT + CEN + BTR + AGR + SVE, +37 tests |
| **Text Analysis 2026** | 2026-06 | analisis de textos juridicos, Legal2LogicICL |
| **Frontier Upgrade 2026** | 2026-07-09 | MetaClaw, AdaptOrch, MuTON, SWE-Master, ShapleyFlow |
| **Frontier Agents + Skills** | 2026-07-09 | Agentes frontier, skills especializados, frontend-uiux, legal-doc Colombia |
| **Curva de Cobertura** | 2026-07 | Evolucion: 33.66% -> 43.69% -> 59.69% |
| **Coverage +26%** | 2026-07-20 | 33.66% -> 59.69% (+1055 tests, de ~460 a ~1520) |
| **Async Coordinator** | 2026-07-20 | AsyncAgentBus + async debate + WAL integrados |
| **Token Economics v2** | 2026-07-20 | ShapedCache + Structured Compaction + pipeline de tokens |
| **Parallel Testing** | 2026-07-20 | pytest-xdist + slow markers + fail-under |
| **Documentacion** | 2026-07-20 | Decisiones de arquitectura completas + manual tecnico + glosario + roadmap + SUMMARY |
| **GPU Acceleration** | 2026-07-20 | RTX 4060 detectada, gpu_accel.py (278ln), gpu_optimize.py (225ln), 6x search |
| **Refactor >500ln** | 2026-07-20 | task_orchestrator 994→830, context_window 1029→943 |
| **Embedding 3.2x** | 2026-07-20 | fallback_embedding vectorizada con np.frombuffer + np.add.at |
| **ShapedCache threshold** | 2026-07-20 | 0.95→0.88 para cache semantico real |
| **Gap Analysis 2026** | 2026-07-29 | 15 papers implementados, mapeo completo de gaps frontier |
| **GovernanceGuard** | 2026-07-29 | arXiv:2606.22528 — deteccion de governance decay en cadenas multi-agente |
| **NaturalLanguageToolkit** | 2026-07-29 | arXiv:2607.03953 — herramientas de lenguaje natural para agentes |
| **MultiUserGovernance** | 2026-07-29 | arXiv:2606.21856 — gobierno multi-usuario con aislamiento de sesiones |
| **OrganizationalLayer** | 2026-07-29 | arXiv:2607.25446 — ciencia organizacional aplicada a colectivos de agentes |
| **Learned Adaptive Memory** | 2026-07-29 | arXiv:2607.13591 — memoria adaptativa con retencion aprendida |
| **Expansion agentes** | 2026-07-29 | 8 → 22 agentes especializados (100% perfiles) |
| **32 Decisiones de Arquitectura** | 2026-07-29 | De 28 a 32 decisiones de arquitectura documentadas e implementadas |
| **Seguridad Paths Portables** | 2026-07-30 | Scanner de secretos + paths portables en CI y pre-commit |
| **Opción A — SSOT Global** | 2026-07-31 | Cerebro `.opencode/` → `~/.config/opencode/` (sync automático en cada commit) + mirror local en 7 proyectos <workspace> |
| **Oráculos reales PBT/mutation** | 2026-08-11 | `pbt_stage.py` Hypothesis REAL en subprocess (5 invariantes) + `mutation_stage.py` AST aislado + DynamicDAG + WAL (Fase 1 TDD) |
| **GPU CUDA 12.6** | 2026-08-11 | torch cu126 en RTX 4060 8GB, vector search x10.9 (10k) / x9.2 (100k), embeddings 41us/msg, `enable_gpu.py` portable |
| **ParallelExecutor** | 2026-08-11 | Fan-out paralelo nativo + voting gobernado (gate score>=70 ∧ confidence<0.7, N=3) — aportación ORCA 2026 |
| **Memoria central SSOT** | 2026-08-11 | `Memory_Proyects` única DB + backups, 7.5GB de DBs duplicadas eliminadas, portabilidad Linux/Mac/Windows |
| **Deuda AGR 0** | 2026-08-11 | 32 módulos >500 líneas → paquetes con `__init__.py` re-export, SOL corregido en 9 clases, mixins ≤2 bases, baseline de tests idéntico |
| **Delegacion local Ollama 5-tier (CODING)** | 2026-09-06 | tier CODING (qwen2.5-coder:7b) con precedencia sobre QUALITY; keywords ES/EN (implementar, refactor, debug, pytest, class, funcion) | 
| **Delegacion local Ollama 4-tier** | 2026-08-14 | delegación local Ollama 4-tier (fast/quality/embedding/vision) + keep_alive → minimiza tokens cloud | 
| **Delegacion local Ollama — final** | 2026-08-14 | modelos 2026 instalados (qwen3:4b, deepseek-r1:8b, qwen2.5-coder:7b, qwen3-embedding:0.6b, qwen3-vl:4b), 38 tests nuevos (21+17), 2 bugs latentes corregidos en _apply_model_routing |
| **Integracion anydoc** | 2026-08-18 | binarios → Markdown → RAG: `DocumentConverter`/`AnyDocConverter` (21 extensiones, `firecrawl-anydoc`), `DocumentChunker` DI + `DocumentConversionError`, `--include-docs` / `!rag ingest --docs` |
| **Plugin lifecycle + session replay** | 2026-08-18 | patrones deepseek-harness: `PluginBase` on_load/on_unload/events, `ToolRegistry` DI + EventBus, `SessionReplay` (markdown/json) — 59 tests, registry 94%, session_replay 100% |

### Evolucion de Cobertura

```
Jul 09:  33.66%  (~460 tests)
Jul 14:  43.69%  (+605 tests, 2ef685f)
Jul 20:  59.69%  (+1522 tests total, cobertura +26%)
Objetivo: 80%    (proximo hito)
```

---

## Proximos Pasos

| Prioridad | Tarea | Impacto | Detalle | Estado |
|-----------|-------|---------|---------|--------|
| ✅ | Router de targets RE (filosofia REA) | RE/Agentes | `harness/reverse_engineering/target_router.py`: metodo+engine+evidencia+guardrail; 25 tests | **HECHO** |
| ✅ | Catalogo MCP variado + frontera | Tooling | `mcp_servers.yaml` 8→23 servers verificados + candidatos por dominio; suite MCP/RE verde | **HECHO** |
| ✅ | Cableado skills+agentes+herramientas | Harness | `mcp_catalog` + `DispatchPlan.tools` + `deploy_all --sync-global`→opencode; wiring e2e probado | **HECHO** |
| ✅ | Skill `mcp-toolkit` + organizacion de tools | Harness/Skills | categorias en la SSOT + `SKILL_TO_TOOLS`; registro+routing+digests; propagado | **HECHO** |
| ✅ | Alinear flota de modelos a lo instalado | Entorno | SSOT `local_models.yaml` regenerada + `fleet_manifest`/`ollama_models.yaml` alineados; `test_fleet_config_drift` 5 passed | **HECHO** |
| ✅ | Oraculo PBT funcional en Windows | TDD | `SandboxExecutor.run_script(require_project_deps=True)` → Job Object host; `pbt_stage` activado | **HECHO** |
| ✅ | Python 3.14 acoplado | Entorno | `.python-version` + PATH de usuario + CI alineado | **HECHO** |
| ✅ | Pre-commit efectivo | Rigor | `install_hooks.py` resuelve `core.hooksPath` (`.githooks`) | **HECHO** |
| ✅ | Agentes `.agent.min` ocultos (V2) | Skills/Agentes | `hidden: true` + `compile_agents.minify_agent` | **HECHO** |
| **Media** | Coverage 80% | Calidad | Atacar archivos con cobertura baja: mcp_executor.py, plugins, evolve_loop | 🔄 Pendiente |
| **Media** | Async pipeline integration | Rendimiento | TaskOrchestrator async completo, integracion con AsyncAgentBus | 🔄 Pendiente |
| **Media** | Fix debate tests | Estabilidad | ~20 tests de debate con ERROR por dependencias de orquestador | ⏳ Pendiente |
| **Media** | Paired eval de skills (Skill Lift) | Skills | Medir Δpp con/sin skill (SkillsBench: 16/84 negativos; self-generated -1.3pp); retiro por outcome N>=100 | 🔄 Pendiente |
| **Media** | Habilitar `formatter: true` (OpenCode V2) | DX/Rigor | Evaluado 2026-10-15 y RECHAZADO con evidencia: `ruff format --check` reescribiría 277/325 tests + 32 scripts y crashea en algunos dirs (bug de ruff). Habilitar tras establish `ruff format` baseline + fix upstream | ⏳ Pendiente |
| **Baja** | Mutation gate de skills en pre-commit | Skills | SkillCI-style (typo, negacion, context-prefix) + self-growing -> test permanente | 🔄 Pendiente |
| **Baja** | Surrogate Verifier aislado por sesion | Gobernanza | Framework distinto emite diagnostico por-assertion (CoEvoSkills 2604.01687) | 🔄 Pendiente |
| ✅ | Integrar TriageSLM+Telemetry al pipeline | Routing/Tokens | `PipelineRouter` (cascada: SLM -> fallback en complejidad timida -> frontier), TelemetryGate hit-rate 0.80, telemetria en agent_dispatcher (R10) | **HECHO** |
| ✅ | Progressive disclosure restantes | Skills | atdd-spec 133→85, process-over-tools 139→88, frontend-uiux 174→113, diagram-design 198→120 (+references/) | **HECHO** |
| ✅ | Cleanup difficulty_router literales (MAG) | MAG | SHORT/MEDIUM/LONG_TEXT_THRESHOLD_CHARS (200/500/1000) | **HECHO** |
| ✅ | Regenerar coordinator.agent.min.md | Coherencia | compile_agents.py consume coordinator_policy.yaml (3 refs) | **HECHO** |
| ✅ | Veto duro de anti-triggers en router | Routing | hard_veto_score/apply_hard_veto en agent_dispatcher (Codex #34712: el routing ignora prosa negativa) | **HECHO** |
| ✅ | Refactor archivos >500ln | Mantenibilidad | 32 módulos → paquetes con `__init__.py` re-export (deuda AGR 0) | **HECHO** |
| ✅ | Session-scoped fixtures | Velocidad tests | MockVectorStore session-scoped creado | **HECHO** |
| ✅ | GPU acceleration | Rendimiento | RTX 4060 + 6x search + embedding 3.2x | **HECHO** |
| **Baja** | MCP server per agent | Integracion | Cada agente con su propio servidor MCP para aislamiento | ⏳ Pendiente |
| **Baja** | GPU full pipeline | Rendimiento | Integrar GPU en mas puntos del pipeline (semantic cache, agent_bus) | 🔄 Pendiente |
| **Baja** | Plugins architecture | Extensibilidad | Sistema de plugins para habilidades externas | ⏳ Pendiente |
| **Baja** | Federated Learning | Innovacion | Aprendizaje federado opcional entre instancias | ⏳ Pendiente |
| ✅ | ADR-0103 Frontera Simple | Estado del arte | WS-A/B/C/D/E implementados (telemetria, cache-shape, masking default, coordinador 54ln, triage SLM, hidden-body, fan-out cap, digests sha256, RSV) | **HECHO** |
| ✅ | Skills finance a PD | Skills | risk-execution 236→71, alpha-research 218→48 + references/ | **HECHO** |
| ✅ | Docs Agent-Native | Docs | INDEX.md frontmatter + indice por capas + 61 links OK | **HECHO** |
| ✅ | Refactor archivos >500ln | Mantenibilidad | 32 módulos → paquetes con `__init__.py` re-export (deuda AGR 0) | **HECHO** |
| ✅ | Session-scoped fixtures | Velocidad tests | MockVectorStore session-scoped creado | **HECHO** |
| ✅ | GPU acceleration | Rendimiento | RTX 4060 + 6x search + embedding 3.2x | **HECHO** |

### Legado de Deuda Tecnica

**Archivos de producción a 0% de cobertura (Auditoria 2026-07-31):**

| Archivo | Stmts | Lineas | Prioridad | Accion |
|---------|------:|-------:|-----------|--------|
| `harness/orchestrator/mars_scheduler.py` | 339 | 1141 | Alta | Tests + refactor <900ln |
| `harness/memory_rag/sqlite_vec_adapter.py` | 337 | 837 | Alta | Tests (tras nosec B608) |
| `harness/memory_rag/federated_search.py` | 249 | 865 | Alta | Tests faltantes |
| `harness/orchestrator/metaclaw.py` | 217 | 833 | Alta | Tests (paper 2026 estrella) |
| `harness/evolve_loop/nudge_system.py` | 109 | ~120 | Media | Tests faltantes |
| `harness/gpu_optimize.py` | 87 | ~225 | Media | Tests + integracion real |
| `harness/memory_rag/token_budget_manager.py` | 75 | ~80 | Media | Tests faltantes |
| `harness/memory_rag/sqlite_vec_utils.py` | 54 | ~55 | Media | Tests faltantes |
| `harness/model_router/hermes_adapter.py` | 52 | ~55 | Media | Tests faltantes |
| `harness/benchmarks/bench_*.py` (×5) | 174 | ~200 | Baja | Tests faltantes |
| `harness/__main__.py` | 2 | 4 | Baja | Smoke test entry point |

**Archivos >500 lineas (Auditoria 2026-07-31, objetivo <900LC):**

| Archivo | Lineas | Prioridad | Accion |
|---------|-------:|-----------|--------|
| `harness/orchestrator/mars_scheduler.py` | 1141 | Alta | Extraer ScheduleEngine, ResourceAllocator |
| `harness/aifactory/factory.py` | 905 | Media | Extraer sub-fabricas |
| `harness/memory_rag/federated_search.py` | 865 | Media | Refactor |
| `harness/orchestrator/adaptive_planner.py` | 859 | Media | Refactor |
| `harness/orchestrator/debate_orchestrator.py` | 856 | Media | Refactor |
| `harness/memory_rag/sqlite_vec_adapter.py` | 837 | Media | Refactor |
| `harness/orchestrator/metaclaw.py` | 833 | Media | Refactor |
| `harness/orchestrator/worktable.py` | 829 | Baja | Refactor |
| `harness/scheduler.py` | 811 | Baja | Refactor |
| `harness/memory_rag/agent_kpi_tracker.py` | 804 | Baja | Refactor |

**Tests lentos (>4s, encontrados 2026-07-31):**

| Test | Tiempo | Archivo |
|------|-------:|---------|
| `TestConnectAll::test_connect_all_success` | 8.17s | `test_mcp_manager.py` |
| `TestConnectAll::test_connect_all_some_fail` | 8.15s | `test_mcp_manager.py` |
| `TestTaskOrchestrator::test_broadcast_plan_envia_subtask_especifica` | 5.73s | `test_orchestrator.py` |
| `TestMultiAPIProvider::test_execute_basic` | 4.18s | `test_frontier_improvements.py` |
| `TestConnectAll::test_connect_all_invalidates_index` | 4.10s | `test_mcp_manager.py` |
| `TestLoadServers::test_load_success` | 4.07s | `test_mcp_manager.py` |

**Deuda de tipos (tipado progresivo pendiente):** 92 errores de mypy en 32 archivos. mypy queda en `|| true` en CI con TODO hasta tipado progresivo. Categorías principales: `list-item`, `union-attr`, `no-redef`, `attr-defined`, `arg-type`, `valid-type` (uso de `callable`/`any` como tipo), `return-value`, `var-annotated`. Archivos más afectados: `task_manager.py` (8 errores), `shaped_cache.py` (7), `lance_vector_store.py` (5), `scope_analyzer.py` (5), `common.py` (3), `context_assembler.py` (1), `evolve_loop/cognition_sync.py` (1).



---

## Metricas Clave

| Metrica | Actual | Objetivo | Tendencia |
|---------|--------|----------|-----------|
| Cobertura de tests | 75.70% | 80% | Subiendo |
| Tests totales | 4722 | ~5000 | Subiendo |
| Agentes | 23 | 30+ | Subiendo |
| Skills | 35 | 50+ | Subiendo |
| Modulos Orchestrator | 142 | 150+ | Subiendo |
| Modulos Memory/RAG | 109 | 120+ | Subiendo |
| Archivos <500LC (deuda AGR) | 100% | 100% | Mantenido |
| Archivos >500LC (deuda AGR) | 0 | 0 | Completada |
| DocStrings ES-UTF8 | ~95% | 100% | Subiendo |
| Tiempo full suite | ~100s | <60s | Bajando |
| Tiempo sin slow | ~45s | <30s | Bajando |
| Decisiones de arquitectura | 44/44 | 44/44 | Completo |
| Commits totales | 230+ | N/A | Subiendo |
| Tecnicas 2026 | 30+ | 40+ | Subiendo |
| Papers implementados | 15 | 20+ | Subiendo |
| GPU Speedup | 6x → 10.9x search | 10x full pipeline | Subiendo |

---

## Notas de la Version

- **2026-08-18**: Integraciones (commit 983f93c): **anydoc** — binarios → Markdown → RAG (`DocumentConverter`/`AnyDocConverter` lazy con `firecrawl-anydoc>=0.1.9`, `DOC_EXTENSIONS` 21 extensiones, `DocumentChunker` con converter DI, `DocumentConversionError(path, reason)` sin tragar errores, `rag_ingest.py --include-docs` + `!rag ingest --docs`); **deepseek-harness** — plugin lifecycle (`PluginBase` on_load/on_unload/events, `ToolRegistry` con event_bus DI, suscripción automática `on_{event}`, load_all/unload_all idempotentes, `GreeterTool` demo) + session replay (`SessionReplay` export markdown/json, `SessionNotFoundError`). 59 tests nuevos (30 plugin + 29 replay); coverage registry 94%, session_replay 100%. **4722 tests** collected, **35 skills** validos.
- **2026-08-11**: Deuda AGR 0 — 32 modulos >500 lineas convertidos a paquetes con `__init__.py` re-export backward-compatible (commits e409982 + 545e591, verificado baseline identico). GPU CUDA 12.6 activa (torch 2.13.0+cu126, RTX 4060 8GB): vector search x10.9 (10k) / x9.2 (100k), embeddings batch 41us/msg, `enable_gpu.py` portable, health hardware info (e246998, 826aeda). Fase 1 TDD: oraculos reales PBT/mutation en subprocess, orchestrator DynamicDAG + WAL, test_router 25 tests + fix `_to_model_route()` (407c36d). ParallelExecutor fan-out + voting gobernado (ORCA 2026 evaluado/descartado, 4408944). Memoria central SSOT Memory_Proyects sin DBs paralelas + portabilidad Linux/Mac/Windows, 7.5GB liberados (4e5583e). **4465 passed, 37 skipped, 4 xfailed**, Ruff all checks passed, Vulture 0.
- **2026-08-08**: TDD always-on (engine authority + test-first real + anti-gaming, `test_dependency_map.py` TDAD src↔tests, `test_reinforcement.py` Tester→mutation→Critic; 74 tests nuevos; contrato TDD 2026 en builder/guardian/coordinator). Fase 3 ahorro de tokens: `complexity_router.py` (RouteLLM-style, 26 tests, ahorro ~2x con fallback) + `token_usage_tracker.py` (medición por agente, 39 tests, thread-safe). Documentación concisa (progressive disclosure: resumen en notas, detalle en módulos). **4277+ tests**.
- **2026-08-08**: Fase 1+2 — MCP stateless 2026-07-28 (`connect_stateless` + `server/discover` + catálogos cacheables + headers Mcp-Method/Mcp-Name, 22 tests), OTel GenAI semconv estables (`start_genai_span`, `gen_ai.*`, 15 tests), DeltaChannel durable exec (`delta_channel.py`, 9 tests), Agent Factory on-demand (`agent_factory.py` + `agent_templates.yaml` 8 plantillas + recommender + render Markdown opencode, 29 tests), validador agentskills.io (`skill_frontmatter.py`, 20 tests, 32/32 skills válidos), skills de dominio 2026 (reviewer adversarial + science citas/reproducibilidad + legal vigencia/citas). Fix test-order: TestGenAISemconv con parcheo por `trace_agent.__globals__` (robusto ante `test_lazy_loading`). **4068+ tests**.
- **2026-08-03**: Memoria central portable (v3.x) en `<Documents>/Memory_Proyects` (MEMORY_ROOT) + backup automático con rotación (`backup_memory.py` + tarea programada) + menú de configuración al instalar (`config_swarmind.py`). TDD: 58 tests nuevos en 5 módulos a 0% cobertura. Optimización de tokens: descripciones de agents/skills -57% (3875→1684 tokens). Deuda técnica: test_agent_builder fechas hardcodeadas corregidas. **3937 tests**.
- **2026-07-31**: Opción A implementada — SSOT global opencode (`~/.config/opencode/`) con sync automático en cada commit (pre-commit hook → `scripts/sync_opencode_global.py`). Mirror local completo (`.opencode/` 125 archivos + `harness/` 8451 + 31 skills + registry) desplegado en 7 proyectos de <workspace> preservando config propia. Seguridad: scanner de secretos 0 violaciones, bandit 0 hallazgos en producción (MD5 `usedforsecurity=False`, nosec justificado), gates CI endurecidos (bandit/pip-audit bloquean), dependabot + github-actions. Guia: [docs/src/es/guide/opcion-a-ssot-global.md](../guide/opcion-a-ssot-global.md).
- **2026-07-30**: Política de paths portables + scanner de secretos/rutas personales (0 violaciones). Limpieza de rutas personales en toda la documentación.
- **2026-07-29**: Gap Analysis 2026 completo (15 papers implementados). Nuevos modulos: GovernanceGuard (arXiv:2606.22528), NaturalLanguageToolkit (arXiv:2607.03953), MultiUserGovernance (arXiv:2606.21856), OrganizationalLayer (arXiv:2607.25446), Learned Adaptive Memory (arXiv:2607.13591). Expansion de 8 a 20 agentes. 3420 tests, 31 skills, 48 modulos orchestrator, 30 modulos memory/rag.
- **2026-07-20 (final)**: GPU acceleration (RTX 4060, 6x search, 3.2x embedding). Refactor task_orch 994→830, ctx_window 1029→943. ShapedCache threshold 0.88. Seguridad: path traversal hardening. 2900+ tests, ~60% coverage.
- **2026-07-20**: Documentacion completa del sistema. Se anaden glosario, roadmap, y se completa SUMMARY con todas las secciones. Cobertura en ~60% con 2900+ tests pasando.
- **2026-07-09**: Frontier Upgrade 2026 con MetaClaw, AdaptOrch, MuTON, SWE-Master, ShapleyFlow.
- **2026-07**: Token Economics v2 con ShapedCache y Structured Compaction. Async coordinator con WAL.
- **2026-06**: Lazy loading PEP 562 (72x mas rapido). 6 nuevas tecnicas (WFP, PBT, CEN, BTR, AGR, SVE).
- **2026-05**: Fundacion del sistema con agentes base, memoria federada, skill router, estandares automaticos.

- **2026-10-22**: MCP interconnect (11.23): circuit breaker + health/retry en MCPManager, puente in-process inter-proyecto (project_bridge), web frontier (exa/tavily), seguridad (security_scan), 26 servers. 7 tests nuevos.

- **2026-10-22**: Integracion Harness2 (11.24): recursive harnessing (Propose-Probe-Compose) en `harness/harness2/` + `RecursiveHarness` en evolve_loop. 9 tests.

- **2026-10-24**: RuscaDB grafo (11.36): edges + last_inserted_id + graph_traverse. Ruff 0.

---

> *Este roadmap se actualiza tras cada hito significativo. Proximas revisiones: semanal.*


## Estado Actual (2026-10-28)

### Estado 2026-10-28 (Ciclo 11.52 — Inventario + research frontier + correccion de gaps)

- **Inventario minucioso**: 616 modulos, 348 tests, 43 skills, 25 agentes. 5 modulos frontier sin cablear identificados.
- **Research frontier**: memoria de agentes (survey 2026), OWASP ASI06 memory poisoning, context engineering/compaction, hybrid retrieval, Rust FFI.
- **Correcciones**: import perezoso lancedb; static_embeddings lazy; QueryResultCache cableado; adaptive_search; provenance/trust tagging; F4 ciclos de import (0).
- **Docs**: audit-implementacion-2026-10-28.md, research/frontier-2026-10-28.md, AGENTS.md 43 skills.
- **Verificacion**: Ruff 0, Vulture 0, tests ruscadb_store 11 passed, adaptive_retriever 4 passed, domain purity 0, ciclos 0.
