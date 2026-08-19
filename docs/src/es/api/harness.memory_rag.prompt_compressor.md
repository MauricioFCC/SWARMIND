<!-- GENERADO POR scripts/gen_docs_api.py — NO editar a mano. Regenerar con `python scripts/gen_docs_api.py`. -->

# API — `harness.memory_rag.prompt_compressor`

PromptCompressor — Core orchestration of prompt compression.

## `PromptCompressor(CompressionStrategies)`

Motor de compresion de prompts multi-estrategia.

### `compress(text: str, target\_ratio: float \| None = None, method: str = 'auto') -> CompressionResult`

Comprime un texto usando la mejor estrategia disponible.

### `extractive\_compress(text: str, ratio: float = 0.5) -> str`

Compresion extractiva: elimina redundancia preservando informacion.

### `abstractive\_compress(text: str, ratio: float = 0.5) -> str`

Compresion abstractiva: resume secciones preservando informacion clave.

### `compress\_system\_prompt(prompt: str, max\_tokens: int = 1500) -> str`

Comprime un system prompt preservando reglas y rol.

### `compress\_conversation(messages: list[dict[str, str]], max\_tokens: int = 4000, preserve\_system: bool = True) -> list[dict[str, str]]`

Comprime una conversacion multi-turno.

### `allocate\_budget(sections: dict[str, str], total\_tokens: int) -> TokenBudget`

Asigna presupuesto de tokens entre secciones.

### `get\_stats() -> dict[str, int]`

Retorna estadisticas de compresion.

### `clear\_cache() -> int`

Limpia el cache interno.
