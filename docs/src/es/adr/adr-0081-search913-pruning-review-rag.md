# ADR 0081: Search 9-13-2026 — Tool Pruning, Cross-Review, RAG-20, Action-First, Sandbox, TurboVec

## Estado
Aplicado | `harness/orchestrator/tool_pruner.py` + `harness/validation/{cross_review,sandbox_executor}.py` + `harness/memory_rag/{rag_evaluator,turbovec_adapter}.py` + `action_first_instruction` + SDD en SPE | Propietario: @coordinator | Fecha: 2026-09-08

## Contexto
Dump `01_search_frontier/Search 9-13-2026.md` (34KB): auditoría SWARMIND + turbovec (Rust TurboQuant: 10M docs en ~4GB, ingesta online, crash-safe, allowlists) + .md de patrones (context-mode 315KB→5KB, docs vivas specs-first, cross-agent review, OpenSandbox, regla 20 preguntas, action-first i-have-adhd 40K★, KISS/"plain code may be better", K2 Horizon diferido por no verificable en Ollama Hub).

## Decisión (6 módulos, TDD, 27 tests)
1. **`tool_pruner`** (A): allowed_tools ≤4 por keywords ES/EN antes del parallel_executor (80%→100% éxito, tokens/2, 724s→141s).
2. **`cross_review`** (C): revisor de familia DISTINTA (mapa claude/gpt/ollama), prefiere local (0 cloud); `KeyError`→ no auto-revisión.
3. **`rag_evaluator`** (E): 20 preguntas fijas del dominio; clasifica RETRIEVAL/MODEL_IGNORED/WRONG_TOOL; solo añade complejidad si el fallo lo justifica.
4. **`action_first_instruction`** (F): 1ª línea = acción, ≤5 pasos, 0 relleno; integrable como `instruction=` del enforcer.
5. **`sandbox_executor`** (D mínimo): docker si existe (env inyectado en runtime, nunca en contexto), subprocess+timeout si no; nunca lanza.
6. **`turbovec_adapter`** (Fase 2 mínima): graceful sin binario; `filter_allowlist` usable ya (documentación viva por paths recientes).
7. **SDD en SPE**: ciclo Spec→Test→Code del atdd-spec con contratos (`skill_contract.py`, ADR-0048) — nunca código sin contrato.

TDD: 27 tests; ruff 0; mutante cross-review muerto.

## Consecuencias
### Positivas
- Foco por poda (menos herramientas = menos distracción del modelo).
- Revisiones con perspectiva distinta + preferencia local.
- RAG auditado con oráculo barato antes de complejizarlo.
- SDD explícito en principios (ya vivía en código/skill, ahora es contrato).

### Negativas
- turbovec sin binario = no-op (experimental documentado).
- Sandbox subprocess no aísla red/FS (Docker sí); suficiente para tests, no para código hostil.

## Alternatives Considered
1. **TurboVecAdapter completo con ingesta**: requiere binario + corpus; el adapter graceful + allowlist cubre el 80%.
2. **Docker obligatorio**: rompe Windows sin Docker Desktop; el fallback lo evita.
3. **20 preguntas con LLM-judge**: overkill; clasificación léxica basta para el gate.

## Relacionado
- ADR-0048 (SDD/skill_contract), ADR-0073 (enforcer), SPE/ERR, Search 9-13-2026.md
