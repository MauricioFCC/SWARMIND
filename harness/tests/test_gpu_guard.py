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

ORNITH = "hf.co/ornith-ai/Ornith-1.5-9B-GGUF:Q4_K_M"
MIMO = "hf.co/bartowski/MiMo-V2.6-Distill-Qwen-9B-GGUF:IQ4_XS"
QWOPUS = "hf.co/Jackrong/Qwopus3.5-9B-v3-GGUF:Q4_K_M"
FAST = "hf.co/unsloth/Qwen3.5-4B-GGUF:UD-Q4_K_XL"
_TEXT_MODELS = (FAST, MIMO, QWOPUS, ORNITH)


def test_constants_anti_tdr() -> None:
    """El techo es 8192 y la reserva 3000 MB (contrato post-BSOD)."""
    assert SAFE_CTX_MAX == 8192
    assert MIN_FREE_VRAM_MB == 3000
    assert MIN_SAFE_CTX <= SAFE_CTX_MAX


def test_safe_num_ctx_never_exceeds_ceiling() -> None:
    """Aunque pidan 16384, jamas devuelve mas de 8192."""
    assert safe_num_ctx(ORNITH, None, requested=16384) == SAFE_CTX_MAX
    assert safe_num_ctx(ORNITH, 24000, requested=16384) <= SAFE_CTX_MAX


def test_safe_num_ctx_low_vram_returns_floor() -> None:
    """VRAM bajo la reserva -> ventana minima (2048), nunca > 8192."""
    ctx = safe_num_ctx(ORNITH, free_vram_mb=2000)
    assert ctx == MIN_SAFE_CTX
    assert ctx <= SAFE_CTX_MAX


def test_safe_num_ctx_scales_with_free_vram() -> None:
    """Con VRAM intermedia escala a multiplos de 1K por debajo del techo."""
    mid = safe_num_ctx(ORNITH, free_vram_mb=6000)
    assert MIN_SAFE_CTX <= mid < SAFE_CTX_MAX
    assert mid % 1024 == 0
    # Mucha VRAM libre -> se permite la ventana declarada del modelo (4096).
    assert safe_num_ctx(ORNITH, free_vram_mb=24000) == 4096
    assert safe_num_ctx(ORNITH, free_vram_mb=24000) <= SAFE_CTX_MAX


def test_should_degrade_true_when_model_does_not_fit() -> None:
    """9B (6.7GB) con 2GB libres no cabe -> degradar."""
    assert should_degrade(ORNITH, free_vram_mb=2000) is True


def test_should_degrade_false_when_fits_or_unknown() -> None:
    """Modelo chico con VRAM holgada o GPU desconocida no degrada."""
    assert should_degrade(FAST, free_vram_mb=6000) is False
    assert should_degrade(ORNITH, free_vram_mb=None) is False


def test_pick_safe_model_degrades_to_smallest_that_fits() -> None:
    """Con 4.3GB libres degrada Ornith -> el 4B (3600MB)."""
    assert pick_safe_model(ORNITH, _TEXT_MODELS, free_vram_mb=4300) == FAST


def test_pick_safe_model_keeps_requested_when_fits() -> None:
    """Si el pedido cabe, no cambia de modelo."""
    assert pick_safe_model(FAST, _TEXT_MODELS, free_vram_mb=8000) == FAST


def test_pick_safe_model_returns_requested_when_none_fits() -> None:
    """Sin candidato viable devuelve el pedido (el llamador va a cloud)."""
    assert pick_safe_model(ORNITH, _TEXT_MODELS, free_vram_mb=1000) == ORNITH
