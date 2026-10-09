"""Tests para gpu_guard — capa de seguridad anti-TDR (BSOD 0x116, 2026-10-01).

El incidente: 9B Q4 + num_ctx 16384 + Vulkan sobre 8GB -> VIDEO_TDR_FAILURE
(0x116). El guard impone un techo de contexto de 8192, reserva VRAM libre y
degrada al modelo mas chico que quepa. Cada test puede fallar si alguien
sube el techo o elimina la degradacion (no son decorativos).
"""

from harness.model_router.gpu_guard import (
    MIN_FREE_VRAM_MB,
    MIN_SAFE_CTX,
    SAFE_CTX_MAX,
    pick_safe_model,
    safe_num_ctx,
    should_degrade,
)

#: Flota reducida 2026-10-08 (vram_mb del manifiesto, KV a 8192).
CODER = "qwen2.5-coder-3b-iq4-xs"  # 3300MB
FAST = "qwen3-5-4b-gguf-ud-q4-k-xl"  # 4600MB
PHI = "phi-4-mini-instruct-q4-k-m"  # 5700MB
_TEXT_MODELS = (FAST, PHI, CODER)


def test_constants_anti_tdr() -> None:
    """El techo es 8192 y la reserva 3000 MB (contrato post-BSOD)."""
    assert SAFE_CTX_MAX == 8192
    assert MIN_FREE_VRAM_MB == 3000
    assert MIN_SAFE_CTX <= SAFE_CTX_MAX


def test_safe_num_ctx_never_exceeds_ceiling() -> None:
    """Aunque pidan 16384, jamas devuelve mas de 8192."""
    assert safe_num_ctx(PHI, None, requested=16384) == SAFE_CTX_MAX
    assert safe_num_ctx(PHI, 24000, requested=16384) <= SAFE_CTX_MAX


def test_safe_num_ctx_low_vram_returns_floor() -> None:
    """VRAM bajo la reserva -> ventana minima (2048), nunca > 8192."""
    ctx = safe_num_ctx(PHI, free_vram_mb=2000)
    assert ctx == MIN_SAFE_CTX
    assert ctx <= SAFE_CTX_MAX


def test_safe_num_ctx_scales_with_free_vram() -> None:
    """Con VRAM intermedia escala a multiplos de 1K por debajo del techo."""
    mid = safe_num_ctx(PHI, free_vram_mb=6000)
    assert MIN_SAFE_CTX <= mid < SAFE_CTX_MAX
    assert mid % 1024 == 0
    # Mucha VRAM libre -> se permite la ventana declarada del modelo (8192).
    assert safe_num_ctx(PHI, free_vram_mb=24000) == 8192
    assert safe_num_ctx(PHI, free_vram_mb=24000) <= SAFE_CTX_MAX


def test_should_degrade_true_when_model_does_not_fit() -> None:
    """phi (5.7GB) con 2GB libres no cabe -> degradar."""
    assert should_degrade(PHI, free_vram_mb=2000) is True


def test_should_degrade_false_when_fits_or_unknown() -> None:
    """Modelo chico con VRAM holgada o GPU desconocida no degrada."""
    assert should_degrade(FAST, free_vram_mb=6000) is False
    assert should_degrade(PHI, free_vram_mb=None) is False


def test_pick_safe_model_degrades_to_smallest_that_fits() -> None:
    """Con 4.3GB libres degrada phi -> el coder 3B (3300MB)."""
    assert pick_safe_model(PHI, _TEXT_MODELS, free_vram_mb=4300) == CODER


def test_pick_safe_model_keeps_requested_when_fits() -> None:
    """Si el pedido cabe, no cambia de modelo."""
    assert pick_safe_model(FAST, _TEXT_MODELS, free_vram_mb=8000) == FAST


def test_pick_safe_model_returns_requested_when_none_fits() -> None:
    """Sin candidato viable devuelve el pedido (el llamador va a cloud)."""
    assert pick_safe_model(PHI, _TEXT_MODELS, free_vram_mb=1000) == PHI
