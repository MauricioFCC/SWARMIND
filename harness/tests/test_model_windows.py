"""Tests para model_windows — presupuesto de ventana anti-loop (ADR-0092).

Bug real: con num_ctx default (4096) y ~17K tokens de sistema+skills, el
modelo local entra en loop de compactacion (analiza el principio, nunca
resuelve) y vuelca la GPU. El guard valida que el prompt quepa en la
ventana ANTES de ejecutar en local.
"""


from harness.model_router.model_windows import (
    DEFAULT_NUM_CTX,
    SYSTEM_BUDGET_TOKENS,
    fits_in_window,
    recommend_num_ctx,
)


def test_recommend_small_models() -> None:
    """Modelos chicos (<=4B) recomiendan 8192 (2x default, seguro en 8GB)."""
    assert recommend_num_ctx("hf.co/LiquidAI/LFM2.5-2.6B-GGUF:Q8_0") == 8192
    assert recommend_num_ctx("llama3.2:3b") == 8192
    assert recommend_num_ctx("qwen3:4b") == 8192


def test_recommend_big_models_conservative() -> None:
    """Modelos 7-9B recomiendan 8192 (no 16K: 6GB pesos + KV = OOM en 8GB)."""
    assert recommend_num_ctx("hf.co/empero-ai/Qwen3.8-9B-Distill-GGUF:Q4_K_M") == 8192
    assert recommend_num_ctx("deepseek-r1:8b") == 8192


def test_recommend_olmoe_arch_limit() -> None:
    """OLMoE (4K arquitectura) recomienda 4096."""
    assert recommend_num_ctx("hf.co/mradermacher/OLMoE-1B-7B-0125-Instruct-Distill-ot114k-batch32-i1-GGUF:IQ4_NL") == 4096


def test_recommend_unknown_defaults() -> None:
    """Modelo desconocido usa el default seguro."""
    assert recommend_num_ctx("algun-modelo-futuro:99b") == DEFAULT_NUM_CTX
    assert DEFAULT_NUM_CTX == 8192


def test_fits_small_task() -> None:
    """Tarea chica + sistema cabe en la ventana."""
    assert fits_in_window("hf.co/LiquidAI/LFM2.5-2.6B-GGUF:Q8_0", task_chars=200) is True


def test_overflow_goes_cloud() -> None:
    """Prompt que excede la ventana no va a local (evita el loop)."""
    assert fits_in_window("llama3.2:3b", task_chars=50_000) is False


def test_system_budget_documented() -> None:
    """Los presupuestos estan documentados (full actual vs lean objetivo)."""
    assert SYSTEM_BUDGET_TOKENS >= 8000


def test_empty_task_fits() -> None:
    """Tarea vacia cabe (no falla el guard)."""
    assert fits_in_window("qwen3:4b", task_chars=0) is True
