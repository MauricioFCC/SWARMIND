# ADR-0015: MCP + A2A Architecture 2026

## Estado
**ACEPTADO** — Implementado parcialmente en codebase, documentado formalmente ahora.

## Contexto
El sistema Swarmind utiliza dos protocolos fundamentales de comunicacion:
- **MCP (Model Context Protocol)**: Para integracion con herramientas externas vía MCPClient/MCPManager
- **A2A (Agent-to-Agent)**: Para descubrimiento y handoff entre agentes vía router_a2a.py

Ambos estan implementados en codigo pero SIN ADR formal ni actualizacion a specs 2026.

## Decision

### 1. MCP — Model Context Protocol
- Version target: spec 2026 (streamable HTTP, MCP Apps)
- Implementacion actual en harness/tools_sandbox/ (MCPClient, MCPManager, MCPExecutor)
- Servidores MCP configurables via YAML en cada proyecto
- Tools expuestas como MCP endpoints para integracion con LLMs

### 2. A2A — Agent-to-Agent Protocol
- Version target: Google A2A v1.0.1 (Linux Foundation, Mayo 2026)
- Implementacion actual en .opencode/core/router_a2a.py
- Agent Cards con capacidades, skills y autenticacion
- Handoff entre agentes con context transfer

### 3. Skills de Seguridad y Platform
- **security-audit**: Nuevo skill para AppSec/DevSecOps (SAST, DAST, SBOM, Threat Modeling)
- **platform-engineering**: Pendiente para proxima iteracion (K8s, CI/CD, IaC)

## Consecuencias
- ADRs totales: 21
- Skills totales: 16 (evolve, hedgefund, quant-trading, alpha-research, risk-execution,
  frontend-uiux, math-doc, legal-doc, science-doc, healthtech, pos-retail, rust-lang,
  architecture, data-science, responsive-ui, security-audit)
- Agentes: 8 (sin cambios)
