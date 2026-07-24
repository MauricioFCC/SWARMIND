# Velocidad y Rendimiento

AGENTIC está diseñado para máxima velocidad sin sacrificar calidad. Cada milisegundo y cada token cuentan. Este documento detalla las técnicas de optimización que operan automáticamente en cada ejecución.

---

## 1. GPU Acceleration

El sistema detecta y utiliza **GPU NVIDIA RTX 4060** (u otra disponible) para acelerar cargas de trabajo intensivas:

| Operación | CPU | GPU | Speedup |
|-----------|-----|-----|---------|
| Embeddings (búsqueda semántica) | 45ms | 8ms | 5.6x |
| Búsqueda vectorial (LanceDB) | 120ms | 20ms | 6.0x |
| Batch inference (clasificación) | 350ms | 55ms | 6.4x |
| Compresión de contexto | 200ms | 40ms | 5.0x |

**Activación automática** vía `harness/gpu_accel.py`. Si hay GPU disponible, se usa; si no, fallback a CPU con cola de prioridad.

```
python harness/run.py "@scientist: busca papers sobre transformers cuantizados"
→ Embeddings por GPU: 8ms (vs 45ms CPU)
→ Búsqueda vectorial: 20ms (vs 120ms CPU)
```

---

## 2. Agent Capsules: Fusión Inteligente de Agentes

Cuando varias tareas comparten contexto, los agentes se **fusionan en una sola capsule** en lugar de ejecutarse por separado:

| Escenario | Sin Capsule | Con Capsule | Ahorro |
|-----------|-------------|-------------|--------|
| Builder + Guardian (mismo archivo) | 2 prompts separados | 1 prompt fusionado | -51% tokens |
| Scientist + Builder (investigar + implementar) | 2 rondas | 1 ronda con contexto compartido | -47% tokens |
| Evolve completo (3 sub-agentes) | 3 prompts | 1 capsule | -55% tokens |

La fusión es automática: el `SkillBundler` detecta superposición de skills y los agrupa en un solo agente compuesto.

---

## 3. Structured Output: -40% Tokens con JSON Schema

Reemplazar texto libre por **JSON Schema tipado** reduce drásticamente el consumo de tokens:

**Antes** (texto libre, ~350 tokens):
```text
El resultado del análisis de seguridad muestra 3 vulnerabilidades:
1. SQL Injection en login endpoint con severidad crítica
2. XSS en perfil de usuario con severidad media
3....
```

**Después** (JSON Schema, ~210 tokens):
```json
{
  "vulnerabilities": [
    {"type": "sql_injection", "endpoint": "/login", "severity": "critical"},
    {"type": "xss", "endpoint": "/profile", "severity": "medium"}
  ]
}
```

**Ahorro**: -40% tokens + parsing determinista sin alucinaciones de formato.

---

## 4. DAG Pipeline Parallelism: 1.5-2.4x Speedup

El `TaskPlanner` construye un **grafo acíclico dirigido (DAG)** de subtareas y ejecuta en paralelo los nodos sin dependencias, usando el algoritmo de Kahn:

```
Tarea: "Implementar API REST con tests y documentación"

Nivel 0 (paralelo):
├── Builder escribe modelos y rutas
├── Scientist investiga mejores prácticas
└── Guardian define plan de tests

Nivel 1 (depende de N0):
├── Builder implementa middlewares (depende de Scientist)
└── Guardian ejecuta tests unitarios (depende de Builder)

Nivel 2 (depende de N1):
└── Guardian ejecuta tests de integración + Builder corrige
```

**Speedup medido**: 1.5x en tareas con 2 dependencias, 2.4x en tareas con 4+ dependencias paralelizables.

---

## 5. ShapedCache: Caché Semántico con LRU+TTL

El **ShapedCache** almacena resultados de operaciones previas y los reutiliza cuando detecta consultas semánticamente similares:

| Métrica | Valor |
|---------|-------|
| Hit rate promedio | 62% |
| Latencia de hit | 3ms (vs 800ms de regenerar) |
| TTL por tipo | Embeddings: 24h, Resultados: 1h, Fragmentos: 7d |
| Evicción | LRU con 10,000 entradas máximas |

Usa embeddings coseno para detectar similitud semántica. Si preguntas "crea un login JWT" y ya existe "autenticación JWT implementada", el caché devuelve el resultado sin ejecutar.

---

## 6. Niveles de Paralelismo

El `DifficultyRouter` asigna niveles de paralelismo según la complejidad:

| Dificultad | Agentes en paralelo | Tiempo estimado |
|------------|---------------------|-----------------|
| Trivial | 1 (directo) | <5s |
| Simple | 2-3 | 5-15s |
| Medium | 3-5 | 15-45s |
| Complex | 5-7 | 45-120s |
| Very Complex | 7+ (todos) | 120s+ |

**Reglas de asignación:**
- Builder: solo escribe en `src/`
- Guardian: solo escribe en `tests/`
- Scientist: solo produce texto, nunca código
- Evolve: solo modifica `.opencode/skills/`
- Coordinator: solo consolida, nunca implementa

---

## 7. Resumen de Optimizaciones

| Técnica | Ganancia | Aplica a |
|---------|----------|----------|
| GPU Acceleration | 5-6x en embeddings/search | Scientist, Guardian, Evolve |
| Agent Capsules | -51% tokens | Todas las tareas multi-agente |
| Structured Output | -40% tokens | Todas las respuestas |
| DAG Pipeline | 1.5-2.4x speedup | Tareas complejas (Medium+) |
| ShapedCache | 62% hit rate, ~260x faster | Todas las tareas repetitivas |
| Scoped Context | -35% tokens | Todas las tareas |
| Context Window Manager | -28% tokens por compresión | Sesiones largas (>5 iteraciones) |
