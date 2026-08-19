<!-- GENERADO POR scripts/gen_docs_api.py — NO editar a mano. Regenerar con `python scripts/gen_docs_api.py`. -->

# API — `harness.memory_rag.doc_ingester`

Document chunker and ingester for RAG pipelines.

## `Chunk`

Chunk.

### `to\_metadata() -> dict[str, Any]`

To metadata.

## `DocumentChunker`

Splits text files into overlapping chunks of configurable size.

### `chunk\_file(filepath: str) -> list[Chunk]`

Read a file and split it into chunks.

### `chunk\_and\_vectorize(filepath: str) -> list[Chunk]`

Chunk a file and compute embeddings for each chunk.

### `ingest\_directory(store, root\_dirs: list[str], chunker: DocumentChunker \| None = None) -> dict[str, int]`

Ingest all .md and .py files from directories into rag\_chunks.

### `ingest\_project\_directory(directory: str, extensions: set \| None = None, exclude\_dirs: set \| None = None, chunk\_size: int = 25, overlap: int = 3, show\_progress: bool = True, include\_docs: bool = False) -> dict[str, Any]`

High-level convenience: scan \*directory\* recursively, chunk every
