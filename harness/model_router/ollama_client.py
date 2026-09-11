"""Cliente HTTP real para la API local de Ollama (localhost:11434).

Permite al harness delegar tareas a modelos locales (minimizando tokens
cloud): generar/chat, embeddings, precarga/descarga de RAM, listado de
modelos, instalacion bajo demanda y consulta de capacidades.

Toda la comunicacion pasa por ``_request``, que centraliza la gestion de
errores HTTP y traduce fallos a :class:`OllamaError` con contexto
WHAT+WHY+WHERE.
"""

from __future__ import annotations

import logging
from typing import Any

import requests

logger = logging.getLogger(__name__)

DEFAULT_BASE_URL = "http://localhost:11434"
DEFAULT_TIMEOUT = 60.0
DEFAULT_KEEP_ALIVE = "5m"
AVAILABILITY_TIMEOUT = 2.0
UNLOAD_KEEP_ALIVE = 0


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


class OllamaError(RuntimeError):
    """Error de comunicacion con la API de Ollama.

    El mensaje incluye contexto accionable: WHAT (que fallo), WHY (causa)
    y WHERE (endpoint HTTP).
    """


class OllamaClient:
    """Cliente HTTP hacia la API REST de Ollama en localhost.

    Args:
        base_url: URL base del servidor Ollama (por defecto localhost:11434).
        timeout: Timeout en segundos para cada peticion HTTP.
    """

    def __init__(self, base_url: str = DEFAULT_BASE_URL, timeout: float = DEFAULT_TIMEOUT) -> None:
        """Inicializa el cliente con la URL base normalizada (sin slash final)."""
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout

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
        """Ejecuta una peticion HTTP contra Ollama y traduce fallos a OllamaError.

        Args:
            method: Verbo HTTP ("GET" o "POST").
            path: Ruta del endpoint (ej. "/api/tags").
            body: Payload JSON opcional para la peticion.
            timeout: Timeout en segundos; si es None usa el del cliente.

        Returns:
            Dict JSON parseado de la respuesta de Ollama.

        Raises:
            OllamaError: Si hay error de conexion, timeout, status HTTP
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
        """Comprueba si la API de Ollama responde usando un timeout corto de 2s.

        Returns:
            True si el endpoint /api/tags respondio correctamente,
            False si hubo cualquier error (incluye Ollama apagado).
        """
        try:
            self._request("GET", "/api/tags", timeout=AVAILABILITY_TIMEOUT)
        except OllamaError as exc:
            logger.debug("Ollama no disponible (WHAT: health check fallido; WHERE: is_available; WHY: %s)", exc)
            return False
        return True

    def list_models(self) -> list[str]:
        """Devuelve los nombres de los modelos instalados en Ollama.

        Returns:
            Lista con los nombres de los modelos (GET /api/tags).

        Raises:
            OllamaError: Si Ollama no responde o devuelve status != 200.
        """
        data = self._request("GET", "/api/tags")
        return [model["name"] for model in data.get("models", []) if model.get("name")]

    def loaded_models(self) -> list[str]:
        """Devuelve los nombres de los modelos actualmente cargados en RAM.

        Returns:
            Lista con los modelos en memoria (GET /api/ps).

        Raises:
            OllamaError: Si Ollama no responde o devuelve status != 200.
        """
        data = self._request("GET", "/api/ps")
        return [model["name"] for model in data.get("models", []) if model.get("name")]

    # ------------------------------------------------------------------
    # Inferencia
    # ------------------------------------------------------------------
    def generate(
        self,
        model: str,
        prompt: str,
        keep_alive: str = DEFAULT_KEEP_ALIVE,
        images: list[str] | None = None,
    ) -> dict[str, Any]:
        """Genera texto con el modelo local (POST /api/generate, sin stream).

        Args:
            model: Nombre del modelo Ollama (ej. "llama3.2:3b").
            prompt: Texto de entrada para el modelo.
            keep_alive: Tiempo que el modelo permanece en RAM ("5m", "0").
            images: Lista opcional de imagenes base64 para modelos vision.

        Returns:
            Dict JSON completo de respuesta de Ollama (incluye "response").

        Raises:
            OllamaError: Si la llamada falla o Ollama reporta "error" sin
                respuesta de texto.
        """
        body: dict[str, Any] = {
            "model": model,
            "prompt": prompt,
            "keep_alive": keep_alive,
            "stream": False,
        }
        if images:
            body["images"] = images
        data = self._request("POST", "/api/generate", body=body)
        error = data.get("error")
        if error and not data.get("response"):
            raise _build_error("Ollama reporto error en generate", str(error), f"POST /api/generate (model={model})")
        return data

    def chat(self, model: str, messages: list[dict], keep_alive: str = DEFAULT_KEEP_ALIVE) -> dict[str, Any]:
        """Mantiene una conversacion con el modelo local (POST /api/chat).

        Args:
            model: Nombre del modelo Ollama.
            messages: Mensajes de chat con formato Ollama
                (ej. [{"role": "user", "content": "hola"}]).
            keep_alive: Tiempo que el modelo permanece en RAM ("5m", "0").

        Returns:
            Dict JSON de respuesta, incluye "message.content".

        Raises:
            OllamaError: Si la llamada falla o Ollama reporta "error".
        """
        body: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "keep_alive": keep_alive,
        }
        data = self._request("POST", "/api/chat", body=body)
        error = data.get("error")
        if error:
            raise _build_error("Ollama reporto error en chat", str(error), f"POST /api/chat (model={model})")
        return data

    def embed(self, model: str, input_text: str | list[str]) -> list[list[float]]:
        """Genera embeddings del texto con el modelo local (POST /api/embed).

        Args:
            model: Nombre del modelo Ollama con capacidad de embedding.
            input_text: Texto unico o lista de textos a vectorizar.

        Returns:
            Lista de vectores de embedding, uno por texto de entrada.

        Raises:
            OllamaError: Si la llamada falla o el modelo no soporta embed.
        """
        body: dict[str, Any] = {
            "model": model,
            "input": input_text,
            "keep_alive": DEFAULT_KEEP_ALIVE,
        }
        data = self._request("POST", "/api/embed", body=body)
        return [[float(value) for value in vector] for vector in data.get("embeddings", [])]

    # ------------------------------------------------------------------
    # Ciclo de vida en RAM
    # ------------------------------------------------------------------
    def warm(self, model: str, keep_alive: str = DEFAULT_KEEP_ALIVE) -> bool:
        """Precarga el modelo en RAM enviando un prompt vacio.

        Args:
            model: Nombre del modelo Ollama a precargar.
            keep_alive: Tiempo que el modelo permanece en RAM ("5m").

        Returns:
            True solo si el modelo quedo cargado (done_reason "load").
            False si la llamada fue exitosa pero no cargo (ej. "stop").

        Raises:
            OllamaError: Si la llamada falla (modelo inexistente, etc.).
        """
        data = self._request(
            "POST",
            "/api/generate",
            body={"model": model, "prompt": "", "keep_alive": keep_alive, "stream": False},
        )
        return data.get("done_reason") == "load"

    def unload(self, model: str) -> bool:
        """Descarga el modelo de RAM usando keep_alive=0 con prompt vacio.

        Args:
            model: Nombre del modelo Ollama a descargar.

        Returns:
            True si la llamada fue exitosa (HTTP 200), indicando que el
            modelo fue marcado para descarga (done_reason "unload").

        Raises:
            OllamaError: Si la llamada falla.
        """
        self._request(
            "POST",
            "/api/generate",
            body={"model": model, "prompt": "", "keep_alive": UNLOAD_KEEP_ALIVE, "stream": False},
        )
        return True

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

    def capabilities(self, model: str) -> list[str]:
        """Devuelve las capacidades del modelo (POST /api/show con body model).

        Args:
            model: Nombre del modelo Ollama a inspeccionar.

        Returns:
            Lista de capacidades soportadas ("completion", "vision", "embed").

        Raises:
            OllamaError: Si la llamada falla o el modelo no existe.
        """
        data = self._request("POST", "/api/show", body={"model": model})
        return list(data.get("capabilities", []))

    def has_capability(self, model: str, capability: str) -> bool:
        """Comprueba si el modelo soporta una capacidad concreta.

        Args:
            model: Nombre del modelo Ollama.
            capability: Capacidad a verificar ("vision", "embed", "completion").

        Returns:
            True si la capacidad esta en la lista del modelo.

        Raises:
            OllamaError: Si no se pueden consultar las capacidades.
        """
        return capability in self.capabilities(model)
