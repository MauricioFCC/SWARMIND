# Coordinator — Swiss Watch Orchestrator

El **coordinator** es el punto de entrada único del sistema (`default: true`, `priority: 1`). Implementa el patrón **Swiss Watch**: recibe el mensaje del usuario, lo clasifica por dificultad, planifica un DAG de subtareas, orquesta agentes en paralelo, y consolida resultados. Actúa como orquestador universal que delega a builder, scientist, guardian y evolve según la naturaleza de la tarea.

## Frontmatter (refleja `.opencode/agents/coordinator.md`)

| Campo | Valor |
|-------|-------|
| `name` | `coordinator` |
| `domain` | `universal` |
| `default` | `true` |
| `priority` | `1` |
| `triggers` | implement, create, build, code, api, test, fix, refactor, research, help, task, project, plan, organize, coordinate, delegate, manage, what, how, when, why, haz, crea, necesito, quiero |
| `capabilities` | auto_routing, task_delegation, context_management, planning, orchestration, swarm_coordination, multi_agent_parallel, quality_automatica, comp_root, resilience, dod, token_governance, structured_output, circuit_breaker, dynamic_scaling, pacore, lts_memory |
| `aliases` | pm, coordinador, orchestrator, lead, default, principal, orquestador |

## Flujo de trabajo (RECEIVE → ROUTE → PLAN → TRACK → ADAPT → EXECUTE → CONSOLIDATE)

1. **RECEIVE**: El usuario envía un mensaje, con o sin `@mención` explícita. Si no hay mención, el coordinator toma control por defecto.
2. **ROUTE**: `DifficultyRouter` clasifica la tarea en 5 niveles (trivial → very_complex) según alcance, dominios involucrados y profundidad técnica requerida.
3. **PLAN**: `TaskPlanner` descompone la tarea en un DAG de subtareas usando 11 templates de planificación predefinidos. Cada nodo del DAG asigna un agente especializado (builder, scientist, guardian, evolve).
4. **TRACK**: `SessionContext` preserva el estado entre iteraciones, incluyendo contexto parcial, decisiones tomadas y resultados intermedios. Esto permite reanudar sesiones sin pérdida de información.
5. **ADAPT**: `AdaptivePlanner` ajusta la estrategia en tiempo real según el historial de ejecución. Si una subtarea falla, se re-planifica con estrategia alternativa.
6. **EXECUTE**: Los niveles independientes del DAG se ejecutan en paralelo (Fan-out/Fan-in). El `ScaleDecider` selecciona el tamaño del swarm según complejidad: 3 agentes (small) hasta 11 (xlarge).
7. **CONSOLIDATE**: Resultados parciales se fusionan vía `Structured Compaction` (compactación por relevancia, no truncación lineal). La respuesta unificada se valida cruzadamente antes de entregar al usuario.

## Dispatchers internos

| Componente | Propósito |
|-----------|-----------|
| `AgentDispatcher` | Enruta tareas a los agentes/skills correspondientes usando LanceDB + catálogo YAML de capacidades |
| `DebateRunner` | Ejecuta debates multi-agente donde múltiples agentes argumentan y refinan soluciones colaborativamente |
| `WriteAheadLog` | Registro previo a cada paso (WAL) para tolerancia a fallos catastróficos y control de gasto (spend bounding) |
| `Worktable` | Mesa de trabajo para debate entre 13 expertos sintéticos en calidad de software |

## Activación

Se activa por defecto en toda conversación. Los triggers incluyen verbos de acción (implement, create, build, code), verbos de coordinación (plan, organize, coordinate, delegate, manage) y preguntas abiertas (what, how, when, why). También reconoce comandos en español: haz, crea, necesito, quiero.

## Delegación automática por detección de dominio

| Agente | Disparadores automáticos |
|--------|------------------------|
| `@builder` | implement, code, api, endpoint, rust, go, python, web, mobile, frontend, ui, component, db, trading, design-system, accesibilidad, responsive, a11y |
| `@scientist` | research, paper, architecture, design, pattern, algorithm, ml, ai, hci, ux, ui-research, generative-ui |
| `@guardian` | test, security, audit, risk, doc, quality, review, validate, frontend-quality, visual-regression, a11y-audit |
| `@evolve` | evolve, improve, optimize, skill, cognition, learn |

## Reglas de delegación UI/UX

Cuando la tarea involucre interfaz de usuario, el coordinator debe: (1) verificar que builder cargue `!skill load frontend-uiux` antes de implementar, (2) incluir guardian en el loop para Frontend Quality Gate post-implementación, (3) referenciar el design system tokenizado (Geeklego 3-tier), (4) preferir Generative UI (A2UI/OpenUI) sobre markdown estático, y (5) exigir cumplimiento WCAG 2.2 AA como mínimo.

## Escalado dinámico (Dynamic Scaling)

| Complejidad | Agentes | Escenario típico |
|-------------|---------|------------------|
| Small | 3 | Tarea simple, 1-2 dominios |
| Medium | 5 | Multi-dominio, coordinación moderada |
| Large | 8 | Sistema completo, varias capas |
| XLarge | 11 | Cross-domain, investigación profunda |

El **ScaleDecider** evalúa automáticamente al inicio. Si la tarea cambia durante ejecución, re-escala dinámicamente. Mínimo 3 agentes (builder + scientist + guardian). Los agentes sobrantes se suspenden durablemente (no se destruyen).

## Gestión de fallos y resiliencia

| Tipo de fallo | Acción |
|---------------|--------|
| Rate Limit (API quota) | Backoff exponencial + cola |
| Stall (sin progreso N pasos) | Timeout + cancellation |
| Timeout (excede ventana) | Retry con ventana ampliada |
| Malformed Stream (respuesta corrupta) | Re-solicitar con validación |
| Provider Outage (servicio caído) | Failover a provider alterno |
| Permanent (error irrecuperable) | Reportar + fallback graceful |

El **Circuit Breaker** abre tras 3 fallos idénticos consecutivos, redirige con causa-aware steering, y prueba en half-open tras cooldown. Cada agente tiene su propio supervisor (árbol Erlang/OTP).

## Economía de tokens y mecanismos de control

| Mecanismo | Impacto |
|-----------|---------|
| Cache-Shape Discipline | -38% tokens (cache de contexto estructurado) |
| Structured Compaction | -41% costo (compactación por relevancia) |
| Scoped Context Spawn | -44% tiempo (sub-agentes con contexto mínimo) |
| Cancellation/Retry First-Class | Resiliencia 3x |
| Write-Ahead Log (WAL) | Zero data loss, spend capped |

**Token Budget Governance**: máximo 50 iteraciones totales, 4 tool calls en paralelo. WAL obligatorio antes de cada tool-call. Si se excede el budget, el harness cancela graceful y retorna resultado parcial.
