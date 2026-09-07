# ADR 0070: Re-Anclaje Post-Compaction + Taxonomía de Principios + Fundamentos de Competición

## Estado
Aplicado | `harness/memory_rag/reanchor.py` + `base_principles.md` v3.0.0 | Propietario: @coordinator | Fecha: 2026-09-06

## Contexto
**Problema del usuario**: en sesiones largas, los agentes pierden el contexto general y dejan de aplicar los lineamientos. **Research frontera (3 tracks, sep-2026)**:

### Track 1 — Context drift (65% de los fallos)
- El 65% de fallos enterprise de agentes es context drift, NO token exhaustion (Forrester 2025).
- Los compactores retienen solo **~17%** de las restricciones inyectadas (COMPINT, arXiv); algunos rinden peor que no compactar.
- GPT-4: accuracy 98.1%→64.1% según posición en la ventana (attention valley); 2% de misalignment temprano compone 40% de fallos al final.
- Técnicas probadas: guideline re-injection condensada (NO verbatim — repetición de bloques grandes dispara attention suppression), re-anchor post-compaction (Anthropic), SC-aware extractor (>90% retención vs 17%), self-restatement cada N turnos, re-anclaje en límites de fase.

### Track 2 — Programación de competición (arXiv 2506.22954 + Wonda ICML 2026)
- Taxonomía de fallos LLM: design 28.6% + boundary 15.5% = 44% prevenible con checklist pre-código.
- Framework de reparación 3 fases: P1 diagnosticar contra taxonomía → P2 reparar anclado a categoría → P3 regenerar con info aumentada: **5/80 → 46/80 AC (9.2x)**.
- Invariantes: Best-of-N filtering; inválida se descarta, no se repara. Dual verification (vs brute-force).

### Track 3 — Adherencia de principios (IFEval/DRFR/FollowBench/SID)
- Instrucciones verificables binarias (IFEval) > aspiracionales; 1 regla = 1 criterio atómico (DRFR).
- Categorías fine-grained aíslan modos de fallo (FollowBench); densidad > detalle (AAAI 2408.08781: más palabras NO mejora).
- Compliance es pattern matching frágil (Ribeiro): re-anclar por ID, nunca parafrasear.

## Decisión
Tres decisiones coordinadas:

1. **RPA + mecanismo `reanchor.py`**: nuevo módulo `harness/memory_rag/reanchor.py` — `build_reanchor(principles, agent, skills, task)` genera bloque condensado `<<RE-ANCHOR>>` (<2000 chars) y `compact_with_reanchor()` envuelve `structured_compact` anteponiendo el bloque post-compactación. Regla behavioral **RPA** en N1: tras CADA compactación recargar N1+rol+skills+agentes. Principio de diseño: la pérdida se asume (17% retención) y se restaura determinísticamente, no se espera que el summary la preserve.

2. **Taxonomía de adherencia v3.0.0**: sección nueva en `base_principles.md` que categoriza los 36 códigos N1 en 8 categorías (PRC/ARC/QLT/SEC/DOC/CTX/GOV/SYS) marcando CHECK (verificable binario) vs GUIDE (orientativo, se cita por ID). Reglas: atomicidad (DRFR), citar por ID, densidad>detalle, self-restatement cada 10 respuestas, jerarquía formato>proceso>estilo. Los IDs existentes (RSF, ERR, ...) NO cambian (SSOT: ya viven en STANDARDS_ENCODED del context_injector).

3. **CPD — fundamentos de competición modernos**: nuevo principio N1 con el checklist pre-código (edges+invariants+BigO+constraints), repair en 3 fases, invariants verificables, dual verification. Aplicado a sistemas LLM: el checklist anti design/boundary va en el prompt, la taxonomía guía el repair de fallos de tests.

TDD: `harness/tests/test_reanchor.py` 7 tests (bloque completo/compacto, fail-fast, preservación post-compactación, SC-aware).

## Consecuencias
### Positivas
- 65% de fallos por drift atacados en la causa: el bloque N1 vuelve tras cada compactación.
- Principios citables por ID con modo de cumplimiento explícito (CHECK/GUIDE).
- 44% de fallos de código (design+boundary) prevenibles con checklist CPD.
- IDP respetado: IDs de principios estables, compactor existente reutilizado (DRY).

### Negativas
- El bloque re-anchor añade ~400-1800 chars por compactación (aceptable: <1% de una ventana típica).
- GUIDE codes (WFP, MCL, MKS, RPA) no son binario-verificables — se audituan por revisión, no por gate.

## Alternatives Considered
1. **Reinyectar AGENTS.md completo post-compactación**: rompe cache + dispara attention suppression (frontera: repetición verbatim degradá).
2. **Confiar en el summary del compactor**: retención medida 17% (COMPINT) — insuficiente.
3. **Renumerar los principios (PRC-01, ARC-02...)**: rompe STANDARDS_ENCODED/agents/skills que citan los IDs; la categoría-vía-tabla logra lo mismo sin migración.
4. **Solo regla behavioral (sin módulo)**: la regla sin mecanismo ejecutable depende de que el modelo recuerde (exactamente lo que falla); el módulo garantiza el restore.

## Relacionado
- ADR-0066 (prompt-cache TTL), ADR-0068 (cascada + cache health)
- `harness/memory_rag/reversible_compaction.py` (compactor base reutilizado)
- arXiv 2601.04170 (Agent Drift), COMPINT (17% retención), arXiv 2506.22954 (taxonomy-driven), arXiv 2510.18892 (IFEval), InFoBench (DRFR)
