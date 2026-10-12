"""Tests TDD para Observation Masking por defecto (FR-A3, ADR-0103).

Cubre WS-A: el masking pasa de opcional a default ON, desactivable solo por
flag explicito de entorno ``SWARMIND_OBS_MASKING_DISABLE=1``. No cambia el
comportamiento de compaction (solo el default del flag de masking).

Patron TDD (RED primero): contrato ANTES del cambio en
``harness/memory_rag/context_window_manager/manager.py``.
"""

from __future__ import annotations

import pytest

from harness.memory_rag.context_window_manager import (
    ContextSection,
    ContextWindowManager,
)

DISABLE_ENV = "SWARMIND_OBS_MASKING_DISABLE"
DEFAULT_ENV = "SWARMIND_OBS_MASKING_DEFAULT"

#: Bloque de tool output > 2000 chars (char_limit = 500 tokens * 4) pero por
#: debajo de 2000 tokens: activa el masking sin forzar el truncado legacy.
_LONG_TOOL = "Tool: runner\n" + "\n".join(
    f"content line {i} with enough padding to exceed the char limit"
    for i in range(60)
)


# ===========================================================================
# Default ON
# ===========================================================================


class TestDefaultOn:
    """Sin flag de disable, el masking queda activo por defecto."""

    def test_enabled_when_env_cleared(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """env limpiado → _use_observation_masking True."""
        monkeypatch.delenv(DISABLE_ENV, raising=False)
        monkeypatch.delenv(DEFAULT_ENV, raising=False)
        manager = ContextWindowManager(use_real_tokenizer=False)
        assert manager._use_observation_masking is True

    def test_enabled_when_default_flag_is_one(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """SWARMIND_OBS_MASKING_DEFAULT=1 → masking True (spec §2 item 4)."""
        monkeypatch.delenv(DISABLE_ENV, raising=False)
        monkeypatch.setenv(DEFAULT_ENV, "1")
        manager = ContextWindowManager(use_real_tokenizer=False)
        assert manager._use_observation_masking is True

    def test_masking_applied_by_default(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Default ON: bloque tool largo se sustituye por placeholder."""
        monkeypatch.delenv(DISABLE_ENV, raising=False)
        monkeypatch.delenv(DEFAULT_ENV, raising=False)
        manager = ContextWindowManager(use_real_tokenizer=False)
        section = ContextSection(
            name="tool_outputs", content=_LONG_TOOL, max_tokens=2000
        )
        assert manager._compress_tool_outputs(section) is True
        assert section.compressed
        assert "[tool_output:" in section.content


# ===========================================================================
# Flag explicito de disable
# ===========================================================================


class TestDisableFlag:
    """SWARMIND_OBS_MASKING_DISABLE=1 desactiva el masking."""

    def test_env_disable_flag(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """disable=1 → _use_observation_masking False."""
        monkeypatch.setenv(DISABLE_ENV, "1")
        manager = ContextWindowManager(use_real_tokenizer=False)
        assert manager._use_observation_masking is False

    def test_env_disable_skips_masking(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """disable=1 → no se inserta placeholder (usa truncado legacy).

        Discriminante: con masking ON (default) el mismo bloque produce el
        placeholder; con disable NO aparece.
        """
        monkeypatch.setenv(DISABLE_ENV, "1")
        manager = ContextWindowManager(use_real_tokenizer=False)
        section = ContextSection(
            name="tool_outputs", content=_LONG_TOOL, max_tokens=2000
        )
        result = manager._compress_tool_outputs(section)
        assert result is False
        assert "[tool_output:" not in section.content

    def test_explicit_true_overrides_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Parametro explicito True gana al env de disable."""
        monkeypatch.setenv(DISABLE_ENV, "1")
        manager = ContextWindowManager(
            use_real_tokenizer=False, use_observation_masking=True
        )
        assert manager._use_observation_masking is True

    def test_explicit_false_overrides_default(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Parametro explicito False gana al default ON."""
        monkeypatch.delenv(DISABLE_ENV, raising=False)
        manager = ContextWindowManager(
            use_real_tokenizer=False, use_observation_masking=False
        )
        assert manager._use_observation_masking is False


# ===========================================================================
# Contextos vacios
# ===========================================================================


class TestEmptyContexts:
    """No rompe el flujo con contextos vacios."""

    def test_empty_section_no_crash(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Seccion vacia → False sin crash."""
        monkeypatch.delenv(DISABLE_ENV, raising=False)
        manager = ContextWindowManager(use_real_tokenizer=False)
        section = ContextSection(name="tool_outputs", content="", max_tokens=100)
        assert manager._compress_tool_outputs(section) is False

    def test_empty_window_no_crash(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Ventana vacia → optimize sin cambios ni crash."""
        monkeypatch.delenv(DISABLE_ENV, raising=False)
        manager = ContextWindowManager(use_real_tokenizer=False)
        window = manager.create_window()
        assert manager.optimize(window) is window
        assert window.total_tokens == 0
