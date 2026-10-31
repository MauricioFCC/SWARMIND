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

Flota INSTALADA 2026-10-14 (RTX 4060 8GB, backend llama.cpp / llama-swap en
127.0.0.1:11434), alineada a la SSOT `local_models.yaml`: fast
`phi-4-mini-reasoning-q4-k-m`, coding `qwen3-4b-thinking-2507-q4-k-m`, quality
`mimo-v2-6-distill-qwen-9b-gguf-iq4-xs`, embedding `qwen3-embedding-0-6b` y
deep `ternary-bonsai-2-27b-ptq1-0` (llama-swap expone nombre corto + alias).
Se RETIRARON qwen3.5-4b, phi-4-mini-instruct, qwen2.5-coder-3b y
deepseek-r1-distill (no estan instalados en disco).

`num_ctx`: llama-server sirve los modelos a 32768 tokens, pero el harness
DECLARA 8192 porque el techo anti-TDR del `GpuBudget` (`gpu_guard.SAFE_CTX_MAX`)
sigue en 8192 (el BSOD VIDEO_TDR_FAILURE 0x116 del 2026-10-01 lo fijo). El
manifiesto es la ventana que el harness SOLICITA; no contradice al servidor.
TODA la flota corre con `keep_alive="0"` (sin residencia: no hay solape).
"""

from __future__ import annotations

from dataclasses import dataclass

from harness.model_router.backend_config import GpuBudget

#: Presupuesto de VRAM utilizable (8GB menos el escritorio WDDM ~1GB),
#: DERIVADO del `GpuBudget` por defecto (SSOT, anti-TDR configurable).
GPU_BUDGET_MB = GpuBudget().budget_mb


@dataclass(frozen=True)
class FleetModel:
    """Hechos medidos de un modelo de la flota local.

    Attributes:
        id: Nombre canonico servido por llama-swap (nombre corto).
        tier: Rol de capacidad (fast/quality/coding/embedding).
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


#: Flota INSTALADA 2026-10-14 (5 modelos), alineada a `local_models.yaml` (SSOT).
#: `num_ctx` DECLARADO a 8192 para toda la flota: el servidor los corre a mas
#: (12288-65536) pero el techo anti-TDR del harness sigue en
#: `gpu_guard.SAFE_CTX_MAX=8192` (BSOD 0x116 del 2026-10-01). `vram_mb` es la
#: huella estimada de GPU con KV a 8192 (espejo de `local_models.FALLBACK_VRAM_MB`).
#: `keep_alive="0"` en TODOS: sin residencia no hay solape en 8GB. `id` = nombre
#: corto que sirve llama-swap; `matches` cubre el nombre corto + el alias largo.
FLEET: tuple[FleetModel, ...] = (
    FleetModel(
        id="phi-4-mini-reasoning-q4-k-m",
        tier="fast", num_ctx=8192, vram_mb=2600, keep_alive="0",
        matches=(
            "phi-4-mini-reasoning-q4-k-m",
            # alias largo servido por llama-swap (guiones/puntos normalizados)
            "microsoft_phi-4-mini-reasoning-q4_k_m",
            "microsoft_phi-4-mini-reasoning", "phi-4-mini-reasoning",
        ),
    ),
    FleetModel(
        id="qwen3-4b-thinking-2507-q4-k-m",
        tier="coding", num_ctx=8192, vram_mb=2600, keep_alive="0",
        matches=(
            "qwen3-4b-thinking-2507-q4-k-m",
            # alias largo servido por llama-swap
            "qwen3-4b-thinking-2507-q4_k_m",
            "qwen3-4b-thinking",
        ),
    ),
    FleetModel(
        id="mimo-v2-6-distill-qwen-9b-gguf-iq4-xs",
        tier="quality", num_ctx=8192, vram_mb=6400, keep_alive="0",
        matches=(
            "mimo-v2-6-distill-qwen-9b-gguf-iq4-xs",
            # alias largo servido por llama-swap
            "mimo-v2.6-distill-qwen-9b-iq4_xs",
            "mimo-v2-6-distill",
        ),
    ),
    FleetModel(
        id="qwen3-embedding-0-6b",
        tier="embedding", num_ctx=8192, vram_mb=3800, keep_alive="0",
        matches=(
            "qwen3-embedding-0-6b",
            # alias largo servido por llama-swap
            "qwen3-embedding-0.6b-q8_0",
            "qwen3-embedding",
        ),
    ),
    FleetModel(
        id="ternary-bonsai-2-27b-ptq1-0",
        tier="deep", num_ctx=8192, vram_mb=5700, keep_alive="0",
        matches=(
            "ternary-bonsai-2-27b-ptq1-0",
            # alias largo servido por llama-swap
            "ternary-bonsai-2-27b-ptq1_0",
            "ternary-bonsai",
        ),
    ),
)


#: Tiers declarados en el cableado de runtime (`.opencode/config/ollama_models.yaml`).
#: La flota instalada 2026-10-14 tiene exactamente estos 4 tiers (deep no es tier).
YAML_TIERS: tuple[str, ...] = (
    "fast", "quality", "coding", "embedding",
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
