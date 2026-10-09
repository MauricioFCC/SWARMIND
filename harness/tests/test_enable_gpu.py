"""Tests hermeticos para los topes VRAM de scripts/enable_gpu.py.

Sin GPU, sin registro ni red: el store de env se sustituye por fakes.
"""

from __future__ import annotations

import sys
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parent.parent.parent / "scripts"
sys.path.insert(1, str(_SCRIPTS))

import enable_gpu as eg


def _store(monkeypatch, values: dict) -> dict:
    """Sustituye el store persistente por un dict en memoria.

    Args:
        monkeypatch: Fixture de pytest.
        values: Estado inicial del store falso.

    Returns:
        El dict vivo (para inspeccionar escrituras).
    """
    monkeypatch.setattr(eg, "_read_user_env", lambda name: values.get(name))
    return values


def test_limits_contract_anti_tdr() -> None:
    """Contrato anti-TDR 8GB: 1 residente, sin paralelo, KV comprimida, ctx 8192.

    El BSOD VIDEO_TDR_FAILURE (0x116) del 2026-10-01 lo causo ctx 16384 +
    Vulkan + modelo residente; este test fija el techo seguro.
    """
    assert eg.OLLAMA_VRAM_LIMITS == {
        "OLLAMA_MAX_LOADED_MODELS": "1",
        "OLLAMA_NUM_PARALLEL": "1",
        "OLLAMA_FLASH_ATTENTION": "1",
        "OLLAMA_KV_CACHE_TYPE": "q8_0",
        "OLLAMA_CONTEXT_LENGTH": "8192",
        "OLLAMA_KEEP_ALIVE": "0",
        "OLLAMA_VULKAN": "false",
    }


def test_check_ok_when_all_match(monkeypatch) -> None:
    """Store igual a topes -> (True, detalle)."""
    _store(monkeypatch, dict(eg.OLLAMA_VRAM_LIMITS))
    ok, detail = eg.check_ollama_limits()
    assert ok is True
    assert "OK" in detail


def test_check_reports_missing_var(monkeypatch) -> None:
    """Store distinto -> (False, nombra la variable)."""
    _store(monkeypatch, {"OLLAMA_MAX_LOADED_MODELS": "3"})
    ok, detail = eg.check_ollama_limits()
    assert ok is False
    assert "OLLAMA_MAX_LOADED_MODELS" in detail
    assert "OLLAMA_NUM_PARALLEL" in detail


def test_ensure_only_writes_missing(monkeypatch) -> None:
    """Idempotente: solo escribe lo distinto y re-verifica."""
    written: dict = {}
    store = {"OLLAMA_MAX_LOADED_MODELS": "1"}

    def fake_read(name: str):
        return written.get(name, store.get(name))

    def fake_write(name: str, value: str) -> bool:
        written[name] = value
        return True

    monkeypatch.setattr(eg, "_read_user_env", fake_read)
    monkeypatch.setattr(eg, "_write_user_env", fake_write)
    ok, _ = eg.ensure_ollama_limits()
    assert ok is True
    assert written == {
        "OLLAMA_NUM_PARALLEL": "1",
        "OLLAMA_FLASH_ATTENTION": "1",
        "OLLAMA_KV_CACHE_TYPE": "q8_0",
        "OLLAMA_CONTEXT_LENGTH": "8192",
        "OLLAMA_KEEP_ALIVE": "0",
        "OLLAMA_VULKAN": "false",
    }


def test_ensure_false_when_write_fails(monkeypatch) -> None:
    """Si persistir falla -> (False, accionable) sin excepcion."""
    _store(monkeypatch, {})
    monkeypatch.setattr(eg, "_write_user_env", lambda n, v: False)
    ok, detail = eg.ensure_ollama_limits()
    assert ok is False
    assert "WHERE" in detail
