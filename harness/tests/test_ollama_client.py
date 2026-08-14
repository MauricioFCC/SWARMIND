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
    assert DEFAULT_KEEP_ALIVE == "5m"


# ---------------------------------------------------------------------------
# Disponibilidad
# ---------------------------------------------------------------------------


def test_is_available_returns_true_when_tags_ok(mocker: MockerFixture) -> None:
    """is_available → True cuando GET /api/tags responde 200."""
    _patch_transport(mocker, response=_FakeResponse(200, {"models": []}))
    assert _client().is_available() is True


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


def test_list_models_extracts_names_from_tags(mocker: MockerFixture) -> None:
    """list_models extrae los nombres de modelo de GET /api/tags."""
    mock_request = _patch_transport(
        mocker,
        response=_FakeResponse(
            200, {"models": [{"name": "llama3.2:3b"}, {"name": "qwen2.5:14b"}]}
        ),
    )
    names = _client().list_models()
    assert names == ["llama3.2:3b", "qwen2.5:14b"]
    assert _url_of(mock_request.call_args).endswith("/api/tags")


# ---------------------------------------------------------------------------
# generate
# ---------------------------------------------------------------------------


def test_generate_posts_correct_body_and_returns_response(mocker: MockerFixture) -> None:
    """generate envía body con model/prompt/keep_alive/stream=false y devuelve dict."""
    mock_request = _patch_transport(
        mocker,
        response=_FakeResponse(200, {"response": "hola"}),
    )
    result = _client().generate(model="llama3.2:3b", prompt="di hola")
    assert result == {"response": "hola"}
    body = mock_request.call_args.kwargs["json"]
    assert body["model"] == "llama3.2:3b"
    assert body["prompt"] == "di hola"
    assert body["keep_alive"] == DEFAULT_KEEP_ALIVE
    assert body["stream"] is False
    assert _url_of(mock_request.call_args).endswith("/api/generate")


def test_generate_includes_images_when_provided(mocker: MockerFixture) -> None:
    """generate con images → el body incluye la lista de imágenes base64."""
    mock_request = _patch_transport(
        mocker,
        response=_FakeResponse(200, {"response": "ok"}),
    )
    _client().generate(model="llava:7b", prompt="describe", images=["aGVsbG8=", "d29ybGQ="])
    body = mock_request.call_args.kwargs["json"]
    assert body["images"] == ["aGVsbG8=", "d29ybGQ="]


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
    assert "/api/generate" in message


# ---------------------------------------------------------------------------
# chat
# ---------------------------------------------------------------------------


def test_chat_posts_messages_and_returns_dict(mocker: MockerFixture) -> None:
    """chat envía messages por POST /api/chat y devuelve el dict de respuesta."""
    messages = [{"role": "user", "content": "hola"}]
    mock_request = _patch_transport(
        mocker,
        response=_FakeResponse(
            200, {"message": {"role": "assistant", "content": "adiós"}}
        ),
    )
    result = _client().chat(model="llama3.2:3b", messages=messages)
    assert result["message"]["content"] == "adiós"
    body = mock_request.call_args.kwargs["json"]
    assert body["model"] == "llama3.2:3b"
    assert body["messages"] == messages
    assert _url_of(mock_request.call_args).endswith("/api/chat")


# ---------------------------------------------------------------------------
# embed
# ---------------------------------------------------------------------------


def test_embed_returns_list_of_float_lists(mocker: MockerFixture) -> None:
    """embed devuelve list[list[float]] desde {"embeddings": [[...]]}."""
    _patch_transport(
        mocker,
        response=_FakeResponse(200, {"embeddings": [[0.1, 0.2], [0.3, 0.4]]}),
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


def test_loaded_models_extracts_names_from_ps(mocker: MockerFixture) -> None:
    """loaded_models extrae nombres de modelo de GET /api/ps."""
    mock_request = _patch_transport(
        mocker,
        response=_FakeResponse(
            200, {"models": [{"name": "llama3.2:3b", "size": 100}]}
        ),
    )
    assert _client().loaded_models() == ["llama3.2:3b"]
    assert _url_of(mock_request.call_args).endswith("/api/ps")


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


def test_capabilities_extracts_from_show(mocker: MockerFixture) -> None:
    """capabilities extrae la lista de capacidades de POST /api/show."""
    mock_request = _patch_transport(
        mocker,
        response=_FakeResponse(200, {"capabilities": ["vision", "chat"]}),
    )
    caps = _client().capabilities(model="llava:7b")
    assert caps == ["vision", "chat"]
    assert _url_of(mock_request.call_args).endswith("/api/show")


def test_has_capability_checks_membership(mocker: MockerFixture) -> None:
    """has_capability → True solo si la capacidad está en la lista de /api/show."""
    _patch_transport(
        mocker,
        response=_FakeResponse(200, {"capabilities": ["vision", "chat"]}),
    )
    client = _client()
    assert client.has_capability(model="llava:7b", capability="vision") is True
    assert client.has_capability(model="llava:7b", capability="tools") is False
