---
name: agentic-hermes
description: "AGENTIC harness integration with Hermes Agent - use procedural skills, MCP, and memory"
version: 1.0.0
agent: software-engineer
domain: multi-agent-systems
trigger: "AGENTIC execute task or run harness with Hermes"
---

# AGENTIC Hermes Integration

## What This Skill Does

This skill provides seamless integration between the AGENTIC multi-agent harness and Hermes Agent, enabling:

- **Skill synchronization**: Use procedural skills defined in AGENTIC with Hermes
- **MCP server reuse**: Access AGENTIC-configured MCP servers through Hermes
- **Memory bridge**: Share cognition lessons between AGENTIC and Hermes memory
- **Agent routing**: Route tasks to AGENTIC's 21 agents using Hermes delegate_task

## Available AGENTIC Agents

When using this skill with Hermes, these agent roles are available:

| Rol | Dominio |
|-----|---------|
| `@project-manager` | Orquestación, planificación |
| `@software-engineer` | APIs, full-stack, testing |
| `@data-architect` | Schemas, migraciones, ETL |
| `@devops-sre` | CI/CD, Docker, infraestructura |
| `@security-engineer` | Seguridad, compliance |
| `@ai-engineer` | ML/AI, LLMOps |
| `@quality-gate` | QA, tests, coverage |
| `@tool-mcp-engineer` | MCP, herramientas |
| `@context-engineer` | RAG, curation |
| `@documentation-specialist` | Docs técnicas |
| `@enterprise-architect` | Arquitectura de sistemas |
| `@quant-developer` | Trading cuantitativo |
| `@quant-scientist` | Validación estadística |
| `@risk-manager` | Gestión de riesgo |
| `@trading-operations` | Monitoreo en vivo |
| `@frontend-engineer` | UI/UX, dashboards |
| `@mobile-engineer` | iOS/Android |
| `@requirements-analyst` | Análisis de requerimientos |
| `@evolve-researcher/engineer/analyzer` | Auto-mejora |

## Commands

### Run AGENTIC task through Hermes

```bash
hermes chat -q "@software-engineer: crear API REST para usuarios"
```

### Sync procedural skills

```bash
python harness/hermes_bridge.py --sync-skills
```

### Register MCP servers

```bash
python harness/hermes_bridge.py --register-mcp
```

### Check available tools

```bash
hermes tools list
```

## Workflow Integration

### GitHub Code Review Integration

```bash
# In a Hermes gateway session (Telegram/Discord/Slack):
/github review 123
# Automatically routes through AGENTIC's quality-gate agent
```

### Multi-Agent Delegation

```python
# Inside Hermes session:
delegate_task(
    goal="Build FastAPI users endpoint",
    toolsets=["terminal", "file"],
    skills=["agentic-hermes"]
)
```

## Configuration

The skill works with these environment variables:

- `HERMES_HOME` - Hermes config directory
- `OLLAMA_ENDPOINT` - For local model execution
- `OPENROUTER_API_KEY` - Cloud provider fallback

## Compatibility

- **OpenCode**: Fully compatible - AGENTIC skills load via `/skill agentic-hermes`
- **VSCode**: Use Hermes extension - skills auto-load from `.hermes/skills/`
- **Standalone**: Run `python harness/run.py` without Hermes installed