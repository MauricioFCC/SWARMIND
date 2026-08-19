<!-- GENERADO POR scripts/gen_docs_api.py — NO editar a mano. Regenerar con `python scripts/gen_docs_api.py`. -->

# API — `harness.memory_rag.doc_converter`

Conversion de documentos binarios a Markdown para el pipeline RAG.

## `DocumentConversionError(RuntimeError)`

Error al convertir un documento binario a Markdown.

## `DocumentConverter(Protocol)`

Contrato de conversion de documentos binarios a texto Markdown.

### `convert(path: Path) -> str`

Convierte el archivo en \*path\* a Markdown.

## `AnyDocConverter`

Implementacion real basada en ``firecrawl-anydoc`` (import lazy).

### `is\_available() -> bool`

Indica si el modulo ``anydoc`` esta instalado en el entorno.

### `convert(path: Path) -> str`

Convierte un documento binario a Markdown con ``anydoc.to\_markdown``.
