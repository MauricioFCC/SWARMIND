# ADR 0069: Tier CODING en OllamaTierRouter — Routing Local para Código con Precedencia

## Estado
Aplicado | `harness/model_router/ollama_tiers.py` + `ollama_models.yaml` | Propietario: @coordinator | Fecha: 2026-09-06

## Contexto
El `OllamaTierRouter` (ADR-0057 relacionado, roadmap 2026-08-14) delega tareas a modelos locales por capacidad con 4 tiers: FAST (qwen3:4b), QUALITY (deepseek-r1:8b), EMBEDDING (qwen3-embedding:0.6b), VISION (qwen3-vl:4b). El heurístico de keywords evaluaba en orden EMBEDDING → VISION → QUALITY → FAST.

Gap identificado: **tareas de código** (`write a pytest test`, `debug the endpoint`, `refactor module`) caían en QUALITY (por "write"/"fix") y usaban `deepseek-r1:8b` (razonamiento general) en vez de un modelo especializado en código. `qwen2.5-coder:7b` (instalado desde 2026-08-14, roadmap "final") estaba configurado en YAML pero **no mapeado en código** ni en el orden de evaluación.

## Decisión
Añadir **tier CODING** como 5º tier con precedencia sobre QUALITY:

1. **Enum + spec**: `CapabilityTier.CODING` + `OllamaTierSpec` con `qwen2.5-coder:7b`.
2. **Orden de evaluación**: EMBEDDING → VISION → **CODING** → QUALITY → FAST. CODING antes que QUALITY para ganar "write a pytest test" (ambos tienen "write", keyword de código desempata).
3. **Keywords ES/EN** (`_CODING_KEYWORDS`): compuestos y con espacio para evitar colisiones (`pytest`, `class `, `funcion`, `refactor`, `debug`, `bug`, `sql`, `query`, `endpoint`). Sin sueltos ambiguos (`test`, `api`, `script` → colisionan con `latest`, `rapid`, `description`).
4. **YAML ya existía**: `ollama_models.yaml` traía `coding:` desde 2026-08-14 — solo faltaba mapear en código.
5. **Tests TDD**: 4 tests nuevos (`test_tier_for_task_coding`, `test_tier_for_task_coding_takes_precedence_over_quality`, actualizados `test_model_for_returns_default_specs`, `test_warm_all`, `test_loaded_tiers`). 20 tests pasan.

## Consecuencias
### Positivas
- Código local usa modelo especializado (7B params, fine-tuned para coding) → mejor calidad, mismos tokens cloud (0).
- Precedencia explícita y testeada: `write a pytest test` → CODING; `write an essay` → QUALITY.
- `check_ollama.py` fix real: `logger.info()` sin args lanzaba `TypeError` — cambiado a `logger.info("")` + `basicConfig`.

### Negativas
- Heurística substring tiene edge cases menores (`fix the essay` → CODING por "fix"); riesgo aceptable y documentado.
- Orden de inserción en dict define precedencia (Python 3.7+); `_TIER_KEYWORDS` construye el dict en el orden correcto (verificado en tests).

## Alternatives Considered
1. **Sin tier CODING**: código seguía en QUALITY (`deepseek-r1:8b`) — probado peor en generación de tests/refactor.
2. **CODING al final (tras QUALITY)**: perdía precedencia; `write a pytest test` → QUALITY.
3. **Keywords sueltas (`test`, `api`)**: colisiones probadas reales; rechazado.

## Relacionado
- Roadmap 2026-08-14: "Delegacion local Ollama 4-tier" y "Delegacion local Ollama - final" (ya listaban `qwen2.5-coder:7b` en YAML).
- ADR-0057: Harnessed Agentic RL (usa `model_router/` como endpoint).
- `harness/tests/test_ollama_tiers.py`: 20 tests (4 nuevos para CODING).
- `ollama_models.yaml`: SSOT de modelos por tier.