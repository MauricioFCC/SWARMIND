# ADR-0044: Paralelismo y Votación Nativos (aportación ORCA 2026)

> **Estado:** Aprobado (2026-08-11)
> **Fecha:** 2026-08-11

## Contexto

Se evaluó ORCA (stablyai/orca), un ADE (Agentic Development Environment) para
flota de agentes en paralelo con BYO subscription, para acciones concretas en
SWARMIND (ahorro de tokens, latencia, velocidad, calidad) mediante mesa de
trabajo con 5 especialistas:

- **explorer** — facts del repo.
- **scientist** — investigación técnica / docs / pricing.
- **architect** — encaje arquitectónico.
- **token-budget-auditor** — análisis cuantitativo.
- **researcher** — benchmark de alternativas (opencode, aider, OpenHands,
  goose, cline).

### Hallazgos de la mesa

1. ORCA **NO es embebible**: app Electron/TypeScript standalone, sin SDK Python.
2. Sus worktrees aislados multiplican el contexto por N (**+200% tokens** en
   fan-out N=3).
3. CLI inestable (proyecto joven ~5 meses, ship diario).
4. Su orquestación duplica la del orchestrator de SWARMIND.

**Ganancias reales verificadas:** paralelismo wall-clock 1.5-4x y calidad por
votación (error -28% a -72% con N votantes independientes, matemática estándar).

## Decisión

NO integrar ORCA como dependencia. Anexar nativamente su aporte:

1. **`harness/orchestrator/parallel_executor.py`** con fan-out paralelo
   (`ThreadPoolExecutor`, `max_workers=3`) sobre `MultiAPIProvider.execute`.
2. **`vote_on_task`** con votación gobernada: gate `score≥70 ∧ confidence<0.7`
   para disparar, N=3 votantes, presupuesto `MAX_TOKENS_BY_AGENT×3` para acotar
   coste.
3. **`get_stats()`** con métricas `fan_out_factor`,
   `tokens_per_parallel_agent`, `voting_events` registradas en
   `token_budgets.yaml`.

## Consecuencias

### Positivas
- Sin dependencia externa; ganancia de paralelismo y votación nativa.
- 21 tests (`test_parallel_executor.py`); suite 4414 verde.

### Negativas
- Las ejecuciones paralelas consumen tokens N veces (acotado por gate +
  presupuesto).
- La votación añade latencia en tareas ambiguas (solo cuando
  `confidence<0.7`).

## Alternativas consideradas

1. **ORCA como provider en MultiAPIProvider** — RECHAZADO: no es un proveedor
   LLM, es una app de escritorio.
2. **ORCA headless como orquestador externo** — RECHAZADO: duplicación con el
   orchestrator y CLI inestable.
3. **Anexar nativamente** — ACEPTADO.

## Commit

- `4408944` — `ParallelExecutor`: fan-out paralelo nativo + votación gobernada,
  aportación ORCA 2026.
