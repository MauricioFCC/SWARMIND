# Onyx — Sistema Multi-Agente Universal

!!! tip "Framework de skills multi-agente con enrutamiento automático, FDE, ASI-Evolve y contexto adaptativo"

    Onyx es un framework universal de agentes que combina **Forward Deployment Engineering (FDE)**,
    un **bucle de auto-mejora ASI-Evolve**, enrutamiento inteligente por intención,
    y un sistema de memoria basado en **LanceDB** con búsqueda vectorial híbrida.

---

## ¿Qué es Onyx?

Onyx es un **sistema operativo para agentes de IA** que orquesta múltiples skills especializados
a través de un grafo de enrutamiento con estado. Cada skill opera bajo principios universales
(ARQ, SEG, DOC, TST, OPS, CMT, QLT, FDE, EVO) y puede ejecutarse de forma autónoma
o bajo supervisión humana.

El sistema está compuesto por tres capas fundamentales:

| Capa | Directorio | Función |
|------|-----------|---------|
| **Cerebro** | `.opencode/` | Reglas, perfiles de agentes, principios FDE, configuración |
| **Motor** | `harness/` | Entorno de ejecución: base de datos vectorial, orquestador, RAG, sandbox |
| **Conocimiento** | `docs/` | Documentación técnica, manuales de usuario, ADRs |

!!! note "Docs-as-Code"

    Toda la documentación se escribe en Markdown y se compila con **Material for MkDocs**
    para generar un portal web profesional. Los agentes pueden leer y escribir directamente
    sobre los archivos `.md`, manteniendo la documentación siempre sincronizada con el código.

---

## Arquitectura

El sistema sigue un patrón de **microservicios de agentes** con un **orquestador central** (`router_v2.py`)
que implementa el **Protocolo A2A (Agent-to-Agent)** para descubrimiento y handoff formal entre agentes.

```
┌─────────────┐
│   Usuario   │
└──────┬──────┘
       │ @rol / mensaje
       ▼
┌─────────────────────┐
│  Project Manager    │ ← Punto de entrada y coordinación
│  (Orquestador)      │
└──────────┬──────────┘
           │ delega
           ▼
┌──────────────────────────────────────────────┐
│  ┌──────────┐ ┌──────────┐ ┌──────────────┐ │
│  │ Quant    │ │ Software │ │ AI/ML        │ │
│  │ Developer│ │ Engineer │ │ Engineer      │ │
│  └──────────┘ └──────────┘ └──────────────┘ │
│  ┌──────────┐ ┌──────────┐ ┌──────────────┐ │
│  │ Security │ │ Data     │ │ Context      │ │
│  │ Engineer │ │ Architect│ │ Engineer      │ │
│  └──────────┘ └──────────┘ └──────────────┘ │
│  ┌──────────┐ ┌──────────┐ ┌──────────────┐ │
│  │ Quality  │ │ Evolve   │ │ ... (21      │ │
│  │ Gate     │ │          │ │  agentes)    │ │
│  └──────────┘ └──────────┘ └──────────────┘ │
└──────────────────────┬───────────────────────┘
                       ▼
┌──────────────────────────────┐
│         Harness              │
│  ┌────────┐ ┌─────────────┐  │
│  │ LanceDB│ │ Tools       │  │
│  │ (Vector│ │ Sandbox     │  │
│  │  Store)│ │ (MCP Exec)  │  │
│  └────────┘ └─────────────┘  │
└──────────────────────────────┘
```

### Componentes del Harness

| Componente | Descripción |
|------------|-------------|
| **LanceDB Store** | Base de datos vectorial embebida (sin servidor). Almacena colecciones de tareas, chunks RAG y cognición. |
| **Orchestrator** | Motor de delegación con grafo de estado. Implementa patrones sequential, parallel y loop. |
| **Memory RAG** | Ensamblador de contexto contextual. Búsqueda semántica híbrida (vector + keyword). |
| **Evolve Loop** | Bucle de auto-mejora ASI-Evolve: cognition store, experiment DB, UCB1 sampling. |
| **Tools Sandbox** | Entorno de ejecución segura para MCP tools con circuit breaker. |

---

## Skills Activos (19)

El framework cuenta con **19 skills especializados** que se asignan mediante enrutamiento por intención.

| Skill | Rol FDE | Disparador de Enrutamiento |
|-------|---------|---------------------------|
| `project-manager` | MISSION, DIPLOMACY, VALUE | roadmap, plan, progreso, delegación @rol |
| `quant-developer` | DELTA, GLUE, EVOLVE | estrategia, señal, broker, ONNX, backtest |
| `quant-scientist` | EVOLVE, DELTA, VALUE | overfitting, sharpe, experimento, validación |
| `risk-manager` | RESILIENCE, MISSION, DELTA | drawdown, position sizing, kelly, var |
| `software-engineer` | GLUE, RESILIENCE, DELTA | api, endpoint, deploy, microservicios |
| `security-engineer` | RESILIENCE, DIPLOMACY, MISSION | vulnerabilidad, compliance, sql injection |
| `data-architect` | DELTA, GLUE, RESILIENCE | esquema, pipeline, migration, etl |
| `devops-sre` | RESILIENCE, GLUE, VALUE | ci/cd, kubernetes, monitoring, iac |
| `enterprise-architect` | DELTA, GLUE, DIPLOMACY | arquitectura, system design, adr |
| `ai-engineer` | DELTA, EVOLVE, VALUE | ml, llm, modelo, inferencia, rag |
| `context-engineer` | VALUE, DIPLOMACY, EVOLVE | context, prompt, compaction, memoria |
| `frontend-engineer` | VALUE, DIPLOMACY, DELTA | dashboard, ui, componente, visualización |
| `quality-gate` | GLUE, RESILIENCE, EVOLVE | validación, gate, test strategy, cobertura |
| `trading-operations` | MISSION, VALUE, RESILIENCE | monitoreo, alerta, conexión, schedule |
| `mobile-engineer` | VALUE, GLUE, DELTA | mobile, push notification, offline |
| `documentation-specialist` | DIPLOMACY, MISSION, VALUE | documentación, manual, api docs |
| `tool-mcp-engineer` | GLUE, VALUE, RESILIENCE | tool, mcp, herramienta, protocolo |
| `requirements-analyst` | — | análisis, requerimientos, viabilidad |
| `evolve` | EVOLVE, GLUE, VALUE | evolución, mejora, aprender, optimizar |

!!! info "Roles fusionados"

    Los siguientes roles se han fusionado en skills activos: `backend-engineer` → `software-engineer`,
    `compliance-officer` → `security-engineer`, `qa-automation` → `quality-gate`.

---

## Agentes del Sistema (21)

Cada skill tiene un **agente** asociado en `.opencode/agents/` con un perfil ejecutable:

| # | Agente | Archivo |
|---|--------|---------|
| 1 | `ai-engineer` | `.opencode/agents/ai-engineer.md` |
| 2 | `context-engineer` | `.opencode/agents/context-engineer.md` |
| 3 | `data-architect` | `.opencode/agents/data-architect.md` |
| 4 | `devops-sre` | `.opencode/agents/devops-sre.md` |
| 5 | `documentation-specialist` | `.opencode/agents/documentation-specialist.md` |
| 6 | `enterprise-architect` | `.opencode/agents/enterprise-architect.md` |
| 7 | `evolve-analyzer` | `.opencode/agents/evolve-analyzer.md` |
| 8 | `evolve-engineer` | `.opencode/agents/evolve-engineer.md` |
| 9 | `evolve-researcher` | `.opencode/agents/evolve-researcher.md` |
| 10 | `frontend-engineer` | `.opencode/agents/frontend-engineer.md` |
| 11 | `mobile-engineer` | `.opencode/agents/mobile-engineer.md` |
| 12 | `project-manager` | `.opencode/agents/project-manager.md` |
| 13 | `quality-gate` | `.opencode/agents/quality-gate.md` |
| 14 | `quant-developer` | `.opencode/agents/quant-developer.md` |
| 15 | `quant-scientist` | `.opencode/agents/quant-scientist.md` |
| 16 | `requirements-analyst` | `.opencode/agents/requirements-analyst.md` |
| 17 | `risk-manager` | `.opencode/agents/risk-manager.md` |
| 18 | `security-engineer` | `.opencode/agents/security-engineer.md` |
| 19 | `software-engineer` | `.opencode/agents/software-engineer.md` |
| 20 | `tool-mcp-engineer` | `.opencode/agents/tool-mcp-engineer.md` |
| 21 | `trading-operations` | `.opencode/agents/trading-operations.md` |

---

## Cómo Empezar

### 1. Instalación

```bash
# Clonar el repositorio
git clone https://github.com/onyx-project/onyx.git
cd onyx

# Instalar dependencias
pip install -r requirements.txt

# Inicializar documentación (opcional)
pip install mkdocs-material
mkdocs serve
```

### 2. Configuración Inicial

Editar `.opencode/config/project_config.yaml` con los datos de tu proyecto:

```yaml
PROJECT_NAME: "Mi Proyecto"
DOMAIN: "web"  # o trading, mobile, ml, iot, robotics
TECH_STACK: "Python"
```

### 3. Primeros Pasos con Agentes

!!! example "Ejemplos de uso"

    **Delegación directa:**
    ```
    @software-engineer: Implementa el endpoint POST /usuarios con validación.
    ```

    **Flujo multi-agente:**
    ```
    @project-manager: Planifica el módulo de autenticación, delega a
    @security-engineer para revisión de seguridad.
    ```

    **Auto-mejora:**
    ```
    !evolve status
    !evolve run software-engineer 5
    ```

### 4. Explorar la Documentación

| Sección | Descripción |
|---------|-------------|
| [Arquitectura](arquitectura/index.md) | Visión general del sistema, componentes y decisiones arquitectónicas |
| [ADR-001: Base de Datos](arquitectura/adr-001-base-datos.md) | Registro de decisión: LanceDB como almacenamiento unificado |
| [Sistema Multi-Agente](dominios_negocio/sistema-agentes.md) | Catálogo completo de agentes, patrones de delegación |
| [Context Engineering](dominios_negocio/context-engineering.md) | Guía de optimización de contexto y presupuesto de tokens |
| [Guía de Agentes](manual_usuario/agentes.md) | Cómo usar `@rol`, lista completa de agentes |
| [Referencia CLI](manual_usuario/cli.md) | Comandos del sistema, evolución y configuración |

---

!!! warning "Proyecto en Fase Foundation (F)"

    Onyx se encuentra en sus etapas iniciales. La documentación y los componentes
    están en evolución constante. Consulta el [CHANGELOG](CHANGELOG.md) para
    ver el historial de cambios.

Para contribuir o reportar issues, visita el [repositorio en GitHub](https://github.com/onyx-project/onyx).
