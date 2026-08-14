"""Tests unitarios para el router de tiers locales Ollama.

Escritos SOLO contra el contrato público (patrón test-writer): verifica la
heurística de enrutamiento por keywords (case-insensitive, orden
EMBEDDING → VISION → QUALITY → FAST), el mapeo de tiers a modelos y las
operaciones de ciclo de vida (ensure/warm/unload/loaded) con un client
mockeado — cero llamadas reales a Ollama.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

from harness.model_router.ollama_tiers import (
    CapabilityTier,
    OllamaTierRouter,
    OllamaTierSpec,
)

DEFAULT_FAST_MODEL = "qwen3:4b"
DEFAULT_QUALITY_MODEL = "deepseek-r1:8b"
DEFAULT_EMBEDDING_MODEL = "qwen3-embedding:0.6b"
DEFAULT_VISION_MODEL = "qwen3-vl:4b"


def _client() -> MagicMock:
    """Crea un client mock aislado para inyectar en el router."""
    return MagicMock()


def _router(client: MagicMock | None = None) -> OllamaTierRouter:
    """Crea un OllamaTierRouter con client mock (nuevo si no se provee)."""
    return OllamaTierRouter(client=client if client is not None else _client())


# ---------------------------------------------------------------------------
# model_for
# ---------------------------------------------------------------------------


def test_model_for_returns_default_specs() -> None:
    """model_for con specs por defecto mapea cada tier a su modelo local."""
    router = _router()
    assert router.model_for(CapabilityTier.FAST) == DEFAULT_FAST_MODEL
    assert router.model_for(CapabilityTier.QUALITY) == DEFAULT_QUALITY_MODEL
    assert router.model_for(CapabilityTier.EMBEDDING) == DEFAULT_EMBEDDING_MODEL
    assert router.model_for(CapabilityTier.VISION) == DEFAULT_VISION_MODEL


def test_model_for_returns_custom_spec_model() -> None:
    """model_for devuelve el modelo definido en un spec personalizado."""
    router = OllamaTierRouter(
        client=_client(),
        specs={
            CapabilityTier.FAST: OllamaTierSpec(
                tier=CapabilityTier.FAST, model="phi4-mini:3.8b"
            ),
        },
    )
    assert router.model_for(CapabilityTier.FAST) == "phi4-mini:3.8b"


# ---------------------------------------------------------------------------
# tier_for_task (heurística de keywords)
# ---------------------------------------------------------------------------


def test_tier_for_task_embedding_spanish() -> None:
    """'buscar en la doc de mis proyectos' se enruta a EMBEDDING."""
    router = _router()
    assert (
        router.tier_for_task("buscar en la doc de mis proyectos")
        == CapabilityTier.EMBEDDING
    )


def test_tier_for_task_embedding_keywords() -> None:
    """Keywords de retrieval/embedding enrutan a EMBEDDING."""
    router = _router()
    assert (
        router.tier_for_task("rag search retrieval embed index")
        == CapabilityTier.EMBEDDING
    )


def test_tier_for_task_vision() -> None:
    """Tareas con imagen/ocr/photo enrutan a VISION."""
    router = _router()
    assert router.tier_for_task("leer imagen y escribir alt-text") == CapabilityTier.VISION
    assert (
        router.tier_for_task("ocr figure diagrama screenshot photo image")
        == CapabilityTier.VISION
    )


def test_tier_for_task_quality() -> None:
    """Tareas de redacción/resumen enrutan a QUALITY."""
    router = _router()
    assert router.tier_for_task("redactar resumen de calidad") == CapabilityTier.QUALITY
    assert (
        router.tier_for_task("draft write summary essay prose copy quality")
        == CapabilityTier.QUALITY
    )


def test_tier_for_task_fast_default() -> None:
    """Tareas sin keywords especiales caen a FAST (else)."""
    router = _router()
    assert router.tier_for_task("extraer datos de un formulario") == CapabilityTier.FAST
    assert router.tier_for_task("clasificar tickets") == CapabilityTier.FAST
    assert router.tier_for_task("formatear json") == CapabilityTier.FAST


def test_tier_for_task_is_case_insensitive() -> None:
    """La heurística ignora mayúsculas/minúsculas."""
    router = _router()
    assert router.tier_for_task("SEARCH retrieval") == CapabilityTier.EMBEDDING


def test_tier_for_task_embedding_takes_precedence_over_vision() -> None:
    """El orden de evaluación es EMBEDDING → VISION → QUALITY → FAST."""
    router = _router()
    # "search" (embedding) e "image" (vision): gana EMBEDDING por precedencia.
    assert router.tier_for_task("search the image") == CapabilityTier.EMBEDDING


def test_tier_for_task_vision_takes_precedence_over_quality() -> None:
    """VISION se evalúa antes que QUALITY."""
    router = _router()
    # "write" (quality) e "image" (vision): gana VISION por precedencia.
    assert router.tier_for_task("write alt text for the image") == CapabilityTier.VISION


# ---------------------------------------------------------------------------
# task_uses_local
# ---------------------------------------------------------------------------


def test_task_uses_local_flags() -> None:
    """task_uses_local: planning (frontier) → False; extraction (local) → True."""
    router = _router()
    assert router.task_uses_local("planning") is False
    assert router.task_uses_local("extraction") is True


# ---------------------------------------------------------------------------
# Ciclo de vida delegado al client
# ---------------------------------------------------------------------------


def test_ensure_models_with_unavailable_client_returns_all_false() -> None:
    """ensure_models no lanza y devuelve False en todos los tiers si Ollama está caído."""
    client = _client()
    client.is_available.return_value = False
    router = OllamaTierRouter(client=client)
    result = router.ensure_models()
    assert set(result) == set(CapabilityTier)
    assert all(ok is False for ok in result.values())


def test_warm_all_returns_all_true_when_client_warm_succeeds() -> None:
    """warm_all delega en client.warm por tier y reporta True en todos."""
    client = _client()
    client.warm.return_value = True
    router = OllamaTierRouter(client=client)
    result = router.warm_all()
    assert set(result) == set(CapabilityTier)
    assert all(ok is True for ok in result.values())
    models_called = [
        call.args[0] if call.args else call.kwargs.get("model")
        for call in client.warm.call_args_list
    ]
    assert set(models_called) == {
        DEFAULT_FAST_MODEL,
        DEFAULT_QUALITY_MODEL,
        DEFAULT_EMBEDDING_MODEL,
        DEFAULT_VISION_MODEL,
    }


def test_unload_all_returns_all_true_when_client_unload_succeeds() -> None:
    """unload_all delega en client.unload por tier y reporta True en todos."""
    client = _client()
    client.unload.return_value = True
    router = OllamaTierRouter(client=client)
    result = router.unload_all()
    assert set(result) == set(CapabilityTier)
    assert all(ok is True for ok in result.values())


def test_loaded_tiers_maps_loaded_models_to_tiers() -> None:
    """loaded_tiers marca True solo los tiers cuyo modelo está cargado."""
    client = _client()
    client.loaded_models.return_value = [DEFAULT_FAST_MODEL, DEFAULT_EMBEDDING_MODEL]
    router = OllamaTierRouter(client=client)
    result = router.loaded_tiers()
    assert result[CapabilityTier.FAST] is True
    assert result[CapabilityTier.QUALITY] is False
    assert result[CapabilityTier.EMBEDDING] is True
    assert result[CapabilityTier.VISION] is False


# ---------------------------------------------------------------------------
# load_from_yaml
# ---------------------------------------------------------------------------


def test_load_from_yaml_reads_specs(tmp_path: Path) -> None:
    """load_from_yaml carga specs desde un YAML temporal con las 4 claves de tier."""
    yaml_path = tmp_path / "ollama_tiers.yaml"
    yaml_path.write_text(
        """
fast:
  model: phi4-mini:3.8b
  keep_alive: 10m
quality:
  model: qwen2.5:32b
embedding:
  model: qwen3-embedding:0.6b
vision:
  model: qwen3-vl:4b
""".strip(),
        encoding="utf-8",
    )
    router = OllamaTierRouter.load_from_yaml(str(yaml_path))
    assert router.model_for(CapabilityTier.FAST) == "phi4-mini:3.8b"
    assert router.model_for(CapabilityTier.QUALITY) == "qwen2.5:32b"
    assert router.model_for(CapabilityTier.EMBEDDING) == DEFAULT_EMBEDDING_MODEL
    assert router.model_for(CapabilityTier.VISION) == DEFAULT_VISION_MODEL


def test_load_from_yaml_with_missing_file_uses_defaults(tmp_path: Path) -> None:
    """load_from_yaml con ruta inexistente no crashea y usa los defaults."""
    missing = str(tmp_path / "no_existe.yaml")
    router = OllamaTierRouter.load_from_yaml(missing)
    assert router.model_for(CapabilityTier.FAST) == DEFAULT_FAST_MODEL
    assert router.model_for(CapabilityTier.QUALITY) == DEFAULT_QUALITY_MODEL
    assert router.model_for(CapabilityTier.EMBEDDING) == DEFAULT_EMBEDDING_MODEL
    assert router.model_for(CapabilityTier.VISION) == DEFAULT_VISION_MODEL
