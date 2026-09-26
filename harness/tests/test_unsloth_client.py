"""Tests para UnslothClient — llama-server de Unsloth Desktop (ADR-0099).

Unsloth expone OpenAI-compatible (/v1/models + /v1/chat/completions) en
puerto DINAMICO por sesion; sin auth en local. API key SOLO por env/arg,
jamas hardcodeada (SEG). Discovery por /health (inyectable en tests).
"""

import pytest

from harness.model_router.unsloth_client import (
    CANDIDATE_PORTS,
    UnslothClient,
    UnslothConfig,
    UnslothError,
    discover_base_url,
)


def _client(**kwargs) -> UnslothClient:
    """Cliente contra URL dummy (transporte mockeado en cada test)."""
    return UnslothClient(UnslothConfig(base_url="http://127.0.0.1:9", **kwargs))


def test_discover_finds_server() -> None:
    """Discovery retorna el primer puerto con /health ok."""

    def _probe(port: int) -> bool:
        return port == 61767

    assert discover_base_url((8080, 61767), probe=_probe) == "http://127.0.0.1:61767"


def test_discover_none_when_down() -> None:
    """Sin servidor: None (graceful, no excepcion)."""
    assert discover_base_url((9,), probe=lambda p: False) is None


def test_is_available_true(mocker) -> None:
    """is_available True con /health ok."""
    import urllib.request

    class _Resp:
        status = 200

        def read(self):
            return b'{"status": "ok"}'

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    mocker.patch.object(urllib.request, "urlopen", return_value=_Resp())
    assert _client().is_available() is True


def test_is_available_false_when_down(mocker) -> None:
    """Servidor apagado -> False sin lanzar."""
    import urllib.request

    def _boom(*a, **k):
        raise ConnectionError("cerrado")

    mocker.patch.object(urllib.request, "urlopen", side_effect=_boom)
    assert _client().is_available() is False


def test_list_models_ids(mocker) -> None:
    """list_models extrae ids del manifest."""
    import json
    import urllib.request

    payload = {"models": [{"model": "m1"}, {"name": "m2"}]}

    class _Resp:
        status = 200

        def read(self):
            return json.dumps(payload).encode()

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    mocker.patch.object(urllib.request, "urlopen", return_value=_Resp())
    assert _client().list_models() == ["m1", "m2"]


def test_generate_chat_completions(mocker) -> None:
    """generate usa /v1/chat/completions con Bearer solo si hay key."""
    import json
    import urllib.request

    seen: dict = {}

    class _Resp:
        status = 200

        def read(self):
            return json.dumps(
                {"choices": [{"message": {"content": "hola"}}]}
            ).encode()

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def _fake(url_or_req, **kwargs):
        url = url_or_req.full_url if hasattr(url_or_req, "full_url") else url_or_req
        seen["url"] = url
        seen["headers"] = dict(url_or_req.header_items()) if hasattr(url_or_req, "header_items") else {}
        seen["payload"] = json.loads(url_or_req.data.decode())
        return _Resp()

    mocker.patch.object(urllib.request, "urlopen", side_effect=_fake)
    out = _client(api_key="sk-test").generate("m1", "di hola")
    assert out == "hola"
    assert seen["url"].endswith("/v1/chat/completions")
    assert seen["headers"].get("Authorization") == "Bearer sk-test"
    assert seen["payload"]["model"] == "m1"


def test_generate_reasoning_fallback(mocker) -> None:
    """Sin content usa reasoning_content (modelos con reasoning on)."""
    import json
    import urllib.request

    class _Resp:
        status = 200

        def read(self):
            return json.dumps(
                {"choices": [{"message": {"content": "", "reasoning_content": "pienso"}}]}
            ).encode()

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    mocker.patch.object(urllib.request, "urlopen", return_value=_Resp())
    assert _client().generate("m", "hola") == "pienso"


def test_no_hardcoded_key_in_source() -> None:
    """El modulo no contiene keys literales (SEG)."""
    from pathlib import Path

    text = (Path(__file__).resolve().parents[1] / "model_router" / "unsloth_client.py").read_text(encoding="utf-8")
    assert "sk-unsloth-" not in text
    assert "sk-test" not in text


def test_candidate_ports_documented() -> None:
    """Puertos candidatos existen (61767 sesion actual primero si se sabe)."""
    assert 8080 in CANDIDATE_PORTS


def test_error_carries_context(mocker) -> None:
    """HTTP != 200 lanza UnslothError con WHAT."""
    import urllib.request

    class _Resp:
        status = 401

        def read(self):
            return b'{"error": "bad key"}'

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    mocker.patch.object(urllib.request, "urlopen", return_value=_Resp())
    with pytest.raises(UnslothError, match="WHAT"):
        _client().list_models()


def test_empty_prompt_raises() -> None:
    """Prompt vacio falla accionable."""
    with pytest.raises(ValueError, match="WHAT"):
        _client().generate("m", "   ")


def test_file_scheme_rejected_without_network(mocker) -> None:
    """Esquema file: se rechaza antes de urlopen (B310/SSRF)."""
    import urllib.request

    spy = mocker.patch.object(urllib.request, "urlopen", side_effect=AssertionError("no debe haber red"))
    bad = UnslothClient(UnslothConfig(base_url="file:///etc/passwd"))
    with pytest.raises(UnslothError, match="WHAT"):
        bad.list_models()
    spy.assert_not_called()
