# ADR 0086: Destilados Frontera + Dominio NT8/MQL5 (Search 9-13 R3)

## Estado
Aplicado | canon NT8 en `quant-trading` + alternos evaluados en YAML | Propietario: @coordinator | Fecha: 2026-09-08

## Contexto
Revisión de `01_search_frontier` (archivos nuevos desde el último pase):
- **`Los mejores modelos destilados.md`**: documenta los 7 instalados (Qwen3.8, DeepSeek-V4-Flash, GLM-Z1, MiniCPM5, Qwopus-coder, Nemotron, Phi-4-mini, LFM2.5, OLMoE) + 3 NO instalados (Qwimi3.5 Kimi+Opus, Nemotron-Cascade-8B, Phi-4-mini-flash) + arquitectura Cerebro+Secretario (ya implementada vía cascade/supervisor/LocalExecutor) + especialización financiera en System Prompt/RAG (ya: PEC + semantic RAG).
- **`configuracion NT8 con Onyx.md`**: guía NT8/NinjaTrader (Rithmic/CQG/FIX, NinjaScript C#, Strategy Analyzer). Onyx-Quan-AIBot confirma dominio activo (100 matches: Rithmic, NT8 ATI, MQL5/ONNX/DLL).
- **`Search 9-8-2026.md`**: mismo contenido que `Randon` (rtk, distributed-systems, K2, tgrep, 7 dimensiones) — ya cubierto por ADR-0076, sin duplicar.
- **Ollama Hub**: qwen3.5 oficial (0.8b–122b), gemma4 edge (e2b/e4b), kimi-k2.6/k2.7, glm-5.x, nemotron-3-nano — monitorear para edge.

## Decisión
1. **Canon NT8 en `quant-trading`**: MQL5 Docs + NinjaTrader 8 + sección `PLATAFORMAS RETAIL` (MT5 off-box, NinjaScript, Rithmic/CQG/FIX, walk-forward). Frontmatter intacto (presupuesto).
2. **Alternos documentados, no instalados**: Qwimi/Nemotron-Cascade/Phi-4-mini en YAML como pendientes (no descargar ~15GB sin aprobación); qwen3.5/gemma4/kimi como monitoreo.
3. Sin código nuevo (IDP: cascade/supervisor/LocalExecutor ya implementan Cerebro+Secretario).

## Consecuencias
### Positivas
- quant-trading cubre el stack real del usuario (CQE/Rust + MT5/MQL5 + NT8).
- Decisiones de descarga pendientes con criterio (no impulso).

### Negativas
- Los 3 destilados siguen sin probar en RTX 4060 (requieren descarga + smoke).

## Alternatives Considered
1. **Descargar ya los 3**: ~15GB sin validación previa de necesidad; el usuario actualiza Ollama cuando decide.
2. **Nueva skill nt8-trading**: el dominio cabe en quant-trading (una sección); skill nueva diluiría retrieval.

## Relacionado
- ADR-0069 (tiers), ADR-0078 (LocalExecutor), ADR-0084 (ratio local), Onyx-Quan-AIBot (dominio)
