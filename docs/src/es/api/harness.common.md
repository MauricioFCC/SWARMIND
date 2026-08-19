<!-- GENERADO POR scripts/gen_docs_api.py — NO editar a mano. Regenerar con `python scripts/gen_docs_api.py`. -->

# API — `harness.common`

Common — Shared utilities for the entire harness.

### `fallback\_embedding(text: str, dim: int = EMBEDDING\_DIM) -> np.ndarray`

Deterministic character-frequency embedding vector (vectorizado).

### `estimate\_tokens(text: str) -> int`

Token estimation: usa tiktoken si disponible, fallback a chars/4.

### `compression\_pct(before: int, after: int) -> float`

Calcula el porcentaje de compresion.

### `avg\_compression\_pct(total\_before: int, total\_saved: int) -> float`

Calcula el porcentaje de compresion promedio.

### `keyword\_match\_score(text: str, keyword\_map: dict[str, Any], default: Any = None, score\_key: str = 'score') -> tuple[Any, int]`

Matches text against a keyword map returning best match + score.

## `StatsMixin`

Mixin that adds get\_stats() with avg\_compression\_pct to any class

### `get\_stats() -> dict[str, Any]`

Return stats with avg\_compression\_pct computed.

### `truncate\_by\_budget(items: list[Any], get\_tokens: callable, budget: int, safety\_margin: float = 0.9, sort\_key: callable \| None = None, reverse: bool = True) -> list[Any]`

Truncate a list of items to fit within a token budget.
