# ADR-0103: Frontera Simple 2026 - enrutamiento aprendido, coordinador minimo y token economics medido

- **Status:** Aceptado (roadmap SDD/TDD activo)
- **Date:** 2026-10-12
- **Deciders:** equipo SWARMIND
- **Relacionados:** ADR-0098 (convenciones), ADR-0075 (skills/agentes frontera), ADR-0100 (dispatch obligatorio), ADR-0102 (escalado por verificación), ADR-0039 (subagentes condensados), `.opencode/core/base_principles.md` (SSOT)

## Contexto

SWARMIND es un harness de orquestación multi-agente con runtime propio (85
archivos / 16.665 líneas en `orchestrator/`, ~25 en `model_router/`, 24 agentes,
36 skills). El 2026-10-12 se realizó una retrospectiva + investigación frontera
en 4 frentes (harness engineering, routing de skills/agentes, minimización de
tokens, coordinador next-gen) con fuentes primarias 2025-2026 (arXiv 2609.00006,
2603.22455, 2508.21433, 2607.15516, 2603.13657, 2608.12720, agentskills.io/LF,
Anthropic/OpenAI engineering). El diagnóstico interno verificó:

1. **Clasificación de tareas es heurística pura** (`DifficultyRouter._extract_features`, `ComplexityRouter` lexical) — sin SLM de triage, sin clasificador aprendido. La frontera usa triage en UNA llamada con modelo pequeño → JSON `{intent, shallow|deep}` + cascada (MemFlow 87.7%).
2. **Selección de agentes por keywords + competencia Beta/Thompson** — correcta como piso, pero sin embeddings de capabilities ni fan-out acotado por heterogeneidad (2 diversos ≥ 16 homogéneos; Ringelmann).
3. **Asignación de skills por bundling de dominio (SIGMA) + embeddings** — sólida, pero sin *hidden-body asymmetry* (el router debe leer el CUERPO del skill al puntuar: quitar el cuerpo degrada 29-44pp — SkillRouter arXiv:2603.22455). En el rango de SWARMIND (<100 skills) no se justifica retriever+reranker entrenado: match semántico barato + selección LLM sobre top-k metadata es competitivo.
4. **Coordinator.md de 273 líneas** — prompt largo (anti-patrón 2026: las políticas migran de prosa a configuración; la laundry list degrada el routing).
5. **Token economics implementado pero NO medido** — Cache-Shape, Structured Compaction, Observation Masking y budgets existen; falta telemetría (cached_tokens, hit-rate, tokens/rol) como gate. Sin medir no se sostiene el 30-60% de ahorro.
6. **Debate/votación**: el debate vanilla pierde frente a majority-vote (ACL 2026); SWARMIND ya usa SPRT (frontera), falta el Minority Sentinel.

**Hipótesis:** aplicar las 8 acciones del roadmap "Frontera Simple" (enrutamiento
aprendido, coordinador mínimo, token economics medido, cap de fan-out, digests
de skills) lleva el harness a estado del arte 2026 con MENOS complejidad, no más:
menos prompts, menos agentes homogéneos, más evidencia medida.

## Decision

Adoptar el roadmap **"Frontera Simple 2026"** con 8 acciones priorizadas por
ROI/riesgo (EDV: evidencia medible, no preferencia):

| # | Acción | Impacto | Evidencia |
|---|--------|---------|-----------|
| 1 | Telemetría de tokens/caché (R10): `cached_tokens`, hit-rate, tokens/rol; gate hit-rate <80% bloquea | Gate para todo lo demás | OpenAI/Anthropic caching guides |
| 2 | Cache-shape del prompt: orden fijo `tools→system→estático→dinámico`, breakpoint estable, `prompt_cache_key` por rol | 40-70% input | CAPC arXiv:2607.15516 |
| 3 | Coordinator.md mínimo (~60 líneas) + política en YAML (`coordinator_policy.yaml`) | +routing, −tokens | arXiv:2609.00006 "política en configuración" |
| 4 | Observation masking por defecto (no opcional) | ~50% del agente | arXiv:2508.21433 (Complexity Trap) |
| 5 | Triage SLM: `small_model` → JSON `{intent, complexity}` + cascada fallback al DifficultyRouter | +routing, −costo | MemFlow / NVIDIA AI-Q |
| 6 | Hidden-body router: `SkillRouter`/`AgentDispatcher` leen el cuerpo de MDs al puntuar | +29-44pp skills | SkillRouter arXiv:2603.22455 |
| 7 | Cap fan-out 3-5 agentes heterogéneos; eliminar debate vanilla por majority-vote + Minority Sentinel | −costo, +calidad | Ringelmann, ACL 2026 |
| 8 | Digests sha256 en `skills_registry.yaml` (supply-chain hardening) | Seguridad | SkillsMP, CVE-2025-59536 |

Principio rector: **el mejor sistema sabe cuándo NO usar multi-agente**; el
escalado se satura por encima de ~45% de baseline single-agent (capability
ceiling, arXiv:2512.08296); escribir serial + lectores paralelos (Cognition
2026).

## Consecuencias

### Positivas
- Enrutamiento por evidencia medible (no preferencia) — cierra el loop
  FailureRegistry → router (co-evolución estilo ERSkill).
- Reducción de tokens 30-60% instrumentada con gate de calidad (evita la
  trampa de CompAct-Bench: compactar sin medir cae a 56.7% de precisión).
- Coordinador con prompt mínimo = mejor routing de subagentes (Claude Code:
  >15K tokens de descripciones degrada el routing).
- Skills como supply-chain segura (digests + sandbox).

### Negativas / riesgos
- El triage SLM depende del small_model local (mimo): si falla, cascada
  silenciosa al DifficultyRouter (fallback determinista, sin degradación).
- El recorte del coordinator.md requiere que la política migre a YAML antes de
  borrar líneas (evitar pérdida de doctrina — se preserva todo en
  `coordinator_policy.yaml` + `docs/src/es/architecture/swiss-watch.md`).
- La telemetría añade overhead mínimo (un decorador/contador por call) — se
  mide sin sampling.

### Mitigación
- Todo el cambio es TDD (spec SDD → RED → GREEN → mutation-style asserts).
- Rollback: cada acción es un commit atómico (ATM); `git revert` restaura.
- Los tests de integridad de principios (`test_principles_integrity.py`) y el
  validador de skills (`validate_skills.py --strict`) son gates que impiden
  drift entre los 3 archivos de principios y el registry.

## Roadmap SDD/TDD (spec: `specs/adr0103-frontera-roadmap.md`)

Cada acción sigue el ciclo: **spec SDD con outcome medible → tests RED →
implementación mínima → GREEN → mutation-style → integrate**. Los workstreams
paralelos:

- **WS-A token economics**: acciones 1, 2, 4 (telemetría, cache-shape, masking).
- **WS-B coordinador**: acción 3 (prompt mínimo + política YAML).
- **WS-C routing**: acciones 5, 6, 7 (triage SLM, hidden-body, cap fan-out).
- **WS-D seguridad**: acción 8 (digests sha256).
- **WS-E principios**: nueva regla N1 `RSV` (Retrospectiva de Roadmap) en
  base_principles + min + full, con tests de integridad extendidos.

El roadmap (`docs/src/es/roadmap/estado.md`) **se actualiza con cada hito** y se
vuelve a leer en el análisis retrospectivo periódico (regla `RSV`).