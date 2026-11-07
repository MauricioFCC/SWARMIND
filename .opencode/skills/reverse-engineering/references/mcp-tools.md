# MCP tools y variables de entorno (detalle bajo demanda)

> Fuente: docs de REA (rea.tools).

REA se expone como **MCP server** por stdio: `npx -y rea-agents@latest mcp`.
El harness/opencode lo registra fuera de esta skill (en `mcp_servers.yaml`,
otro workstream); aquí se documenta el catálogo de tools y su contrato.

## Tools MCP (`rea.*`)
| Tool | Propósito | Args clave |
|------|-----------|-----------|
| `rea.doctor` | Diagnóstico de entorno | — |
| `rea.providers` | Proveedores de decompilación disponibles | — |
| `rea.capabilities` | Capacidades por tipo de target | — |
| `rea.analyze` | Análisis genérico del artefacto | `path`, `provider?` |
| `rea.analyze_javascript_application` | JS/Electron estático (`.asar`) | `path` |
| `rea.inspect_binary` | Formato/secciones/entropía | `path` |
| `rea.inspect_metadata` | Metadata .NET | `path` |
| `rea.inspect_website` | Crawl de endpoints/assets | `url` |
| `rea.inspect_sqlite` | Esquema y tablas | `path` |
| `rea.search` | Búsqueda por patrón | `path`, `pattern` |
| `rea.function` | Recupera una función | `path`, `name` |
| `rea.decompile` | Pseudocódigo de una función | `path`, `function` |
| `rea.xrefs` | Referencias cruzadas | `path`, `symbol` |
| `rea.trace` | Rastrea flujo desde una entrada | `path`, `entry` |
| `rea.compare` | Diff entre dos artefactos | `a`, `b` |
| `rea.evidence_import` | Reimporta evidencia | `file` |
| `rea.evidence_export` | Exporta evidencia reproducible | — |

## Variables de entorno
| Variable | Efecto |
|----------|--------|
| `REA_ANALYSIS_PROVIDER` | Fuerza el provider por defecto (`hopper`\|`ghidra`\|`ida`). |
| `REA_MCP_INPUT_SCHEMA_PROFILE` | Perfil de validación del input schema MCP (estricto vs laxo). |
| `REA_MCP_MAX_RESPONSE_BYTES` | Tope de bytes por respuesta MCP (token economics). |

## Patrón de uso desde el harness
1. Arrancar/registrar el server stdio y listar tools.
2. Llamar `rea.doctor` → `rea.providers` → `rea.analyze` (fail-fast tipado).
3. Encadenar `search → xrefs → decompile → evidence_export`.
4. Ajustar `REA_MCP_MAX_RESPONSE_BYTES` para no saturar el contexto (Cache-Shape).

## Skill bundle oficial
Existe un bundle de REA instalable como skill genérica:
`npx skills add morluto/rea --skill reverse-engineer-anything`.
Esta skill del repo lo envuelve para integrarlo con el harness (evidencia + guardrails).
