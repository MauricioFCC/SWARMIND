> Migrado a references/ por politica focused beats comprehensive - SkillsBench 2026.

## Caso real ORCA 2026 (fuente: ADR-0044)

stablyai/orca (ADE para flota de agentes en paralelo) se evaluo con mesa de 5
especialistas (explorer, scientist, architect, token-budget-auditor,
researcher): NO embebible (Electron/TS sin SDK Python), worktrees aislados
**+200% tokens** en fan-out N=3, CLI inestable, orquestacion duplicada.
**Veredicto: se descarto la herramienta y se adopto su proceso** —
`parallel_executor.py` (fan-out `ThreadPoolExecutor` N=3) + `vote_on_task`
(votacion gobernada gate score>=70 ∧ confidence<0.7, N=3, presupuesto
`MAX_TOKENS_BY_AGENT×3`). Ganancias verificadas: wall-clock 1.5-4x, error
-28% a -72% con N votantes independientes.

## Comandos

- `!iteration` — pipeline fin de iteracion (bugs, security, docs, tokens,
  commit) sobre el harness (`harness/run_commands/handlers_iteration.py`).
- `!rag` — consulta/ingesta de la memoria vectorial
  (`harness/run_commands/handlers_other.py`).

## Agentes que lo usan

- `builder`, `guardian`, `scientist`, `evolve`, `architect`, `researcher`,
  `token-budget-auditor` (`.opencode/agents/`).

## Referencias

- `README.md` (seccion ParallelExecutors/ORCA; comandos `!rag`/`!iteration`).
- `docs/src/es/adr/adr0044-paralelismo-votacion-orca.md` (caso ORCA 2026).
- `docs/.MEJORAS_SWARMIND.md` (seccion 11.3 ParallelExecutor).
- `docs/src/es/roadmap/estado.md` (ParallelExecutor en roadmap).
- `harness/orchestrator/parallel_executor.py`, `harness/validation/pbt_stage.py`,
  `harness/validation/mutation_stage.py`.
