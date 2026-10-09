"""Cliente HTTP del backend local del harness (URL base desde ``BackendConfig``).

NOTA DE MIGRACION: este modulo conserva el nombre ``ollama_client`` y la
clase :class:`OllamaClient` (los llamadores y los tests dependen de ambos),
pero desde 2026 habla la API **OpenAI-compatible** ``/v1`` que exponen
Ollama, llama-server y llama-swap, en lugar de la API nativa ``/api/*``.
Cambiar el protocolo por dentro (patron hexagonal) mantiene el contrato
publico.

Metodos migrados a ``/v1``:

* ``is_available`` y ``list_models`` usan ``GET /v1/models``.
* ``generate`` y ``chat`` usan ``POST /v1/chat/completions``.
* ``capabilities`` devuelve metadatos deterministas (OpenAI no expone
  ``/api/show``).
* ``loaded_models`` usa ``GET /running`` de llama-swap (best-effort).

Los helpers de ciclo de vida no tienen un endpoint OpenAI estandar:

* ``warm`` usa ``POST /v1/chat/completions`` con ``max_tokens=1`` y
  ``stream=False``: fuerza la carga del modelo en llama-swap/llama-server
  (que no exponen ``/api/generate``) y funciona igual sobre Ollama.
* ``unload`` intenta ``POST /api/models/unload/<model>`` (llama-swap) y cae
  a la API nativa de Ollama (``/api/generate`` con ``keep_alive=0``).
* ``embed`` y ``pull`` conservan su endpoint (``/v1/embeddings`` y
  ``/api/pull``) porque OpenAI no define equivalentes al pull.

La opcion ``think`` se traduce a ``chat_template_kwargs.enable_thinking``
(llama.cpp la respeta) sin perder el campo nativo ``think`` de Ollama.

Toda la comunicacion pasa por ``_request``, que centraliza la gestion de
errores HTTP y traduce cualquier ``requests.RequestException`` (incluidos
``InvalidURL``, ``SSLError``, ``TooManyRedirects``, ``ChunkedEncodingError``
y demas subclases) a :class:`OllamaError` con contexto WHAT+WHY+WHERE.
"""

from __future__ import annotations

import logging
import re
from typing import Any, NamedTuple

import requests

from harness.model_router.backend_config import BackendConfig

logger = logging.getLogger(__name__)

#: URL base del backend local derivada del SSOT ``BackendConfig`` (ADR-0098).
#: Lee ``SWARMIND_LOCAL_BASE_URL`` (alias legacy ``SWARMIND_LLAMA_BASE_URL``) o
#: cae al default local ``http://127.0.0.1:11434``. Se conserva el nombre
#: publico historico del contrato.
DEFAULT_BASE_URL = BackendConfig.from_env().base_url
DEFAULT_TIMEOUT = 60.0
#: Residencia por defecto de un modelo en VRAM. "0" = descarga inmediata.
#: En 8GB la residencia acumulada es riesgo de TDR/OOM (BSOD 0x116 2026-10-01):
#: el manifiesto de flota declara "0" en TODOS los tiers; este default lo
#: refleja. Para warm explicito, pasar keep_alive="5m" en la llamada.
DEFAULT_KEEP_ALIVE = "0"
AVAILABILITY_TIMEOUT = 2.0
UNLOAD_KEEP_ALIVE = 0

#: Endpoints OpenAI-compatibles (Ollama /v1, llama-server, llama-swap).
MODELS_PATH = "/v1/models"
CHAT_COMPLETIONS_PATH = "/v1/chat/completions"
EMBEDDINGS_PATH = "/v1/embeddings"
#: Formato de codificacion de embeddings de la API OpenAI ("float" | "base64").
EMBEDDING_ENCODING_FORMAT = "float"
#: Endpoint informativo de llama-swap: modelos cargados en memoria.
RUNNING_PATH = "/running"
#: Identificador del backend que reporta capabilities() (OpenAI no expone show).
BACKEND_NAME = "openai-compatible"
#: Traduccion de opciones Ollama a su campo OpenAI equivalente en el body.
OPTION_ALIASES: dict[str, str] = {"num_predict": "max_tokens"}
#: Endpoint nativo de Ollama (solo como fallback de ``unload``).
GENERATE_PATH = "/api/generate"
#: Endpoint propio de llama-swap para descargar un modelo concreto.
MODELS_UNLOAD_PATH = "/api/models/unload"
#: Warm: un token basta para forzar la carga, no para generar contenido util.
WARM_MAX_TOKENS = 1
#: Prompt minimo del warm (algunos backends ignoran cuerpos vacios).
WARM_PROMPT = "."
#: La opcion nativa `think` de Ollama y su traduccion para llama.cpp.
THINK_OPTION = "think"
CHAT_TEMPLATE_KWARGS = "chat_template_kwargs"
ENABLE_THINKING = "enable_thinking"

#: Envoltorios de razonamiento que se limpian del fallback `reasoning_content`.
_THINK_BLOCK_RE = re.compile(r"<think\b[^>]*>.*?</think\s*>", re.DOTALL | re.IGNORECASE)
_THINK_TAG_RE = re.compile(r"</?think\b[^>]*>", re.IGNORECASE)
_THINKING_LABEL_RE = re.compile(r"^\s*Thinking Process:[ \t]*", re.IGNORECASE)


class _AssistantMessage(NamedTuple):
    """Texto del asistente separado del razonamiento crudo del backend.

    Attributes:
        text: Contenido a devolver al llamador (``content`` o el
            ``reasoning_content`` limpio de envoltorios).
        reasoning_content: ``reasoning_content`` crudo tal cual llego;
            "" si el backend no lo envio.
    """

    text: str
    reasoning_content: str


def _build_error(what: str, why: str, where: str) -> OllamaError:
    """Construye un OllamaError con mensaje que incluye contexto WHAT+WHY+WHERE.

    Args:
        what: Descripcion de que fallo.
        why: Causa raiz del fallo.
        where: Endpoint y metodo HTTP donde ocurrio.

    Returns:
        Excepcion OllamaError lista para lanzar.
    """
    return OllamaError(f"{what} | why: {why} | where: {where}")


def _strip_thinking_wrappers(text: str) -> str:
    """Quita los envoltorios de pensamiento del ``reasoning_content``.

    Los modelos Qwen3.x devuelven el CoT en ``reasoning_content`` y a veces
    lo envuelven en ``<think>...</think>`` o lo prefijan con
    ``Thinking Process:``. Ese envoltorio no es la respuesta: se elimina
    (bloque completo y etiquetas sueltas) antes de exponer el texto. Si el
    CoT no tenia envoltorio, se devuelve intacto.

    Args:
        text: Razonamiento crudo del backend.

    Returns:
        Texto sin bloques ``<think>...</think>``, sin etiquetas ``think``
        sueltas y sin el prefijo ``Thinking Process:``; "" si todo el
        contenido era un envoltorio.
    """
    cleaned = _THINK_BLOCK_RE.sub("", text)
    cleaned = _THINK_TAG_RE.sub("", cleaned)
    cleaned = _THINKING_LABEL_RE.sub("", cleaned)
    return cleaned.strip()


def _extract_message_content(data: dict[str, Any], endpoint: str, model: str) -> _AssistantMessage:
    """Extrae el texto del asistente y su razonamiento del formato OpenAI.

    Usa ``choices[0].message.content`` y, si viene vacio, cae a
    ``reasoning_content`` (mismo patron que ``unsloth_client``): los modelos
    Qwen3.5 con modo pensamiento devuelven el CoT en ``reasoning_content`` y
    dejan ``content`` vacio mientras el presupuesto se agota en el ``<think>``;
    sin este fallback la salida se veia vacia y el harness descartaba el
    resultado local. El ``reasoning_content`` se limpia de sus envoltorios
    (ver ``_strip_thinking_wrappers``); si tras limpiar queda vacio se
    devuelve el crudo para que el llamador decida.

    Args:
        data: JSON de respuesta de ``/v1/chat/completions``.
        endpoint: Endpoint HTTP consultado (contexto de error).
        model: Modelo consultado (contexto de error).

    Returns:
        ``_AssistantMessage`` con el texto a devolver y el
        ``reasoning_content`` crudo ("" si el backend no lo envio).

    Raises:
        OllamaError: Si la respuesta no trae ``choices[0].message``.
    """
    try:
        message = data["choices"][0]["message"]
    except (KeyError, IndexError, TypeError) as exc:
        raise _build_error(
            "Respuesta OpenAI sin choices[0].message", str(exc), f"{endpoint} (model={model})"
        ) from exc
    if not isinstance(message, dict):
        raise _build_error(
            "Respuesta OpenAI sin choices[0].message",
            "message no es un objeto",
            f"{endpoint} (model={model})",
        )
    content = message.get("content") or ""
    reasoning = str(message.get("reasoning_content") or "")
    if content:
        return _AssistantMessage(str(content), reasoning)
    cleaned = _strip_thinking_wrappers(reasoning)
    return _AssistantMessage(cleaned or reasoning, reasoning)


def _apply_think_option(body: dict[str, Any], value: Any) -> None:
    """Traduce la opcion ``think`` al campo que respeta cada backend.

    ``think`` es la opcion nativa de Ollama; llama-server/llama.cpp la
    ignora y solo respeta ``chat_template_kwargs.enable_thinking``. Se
    escriben AMBOS: Ollama obedece ``think`` y llama.cpp obedece
    ``chat_template_kwargs``, sin romper a ninguno.

    Args:
        body: Body a completar; se muta ``think`` y ``chat_template_kwargs``.
        value: Valor booleano solicitado para el razonamiento.
    """
    body[THINK_OPTION] = value
    kwargs = body.get(CHAT_TEMPLATE_KWARGS)
    if not isinstance(kwargs, dict):
        kwargs = {}
    kwargs[ENABLE_THINKING] = bool(value)
    body[CHAT_TEMPLATE_KWARGS] = kwargs


def _apply_options(body: dict[str, Any], options: dict[str, Any] | None) -> None:
    """Fusiona opciones tipo Ollama en un body OpenAI-compatible.

    OpenAI no conoce ``num_ctx``/``num_gpu``/``keep_alive``: viajan como
    campos extra que llama-server/llama-swap ignoran y Ollama respeta.
    ``num_predict`` se traduce al campo estandar ``max_tokens`` y ``think``
    se traduce a ``chat_template_kwargs.enable_thinking`` conservando
    ``think`` para Ollama nativo.

    Args:
        body: Body a completar; se mutan solo las claves presentes.
        options: Opciones del llamador; None o {} no hace nada.
    """
    if not options:
        return
    for key, value in options.items():
        if key == THINK_OPTION:
            _apply_think_option(body, value)
            continue
        body[OPTION_ALIASES.get(key, key)] = value


def _parse_running_models(data: object) -> list[str]:
    """Normaliza las variantes de ``GET /running`` de llama-swap a nombres.

    llama-swap ha devuelto tres formas: ``{"running": ["m1"]}``,
    ``{"running": [{"model": "m1", "state": "ready"}]}`` y ``{"model": "m1"}``.

    Args:
        data: JSON devuelto por ``GET /running`` (puede no ser dict).

    Returns:
        Nombres de modelo cargados; [] si el formato viene vacio o ajeno.
    """
    if not isinstance(data, dict):
        return []
    running = data.get("running")
    if isinstance(running, list):
        names: list[str] = []
        for item in running:
            if isinstance(item, str) and item:
                names.append(item)
            elif isinstance(item, dict) and item.get("model"):
                names.append(str(item["model"]))
        return names
    model = data.get("model")
    return [str(model)] if isinstance(model, str) and model else []


class OllamaError(RuntimeError):
    """Error de comunicacion con la API de Ollama.

    El mensaje incluye contexto accionable: WHAT (que fallo), WHY (causa)
    y WHERE (endpoint HTTP).
    """


class OllamaClient:
    """Cliente HTTP hacia la API REST del backend local (Ollama/llama-swap).

    La URL base sale del SSOT ``BackendConfig`` (``SWARMIND_LOCAL_BASE_URL``),
    de modo que no hay endpoint hardcodeado ni duplicado.

    Args:
        base_url: URL base del backend local; None resuelve
            ``BackendConfig.from_env().base_url`` en cada instancia (permite
            que el entorno cambie el default sin reimportar el modulo).
        timeout: Timeout en segundos para cada peticion HTTP.
    """

    def __init__(self, base_url: str | None = None, timeout: float = DEFAULT_TIMEOUT) -> None:
        """Inicializa el cliente resolviendo la URL base del SSOT y normalizandola.

        Args:
            base_url: URL base explicita; None usa ``BackendConfig.from_env()``.
            timeout: Timeout en segundos para cada peticion HTTP.
        """
        resolved = base_url if base_url is not None else BackendConfig.from_env().base_url
        self._base_url = resolved.rstrip("/")
        self._timeout = timeout
        self._tags_cache: tuple[float, list[str]] | None = None
        self._last_reasoning_content: str | None = None

    @property
    def last_reasoning_content(self) -> str | None:
        """Razonamiento crudo de la ultima generacion (o None si no hubo).

        Se puebla en ``generate``/``chat`` con el ``reasoning_content`` tal
        cual lo envio el backend, sin limpiar. Permite al llamador recuperar
        el CoT cuando el texto devuelto se limpio o quedo vacio.

        Returns:
            ``reasoning_content`` crudo de la ultima respuesta; None si aun
            no se genero nada.
        """
        return self._last_reasoning_content

    def _cached_tags(self, ttl_s: float = 60.0) -> list[str] | None:
        """Modelos cacheados si estan frescos (evita HTTP por routing).

        Args:
            ttl_s: Segundos de validez de la cache.

        Returns:
            Lista cacheada o None si expiro/ausente.
        """
        import time

        if self._tags_cache is None:
            return None
        stamped, models = self._tags_cache
        if time.monotonic() - stamped > ttl_s:
            return None
        return models

    def _store_tags(self, models: list[str]) -> None:
        """Guarda modelos en cache con timestamp.

        Args:
            models: Nombres de modelos instalados.
        """
        import time

        self._tags_cache = (time.monotonic(), list(models))

    # ------------------------------------------------------------------
    # Helper privado centralizado
    # ------------------------------------------------------------------
    def _request(
        self,
        method: str,
        path: str,
        body: dict[str, Any] | None = None,
        timeout: float | None = None,
    ) -> dict[str, Any]:
        """Ejecuta una peticion HTTP contra el backend y traduce fallos a OllamaError.

        Args:
            method: Verbo HTTP ("GET" o "POST").
            path: Ruta del endpoint (ej. "/v1/models").
            body: Payload JSON opcional para la peticion.
            timeout: Timeout en segundos; si es None usa el del cliente.

        Returns:
            Dict JSON parseado de la respuesta de Ollama.

        Raises:
            OllamaError: Si hay error de conexion, timeout, cualquier otra
                ``requests.RequestException`` (InvalidURL, SSLError,
                TooManyRedirects, ChunkedEncodingError...), status HTTP
                distinto de 200 o respuesta JSON invalida.
        """
        url = f"{self._base_url}{path}"
        effective_timeout = self._timeout if timeout is None else timeout
        try:
            response = requests.request(method, url, json=body, timeout=effective_timeout)
        except requests.ConnectionError as exc:
            raise _build_error("ConnectionError al conectar con Ollama", str(exc), f"{method} {url}") from exc
        except requests.Timeout as exc:
            raise _build_error(f"Timeout tras {effective_timeout}s", str(exc), f"{method} {url}") from exc
        except requests.RequestException as exc:
            raise _build_error(
                f"{type(exc).__name__} al comunicarse con el backend",
                str(exc) or "fallo de red no clasificado",
                f"{method} {url}",
            ) from exc
        if response.status_code != 200:
            error_text = self._extract_error(response)
            raise _build_error(f"HTTP {response.status_code}", error_text, f"{method} {url}")
        try:
            return response.json()
        except ValueError as exc:
            raise _build_error("Respuesta JSON invalida", str(exc), f"{method} {url}") from exc

    @staticmethod
    def _extract_error(response: requests.Response) -> str:
        """Extrae el mensaje de error del body de una respuesta fallida de Ollama.

        Args:
            response: Respuesta HTTP de requests con status != 200.

        Returns:
            Mensaje de error de Ollama si el body es JSON con clave "error",
            el texto crudo del body, o un fallback con el status HTTP.
        """
        try:
            error = response.json().get("error")
        except ValueError:
            error = None
        if error:
            return str(error)
        return response.text.strip() or f"HTTP {response.status_code}"

    # ------------------------------------------------------------------
    # Disponibilidad y listado
    # ------------------------------------------------------------------
    def is_available(self) -> bool:
        """Comprueba si la API responde con un timeout corto de 2s.

        Habla la API OpenAI-compatible (GET /v1/models); usa la cache de
        tags si esta fresca (evita 1 HTTP por routing).

        Returns:
            True si GET /v1/models respondio correctamente, False si hubo
            cualquier error (incluye el backend apagado).
        """
        if self._cached_tags() is not None:
            return True
        try:
            self._request("GET", MODELS_PATH, timeout=AVAILABILITY_TIMEOUT)
        except OllamaError as exc:
            logger.debug("Backend no disponible (WHAT: health check fallido; WHERE: is_available; WHY: %s)", exc)
            return False
        return True

    def list_models(self) -> list[str]:
        """Devuelve los ids de los modelos instalados (GET /v1/models).

        Returns:
            Lista con los ids de los modelos (``data[].id``).

        Raises:
            OllamaError: Si el backend no responde o devuelve status != 200.
        """
        data = self._request("GET", MODELS_PATH)
        models = [model["id"] for model in data.get("data", []) if model.get("id")]
        self._store_tags(models)
        return models

    def loaded_models(self) -> list[str]:
        """Devuelve los modelos cargados en RAM (best-effort, nunca lanza).

        Usa ``GET /running`` de llama-swap, que no forma parte del estandar
        OpenAI. Si el backend no lo expone (Ollama nativo, llama-server) o
        falla, devuelve [] sin lanzar: es informacion de diagnostico, no un
        contrato de inferencia.

        Returns:
            Lista de modelos cargados; [] si el endpoint no existe o falla.
        """
        try:
            data = self._request("GET", RUNNING_PATH, timeout=AVAILABILITY_TIMEOUT)
        except OllamaError as exc:
            logger.debug("loaded_models: /running no disponible (%s); se asume []", exc)
            return []
        return _parse_running_models(data)

    # ------------------------------------------------------------------
    # Inferencia
    # ------------------------------------------------------------------
    def generate(
        self,
        model: str,
        prompt: str,
        keep_alive: str = DEFAULT_KEEP_ALIVE,
        images: list[str] | None = None,
        options: dict[str, Any] | None = None,
    ) -> str:
        """Genera texto (POST /v1/chat/completions, sin stream).

        OpenAI no tiene un endpoint /completions fiable en todos los
        backends, asi que un prompt unico viaja como un mensaje de chat
        ``{"role": "user", "content": prompt}``.

        Args:
            model: Id del modelo (ej. "llama3.2:3b").
            prompt: Texto de entrada para el modelo.
            keep_alive: Residencia en RAM; viaja como campo extra (Ollama lo
                respeta; llama-server/llama-swap lo ignoran).
            images: Imagenes base64 opcionales para modelos vision; viajan
                como campo extra "images" del body.
            options: Opciones tipo Ollama por llamada (num_ctx, num_gpu,
                keep_alive, temperature, num_predict, think...). Se fusionan
                en el body: ``num_predict`` -> ``max_tokens``; ``think`` ->
                ``chat_template_kwargs.enable_thinking`` (conservando
                ``think`` nativo); el resto como campos extra. None = defaults
                del modelo.

        Returns:
            Texto generado (``choices[0].message.content``); si viene vacio,
            el ``reasoning_content`` limpio de envoltorios. El crudo queda en
            ``last_reasoning_content``.

        Raises:
            OllamaError: Si la llamada falla o la respuesta no trae contenido.
        """
        body: dict[str, Any] = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "stream": False,
            "keep_alive": keep_alive,
        }
        if images:
            body["images"] = list(images)
        _apply_options(body, options)
        data = self._request("POST", CHAT_COMPLETIONS_PATH, body=body)
        error = data.get("error")
        if error:
            raise _build_error(
                "Backend reporto error en generate", str(error),
                f"POST {CHAT_COMPLETIONS_PATH} (model={model})",
            )
        message = _extract_message_content(data, CHAT_COMPLETIONS_PATH, model)
        self._last_reasoning_content = message.reasoning_content
        return message.text

    def chat(
        self, model: str, messages: list[dict],
        keep_alive: str = DEFAULT_KEEP_ALIVE,
        options: dict[str, Any] | None = None,
    ) -> str:
        """Mantiene una conversacion (POST /v1/chat/completions).

        Args:
            model: Id del modelo.
            messages: Mensajes con formato OpenAI/Ollama
                (ej. [{"role": "user", "content": "hola"}]).
            keep_alive: Residencia en RAM (campo extra).
            options: Opciones por llamada; temperature/max_tokens/seed se
                envian como campos estandar, ``think`` se traduce a
                ``chat_template_kwargs.enable_thinking`` y el resto como
                extra (ver generate()).

        Returns:
            Texto del asistente (``choices[0].message.content``); si viene
            vacio, el ``reasoning_content`` limpio de envoltorios. El crudo
            queda en ``last_reasoning_content``.

        Raises:
            OllamaError: Si la llamada falla o la respuesta no trae contenido.
        """
        body: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "stream": False,
            "keep_alive": keep_alive,
        }
        _apply_options(body, options)
        data = self._request("POST", CHAT_COMPLETIONS_PATH, body=body)
        error = data.get("error")
        if error:
            raise _build_error(
                "Backend reporto error en chat", str(error),
                f"POST {CHAT_COMPLETIONS_PATH} (model={model})",
            )
        message = _extract_message_content(data, CHAT_COMPLETIONS_PATH, model)
        self._last_reasoning_content = message.reasoning_content
        return message.text

    def embed(self, model: str, input_text: str | list[str]) -> list[list[float]]:
        """Genera embeddings del texto con el modelo local (POST /v1/embeddings).

        Migrado de la API nativa de Ollama (`/api/embed`) a la API
        OpenAI-compatible: `input` puede ser texto unico o lista, y la respuesta
        llega en `data[].embedding` indexada por `index`.

        Args:
            model: Nombre del modelo con capacidad de embedding.
            input_text: Texto unico o lista de textos a vectorizar.

        Returns:
            Lista de vectores de embedding, uno por texto de entrada (mismo orden).

        Raises:
            OllamaError: Si la llamada falla o el modelo no soporta embeddings.
        """
        body: dict[str, Any] = {
            "model": model,
            "input": input_text,
            "encoding_format": EMBEDDING_ENCODING_FORMAT,
        }
        data = self._request("POST", EMBEDDINGS_PATH, body=body)
        items = data.get("data", [])
        if not isinstance(items, list):
            return []
        # Orden estable por `index`: la API OpenAI no garantiza el orden de llegada.
        ordered = sorted(items, key=lambda item: item.get("index", 0))
        return [
            [float(value) for value in item.get("embedding", [])]
            for item in ordered
        ]

    # ------------------------------------------------------------------
    # Ciclo de vida en RAM
    # ------------------------------------------------------------------
    def warm(self, model: str, keep_alive: str = DEFAULT_KEEP_ALIVE) -> bool:
        """Precarga el modelo en RAM via POST /v1/chat/completions.

        llama-swap y llama-server no exponen ``/api/generate``, asi que el
        warm usa el endpoint OpenAI con ``max_tokens=1`` y ``stream=False``:
        un token basta para forzar la carga del modelo. ``keep_alive`` viaja
        como campo extra (Ollama lo respeta; llama-swap lo ignora).

        Args:
            model: Nombre del modelo a precargar.
            keep_alive: Tiempo que el modelo permanece en RAM ("5m").

        Returns:
            True si el backend acepto la peticion (HTTP 200), es decir el
            modelo quedo cargado.

        Raises:
            OllamaError: Si la llamada falla (backend caido, modelo
                inexistente o status HTTP distinto de 200).
        """
        body: dict[str, Any] = {
            "model": model,
            "messages": [{"role": "user", "content": WARM_PROMPT}],
            "max_tokens": WARM_MAX_TOKENS,
            "stream": False,
            "keep_alive": keep_alive,
        }
        self._request("POST", CHAT_COMPLETIONS_PATH, body=body)
        return True

    def unload(self, model: str) -> bool:
        """Descarga el modelo de RAM (llama-swap con fallback a Ollama nativo).

        Intenta primero ``POST /api/models/unload/<model>`` (llama-swap),
        que no existe en Ollama nativo; si falla, cae al mecanismo nativo
        ``POST /api/generate`` con ``keep_alive=0``. Asi funciona con
        llama-swap, Ollama y llama-server.

        Args:
            model: Nombre del modelo a descargar.

        Returns:
            True si alguno de los dos backends acepto la descarga.

        Raises:
            OllamaError: Si ni llama-swap ni la API nativa pudieron
                descargar el modelo.
        """
        try:
            self._request("POST", f"{MODELS_UNLOAD_PATH}/{model}")
            return True
        except OllamaError as exc:
            logger.debug(
                "unload: %s no disponible (%s); fallback a %s",
                MODELS_UNLOAD_PATH,
                exc,
                GENERATE_PATH,
            )
        self._unload_native(model)
        return True

    def _unload_native(self, model: str) -> None:
        """Fallback: descarga via /api/generate con keep_alive=0 (Ollama).

        Args:
            model: Nombre del modelo a descargar.

        Raises:
            OllamaError: Si el backend nativo tampoco responde o falla.
        """
        self._request(
            "POST",
            GENERATE_PATH,
            body={"model": model, "prompt": "", "keep_alive": UNLOAD_KEEP_ALIVE, "stream": False},
        )

    # ------------------------------------------------------------------
    # Instalacion y capacidades
    # ------------------------------------------------------------------
    def pull(self, model: str) -> bool:
        """Instala el modelo en Ollama si no esta descargado (POST /api/pull).

        Args:
            model: Nombre del modelo a instalar (ej. "llama3.2:3b").

        Returns:
            True si el modelo quedo disponible (status "success" o exito).

        Raises:
            OllamaError: Si la descarga falla, el modelo no existe o la
                API devuelve status != 200 (incluye 404).
        """
        data = self._request("POST", "/api/pull", body={"model": model, "stream": False})
        error = data.get("error")
        if error:
            raise _build_error("Ollama reporto error en pull", str(error), f"POST /api/pull (model={model})")
        return data.get("status") == "success" or bool(data)

    def capabilities(self, model: str) -> dict[str, Any]:
        """Devuelve metadatos deterministas del modelo (sin endpoint).

        La API OpenAI-compatible no expone un endpoint tipo ``/api/show``,
        por lo que no hay lista real de capacidades. Se devuelve un dict
        minimo y estable para no romper a los llamadores que solo necesitan
        identificar el backend.

        Args:
            model: Id del modelo a inspeccionar.

        Returns:
            Dict con "model" y "backend" ("openai-compatible").
        """
        return {"model": model, "backend": BACKEND_NAME}

    def has_capability(self, model: str, capability: str) -> bool:
        """Comprueba si el modelo expone una clave de capability conocida.

        En OpenAI-compatible no se pueden enumerar capacidades reales; el
        unico dato disponible son las claves de ``capabilities()``.

        Args:
            model: Id del modelo.
            capability: Clave a verificar (ej. "backend").

        Returns:
            True si la clave esta presente en ``capabilities(model)``.
        """
        return capability in self.capabilities(model)
