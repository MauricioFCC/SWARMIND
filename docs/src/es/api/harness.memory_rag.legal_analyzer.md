<!-- GENERADO POR scripts/gen_docs_api.py — NO editar a mano. Regenerar con `python scripts/gen_docs_api.py`. -->

# API — `harness.memory_rag.legal_analyzer`

Legal Analyzer — NLP juridico avanzado para documentos legales colombianos.

## `LegalEntity`

Entidad juridica extraida de un documento.

## `Argument`

Argumento juridico extraido.

## `LegalDocument`

Documento legal analizado.

## `LegalAnalyzer`

Analizador de documentos legales con tecnicas NLP 2026.

### `extract\_entities(text: str) -> list[LegalEntity]`

Extraer entidades juridicas de un texto.

### `extract\_arguments(text: str) -> list[Argument]`

Extraer argumentos juridicos (ratio decidendi, obiter dicta).

### `summarize(text: str, max\_length: int = 500) -> str`

Generar resumen de un documento legal.

### `classify\_document(text: str) -> str`

Clasificar tipo de documento legal.

### `compare\_documents(doc1: str, doc2: str) -> dict[str, Any]`

Comparar dos documentos legales.
