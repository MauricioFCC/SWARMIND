# Arquitectura del Sistema

!!! abstract "Resumen"

    Onyx utiliza una arquitectura de **microservicios de agentes** orquestados mediante
    un grafo de estado con enrutamiento por intención. El sistema se divide en tres
    capas: Cerebro (`.opencode/`), Motor (`harness/`) y Conocimiento (`docs/`).

---

## Diagrama de Contexto (C4 - Nivel 1)

```
┌─────────────────────────────────────────────────────────────────┐
│                    SISTEMA ONYX                                  │
│                                                                  │
│  ┌──────────┐   @rol / mensaje   ┌───────────────────────────┐  │
│  │ Usuario  │ ──────────────────▶│   Project Manager         │  │
│  │ (Humano) │ ◀──────────────────│   (Orquestador Central)   │  │
│  └──────────┘   respuesta        └───────────┬───────────────┘  │
│                                              │                   │
│                    ┌─────────────────────────┼──────────────┐    │
│                    │      Specialized Agents  │              │    │
│                    │                         │              │    │
│  ┌─────────────────▼──┐  ┌───────────────────▼──────────┐   │    │
│  │ Software Engineer  │  │ Quant Developer              │   │    │
│  │ (APIs, servicios)  │  │ (Estrategias, ejecución)     │   │    │
│  └─────────────────┬──┘  └───────────────────┬──────────┘   │    │
│                    │                         │              │    │
│  ┌─────────────────▼──┐  ┌───────────────────▼──────────┐   │    │
│  │ Security Engineer  │  │ AI/ML Engineer               │   │    │
│  │ (Hardening, audit) │  │ (Modelos, pipelines)         │   │    │
│  └─────────────────┬──┘  └───────────────────┬──────────┘   │    │
│                    │                         │              │    │
│  ┌─────────────────▼──┐  ┌───────────────────▼──────────┐   │    │
│  │ Data Architect     │  │ Context Engineer             │   │    │
│  │ (Schemas, ETL)     │  │ (Prompt, memoria, JIT)       │   │    │
│  └─────────────────┬──┘  └───────────────────┬──────────┘   │    │
│                    │      ... (15+ agentes)  │              │    │
│                    └─────────────────────────┼──────────────┘    │
│                                              │                   │
│                                              ▼                   │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │                    HARNESS (Motor)                        │   │
│  │  ┌──────────────┐  ┌──────────────┐  ┌────────────────┐ │   │
│  │  │   LanceDB    │  │ Orchestrator │  │ Evolve Loop    │ │   │
│  │  │  VectorStore │  │ (Router v2)  │  │ (ASI-Evolve)   │ │   │
│  │  └──────────────┘  └──────────────┘  └────────────────┘ │   │
│  │  ┌──────────────┐  ┌──────────────┐                     │   │
│  │  │ Memory RAG   │  │ Tools        │                     │   │
│  │  │ (Context)    │  │ Sandbox (MCP)│                     │   │
│  │  └──────────────┘  └──────────────┘                     │   │
│  └──────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

---

## Componentes Core

### 1. `.opencode/` — El Cerebro

Directorio que contiene la inteligencia del sistema: reglas, perfiles de agentes, principios y configuración.

| Subdirectorio | Contenido |
|---------------|-----------|
| `agents/` | 21 perfiles de agentes ejecutables (formato Markdown con frontmatter) |
| `config/` | Configuración central: `project_config.yaml`, `routing_rules.yaml`, `token_budgets.yaml` |
| `core/` | Módulos base del framework: principios, router, registry, guardrails, prompt optimizer |
| `skills/` | 19 skills especializados con plantillas FDE + EVO + C.A.S.E. |

### 2. `harness/` — El Motor

Entorno de ejecución que orquesta agentes, gestiona memoria y ejecuta herramientas.

| Módulo | Archivos Clave | Función |
|--------|----------------|---------|
| `db/lancedb_store/` | `(carpeta embebida)` | Base de datos vectorial LanceDB (sin servidor) |
| `orchestrator/` | `__init__.py` | Motor de delegación con grafo de estado |
| `memory_rag/` | *(en desarrollo)* | Ensamblador de contexto con búsqueda semántica híbrida |
| `evolve_loop/` | *(en desarrollo)* | Bucle ASI-Evolve: cognition store, experiment DB |
| `tools_sandbox/` | *(en desarrollo)* | Entorno de ejecución segura para MCP tools |

### 3. `docs/` — El Conocimiento

Documentación técnica en formato Markdown compilada con Material for MkDocs.

| Ruta | Contenido |
|------|-----------|
| `index.md` | Página principal del portal de documentación |
| `arquitectura/` | Visión general, ADRs, diagramas de arquitectura |
| `dominios_negocio/` | Documentación por dominio de negocio |
| `manual_usuario/` | Guías de usuario, referencia CLI |

---

## FDE — Forward Deployment Engineering

El sistema se rige por **7 pilares FDE** que garantizan que cada skill opera con propósito, resiliencia y capacidad de evolución.

| Pilar | Principio | Aplicación en Onyx |
|-------|-----------|-------------------|
| **DELTA** | Identificar el gap entre producto ideal y realidad | Cada misión comienza con un delta documentado |
| **MISSION** | Stakeholder definido + métrica de éxito | Todo agente tiene un propósito medible |
| **GLUE** | 50% del código es integración | A2A Protocol, adapters, contracts |
| **VALUE** | Speed-to-value primero | MVA en <30 días, 80/20 scope |
| **DIPLOMACY** | El problema técnico es 50% político | Champion + Blocker identificados |
| **RESILIENCE** | Air-gap ready, zero-trust | Timeouts, retry, circuit breakers |
| **EVOLVE** | Cada entrega genera cognition | ASI-Evolve: cognition store + experiment DB |

!!! tip "Glosario FDE"

    Consulta el [FDE Principles](https://github.com/onyx-project/onyx/blob/main/.opencode/core/fde_principles.md)
    para el glosario completo de términos como C.A.S.E., MVA, Medallion Architecture,
    Three Whys, A2A Protocol, RAG Triad, Inner/Outer Loop, Pairwise Evaluation, etc.

---

## Principios de Context Engineering

Basados en el artículo de Anthropic (Sep 2025) sobre ingeniería de contexto para sistemas multi-agente:

| Principio | Descripción |
|-----------|-------------|
| **Minimal Viable Tokens** | Usar solo los tokens necesarios para la tarea actual |
| **Sectioned Prompts** | Prompts estructurados en secciones (XML/Markdown) |
| **JIT Retrieval** | Recuperar contexto just-in-time, no pre-cargar todo |
| **Compaction** | Compactar contexto preservando decisiones críticas |
| **Structured Note-taking** | Notas persistentes para tareas multi-turno |
| **Tool Call Clearing** | Limpiar resultados de tools después de profundidad >5 |

!!! info "Más información"

    Consulta la guía completa de [Context Engineering](../dominios_negocio/context-engineering.md)
    para estrategias detalladas de optimización de tokens y gestión de contexto.

---

## Flujo de Ejecución Típico

### Delegación Directa

```
Usuario: @software-engineer: Implementa endpoint POST /usuarios
  ↓
Router v2: Detecta intención → keywords ["api", "endpoint"]
  ↓
Orquestador: Enruta a software-engineer con confianza 0.8
  ↓
Agente: Ejecuta tarea, pasa por guardrails
  ↓
Respuesta: Código implementado + documentación actualizada
```

### Flujo Multi-Agente Secuencial

```
Usuario: @project-manager: Planifica módulo de autenticación
  ↓
PM: Desglosa en tareas → delega secuencialmente
  ├─ @security-engineer: Diseña esquema de autenticación
  ├─ @software-engineer: Implementa endpoints
  └─ @quality-gate: Valida cobertura de tests
```

### Bucle de Auto-Mejora (ASI-Evolve)

```
Usuario: !evolve run software-engineer 5
  ↓
Evolve Loop: 3-agent pipeline
  ├─ Researcher: Propone mejora basada en cognition store
  ├─ Engineer: Ejecuta cambio con diff-based evolution
  └─ Analyzer: Evalúa resultado y destila lección
  ↓
Resultado: Best snapshot promovido + cognition actualizada
```

---

## Tecnologías Clave

| Tecnología | Uso en Onyx |
|------------|-------------|
| **Python 3.11+** | Lenguaje principal del framework |
| **LanceDB** | Base de datos vectorial embebida (Apache Arrow) |
| **MkDocs + Material** | Portal de documentación |
| **ONNX Runtime** | Inferencia de modelos cuantitativos |
| **Pydantic** | Validación de schemas y datos |

!!! warning "Estado del Desarrollo"

    El proyecto se encuentra en **Fase Foundation (F)** del plan F.R.A.M.E.
    Algunos módulos de `harness/` (memory_rag, evolve_loop, tools_sandbox)
    están en diseño activo y pueden no ser funcionales aún.
