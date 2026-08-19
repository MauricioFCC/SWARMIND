<!-- GENERADO POR scripts/gen_docs_api.py — NO editar a mano. Regenerar con `python scripts/gen_docs_api.py`. -->

# API — `harness.gpu_optimize`

GPU Optimization Module — Swarmind Acceleration Engine.

### `gpu\_embedding(text: str, texts: list[str] \| None = None, dim: int = 384) -> np.ndarray`

Generación de embeddings acelerada por GPU.

### `gpu\_similarity\_search(query: np.ndarray, candidates: np.ndarray, top\_k: int = 5, threshold: float = 0.0, min\_gpu\_size: int = 10000) -> list[tuple[int, float]]`

Búsqueda por similitud coseno con enrutamiento inteligente CPU/GPU.

### `batch\_embed\_messages(messages: list[str], dim: int = 384) -> np.ndarray`

Generar embeddings para múltiples mensajes en batch (GPU si disponible).

### `gpu\_self\_test() -> dict`

Ejecutar autodiagnóstico GPU y retornar métricas de rendimiento.
