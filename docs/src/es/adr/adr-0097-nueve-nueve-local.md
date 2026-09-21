# ADR 0097: 99% Local + Oráculo Cloud 1% — Recableo a 4 Destilados Instalados

## Estado
Aplicado | tiers/modelos a instalados + `local_first: 0.99/0.01` + opencode.json 4 modelos | Propietario: @coordinator | Fecha: 2026-09-08

## Contexto
Auditoría Ollama: 8 tags = 4 modelos únicos (Qwen3.8, Qwopus-coder, GLM-Z1, MiniCPM5); 9 configurados ausentes (LFM2.5, OLMoE, llama3.2, qwen3:4b, deepseek-r1, qwen2.5-coder×2, qwen3-vl, Qwen3.5-flash). Config con modelos ausentes = selección rota + default caído.

## Decisión
1. **Tiers a instalados**: fast→MiniCPM5, quality→Qwen3.8, coding→Qwopus (embedding/vision mantienen nombre, pendientes de pull).
2. **opencode.json**: default Qwen3.8 + 4 modelos (qwen3-vl removido: ausente).
3. **Política 99%/1%**: `local_first` (0.99/0.50/0.01) + defaults de código alineados; oráculo cloud = `sample_rate: 0.01`.
4. Verificación: **19/20 = 95% local** (el restante es planning-frontier por diseño).

TDD: suites verdes (64 passed); ruff 0.

## Consecuencias
### Positivas
- Cero referencias a modelos fantasma; default siempre resuelve.
- Oráculo barato: 1% audita, 99% ejecuta local.

### Negativas
- Sin embedding/vision locales hasta pull (RAG multimodal degradado a texto).

## Alternatives Considered
1. **Mantener 13 modelos listados**: UX rota (errores al seleccionar ausentes).
2. **Descargar los 9 ahora**: ~40GB sin necesidad inmediata; a demanda.

## Relacionado
- ADR-0069/0078/0084/0092, `ollama_local.yaml` (gitignored)
