# Coordinator — Swiss Watch Orchestrator

El **coordinator** es el punto de entrada único del sistema. Implementa el patrón **Swiss Watch**: recibe el mensaje del usuario, analiza su complejidad, y delega a los agentes especializados (builder, scientist, guardian, evolve).

## Cómo funciona
1. **RECEIVE**: Usuario envía un mensaje (con o sin @agente)
2. **ROUTE**: `DifficultyRouter` clasifica la complejidad (trivial → very_complex, 5 niveles)
3. **PLAN**: `TaskPlanner` descompone en DAG de subtasks con agentes asignados (11 templates)
4. **TRACK**: `SessionContext` preserva estado entre iteraciones
5. **ADAPT**: `AdaptivePlanner` ajusta estrategia según historial
6. **EXECUTE**: Niveles independientes se ejecutan en paralelo (Fan-out/Fan-in)
7. **CONSOLIDATE**: Resultados se consolidan y presentan al usuario

## Capacidades
- `auto_routing`: Enrutamiento automático sin @mención
- `swarm_coordination`: Coordinación de múltiples agentes
- `multi_agent_parallel`: Ejecución paralela de subtareas
- `circuit_breaker`: Interrupción ante fallos repetidos
- `dynamic_scaling`: 3-11 agentes según complejidad (ADR-0002)
- `pacore`: Parallel Coordination con message-passing (ADR-0017)
- `token_governance`: Economía de tokens (ADR-0018)

## Dispatchers internos
| Dispatcher | Propósito |
|-----------|-----------|
| `AgentDispatcher` | Enruta tareas a skills via LanceDB + YAML |
| `DebateRunner` | Ejecuta debates multi-agente (extraído de TaskOrchestrator) |
| `WriteAheadLog` | Retry con backoff + cancelación (ADR-0017) |
| `Worktable` | Debate entre 13 expertos en calidad de software |

## Activación
Se activa por defecto (default: true, priority: 1). Triggers: plan, organize, coordinate, delegate, manage, orchestrate, task, project, swarm, pipeline, workflow.
