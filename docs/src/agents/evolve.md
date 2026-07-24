# Evolve — Meta-Agente de Auto-Mejora Continua (ASI-Evolve)

El **evolve** es el meta-agente de auto-mejora del sistema. Orquesta el ciclo **ASI-Evolve** (Learn → Design → Experiment → Analyze → Deploy) para mejorar todos los skills, agentes y configuraciones del ecosistema AGENTIC. Cada mejora debe pagar sus propios tokens (Token Economics): sin delta medible, no hay deploy. Implementa **Forward Deployment Engineering (FDE)**: cada mejora resuelve un delta real identificado en logs y métricas.

## Frontmatter (refleja `.opencode/agents/evolve.md`)

| Campo | Valor |
|-------|-------|
| `name` | `evolve` |
| `domain` | `self-improvement` |
| `triggers` | evolve, self-improve, improve, optimize, automate, skill, cognition, learn, adapt |
| `capabilities` | self_improvement, skill_generation, cognition_sync, agent_evolution, experiment_design, token_economics, harness_optimization, rl_scaling, spec_regression_safety, role_adaptation, forward_deployment, task_autobuild |
| `aliases` | evolve |

## Arquitectura: 3 sub-agentes + 1 autobuilder

El meta-agente evolve orquesta 4 sub-agentes especializados que ejecutan las fases del ciclo ASI-Evolve:

| Sub-agente | Rol | Fase del ciclo |
|-----------|-----|----------------|
| `evolve-researcher` | Investiga la cognition store y experiment database, analiza patrones de mejora, propone la siguiente hipótesis de evolución con código candidato | **Learn → Design** |
| `evolve-engineer` | Recibe el candidato del researcher, lo evalúa contra métricas universales de calidad, mide el impacto de cada cambio | **Experiment** |
| `evolve-analyzer` | Compara resultados vs baseline, identifica qué funcionó y qué no, destila lecciones transferibles para cognition store, recomienda promover/continuar/detener/pivotar | **Analyze** |
| `evolve-autobuilder` | Construye tareas de RL data synthesis autónomamente: sampling de templates desde cognition store, mutación controlada, verificación de validez, anotación con metadatos, push a buffer con prioridad por novedad | **Deploy** (generación continua) |

## Ciclo ASI-Evolve (Learn → Design → Experiment → Analyze → Deploy)

Cada fase tiene métricas target que garantizan eficiencia y evitan ciclos de mejora sin retorno:

| Fase | Descripción | Métrica target |
|------|-------------|----------------|
| **Learn** | Analiza cognition store (lecciones de sesiones anteriores) y experiment DB. Identifica patrones recurrentes y heurísticas aplicables. Busca el mejor snapshot actual como baseline. | Tokens/insight <500 |
| **Design** | Formula UNA hipótesis concreta por ronda (cambio 80/20: 20% esfuerzo → 80% impacto). Debe ser específica, medible, preservar compatibilidad hacia atrás. | Compactación de spec ≥40% vs baseline |
| **Experiment** | Implementa el candidato, ejecuta tests contra métricas universales (estructura, universalidad, FDE coverage, EVO coverage, guardrails, calidad). | Failure-spend ratio <5% |
| **Analyze** | Calcula delta vs baseline. Si mejoró: identifica qué cambio específico causó la mejora. Si empeoró: identifica qué se rompió. Destila lección transferible a cognition store. | Cache-hit rate ≥70% |
| **Deploy** | Aplica FDE checklist: delta real, costo implementación, costo de no-hacer, regresión (SURS), token impact, rollback, success metric, stop-loss. | SURS score ≥90% |

## Capacidades del sistema

| Capacidad | Descripción |
|-----------|-------------|
| **Agent Builder** | Construye agentes desde patrones exitosos identificados en cognition store |
| **Agent Pruner** | Elimina agentes que no funcionan o cuyo rendimiento degrada el sistema |
| **Skill Generator** | Genera skills procedurales desde tareas exitosas ejecutadas por builder/scientist |
| **GEPA Mutation** | Muta prompts de agentes para mejora continua sin degradar métricas existentes |
| **C.A.S.E. Evaluation** | Evalúa respuestas en 4 dimensiones (Correctness, Alignment, Safety, Efficiency) |
| **Nudge System** | Auto-persiste contexto valioso periódicamente para evitar pérdida de conocimiento |
| **Token Economics** | Optimiza costo/task via Cache-Shape Discipline, Structured Compaction, Failure-Spend Governance |
| **Harness Optimization** | Mueve costo del modelo al orquestador (harness). Costo/task = f(harness) > f(modelo) |
| **RL Scaling** | Entrenamiento RL multi-dimensional con PaCoRe Training, LTS Controller Training y 3D RL Data Synthesis |
| **Spec Regression Safety** | Mide regresión via SURS (Specification Upgrade Regression Score). Ningún deploy sin SURS reportado |
| **Role Adaptation** | Roles como first-class entities con runtime switching, composición y evolución en caliente |
| **Forward Deployment** | Cada mejora resuelve un delta real identificado en logs/métricas del sistema |
| **Task Autobuild** | Construcción autónoma de tasks RL data synthesis: 100K+ training samples autónomos |

## Forward Deployment Engineering (FDE) Checklist

Antes de desplegar cualquier mejora, evolve ejecuta 8 verificaciones:

| # | Check | Criterio |
|---|-------|----------|
| 1 | Delta real | ¿Qué problema concreto resuelve? Evidencia en logs/métricas |
| 2 | Costo de implementación | Tokens estimados, tiempo, recursos necesarios |
| 3 | Costo de no-hacer | ¿Cuánto pierde el sistema SIN la mejora? |
| 4 | Regresión | SURS ≥ threshold del escenario (additive ≥95%, refactor 100%, deprecate ≥90%, breaking ≥80%) |
| 5 | Token impact | Impacto positivo en token efficiency |
| 6 | Rollback | ¿Cómo se revierte si falla? |
| 7 | Success metric | ¿Qué mejora y en cuánto? (ej: -X% tokens, +Y% speed, +Z% SURS) |
| 8 | Stop-loss | ¿Cuándo se aborta? Límite de iteraciones sin mejora |

## Activación

Se activa con triggers de evolución: `evolve`, `self-improve`, `improve`, `optimize`, `automate`, `skill`, `cognition`, `learn`, `adapt`. También mediante `!evolve run`, `!evolve engineer`, `!evolve analyze` para invocar sub-agentes específicos. El coordinator lo delega automáticamente cuando detecta oportunidades de mejora continua en el sistema.
