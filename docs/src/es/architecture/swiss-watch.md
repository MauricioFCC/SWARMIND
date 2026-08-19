# Swiss Watch Pattern — Arquitectura de Coordinacion

El patron **Swiss Watch** es el modelo arquitectonico central de Swarmind. Toma su nombre de los relojes suizos: multiples engranajes (agentes) trabajando en perfecta coordinacion, impulsados por un mecanismo central (coordinator).

## Capas del Sistema

1. **`.opencode/`** — Cerebro: agentes, skills y configuracion como SSOT (23 perfiles de agente, 35 skills, principios base).
2. **`harness/`** — Motor de ejecucion: orquestacion (19 paquetes/56 modulos), memoria/RAG (15 paquetes/34 modulos), hooks, seguridad Zero Trust, tests (4662).
3. **`scripts/`** — Herramientas auxiliares: deploy, export, sync.
4. **`knowledge/`** — Documentos de referencia y conocimiento compartido.

Para la estructura detallada de archivos, ver [Agentes y Skills](../guide/agentes-y-skills.md#sistema-de-archivos).

## Diagrama de Flujo

```
Usuario -> Coordinator -> DifficultyRouter -> TaskPlanner -> DAG de Subtareas
                |                                                  |
          AgentBus (mensajeria)                       Nivel 0: Agentes en paralelo
                |                                                  |
          SessionContext                              Nivel 1: Ejecucion concurrente
                |                                                  |
          AdaptivePlanner                             Nivel N: Consolidacion
                |                                                  |
          Resultado Consolidado < - - - - - - - - - - - - - - - <
```

## Flujo de Ejecucion

1. **RECEIVE**: El coordinator recibe el mensaje del usuario
2. **ROUTE**: `DifficultyRouter` clasifica la complejidad (trivial -> very_complex, 5 niveles)
3. **PLAN**: `TaskPlanner` descompone en un DAG de subtareas con agentes asignados (11 templates)
4. **TRACK**: `SessionContext` preserva el estado entre iteraciones
5. **ADAPT**: `AdaptivePlanner` ajusta la estrategia segun el historial de ejecucion
6. **EXECUTE**: Los niveles independientes se ejecutan en paralelo (Fan-out/Fan-in)
7. **HEAL**: `SelfHealingContext` monitorea timeouts, estancamiento y circuit breakers
8. **CONSOLIDATE**: Los resultados se consolidan y presentan al usuario

## Agentes del Swiss Watch

| Agente | Rol | Se activa cuando |
|--------|-----|-----------------|
| **Coordinator** | Orquestador central | Siempre (punto de entrada unico) |
| **Builder** | Implementacion | Tareas tecnicas, codigo, APIs |
| **Scientist** | Investigacion | Papers, arquitectura, experimentos |
| **Guardian** | Calidad y seguridad | Tests, auditorias, compliance |
| **Evolve** | Auto-mejora | Optimizacion, evolucion del sistema |

## Dynamic Scaling

El sistema ajusta el numero de agentes segun la complejidad de la tarea. El `DifficultyRouter` usa 5 heuristicas:

- Longitud del mensaje
- Cantidad de entidades/verbos tecnicos
- Keywords de alta complejidad
- Cantidad de dominios involucrados
- Ambiguedad o requisitos implicitos

El `AdaptivePlanner` complementa ajustando segun historial de exito/fracaso (tasa de fallo >50% -> re-planifica).

| Complejidad | Agentes | Descripcion |
|-------------|---------|-------------|
| Trivial | 1 | Respuesta directa del coordinator |
| Simple | 2 | Coordinator + 1 especialista |
| Moderate | 3-4 | Coordinator + 2-3 especialistas |
| Complex | 5-7 | Multi-agente con 2 niveles |
| Very Complex | 8-11 | Multi-agente con 3+ niveles |

Las **estrategias de planificacion** disponibles estan documentadas en [Dynamic Scaling — Estrategias](dynamic-scaling.md#estrategias-de-planificacion).

## Beneficios

- **Aislamiento**: Cada agente opera independientemente
- **Escalabilidad**: Se pueden agregar agentes sin modificar la arquitectura
- **Resiliencia**: Si un agente falla, los demas continuan
- **Paralelismo**: Niveles independientes se ejecutan simultaneamente
- **Trazabilidad**: Cada decision queda registrada en el SessionContext
- **Delegacion local (Ollama 4-tier)**: tareas simples/RAG/vision se resuelven con
  modelos locales 2026 (`qwen3:4b`, `deepseek-r1:8b`, `qwen2.5-coder:7b`,
  `qwen3-embedding:0.6b`, `qwen3-vl:4b`) — 0 tokens cloud (TKN), con degradacion
  automatica a cloud si Ollama no esta disponible

## Modulos recientes (2026-08-18)

| Modulo | Ruta | Proposito |
|--------|------|-----------|
| **doc_converter** | `harness/memory_rag/doc_converter.py` | anydoc: Protocol `DocumentConverter` + `AnyDocConverter` (lazy, `firecrawl-anydoc>=0.1.9`), `DOC_EXTENSIONS` (21 extensiones), `DocumentConversionError(path, reason)` |
| **doc_ingester** | `harness/memory_rag/doc_ingester.py` | `DocumentChunker` con `converter` inyectado (DI, default `AnyDocConverter`), `_EXTENSION_TIPO` ampliado (documento/presentacion/hoja_calculo/datos_tabulares), conversion binarios → Markdown antes de chunkear |
| **session_replay** | `harness/observability/session_replay.py` | `SessionReplay` reproduce sesiones grabadas (export markdown/json) + `SessionNotFoundError` |
| **registry (plugins)** | `harness/plugins/registry.py` | Plugin lifecycle: `PluginBase` con `on_load()`/`on_unload()`/`events`, `ToolRegistry.__init__(event_bus=None)` (DI), suscripcion automatica `on_{event}`, `load_all()`/`unload_all()` idempotentes |

**Ver tambien**

- [Composicion del Sistema](composicion.md) — Tecnicas frontier por agente y skill
- [Dynamic Scaling — Estrategias](dynamic-scaling.md) — Estrategias de planificacion
- [Filosofia del Sistema](../guide/filosofia.md) — Principios de diseno
