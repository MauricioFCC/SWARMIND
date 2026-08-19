<!-- GENERADO POR scripts/gen_docs_api.py — NO editar a mano. Regenerar con `python scripts/gen_docs_api.py`. -->

# API — `harness.memory_rag.corrective_retriever`

corrective\_retriever.py — CRAG: validacion de recuperacion previa a generacion.

## `RetrievalSource(Protocol)`

Contrato de una fuente de recuperacion (vector, fts, hibrido).

### `retrieve(query: str, top\_k: int = 5) -> list[dict[str, Any]]`

_Sin docstring._

## `CorrectiveResult`

Resultado de la recuperacion correctiva.

## `CorrectiveRetriever`

Retriever correctivo que valida y corrige la recuperacion.

### `retrieve(query: str, top\_k: int = 5) -> CorrectiveResult`

Recupera validando calidad y aplicando correcciones si es pobre.
