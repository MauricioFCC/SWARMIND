<!-- GENERADO POR scripts/gen_docs_api.py — NO editar a mano. Regenerar con `python scripts/gen_docs_api.py`. -->

# API — `harness.memory_rag.context_compression`

context\_compression — Estrategias de compresion de ventana de contexto.

### `summarize\_conversation(self: Any, section: Any) -> bool`

Summarize conversation history to fit within budget.

### `compress\_tool\_outputs(self: Any, section: Any) -> bool`

Comprime tool outputs con Observation Masking primero, luego truncado legacy.

### `hard\_truncate(self: Any, window: Any) -> Any`

Last resort: hard truncate at token limit.

### `aggressive\_compress(text: str) -> str`

Compress text aggressively by removing redundant whitespace/lines.

### `summarize\_messages(messages: list[dict[str, Any]]) -> str`

Summarize a list of messages.
