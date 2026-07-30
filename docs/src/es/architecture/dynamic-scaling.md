# Estrategias de Planificacion

> Los niveles de escalado y las heuristicas del `DifficultyRouter` estan documentados en [Swiss Watch — Dynamic Scaling](swiss-watch.md#dynamic-scaling).

## Estrategias de Planificacion

| Estrategia | Descripcion | Cuando usarla |
|------------|-------------|---------------|
| **single_agent** | Un solo agente ejecuta | Tareas triviales |
| **sequential** | Agentes en secuencia | Tareas con dependencias lineales |
| **fan_out_fan_in** | Paralelo + consolidacion | Tareas independientes |
| **hybrid** | Combinacion de las anteriores | Tareas complejas multi-dominio |
| **swarm** | Multiples agentes en paralelo | Tareas muy complejas |

## Ver tambien

- [Swiss Watch Pattern](swiss-watch.md) — Arquitectura general y niveles de escalado
- [Composicion del Sistema](composicion.md) — Componentes del harness
