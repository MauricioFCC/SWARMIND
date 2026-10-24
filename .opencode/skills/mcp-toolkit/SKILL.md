---
name: mcp-toolkit
domain: tooling
description: "Usar cuando hay que elegir o cablear herramientas MCP para una tarea (browser, scraping, db, kubernetes, reverse engineering, observabilidad, data, devops). Alcance: seleccion de herramientas MCP del harness; para comprension de codigo ver codebase-comprehension; para RE ver reverse-engineering. | UPG·NAM·FRS"
license: MIT
compatibility: 'opencode + harness MCPManager; catalogo en harness/tools_sandbox/mcp_servers.yaml'
version: 1.0.0
project_agnostic: true
---

# MCP Toolkit — la herramienta correcta para el trabajo

## PERSONA & CANON (patrón PEC universal, ADR-0072)

- **PERSONA**: Eres un/a **platform engineer senior (10+ años)** especializado en integración de herramientas vía MCP y en elegir la herramienta adecuada por tarea (no martillar con la misma herramienta).
- **CANON** (estudiar ANTES de generar, regla RSF):
  - Especificación MCP — https://modelcontextprotocol.io
  - Registro oficial de servers — https://registry.modelcontextprotocol.io
  - Catalogo del harness — `harness/tools_sandbox/mcp_servers.yaml`
- **ANTI-HEDGING**: elige la herramienta por evidencia (categoria, credenciales, engine); si no hay herramienta adecuada, dilo en vez de forzar una.

## Catalogo por categoria (SSOT: `harness/tools_sandbox/mcp_servers.yaml`)

| Categoria | Servers MCP |
|-----------|-------------|
| reverse-engineering | `rea`, `rc_devtools`, `ghidra_mcp`, `radare2` |
| browser / testing | `playwright`, `chrome_devtools` |
| web / scraping | `fetch`, `firecrawl` |
| datos | `postgres`, `supabase` (candidatos: mongodb, redis, clickhouse) |
| vcs | `github`, `git` |
| devops / infra | `kubernetes` (candidatos: cloudflare, terraform, aws) |
| observabilidad | `sentry` (candidato: grafana, datadog) |
| productividad / docs | `notion`, `context7` |
| razonamiento | `sequentialthinking` |
| utilidades | `time`, `memory` (grafo de conocimiento) |
| comprension de codigo | `serena` |
| diseno | figma (candidato) |
| ML / cloud | huggingface (candidato), cloudflare (candidato) |

## Regla de seleccion (la herramienta correcta)

1. Identifica el TARGET/dominio de la tarea (keyword: browser, scrape, sql, k8s, reverse…).
2. `harness.tools_sandbox.mcp_catalog.servers_for_task(task)` devuelve los servers aplicables (nunca inventa: todo nombre existe en la SSOT).
3. El harness los expone en `DispatchPlan.tools` (agente + skills + **herramientas** juntos).
4. opencode los usa via `mcp.servers` (registrados por `deploy_all.py --sync-global`).

## Cableado en el harness

- SSOT: `harness/tools_sandbox/mcp_servers.yaml` (23 servers).
- Seleccion: `mcp_catalog.servers_for_task(task)` y `servers_for_skill(skill)`.
- Traduccion a opencode: `mcp_opencode` (stdio→local, http→remote) + `deploy_all.py --sync-global`.
- Router RE: `harness/reverse_engineering/target_router.py` (target→engine+evidencia+servers).

## Guardrails

- Solo servers VERIFICADOS (comando + tools contra el repo oficial); los candidatos se documentan aparte.
- Credenciales por entorno (`{env:VAR}`); nunca hardcodear API keys.
- Server sin credenciales/engine → `disabled` (no romper el arranque de opencode).
- Solo targets propios o con autorizacion (RE/pentest).

## Checklist

- [ ] Categoria/target de la tarea identificada
- [ ] `servers_for_task` devuelve la herramienta correcta (no inventa)
- [ ] Credenciales por entorno, no en el archivo
- [ ] `deploy_all --sync-global` deja la config de opencode en sync
- [ ] Evidencia de la herramienta (salida real), no afirmacion (VER)

## Anti-patrones (prohibidos)

- Usar siempre la misma herramienta en vez de la correcta para el trabajo.
- Hardcodear API keys o tokens (SEG).
- Registrar un server sin verificar su comando y tools.
- Cargar servers pesados al arranque sin necesidad (timeouts).
