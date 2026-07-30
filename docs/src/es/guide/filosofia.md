# Filosofia del Sistema

Swarmind es un **sistema multi-agente evolutivo** disenido para operar como un reloj suizo: multiples especialistas trabajando en paralelo, sincronizados, sin friccion. Todo esta gobernado por principios inmutables que garantizan calidad, eficiencia y escalabilidad.

## 1. Multi-Agente Evolutivo

El sistema opera con **20 agentes** organizados en una jerarquia funcional donde el coordinator planifica, delega a especialistas (builder, scientist, guardian) y el meta-agente evolve orquesta la auto-mejora continua. Para la jerarquia detallada, ver [Agentes y Skills](agentes-y-skills.md#agentes-20).

**Principio**: ningun agente es isla. Cuando uno escribe, otro investiga y un tercero verifica. El resultado es siempre auditado por al menos dos agentes.

## 2. Swiss Watch Pattern

El **coordinator** es el punto de entrada unico. Implementa el patron Swiss Watch:

1. **RECEIVE**: Usuario envia mensaje (con o sin `@agente`)
2. **ROUTE**: `DifficultyRouter` clasifica la complejidad (trivial -> very_complex)
3. **PLAN**: `TaskPlanner` descompone en un **DAG de subtareas** (11 templates)
4. **TRACK**: `SessionContext` preserva estado entre iteraciones
5. **ADAPT**: `AdaptivePlanner` ajusta estrategia segun historial previo
6. **EXECUTE**: Niveles independientes se ejecutan **en paralelo**
7. **CONSOLIDATE**: Resultados se unifican y presentan al usuario

La sincronizacion es responsabilidad del coordinador, no del usuario. El sistema decide como y cuando paralelizar.

La arquitectura completa esta documentada en [Swiss Watch Pattern](../architecture/swiss-watch.md).

## 3. Research First

Antes de ejecutar cualquier tarea no trivial, el `scientist` investiga el estado del arte:

- **MetaClaw**: +32% accuracy en tareas complejas mediante razonamiento estructurado
- **MARS**: Metacognitive reflection de un solo ciclo para validar supuestos
- **ShapleyFlow**: Atribucion game-theoretic con Shapley values para decidir que agente aporta mas
- **ERL**: Extraccion de heuristicas desde cognition store (+7.8% en benchmark Gaia2)

**Regla**: ninguna implementacion critica comienza sin al menos 3 fuentes validadas. La investigacion no es un lujo, es un paso obligatorio del pipeline.

## 4. IDP — Idempotencia y No Reimplementar

Tres doctrinas que gobiernan cada operacion:

| Principio | Significado |
|-----------|-------------|
| **Idempotencia** | Ejecutar la misma tarea N veces produce el mismo resultado. El sistema detecta y evita trabajo duplicado. |
| **No Reimplementar** | Si un skill o solucion ya existe en el cognition store, se recicla. No se reinventa la rueda. |
| **ShapedCache** | Cache semantico con LRU+TTL que aprende que resultados son reutilizables. Hit rate >60% en ciclos evolutivos. |

El **cognition store** (LanceDB vector store) almacena todo: decisiones, fragmentos de codigo, patrones, experimentos fallidos. Cada busqueda empieza preguntando "¿esto ya se resolvio?".

## 5. Token Economics

Swarmind trata los tokens como un **recurso economico** con presupuestos asignados por rol:

| Tecnica | Ahorro | Mecanismo |
|---------|--------|-----------|
| Structured Output | -40% tokens | JSON Schema tipado en lugar de texto libre |
| Agent Capsules | -51% tokens | Fusion de agentes en un solo prompt cuando las tareas comparten contexto |
| Scoped Context | -35% tokens | Solo inyecta skills relevantes, no todos |
| Context Window Manager | -28% tokens | Compresion progresiva del historial |
| Token Budget Manager | Control granular | Presupuestos diferenciables por rol, con alertas de overspend |

**Objetivo**: maximizar calidad por token gastado. Cada token tiene un costo real y un impacto medible en la calidad del output.

> Detalle de implementacion en [Agentes y Skills — Token Optimizer](agentes-y-skills.md#token-optimizer).

## 6. Quality by Default

Ningun estandar se menciona en el prompt del usuario — todos estan embebidos en los agentes:

- **COD**: Clean Code, DRY, KISS, SSOT, YAGNI, <900LC por archivo
- **DOC**: DocStrings ES-UTF8 obligatorios (Args/Returns/Raises)
- **ERR**: Errores con WHAT+WHY+WHERE, sin `except:pass`
- **TST**: Tests >80% coverage, PBT, mutation testing
- **TKN**: Cache shape, structured compaction, scoped context

El usuario describe **que** quiere. El sistema decide **como** lo hace, aplicando estos estandares automaticamente.

## 7. Evolucion Continua

El agente `evolve` orquesta el ciclo **ASI-Evolve**:

```
Learn -> Design -> Experiment -> Analyze -> Deploy
```

Cada iteracion mejora los skills, los prompts y las heuristicas del sistema. Forward Deployment Engineering (FDE) asegura que cada mejora resuelva un delta real medible. No hay cambio sin validacion.
