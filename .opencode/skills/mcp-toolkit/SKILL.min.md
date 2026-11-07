---
name: mcp-toolkit
domain: tooling
description: "Usar cuando hay que elegir o cablear herramientas MCP para una tarea (browser, scraping, db, kubernetes, reverse engineering, observabilidad, data, devops)."
version: 1.0.0
project_agnostic: true
---

# MCP Toolkit (min)

PERSONA: platform engineer senior (10+ años), integracion de herramientas MCP.
CANON: https://modelcontextprotocol.io ; https://registry.modelcontextprotocol.io ; SSOT `harness/tools_sandbox/mcp_servers.yaml`.

CATEGORIAS -> servers:
- reverse-engineering: rea, rc_devtools, ghidra_mcp, radare2
- browser: playwright, chrome_devtools
- web/scraping: fetch, firecrawl
- datos: postgres, supabase
- vcs: github, git
- devops: kubernetes
- observabilidad: sentry
- docs/productividad: notion, context7
- razonamiento: sequentialthinking | utilidades: time, memory | codigo: serena

SELECCION: `mcp_catalog.servers_for_task(task)` (no inventa) -> `DispatchPlan.tools` (agente+skills+herramientas) -> opencode `mcp.servers` via `deploy_all --sync-global`.
GUARDRAILS: servers verificados; credenciales `{env:VAR}`; sin creds/engine -> disabled.
