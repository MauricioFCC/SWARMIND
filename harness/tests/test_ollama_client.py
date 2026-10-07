"""Tests unitarios para OllamaClient (harness/model_router/ollama_client.py).

Escritos SOLO contra el contrato público (patrón test-writer): los módulos de
delegación local Ollama se están creando en paralelo y estos tests fijan el
comportamiento esperado; si la implementación no cumple el contrato, fallan.

Todos los tests corren con Ollama APAGADO: el transporte requests se mockea
a nivel de requests.request (intercepta también get/post) — cero llamadas
reales de red.
"""

from __future__ import annotations

from typing import Any

import pytest
import requests
from pytest_mock import MockerFixture

from harness.model_router.ollama_client import (
    DEFAULT_BASE_URL,
    DEFAULT_KEEP_ALIVE,
    DEFAULT_TIMEOUT,
    OllamaClient,
    OllamaError,
)


class _FakeResponse:
    """Respuesta HTTP simulada que emula requests.Response sin red real.

    Args:
        status_code: código HTTP de la respuesta.
        payload: diccionario que devolverá ``json()``.

    Attributes:
        status_code: código HTTP simulado.
        ok: True si el status es 2xx/3xx (compatible con requests.Response).
    """

    def __init__(self, status_code: int, payload: dict) -> None:
        self.status_code = status_code
        self._payload = payload
        self.text = payload.get("text", "") if isinstance(payload, dict) else str(payload)

    @property
    def ok(self) -> bool:
        """True para status 2xx/3xx, igual que requests.Response."""
        return 200 <= self.status_code < 400

    def json(self) -> dict:
        """Devuelve el payload JSON simulado."""
        return self._payload

    def raise_for_status(self) -> None:
        """Lanza HTTPError para status >= 400, igual que requests.Response."""
        if self.status_code >= 400:
            raise requests.exceptions.HTTPError(f"HTTP {self.status_code}")


def _client() -> OllamaClient:
    """Crea un OllamaClient apuntando a la URL local por defecto."""
    return OllamaClient(base_url=DEFAULT_BASE_URL)


def _patch_transport(
    mocker: MockerFixture,
    response: _FakeResponse | None = None,
    error: Exception | None = None,
) -> Any:
    """Intercepta requests.request; cero llamadas reales a Ollama.

    Args:
        mocker: fixture de pytest-mock.
        response: respuesta simulada si el test espera éxito HTTP.
        error: excepción a lanzar si el test simula fallo de red.

    Returns:
        El mock del transporte requests para inspeccionar llamadas.
    """
    mock_request = mocker.patch("requests.request")
    if error is not None:
        mock_request.side_effect = error
    else:
        mock_request.return_value = response
    return mock_request


_HTTP_METHODS = {"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"}


def _url_of(call: Any) -> str:
    """Extrae la URL de una llamada a requests (get/post/request).

    Args:
        call: objeto _Call de un MagicMock.

    Returns:
        La URL objetivo de la llamada.
    """
    args = call.args
    if not args:
        return call.kwargs.get("url", "")
    if len(args) >= 2 and args[0] in _HTTP_METHODS:
        return args[1]
    return args[0]


# ---------------------------------------------------------------------------
# Contrato público: constantes
# ---------------------------------------------------------------------------


def test_default_constants_match_public_contract() -> None:
    """Verifica que las constantes públicas del contrato existen con sus valores."""
    assert DEFAULT_BASE_URL == "http://localhost:11434"
    assert DEFAULT_TIMEOUT == 60.0
    assert DEFAULT_KEEP_ALIVE == "0"


# ---------------------------------------------------------------------------
# Disponibilidad
# ---------------------------------------------------------------------------


def test_is_available_returns_true_when_models_ok(mocker: MockerFixture) -> None:
    """is_available → True cuando GET /v1/models responde 200."""
    mock_request = _patch_transport(mocker, response=_FakeResponse(200, {"data": []}))
    assert _client().is_available() is True
    assert _url_of(mock_request.call_args).endswith("/v1/models")


def test_is_available_returns_false_on_connection_error(mocker: MockerFixture) -> None:
    """is_available → False cuando la conexión falla (ConnectionError)."""
    _patch_transport(
        mocker,
        error=requests.exceptions.ConnectionError("ollama down"),
    )
    assert _client().is_available() is False


def test_is_available_returns_false_on_timeout(mocker: MockerFixture) -> None:
    """is_available → False cuando la petición expira (Timeout)."""
    _patch_transport(mocker, error=requests.exceptions.Timeout("slow"))
    assert _client().is_available() is False


# ---------------------------------------------------------------------------
# Listado de modelos
# ---------------------------------------------------------------------------


def test_list_models_extracts_ids_from_v1_models(mocker: MockerFixture) -> None:
    """list_models extrae los ids de modelo de GET /v1/models (data[].id)."""
    mock_request = _patch_transport(
        mocker,
        response=_FakeResponse(
            200, {"data": [{"id": "llama3.2:3b"}, {"id": "qwen2.5:14b"}]}
        ),
    )
    names = _client().list_models()
    assert names == ["llama3.2:3b", "qwen2.5:14b"]
    assert _url_of(mock_request.call_args).endswith("/v1/models")


# ---------------------------------------------------------------------------
# generate
# ---------------------------------------------------------------------------


def test_generate_posts_single_user_message_and_returns_text(mocker: MockerFixture) -> None:
    """generate envía un mensaje user a /v1/chat/completions y devuelve el texto."""
    mock_request = _patch_transport(
        mocker,
        response=_FakeResponse(200, {"choices": [{"message": {"content": "hola"}}]}),
    )
    result = _client().generate(model="llama3.2:3b", prompt="di hola")
    assert result == "hola"
    body = mock_request.call_args.kwargs["json"]
    assert body["model"] == "llama3.2:3b"
    assert body["messages"] == [{"role": "user", "content": "di hola"}]
    assert body["keep_alive"] == DEFAULT_KEEP_ALIVE
    assert body["stream"] is False
    assert _url_of(mock_request.call_args).endswith("/v1/chat/completions")


def test_generate_includes_images_when_provided(mocker: MockerFixture) -> None:
    """generate con images → el body incluye la lista de imágenes base64."""
    mock_request = _patch_transport(
        mocker,
        response=_FakeResponse(200, {"choices": [{"message": {"content": "ok"}}]}),
    )
    _client().generate(model="llava:7b", prompt="describe", images=["aGVsbG8=", "d29ybGQ="])
    body = mock_request.call_args.kwargs["json"]
    assert body["images"] == ["aGVsbG8=", "d29ybGQ="]


def test_generate_omits_options_when_none(mocker: MockerFixture) -> None:
    """generate sin options → el body no incluye campos extra ni max_tokens."""
    mock_request = _patch_transport(
        mocker,
        response=_FakeResponse(200, {"choices": [{"message": {"content": "ok"}}]}),
    )
    _client().generate(model="llama3.2:3b", prompt="x")
    body = mock_request.call_args.kwargs["json"]
    assert "max_tokens" not in body
    assert "num_ctx" not in body


def test_generate_forwards_options_when_provided(mocker: MockerFixture) -> None:
    """generate con options → num_predict a max_tokens y num_ctx como campo extra."""
    mock_request = _patch_transport(
        mocker,
        response=_FakeResponse(200, {"choices": [{"message": {"content": "ok"}}]}),
    )
    opts = {"num_ctx": 8192, "num_predict": 256, "temperature": 0.2}
    _client().generate(model="llama3.2:3b", prompt="x", options=opts)
    body = mock_request.call_args.kwargs["json"]
    assert body["max_tokens"] == 256
    assert body["num_ctx"] == 8192
    assert body["temperature"] == 0.2


def test_generate_raises_ollama_error_on_ollama_body_error(mocker: MockerFixture) -> None:
    """generate → OllamaError cuando Ollama responde {"error": ...} en el body."""
    _patch_transport(
        mocker,
        response=_FakeResponse(200, {"error": "model not found"}),
    )
    with pytest.raises(OllamaError):
        _client().generate(model="ghost", prompt="x")


def test_generate_raises_ollama_error_on_non_200_status(mocker: MockerFixture) -> None:
    """generate → OllamaError cuando el status HTTP no es 200."""
    _patch_transport(mocker, response=_FakeResponse(500, {}))
    with pytest.raises(OllamaError):
        _client().generate(model="llama3.2:3b", prompt="x")


def test_generate_raises_ollama_error_without_choices(mocker: MockerFixture) -> None:
    """generate → OllamaError cuando la respuesta no trae choices[0].message."""
    _patch_transport(mocker, response=_FakeResponse(200, {"id": "x"}))
    with pytest.raises(OllamaError):
        _client().generate(model="llama3.2:3b", prompt="x")


def test_generate_returns_empty_string_when_content_is_null(mocker: MockerFixture) -> None:
    """generate → "" cuando choices[0].message.content es null."""
    _patch_transport(
        mocker,
        response=_FakeResponse(200, {"choices": [{"message": {"content": None}}]}),
    )
    assert _client().generate(model="llama3.2:3b", prompt="x") == ""


def test_generate_raises_ollama_error_with_context_on_connection_error(
    mocker: MockerFixture,
) -> None:
    """generate → OllamaError con contexto (WHAT/WHY/WHERE) ante ConnectionError."""
    _patch_transport(
        mocker,
        error=requests.exceptions.ConnectionError("down"),
    )
    with pytest.raises(OllamaError) as exc_info:
        _client().generate(model="llama3.2:3b", prompt="x")
    message = str(exc_info.value)
    assert "connection" in message.lower()
    assert "/v1/chat/completions" in message


# ---------------------------------------------------------------------------
# chat
# ---------------------------------------------------------------------------


def test_chat_posts_messages_and_returns_text(mocker: MockerFixture) -> None:
    """chat envía messages a /v1/chat/completions y devuelve el texto."""
    messages = [{"role": "user", "content": "hola"}]
    mock_request = _patch_transport(
        mocker,
        response=_FakeResponse(
            200, {"choices": [{"message": {"role": "assistant", "content": "adiós"}}]}
        ),
    )
    result = _client().chat(model="llama3.2:3b", messages=messages)
    assert result == "adiós"
    body = mock_request.call_args.kwargs["json"]
    assert body["model"] == "llama3.2:3b"
    assert body["messages"] == messages
    assert _url_of(mock_request.call_args).endswith("/v1/chat/completions")


def test_chat_forwards_options_when_provided(mocker: MockerFixture) -> None:
    """chat con options → num_predict se mapea a max_tokens (contrato OpenAI)."""
    messages = [{"role": "user", "content": "hola"}]
    mock_request = _patch_transport(
        mocker,
        response=_FakeResponse(
            200, {"choices": [{"message": {"role": "assistant", "content": "adiós"}}]}
        ),
    )
    _client().chat(
        model="llama3.2:3b", messages=messages,
        options={"num_predict": 128},
    )
    body = mock_request.call_args.kwargs["json"]
    assert body["max_tokens"] == 128
    assert "options" not in body


# ---------------------------------------------------------------------------
# embed
# ---------------------------------------------------------------------------


def test_embed_returns_list_of_float_lists(mocker: MockerFixture) -> None:
    """embed devuelve list[list[float]] desde {"data": [{"embedding": [...]}]}."""
    _patch_transport(
        mocker,
        response=_FakeResponse(
            200,
            {
                "data": [
                    {"index": 0, "embedding": [0.1, 0.2]},
                    {"index": 1, "embedding": [0.3, 0.4]},
                ]
            },
        ),
    )
    embeddings = _client().embed(model="nomic-embed-text", input_text="hola")
    assert embeddings == [[0.1, 0.2], [0.3, 0.4]]
    assert isinstance(embeddings[0][0], float)


def test_embed_with_string_input_posts_string_body(mocker: MockerFixture) -> None:
    """embed con str → el body envía el texto plano como 'input'."""
    mock_request = _patch_transport(
        mocker,
        response=_FakeResponse(200, {"embeddings": [[0.1]]}),
    )
    _client().embed(model="nomic-embed-text", input_text="hola")
    body = mock_request.call_args.kwargs["json"]
    assert body["input"] == "hola"


def test_embed_with_list_input_posts_list_body(mocker: MockerFixture) -> None:
    """embed con input list[str] → el body envía la lista como 'input'."""
    mock_request = _patch_transport(
        mocker,
        response=_FakeResponse(200, {"embeddings": [[0.1], [0.2]]}),
    )
    _client().embed(model="nomic-embed-text", input_text=["hola", "mundo"])
    body = mock_request.call_args.kwargs["json"]
    assert body["input"] == ["hola", "mundo"]


# ---------------------------------------------------------------------------
# Ciclo de vida: warm / unload / loaded_models / pull
# ---------------------------------------------------------------------------


def test_warm_posts_empty_prompt_and_returns_true_on_load(mocker: MockerFixture) -> None:
    """warm → POST /api/generate con prompt vacío; True si done_reason == 'load'."""
    mock_request = _patch_transport(
        mocker,
        response=_FakeResponse(200, {"done_reason": "load"}),
    )
    assert _client().warm(model="llama3.2:3b") is True
    body = mock_request.call_args.kwargs["json"]
    assert body["model"] == "llama3.2:3b"
    assert body["prompt"] == ""
    assert body["keep_alive"] == DEFAULT_KEEP_ALIVE


def test_warm_returns_false_when_done_reason_not_load(mocker: MockerFixture) -> None:
    """warm → False cuando done_reason no es 'load'."""
    _patch_transport(
        mocker,
        response=_FakeResponse(200, {"done_reason": "stop"}),
    )
    assert _client().warm(model="llama3.2:3b") is False


def test_unload_posts_keep_alive_zero(mocker: MockerFixture) -> None:
    """unload → POST con keep_alive=0 para descargar el modelo de memoria."""
    mock_request = _patch_transport(mocker, response=_FakeResponse(200, {}))
    assert _client().unload(model="llama3.2:3b") is True
    body = mock_request.call_args.kwargs["json"]
    assert body["model"] == "llama3.2:3b"
    assert body["keep_alive"] == 0


def test_loaded_models_extracts_names_from_running(mocker: MockerFixture) -> None:
    """loaded_models extrae nombres de modelo de GET /running (llama-swap)."""
    mock_request = _patch_transport(
        mocker,
        response=_FakeResponse(
            200, {"running": [{"model": "llama3.2:3b", "state": "ready"}]}
        ),
    )
    assert _client().loaded_models() == ["llama3.2:3b"]
    assert _url_of(mock_request.call_args).endswith("/running")


def test_loaded_models_supports_string_list_running(mocker: MockerFixture) -> None:
    """loaded_models acepta la variante {"running": ["m1", "m2"]} de llama-swap."""
    _patch_transport(
        mocker,
        response=_FakeResponse(200, {"running": ["m1", "m2"]}),
    )
    assert _client().loaded_models() == ["m1", "m2"]


def test_loaded_models_returns_empty_when_running_missing(mocker: MockerFixture) -> None:
    """loaded_models devuelve [] sin lanzar si /running no existe (informativo)."""
    _patch_transport(mocker, response=_FakeResponse(404, {"error": "not found"}))
    assert _client().loaded_models() == []


def test_loaded_models_returns_empty_on_connection_error(mocker: MockerFixture) -> None:
    """loaded_models devuelve [] sin lanzar ante ConnectionError (best-effort)."""
    _patch_transport(mocker, error=requests.exceptions.ConnectionError("down"))
    assert _client().loaded_models() == []


def test_pull_posts_stream_false_and_returns_true(mocker: MockerFixture) -> None:
    """pull → POST /api/pull con stream=false y devuelve True."""
    mock_request = _patch_transport(
        mocker,
        response=_FakeResponse(200, {"status": "success"}),
    )
    assert _client().pull(model="llama3.2:3b") is True
    body = mock_request.call_args.kwargs["json"]
    assert body["model"] == "llama3.2:3b"
    assert body["stream"] is False
    assert _url_of(mock_request.call_args).endswith("/api/pull")


# ---------------------------------------------------------------------------
# Capacidades
# ---------------------------------------------------------------------------


def test_capabilities_returns_deterministic_metadata_without_http(
    mocker: MockerFixture,
) -> None:
    """capabilities devuelve metadatos deterministas sin llamar a /api/show."""
    mock_request = _patch_transport(mocker, response=_FakeResponse(200, {}))
    caps = _client().capabilities(model="llava:7b")
    assert caps == {"model": "llava:7b", "backend": "openai-compatible"}
    assert mock_request.call_count == 0


def test_has_capability_checks_metadata_keys(mocker: MockerFixture) -> None:
    """has_capability → True solo si la clave está en capabilities (OpenAI)."""
    _patch_transport(mocker, response=_FakeResponse(200, {}))
    client = _client()
    assert client.has_capability(model="llava:7b", capability="backend") is True
    assert client.has_capability(model="llava:7b", capability="vision") is False


def test_list_models_populates_cache(mocker: MockerFixture) -> None:
    """list_models guarda en cache; is_available reusa sin HTTP (TTL 60s)."""
    mock_request = _patch_transport(
        mocker,
        response=_FakeResponse(200, {"data": [{"id": "qwen3:4b"}]}),
    )
    client = _client()
    assert client.list_models() == ["qwen3:4b"]
    assert client.is_available() is True
    assert mock_request.call_count == 1  # 2da llamada servida por cache


def test_cache_expired_refetches(mocker: MockerFixture) -> None:
    """Cache expirada vuelve a HTTP (TTL vencido)."""
    mock_request = _patch_transport(
        mocker,
        response=_FakeResponse(200, {"data": []}),
    )
    client = _client()
    assert client.is_available() is True
    assert mock_request.call_count == 1
    client._tags_cache = (0.0, [])  # fuerza expiracion (monotonic >> 0)
    assert client.is_available() is True
    assert mock_request.call_count == 2
