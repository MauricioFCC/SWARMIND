> Migrado a references/ por politica focused beats comprehensive - SkillsBench 2026.

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
