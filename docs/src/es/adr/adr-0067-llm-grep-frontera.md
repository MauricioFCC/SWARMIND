# ADR 0067: LLM-Grep Frontera — Ripgrep-First 3 Capas, Budget-Aware, Compaction-Friendly

## Estado
Aplicado | Implementado en `harness/memory_rag/llm_grep.py` + `harness/tests/test_llm_grep.py` | Propietario: @coordinator | Fecha: 2026-09-06

## Contexto
Frontera 2026 convergente (web research 2026-09-06):

1. **ceaksan 2026-05-19** (Code Search for AI Agents): 3 capas — léxica (ripgrep), estructural (ast-grep), semántica (repo-map/embeddings). Orden: **ripgrep primero, ast-grep si patrón estructural, repo-map solo si query conceptual; embeddings último recurso**. CoREB: queries cortas colapsan todo modelo semántico. Reglas salida: dedup, gitignore-aware, strip blanks, `file:line + 2 líneas` (alinea con tool-result clearing de Claude Code). Speculative prefetch LLM-free (Tree-sitter + ripgrep ~50ms) y métrica `semantic_ratio >20% = misrouting`.
2. **arXiv:2605.15184** (Is Grep All You Need?): en harnesses agénticos **grep supera a vector** en spans literales; el harness y el formato de tool-output pesan más que el backend.
3. **particula 2026-07-06**: híbrido BM25+dense recorta tokens ~40% a igual calidad.

SWARMIND tiene `HybridRetriever` (RRF k=60) + `FTSSearch` + `LanceVectorStore.hybrid_search` para **memoria**, pero ningún grep de **código** budget-aware para LLMs (gap verde, IDP ok).

## Decisión
`harness/memory_rag/llm_grep.py` con protocolo inyectable + 3 backends ordenados:

1. **LEXICAL primero** (`ripgrep` via `rg --vimgrep`, gitignore-aware nativo): keyword/regex literal. Si hits ≥ `min_hits` → retornar sin escalar.
2. **STRUCTURAL** (adapter `ast-grep`, lazy/optional): solo si query es estructural (`def|class|fn|interface|struct` o flag explícito) o lexical vacío.
3. **SEMANTIC último recurso**: delega a `HybridRetriever.retrieve()` existente (sin duplicarlo).
4. **Salida compaction-friendly**: `GrepHit(path, line, col, context[2])`, dedup por `(path,line)`, strip blanks/decoradores, cap `max_hits` + `max_context_lines=2`.
5. **Budget governance**: `GrepBudget(max_hits, max_bytes)` fail-fast; `route_report()` expone `lexical/structural/semantic` + `semantic_ratio` para detectar misrouting (>20% alerta); errores WHAT+WHY+WHERE, sin `except:pass`.

## Consecuencias
### Positivas
- Tokens búsqueda acotados desde el diseño (no por disciplina posterior).
- Reutiliza RRF/BM25 existentes en vez de reimplementar (IDP).
- Métrica routing auditable (misrouting visible).

### Negativas
- `rg` binario requerido (falla explícita si ausente; sin fallback silencioso a Python).
- ast-grep opcional: sin binario, capa structural = no-op documentado.

## Alternatives Considered
1. **Solo vector sobre código**: pierde en spans literales (2605.15184) y cuesta ~40% más tokens.
2. **Solo ripgrep raw**: sin policy, sin dedup, sin budget (raw no es apto para agente).
3. **Aider repo-map externo**: determinista pero acoplado a Aider; YAGNI como dependencia.

## Relacionado
- ADR 0050 (capa semántica), `hybrid_retriever.py` (RRF), `fts_search.py`, ADR 0056 (dedup keep-last)
- ceaksan pillar 2026-05-19, arXiv:2605.15184, particula 2026-07-06, `01_search_frontier/RandomSearch.md`
