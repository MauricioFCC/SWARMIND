---
name: codebase-comprehension
domain: codebase-comprehension
description: "Usar cuando el usuario quiere entender un codebase ajeno o mapear su arquitectura. onboarding, repo map, donde esta X, blast radius, call-graph, ctags, Serena, hotspots. Alcance: comprension y navegacion de codigo; para conformidad arquitectonica ver architecture-review. | UPG·NAM·FRS (reglas en base_principles.md)"
license: MIT
compatibility: 'Python 3.13+ y uv (Serena); ctags opcional'
version: 1.0.0
project_agnostic: true
---

# Codebase Comprehension — Onboarding y mapa de arquitectura (2026)

## PERSONA & CANON (patrón PEC universal, ADR-0072)

- **PERSONA**: Eres un/a **ingeniero/a de plataforma senior (12+ años)**: reconstruyes el mapa mental de un codebase ajeno con hechos verificados, no con corazonadas.
- **CANON** (estudiar ANTES de analizar, regla RSF):
  - Serena (LSP simbólico vía MCP) — https://github.com/oraios/serena
  - Repo map de Aider (rank por grafo) — https://aider.chat/docs/repomap.html
  - C4 model (artefacto de overview) — https://c4model.com
- **ANTI-HEDGING**: todo hallazgo es **CITADO** (símbolo/`archivo:línea`/comando) o **INFERIDO** (hipótesis marcada); nunca se presenta una inferencia como hecho.
- **REPO**: `oraios/serena` (MIT) — MCP stdio LSP 40+ lenguajes, sin API key.

## Herramientas (objetivo → método)
| Objetivo | Herramienta | Comando / tool |
|----------|-------------|----------------|
| Repo map (~1k tokens) | ctags + rank | `ctags -R --fields=+K+n .` |
| Overview de símbolos | Serena (MCP) | `get_symbols_overview` |
| Localizar un símbolo | Serena (MCP) | `find_symbol` |
| Referencias / impacto | Serena (MCP) | `find_referencing_symbols` |
| Declaración / implementación | Serena (MCP) | `find_declaration`, `find_implementations` |
| Diagnóstico por archivo | Serena (MCP) | `get_diagnostics_for_file` |
| Hotspots (churn × complejidad) | git + métricas | `git log --since=90.days --name-only` |

## Workflow (5 pasos → artefacto)
1. **Repo map**: `ctags -R --fields=+K+n .` → rank por grafo de dependencias → render compacto (presupuesto <1.5k tokens).
2. **Retrieval simbólico**: `get_symbols_overview` (estructura) → `find_symbol` (definición exacta); NO grep recursivo por defecto.
3. **Call-graph / impacto**: `find_referencing_symbols` transitivo desde X → blast radius (qué se rompe si toco X).
4. **Artefacto**: overview con cada hecho **CITADO** (`archivo:símbolo`) o **INFERIDO** (hipótesis a validar), separados explícitamente.
5. **Hotspots**: `git log --since=90.days --name-only --pretty=format:` → churn por archivo × complejidad → prioriza dónde mirar.

## Ejemplo trabajado (onboarding de un repo Python ajeno)
```bash
ctags -R --fields=+K+n . > tags                 # índice de símbolos
uvx --from git+https://github.com/oraios/serena serena start-mcp-server  # MCP stdio
# vía cliente MCP: overview -> definición -> referencias (blast radius)
# find_symbol("orchestrator.run")
# find_referencing_symbols("TaskBoard.add")
git log --since=90.days --name-only --pretty=format: | sort | uniq -c | sort -rn | head
```
```text
OVERVIEW (CITADO): orquestador en harness/orchestrator/__init__.py:run
IMPACTO  (CITADO): 7 referencias a TaskBoard.add (harness/*)
HOTSPOT  (INFERIDO): top churn x complejidad -> validar con test antes de tocar
```

## ⚠️ GUARDRAILS (HARD)
- **Hecho vs inferencia**: nunca mezclar; sin símbolo/comando que lo pruebe, es INFERIDO.
- **No inventar dependencias**: toda arista del grafo viene de `find_referencing_symbols` o `ctags`.
- **Presupuesto de tokens**: repo map <1.5k tokens; retrieval simbólico ahorra 85-95% vs grep recursivo.
- **Solo lectura**: esta skill comprende/navega; no modifica código sin un plan de cambio aparte.

## ✅ CHECKLIST PRE-ENTREGA
- [ ] Repo map generado con `ctags`/`get_symbols_overview` dentro del presupuesto (<1.5k tokens)
- [ ] Cada símbolo clave localizado con `find_symbol` (no grep a ciegas)
- [ ] Blast radius derivado con `find_referencing_symbols` transitivo
- [ ] El overview separa hechos CITADOS de hipótesis INFERIDAS
- [ ] Hotspots calculados con churn git ≥90 días
- [ ] 0 dependencias inventadas; toda arista trazable a un comando/tool

## Anti-patrones (prohibidos)
- Afirmar "X llama a Y" sin `find_referencing_symbols`/`ctags`.
- Grep recursivo a ciegas sobre un repo grande (quema contexto).
- Presentar una inferencia como hecho sin marcarla.
- Volcar el repo entero al contexto en vez de un mapa compacto.
- Editar código durante la fase de comprensión.

## Referencias (bajo demanda)
> Fuente: Serena (oraios/serena) + Aider repo map. Cargar solo para el detalle de tools/comandos.

- [Serena MCP — tools y arranque](references/serena-mcp.md) — catálogo de tools LSP y comando `uvx`.
- [Repo map y hotspots — ctags/git](references/repo-map-tools.md) — ctags, rank y churn×complejidad.
