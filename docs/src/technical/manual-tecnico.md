# Manual Técnico — AGENTIC Harness

**Versión:** 0.1.0  
**Última actualización:** Julio 2026  
**Repositorio:** `agentic-harness`  
**Python mínimo:** 3.10+

---

## Índice

1. [Arquitectura del Sistema](#1-arquitectura-del-sistema)
2. [Componentes del Harness](#2-componentes-del-harness)
   - [orchestrator/](#21-orchestrator)
   - [memory_rag/](#22-memory_rag)
   - [tools_sandbox/](#23-tools_sandbox)
3. [Flujo de Datos](#3-flujo-de-datos)
4. [API Reference](#4-api-reference)
5. [Token Economics](#5-token-economics)
6. [Concurrencia](#6-concurrencia)
7. [Testing](#7-testing)

---

## 1. Arquitectura del Sistema

### 1.1 Visión General

AGENTIC Harness es un **orquestador multi-agente** con arquitectura **Plan-and-Execute** que descompone tareas del usuario en un DAG (Directed Acyclic Graph) de subtareas atómicas, las asigna a agentes especializados y coordina su ejecución paralela con auto-recuperación.

```
                    ┌─────────────────────────────────────┐
                    │           USUARIO (prompt)           │
                    └──────────────┬──────────────────────┘
                                   │
                    ┌──────────────▼──────────────────────┐
                    │         TaskOrchestrator            │
                    │  (Plan-and-Execute + Self-Healing)  │
                    └──────┬──────────┬──────────┬───────┘
                           │          │          │
              ┌────────────▼──┐ ┌─────▼──────┐ ┌─▼──────────┐
              │  TaskPlanner  │ │ AgentBus   │ │SessionCtx  │
              │  (DAG+11 tpl) │ │(Slack-like)│ │(Persist)   │
              └───────┬───────┘ └──────┬──────┘ └─────┬──────┘
                      │                │              │
         ┌────────────▼────────────────▼──────────────▼──────┐
         │              Agent Dispatcher + DifficultyRouter   │
         │         (LanceDB skills + routing por complejidad) │
         └──────┬──────────────────────────────────┬─────────┘
                │                                  │
     ┌──────────▼──────────┐        ┌──────────────▼──────────┐
     │  builder (src/)     │        │  guardian (tests/)      │
     │  scientist (texto)  │        │  coordinator (merge)    │
     │  evolve (meta)      │        │  ... (3-11 agentes)     │
     └─────────────────────┘        └─────────────────────────┘
```

### 1.2 Patrón Swiss Watch

El sistema sigue el patrón **Swiss Watch**: un coordinador central (TaskOrchestrator) descompone tareas y orquesta agentes especializados que operan en **directorios separados** para evitar colisiones de archivos.

| Agente | Rol | Directorio | Tipo de output |
|--------|-----|-----------|----------------|
| `builder` | Implementa código | `src/` | Código fuente |
| `guardian` | Tests + calidad | `tests/` | Tests + reportes |
| `scientist` | Investigación | — (texto) | Documentos/análisis |
| `coordinator` | Orquestación | — | Planes + merge |
| `evolve` | Auto-mejora | Meta-skills | Optimizaciones |

### 1.3 Dynamic Scaling (3–11 Agentes)

El `ScopeAnalyzer` determina cuántos builders y guardians lanzar según la complejidad de la tarea, escalando de 3 a 11 agentes:

| Nivel | Agentes | Caso típico |
|-------|---------|-------------|
| Trivial | 1–2 | "Hola", saludo simple |
| Simple | 2–3 | "Corrige este bug" |
| Moderate | 3–5 | "Implementa un endpoint" |
| Complex | 5–8 | "API REST completa con tests" |
| Very Complex | 8–11 | "Microservicio completo + CI/CD + docs" |

### 1.4 Diagrama de Componentes

```
┌──────────────────────────────────────────────────────────────────┐
│                     AGENTIC HARNESS                              │
│                                                                  │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │                    orchestrator/                         │   │
│  │  ┌─────────────┐ ┌──────────┐ ┌──────────┐ ┌─────────┐  │   │
│  │  │TaskOrch     │ │TaskPlan  │ │AgentBus  │ │Debate   │  │   │
│  │  │+self-healing│ │(DAG+11t) │ │(msg bus) │ │Orch     │  │   │
│  │  └──────┬──────┘ └──────────┘ └────┬─────┘ └─────────┘  │   │
│  │         │                          │                     │   │
│  │  ┌──────▼──────┐ ┌──────────┐ ┌───▼────────┐           │   │
│  │  │Difficulty   │ │SessionCtx│ │AsyncAgent  │           │   │
│  │  │Router       │ │(Persist) │ │Bus (async) │           │   │
│  │  └─────────────┘ └──────────┘ └────────────┘           │   │
│  │                                                         │   │
│  │  ┌──────────┐ ┌────────┐ ┌────────┐ ┌──────────────┐   │   │
│  │  │HITLGuard │ │Sandbox │ │Write   │ │Federated     │   │   │
│  │  │(HITL)    │ │Loop    │ │AheadLog│ │Memory        │   │   │
│  │  └──────────┘ └────────┘ └────────┘ └──────────────┘   │   │
│  └──────────────────────────────────────────────────────────┘   │
│                                                                  │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │                    memory_rag/                           │   │
│  │  ┌──────────────┐ ┌─────────────┐ ┌────────────────┐    │   │
│  │  │LanceVector    │ │SemanticCache│ │ContextWindow    │    │   │
│  │  │Store (CRUD)   │ │(LLM cache)  │ │Manager         │    │   │
│  │  └──────────────┘ └──────┬──────┘ └────────┬───────┘    │   │
│  │                          │                 │            │   │
│  │  ┌──────────────┐ ┌──────▼──────┐ ┌────────▼───────┐   │   │
│  │  │SkillRouter   │ │ShapedCache  │ │TokenBudget     │   │   │
│  │  │(semantic)    │ │(LRU+TTL)    │ │(per-agent)     │   │   │
│  │  └──────────────┘ └─────────────┘ └────────────────┘   │   │
│  └──────────────────────────────────────────────────────────┘   │
│                                                                  │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │                   tools_sandbox/                         │   │
│  │  ┌──────────┐ ┌──────────┐ ┌──────────┐                │   │
│  │  │MCPClient │ │MCPManager│ │MCPExecutor                │   │
│  │  │(JSON-RPC)│ │(pool)    │ │(subprocess sandbox)       │   │
│  │  └──────────┘ └──────────┘ └──────────┘                │   │
│  └──────────────────────────────────────────────────────────┘   │
└──────────────────────────────────────────────────────────────────┘
```

---

## 2. Componentes del Harness

### 2.1 orchestrator/

#### 2.1.1 TaskOrchestrator

**Archivo:** `harness/orchestrator/task_orchestrator.py` (994 líneas)

El `TaskOrchestrator` es el componente central que implementa el pipeline **Plan-and-Execute** con self-healing. Conecta `TaskPlanner` → `SessionContext` → `AgentBus` → dispatch.

**Pipeline completo para cada mensaje:**

```
  RECEIVE → ROUTE → PLAN → TRACK → ADAPT → EXECUTE → HEAL → TELEMETRY → CONSOLIDATE
    ①        ②      ③      ④       ⑤       ⑥        ⑦       ⑧           ⑨
```

**Características clave:**

- **Circuit Breaker global:** Abre tras 5 fallos consecutivos, auto-recupera tras 60s
- **Confidence-gated early stopping:** Salta niveles de validación si la confianza es >90%
- **ShapedCache integration:** Cache semántico (-38% tokens)
- **Idempotencia:** Ventana de 30s para mensajes duplicados
- **Self-healing por sesión:** Timeouts por nivel, detección de estancamiento

**Ejemplo de uso:**

```python
from harness.orchestrator.task_orchestrator import TaskOrchestrator, enable_cache
from harness.tests.mock_vector_store import MockVectorStore

# Inicializar con store mock (para tests)
store = MockVectorStore()
orch = TaskOrchestrator(vector_store=store)

# Habilitar cache semantico (Token Economics)
enable_cache(orch, max_tokens=50000)

# Procesar mensaje
result = orch.process_message("implementa una API REST en Rust con Axum")

# Inspeccionar resultado
print(f"Sesión: {result.session_id}")
print(f"Plan: {result.plan.template_name}")
print(f"Nivel actual: {len(result.current_level)} subtasks")
print(f"Completado: {result.is_complete}")

# Ejecutar debate multi-agente
if result.is_debate:
    debate_result = orch.run_debate(
        session_id=result.session_id,
        task="Elegir framework web para API REST",
        agents=["builder", "scientist", "guardian"],
        strategy="consensus",
    )
    print(f"Confianza tras debate: {debate_result.confidence:.2f}")
```

#### 2.1.2 TaskPlanner

**Archivo:** `harness/orchestrator/task_planner.py` (615 líneas)

Descompone mensajes del usuario en un DAG de subtareas atómicas usando **11 templates** predefinidos.

**Templates disponibles:**

| Template | Triggers | Subtasks | Agentes |
|----------|----------|----------|---------|
| `swarm_default` | implement, create, build, haz, crea... | 9 | builder×3, guardian×3, scientist, coordinator×2 |
| `implement_api` | api, rest, graphql, grpc... | 4 | builder, guardian×3 |
| `fix_bug` | bug, fix, error, issue... | 4 | scientist, builder, guardian×2 |
| `research` | research, study, analysis... | 3 | scientist×2, guardian |
| `refactor` | refactor, cleanup, deuda técnica... | 4 | scientist, builder, guardian×2 |
| `security_audit` | security, audit, hardening... | 4 | guardian×2, builder, guardian |
| `deploy` | deploy, release, producción... | 4 | builder×2, guardian×2 |
| `docs` | document, docs, manual... | 3 | scientist, guardian×2 |
| `test` | test, coverage, pruebas... | 4 | scientist, guardian×3 |
| `database` | database, db, sql, schema... | 4 | scientist, builder, guardian×2 |
| `debate` | debate, consenso, votar... | 5 | coordinator×2, builder, scientist, guardian |
| `general` | (fallback) | 5 | builder, guardian×2, scientist, coordinator |

**Estructura de un plan (DAG):**

```python
from harness.orchestrator.task_planner import TaskPlanner

planner = TaskPlanner()
plan = planner.decompose("implementa una API REST en Rust con Axum y tests")

print(f"Template: {plan.template_name}")
print(f"Subtask count: {len(plan.subtasks)}")

for level_idx, level in enumerate(plan.get_levels()):
    print(f"\nNivel {level_idx} ({'⚡ PARALELO' if len(level)>1 else '→ SECUENCIAL'}):")
    for st in level:
        deps = f" [deps: {', '.join(st.dependencies)}]" if st.dependencies else ""
        print(f"  [{st.agent}] {st.description}{deps}")
```

**Salida típica:**
```
Template: swarm_default
Subtask count: 9

Nivel 0 (⚡ PARALELO):
  [coordinator] PLAN: dividir trabajo en modulos...
  [scientist] INVESTIGAR: mejores practicas y alternativas...
Nivel 1 (⚡ PARALELO):
  [builder] CORE: implementar logica de negocio en src/core/...
  [builder] API: implementar endpoints y routing en src/api/...
  [builder] DB: implementar modelos y migraciones en src/db/...
Nivel 2 (⚡ PARALELO):
  [guardian] TESTS: escribir tests unitarios en tests/...
  [guardian] DOCS: documentar API, modulos y ejemplos...
Nivel 3 (→ SECUENCIAL):
  [guardian] BUGFIX: ejecutar tests, identificar fallos y corregir...
Nivel 4 (→ SECUENCIAL):
  [coordinator] CONSOLIDAR: integrar todos los modulos...
```

#### 2.1.3 AgentBus

**Archivo:** `harness/orchestrator/agent_bus.py` (689 líneas)

Bus de mensajes entre agentes con persistencia en LanceDB. Funciona como "Slack para agentes".

**Tipos de mensaje:** `request`, `response`, `error`, `notification`, `escalation`  
**Estados:** `sent`, `delivered`, `acknowledged`

```python
from harness.orchestrator.agent_bus import AgentBus
from harness.tests.mock_vector_store import MockVectorStore

store = MockVectorStore()
bus = AgentBus(vector_store=store)

# Enviar mensaje
msg_id = bus.post_message(
    channel="#session-abc123",
    from_agent="@coordinator",
    to_agent="@builder",
    message="🎯 TU TAREA: implementar API en src/api/",
    message_type="request",
)

# Poll de mensajes no leídos
mensajes = bus.poll_channel("#session-abc123", "@builder")
for m in mensajes:
    print(f"[{m['message_type']}] {m['from_agent']}: {m['message'][:80]}")

# Batch de mensajes
ids = bus.post_message_batch([
    {"channel": "#session-xyz", "from_agent": "@c1", "to_agent": "@b1",
     "message": "tarea 1", "message_type": "request"},
    {"channel": "#session-xyz", "from_agent": "@c1", "to_agent": "@b2",
     "message": "tarea 2", "message_type": "request"},
])
```

#### 2.1.4 AsyncAgentBus

**Archivo:** `harness/orchestrator/agent_bus.py` (clase `AsyncAgentBus`, línea 631)

Versión asíncrona con `asyncio.Queue` para coordinación PaCoRe (ADR-0017). Reduce overhead 95% y acelera 4.8x vs versión síncrona.

```python
from harness.orchestrator.agent_bus import AsyncAgentBus
import asyncio

async def ejemplo():
    bus = AsyncAgentBus()
    
    # Publicar concurrentemente
    await asyncio.gather(
        bus.post_message("#debate", {"agente": "builder", "voto": "Axum"}),
        bus.post_message("#debate", {"agente": "scientist", "voto": "Actix"}),
        bus.post_message("#debate", {"agente": "guardian", "voto": "Axum"}),
    )
    
    # Consumir con timeout
    try:
        msg = await bus.consume("#debate", timeout=5.0)
        print(f"Recibido: {msg}")
    except asyncio.TimeoutError:
        print("Timeout - no hay mensajes")
```

#### 2.1.5 DebateOrchestrator

**Archivo:** `harness/orchestrator/debate_orchestrator.py` (856 líneas)

Orquesta debates multi-agente con 3 estrategias (Princeton NLP 2026: +2.1 puntos de precisión vs single-agent).

**Estrategias:**

| Estrategia | Descripción | Agentes mínimos |
|-----------|-------------|-----------------|
| `CONSENSUS` | Todos responden independientemente, luego votan | 2 |
| `CRITIQUE` | Agente primario responde, secundario critica, refinamiento | 2 |
| `DELIBERATION` | Debate secuencial donde cada agente construye sobre el anterior | 2 |

```python
from harness.orchestrator.debate_orchestrator import (
    DebateOrchestrator, DebateStrategy
)

orch = DebateOrchestrator()

# Estrategia CONSENSUS
result = orch.debate(
    task="¿Qué framework web elegir para API REST en Rust?",
    agents=["builder", "scientist", "guardian"],
    strategy=DebateStrategy.CONSENSUS,
    max_rounds=2,
)

print(f"Confianza: {result.confidence:.2f}")
print(f"Acuerdo entre agentes: {result.agent_agreement:.2f}")
print(f"Respuesta final: {result.final_answer[:200]}")

# Versión asíncrona (PaCoRe - O(n)→O(1))
import asyncio
async def debate_async():
    result = await orch._execute_consensus_async(
        task="Elegir stack para microservicio",
        agents=["builder", "scientist"],
        max_rounds=2,
        dispatch_fn=orch._default_dispatch,
        session_id="async-test",
    )
    return result

result_async = asyncio.run(debate_async())
```

#### 2.1.6 ConfidenceScorer

**Archivo:** `harness/orchestrator/confidence_scorer.py` (486 líneas)

Evalúa la confianza de outputs de agente usando **7 señales heurísticas**:

| Señal | Peso | Descripción |
|-------|------|-------------|
| `length` | 0.25 | Ratio output/task (Goldilocks: 2x–20x) |
| `hedging` | 0.25 | Ausencia de lenguaje de incertidumbre |
| `self_correction` | 0.20 | Ausencia de auto-corrección excesiva |
| `speed` | 0.30 | Velocidad de generación (solo si hay duration) |
| `agreement` | — | Acuerdo entre múltiples agentes (score_debate) |

```python
from harness.orchestrator.confidence_scorer import ConfidenceScorer

scorer = ConfidenceScorer()

# Scoring individual
score = scorer.score_completion(
    task="Implementa una función de ordenamiento",
    result="Aquí está la implementación del quicksort...",
    agent="builder",
    duration_ms=1200.0,
)

print(f"Confianza: {score.score:.2f} ({score.level})")
print(f"Señales: {score.signals}")
print(f"Early stopping posible: {score.should_stop}")

# Scoring de acuerdo entre agentes
agreement = scorer.score_debate_agreement({
    "builder": "Usar Axum para la API...",
    "scientist": "Axum muestra mejor rendimiento...",
    "guardian": "Axum tiene mejor cobertura de tests...",
})
print(f"Acuerdo: {agreement.score:.2f}")
```

#### 2.1.7 SessionContext

**Archivo:** `harness/orchestrator/session_context.py` (381 líneas)

Preserva el estado de ejecución a través de iteraciones. Persiste automáticamente a LanceDB.

```python
from harness.orchestrator.session_context import SessionContext
from harness.orchestrator.task_planner import TaskPlanner

ctx = SessionContext()
planner = TaskPlanner()
plan = planner.decompose("implementa API REST")

# Crear o reanudar sesión
session = ctx.get_or_create("implementa API REST", plan)
print(f"Sesión: {session.session_id}")

# Marcar subtask como completada
ctx.mark_subtask_done(session, "st-1", "Código implementado")

# Ver progreso
status = ctx.get_status(session)
print(status)
```

**Salida de `get_status()`:**
```
🔵 Sesión: a1b2c3d4
📝 Tarea original: implementa API REST
📊 Progreso: 1/4 subtasks

✅ Completadas (1):
   ✅ [builder] CODIGO: implementar API en src/
      → Código implementado...

⏳ Siguiente nivel (⚡ PARALELO):
   ⏳ [guardian] TESTS: escribir tests unitarios...
   ⏳ [guardian] DOCS + SEGURIDAD...
```

#### 2.1.8 SelfHealingContext

**Archivo:** `harness/orchestrator/self_healing.py` (197 líneas)

Implementa Circuit Breaker y detección de fallos por sesión.

```python
from harness.orchestrator.self_healing import CircuitBreaker, SelfHealingContext

# Circuit Breaker individual
cb = CircuitBreaker(failure_threshold=3, recovery_timeout=30.0)

if cb.is_available:
    try:
        # operación riesgosa
        cb.record_success()
    except Exception:
        cb.record_failure()

# Contexto de self-healing por sesión
healing = SelfHealingContext(
    session_id="abc-123",
    level_timeout_sec=300.0,
    stall_timeout_sec=120.0,
)

healing.advance_level(1)

timeout = healing.check_timeout()  # None si ok
stalled = healing.check_stalled()  # None si ok

print(healing.to_dict())
# {'session_id': 'abc-123', 'level': 1, 'level_age_sec': 5.2, ...}
```

#### 2.1.9 DifficultyRouter

**Archivo:** `harness/orchestrator/difficulty_router.py` (396 líneas)

Clasifica tareas en **5 niveles de complejidad** y selecciona el pipeline óptimo.

**Heurísticas de clasificación:**

| Feature | Peso máximo |
|---------|-------------|
| Longitud (>1000 chars) | +0.3 |
| Keywords alta complejidad | +0.4 |
| Verbos técnicos | +0.3 |
| Ambigüedad | por pattern |
| Multi-dominio (≥3) | +0.3 |
| Bullet points | +0.1 |
| Code blocks | +0.15 |
| Keywords baja complejidad | -0.3 (descuento) |

```python
from harness.orchestrator.difficulty_router import DifficultyRouter

router = DifficultyRouter()

decision = router.route("Implementar API REST con Docker, CI/CD y documentación")

print(f"Complejidad: {decision.complexity.value}")  # very_complex
print(f"Pipeline: {decision.pipeline.value}")        # deep
print(f"Score: {decision.score:.2f}")                # 0.85
print(f"Dominios: {decision.features.domains_found}")
print(f"Subtask estimadas: {decision.features.estimated_subtasks}")
```

#### 2.1.10 AgentDispatcher

**Archivo:** `harness/orchestrator/agent_dispatcher.py` (327 líneas)

Enruta tareas a skills relevantes usando LanceDB + registro YAML. Si existe un skill con similitud >70%, inyecta su contenido `.md` en el contexto.

```python
from harness.orchestrator.agent_dispatcher import AgentDispatcher

dispatcher = AgentDispatcher()

# Búsqueda de skill
skill = dispatcher.find_skill_for_task("implementar estrategia de trading cuantitativo")
if skill:
    print(f"Skill: {skill['name']} (similitud: {skill['similarity']:.2f})")

# Dispatch completo
result = dispatcher.dispatch(
    agent_role="builder",
    task_description="implementa API REST con Axum en Rust",
)
print(f"Usó skill: {result['used_skill']}")
print(f"Modo: {result['reasoning_mode']}")

# Dispatch asíncrono con plan context
import asyncio
async_result = asyncio.run(dispatcher.dispatch_async(
    agent_role="builder",
    task_description="implementa modelo de datos",
    plan_context={
        "session_id": "abc-123",
        "plan_summary": "Plan de 4 subtasks...",
        "current_level": [...],
        "previous_results": [...],
    },
))
```

#### 2.1.11 HITLGuard

**Archivo:** `harness/orchestrator/hitl_guard.py` (390 líneas)

Human-in-the-Loop para acciones destructivas. Intercepta operaciones peligrosas y requiere aprobación humana.

**3 modos de operación:**

- `hitl` (default): Pregunta por cada acción destructiva
- `auto_pilot`: Salta todos los checks (entornos confiables)
- `hitl_sensitive`: Solo intercepta patrones críticos

**Patrones destructivos detectados:**

| Categoría | Patrones | Severidad |
|-----------|----------|-----------|
| Base de datos | DROP TABLE, DELETE sin WHERE, TRUNCATE | critical |
| Filesystem | rm -rf, mkfs, dd, > /dev/ | critical |
| Infraestructura | terraform apply/destroy, kubectl delete --force | critical/high |
| Git | git push --force | high |
| Docker | docker rm -f, system prune -f | high |

```python
from harness.orchestrator.hitl_guard import HITLGuard

guard = HITLGuard(mode="hitl")

# Check rápido
check = guard.check_action("DROP TABLE users", "data-architect")
if not check["approved"]:
    print(f"⚠️  Bloqueado: {check['reason']}")
    approved = guard.request_approval("DROP TABLE users", "data-architect")
    if approved:
        print("✅ Aprobado por humano")

# Método conveniencia
if guard.check_and_approve("rm -rf /data", "devops"):
    print("Acción permitida")
```

#### 2.1.12 SandboxLoop

**Archivo:** `harness/orchestrator/sandbox_loop.py` (447 líneas)

Bucle autónomo de calidad: ejecuta tests, notifica resultados, y escala si el circuit breaker se dispara.

```
┌──────────┐    ┌──────────┐    ┌──────────┐
│ Software │───►│ Sandbox  │───►│ ¿Tests   │
│ Engineer │    │ Loop     │    │ pasan?   │
└──────────┘    └──────────┘    └────┬─────┘
                                     │
                    ┌────────────────┼────────────┐
                    ▼                ▼            ▼
              ┌──────────┐    ┌──────────┐  ┌──────────┐
              │ Notificar│    │ Notificar│  │ Escalar  │
              │ @quality │    │ @engineer│  │ a humano │
              │  gate    │    │ + retry  │  │ (CB)     │
              └──────────┘    └──────────┘  └──────────┘
```

```python
from harness.orchestrator.sandbox_loop import SandboxLoop

loop = SandboxLoop()

# Ciclo individual
exito, resultado = loop.execute_cycle(
    task_description="Implementar función de ordenamiento",
    code="def test_sort(): assert sorted([3,1,2]) == [1,2,3]",
    test_command="pytest",
    task_id="task-001",
)
print(f"Tests pasaron: {exito}")

# Bucle autónomo completo (hasta 5 iteraciones)
exito, resultado = loop.run_autonomous(
    task_id="task-002",
    code="def test_foo(): assert 1+1 == 2",
    max_iterations=5,
)
```

#### 2.1.13 FederatedMemory

**Archivo:** `harness/orchestrator/federated_memory.py` (569 líneas)

Sincroniza conocimiento entre proyectos mediante archivos JSON compartidos.

```python
from harness.orchestrator.federated_memory import (
    FederatedMemoryStore, KnowledgeType
)

store = FederatedMemoryStore(
    project_name="agentic",
    auto_sync=True,
    sync_interval_sec=300,
)

# Almacenar conocimiento
store.store_knowledge(
    key="task_planner:optimal_subtask_count",
    value=5,
    ktype=KnowledgeType.PATTERN,
    source_agent="planner",
    tags=["optimization"],
)

# Consultar conocimiento de otros proyectos
records = store.query_knowledge(
    key_prefix="task_planner",
    min_confidence=0.7,
)
for r in records:
    print(f"{r.key} = {r.value} (de {r.source_project})")

# Sincronizar manualmente
imported = store.sync()
print(f"{imported} registros importados")
```

#### 2.1.14 WriteAheadLog

**Archivo:** `harness/orchestrator/write_ahead_log.py` (280 líneas)

Write-Ahead Log con retry con backoff exponencial, cancelación y recuperación.

**Estados:** `pending` → `committed` / `failed` / `cancelled`

```python
from harness.orchestrator.write_ahead_log import WriteAheadLog

wal = WriteAheadLog(log_dir="./.wal")

# Registrar operación
entry = wal.begin(
    operation_type="llm_call",
    payload={"prompt": "genera código...", "model": "claude-4"},
    max_retries=3,
)

# Ejecutar con reintento automático
try:
    result = wal.execute(entry, mi_funcion_llm, arg1, arg2)
    print(f"Operación {entry.operation_id} exitosa")
except RuntimeError as e:
    print(f"Fallo tras reintentos: {e}")

# Cancelar operación pendiente
wal.cancel(entry.operation_id)

# Recuperar operaciones pendientes tras crash
pending = wal.recover_pending()
for p in pending:
    print(f"Pendiente: {p.operation_id} ({p.operation_type})")
```

---

### 2.2 memory_rag/

#### 2.2.1 LanceVectorStore

**Archivo:** `harness/memory_rag/lance_vector_store.py` (779 líneas)

CRUD vectorial unificado sobre LanceDB. LanceDB es **obligatorio**; el fallback in-memory solo es para tests.

**Colecciones predefinidas:**

| Colección | Propósito |
|-----------|-----------|
| `agent_workspace_logs` | Mensajes del AgentBus |
| `session_context` | Estado de sesiones |
| `semantic_cache` | Cache semántico de LLM |
| `procedural_skills` | Skills procedurales |
| `hitl_approval_log` | Log de decisiones HITL |
| `prompt_evolution_log` | Evolución de prompts |

```python
from harness.memory_rag.lance_vector_store import LanceVectorStore
import numpy as np

store = LanceVectorStore(db_path="./db/lancedb")

# Insertar vectores
vectors = np.random.randn(3, 384).astype(np.float32)
ids = store.insert("agent_workspace_logs", vectors, [
    {"text": "mensaje 1", "agent": "@builder"},
    {"text": "mensaje 2", "agent": "@guardian"},
    {"text": "mensaje 3", "agent": "@scientist"},
])

# Búsqueda por similitud
query = np.random.randn(384).astype(np.float32)
results = store.search("agent_workspace_logs", query, top_k=5)
for r in results:
    print(f"Score: {r['score']:.4f} | {r['metadata']['text'][:60]}")

# Búsqueda híbrida (vector + keyword)
results = store.hybrid_search(
    "agent_workspace_logs", query,
    keyword_filter="builder", top_k=3,
)
```

#### 2.2.2 SemanticCache

**Archivo:** `harness/memory_rag/semantic_cache.py` (939 líneas)

Cache semántico de respuestas LLM con dos niveles: hash exacto + similitud vectorial.

```python
from harness.memory_rag.semantic_cache import SemanticCache

cache = SemanticCache(threshold=0.92, default_ttl=3600)

# Antes de llamar al LLM
cached = cache.get(
    prompt="Implementa una función de ordenamiento en Python",
    agent_role="builder",
)
if cached:
    print("Cache hit! Usando respuesta cacheada")
else:
    # Llamar al LLM...
    llm_response = "def bubble_sort(arr): ..."
    cache.set(
        prompt="Implementa una función de ordenamiento en Python",
        response=llm_response,
        agent_role="builder",
    )

# Estadísticas
stats = cache.get_stats()
print(f"Hit rate: {stats['hit_rate']}%")
print(f"Hits: {stats['hits']}, Misses: {stats['misses']}")
```

#### 2.2.3 ShapedCache

**Archivo:** `harness/memory_rag/semantic_cache.py` (clase `ShapedCache`, línea 772)

Cache con **Cache-Shape Discipline** (Mojentum 2026): LRU + TTL + relevancia. Reduce tokens en **38%** manteniendo hit rate >85%.

```python
from harness.memory_rag.semantic_cache import SemanticCache, ShapedCache

sem_cache = SemanticCache()
shaped = ShapedCache(
    semantic_cache=sem_cache,
    max_tokens=10000,
    ttl_sec=3600.0,
    min_relevance=0.1,
)

# Get con shape activo
result = shaped.get_shaped(
    prompt="implementa API en Rust",
    threshold=0.92,
    context_window=8000,  # para compactación
)

# Set con token cost
shaped.set_shaped(
    prompt="implementa API en Rust",
    response="usar Axum con sqlx...",
    metadata={"agent": "builder"},
    token_cost=500,
)

# Estadísticas
stats = shaped.get_stats()
print(f"Hit rate: {stats['hit_rate']:.1%}")
print(f"LRU size: {stats['lru_size']}/{stats['max_tokens']}")
```

**Mecanismo de evicción LRU:**
```
1. Cada entrada tiene un token_cost asociado
2. Cuando la suma de tokens excede max_tokens, se elimina la entrada más antigua
3. Entradas poco usadas (min_relevance) se compactan primero
4. TTL por entrada: expirado → eliminado automáticamente
```

#### 2.2.4 ContextWindowManager

**Archivo:** `harness/memory_rag/context_window_manager.py` (1029 líneas)

Gestión adaptativa de la ventana de contexto con 6 estrategias de optimización.

**Estrategias (aplicadas en orden):**

1. **Priority ordering:** Secciones críticas (system prompt) nunca se truncan
2. **Budget allocation:** Cada sección tiene un máximo de tokens
3. **Sliding window:** Últimos N mensajes completos preservados
4. **Summarization:** Historial antiguo comprimido a resumen
5. **Observation Masking:** Tool outputs grandes → placeholders
6. **Section dropping:** Secciones de baja prioridad eliminadas si es necesario

**Prioridades de sección:**

| Sección | Prioridad | Budget default |
|---------|-----------|----------------|
| `system_identity` | CRITICAL (nunca truncar) | 500 |
| `system_rules` | CRITICAL | 1000 |
| `system_guardrails` | CRITICAL | 500 |
| `current_instruction` | HIGH | 400 |
| `session_context` | HIGH | 800 |
| `skill_context` | NORMAL | 2000 |
| `rag_context` | LOW | 2000 |
| `conversation_history` | LOW | 3000 |
| `tool_outputs` | BACKGROUND | 2000 |

```python
from harness.memory_rag.context_window_manager import ContextWindowManager

cwm = ContextWindowManager(
    total_budget=12000,
    model_family="claude",
    use_observation_masking=True,
)

# Crear ventana
window = cwm.create_window()
window.add_section("system_identity", "Eres un asistente experto...", frozen=True)
window.add_section("rag_context", "Contexto recuperado de la base de datos...")
window.add_section("current_instruction", "Implementa una API REST...")
window.add_section("tool_outputs", "Resultado de ejecución de tests...")

# Optimizar
optimized = cwm.optimize(window)
prompt = optimized.to_prompt(format="labeled")
print(prompt)

# Compactar historial
history = [
    {"role": "user", "content": "Haz X"},
    {"role": "assistant", "content": "Aquí está X..."},
    # ... muchos mensajes
]
compacted = cwm.compact_history(history, max_messages=8)
```

#### 2.2.5 structured_compact

**Archivo:** `harness/memory_rag/context_window_manager.py` (función `structured_compact`, línea 947)

Compresión estructurada de texto que reduce tokens **~41%** preservando secciones críticas.

```python
from harness.memory_rag.context_window_manager import structured_compact

texto_largo = """
# Plan de Implementación

**Objetivo:** Implementar API REST en Rust con Axum

## Módulos
- Core: lógica de negocio
- API: endpoints HTTP
- DB: persistencia

## Output de herramientas
Output: Resultado muy largo de más de 200 caracteres...

## Logs
[DEBUG] 2026-01-01 Conexión exitosa
[DEBUG] 2026-01-01 Query ejecutada
[INFO] 2026-01-01 Procesando...
"""

compactado = structured_compact(texto_largo, budget_ratio=0.6)
print(f"Original: {len(texto_largo)} chars")
print(f"Compactado: {len(compactado)} chars")
print(f"Compresión: {(1 - len(compactado)/len(texto_largo))*100:.0f}%")
```

#### 2.2.6 TokenBudget

**Archivo:** `harness/memory_rag/token_budget.py` (506 líneas)

Presupuesto de tokens por agente con confidence-gated spending y redistribución dinámica.

**6 pools de tokens:**

| Pool | Asignación default | Prioridad |
|------|-------------------|-----------|
| `system` | 15% | CRITICAL |
| `user` | 5% | HIGH |
| `rag` | 30% | NORMAL |
| `skill` | 15% | NORMAL |
| `tool_output` | 20% | LOW |
| `conversation` | 15% | LOW |

```python
from harness.memory_rag.token_budget import (
    TokenBudget, BudgetManager, PRIORITY_CRITICAL
)

# Budget por agente
budget = TokenBudget(
    agent_id="builder",
    total_budget=4000,
    priority=PRIORITY_CRITICAL,
)

# Solicitar tokens
granted = budget.request("rag", tokens=500)
print(f"Concedidos: {granted} tokens")

# Commit tras usar
budget.commit("rag", granted)

# Confidence gate
budget.set_confidence(0.95)
if budget.can_spend:
    print("Puede seguir gastando")
else:
    print("Confianza alta → no más gasto")

# Budget Manager (sesión multi-agente)
manager = BudgetManager(session_budget=16000)
manager.register_agent("builder", budget=5000, priority=PRIORITY_CRITICAL)
manager.register_agent("guardian", budget=3000)
manager.register_agent("scientist", budget=2000)

# Redistribuir presupuesto no usado
redistributed = manager.redistribute_idle()
print(f"Redistribuido: {redistributed}")

# Snapshot de sesión
snap = manager.session_snapshot("session-abc")
```

#### 2.2.7 SkillRouter

**Archivo:** `harness/memory_rag/skill_router.py` (164 líneas)

Routing semántico de skills: dado un mensaje, selecciona solo los **2 skills más relevantes** (de 10 disponibles), reduciendo tokens 60–80%.

```python
from harness.memory_rag.skill_router import SkillRouter

router = SkillRouter()

# Encontrar skills relevantes
skills = router.route("implementa estrategia de trading cuantitativo")
print(f"Skills activados: {skills}")
# → ['evolve', 'quant-trading']

# Construir contexto solo para esos skills
context = router.build_context(skills)
print(context)
# - quant-trading: trading strategy quantitative cqe rust...

# Skills disponibles
all_skills = router.get_available_skills()
```

**Registro de skills (10 skills):**
```
alpha-research, evolve, healthtech, hedgefund, legal-doc,
math-doc, pos-retail, quant-trading, risk-execution, science-doc
```

#### 2.2.8 SkillMinifier / SkillLoader

**Archivos:** `harness/memory_rag/skill_minifier.py` (497 líneas), `harness/memory_rag/skill_loader.py`

Minificación y carga eficiente de skills. Basado en SkillReducer (arXiv:2603.29919, Mar 2026): 48% compresión en descripciones, 39% en cuerpo.

```python
from harness.memory_rag.skill_minifier import SkillMinifier, minify_all_skills

minifier = SkillMinifier()

# Minificar contenido individual
original = """
---
name: quant-trading
description: Esta función es para implementar estrategias de trading cuantitativo...
---

## Propósito
Implementar estrategias cuantitativas con CQE Rust.

## Ejemplo (se eliminará)
```python
# código de ejemplo...
```

## Uso
Ejecutar con: python trade.py
"""

minified = minifier.minify(original)
print(f"Original: {len(original)} chars")
print(f"Minificado: {len(minified)} chars")
print(f"Compresión: {minifier.get_compression_ratio(original):.1%}")

# Batch minificar todos los skills
results = minify_all_skills(
    skills_dir=".opencode/skills",
    dry_run=True,  # False para escribir .min.md
)
```

---

### 2.3 tools_sandbox/

#### 2.3.1 MCPClient

**Archivo:** `harness/tools_sandbox/mcp_client.py` (399 líneas)

Cliente JSON-RPC 2.0 para servidores MCP (Model Context Protocol) sobre HTTP/SSE.

```python
from harness.tools_sandbox.mcp_client import MCPClient

client = MCPClient(default_timeout=30)

if client.connect("http://localhost:3100"):
    # Listar herramientas
    tools = client.list_tools()
    for t in tools:
        print(f"  {t.name}: {t.description[:60]}")

    # Ejecutar herramienta
    result = client.execute_tool(
        "read_file",
        {"path": "/tmp/test.txt"},
        timeout=10,
    )
    if result.success:
        print(f"Output: {result.output[:200]}")
    else:
        print(f"Error: {result.error}")

    client.disconnect()
```

#### 2.3.2 MCPManager

**Archivo:** `harness/tools_sandbox/mcp_manager.py` (345 líneas)

Pool de conexiones MCP con índice unificado de herramientas.

```python
from harness.tools_sandbox.mcp_manager import MCPManager

manager = MCPManager()

# Cargar servidores desde YAML
manager.load_servers("mcp_servers.yaml")

# Registrar servidor manualmente
manager.register_server(
    name="filesystem",
    url="http://localhost:3100",
    tools=["read_file", "write_file", "list_dir"],
    enabled=True,
)

# Conectar todos los servidores habilitados
connected = manager.connect_all()
print(f"{connected} servidores conectados")

# Ejecutar herramienta (resuelve automáticamente el servidor)
result = manager.execute("read_file", {"path": "/tmp/test.txt"})

# Listar todas las herramientas disponibles
all_tools = manager.list_all_tools()
```

#### 2.3.3 MCPExecutor

**Archivo:** `harness/tools_sandbox/mcp_executor.py` (461 líneas)

Ejecutor sandboxeado de herramientas vía subprocess con timeouts y validación de schemas.

**Herramientas built-in:**

| Tool | Comando | Parámetros |
|------|---------|------------|
| `pytest` | `pytest <test_path> [args]` | test_path, args |
| `python` | `python <script> [args]` | script, args |
| `shell` | `cmd /c <command>` (Win) / `sh -c <command>` (Unix) | command |
| `echo` | `echo <json>` | params |

```python
from harness.tools_sandbox.mcp_executor import MCPExecutor

executor = MCPExecutor(
    default_timeout=30,
    allowed_commands=["pytest", "python", "echo"],
)

# Ejecutar tests
result = executor.execute_tool("pytest", {
    "test_path": "tests/test_api.py",
    "args": ["-x", "--tb=short"],
})
print(f"Éxito: {result.success}, Time: {result.execution_time:.2f}s")

# Run test (conveniencia: escribe código a temp file y ejecuta)
result = executor.run_test(
    code="def test_foo(): assert 1 + 1 == 2",
    test_type="pytest",
)
print(f"Tests pasaron: {result.success}")

# Validar output contra schema
is_valid, msg = executor.validate_output(
    {"name": "test", "value": 42},
    schema={
        "type": "dict",
        "required": ["name"],
        "properties": {
            "name": {"type": "string"},
            "value": {"type": "integer"},
        },
    },
)
print(f"Válido: {is_valid} — {msg}")
```

---

## 3. Flujo de Datos

### 3.1 Pipeline Completo

```
  RECEIVE ──► ROUTE ──► PLAN ──► TRACK ──► ADAPT ──► EXECUTE ──► HEAL ──► TELEMETRY ──► CONSOLIDATE
    │           │         │         │         │          │          │          │             │
    │ ①        ②         ③        ④        ⑤         ⑥          ⑦         ⑧            ⑨
    │           │         │         │         │          │          │          │             │
    ▼           ▼         ▼         ▼         ▼          ▼          ▼          ▼             ▼
  ┌──────┐  ┌──────┐  ┌──────┐  ┌──────┐  ┌──────┐  ┌──────┐  ┌──────┐  ┌──────┐  ┌──────────┐
  │ User │  │Diffi │  │Task  │  │Sessn │  │Scope │  │Agent │  │Self  │  │KPI   │  │Consoli-  │
  │ msg  │  │culty │  │Plan- │  │Con-  │  │Ana-  │  │Dis-  │  │Heal  │  │Trac- │  │date +    │
  │      │  │Router│  │ner   │  │text  │  │lyzer │  │patch │  │Ctx   │  │ker   │  │Notify    │
  └──────┘  └──────┘  └──────┘  └──────┘  └──────┘  └──────┘  └──────┘  └──────┘  └──────────┘
```

**Descripción de cada etapa:**

| # | Etapa | Componente | Acción |
|---|-------|-----------|--------|
| ① | RECEIVE | TaskOrchestrator | Recibe mensaje, verifica circuit breaker, cache semántico, idempotencia |
| ② | ROUTE | DifficultyRouter | Clasifica complejidad (5 niveles), determina pipeline (shallow/standard/deep) |
| ③ | PLAN | TaskPlanner | Descompone en DAG usando 11 templates, ScopeAnalyzer escala agentes |
| ④ | TRACK | SessionContext | Persiste estado en LanceDB, trackea progreso |
| ⑤ | ADAPT | ScopeAnalyzer | Ajusta número de agentes según alcance detectado |
| ⑥ | EXECUTE | AgentDispatcher + AgentBus | Asigna subtasks a agentes, inyecta skills, broadcast via bus |
| ⑦ | HEAL | SelfHealingContext | Circuit breaker, timeouts, stall detection, confidence-gated stopping |
| ⑧ | TELEMETRY | AgentKPITracker | Registra KPIs, interacciones, rendimiento por skill |
| ⑨ | CONSOLIDATE | TaskOrchestrator | Merge resultados, broadcast completion, cierra sesión |

### 3.2 Flujo de Mensajes entre Agentes

```
@coordinator                     @builder                    @guardian
     │                              │                           │
     │  [request] PLAN de trabajo   │                           │
     ├─────────────────────────────►│                           │
     │                              │                           │
     │  [request] Core: src/core/   │                           │
     ├─────────────────────────────►│                           │
     │                              │                           │
     │                     [response] Código implementado       │
     │◄─────────────────────────────┤                           │
     │                              │                           │
     │  [notification] Subtask OK   │                           │
     ├─────────────────────────────────────────────────────────►│
     │                              │                           │
     │  [request] Tests en tests/   │                           │
     ├─────────────────────────────────────────────────────────►│
     │                              │                           │
     │                              │              [response]   │
     │◄─────────────────────────────────────────────────────────┤
     │                              │                           │
     │  [notification] PLAN COMPLETO│                           │
     ├─────────────────────────────►├──────────────────────────►│
```

### 3.3 Persistencia en LanceDB

```
LanceDB (db/lancedb/)
│
├── agent_workspace_logs    ← Mensajes del AgentBus
│   ├── id, channel, from_agent, to_agent, message
│   ├── message_type, status, task_id, iteration
│   └── created_at, thread_id, attachments
│
├── session_context          ← Estado de sesiones
│   ├── session_id, plan (JSON), messages
│   ├── created_at, updated_at, completed
│   └── original_message
│
├── semantic_cache           ← Cache semántico LLM
│   ├── prompt_hash, prompt_text, response
│   ├── agent_role, hit_count, ttl_seconds
│   └── created_at, last_accessed
│
├── hitl_approval_log        ← Decisiones HITL
│   ├── action, agent_role, approved
│   ├── user_feedback, mode
│   └── created_at
│
├── procedural_skills        ← Skills procedurales
│   ├── name, domain, agent, trigger
│   ├── vector (embedding)
│   └── content (ruta .md)
│
├── prompt_evolution_log     ← Evolución de prompts
├── scheduler_log            ← Log del scheduler
├── asi_cognition_store      ← Lecciones aprendidas
└── kpi_store                ← KPIs de agentes
```

### 3.4 Sincronización Federada

```
Proyecto A                    Proyecto B                    Proyecto C
(LanceDB_A)                  (LanceDB_B)                   (LanceDB_C)
     │                            │                            │
     │  knowledge_agentic.json    │  knowledge_otro.json       │
     │  ┌─────────────────┐       │  ┌─────────────────┐       │
     │  │ patterns: [...]  │       │  │ patterns: [...]  │       │
     │  │ prompts: [...]   │       │  │ prompts: [...]   │       │
     │  │ metrics: [...]   │       │  │ metrics: [...]   │       │
     │  └────────┬────────┘       │  └────────┬────────┘       │
     │           │                │           │                │
     └───────────┼────────────────┘───────────┼────────────────┘
                 │                            │
         ┌───────▼────────────────────────────▼────────┐
         │           Directorio Federado               │
         │     .opencode/federado/knowledge_*.json     │
         │                                              │
         │  sync(): merge por ID + version              │
         └──────────────────────────────────────────────┘
```

---

## 4. API Reference

### 4.1 TaskOrchestrator

#### `TaskOrchestrator.process_message()`

```python
def process_message(
    message: str,
    force_agent: Optional[str] = None,
) -> OrchestratorResult:
```

**Args:**
- `message` (str): Mensaje del usuario.
- `force_agent` (Optional[str]): Agente forzado (si el usuario usó `@agent`).

**Returns:**
- `OrchestratorResult` con:
  - `session_id`: ID de la sesión
  - `plan`: TaskPlan con DAG completo
  - `current_level`: Lista de subtasks listas para ejecutar
  - `session_status`: Estado legible
  - `previous_results`: Resultados de subtasks completadas
  - `is_complete`: Si el plan está completo
  - `is_debate`: Si el template es debate
  - `debate_agents`: Agentes para el debate

#### `TaskOrchestrator.run_debate()`

```python
def run_debate(
    session_id: str,
    task: str,
    agents: Optional[List[str]] = None,
    strategy: str = "consensus",
    dispatch_fn: Optional[callable] = None,
) -> DebateResult:
```

**Args:**
- `session_id` (str): ID de la sesión.
- `task` (str): Tarea a debatir.
- `agents` (Optional[List[str]]): Agentes participantes.
- `strategy` (str): Estrategia (`consensus`, `critique`, `deliberation`).
- `dispatch_fn` (Optional[callable]): Función para obtener respuestas de agente.

**Returns:**
- `DebateResult` con `final_answer`, `confidence`, `agent_agreement`, `rounds`.

### 4.2 AgentBus

#### `AgentBus.post_message()`

```python
def post_message(
    channel: str,
    from_agent: str,
    to_agent: str,
    message: str,
    message_type: str = "notification",
    task_id: Optional[str] = None,
    iteration: int = 0,
    attachments: Optional[List[str]] = None,
    thread_id: Optional[str] = None,
) -> str:
```

**Returns:** ID del mensaje creado.

#### `AgentBus.consume()` (AsyncAgentBus)

```python
async def consume(channel: str, timeout: float = 30.0) -> Any:
```

**Raises:** `asyncio.TimeoutError` si no hay mensaje dentro del timeout.

### 4.3 SemanticCache

#### `SemanticCache.get()`

```python
def get(
    prompt: str,
    agent_role: str = "*",
    threshold: Optional[float] = None,
) -> Optional[str]:
```

**Returns:** Respuesta cacheada o `None`.

#### `SemanticCache.set()`

```python
def set(
    prompt: str,
    response: str,
    agent_role: str = "*",
    ttl_seconds: Optional[int] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> bool:
```

### 4.4 ShapedCache

#### `ShapedCache.get_shaped()`

```python
def get_shaped(
    prompt: str,
    threshold: float = 0.92,
    context_window: Optional[int] = None,
) -> Optional[Dict[str, Any]]:
```

#### `ShapedCache.set_shaped()`

```python
def set_shaped(
    prompt: str,
    response: str,
    metadata: Optional[Dict[str, Any]] = None,
    token_cost: int = 0,
) -> str:
```

**Returns:** Hash del prompt almacenado.

### 4.5 WriteAheadLog

#### `WriteAheadLog.begin()`

```python
def begin(
    operation_type: str,
    payload: Dict[str, Any],
    max_retries: int = 3,
) -> WALEntry:
```

#### `WriteAheadLog.execute()`

```python
def execute(
    entry: WALEntry,
    fn: Callable[..., T],
    *args: Any,
    **kwargs: Any,
) -> T:
```

**Raises:** `RuntimeError` si se agotan los reintentos.

#### `WriteAheadLog.cancel()`

```python
def cancel(operation_id: str) -> bool:
```

### 4.6 structured_compact

```python
def structured_compact(
    text: str,
    budget_ratio: float = 0.6,
    min_chars: int = 50,
) -> str:
```

---

## 5. Token Economics

### 5.1 Resumen de Ahorros

| Técnica | Ahorro | Referencia |
|---------|--------|------------|
| ShapedCache (LRU+TTL) | -38% tokens | Cache-Shape Discipline, Mojentum 2026 |
| structured_compact | -41% tokens | Struct47, LAS51 |
| Observation Masking | -30-50% en tool outputs | JetBrains 2026 (500 SWE-bench instances) |
| SkillRouter (top-2 skills) | -60-80% vs cargar todos | — |
| SkillMinifier (.min.md) | -40-50% por skill | SkillReducer, arXiv:2603.29919 |
| TokenBudget (confidence-gated) | -30-50% en sesiones multi-agente | — |
| ContextWindowManager | -40-60% en historial | — |

### 5.2 ShapedCache (Cache-Shape Discipline)

El `ShapedCache` implementa tres políticas simultáneas:

```
┌────────────────────────────────────────────────┐
│              ShapedCache                       │
│                                                │
│  LRU Policy:  max_tokens=10000                │
│  ┌────┬────┬────┬────┬────┬────┬────┬────┐    │
│  │ A  │ B  │ C  │ D  │ E  │ F  │ G  │ H  │    │
│  │500t│300t│200t│400t│600t│100t│300t│200t│    │
│  └────┴────┴────┴────┴────┴────┴────┴────┘    │
│        ▲                                ▲      │
│        │                                │      │
│   Oldest (evict first)            Newest       │
│                                                │
│  TTL Policy: ttl=3600s                        │
│  Relevancy: min_relevance=0.1                 │
└────────────────────────────────────────────────┘
```

**Mecanismo:**
1. Cada entrada tiene `token_cost` (estimado por `estimate_tokens()`)
2. `get_shaped()` refresca LRU en cada hit
3. Cuando `sum(token_cost) > max_tokens` → evict LRU
4. TTL elimina entradas expiradas en `get_shaped()` y `clear_expired()`

### 5.3 structured_compact

Estrategia de compresión en 4 pasos:

1. **Preservar cabeceras** (`# `, `## `, `### `, `**`, `---`)
2. **Comprimir tool outputs** >200 chars a `[... N lines ...]`
3. **Compactar bloques de código** >20 líneas a resumen
4. **Eliminar logging repetitivo**

```python
# Ejemplo de compactación
texto = "# Report\n## Tool Output\n" + "A" * 1000 + "\n## Conclusión\nOK"
compactado = structured_compact(texto, budget_ratio=0.5)
# Resultado: preserva "# Report", comprime tool output, mantiene "## Conclusión"
```

### 5.4 WriteAheadLog (Failure-Spend Governance)

El WAL implementa **Failure-Spend Governance**: cuando una operación falla, se registra el costo y se penaliza el presupuesto del agente en un 50% de los tokens usados.

```
Operación normal:
  begin() → execute() → commit (sin costo extra)

Operación con fallos:
  begin() → execute() → FAIL → retry (backoff: 0.1s, 0.2s, 0.4s)
         → FAIL → retry → FAIL → RuntimeError
         → TokenBudget.record_failure() penaliza 50% de tokens

Cancelación:
  begin() → cancel() → CANCELLED (libera recursos)

Recuperación:
  crash → recover_pending() → retry automático
```

### 5.5 Observation Masking

Reemplaza outputs extensos de herramientas con placeholders inteligentes:

```
Original:
  Tool: pytest
  Status: completed
  Duration: 12.3s
  Output:
    test_foo PASSED
    test_bar PASSED
    ... (2000 líneas más)

Masked:
  Tool: pytest
  Status: completed
  Duration: 12.3s
  Output:
    test_foo PASSED
    test_bar PASSED
    [tool_output:pytest:0]
```

---

## 6. Concurrencia

### 6.1 AsyncAgentBus con asyncio.Queue

El `AsyncAgentBus` usa `asyncio.Queue` por canal para mensajería no bloqueante:

```python
from harness.orchestrator.agent_bus import AsyncAgentBus
import asyncio

async def worker(bus, name):
    while True:
        msg = await bus.consume("canal-trabajo", timeout=5.0)
        print(f"{name} procesa: {msg}")

async def main():
    bus = AsyncAgentBus()
    
    # Lanzar workers concurrentes
    workers = [worker(bus, f"worker-{i}") for i in range(3)]
    
    # Publicar mensajes
    for i in range(10):
        await bus.post_message("canal-trabajo", f"tarea-{i}")
    
    await asyncio.gather(*workers)

asyncio.run(main())
```

### 6.2 Debate Paralelo con asyncio.gather

El método `_execute_consensus_async` ejecuta dispatch de todos los agentes simultáneamente, reduciendo latencia de **O(n) a O(1)**:

```
Versión síncrona:
  builder ──► esperar ──► scientist ──► esperar ──► guardian
  │<────────── T × 3 ──────────►│

Versión asíncrona (PaCoRe):
  builder ──►
  scientist ──► (en paralelo)
  guardian ──►
  │<────── T (el más lento) ────►│
```

### 6.3 WriteAheadLog con Retry + Backoff

```python
# Backoff exponencial integrado:
# Intento 1: 0ms de espera
# Intento 2: 100ms de espera  (2^0 * 0.1)
# Intento 3: 200ms de espera  (2^1 * 0.1)
# Intento 4: 400ms de espera  (2^2 * 0.1)

entry = wal.begin("llm_call", {...}, max_retries=3)
try:
    result = wal.execute(entry, llm_call_function, prompt)
except RuntimeError:
    # 4 intentos fallidos con backoff
    pass
```

### 6.4 AgentDispatcher Async

```python
# Dispatch paralelo de skill search + RAG + messages
skill_task = asyncio.to_thread(self.find_skill_for_task, task_desc)
context_task = asyncio.to_thread(assembler.assemble, task_desc, agent_role)
messages_task = asyncio.to_thread(bus.get_channel_history, channel, 10)

skill_result, context_result, messages = await asyncio.gather(
    skill_task, context_task, messages_task
)
```

---

## 7. Testing

### 7.1 Resumen

| Métrica | Valor |
|---------|-------|
| Tests totales | ~1,518 (estimado basado en 47 archivos × ~32 tests/archivo) |
| Suites de test | 52 (47 archivos + conftest + mocks + benchmarks) |
| Cobertura (fail_under) | **59%** (Jul 2026: 59.69%) |
| Framework | pytest 8+ |
| Plugins | pytest-cov, pytest-mock, pytest-xdist, pytest-asyncio, pytest-split |
| Paralelización | `pytest -n auto` (xdist) |
| Mock principal | `MockVectorStore` (sin LanceDB) |

### 7.2 Archivos de Test

```
harness/tests/
├── conftest.py                          # Fixtures globales
├── mock_vector_store.py                 # Mock de LanceDB (456 líneas)
├── test_agent_bus.py                    # AgentBus (21 tests)
├── test_async_agent_bus.py              # AsyncAgentBus
├── test_agent_dispatcher.py             # AgentDispatcher (~30 tests)
├── test_agent_kpi_tracker.py            # KPI Tracker
├── test_agent_selector.py               # Agent Selector
├── test_architectural_guardrails.py     # Architectural Guardrails
├── test_behavioral_tracer.py            # Behavioral Tracer
├── test_cache.py                        # SemanticCache + ShapedCache
├── test_common.py                       # Common utilities
├── test_compressor.py                   # Prompt compressor
├── test_confidence.py                   # ConfidenceScorer
├── test_context_injector.py             # ContextInjector
├── test_context_window.py               # ContextWindow
├── test_context_window_manager.py       # ContextWindowManager
├── test_debate.py                       # DebateOrchestrator
├── test_difficulty_router.py            # DifficultyRouter
├── test_discovery.py                    # Agent Discovery
├── test_embeddings.py                   # Embeddings
├── test_federated_memory.py             # FederatedMemory
├── test_hermes.py                       # Hermes Bridge
├── test_hitl_guard.py                   # HITLGuard
├── test_integration.py                  # Tests de integración
├── test_lance_vector_store.py           # LanceVectorStore
├── test_lazy_loading.py                 # Lazy loading
├── test_mcp_client.py                   # MCPClient
├── test_mcp_manager.py                  # MCPManager
├── test_memory.py                       # Memory RAG
├── test_mock_vector_store.py            # MockVectorStore tests
├── test_orchestrator.py                 # TaskOrchestrator
├── test_pbt_templates.py                # PBT templates
├── test_reset_state.py                  # Reset state
├── test_routing.py                      # Routing
├── test_run.py                          # Run harness
├── test_run_commands.py                 # Run commands
├── test_sandbox_loop.py                 # SandboxLoop
├── test_scheduler.py                    # Scheduler
├── test_scope_analyzer.py               # ScopeAnalyzer
├── test_semantic_cache_extended.py      # SemanticCache extended
├── test_session_context.py              # SessionContext
├── test_skill_router.py                 # SkillRouter
├── test_structured_log.py               # StructuredLog
├── test_task_manager.py                 # TaskManager
├── test_task_orchestrator.py            # TaskOrchestrator specific
├── test_task_planner.py                 # TaskPlanner
├── test_telemetry.py                    # Telemetry
├── test_workflow_patterns.py            # Workflow patterns
└── test_write_ahead_log.py             # WriteAheadLog
```

### 7.3 MockVectorStore

El `MockVectorStore` reemplaza LanceDB real con almacenamiento en memoria, permitiendo:

- Session-scoped fixtures sin depender de LanceDB instalado
- Tests paralelos con pytest-xdist (sin lock de base de datos)
- Ejecución sin dependencia de `lancedb`

```python
from harness.tests.mock_vector_store import MockVectorStore

# Uso en tests
store = MockVectorStore()

# Compatible con LanceVectorStore
store.create_collection("test")
ids = store.insert("test", np.random.randn(2, 384), [
    {"text": "hola"}, {"text": "mundo"},
])
results = store.search("test", np.random.randn(384))
```

### 7.4 Ejecución

```bash
# Todos los tests
cd agentic-harness
pytest

# Con cobertura
pytest --cov=harness --cov-report=term-missing

# Paralelo (requiere pytest-xdist)
pytest -n auto

# Tests específicos
pytest harness/tests/test_agent_bus.py -v
pytest harness/tests/test_debate.py -v -k "test_consensus"

# Tests lentos / integración
pytest -m "slow"
pytest -m "integration"

# Tests unitarios puros
pytest -m "unit"
```

### 7.5 Configuración (pyproject.toml)

```toml
[tool.pytest.ini_options]
minversion = "8.0"
testpaths = ["harness/tests"]
python_files = ["test_*.py"]
markers = [
    "slow: tests lentos (>1s) que requieren integracion real",
    "integration: tests que dependen de LanceDB real u otros servicios externos",
    "unit: tests unitarios puros sin dependencias externas (default)",
]

[tool.coverage.report]
fail_under = 59     # Jul 2026: 59.69%
```

---

*Documentación generada a partir del código fuente de AGENTIC Harness. Julio 2026.*
