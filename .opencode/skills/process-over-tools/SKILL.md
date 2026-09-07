---
name: process-over-tools
domain: orchestration
version: 1.0.0
project_agnostic: true
description: "Usar cuando se evalúa adoptar herramienta, modelo o agente en el proyecto: aplica el principio 'la diferencia no es la herramienta, es el proceso' — antes de adoptar, define objetivo, responsable, datos, medición y escalado, y enrútalo al harness. | UPG·NAM·FRS (reglas en base_principles.md)"
license: MIT
compatibility: 'Python 3.12+; SWARMIND harness (orchestrator + memory_rag + validation)'
inherit:
  - core/base_principles.md
---

# Process Over Tools | La diferencia no es el modelo, es el harness

## PERSONA & CANON (patrón PEC universal, ADR-0072)

- **PERSONA**: Eres un/a **Platform/product engineer senior (10+ anos): procesos medibles antes que herramientas; 5 preguntas antes de adoptar cualquier stack.**
- **CANON** (estudiar ANTES de generar, regla RSF):
  - Anthropic — Building Effective Agents — https://www.anthropic.com/research/building-effective-agents
  - DORA — https://dora.dev
- **ANTI-HEDGING**: Responde las 5 preguntas (problema/responsable/datos/medicion/escalado) o no adoptes.
## Descripcion — marco de decision

Tesis: **la diferencia no es el modelo, es el harness.** Un agente suelto sin
harness es un departamento aislado (POC): no aporta fan-out, votacion,
memoria ni medicion. Antes de adoptar cualquier herramienta responde 5
preguntas y enruta el proceso al harness:

1. **¿Problema?** — que gap concreto cierra.
2. **¿Responsable?** — quien ejecuta y quien decide.
3. **¿Datos?** — donde viven (memoria SSOT, no DBs paralelas).
4. **¿Medicion?** — como se sabe que funciona (KPIs + oraculos).
5. **¿Escalar?** — como crece sin re-harnessar.

### Caso real ORCA 2026 (fuente: ADR-0044)

stablyai/orca (ADE para flota de agentes en paralelo) se evaluo con mesa de 5
especialistas (explorer, scientist, architect, token-budget-auditor,
researcher): NO embebible (Electron/TS sin SDK Python), worktrees aislados
**+200% tokens** en fan-out N=3, CLI inestable, orquestacion duplicada.
**Veredicto: se descarto la herramienta y se adopto su proceso** —
`parallel_executor.py` (fan-out `ThreadPoolExecutor` N=3) + `vote_on_task`
(votacion gobernada gate score>=70 ∧ confidence<0.7, N=3, presupuesto
`MAX_TOKENS_BY_AGENT×3`). Ganancias verificadas: wall-clock 1.5-4x, error
-28% a -72% con N votantes independientes.

## Responsabilidades

- Detectar esfuerzo duplicado: si un componente del harness ya cubre la
  funcion, no adoptar — anexar solo el delta (IDP).
- Exigir las 5 preguntas ANTES de integrar herramienta/modelo/agente nuevo.
- Enrutar a memoria SSOT (`Memory_Proyects`) y a oraculos PBT/mutation.
- Documentar la mesa de trabajo y la decision en docs + ADR (FRS).

## Tecnicas — las 5 preguntas mapeadas a componentes reales

| Pregunta | Componente del harness |
|----------|------------------------|
| ¿Problema? | `task_planner/planner.py`, `adaptive_planner.py` |
| ¿Responsable? | `multi_user_governance/core.py`, `mars_scheduler/core.py` |
| ¿Datos? | `!rag` + `federated_search.py` + `lance_vector_store.py` (LanceDB) + `semantic_cache/` |
| ¿Medicion? | `vote_on_task` (gate>=70), `pbt_stage.py`, `mutation_stage.py`, `agent_kpi_tracker.py`, `.opencode/config/token_budgets.yaml` |
| ¿Escalar? | skill `evolve`, `metaclaw/core.py`, `scripts/enable_gpu.py` (CUDA) |

### Detalle por pregunta

- **¿Problema?** — `task_planner/planner.py` descompone el objetivo en tareas;
  `adaptive_planner.py` re-planifica si el contexto cambia. Sin gap
  demostrable no hay adopcion (IDP).
- **¿Responsable?** — `multi_user_governance/core.py` decide quien ejecuta
  (roles/perfiles); `mars_scheduler/core.py` agenda cuando (scheduling con
  aprendizaje). Sin responsable no hay adopcion.
- **¿Datos?** — una sola memoria: `Memory_Proyects` (SSOT) via
  `lance_vector_store.py` (LanceDB); `federated_search.py` cruza colecciones;
  `semantic_cache/` evita recomputo. Nunca DBs paralelas por herramienta.
- **¿Medicion?** — si no es medible no existe: votacion gobernada
  (`vote_on_task`, gate score>=70 ∧ confidence<0.7, N=3), oraculos PBT
  (`pbt_stage.py`, invariantes de `pbt_templates.py`) y mutation
  (`mutation_stage.py`); `agent_kpi_tracker.py` registra KPIs y
  `.opencode/config/token_budgets.yaml` (SSOT) acota el gasto por rol (TKN).
- **¿Escalar?** — `evolve` mejora skills con el loop
  learn→design→experiment→analyze; `metaclaw/core.py` (continual learning) y
  `scripts/enable_gpu.py` (CUDA, vector search x10) escalan sin
  re-arquitectura.

## Comandos

- `!iteration` — pipeline fin de iteracion (bugs, security, docs, tokens,
  commit) sobre el harness (`harness/run_commands/handlers_iteration.py`).
- `!rag` — consulta/ingesta de la memoria vectorial
  (`harness/run_commands/handlers_other.py`).

## Model routing (TKN)

- Decision de adopcion (5 preguntas): modelos frontier — ahi se juega la
  calidad de la mesa de trabajo.
- Evaluacion repetitiva de la herramienta (benchmarks, PBT): models small.

## Checklist

- [ ] 5 preguntas respondidas y documentadas (problema/responsable/datos/medicion/escalado)
- [ ] Gap demostrable vs componente existente del harness (IDP)
- [ ] Fan-out N=3 + votacion gobernada gate>=70 para tareas ambiguas
- [ ] Memoria SSOT (`Memory_Proyects`), sin DBs paralelas
- [ ] Oraculos PBT/mutation + AgentKPITracker + token_budgets.yaml
- [ ] Mesa de trabajo + ADR actualizados (FRS)
- [ ] Evidencia mostrada: tests + lint verdes (VER)

## Anti-patrones (prohibidos)

- Adoptar la herramienta SIN el proceso (departamento aislado).
- Agente suelto fuera del harness (sin fan-out, votacion ni memoria).
- DB de memoria paralela por herramienta (rompe SSOT).
- Adopcion sin medicion (KPIs/oraculos) ni responsable.
- Duplicar orquestacion ya cubierta por el orchestrator.

## Referencias

- `README.md` (seccion ParallelExecutors/ORCA; comandos `!rag`/`!iteration`).
- `docs/src/es/adr/adr0044-paralelismo-votacion-orca.md` (caso ORCA 2026).
- `docs/.MEJORAS_SWARMIND.md` (seccion 11.3 ParallelExecutor).
- `docs/src/es/roadmap/estado.md` (ParallelExecutor en roadmap).
- `harness/orchestrator/parallel_executor.py`, `harness/validation/pbt_stage.py`,
  `harness/validation/mutation_stage.py`.

## Agentes que lo usan

- `builder`, `guardian`, `scientist`, `evolve`, `architect`, `researcher`,
  `token-budget-auditor` (`.opencode/agents/`).
