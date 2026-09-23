"""Tests hermeticos para check_unsloth (sin red ni GPU).

El smoke de Unsloth no debe generar si el modelo no cabe en VRAM
(anti-OOM: llama-server + Ollama residente en 8GB = nvlddmkm 153).
"""

from __future__ import annotations

import harness.model_router.unsloth_client as unsloth_module
import harness.model_router.vram_guard as vram_guard_module
from harness.scripts.check_unsloth import check_unsloth


class _FakeConfig:
    """Config fake compatible con UnslothClient falso."""

    def __init__(self, base_url: str = "", api_key: str | None = None) -> None:
        """Guarda base_url y api_key sin validar.

        Args:
            base_url: Base del servidor falso.
            api_key: Clave opcional (ignorada en local).
        """
        self.base_url = base_url
        self.api_key = api_key


class _FakeUnslothClient:
    """UnslothClient falso: modelos programables y generate que registra llamadas."""

    def __init__(
        self, config=None, models: list[str] | None = None, output: str = "UNSLOTH OK",
    ) -> None:
        """Inicializa el fake con modelos y salida programables.

        Args:
            config: Config ignorada (compatibilidad de firma).
            models: Modelos que list_models() retorna.
            output: Texto que generate() retorna.
        """
        self._models = list(models) if models is not None else []
        self._output = output
        self.generate_calls: list[tuple[str, str]] = []

    def is_available(self) -> bool:
        """Siempre disponible (el discovery ya fue parcheado).

        Returns:
            True siempre.
        """
        return True

    def list_models(self) -> list[str]:
        """Retorna los modelos programados.

        Returns:
            Copia de la lista de modelos.
        """
        return list(self._models)

    def generate(self, model: str, prompt: str, **kwargs) -> str:
        """Registra la llamada y retorna la salida programada.

        Args:
            model: Modelo objetivo.
            prompt: Prompt del smoke.
            kwargs: Ignorados (max_tokens, etc.).

        Returns:
            Salida programada.
        """
        self.generate_calls.append((model, prompt))
        return self._output


def _patch_unsloth(monkeypatch, models: list[str], output: str = "UNSLOTH OK"):
    """Parchea discovery + cliente de Unsloth con fakes hermeticos.

    Args:
        monkeypatch: Fixture de pytest.
        models: Modelos que el servidor falso sirve.
        output: Salida del generate falso.

    Returns:
        Fake cliente instanciado por check_unsloth (via holder).
    """
    holder: dict = {}
    monkeypatch.setattr(
        unsloth_module, "discover_base_url", lambda: "http://127.0.0.1:9999",
    )
    monkeypatch.setattr(unsloth_module, "UnslothConfig", _FakeConfig)

    def _factory(config=None):
        client = _FakeUnslothClient(config=config, models=models, output=output)
        holder["client"] = client
        return client

    monkeypatch.setattr(unsloth_module, "UnslothClient", _factory)
    return holder


def test_server_off_returns_false(monkeypatch) -> None:
    """Servidor apagado (discovery None) -> False sin red."""
    monkeypatch.setattr(unsloth_module, "discover_base_url", lambda: None)
    assert check_unsloth() is False


def test_big_model_skips_smoke_without_generate(monkeypatch) -> None:
    """Modelo 26B con 8188MB libres -> False SIN llamar a generate (anti-OOM)."""
    holder = _patch_unsloth(monkeypatch, models=["unsloth/gemma-4-26B"])
    monkeypatch.setattr(vram_guard_module, "free_vram_mb", lambda: 8188)
    assert check_unsloth() is False
    assert holder["client"].generate_calls == []


def test_small_model_smoke_ok(monkeypatch) -> None:
    """Modelo pequeno con VRAM suficiente -> smoke genera y retorna True."""
    holder = _patch_unsloth(
        monkeypatch, models=["minicpm5-2b-32k"], output="UNSLOTH OK",
    )
    monkeypatch.setattr(vram_guard_module, "free_vram_mb", lambda: 8188)
    assert check_unsloth() is True
    assert len(holder["client"].generate_calls) == 1
