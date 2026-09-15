# ADR 0084: Ratio Local ≥60% — Draft-Review + Supervisión Cloud como Guía

## Estado
Aplicado | `harness/model_router/{draft_review,local_policy}.py` + `harness/orchestrator/local_supervisor.py` + sección `local_first:` en YAML | Propietario: @coordinator | Fecha: 2026-09-08

## Contexto
Objetivo del usuario: ≥60% de uso de LLMs locales destilados (potentes, ahorro de tokens), con supervisión cloud como guía (más cómputo bruto) sin perder calidad. Research frontera (sep-2026):
- **RLM-Cascade** (arXiv:2606.22840): proxy con speculative decoding a nivel respuesta — draft local + verify cloud (acepta/mejora/bypass según router): **88.8% draft-use, −45.8% costo, 1.83× speedup, 100% vs 95% calidad** en workload agéntico real (Claude Code).
- **Local-Splitter** (abr-2026, 7 tácticas): T1+T2 (routing local + compresión) = **45–79% ahorro**; T4 draft-review = 51% en RAG-heavy; margen de confianza contra falsos positivos (trivial mal clasificado degrada calidad).
- **UCCI** (arXiv:2605.18796): cascada calibrada (incertidumbre→probabilidad de error vía isotonic regression): **−31% costo** a F1=0.91; thresholds sin calibrar requieren tuning por workload.

## Decisión
1. **`DraftReviewer`** (3 paths): SKIPPED (trivial+confiado: 0 tokens cloud) → VERIFY (medio: cloud acepta con ~150 tokens) → ENHANCE (duro o poca confianza: cloud parchea). El cloud supervisa/edita, no redacta (output tokens caros).
2. **`LocalSupervisor`**: audita `sample_rate` (default 0.10) de salidas locales con juez cloud y alimenta `CompetenceModel.update` — cierra el loop local→evidencia→routing (los destilados mejoran su posterior con veredictos reales).
3. **Sin hardcode**: `local_first:` en `ollama_models.yaml` (`target_local_ratio: 0.60`, `confidence_margin: 0.50`, `sample_rate: 0.10`) + overrides `SWARMIND_LOCAL_*` + defaults seguros; loader con parser mínimo sin dependencias.
4. Ruta al 60%: triviales SKIPPED (LocalExecutor ya) + medios VERIFY + duros ENHANCE + muestreo 10% que calibra; el ratio se mide con `local_tasks/cloud_tasks` del executor.

TDD: 15 tests; ruff 0; mutante del margen muerto.

## Consecuencias
### Positivas
- Camino medible al ≥60% local con calidad acotada por verificación (no por esperanza).
- Supervisión barata: 10% auditado calibra el 100% vía competence.
- Operable sin editar código (YAML + entorno).

### Negativas
- VERIFY/ENHANCE aún no enchufados a proveedores reales (fns inyectadas; wiring como ADR-0075).
- `VERIFY_ACCEPT_TOKENS=150` es estimación (calibrar con telemetría real).

## Alternatives Considered
1. **Todo local sin supervisión**: Local-Splitter demuestra degradación por falsos positivos; el margen + muestreo lo contienen.
2. **Cascada UCCI completa**: requiere calibración isotónica con datos de producción; el margen fijo es el primer paso honesto.
3. **GRPO/MTP/MLA propios**: nivel entrenamiento/serving; somos consumidores (documentado en ADR-0078).

## Relacionado
- ADR-0068 (cascada), ADR-0078 (LocalExecutor), competence_model (SkillOrchestra), RLM-Cascade/Local-Splitter/UCCI
