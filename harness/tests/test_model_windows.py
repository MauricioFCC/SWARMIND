"""Tests para model_windows — presupuesto de ventana anti-volcado (ADR-0092).

Medido 2026-09-29 (`ollama ps` CONTEXT + `ollama show` sin PARAMETER):
los blobs canonicos hf.co corren con el default 4096, NO 8192. El guard
valida sistema+tarea+respuesta acotada contra la ventana MEDIDA antes de
ejecutar en local (antes admitia 2x y el KV desbordaba con residentes).
"""


from harness.model_router.model_windows import (
    DEFAULT_NUM_CTX,
    RESPONSE_RESERVE_TOKENS,
    SYSTEM_BUDGET_TOKENS,
    fits_in_window,
    recommend_num_ctx,
)


def test_recommend_measured_defaults() -> None:
    """Blobs canonicos: default real 4096 (medido, no aspiracional)."""
    assert recommend_num_ctx("hf.co/LiquidAI/LFM2.5-2.6B-GGUF:Q8_0") == 4096
    assert recommend_num_ctx("llama3.2:3b") == 4096
    assert recommend_num_ctx("qwen3:4b") == 4096
    assert recommend_num_ctx("hf.co/openbmb/MiniCPM5-2B-GGUF:Q8_0") == 4096


def test_recommend_big_models_measured() -> None:
    """9B canonicos: 4096 medidos (5.3GB/4096 en `ollama ps`)."""
    assert recommend_num_ctx("hf.co/empero-ai/Qwen3.8-9B-Distill-GGUF:Q4_K_M") == 4096
    assert recommend_num_ctx("deepseek-r1:8b") == 4096


def test_recommend_baked_ctx_short_names() -> None:
    """Nombres cortos con ctx horneado: 16384 medido (`ollama show`)."""
    assert recommend_num_ctx("qwen38-9b-16k") == 16384


def test_recommend_olmoe_arch_limit() -> None:
    """OLMoE (4K arquitectura) recomienda 4096."""
    assert recommend_num_ctx("hf.co/mradermacher/OLMoE-1B-7B-0125-Instruct-Distill-ot114k-batch32-i1-GGUF:IQ4_NL") == 4096


def test_recommend_unknown_defaults() -> None:
    """Modelo desconocido usa el default honesto (default real Ollama)."""
    assert recommend_num_ctx("algun-modelo-futuro:99b") == DEFAULT_NUM_CTX
    assert DEFAULT_NUM_CTX == 4096


def test_fits_small_task() -> None:
    """Tarea chica + sistema cabe con la reserva de respuesta intacta."""
    assert fits_in_window("hf.co/LiquidAI/LFM2.5-2.6B-GGUF:Q8_0", task_chars=200) is True


def test_overflow_goes_cloud() -> None:
    """Prompt que excede la ventana medida no va a local (evita el volcado)."""
    assert fits_in_window("llama3.2:3b", task_chars=50_000) is False
    # 12K chars = 3000 tok + 2500 sistema > 4096 - reserva: antes pasaba.
    assert fits_in_window("hf.co/empero-ai/Qwen3.8-9B-Distill-GGUF:Q4_K_M",
                          task_chars=12_000) is False


def test_baked_window_admits_more() -> None:
    """Ventana horneada 16K si admite tareas que en 4096 irian a cloud."""
    assert fits_in_window("qwen38-9b-16k", task_chars=40_000) is True


def test_system_budget_documented() -> None:
    """Los presupuestos estan documentados (full actual vs lean objetivo)."""
    assert SYSTEM_BUDGET_TOKENS >= 8000
    assert RESPONSE_RESERVE_TOKENS >= 512


def test_empty_task_fits() -> None:
    """Tarea vacia cabe (no falla el guard)."""
    assert fits_in_window("qwen3:4b", task_chars=0) is True
