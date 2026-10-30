# Spec — RuscaDB como MCP Server en SWARMIND

> Estado: blocked-upstream — Dueño: harness/tools_sandbox — Frontera: 2026-10.
> RuscaDB spec: `mcp_server.md`, `mcp_advanced_write.md`, `mcp_write_tools.md`.

## 1. Objetivo
Exponer RuscaDB como servidor MCP (stdio) para que los agentes puedan
consultar/insertar datos via MCP tools.

## 2. Diseno
- `ruscadb mcp --db <path>` como servidor MCP.
- Tools: query, insert, update, delete, tables, integrity_check.
- Integrar en `MCPManager` de SWARMIND (catalog entry).

## 3. Integracion
- Agregar entrada en `mcp_catalog.py` para ruscadb.
- Configurar en `.opencode` MCP servers.
- Auth via keystore KMS-lite (SPEC-0088).

## 4. Outcome medible
- Agentes pueden consultar RuscaDB via MCP.
- Latencia de tool call < 100ms.

## 5. Esfuerzo: 2 dias.
