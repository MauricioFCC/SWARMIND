<!-- GENERADO POR scripts/gen_docs_api.py — NO editar a mano. Regenerar con `python scripts/gen_docs_api.py`. -->

# API — `harness.memory_rag.trajectory_compressor`

Trajectory Compressor — Hermes-inspired conversation compression + SelfCompact.

## `TrajectoryCompressor`

Comprime trayectorias de conversacion multi-turno.

### `compress(conversation: list[dict[str, Any]], target\_tokens: int \| None = None, phase: str \| None = None) -> list[dict[str, Any]]`

Comprime una trayectoria de conversacion.

### `get\_stats() -> dict[str, Any]`

Return compressor statistics.

### `get\_compact\_rubric() -> str`

Retorna un prompt/rubric ligero para que el LLM decida si compactar.

### `mark\_trajectory\_phase(phase: str) -> None`

Marca la fase actual de la trayectoria para decisiones de compactacion.

### `should\_compact(phase: str, context\_usage\_pct: float, turn\_count: int) -> bool`

Implementa la logica del rubric Self-Compact.

### `compress\_conversation(conversation: list[dict[str, Any]], target\_tokens: int \| None = None, phase: str \| None = None) -> list[dict[str, Any]]`

Comprime una conversacion multi-turno (funcion de conveniencia).
