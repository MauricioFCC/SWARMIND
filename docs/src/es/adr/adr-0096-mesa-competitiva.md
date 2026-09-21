# ADR 0096: Mesa Competitiva — Timeout Dual, Reasoning 5º Pilar, Math-Gate

## Estado
Aplicado | timeout en `dual_verify` + `check_reasoning` + `math_gate.py` | Propietario: @coordinator | Fecha: 2026-09-08

## Contexto
Mesa adversarial (atacante/steelman/juez) sobre lo implementado: 13 gaps, veredicto de implementar timeout anti-hang, reasoning auditable y micro-gate math; diferir telemetría OTLP y GRPO-lite (infra mayor). Research: Qwen3-4B-Thinking 81.30 AIME, MATH-500, LemmaBench live, LiveCodeBench rolling, CoT −9.2pp.

## Decisión
1. **`timeout_s` en `dual_verify`** (y `_safe_brute`): ThreadPool 1 hilo + `shutdown(wait=False)` (el `with` esperaba sleeps de 30s: 60s por test); timeout → mismatch con "timeout" en el mensaje.
2. **`check_reasoning`**: 5º pilar OPCIONAL (verdict + pasos numerados; no rompe `check_spec`).
3. **`math_gate`**: 20 casos exactos deterministas (sin LLM-judge); score + wrong indexados.
4. Mutante de shutdown (wait True/False) declarado no-matable por diseño (propiedad de performance, no de corrección; cubierto por review).

TDD: 10 tests; ruff 0 (DTZ011 corregido con `now(UTC)`).

## Consecuencias
### Positivas
- Ni fast ni brute pueden colgar el guardian (lo primero que rompía en prod).
- R1 auditable sin romper el gate de 4 pilares.
- Math con oráculo exacto (sin GSM8K contaminado).

### Negativas
- Hilos daemon colgados hasta 30s en background (aceptable: no bloquean).
- Micro-gate de 20 casos no sustituye MATH-500 real (smoke, no certificación).

## Alternatives Considered
1. **multiprocessing con kill**: mata el hang de verdad pero pickling de callables arbitrarios falla; threads bastan.
2. **Hacer reasoning obligatorio**: rompería `check_spec` existente; opcional es compatible.
3. **LLM-judge para math**: -9.2pp y costo; exact-match es determinista.

## Relacionado
- ADR-0080 (dual_verify), CPD, LemmaBench/LiveCodeBench
