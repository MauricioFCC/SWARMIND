# Serena MCP — tools y arranque (detalle bajo demanda)

> Fuente: `oraios/serena` (MIT) — https://github.com/oraios/serena

Serena expone un **MCP server por stdio** que envuelve un **LSP** (Language
Server Protocol): comprensión simbólica real de 40+ lenguajes, sin API key
(el razonamiento lo hace el agente; Serena aporta los símbolos).

## Arranque (sin instalar)
```bash
uvx --from git+https://github.com/oraios/serena serena start-mcp-server
```

## Tools de comprensión (`*.get_*` / `*.find_*`)
| Tool | Propósito | Args clave |
|------|-----------|-----------|
| `get_symbols_overview` | Estructura de un archivo (símbolos de nivel superior) | `file` |
| `find_symbol` | Localiza un símbolo por nombre (definición exacta) | `name_path`, `substring_matching?` |
| `find_referencing_symbols` | Quién referencia un símbolo (base del blast radius) | `symbol` |
| `find_declaration` | Declaración de un símbolo | `symbol` |
| `find_implementations` | Implementaciones de una interfaz/método | `symbol` |
| `get_diagnostics_for_file` | Diagnósticos LSP del archivo | `file` |
| `search_for_pattern` | Búsqueda por patrón acotada por rutas | `pattern`, `paths?` |

## Tools de edición (`*.replace_*` / `*.insert_*`)
| Tool | Propósito |
|------|-----------|
| `replace_content` | Reemplazo puntual de contenido |
| `replace_symbol_body` | Reemplaza el cuerpo de un símbolo |
| `insert_after_symbol` / `insert_before_symbol` | Inserta código relativo a un símbolo |

> En esta skill se usan **solo las tools de comprensión** (lectura). La edición
> pertenece a un plan de cambio aparte.

## Patrón de uso desde el harness
1. `get_symbols_overview` → mapa del archivo.
2. `find_symbol` → definición exacta (evita grep recursivo).
3. `find_referencing_symbols` (transitivo) → **blast radius** de un cambio.
4. `get_diagnostics_for_file` → salud estática del archivo tocado.
5. Ajustar el tamaño de respuesta MCP para no saturar el contexto (Cache-Shape).

## LSP vs grep
- LSP resuelve **símbolos** (con scope/tipo), no texto: 85-95% de ahorro de
  tokens vs `grep -r` y 0 falsos positivos de coincidencias en strings/comentarios.
- Sin símbolo que lo demuestre, un hallazgo es **INFERIDO**, no CITADO.
