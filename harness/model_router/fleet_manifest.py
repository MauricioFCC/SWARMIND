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

Medido 2026-09-30 (RTX 4060 8GB, Ollama 0.34.4, `ollama ps` + `/api/show`).
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


#: Flota canonica. Los `num_ctx` son los valores que la ruta local solicita
#: (verificado: 16384 en 9B Q4 -> 5.15GB con KV comprimida, 5.7GB sin ella).
FLEET: tuple[FleetModel, ...] = (
    FleetModel(
        id="hf.co/openbmb/MiniCPM5-2B-GGUF:Q8_0",
        tier="fast", num_ctx=8192, vram_mb=2700, keep_alive="5m",
        matches=("minicpm5", "minicpm"),
    ),
    FleetModel(
        id="hf.co/empero-ai/Qwen3.8-9B-Distill-GGUF:Q4_K_M",
        tier="quality", num_ctx=16384, vram_mb=5800, keep_alive="0",
        matches=("qwen3.8", "qwen38"),
    ),
    FleetModel(
        id="hf.co/Jackrong/Qwopus3.5-9B-v3-GGUF:Q4_K_M",
        tier="coding", num_ctx=16384, vram_mb=6600, keep_alive="0",
        matches=("qwopus3.5-9b-v3", "qwopus-v3", "qwopus3.5", "qwopus"),
    ),
    FleetModel(
        id="hf.co/Jackrong/Qwen3.5-9B-Claude-4.6-Opus-Reasoning-Distilled-v2-GGUF:Q4_K_M",
        tier="reasoning", num_ctx=16384, vram_mb=6600, keep_alive="0",
        matches=("claude-4.6-opus", "opus-distill", "claude-opus-distill"),
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
