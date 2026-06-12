# AGENTS.md — Onyx Multi-Agent System (Hermes-style manifest)

Este proyecto utiliza un sistema multi-agente orquestado por el **Harness**.

## Agentes (21)

| Rol | Dominio principal | Delegacion |
|------|------------------|------------|
| @project-manager | Orquestacion F.R.A.M.E., planificacion | `@pm` |
| @context-engineer | Curation de contexto, token budget, RAG | `@context` |
| @tool-mcp-engineer | Ecosistema MCP, herramientas | `@mcp` |
| @software-engineer | APIs, servicios, full-stack | `@swe` |
| @data-architect | Schemas, modelos, migraciones | `@data` |
| @devops-sre | CI/CD, Docker, infraestructura | `@devops` |
| @security-engineer | Seguridad, compliance, hardening | `@sec` |
| @frontend-engineer | UI/UX, dashboards | `@frontend` |
| @mobile-engineer | Apps iOS/Android | `@mobile` |
| @ai-engineer | ML/AI, pipelines, LLMOps | `@ai` |
| @quality-gate | QA, tests, cobertura | `@qa` |
| @documentation-specialist | Documentacion tecnica | `@docs` |
| @requirements-analyst | Analisis de requerimientos | `@ra` |
| @enterprise-architect | Arquitectura de sistemas, ADR | `@architect` |
| @quant-developer | Estrategias cuantitativas, brokers | `@quant` |
| @quant-scientist | Validacion estadistica, experimentos | `@scientist` |
| @risk-manager | Gestion de riesgo, position sizing | `@risk` |
| @trading-operations | Monitoreo en vivo, alertas | `@ops` |
| @evolve-researcher | Investigacion de mejoras | `!evolve run` |
| @evolve-engineer | Ejecucion de mejoras | `!evolve run` |
| @evolve-analyzer | Analisis de resultados | `!evolve run` |

## Skills (19)

`quant-developer`, `quant-scientist`, `risk-manager`, `trading-operations`,
`software-engineer`, `data-architect`, `devops-sre`, `security-engineer`,
`frontend-engineer`, `mobile-engineer`, `ai-engineer`, `quality-gate`,
`project-manager`, `context-engineer`, `tool-mcp-engineer`,
`documentation-specialist`, `requirements-analyst`, `enterprise-architect`,
`evolve` (compartido por los 3 subagentes).

## Comandos rapidos

- `@rol: mensaje` — Delegacion directa
- `python harness/run.py "@rol: tarea"` — CLI entry point
- `python scripts/init.py` — Bootstrap de nuevo proyecto
- `python scripts/generate_llms_txt.py` — Generar /llms.txt

## Fuentes de inspiracion

- Hermes Agent (NousResearch) — memoria procedural, GEPA, /llms.txt
- Arquitectura de Integracion Actualizada (harness + context + hermes)
