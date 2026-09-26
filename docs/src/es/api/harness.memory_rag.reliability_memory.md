<!-- GENERADO POR scripts/gen_docs_api.py — NO editar a mano. Regenerar con `python scripts/gen_docs_api.py`. -->

# API — `harness.memory_rag.reliability_memory`

Memoria de confiabilidad online (Sigma-Mem, ADR-0039 #6, arXiv 2607.27958).

## `ReliabilityMemory`

Memoria de confiabilidad online por agente con persistencia JSON atomica.

### `record\_outcome(agent: str, task\_type: str, success: bool, meta: dict \| None = None) -> None`

Registra una evidencia de competencia (exito o fallo) para un agente.

### `get\_reliability(agent: str, task\_type: str \| None = None) -> float`

Retorna el success-rate con suavizado Laplace para un agente.

### `get\_ranked\_agents(task\_type: str \| None = None) -> list[tuple[str, float]]`

Ranking de agentes por confiabilidad, ordenado descendente.

### `get\_stats() -> dict[str, Any]`

Resumen estadistico de la memoria de confiabilidad.

### `clear() -> None`

Limpia toda la evidencia registrada y persiste el estado vacio.
