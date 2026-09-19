# ADR 0092: Ratio Local ≥60% — Capability Profiles + YAML Confidencial (Mesa 2-1)

## Estado
Aplicado | `harness/model_router/capability_profiles.py` + `ollama_local.yaml` (gitignored) + `ollama_local.example.yaml` | Propietario: @coordinator | Fecha: 2026-09-08

## Contexto
Objetivo del usuario: ≥60% de uso local con destilados potentes (ahorro tokens), administrados por capacidades, clasificados por necesidad/tarea, configurados en YAML no-commiteable. Research (MiniCPM-SALA 0.951 HumanEval, Qwen reports, LXT: solo 4/15 benchmarks predicen prod, LiveBench/AA como referencia) + mesa adversarial (2-1: híbrido — perfiles estáticos + calibración online + fallback congelado; disenso: deriva si el supervisor cae).

## Decisión
1. **`capability_profiles`**: 13 perfiles builtin (coding/reasoning/math/multilingual/agentic/vision 0..1 desde benchmarks + trust) + `classify_task` (keywords <5ms) + `route_by_capability` (score = dot×trust normalizado por match perfecto; conf ≥0.65 → local).
2. **`ollama_local.yaml` gitignored** (+ `.gitignore`) con plantilla versionada (`.example.yaml`): overrides de caps/trust por model_id + `local_first` sin tocar el repo.
3. **Verificación**: simulación 20 tareas → **19/20 = 95% local** (solo diseno/planning profundo a cloud), supervisión 10%, mejor modelo por función (codigo→Qwopus, diseno→GLM, vision→qwen3-vl).

TDD: 8 tests; ruff 0.

## Consecuencias
### Positivas
- Clasificación universal por necesidad (no por tier fijo).
- Tuning privado sin contaminar el repo (ejemplo versionado como contrato).
- Calibración online lista (veredictos → trust EWMA).

### Negativas
- Priors por benchmark ≠ Ollama local quantizado (el trust los corrige con evidencia).
- Keywords ES/EN (frágiles ante jerga; el supervisor las compensa).

## Alternatives Considered
1. **Micro-benchmark al arranque**: +30-90s boot × 14 modelos, overfit a prompt toy.
2. **Solo tiers fijos**: no distingue calidades dentro del tier (Qwopus vs LFM para código).
3. **Comandos `overlay`/`dashboard` CLI**: YAGNI (API Python + YAML bastan).

## Relacionado
- ADR-0068/0069/0078/0084 (routing, tiers, local-first), competence_model, MiniCPM-SALA/Qwen reports
