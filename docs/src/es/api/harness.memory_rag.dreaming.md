<!-- GENERADO POR scripts/gen_docs_api.py — NO editar a mano. Regenerar con `python scripts/gen_docs_api.py`. -->

# API — `harness.memory_rag.dreaming`

DreamingConsolidator — Dreaming-lite (ADR-0034).

### `jaccard\_similarity(a: str, b: str) -> float`

Similitud de Jaccard entre dos textos (conjunto de palabras).

## `ConsolidationResult`

Resultado de una consolidación.

## `DreamingConsolidator`

Consolida entradas de memoria (dedup + stale + compactación).

### `consolidate(entries: list[dict]) -> ConsolidationResult`

Consolida una lista de entradas sin mutar el input.

### `consolidate\_dir(source: str \| Path, dest: str \| Path \| None = None) -> ConsolidationResult`

Consolida todos los JSON de un directorio y escribe el resultado.
