# Dynamic Scaling — Escalado Automatico de Agentes

El sistema ajusta automaticamente la cantidad de agentes segun la complejidad de la tarea, utilizando el `DifficultyRouter` y el `AdaptivePlanner`.

## Niveles de Escalado

| Nivel | Agentes | Cuando |
|-------|---------|--------|
| **Micro** (1) | Solo coordinator | Saludos, consultas simples, comandos del sistema |
| **Small** (2-3) | Coordinator + 1-2 especialistas | Tareas simples: crear un archivo, una consulta rapida |
| **Medium** (3-5) | Coordinator + 2-4 especialistas | Tareas moderadas: implementar una funcion, investigar un tema |
| **Large** (5-8) | Coordinator + 4-7 especialistas | Tareas complejas: implementar un modulo completo, disenar una arquitectura |
| **XLarge** (8-11) | Coordinator + 7-10 especialistas | Tareas muy complejas: sistema completo, plataforma multi-componente |

## Como funciona

1. El `DifficultyRouter` analiza el mensaje usando 5 heuristicas:
   - Longitud del mensaje
   - Cantidad de entidades/verbos tecnicos
   - Keywords de alta complejidad
   - Cantidad de dominios involucrados
   - Ambiguedad o requisitos implicitos

2. El `AdaptivePlanner` ajusta la estrategia basado en:
   - Historial de exito/fracaso por estrategia
   - Tasa de fallo >50% → re-planifica con estrategia diferente
   - Feedback de ejecuciones anteriores

## Estrategias de Planificacion

| Estrategia | Descripcion | Cuando usarla |
|------------|-------------|---------------|
| **single_agent** | Un solo agente ejecuta | Tareas triviales |
| **sequential** | Agentes en secuencia | Tareas con dependencias lineales |
| **fan_out_fan_in** | Paralelo + consolidacion | Tareas independientes |
| **hybrid** | Combinacion de las anteriores | Tareas complejas multi-dominio |
| **swarm** | Multiples agentes en paralelo | Tareas muy complejas |

## Ver tambien
- [Swiss Watch Pattern](swiss-watch.md) — Arquitectura general
- [Composicion del Sistema](composicion.md) — Componentes del harness
