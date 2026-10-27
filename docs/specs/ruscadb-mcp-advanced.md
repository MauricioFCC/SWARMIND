# Spec — MCP Avanzado (RuscaDB) en SWARMIND

> Estado: proposed — Dueño: harness/tools_sandbox — Frontera: 2026-10.
> RuscaDB spec: `mcp_advanced_write.md`, `mcp_write_tools.md`, `mcp_server.md`.

## 1. Objetivo
Exponer RuscaDB como MCP server con tools de escritura avanzadas (upsert,
update, delete, backup, integrity_check).

## 2. Integracion
- `ruscadb mcp --db <path> --write` como servidor MCP.
- Agregar a MCPManager catalog.
- Auth via keystore KMS-lite.

## 3. Outcome medible
- Agentes pueden leer/escribir RuscaDB via MCP.
- Latencia de tool call < 100ms.

## 5. Esfuerzo: 2 dias.
