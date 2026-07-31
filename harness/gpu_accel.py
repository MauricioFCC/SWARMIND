"""
GPU Acceleration Module â€” Swarmind Harness

Provee aceleracion GPU para operaciones del sistema multi-agente.
Detecta automaticamente GPU disponible y fallback a CPU si no hay.

Operaciones aceleradas:
- Embeddings: generacion de vectores con torch
- Matrices: operaciones de algebra lineal (LanceDB usa numpy)
- Batch processing: procesamiento paralelo en GPU

Usage:
    from harness.gpu_accel import gpu, HAVE_CUDA
    
    if HAVE_CUDA:
        vector = gpu.embed(text)
        similarity = gpu.cosine_similarity(v1, v2)
"""

from __future__ import annotations

import logging
import os as _os
from pathlib import Path as _Path
from typing import Any

import numpy as np
from typing_extensions import Self

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# GPU Detection
# ---------------------------------------------------------------------------

HAVE_CUDA: bool = False      # Current state (may be overridden by force_cpu/gpu)
_HARDWARE_CUDA: bool = False  # Actual hardware capability (read-only)
DEVICE: str = "cpu"
DEVICE_NAME: str = "CPU"
GPU_MEMORY_GB: float = 0.0

# Asegurar que torch/lib con DLLs CUDA este en PATH (Windows)
_torch_lib = str(
    _Path(__file__).resolve().parent.parent / ".venv" / "Lib" / "site-packages" / "torch" / "lib"
)
if _Path(_torch_lib).is_dir() and _torch_lib not in _os.environ.get("PATH", ""):
    _os.environ["PATH"] = _torch_lib + _os.pathsep + _os.environ.get("PATH", "")

try:
    import torch
    if torch.cuda.is_available():
        HAVE_CUDA = True
        _HARDWARE_CUDA = True
        DEVICE = "cuda:0"
        DEVICE_NAME = torch.cuda.get_device_name(0)
        GPU_MEMORY_GB = torch.cuda.get_device_properties(0).total_memory / 1024**3
        logger.info(
            "GPU detected: %s (%d GB CUDA %s)",
            DEVICE_NAME, int(GPU_MEMORY_GB), torch.version.cuda,
        )
    else:
        logger.info("CUDA available but no GPU detected, using CPU")
except ImportError:
    logger.info("PyTorch not installed, using CPU")
except Exception as exc:  # noqa: BLE001
    logger.warning("GPU detection error: %s", exc)


def force_cpu() -> None:
    """Forzar uso de CPU incluso si hay GPU disponible."""
    global HAVE_CUDA, DEVICE
    HAVE_CUDA = False
    DEVICE = "cpu"
    logger.info("GPU acceleration disabled by force_cpu()")


def force_gpu() -> None:
    """Forzar uso de GPU si esta disponible."""
    global HAVE_CUDA, DEVICE
    global _HARDWARE_CUDA  # noqa: PLW0602
    if _HARDWARE_CUDA:
        HAVE_CUDA = True
        DEVICE = "cuda:0"
        logger.info("GPU acceleration enabled: %s", DEVICE_NAME)
    else:
        logger.warning("force_gpu() called but no GPU available")


# ---------------------------------------------------------------------------
# GPU-Accelerated Operations
# ---------------------------------------------------------------------------


def to_gpu(data: Any) -> Any:
    """
    Transferir datos a GPU si esta disponible (retorna numpy array siempre).

    Args:
        data: numpy array o torch tensor.

    Returns:
        numpy array (copia en GPU si disponible, CPU si no).
    """
    if not HAVE_CUDA:
        return data
    import torch
    if isinstance(data, torch.Tensor):
        return data.to(DEVICE)
    if isinstance(data, np.ndarray):
        return torch.from_numpy(data).to(DEVICE)
    return data


def to_cpu(data: Any) -> np.ndarray | Any:
    """
    Transferir datos de GPU a CPU como numpy array.

    Args:
        data: torch tensor en GPU.

    Returns:
        numpy array.
    """
    if HAVE_CUDA and hasattr(data, "cpu"):
        return data.cpu().numpy()
    return data


def cosine_similarity(
    a: np.ndarray,
    b: np.ndarray,
) -> float:
    """
    Similitud coseno entre dos vectores (GPU acelerada si disponible).

    Args:
        a: Primer vector.
        b: Segundo vector.

    Returns:
        Similitud coseno (0-1).
    """
    if HAVE_CUDA:
        import torch
        ta = torch.from_numpy(a).to(DEVICE)
        tb = torch.from_numpy(b).to(DEVICE)
        return float(torch.nn.functional.cosine_similarity(ta.unsqueeze(0), tb.unsqueeze(0)).item())
    norm = np.linalg.norm(a) * np.linalg.norm(b)
    return float(np.dot(a, b) / norm) if norm > 0 else 0.0


def cosine_similarity_batch(
    query: np.ndarray,
    candidates: np.ndarray,
) -> np.ndarray:
    """
    Similitud coseno batch (query vs multiples candidatos) en GPU.

    Args:
        query: Vector query (1D o 2D).
        candidates: Matriz de candidatos (N x D).

    Returns:
        Array de similitudes (N,).
    """
    if query.ndim == 1:
        query = query.reshape(1, -1)
    if HAVE_CUDA:
        import torch
        tq = torch.from_numpy(query).to(DEVICE)
        tc = torch.from_numpy(candidates).to(DEVICE)
        scores = torch.nn.functional.cosine_similarity(tq, tc)
        return scores.cpu().numpy()
    query_norm = np.linalg.norm(query)
    if query_norm == 0:
        return np.zeros(candidates.shape[0], dtype=np.float32)
    cand_norms = np.linalg.norm(candidates, axis=1)
    dots = np.dot(candidates, query.flatten())
    denom = cand_norms * query_norm
    return np.where(denom > 0, dots / denom, 0.0)


def normalize(vectors: np.ndarray) -> np.ndarray:
    """
    Normalizar vectores L2 en GPU.

    Args:
        vectors: Array de vectores (N x D) o vector unico (D,).

    Returns:
        Vectores normalizados.
    """
    if HAVE_CUDA:
        import torch
        tv = torch.from_numpy(vectors).to(DEVICE)
        normalized = torch.nn.functional.normalize(tv, p=2, dim=-1)
        return normalized.cpu().numpy()
    norms = np.linalg.norm(vectors, axis=-1, keepdims=True)
    return np.where(norms > 0, vectors / norms, 0.0)


def zeros(dim: int, dtype: Any = np.float32) -> np.ndarray:
    """
    Crear vector de zeros (en GPU si disponible).

    Args:
        dim: Dimension del vector.
        dtype: Tipo de dato.

    Returns:
        Vector de zeros.
    """
    if HAVE_CUDA:
        import torch
        return torch.zeros(dim, dtype=torch.float32, device=DEVICE).cpu().numpy()
    return np.zeros(dim, dtype=dtype)


# ---------------------------------------------------------------------------
# GPU Context Manager
# ---------------------------------------------------------------------------


class GPUContext:
    """
    Context manager para operaciones GPU con fallback automatico a CPU.

    Usage:
        with GPUContext() as ctx:
            if ctx.available:
                result = ctx.compute_embedding(text)
            else:
                result = cpu_compute(text)
    """

    def __init__(self) -> None:
        self.available = HAVE_CUDA
        self.device = DEVICE
        self.device_name = DEVICE_NAME

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *args: object) -> None:
        if HAVE_CUDA:
            import torch
            torch.cuda.empty_cache()

    @staticmethod
    def clear_cache() -> None:
        """Limpiar cache de GPU."""
        if HAVE_CUDA:
            import torch
            torch.cuda.empty_cache()
            logger.debug("GPU cache cleared")

    @staticmethod
    def get_memory_info() -> dict:
        """
        Informacion de uso de memoria GPU.

        Returns:
            Dict con allocated, cached, free en MB.
        """
        if not HAVE_CUDA:
            return {"available": False}
        import torch
        return {
            "available": True,
            "allocated_mb": torch.cuda.memory_allocated() / 1024**2,
            "cached_mb": torch.cuda.memory_reserved() / 1024**2,
            "device": DEVICE_NAME,
            "total_gb": GPU_MEMORY_GB,
        }


# ---------------------------------------------------------------------------
# Auto-initialization
# ---------------------------------------------------------------------------

if HAVE_CUDA:
    logger.info(
        "GPU acceleration READY: %s | %.1f GB VRAM | CUDA %s",
        DEVICE_NAME, GPU_MEMORY_GB, torch.version.cuda,
    )
else:
    logger.info("GPU acceleration: UNAVAILABLE (using CPU fallback)")
