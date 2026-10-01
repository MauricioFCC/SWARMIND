"""Tests para model_windows — presupuesto de ventana anti-volcado (ADR-0092).

Tras el BSOD VIDEO_TDR_FAILURE (0x116) del 2026-10-01 (9B + ctx 16384 +
Vulkan en 8GB), el default honesto es 8192 (`gpu_guard.SAFE_CTX_MAX`): 16384
NO es seguro en 8GB. El guard valida sistema+tarea+respuesta acotada contra
la ventana MEDIDA antes de ejecutar en local.
"""

from harness.model_router.model_windows import (
    DEFAULT_NUM_CTX,
    RESPONSE_RESERVE_TOKENS,
    SYSTEM_BUDGET_TOKENS,
    fits_in_window,
    recommend_num_ctx,
)

_FAST = "hf.co/unsloth/Qwen3.5-4B-GGUF:UD-Q4_K_XL"
_MIMO = "hf.co/bartowski/MiMo-V2.6-Distill-Qwen-9B-GGUF:IQ4_XS"
_QWOPUS = "hf.co/Jackrong/Qwopus3.5-9B-v3-GGUF:Q4_K_M"
_ORNITH = "hf.co/ornith-ai/Ornith-1.5-9B-GGUF:Q4_K_M"


def test_default_ctx_is_safe_ceiling() -> None:
    """El default es 8192 (techo anti-TDR); 16384 NO es seguro en 8GB."""
    assert DEFAULT_NUM_CTX == 8192


def test_retired_models_fall_to_default() -> None:
    """Retirados/no-flota: sin clave en la tabla, caen al default 8192.

    MiniCPM5, Qwen3.8 y Opus-Distill se retiraron 2026-10-01 y no deben
    recuperar una ventana propia (ni 16K/32K horneados) por accidente.
    """
    for retired in (
        "hf.co/openbmb/MiniCPM5-2B-GGUF:Q8_0",
        "hf.co/empero-ai/Qwen3.8-9B-Distill-GGUF:Q4_K_M",
        "hf.co/Jackrong/Qwen3.5-9B-Claude-4.6-Opus-Reasoning-Distilled-v2-GGUF:Q4_K_M",
        "qwen38-9b-16k",
        "minicpm5-2b-32k",
        "opus-distill-9b-16k",
        "llama3.2:3b",
        "qwen2.5-coder:7b",
    ):
        assert recommend_num_ctx(retired) == DEFAULT_NUM_CTX, retired


def test_recommend_fleet_windows_declared() -> None:
    """La flota declara su ventana segura: 4B=8192, 9B=4096 (SSOT, ADR-0101)."""
    assert recommend_num_ctx(_FAST) == 8192
    assert recommend_num_ctx(_MIMO) == 4096
    assert recommend_num_ctx(_QWOPUS) == 4096
    assert recommend_num_ctx(_ORNITH) == 4096
    assert recommend_num_ctx("qwen3-embedding:0.6b") == 8192
    assert recommend_num_ctx("qwen3-vl:4b") == 8192


def test_recommend_unknown_defaults() -> None:
    """Modelo desconocido usa el default seguro (anti-TDR)."""
    assert recommend_num_ctx("algun-modelo-futuro:99b") == DEFAULT_NUM_CTX


def test_fits_small_task() -> None:
    """Tarea chica + sistema cabe con la reserva de respuesta intacta."""
    assert fits_in_window(_FAST, task_chars=200) is True


def test_overflow_goes_cloud() -> None:
    """Prompt que excede la ventana declarada no va a local (evita el volcado)."""
    assert fits_in_window("llama3.2:3b", task_chars=50_000) is False
    # Ornith 9B: ventana 4096 - 1024 reserva = 3072; una tarea de 60K chars
    # (15000 tok) NO cabe y va a cloud.
    assert fits_in_window(_ORNITH, task_chars=60_000) is False
    # Tarea chica SI cabe en la ventana de 4096.
    assert fits_in_window(_ORNITH, task_chars=1_000) is True


def test_system_budget_documented() -> None:
    """Los presupuestos estan documentados (full actual vs lean objetivo)."""
    assert SYSTEM_BUDGET_TOKENS >= 8000
    assert RESPONSE_RESERVE_TOKENS >= 512


def test_empty_task_fits() -> None:
    """Tarea vacia cabe (no falla el guard)."""
    assert fits_in_window("modelo-ajeno:1b", task_chars=0) is True
