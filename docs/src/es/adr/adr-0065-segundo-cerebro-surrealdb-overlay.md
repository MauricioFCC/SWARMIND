# ADR 0065: Segundo Cerebro — Overlay Grafo SurrealDB + Captura Híbrida Local/Nube

## Estado
Propuesto | Spike, no migrar LanceDB | Propietario: @coordinator | Fecha: 2026-09-06

## Contexto
`docs/src/es/roadmap/estado.md` declara GraphRAG CUBIERTO (`knowledge_graph.py` + TokenBudgetRouter PageRank+TF-IDF, pipeline LLM entidades = YAGNI) y Agentic RAG CUBIERTO (orchestrator). El diseño **Segundo Cerebro Aumentado v2.0** (`01_search_frontier/Segundo_cerebro.md`, 122 líneas) aporta un delta no cubierto:

1. **SurrealDB multimodelo** (documento + grafo + vectorial + KV en un solo motor): guarda texto, embedding y relaciones (`Nota_A -> SE_RELACIONA_CON -> Nota_B`) con **GraphRAG nativo + hybrid search vector+BM25+grafo en una sola query**. LanceDB + SQLite-vec actuales exigen dos motores.
2. **Arquitectura híbrida local/nube**: Qwen 2.5 7B/14B Q4_K_M local (OpenVINO/Metal/MLX, function-calling, español) para búsqueda rápida, preguntas Cornell y enlace de Zettels; nube (Claude/Gemini/GPT) **solo** para pesado (paper 40 págs, esquema comparativo).
3. **Captura Telegram + Whisper local** con iteración proactiva (el cerebro te habla a las 2h con conexiones nuevas).
4. **Fusión Cornell + Zettelkasten automatizada**: Cornell (Cues/Notas/Resumen 3 líneas) para ingesta, Zettels atómicos + enlaces bidireccionales Obsidian para iteración.
5. Papers base 2024-2025: GraphRAG Microsoft, PKG Survey, Toolformer, Speculative Decoding, Hybrid Search.

## Decisión
**Spike opcional, sin migración**: `harness/memory_rag/graph_overlay.py` (Protocolo + adapter SurrealDB lazy) como overlay de relaciones sobre LanceDB (que sigue SSOT). Reglas:

1. LanceDB sigue default; SurrealDB solo aristas `SE_RELACIONA_CON` + metadatos Cornell/Zettel.
2. Router híbrido: local-first (Qwen/Ollama 4-tier existente) → nube solo si `is_heavy()` (doc >20 págs o síntesis multi-fuente).
3. Ingesta voz/texto con formato Cornell obligatorio (Cues/Notas/Resumen).
4. `docker run --rm -p 8000:8000 surrealdb/surrealdb:latest start` como entorno spike; sin dependencia dura en `pyproject.toml`.

## Consecuencias
### Positivas
- Relaciones consultables en una query (hoy dos motores + join manual).
- Soberanía datos + costo: local 24/7 barato, nube solo pesado.
- Reutiliza delegación Ollama 4-tier (2026-08-14) y `doc_converter.py` anydoc.

### Negativas
- Motor extra (Docker) solo para spike; riesgo sync LanceDB↔SurrealDB.
- Whisper/Telegram fuera del harness (superficie nueva).

## Alternatives Considered
1. **Migrar todo a SurrealDB**: rompe SSOT Memory_Proyects + 7.5GB ya deduplicados; viola IDP.
2. **Quedarse solo LanceDB**: relaciones como metadatos planos, sin recorrido grafo.
3. **Qdrant/ChromaDB**: un solo modelo (vectorial), no cierran el gap multimodelo.

## Relacionado
- ADR 0025 (federated vector + SQLite-vec), ADR 0050 (capa semántica), roadmap estado 2026-08-18 (GraphRAG CUBIERTO parcial)
- `01_search_frontier/Segundo_cerebro.md` + GraphRAG Microsoft 2024, PKG Survey 2024
