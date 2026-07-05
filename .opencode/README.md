# .opencode System — Universal Multi-Agent Framework

> **🏦 Doctrina Hedge Fund**: Este sistema puede operar bajo la doctrina de **Hedge Fund Institucional**.
> Los LLMs actúan como gestores del fondo (CIO, PM, Quant, CRO, COO). Cada tarea es una asignación
> de capital con riesgo/reward, mandato y stop-loss. Más información en `skills/hedgefund/SKILL.md`.

Sistema de skills multi-agente con enrutamiento automático, FDE (Forward Deployment Engineering) y ASI-Evolve (autonomous self-improvement loop).

## Estructura

```
.opencode/
├── agents/            # 21 agentes activos
│   ├── ai-engineer.md
│   ├── context-engineer.md
│   ├── data-architect.md
│   ├── devops-sre.md
│   ├── documentation-specialist.md
│   ├── enterprise-architect.md
│   ├── evolve-analyzer.md
│   ├── evolve-engineer.md
│   ├── evolve-researcher.md
│   ├── frontend-engineer.md
│   ├── mobile-engineer.md
│   ├── project-manager.md
│   ├── quality-gate.md
│   ├── quant-developer.md
│   ├── quant-scientist.md
│   ├── requirements-analyst.md
│   ├── risk-manager.md
│   ├── security-engineer.md
│   ├── software-engineer.md
│   ├── tool-mcp-engineer.md
│   └── trading-operations.md
├── config/            # Configuración central
│   ├── project_config.yaml    # Variables del proyecto
│   ├── routing_rules.yaml     # Keywords/regex → agente destino
│   └── token_budgets.yaml     # Límites de tokens por rol
├── core/              # Módulos base del framework
│   ├── __init__.py
│   ├── base_principles.md     # 9 categorías universales (ARQ, SEG, DOC...)
│   ├── base_skill_template.md # Plantilla v3 con FDE + Evolve + C.A.S.E.
│   ├── fde_principles.md      # 7 pilares FDE + glosario + checklist
│   ├── guardrails.py          # Pre/post pipeline (19 checks)
│   ├── prompt_optimizer.py    # Compresión, budget, relevance scoring
│   ├── registry.py
│   ├── router_v2.py           # Grafo de estado + A2A Protocol + multi-agent
│   └── skill_schema.json      # Schema v3
├── skills/            # 20 skills activos
│   ├── ai-engineer/           # ML/AI engineering, LLMOps
│   ├── context-engineer/      # Context curation, compaction, memory
│   ├── data-architect/        # Data modeling, ETL, migrations
│   ├── devops-sre/            # CI/CD, infra, Docker/K8s
│   ├── documentation-specialist/
│   ├── enterprise-architect/  # System design, ADR, strategy
│   ├── evolve/                # Meta-skill: self-improvement loop
│   ├── frontend-engineer/     # UI, dashboards, visualization
│   ├── hedgefund/ ⭐          # Doctrina fundacional: operar como hedge fund institucional
│   ├── mobile-engineer/
│   ├── project-manager/       # F.R.A.M.E. orchestration
│   ├── quality-gate/          # QA + test strategy (merged qa-automation)
│   ├── quant-developer/       # Trading strategy implementation
│   ├── quant-scientist/       # Research, validation, experiments
│   ├── requirements-analyst/  # Feature analysis, feasibility
│   ├── risk-manager/          # Position sizing, Monte Carlo
│   ├── security-engineer/     # AppSec + compliance (merged compliance-officer)
│   ├── software-engineer/     # Full-stack, APIs, services
│   ├── tool-mcp-engineer/     # MCP tools, tool ecosystem
│   └── trading-operations/    # Live monitoring, alerts
└── .gitignore
```

## Arquitectura

### Core Pillars
- **FDE** — Forward Deployment Engineering: 7 pilares (DELTA, MISSION, GLUE, VALUE, DIPLOMACY, RESILIENCE, EVOLVE) que garantizan que cada skill opera con stakeholder real, métrica de éxito y Day 2 plan.
- **C.A.S.E.** — Clarify → Architect → Solve → Evaluate: marco universal de razonamiento que toda respuesta de agente debe seguir.
- **ASI-Evolve** — Autonomous self-improvement loop: cognition store, experiment DB, UCB1 sampling, best snapshot promotion.

### Routing Graph
Router v2 implementa un grafo de estado con nodos que definen transiciones condicionales entre agentes. Soporta:
- **Single-agent**: ruteo directo por intención (keywords + regex)
- **Multi-agent Sequential**: cadena de agentes (output de N → input de N+1)
- **Multi-agent Parallel**: agentes en paralelo con merge (concat / vote / priority)
- **Multi-agent Loop**: repite agente hasta convergencia o max_iterations

### Guardrail Pipeline
Pre-checks (arquitectura + discovery) y post-checks (seguridad + commits + docs + three whys) con 3 severidades: BLOCK / WARN / INFO.

## Skills Activos (20)

| Skill | FDE Pillars | Routing Trigger |
|-------|-------------|-----------------|
| **hedgefund** ⭐ | **DELTA, MISSION, RESILIENCE** | **Doctrina fundacional: hedge fund, fondo, inversión, capital, riesgo, mandato, institutional, data science** |
| project-manager | MISSION, DIPLOMACY, VALUE | roadmap, plan, progreso, delegación @rol |
| quant-developer | DELTA, GLUE, EVOLVE | estrategia, señal, broker, ONNX, backtest |
| quant-scientist | EVOLVE, DELTA, VALUE | overfitting, sharpe, experimento, validación |
| risk-manager | RESILIENCE, MISSION, DELTA | drawdown, position sizing, kelly, var |
| software-engineer | GLUE, RESILIENCE, DELTA | api, endpoint, deploy, microservicios, full-stack |
| security-engineer | RESILIENCE, DIPLOMACY, MISSION | vulnerabilidad, compliance, sql injection, auth |
| data-architect | DELTA, GLUE, RESILIENCE | esquema, pipeline, migration, etl |
| devops-sre | RESILIENCE, GLUE, VALUE | ci/cd, kubernetes, monitoring, iac |
| enterprise-architect | DELTA, GLUE, DIPLOMACY | arquitectura, system design, adr, roadmap |
| ai-engineer | DELTA, EVOLVE, VALUE | ml, llm, modelo, inferencia, rag, pipeline |
| context-engineer | VALUE, DIPLOMACY, EVOLVE | context, prompt, compaction, memoria, retrieval |
| frontend-engineer | VALUE, DIPLOMACY, DELTA | dashboard, ui, componente, visualización |
| quality-gate | GLUE, RESILIENCE, EVOLVE | validación, gate, test strategy, cobertura |
| trading-operations | MISSION, VALUE, RESILIENCE | monitoreo, alerta, conexión, schedule |
| mobile-engineer | VALUE, GLUE, DELTA | mobile, push notification, offline |
| documentation-specialist | DIPLOMACY, MISSION, VALUE | documentación, manual, api docs |
| evolve | EVOLVE, GLUE, VALUE | evolucion, mejora, aprender, optimizar |
| tool-mcp-engineer | GLUE, VALUE, RESILIENCE | tool, mcp, herramienta, protocolo, tool call |
| requirements-analyst | — | análisis, requerimientos, viabilidad |

**Merged into active roles**: `backend-engineer` (→ software-engineer), `compliance-officer` (→ security-engineer), `qa-automation` (→ quality-gate).

**Doctrina Fundacional**: `hedgefund` es una skill doctrinal que NO reemplaza a las demás skills. Proporciona el marco de inversión (riesgo/reward, mandato, stop-loss, reporting) que contextualiza todas las operaciones del sistema.

## Commands

### Evolve Loop
- `!evolve status` — Estado del loop
- `!evolve run <skill> <rounds>` — Ejecutar N rondas de mejora
- `!evolve cognition add <title> <content>` — Añadir conocimiento
- `!evolve cognition search <query>` — Buscar en cognition store
- `!evolve best <skill>` — Mejor snapshot actual
- `!evolve stats` — Estadísticas del loop

### Delegation
- `@project-manager: ...` — Delegar a PM
- `@quant-developer: ...` — Delegar implementación
- `@risk-manager: ...` — Delegar revisión de riesgo
- `@quant-scientist: ...` — Delegar investigación/experimento

## Extending

1. Crear `skills/{nuevo-rol}/SKILL.md` usando `core/base_skill_template.md` como template
2. Añadir routing rules en `config/routing_rules.yaml` (keywords + regex)
3. Añadir nodo en `core/router_v2.py` `ROUTING_GRAPH` con transiciones
4. Añadir agente en `agents/{nuevo-rol}.md` con input/output schema
5. Opcional: registrar `fde` + `evolve` en `core/skill_schema.json`

## References

- **`skills/hedgefund/SKILL.md`** ⭐ — **Doctrina Fundacional**: Hedge Fund Institucional con LLMs como gestores
- `core/base_skill_template.md` — Template v3.0 con FDE Layer + Evolve Layer + C.A.S.E.
- `core/fde_principles.md` — 7 pilares FDE + glosario + checklist operativo
- `core/guardrails.py` — Pre/post pipeline con 19 checks (ARQ, SEC, COST, MCP, RAG)
- `core/prompt_optimizer.py` — Compresión, budget, relevance scoring
- `core/router_v2.py` — Grafo de estado con multi-agent patterns
- `core/registry.py` — Skill registry con contratos y versionado SemVer
- `config/project_config.yaml` — Variables del proyecto
