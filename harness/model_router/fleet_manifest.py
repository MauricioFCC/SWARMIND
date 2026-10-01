"""fleet_manifest.py — SSOT de la flota local (ADR-0101).

WHAT: hechos medidos de cada modelo local en UN solo lugar (id canonico,
tier, num_ctx real, VRAM pico, keep_alive) + `model_entry()` que resuelve
un nombre de modelo a su entrada por substring.
WHY: habia triple lista de tiers (`ollama_models.yaml`,
`ollama_tiers._DEFAULT_TIER_MODELS`, `capability_profiles._BUILTIN`) y la
ventana real derivaba en silencio (el guardian asumia 8192 y los tiers
corrian a 4096; las variantes horneadas a 16384 sin declararlo). Resultado:
desajustes y volcados de VRAM. Un manifiesto tipado + tests de invariantes
(ver specs/local-fleet-ssot.md) mata la deriva sin parser YAML propio.
WHERE: `model_windows.recommend_num_ctx` (ventana), `vram_guard.footprint_mb`
(presupuesto), `local_executor` (options.num_ctx). El YAML de config sigue
siendo el cableado de runtime y los tests verifican que coincida.

Medido 2026-10-01 (RTX 4060 8GB, Ollama 0.34.4). Tras el BSOD
VIDEO_TDR_FAILURE (0x116) del 2026-10-01 (9B + ctx 16384 + Vulkan en 8GB)
TODA la flota corre a `num_ctx=8192` y `keep_alive="0"` salvo el tier fast.
"""

from __future__ import annotations

from dataclasses import dataclass

#: Presupuesto de VRAM utilizable (8GB menos el escritorio WDDM ~1GB).
GPU_BUDGET_MB = 7000


@dataclass(frozen=True)
class FleetModel:
    """Hechos medidos de un modelo de la flota local.

    Attributes:
        id: Nombre canonico en Ollama (pullable desde el registro).
        tier: Rol de capacidad (fast/quality/coding/reasoning/embedding/vision).
        num_ctx: Ventana real que se solicita via `options.num_ctx`.
        vram_mb: VRAM pico medida (MB, conservadora sin compresion KV).
        keep_alive: Politica de residencia ("0" = descarga inmediata).
        matches: Substrings que identifican el modelo (case-insensitive).
    """

    id: str
    tier: str
    num_ctx: int
    vram_mb: int
    keep_alive: str
    matches: tuple[str, ...]


#: Flota canonica 2026-10-01. `num_ctx` escalado por TAMANO del modelo:
#: los 9B Q4 (~6.1-6.7GB) van a 4096 para dejar KV headroom en 8GB; el 4B
#: (3.6GB) admite 8192. Techo duro anti-TDR: `gpu_guard.SAFE_CTX_MAX=8192`.
#: 16384 NO es seguro (causa del BSOD 0x116 del 2026-10-01).
#: `keep_alive="0"` en TODOS: sin residencia no hay solape de modelos.
FLEET: tuple[FleetModel, ...] = (
    FleetModel(
        id="hf.co/unsloth/Qwen3.5-4B-GGUF:UD-Q4_K_XL",
        tier="fast", num_ctx=8192, vram_mb=3600, keep_alive="0",
        matches=("unsloth/qwen3.5-4b", "qwen3.5-4b", "ud-q4_k_xl"),
    ),
    FleetModel(
        id="hf.co/bartowski/MiMo-V2.6-Distill-Qwen-9B-GGUF:IQ4_XS",
        tier="quality", num_ctx=4096, vram_mb=6100, keep_alive="0",
        matches=("bartowski/mimo", "mimo-v2.6", "mimo"),
    ),
    FleetModel(
        id="hf.co/Jackrong/Qwopus3.5-9B-v3-GGUF:Q4_K_M",
        tier="coding", num_ctx=4096, vram_mb=6600, keep_alive="0",
        matches=("jackrong/qwopus3.5-9b-v3", "qwopus3.5-9b-v3", "qwopus3.5-9b"),
    ),
    FleetModel(
        id="hf.co/ornith-ai/Ornith-1.5-9B-GGUF:Q4_K_M",
        tier="reasoning", num_ctx=4096, vram_mb=6700, keep_alive="0",
        matches=("ornith-ai/ornith", "ornith-1.5"),
    ),
    FleetModel(
        id="qwen3-embedding:0.6b",
        tier="embedding", num_ctx=8192, vram_mb=400, keep_alive="0",
        matches=("qwen3-embedding",),
    ),
    FleetModel(
        id="qwen3-vl:4b",
        tier="vision", num_ctx=8192, vram_mb=2600, keep_alive="0",
        matches=("qwen3-vl",),
    ),
)


#: Tiers declarados en el cableado de runtime (`.opencode/config/ollama_models.yaml`).
#: El manifiesto es un superset (incluye reasoning, sin tier en el enum).
YAML_TIERS: tuple[str, ...] = (
    "fast", "quality", "coding", "embedding", "vision",
)


def model_entry(model: str) -> FleetModel | None:
    """Resuelve un nombre/tag de modelo a su entrada de flota.

    Match por substring case-insensitive; si varios coinciden, gana el
    substring mas especifico (mas largo) para evitar colisiones de familia.

    Args:
        model: Nombre/tag de Ollama (canonico o variante local).

    Returns:
        La entrada de flota, o None si el modelo no pertenece a la flota.
    """
    lowered = model.lower()
    best: FleetModel | None = None
    best_len = 0
    for entry in FLEET:
        for key in entry.matches:
            if key in lowered and len(key) > best_len:
                best, best_len = entry, len(key)
    return best


def tier_entry(tier: str) -> FleetModel | None:
    """Entrada de flota para un tier de capacidad.

    Args:
        tier: Nombre del tier ("fast", "quality", ...).

    Returns:
        La entrada del tier, o None si no existe.
    """
    for entry in FLEET:
        if entry.tier == tier:
            return entry
    return None
