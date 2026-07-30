# Filosofía del Sistema

Swarmind es un **sistema multi-agente evolutivo** diseñado para operar como un reloj suizo: múltiples especialistas trabajando en paralelo, sincronizados, sin fricción. Todo está gobernado por principios inmutables que garantizan calidad, eficiencia y escalabilidad.

---

## 1. Multi-Agente Evolutivo con 8 Especialistas

El sistema cuenta con **8 agentes** que ejecutan **30 skills** especializados, organizados en una jerarquía funcional:

```
coordinator → Punto de entrada. Planifica, delega y consolida.
├── builder   → Implementa código con calidad automática.
├── scientist → Investiga papers, diseña experimentos, evalúa arquitecturas.
├── guardian  → Verifica calidad, seguridad y testing de vanguardia.
└── evolve    → Meta-agente de auto-mejora continua (ASI-Evolve).
     ├── evolve-researcher → Analiza cognition store, propone hipótesis.
     ├── evolve-engineer   → Implementa mutaciones, ejecuta experimentos.
     └── evolve-analyzer   → Analiza resultados, decide promoción/descartes.
```

**Principio**: ningún agente es isla. Cuando uno escribe, otro investiga y un tercero verifica. El resultado es siempre auditado por al menos dos agentes.

---

## 2. Swiss Watch Pattern

El **coordinator** es el punto de entrada único. Implementa el patrón Swiss Watch:

1. **RECEIVE**: Usuario envía mensaje (con o sin `@agente`)
2. **ROUTE**: `DifficultyRouter` clasifica la complejidad (trivial → very_complex)
3. **PLAN**: `TaskPlanner` descompone en un **DAG de subtareas** (11 templates)
4. **TRACK**: `SessionContext` preserva estado entre iteraciones
5. **ADAPT**: `AdaptivePlanner` ajusta estrategia según historial previo
6. **EXECUTE**: Niveles independientes se ejecutan **en paralelo**
7. **CONSOLIDATE**: Resultados se unifican y presentan al usuario

**Máxima**: la sincronización es responsabilidad del coordinador, no del usuario. El sistema decide cómo y cuándo paralelizar.

---

## 3. Research First

Antes de ejecutar cualquier tarea no trivial, el `scientist` investiga el estado del arte:

- **MetaClaw**: +32% accuracy en tareas complejas mediante razonamiento estructurado
- **MARS**: Metacognitive reflection de un solo ciclo para validar supuestos
- **ShapleyFlow**: Atribución game-theoretic con Shapley values para decidir qué agente aporta más
- **ERL**: Extracción de heurísticas desde cognition store (+7.8% en benchmark Gaia2)

**Regla**: ninguna implementación crítica comienza sin al menos 3 fuentes validadas. La investigación no es un lujo, es un paso obligatorio del pipeline.

---

## 4. IDP — Idempotencia y No Reimplementar

Tres doctrinas que gobiernan cada operación:

| Principio | Significado |
|-----------|-------------|
| **Idempotencia** | Ejecutar la misma tarea N veces produce el mismo resultado. El sistema detecta y evita trabajo duplicado. |
| **No Reimplementar** | Si un skill o solución ya existe en el cognition store, se recicla. No se reinventa la rueda. |
| **ShapedCache** | Caché semántico con LRU+TTL que aprende qué resultados son reutilizables. Hit rate >60% en ciclos evolutivos. |

El **cognition store** (LanceDB vector store) almacena todo: decisiones, fragmentos de código, patrones, experimentos fallidos. Cada búsqueda empieza preguntando "¿esto ya se resolvió?".

---

## 5. Token Economics

Swarmind trata los tokens como un **recurso económico** con presupuestos asignados por rol:

| Técnica | Ahorro | Mecanismo |
|---------|--------|-----------|
| Structured Output | -40% tokens | JSON Schema tipado en lugar de texto libre |
| Agent Capsules | -51% tokens | Fusión de agentes en un solo prompt cuando las tareas comparten contexto |
| Scoped Context | -35% tokens | Solo inyecta skills relevantes, no todos |
| Context Window Manager | -28% tokens | Compresión progresiva del historial |
| Token Budget Manager | Control granular | Presupuestos diferenciables por rol, con alertas de overspend |

**Objetivo**: maximizar calidad por token gastado. Cada token tiene un costo real y un impacto medible en la calidad del output.

---

## 6. Quality by Default

Ningún estándar se menciona en el prompt del usuario — todos están embebidos en los agentes:

- **COD**: Clean Code, DRY, KISS, SSOT, YAGNI, <900LC por archivo
- **DOC**: DocStrings ES-UTF8 obligatorios (Args/Returns/Raises)
- **ERR**: Errores con WHAT+WHY+WHERE, sin `except:pass`
- **TST**: Tests >80% coverage, PBT, mutation testing
- **TKN**: Cache shape, structured compaction, scoped context

El usuario describe **qué** quiere. El sistema decide **cómo** lo hace, aplicando estos estándares automáticamente.

---

## 7. Evolución Continua

El agente `evolve` orquesta el ciclo **ASI-Evolve**:

```
Learn → Design → Experiment → Analyze → Deploy
```

Cada iteración mejora los skills, los prompts y las heurísticas del sistema. Forward Deployment Engineering (FDE) asegura que cada mejora resuelva un delta real medible. No hay cambio sin validación.
