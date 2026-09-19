# ADR 0093: OTP Lite — Bulkhead + Backpressure + Watchdog (Mesa 2/3)

## Estado
Aplicado | `harness/orchestrator/bounded_executor.py` (7 tests) | Propietario: @coordinator | Fecha: 2026-09-08

## Contexto
Research OTP (supervision trees, restart one-for-one/all, bulkhead, backpressure, let-it-crash, budgets) + mesa adversarial (2/3: B+D+C-lite ahora; A/E diferidos hasta multiprocess real). El harness ya tiene retry+backoff, circuit breaker, sandbox, IdempotencyGuard, WAL y failure registry.

## Decisión
**`BoundedParallelExecutor`**: pool por dominio (bulkhead) + `Queue(maxsize)` con shed policies (drop-newest/oldest + log, nunca OOM silencioso) + deadline por tarea (watchdog: detecta hangs que CB/retry no ven; hilo daemon, no bloquea) + métricas (`executed/shed/timeouts`) para tunear vía failure-registry. Mismas primitivas (Semaphore+Queue+wait_for), ~130 LOC con docstrings, sin procesos OTP (GIL/threads bastan con idempotencia+WAL). Métricas 30d: 0 OOM fan-out, shed-rate<2%.

TDD: 7 tests; ruff 0; vulture 0; mutante de cotas muerto.

## Consecuencias
### Positivas
- Fan-out acotado (thunder-herd/OOM imposible por diseño).
- Timeouts medidos (no solo reintentados).

### Negativas
- Shed descarta trabajo real (mitigado: log + métrica + tuning).
- Sin restart automático (diferido a supervision tree con multiprocess).

## Alternatives Considered
1. **Supervision tree full (A)**: exige multiprocessing/actor-lib en Python; duplica sandbox+retry; diferido.
2. **Error kernel (E)**: refactorizar núcleo vs resto; vago y costoso; diferido.
3. **Cola infinita + hope**: OOM en fan-out (lo que se evita).

## Relacionado
- ADR-0075 (fanout_gate), IdempotencyGuard, WAL, failure_registry
