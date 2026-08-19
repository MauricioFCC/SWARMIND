<!-- GENERADO POR scripts/gen_docs_api.py — NO editar a mano. Regenerar con `python scripts/gen_docs_api.py`. -->

# API — `harness.gpu_accel`

GPU Acceleration Module — Swarmind Harness

### `force\_cpu() -> None`

Forzar uso de CPU incluso si hay GPU disponible.

### `force\_gpu() -> None`

Forzar uso de GPU si esta disponible.

### `to\_gpu(data: Any) -> Any`

Transferir datos a GPU si esta disponible.

### `to\_cpu(data: Any) -> np.ndarray \| Any`

Transferir datos de GPU a CPU como numpy array.

### `get\_device\_info() -> dict[str, Any]`

Informacion estandar del dispositivo de aceleracion (health-check).

### `cosine\_similarity(a: np.ndarray, b: np.ndarray) -> float`

Similitud coseno entre dos vectores (GPU acelerada si disponible).

### `cosine\_similarity\_batch(query: np.ndarray, candidates: np.ndarray) -> np.ndarray`

Similitud coseno batch (query vs multiples candidatos) en GPU.

### `normalize(vectors: np.ndarray) -> np.ndarray`

Normalizar vectores L2 en GPU.

### `zeros(dim: int, dtype: Any = np.float32, on\_gpu: bool = False) -> np.ndarray \| Any`

Crear vector de zeros (en GPU si disponible y on\_gpu=True).

## `GPUContext`

Context manager para operaciones GPU con fallback automatico a CPU.

### `clear\_cache() -> None`

Limpiar cache de GPU.

### `get\_memory\_info() -> dict`

Informacion de uso de memoria GPU.
