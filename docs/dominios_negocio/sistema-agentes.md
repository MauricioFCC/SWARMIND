# Sistema Multi-Agente

!!! abstract "Resumen"

    Onyx implementa un sistema de **21 agentes especializados** que colaboran bajo la
    orquestación de un grafo de estado con enrutamiento por intención. Cada agente tiene
    un perfil definido, capacidades específicas y reglas de transición hacia otros agentes.

---

## Catálogo de Agentes

### Agentes de Evolución (3)

| Agente | Rol | Capacidades | Cuándo Usarlo |
|--------|-----|-------------|---------------|
| `@evolve-researcher` | Investigador de mejora continua | Propone mejoras basadas en cognition store, analiza patrones de fallo | Para identificar oportunidades de optimización en skills existentes |
| `@evolve-engineer` | Ingeniero de auto-mejora | Ejecuta cambios mediante diff-based evolution, muta prompts genéticamente | Para aplicar mejoras aprobadas y generar nuevas versiones de skills |
| `@evolve-analyzer` | Analista de resultados | Evalúa experiments, promueve best snapshots, destila lecciones | Para analizar resultados del evolve loop y actualizar cognition store |

### Agentes de Desarrollo (5)

| Agente | Rol | Capacidades | Cuándo Usarlo |
|--------|-----|-------------|---------------|
| `@software-engineer` | Ingeniero de software full-stack | APIs, microservicios, CI/CD, arquitectura hexagonal | Para implementar endpoints, servicios backend, o refactorizar código |
| `@frontend-engineer` | Ingeniero frontend | Dashboards, UI, componentes React/Svelte/Vue, visualizaciones | Para crear interfaces de usuario o paneles de monitoreo |
| `@mobile-engineer` | Ingeniero móvil | Apps iOS/Android, React Native/Flutter, offline-first, push notifications | Para desarrollar o mantener aplicaciones móviles |
| `@data-architect` | Arquitecto de datos | Schemas, migraciones, ETL, pipelines, modelos de datos | Para diseñar bases de datos, migraciones o pipelines de datos |
| `@devops-sre` | DevOps / SRE | Docker, Kubernetes, CI/CD, monitoreo, IaC | Para configurar infraestructura, pipelines de deploy o monitoreo |

### Agentes de Seguridad y Calidad (3)

| Agente | Rol | Capacidades | Cuándo Usarlo |
|--------|-----|-------------|---------------|
| `@security-engineer` | Ingeniero de seguridad | AppSec, hardening, compliance, threat modeling, secret scanning | Para auditorías de seguridad, revisión de vulnerabilidades o cumplimiento normativo |
| `@quality-gate` | Guardián de calidad | Test strategy, cobertura, pre-commit gates, regresión | Para validar código antes de commit, diseñar estrategias de testing |
| `@requirements-analyst` | Analista de requerimientos | Análisis de viabilidad, propuestas de mejora, user stories | Para analizar nuevas features, investigar viabilidad técnica |

### Agentes Cuantitativos (3)

| Agente | Rol | Capacidades | Cuándo Usarlo |
|--------|-----|-------------|---------------|
| `@quant-developer` | Desarrollador cuantitativo | Estrategias de trading, ejecución de órdenes, broker adapters, ONNX | Para implementar estrategias de trading o conectarse con brokers |
| `@quant-scientist` | Científico cuantitativo | Validación estadística, experimentos, feature engineering, OOS testing | Para investigación, backtesting, análisis de overfitting |
| `@risk-manager` | Gestor de riesgo | Position sizing, Kelly criterion, drawdown tracking, Monte Carlo | Para evaluar riesgo de cartera, calcular tamaño de posiciones |

### Agentes Estratégicos (3)

| Agente | Rol | Capacidades | Cuándo Usarlo |
|--------|-----|-------------|---------------|
| `@project-manager` | Gerente de proyecto | Orquestación, planificación, delegación, reporte de progreso | Para planificar proyectos, delegar tareas, coordinar equipos multi-agente |
| `@enterprise-architect` | Arquitecto empresarial | System design, ADR, C4 modeling, roadmaps tecnológicos | Para decisiones arquitectónicas, diseño de sistemas, selección tecnológica |
| `@documentation-specialist` | Especialista en documentación | Manuales técnicos, API docs, white papers, glosarios | Para crear o actualizar documentación técnica |

### Agentes de IA y Contexto (3)

| Agente | Rol | Capacidades | Cuándo Usarlo |
|--------|-----|-------------|---------------|
| `@ai-engineer` | Ingeniero de IA/ML | Modelos ML, pipelines, LLMOps, fine-tuning, RAG, ONNX | Para implementar modelos ML, optimizar inferencia, diseñar RAG |
| `@context-engineer` | Ingeniero de contexto | Curación de prompts, compactación, JIT retrieval, token budgets | Para optimizar contexto, reducir tokens, diseñar memoria de agentes |
| `@tool-mcp-engineer` | Ingeniero de herramientas MCP | Diseño de tools, MCP servers, tool call optimization | Para crear o mantener el ecosistema de herramientas que los agentes consumen |

### Agente de Operaciones (1)

| Agente | Rol | Capacidades | Cuándo Usarlo |
|--------|-----|-------------|---------------|
| `@trading-operations` | Operaciones de trading | Monitoreo en vivo, alertas, conectividad con brokers, schedules | Para monitorear bots en producción, configurar alertas, gestionar horarios de mercado |

---

## Patrones de Delegación

El `Router v2` implementa tres patrones de ejecución multi-agente definidos en
`MultiAgentPattern`:

### 1. Secuencial (Chain)

Los agentes se ejecutan en cadena: el output de uno es el input del siguiente.

```
@software-engineer → @security-engineer → @devops-sre
     (codifica)         (audita)           (despliega)
```

**Predefinido:** `strategy_to_deploy`, `research_to_implement`, `secure_deploy`

### 2. Paralelo (Fan-out)

Varios agentes ejecutan simultáneamente. Los outputs se mergean según estrategia:

| Estrategia | Comportamiento |
|------------|----------------|
| `concat` | Combina todos los outputs |
| `vote` | Mayoría simple (aprueba/rechaza) |
| `priority` | Toma el output del agente con mayor prioridad |

**Predefinido:** `compliance_review` (security-engineer + risk-manager en paralelo)

### 3. Loop (Iteración Controlada)

Un agente se repite hasta que se cumple una condición de convergencia o se alcanza
el máximo de iteraciones (circuit breaker).

```
evolve → evalúa → ¿mejoró? → sí → otra iteración
                            → no  → convergió
```

**Predefinido:** `evolve_iteration` (max 10 iteraciones, condición de score_improvement < 0.01)

!!! warning "Circuit Breaker"

    Todos los loops tienen un `max_iterations` (por defecto 5) para evitar bucles
    infinitos que consuman el presupuesto de tokens. Si el loop no converge, se
    escala al `@project-manager` con un reporte del estado actual.

---

## Flujo de Quality Gate

El `@quality-gate` implementa un pipeline de validación de dos niveles:

### Inner Loop (<30s, pre-commit)

Validación rápida en entorno de desarrollo:

```
IL-1: Lint (ruff / eslint)
IL-2: Type narrow (mypy / TypeScript)
IL-3: Tests unitarios (pytest / vitest)
IL-4: Diff review (cambio mínimo)
IL-5: Secrets scan (detectar credenciales)
```

### Outer Loop (CI/CD, pre-merge)

Validación completa antes de fusionar:

```
OL-1: Full test suite
OL-2: Full lint
OL-3: Type check completo
OL-4: Security scan (SAST)
OL-5: Performance benchmark
OL-6: Integration tests
OL-7: Documentation check (docs 1:1)
```

### Evaluación de Respuestas

El Quality Gate soporta dos modos de evaluación:

- **Pointwise**: Scoring absoluto contra rúbrica fija (1-5) en groundedness, clarity, completeness, safety
- **Pairwise**: Comparación candidate vs baseline con Model-as-a-Judge (correctness, efficiency, readability, security)

---

## ASI-Evolve: Auto-Mejora Continua

El sistema de evolución autónoma sigue el pipeline de 3 agentes:

```
┌──────────────┐    ┌──────────────┐    ┌──────────────┐
│  Researcher  │───▶│   Engineer   │───▶│   Analyzer   │
│  (Propone)   │    │  (Ejecuta)   │    │  (Destila)   │
└──────────────┘    └──────────────┘    └──────────────┘
       │                    │                    │
       ▼                    ▼                    ▼
┌──────────────┐    ┌──────────────┐    ┌──────────────┐
│ Cognition    │    │ Experiment   │    │ Best         │
│ Store        │    │ DB           │    │ Snapshot     │
│ (lecciones)  │    │ (registros)  │    │ (promoción)  │
└──────────────┘    └──────────────┘    └──────────────┘
```

### Características

- **Diff-Based Evolution**: Evolución mediante parches SEARCH/REPLACE (no reescritura completa)
- **Island Sampling**: Muestreo multi-isla con parámetros de migración y ratio exploración/explotación
- **FAISS Index**: Índice vectorial (Inner Product, 384 dim, all-MiniLM-L6-v2) para búsqueda en cognition store
- **Judge Model**: LLM externo para scoring final de candidatos

### Comandos CLI

| Comando | Función |
|---------|---------|
| `!evolve status` | Estado del loop de evolución |
| `!evolve run <skill> <rounds>` | Ejecuta N rondas de mejora sobre un skill |
| `!evolve cognition add <title> <content>` | Añade conocimiento al cognition store |
| `!evolve cognition search <query>` | Busca en el cognition store |
| `!evolve best <skill>` | Muestra el mejor snapshot de un skill |
| `!evolve stats` | Estadísticas del sistema de evolución |

!!! tip "Cognition Store"

    El cognition store en LanceDB es el corazón del aprendizaje del sistema.
    Cada lección, error y métrica se vectoriza y almacena para que los agentes
    puedan consultarlo en futuras iteraciones. Es la memoria a largo plazo del sistema.

---

## Mapa de Transiciones (Routing Graph)

El grafo de enrutamiento define las transiciones condicionales entre agentes:

```
project-manager ──→ quant-developer ──→ quant-scientist ──→ risk-manager
      │                    │                   │                  │
      │                    ▼                   ▼                  ▼
      └──────────→ software-engineer ←── security-engineer ──→ enterprise-architect
      │                    │                                      │
      │                    ▼                                      ▼
      └──────────→ ai-engineer ──────────→ evolve ───────────→ context-engineer
                                                                     │
                                                                     ▼
                                                              tool-mcp-engineer
```

Cada nodo tiene:
- `transitions`: mapa de condición → siguiente agente
- `fallback`: agente por defecto si no hay transición (generalmente `project-manager`)
- `max_retries`: reintentos antes de escalar
- `timeout_seconds`: timeout de ejecución
