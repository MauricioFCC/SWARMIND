"""unsloth_client.py — Cliente del llama-server de Unsloth Desktop (ADR-0099).

WHAT: Habla con el llama-server que levanta Unsloth Studio (OpenAI-
compatible): discovery dinamico del puerto (/health), /v1/models y
/v1/chat/completions. Sin auth en local (la key del gateway es solo
para acceso remoto); api_key opcional para ese caso.
WHY: Unsloth corre modelos que Ollama no carga (forks/quants propios)
compartiendo los blobs de Ollama (.studio_links); puerto dinamico por
sesion (61767 hoy) -> discovery, nunca puerto hardcodeado.
WHERE: Tier alternativo local cuando Ollama no tiene el modelo;
`check_unsloth.py` para diagnostico.

Uso:
    client = UnslothClient.discover()  # None si no hay servidor
    if client and client.is_available():
        out = client.generate("unsloth/gemma-4-26B", "hola")
"""

from __future__ import annotations

import logging
import urllib.parse
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass

logger = logging.getLogger("harness.model_router.unsloth_client")

#: Esquemas permitidos para urlopen (B310: file:/custom schemes bloqueados).
ALLOWED_URL_SCHEMES: tuple[str, ...] = ("http", "https")

#: Puertos candidatos (el de la sesion actual primero si se conoce).
CANDIDATE_PORTS: tuple[int, ...] = (61767, 8080, 8000, 5000)
#: Timeout corto para discovery/health (segundos).
PROBE_TIMEOUT_S = 2.0
#: Timeout de generacion (los locales piensan; el default es generoso).
DEFAULT_TIMEOUT_S = 180.0


class UnslothError(RuntimeError):
    """Error de comunicacion con Unsloth (WHAT+WHY+WHERE en mensaje)."""


def _validate_http_url(url: str, base_url: str) -> str:
    """Valida esquema http/https antes de urlopen (B310/SSRF).

    Args:
        url: URL completa a validar.
        base_url: Base configurada (contexto del error).

    Returns:
        La misma URL si el esquema es http/https.

    Raises:
        UnslothError: Si el esquema no es http/https (file:, ftp:, etc.).
    """
    scheme = urllib.parse.urlsplit(url).scheme.lower()
    if scheme not in ALLOWED_URL_SCHEMES:
        raise UnslothError(
            f"WHAT: esquema {scheme!r} no permitido en {url}. "
            f"WHY: solo http/https (bloquea file:/custom schemes). "
            f"WHERE: UnslothClient ({base_url})"
        )
    return url


@dataclass(frozen=True)
class UnslothConfig:
    """Config del endpoint (sin secretos hardcodeados).

    Attributes:
        base_url: Base del llama-server (descubierta o por env).
        api_key: Solo para gateway remoto (None = local sin auth).
    """

    base_url: str
    api_key: str | None = None


def _get(path: str, base_url: str, api_key: str | None, timeout: float) -> dict:
    """GET JSON contra el servidor (WHAT+WHY+WHERE en errores).

    Args:
        path: Ruta (ej. "/health").
        base_url: Base del servidor.
        api_key: Bearer opcional (solo remoto).
        timeout: Timeout en segundos.

    Returns:
        Dict parseado.

    Raises:
        UnslothError: Si no responde, timeout o HTTP != 200.
    """
    import json

    url = _validate_http_url(base_url.rstrip("/") + path, base_url)
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    request = urllib.request.Request(url, headers=headers)
    try:
        # URL ya validada a http/https en _validate_http_url (B310/SSRF).
        with urllib.request.urlopen(request, timeout=timeout) as response:  # nosec B310
            if response.status != 200:
                raise UnslothError(
                    f"WHAT: HTTP {response.status} en {url}. "
                    f"WHY: el servidor rechazo la peticion. "
                    f"WHERE: UnslothClient ({base_url})"
                )
            return json.loads(response.read().decode("utf-8"))
    except UnslothError:
        raise
    except Exception as exc:
        raise UnslothError(
            f"WHAT: sin respuesta de {url} ({exc}). "
            f"WHY: servidor apagado o puerto distinto (dinamico por sesion). "
            f"WHERE: UnslothClient ({base_url})"
        ) from exc


def discover_base_url(
    ports: tuple[int, ...] = CANDIDATE_PORTS,
    probe: Callable[[int], bool] | None = None,
) -> str | None:
    """Descubre el llama-server probando /health en puertos candidatos.

    Args:
        ports: Puertos a probar en orden.
        probe: Callable (port) -> True si hay servidor (inyectable tests).

    Returns:
        base_url del primero que responde, o None si ninguno.
    """
    check = probe or (lambda port: _probe_port(port))
    for port in ports:
        try:
            alive = check(port)
        except Exception as exc:  # noqa: BLE001 - un puerto caido no aborta el scan
            logger.debug("unsloth: puerto %d no responde (%s)", port, exc)
            continue
        if alive:
            return f"http://127.0.0.1:{port}"
    return None


def _probe_port(port: int) -> bool:
    """True si /health responde ok en el puerto.

    Args:
        port: Puerto a probar.

    Returns:
        True si hay llama-server vivo.
    """
    try:
        data = _get("/health", f"http://127.0.0.1:{port}", None, PROBE_TIMEOUT_S)
    except UnslothError:
        return False
    return data.get("status") == "ok"


class UnslothClient:
    """Cliente del llama-server de Unsloth (descubierto, no hardcodeado).

    Args:
        config: UnslothConfig con base_url (y api_key solo remoto).
    """

    def __init__(self, config: UnslothConfig) -> None:
        """Guarda la config (sin I/O).

        Args:
            config: Endpoint + key opcional.
        """
        self._config = config

    @classmethod
    def discover(
        cls, ports: tuple[int, ...] = CANDIDATE_PORTS, api_key: str | None = None
    ) -> UnslothClient | None:
        """Descubre el servidor y retorna cliente, o None si no hay.

        Args:
            ports: Puertos candidatos.
            api_key: Solo gateway remoto.

        Returns:
            Cliente listo o None (apagado).
        """
        base_url = discover_base_url(ports)
        if base_url is None:
            logger.info("unsloth: sin servidor (Unsloth apagado o puerto nuevo)")
            return None
        return cls(UnslothConfig(base_url=base_url, api_key=api_key))

    @property
    def base_url(self) -> str:
        """Base URL descubierta."""
        return self._config.base_url

    def is_available(self) -> bool:
        """True si /health responde ok (nunca lanza).

        Returns:
            Disponibilidad del servidor.
        """
        try:
            return _get("/health", self._config.base_url,
                        self._config.api_key, PROBE_TIMEOUT_S).get("status") == "ok"
        except UnslothError:
            return False

    def list_models(self) -> list[str]:
        """Modelos servidos (ids del manifest, pueden ser largos).

        Returns:
            Lista de ids.

        Raises:
            UnslothError: Si el servidor falla.
        """
        data = _get("/v1/models", self._config.base_url,
                    self._config.api_key, PROBE_TIMEOUT_S)
        models = data.get("models", [])
        return [str(m.get("model") or m.get("name") or m) for m in models]

    def generate(
        self, model: str, prompt: str, max_tokens: int = 512,
        timeout_s: float = DEFAULT_TIMEOUT_S,
    ) -> str:
        """Genera via /v1/chat/completions (content o reasoning_content).

        Args:
            model: Id del modelo (tal cual lo anuncia /v1/models).
            prompt: Prompt de usuario (no vacio).
            max_tokens: Tope de salida.
            timeout_s: Timeout (los locales con reasoning tardan).

        Returns:
            Texto (content, o reasoning_content si content vacio).

        Raises:
            ValueError: Si el prompt esta vacio.
            UnslothError: Si el servidor falla.
        """
        if not prompt.strip():
            raise ValueError(
                "WHAT: prompt vacio. "
                "WHY: sin prompt no hay generacion. "
                "WHERE: UnslothClient.generate"
            )
        import json

        body = json.dumps({
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": max_tokens,
        }).encode("utf-8")
        headers = {"Content-Type": "application/json"}
        if self._config.api_key:
            headers["Authorization"] = f"Bearer {self._config.api_key}"
        request = urllib.request.Request(
            _validate_http_url(
                self._config.base_url.rstrip("/") + "/v1/chat/completions",
                self._config.base_url,
            ),
            data=body,
            headers=headers,
        )
        try:
            # URL ya validada a http/https en _validate_http_url (B310/SSRF).
            with urllib.request.urlopen(request, timeout=timeout_s) as response:  # nosec B310
                if response.status != 200:
                    raise UnslothError(
                        f"WHAT: HTTP {response.status} generando. "
                        f"WHY: el servidor rechazo la generacion. "
                        f"WHERE: UnslothClient ({self._config.base_url})"
                    )
                payload = json.loads(response.read().decode("utf-8"))
        except UnslothError:
            raise
        except Exception as exc:
            raise UnslothError(
                f"WHAT: fallo generando ({exc}). "
                f"WHY: servidor caido o timeout. "
                f"WHERE: UnslothClient ({self._config.base_url})"
            ) from exc
        try:
            message = payload["choices"][0]["message"]
        except (KeyError, IndexError, TypeError) as exc:
            raise UnslothError(
                f"WHAT: respuesta sin choices/message. "
                f"WHY: formato inesperado del servidor. "
                f"WHERE: UnslothClient ({self._config.base_url})"
            ) from exc
        content = message.get("content") or ""
        if content:
            return str(content)
        return str(message.get("reasoning_content") or "")
