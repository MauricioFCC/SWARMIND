<!-- GENERADO POR scripts/gen_docs_api.py — NO editar a mano. Regenerar con `python scripts/gen_docs_api.py`. -->

# API — `harness.memory_rag.prompt_cache_builder`

Prompt Cache Builder — Construye prompts optimizados para cache de proveedores LLM.

## `CacheSection`

A section of the prompt with cache awareness.

## `PromptCacheBuilder`

Construye prompts optimizados para cache de LLM providers.

### `build(\*, system\_identity: str = '', system\_rules: str = '', system\_guardrails: str = '', tool\_definitions: str = '', output\_schema: str = '', skill\_catalog: str = '', user\_message: str = '', rag\_context: str = '', conversation\_history: str = '', loaded\_skills: str = '', session\_context: str = '', tool\_outputs: str = '', \*\*extra\_sections: str) -> str`

Build a cache-optimized prompt.

### `build\_chat\_messages(system\_content: str, messages: list[dict[str, str]], cache\_system: bool = True) -> list[dict[str, Any]]`

Build cache-optimized chat messages for chat-style APIs.

### `estimate\_cache\_savings(prompt: str, num\_calls: int = 100) -> dict[str, Any]`

Estimate token savings from prompt caching.

### `optimize\_for\_caching(prompt: str) -> str`

Reorganize an existing prompt for better cache performance.

### `get\_stats() -> dict[str, Any]`

Return builder statistics.
