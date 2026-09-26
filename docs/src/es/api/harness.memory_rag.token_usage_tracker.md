<!-- GENERADO POR scripts/gen_docs_api.py — NO editar a mano. Regenerar con `python scripts/gen_docs_api.py`. -->

# API — `harness.memory_rag.token_usage_tracker`

TokenUsageTracker — Medicion de tokens por agente/llamada (ADR-0041 H2).

## `UsageRecord`

Registro de una llamada LLM con desglose de tokens.

### `total() -> int`

Total de tokens de la llamada (input+output+cache\_read+cache\_write).

### `summary() -> str`

Resumen legible del registro para logs/diagnostico.

## `AgentUsageSummary`

Agregacion de uso de tokens para un agente.

### `summary() -> str`

Resumen legible del agregado para logs/diagnostico.

## `TokenUsageTracker`

Medidor de tokens por agente con agregacion, alertas y export.

### `record(usage: UsageRecord) -> None`

Registra una llamada LLM; descarta la mas antigua si se excede max\_records.

### `record\_from\_provider(agent: str, model: str, provider\_usage: dict[str, int]) -> None`

Registra uso directamente desde un dict de usage del provider.

### `usage\_by\_agent() -> dict[str, AgentUsageSummary]`

Agrega el uso de tokens por agente.

### `total\_tokens() -> int`

Total global de tokens consumidos (todos los registros).

### `top\_consumers(n: int = 5) -> tuple[AgentUsageSummary, ...]`

Retorna los top N agentes por total de tokens (descendente).

### `cache\_hit\_ratio(agent: str \| None = None) -> float`

Ratio de cache: cache\_read / (input + cache\_read) en [0, 1].

### `alerts(budgets: dict[str, int]) -> tuple[str, ...]`

Genera alertas para agentes que superan el umbral de su budget.

### `export() -> dict[str, Any]`

Snapshot serializable para telemetria/dashboard.
