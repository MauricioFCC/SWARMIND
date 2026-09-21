# ADR 0095: Benchmarks Competitivos — Calibración Math + Freshness + Global Sincronizado

## Estado
Aplicado | calibración math en `capability_profiles` + `stale` en `dual_verify` + `opencode.jsonc` global con 13 modelos | Propietario: @coordinator | Fecha: 2026-09-08

## Contexto
Research (DataLearner 2026-07, LemmaBench arXiv:2602.24173, LiveCodeBench, FrontierMath): Qwen3-4B-Thinking 81.30 AIME2025 (thinking>size, +33.9pp vs base), Hunyuan-7B 75.30 AIME + 93.70 MATH-500, DeepSeek-R1-Distill 91.40 MATH-500, GSM8K/MATH saturados y contaminados (deprecar), lemmas live anti-contaminación, rolling+delayed-release, tools>reasoning (mejor 53% medium/0% hard sin tools), CoT zero-shot −9.2pp (prohibir CoT libre, solo ejecución vs referencia).

## Decisión
1. **Calibración math**: GLM-Z1 y Qwen3.8 `math: 0.80 → 0.85` (thinking destilados); Qwen3.5-flash queda default general.
2. **Freshness en `dual_verify`**: `as_of` ISO + `CASE_FRESHNESS_DAYS=540` → flag `stale` (backward-compatible, default False); frontera exacta testada (mutante muerto); `datetime.now(UTC)` (ruff DTZ011).
3. **Global sincronizado**: `opencode.jsonc` con los 13 modelos + default flash + reserved 2000 (estaba en 7 por sync parcial previo).
4. **GSM8K deprecado** como gate (comentario en profiles; Morandi citado como hecho histórico, intacto).

TDD: 4 tests nuevos (fresh/stale/boundary/compat); ruff 0; mutante muerto.

## Consecuencias
### Positivas
- Math local mejor ruteado (GLM/Qwen3.8 primero en math).
- Sets viejos marcados (no se confía en benchmarks contaminados).
- opencode global = repo (13 modelos, default local).

### Negativas
- `stale` es heurístico por fecha (no detecta contaminación real; LemmaBench completo queda futuro).

## Alternatives Considered
1. **LemmaBench completo local**: generar tests desde arXiv-recientes (infra mayor; diferido).
2. **Cambiar default a GLM**: flash sigue mejor generalista; el router ya dirige math a GLM.

## Relacionado
- ADR-0080 (dual_verify), capability_profiles, math-doc, LemmaBench/LiveCodeBench
