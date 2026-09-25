<!-- GENERADO POR scripts/gen_docs_api.py — NO editar a mano. Regenerar con `python scripts/gen_docs_api.py`. -->

# API — `harness.memory_rag.hybrid_retriever`

hybrid\_retriever.py — RAG hibrido: fusion RRF de vector denso + BM25 disperso.

## `HybridResult`

Resultado fusionado de la busqueda hibrida.

## `HybridRetriever`

Retriever hibrido que fusiona vector denso y BM25 disperso con RRF.

### `retrieve(query: str, top\_k: int = 5) -> list[HybridResult]`

Recupera documentos fusionando rankings denso y disperso (RRF).
