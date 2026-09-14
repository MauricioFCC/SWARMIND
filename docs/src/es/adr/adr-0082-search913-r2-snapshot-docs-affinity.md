# ADR 0082: Search 9-13 R2 — Snapshot 5KB, Docs-Gate, Affinity Wiring, 7 Dimensiones

## Estado
Aplicado | `harness/memory_rag/session_snapshot.py` + `harness/validation/docs_gate.py` + affinity en `ModelRouter` + 7D en business-strategy | Propietario: @coordinator | Fecha: 2026-09-08

## Contexto
Segunda revision minuciosa de `Search 9-13-2026.md`: lo que quedo sin implementar del primer pase (ADR-0081) + research frontera (Scroll arXiv:2608.21690 — estado fuera del contexto, working view acotada; ACM — manage_context con offload a disco + query_memory).

## Decisión (4 deltas, TDD, 11 tests)
1. **`session_snapshot`**: `SessionSnapshotter.save(state)` → JSON en disco + vista esencial ≤5KB (tarea + últimos 5 turnos + 10 hechos + handle); `restore(handle)` byte-exacto; `save_snapshot()` atajo. (Scroll/ACM + context-mode 315KB→5KB.)
2. **`docs_gate`**: `check_docs_fresh(repo)` — Fase 2: PLAN.md/AGENTS.md/SPECS.md/ARCHITECTURE.md/ADR/adr/docs/specs/CLAUDE.md modificados en working tree → PASS; solo código → FAIL listando; fuera de repo git → SKIP pass. Mutante del gate muerto.
3. **Affinity wiring**: `ModelRouter.attach_affinity()` + `route(..., session_id=)` — 2ª tarea de la sesión reusa sin re-decidir (resultado completo cacheado por sesión); sin affinity el comportamiento no cambia (compat, tests viejos verdes).
4. **7 dimensiones IA** en business-strategy (Ambición, Casos/valor, Datos, Tecnología, Modelo operativo, Personas/cultura, Gobernanza/riesgos).
5. **K2 Horizon evaluado**: no instalado en Ollama local ni verificado en el Hub → diferido con causa (no se configura lo que no se puede probar; re-evaluar cuando haya peso en el hub).

TDD: 11 tests; ruff 0.

## Consecuencias
### Positivas
- Snapshot lossless fuera del contexto (la compaction ya no decide a ciegas).
- Docs vivas con gate ejecutable (no solo intención).
- La afinidad SAAR por fin corre en el router real (antes sin callers).

### Negativas
- Snapshots en tmp por defecto (GC pendiente, como ArtifactStore).
- docs_gate depende de git CLI (fuera de repos → SKIP, correcto).

## Alternatives Considered
1. **Ingesta turbovec completa**: requiere binario; el adapter graceful + allowlist ya cubre (ADR-0081).
2. **K2 como tier ya**: sin peso verificable no se configura (FRS: verificar antes).
3. **Affinity siempre-on**: rompería tests viejos y callers sin sesión; opt-in por DI.

## Relacionado
- ADR-0081 (Search 9-13 R1), ADR-0073 (session_affinity), ADR-0070 (reanchor), Scroll/ACM 2026
