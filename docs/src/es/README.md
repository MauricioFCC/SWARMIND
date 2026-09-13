# Swarmind — Sistema Multi-Agente Evolutivo

![Swarmind](/assets/logo.svg)

**Swarmind** es un sistema multi-agente de orquestacion, ejecucion y auto-mejora continua con
35 skills contextuales (PEC universal), orquestacion multi-nivel, GPU acceleration y token economics.

## Estado Actual (Septiembre 2026)

| Metrica | Valor |
|---------|-------|
| Tests | 5276 collected (TDD suite) · mutation testing ≥70% |
| Agentes | 22 especializados (100% perfiles) |
| Skills | 35 contextuales (100% SKILL.md + SKILL.min.md + **PEC universal**) |
| ADRs frontera | 0065-0080 (surrealdb spike, prompt-cache TTL, llm-grep, cascada STEER, cache-health, Ollama CODING, reanchor+taxonomía, PEC universal, quality/latency/tokens, contexto, skills/agentes, tooling, verify-replan, competición, deepseek-local) |
| Re-anclaje post-compaction | bloque `<<RE-ANCHOR>>` (restaura >90% de restricciones vs ~17% del summary) |
| Routing | complexity + cascade STEER-lite + session-affinity (SAAR) + Ollama 5-tier local + LocalExecutor (triviales = 0 tokens cloud) |
| Votación | fan-out gobernado + batch_vote k-en-1 (input 1× vs k×) + fanout_gate anti-sobre-descomposición |
| Salidas machine-readable | structured_enforcer (JSON schema + retries con feedback + strict keys) |
| Búsqueda de código | llm_grep ripgrep-first 3 capas (lexical → estructural → semántica) + backend tgrep opt-in |
| Competición | cp_spec_gate (4 pilares pre-código) + dual_verify (fast vs brute-force) |
| Trazas | trace_viewer (export trace.jsonl + replay sin LLM) + verify_replan_gate (VMAO) |
| Skills/agentes | skill_composition (calls + invocation + compat) + competence_model (Beta/Thompson) |
| Contexto | artifact_store + cue_ledger + compaction_calibration + prune_then_summarize |
| Tooling | rtk wrapper + idempotency_guard + scripts Python/bash (PowerShell prohibido, corrompe UTF-8) |
| opencode local | default `ollama/qwen3:4b` + 6 modelos registrados + permisos por agente |
| Modulos Orchestrator | 19 paquetes / 142 modulos |
| Modulos Memory/RAG | 14 paquetes / 109 modulos |
| Modulos Validation | cp_spec_gate + dual_verify + mutation/pbt stages + conclusion_gate |
| Modulos Hooks | 4 (security_validator, permission_checker, audit_logger, metrics) |
| Modulos Security | Zero Trust (TokenManager, PolicyEngine, verify_agent_identity) |
| Modulos Multi-Harness | 5 adapters (opencode, claude, codex, cursor, gemini) |
| GPU | RTX 4060 8GB, CUDA 12.6, torch 2.13.0+cu126 (search x10.9, embeddings 41us/msg) |
| Deuda arquitectura (AGR) | 0 archivos >500 lineas en codigo no-test (32 modulos refactor a paquetes) |
| Token savings | -51% capsulas, -40% structured output, -38% cache-shape, hit<60% con volumen = cache-buster flaggeado |
| Vector stores | LanceDB (central) + SQLite-vec (edge) + federated search |
| Observabilidad | OpenTelemetry (trazas, metricas, exportacion OTLP) |
| Orquestacion paralela | ParallelExecutor fan-out nativo + voting gobernado |
| CI | lint / test / security verdes (3-tier: T1 bloquea, T2 mutation, T3 nightly) |
| Principios | base_principles v3.1.0 (36 IDs, taxonomía CHECK/GUIDE, RPA + CPD + TDD adversarial) |
| Lint / dead code | ruff 0 errores, vulture 0 dead code |

El detalle de cobertura por modulo, hitos y roadmap esta en [Estado del Proyecto](roadmap/estado.md).

## Quick Start

Delega una tarea a un agente con `@`:

```bash
python harness/run.py "@builder: implementa una API REST en Rust con endpoints /users CRUD"
```

O sin `@` para deteccion automatica:

```bash
python harness/run.py "investiga papers sobre transformers 2026"
```

Comandos del sistema: `!health`, `!metrics`, `!skill list`, `!session`, `!reset`, `!help`.

Tutorial completo en [Como Usar Swarmind](guide/como-usar.md).

## Novedades Agosto 2026

Los modulos nuevos (Multi-Harness Adapter Layer, Hook System, Zero Trust, Federated Vector Search, SQLite-vec Backend, Async TaskOrchestrator) y los **15 papers 2026 implementados** se documentan en detalle en [Agentes y Skills](guide/agentes-y-skills.md#novedades-julio-2026).

## Documentacion

- [Filosofia](guide/filosofia.md) — Principios de diseno
- [Como Usar](guide/como-usar.md) — Tutorial de uso
- [Opcion A — SSOT Global OpenCode](guide/opcion-a-ssot-global.md) — Config global + mirror local + sync automatico
- [Agentes y Skills (completo)](guide/agentes-y-skills.md) — SSOT de agentes, skills, modulos
- [Arquitectura Swiss Watch](architecture/swiss-watch.md) — Patron de coordinacion
- [Dynamic Scaling](architecture/dynamic-scaling.md) — Estrategias de planificacion
- [Tecnicas Frontier](architecture/composicion.md) — Tecnicas 2026 por agente/skill
- [Manual Tecnico](technical/manual-tecnico.md) — Documentacion tecnica del harness
- [Testing Guide](development/testing-guide.md) — Como escribir y ejecutar tests
- [Glosario](reference/glosario.md) — Terminos y abreviaturas
- [Roadmap](roadmap/estado.md) — Estado del proyecto y proximos pasos
- [Desarrollo](development/modificar.md) — Como modificar y contribuir
- [Comparativa Harness 2026](reference/comparativa-harness-2026.md) — vs ECC, DeerFlow, CowAgent, CodeWhale

## Arquitectura

```
Swarmind/
├── .opencode/        ← SSOT (agentes, skills, config)
├── harness/          ← Motor de ejecucion (orchestrator, memory, hooks, security, tests)
├── docs/src/         ← Documentacion mdbook
└── pyproject.toml
```

![Diagrama de Arquitectura](/assets/diagrams/architecture.svg)

Para la estructura detallada, ver [Agentes y Skills — Sistema de Archivos](guide/agentes-y-skills.md#sistema-de-archivos).

## Benchmark Projects 2026

Swarmind compite con **ECC** (235k stars), **DeerFlow** (78.1k), **CowAgent** (46.2k) y **CodeWhale** (40.2k). La comparativa completa con tabla de capacidades esta en [Comparativa Harness 2026](reference/comparativa-harness-2026.md).

**Diferenciación clave:** GPU Acceleration (search x10.9), Token Economics (-51%), Governance completo, Zero Trust, Hook System determinista, Multi-Harness (5 runtimes), 5276 tests, PEC universal en skills, re-anclaje post-compaction, ejecución local real (0 tokens cloud en triviales).

### Cambios Septiembre 2026 (ADR-0065 .. 0080)

- **Re-anclaje post-compaction** (`reanchor.py`): bloque `<<RE-ANCHOR>>` con N1+rol+skills+estado tras cada compactacion (los summaries retienen ~17%, el bloque restaura >90%); regla RPA en base_principles v3.1.0.
- **base_principles v3.1.0**: taxonomia de adherencia CHECK/GUIDE (IFEval/DRFR), CPD (fundamentos de competicion: checklist edges+invariants+BigO, repair 3 fases 5/80→46/80) + TST/PBT ampliados (AdverTest, mutantes, pairwise t=2→6, BVA, PROBE, MR metamorficas, fuzz) + disciplina R1 (reason→verify→reflect→final).
- **PEC universal (ADR-0072)**: las 35 skills envebidas con persona experta + canon frontera por especialidad + anti-hedging (`scripts/apply_pec.py`, 176 tests).
- **LLM-grep** (`llm_grep.py`, ADR-0067): busqueda de codigo ripgrep-first 3 capas, budget-aware, salida compaction-friendly con alerta de misrouting semantico + backend tgrep opt-in (ADR-0076).
- **Cascada STEER-lite** (`cascade_router.py`, ADR-0068): small→frontier si confianza<0.7 con costo por intento + `cache_health` (flag de cache-buster estructural si hit<60% con volumen) + `model_efficiency_report()` (ADR-0074).
- **Session-affinity** (`session_affinity.py`, ADR-0073): tier sticky por sesion con TTL (patron SAAR: -79% switches, -78.7% costo).
- **Votacion k-en-1** (`batch_vote.py`, ADR-0073): k votos en 1 llamada con el parametro n (input 1x vs kx, arXiv 2604.13717) + fallback + fanout_gate anti-sobre-descomposición (ADR-0075).
- **Structured enforcer** (`structured_enforcer.py`, ADR-0073/0076): JSON schema + retries con feedback (99.9% adherencia) + strict keys contra troyanos.
- **Ollama 5-tier + ejecución real** (ADR-0069/0078): tier CODING (`qwen2.5-coder:7b`) con precedencia + filtro `is_frontier_only()` + `LocalExecutor` (triviales ejecutadas en local, 0 tokens cloud) + `pressure()` + pipeline `prune_then_summarize`.
- **Prompt-cache TTL** (ADR-0066): prefijo estable, prohibido cambio de modelo mid-sesion, TTL chat 3600 / API-subagente 300.
- **Skills 35** (fusión `responsive-ui`→`frontend-uiux` v1.2.0 + nueva `agent-rigor`) + tiers de residencia (REF/Saved/Installed ≤10) + composición (`calls:`, invocation tiers, poda de conflictos, ADR-0075).
- **Agentes con evidencia** (ADR-0075): `competence_model.py` (Beta/Thompson) integrado en `AgentSelector`; `adaptive_planner` degrada a single con baseline fuerte.
- **Contexto optimizado** (ADR-0074): `artifact_store.py` + `cue_ledger.py` (dedup −42%) + `compaction_calibration.py` (AgeMem).
- **Verify-replan + trazas** (ADR-0079): `verify_replan_gate.py` (VMAO) + `trace_viewer.py` (replay sin LLM) + permisos por agente en `opencode.json` + skill `agent-rigor`.
- **Competición aplicada** (ADR-0080): `cp_spec_gate.py` (4 pilares) + `dual_verify.py` (fast vs brute-force).
- **Tooling Linux-first** (ADR-0076): wrapper `rtk` (−90% output bash) + `idempotency_guard` (distributed systems); scripts Python/bash (PowerShell prohibido, corrompe UTF-8).
- **opencode local por defecto** (este equipo): `"model": "ollama/qwen3:4b"` + 6 modelos registrados.
- **CI 3-tier verdes**: required {lint, test, security} PASS (extras dev en CI, SDO+presupuesto skills, safety con ignore CVE-2025-33228 falso-positivo).
- **main sincronizado**: PR #16 mergeado a `main` (`d3934fe`); ADRs 0065-0080 versionados local (pre-push los bloquea, correcto por diseño).

### Cambios Agosto 2026

- Refactor total: **32 modulos >500 lineas a paquetes** (deuda arquitectura AGR = 0), SOLID corregido en 9 clases.
- **ParallelExecutor**: fan-out paralelo nativo (ThreadPoolExecutor `max_workers=3`) + voting gobernado.
- **GPU CUDA 12.6** habilitada (torch 2.13.0+cu126): search x10.9, embeddings 41us/msg.
- **Memoria central SSOT** portable (`Memory_Proyects` via `MEMORY_ROOT`), 7.5 GB liberados, backup automatico.
- **Delegación local Ollama 4-tier**: tareas simples/RAG/visión con modelos locales 2026 (`qwen3:4b`, `deepseek-r1:8b`, `qwen2.5-coder:7b`, `qwen3-embedding:0.6b`, `qwen3-vl:4b`) — 0 tokens cloud (TKN), degradación a cloud automática.
- **Integración anydoc** (`harness/memory_rag/doc_converter.py` + `doc_ingester.py`): binarios → Markdown → RAG con **21 extensiones** (pdf/docx/pptx/xlsx/odt/epub/rtf/csv…), `AnyDocConverter` lazy (firecrawl-anydoc>=0.1.9), `DocumentConversionError(path, reason)` sin tragar errores; ingesta con `rag_ingest.py --include-docs` o `!rag ingest --docs`.
- **Patrones deepseek-harness**: plugin lifecycle (`PluginBase` con `on_load`/`on_unload`/`events`, `ToolRegistry` con `event_bus` DI + suscripción automática `on_{event}`, `load_all`/`unload_all` idempotentes) + session replay (`SessionReplay` export markdown/json, `SessionNotFoundError`) — 59 tests nuevos (30 plugin + 29 replay), registry 94%, session_replay 100%.
- **Arquitecturas RAG frontier (5 evaluadas)**: **Híbrido RRF** (`hybrid_retriever.py` — fusión vector denso + BM25 disperso con Reciprocal Rank Fusion k=60) y **Correctivo CRAG** (`corrective_retriever.py` — validación de calidad pre-generación con query rewrite/fallback, arXiv:2401.15884) IMPLEMENTADOS; **GraphRAG** (knowledge_graph + PageRank de TokenBudgetRouter) y **Agentic RAG** (orchestrator multi-agente) CUBIERTOS; **Multimodal** PARCIAL vía anydoc. 22 tests nuevos.
- Documentacion publica actualizada y depurada.
