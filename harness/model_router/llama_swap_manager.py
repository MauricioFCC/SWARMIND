"""llama_swap_manager.py — ciclo de vida de llama.cpp/llama-swap (:11434).

WHAT: garantiza que el backend local (llama-swap, que a su vez lanza
``llama-server`` por modelo) este arriba y sirva el modelo que el harness
necesita, hablando protocolo OpenAI en ``http://127.0.0.1:11434``. Expone
``ensure_running`` (arranca el backend si cayo, single-flight e idempotente),
``ensure_model`` (arranca + hace swap/precalienta el modelo pedido),
``is_ready`` (readiness sobre ``/health`` o ``/running``) y ``unload_all``
(libera VRAM).
WHY: el backend puede no estar arriba (PC recien encendido, proceso caido) y
el harness debe poder subirlo solo; y como en 8GB dos modelos no caben, el
swap de llama-swap + el gate de VRAM evitan la colision/TDR historica
(VIDEO_TDR_FAILURE 0x116). Un ``threading.Lock`` de clase serializa el
arranque (elimina el race TOCTOU de doble spawn) y un retry con backoff
exponencial + jitter absorbe los arranques lentos del proxy. El autostart de
sesion cubre el caso normal y este manager el caso degradado.
WHERE: ``LocalExecutor`` (antes de generar), ``run.py`` (composicion) y
``scripts/llama_boot.py`` (autostart). La config (URL, launcher, timeouts y
politica de retry) se resuelve via ``backend_config.BackendConfig.from_env()``
(SSOT) para no duplicar defaults.
"""

from __future__ import annotations

import logging
import random
import threading
import time
from pathlib import Path

import requests

from harness.model_router.backend_config import (
    DEFAULT_BASE_URL,
    DEFAULT_LAUNCHER,
    DEFAULT_POLL_INTERVAL_S,
    DEFAULT_RETRY_ATTEMPTS,
    DEFAULT_RETRY_BACKOFF_S,
    DEFAULT_START_TIMEOUT_S,
    ENV_BASE_URL,
    ENV_BASE_URL_LEGACY,
    ENV_LAUNCHER,
    BackendConfig,
)
from harness.model_router.backend_launcher import (
    BackendLaunchError,
    build_launch_command,
    spawn_detached,
)

logger = logging.getLogger("harness.model_router.llama_swap_manager")

#: Re-export intencional del SSOT: mantiene imports historicos de compatibilidad
#: (tests/llamadores referencian estos nombres desde este modulo).
__all__ = [
    "DEFAULT_BASE_URL",
    "DEFAULT_LAUNCHER",
    "ENV_BASE_URL",
    "ENV_BASE_URL_LEGACY",
    "ENV_LAUNCHER",
    "BackendConfig",
    "LlamaSwapConfig",
    "LlamaSwapError",
    "LlamaSwapManager",
    "resolve_config",
]

#: Alias retrocompatible: llamadores/tests usaban ``LlamaSwapConfig``.
LlamaSwapConfig = BackendConfig

#: Defaults re-exportados desde el SSOT (compat de imports historicos).
START_TIMEOUT_S = DEFAULT_START_TIMEOUT_S
POLL_INTERVAL_S = DEFAULT_POLL_INTERVAL_S
RETRY_ATTEMPTS = DEFAULT_RETRY_ATTEMPTS
RETRY_BACKOFF_S = DEFAULT_RETRY_BACKOFF_S

#: Endpoints OpenAI-compatibles y propios de llama-swap.
MODELS_PATH = "/v1/models"
CHAT_COMPLETIONS_PATH = "/v1/chat/completions"
RUNNING_PATH = "/running"
HEALTH_PATH = "/health"
UNLOAD_PATH = "/api/models/unload"

#: Timeout del health check (debe ser corto: se llama en cada arranque).
HEALTH_TIMEOUT_S = 3.0
#: Tokens del precalentamiento (solo fuerza la carga del modelo, no genera).
WARM_MAX_TOKENS = 1
#: Base del crecimiento exponencial del backoff (``base * 2**intento``).
_BACKOFF_GROWTH = 2
#: Endpoints de diagnostico que cuentan como readiness (en orden de sondeo).
_READINESS_PROBES = (HEALTH_PATH, RUNNING_PATH)


class LlamaSwapError(RuntimeError):
    """Error de comunicacion o ciclo de vida con llama-swap.

    El mensaje incluye contexto accionable WHAT (que fallo), WHY (causa) y
    WHERE (endpoint o launcher).
    """


def resolve_config() -> BackendConfig:
    """Resuelve la config del backend desde el entorno (SSOT backend_config).

    Returns:
        BackendConfig con base_url/launcher/timeouts/retry efectivos.

    Raises:
        ValueError: Si una combinacion de entorno viola las invariantes.
    """
    return BackendConfig.from_env()


class LlamaSwapManager:
    """Gestiona el ciclo de vida del backend local llama.cpp/llama-swap.

    Args:
        config: Configuracion del backend (None = resolver del entorno).
    """

    #: Lock de clase: one backend -> un solo arranque concurrente (single-flight).
    _start_lock: threading.Lock = threading.Lock()

    def __init__(self, config: LlamaSwapConfig | None = None) -> None:
        """Guarda la config efectiva (sin I/O)."""
        self._config = config if config is not None else resolve_config()

    @property
    def base_url(self) -> str:
        """Base URL del proxy llama-swap."""
        return self._config.base_url

    @property
    def launcher(self) -> Path | None:
        """Ruta del launcher idempotente (None si no se configuro)."""
        return self._config.launcher

    @staticmethod
    def _dispatch(
        method: str, url: str, json_body: dict | None, timeout: float
    ) -> requests.Response:
        """Ejecuta GET o POST segun ``method`` (aislado para test/extender).

        Args:
            method: "GET" o "POST".
            url: URL completa del endpoint.
            json_body: Cuerpo JSON para POST (ignorado en GET).
            timeout: Timeout del intento en segundos.

        Returns:
            La ``requests.Response`` cruda.
        """
        if method.upper() == "GET":
            return requests.get(url, timeout=timeout)
        return requests.post(url, json=json_body, timeout=timeout)

    def _backoff_delay(self, attempt: int) -> float:
        """Delay de backoff exponencial con jitter uniforme ``(0, techo]``.

        Args:
            attempt: Indice del intento fallido (base 0).

        Returns:
            Segundos a dormir; 0.0 si ``retry_backoff_s`` es 0.
        """
        ceiling = self._config.retry_backoff_s * (_BACKOFF_GROWTH**attempt)
        if ceiling <= 0:
            return 0.0
        return random.uniform(0.0, ceiling)

    def _request_with_retry(
        self,
        method: str,
        path: str,
        *,
        json_body: dict | None = None,
        timeout: float,
        attempts: int | None = None,
    ) -> requests.Response:
        """Request con reintentos y backoff exponencial + jitter.

        Args:
            method: "GET" o "POST".
            path: Ruta del endpoint (ej. "/v1/chat/completions").
            json_body: Cuerpo JSON para POST (None en GET).
            timeout: Timeout por intento en segundos.
            attempts: Intentos totales; None = ``config.retry_attempts``.

        Returns:
            La ``requests.Response`` con status 200.

        Raises:
            LlamaSwapError: Si se agotan los intentos (conexion o status != 200).
        """
        url = f"{self._config.base_url}{path}"
        total = attempts if attempts is not None else self._config.retry_attempts
        last_error: LlamaSwapError | None = None
        for attempt in range(total):
            try:
                response = self._dispatch(method, url, json_body, timeout)
                if response.status_code == 200:
                    return response
                last_error = self._http_error(url, response.status_code)
            except requests.RequestException as exc:
                last_error = self._connection_error(url, exc)
            if attempt < total - 1:
                self._sleep_backoff(attempt, total, url)
        raise self._exhausted_error(url, total, last_error) from last_error

    @staticmethod
    def _http_error(url: str, status: int) -> LlamaSwapError:
        """Construye el error accionable de una respuesta con status != 200."""
        return LlamaSwapError(
            f"WHAT: HTTP {status} en {url}. "
            "WHY: el backend rechazo la peticion. "
            f"WHERE: LlamaSwapManager._request_with_retry ({url})"
        )

    @staticmethod
    def _connection_error(url: str, exc: Exception) -> LlamaSwapError:
        """Construye el error accionable de una falla de conexion."""
        return LlamaSwapError(
            f"WHAT: sin respuesta de {url} ({exc}). "
            "WHY: el backend no esta arriba o el puerto esta ocupado. "
            f"WHERE: LlamaSwapManager._request_with_retry ({url})"
        )

    @staticmethod
    def _exhausted_error(url: str, total: int, last_error: Exception | None) -> LlamaSwapError:
        """Construye el error final cuando se agotan los reintentos."""
        return LlamaSwapError(
            f"WHAT: agotados {total} intentos contra {url}. "
            f"WHY: ultimo fallo: {last_error}. "
            f"WHERE: LlamaSwapManager._request_with_retry ({url})"
        )

    def _sleep_backoff(self, attempt: int, total: int, url: str) -> None:
        """Duerme el backoff+jitter del intento fallido y registra el retry.

        Args:
            attempt: Indice del intento fallido (base 0).
            total: Intentos totales configurados.
            url: URL del endpoint (para el log accionable).
        """
        delay = self._backoff_delay(attempt)
        logger.debug(
            "llama_swap_manager: retry %s/%s en %.3fs (%s)", attempt + 1, total, delay, url
        )
        time.sleep(delay)

    def _get(self, path: str, timeout: float) -> dict:
        """GET JSON contra el backend, traduciendo fallos a LlamaSwapError.

        Args:
            path: Ruta del endpoint (ej. "/v1/models").
            timeout: Timeout en segundos.

        Returns:
            Dict JSON de la respuesta.

        Raises:
            LlamaSwapError: Si no hay conexion, timeout, status != 200 o
                JSON invalido.
        """
        url = f"{self._config.base_url}{path}"
        response = self._request_with_retry("GET", path, timeout=timeout, attempts=1)
        try:
            return response.json()
        except ValueError as exc:
            raise LlamaSwapError(
                f"WHAT: respuesta no-JSON de {url} ({exc}). "
                "WHY: el endpoint no es OpenAI-compatible. "
                f"WHERE: LlamaSwapManager._get ({url})"
            ) from exc

    def _probe(self, path: str) -> bool:
        """Sondea best-effort un endpoint de diagnostico (nunca lanza).

        Args:
            path: Ruta a sondear (ej. "/health").

        Returns:
            True si responde 200 con JSON valido; False en cualquier fallo.
        """
        try:
            self._get(path, HEALTH_TIMEOUT_S)
        except LlamaSwapError as exc:
            logger.debug("llama_swap_manager: %s no disponible (%s)", path, exc)
            return False
        return True

    def is_up(self) -> bool:
        """True si ``GET /v1/models`` responde (backend vivo).

        Nunca lanza: es un chequeo de salud, no un contrato de inferencia.

        Returns:
            True si el backend responde 200; False en cualquier fallo.
        """
        try:
            self._get(MODELS_PATH, HEALTH_TIMEOUT_S)
        except LlamaSwapError as exc:
            logger.debug("llama_swap_manager: backend caido (%s)", exc)
            return False
        return True

    def is_ready(self) -> bool:
        """Readiness: liveness (``/v1/models``) + ``/health`` o ``/running``.

        Best-effort: el backend esta listo cuando cumple el contrato OpenAI y
        ademas expone algun endpoint de diagnostico. Si ninguno de los dos
        responde, se considera NO listo (vivo pero no verificable).

        Returns:
            True si el backend esta vivo y expone diagnostico; False si no.
        """
        if not self.is_up():
            return False
        if any(self._probe(path) for path in _READINESS_PROBES):
            return True
        logger.debug("llama_swap_manager: vivo pero sin /health ni /running")
        return False

    def list_models(self) -> list[str]:
        """Ids de modelos servidos (incluye aliases si el config los publica).

        Returns:
            Lista de ids (``data[].id``).

        Raises:
            LlamaSwapError: Si el backend no responde.
        """
        data = self._get(MODELS_PATH, HEALTH_TIMEOUT_S)
        return [str(item["id"]) for item in data.get("data", []) if item.get("id")]

    def loaded_models(self) -> list[str]:
        """Modelos cargados en VRAM (``GET /running``, best-effort).

        Returns:
            Nombres de modelos residentes; [] si el endpoint falla.
        """
        try:
            data = self._get(RUNNING_PATH, HEALTH_TIMEOUT_S)
        except LlamaSwapError as exc:
            logger.debug("llama_swap_manager: /running no disponible (%s)", exc)
            return []
        running = data.get("running", [])
        if not isinstance(running, list):
            return []
        return [
            str(item.get("model") if isinstance(item, dict) else item)
            for item in running
            if item
        ]

    def _launch_command(self) -> list[str]:
        """Comando de arranque delegado a ``backend_launcher`` (SSOT).

        Prefiere el binario directo (SILENCIOSO); si no existe, cae al launcher.

        Returns:
            Lista de argumentos para ``subprocess.Popen``.

        Raises:
            LlamaSwapError: Si ni el binario ni el launcher existen.
        """
        try:
            return build_launch_command(self._config)
        except BackendLaunchError as exc:
            raise LlamaSwapError(str(exc)) from exc

    def _spawn(self) -> None:
        """Lanza el backend desacoplado delegando en ``backend_launcher``.

        El proceso no hereda ni abre consola/ventana (multiplataforma), asi que
        el arranque bajo demanda es SILENCIOSO.

        Raises:
            LlamaSwapError: Si no hay binario/launcher o no se puede ejecutar.
        """
        command = self._launch_command()
        try:
            spawn_detached(command, cwd=str(Path(command[0]).parent))
        except BackendLaunchError as exc:
            raise LlamaSwapError(str(exc)) from exc

    def _wait_until_up(self, timeout_s: float) -> bool:
        """Sondea el health hasta que el backend responde o vence el margen.

        Args:
            timeout_s: Margen maximo de espera en segundos.

        Returns:
            True si el backend quedo arriba dentro del margen.
        """
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            if self.is_up():
                return True
            time.sleep(self._config.poll_interval_s)
        return False

    def ensure_running(self) -> bool:
        """Garantiza el backend arriba: no-op si responde, si no lo lanza.

        Single-flight: el lock de clase serializa los llamadores, de modo que
        dos hilos concurrentes no lanzan dos ``llama-swap`` (race TOCTOU). El
        segundo espera al primero y, al verlo arriba, no arranca nada.

        Returns:
            True si el backend quedo disponible; False si no arranco a tiempo.
        """
        with self._start_lock:
            if self.is_up():
                logger.debug(
                    "llama_swap_manager: backend ya arriba en %s", self._config.base_url
                )
                return True
            try:
                logger.info(
                    "llama_swap_manager: backend caido, lanzando %s", self._config.launcher
                )
                self._spawn()
            except LlamaSwapError as exc:
                logger.warning("llama_swap_manager: no se pudo lanzar el backend (%s)", exc)
                return False
            if self._wait_until_up(self._config.start_timeout_s):
                logger.info("llama_swap_manager: backend arriba en %s", self._config.base_url)
                return True
            logger.warning(
                "llama_swap_manager: backend no respondio tras %ss",
                self._config.start_timeout_s,
            )
            return False

    def warm(self, model: str) -> bool:
        """Precalienta un modelo forzando su carga (POST chat, 1 token).

        llama-swap carga el modelo al recibir una peticion proxied; el
        ``/v1/models`` no lo carga. Un chat minimo lo sube a VRAM y verifica
        que el swap (descarga del anterior) funciona. Reintenta con backoff.

        Args:
            model: Id del modelo (canonico o alias) a precargar.

        Returns:
            True si el backend acepto la peticion; False si fallo.

        Raises:
            LlamaSwapError: Si ``model`` esta vacio.
        """
        if not model.strip():
            raise LlamaSwapError(
                "WHAT: model vacio. "
                "WHY: sin id no hay modelo que precargar. "
                "WHERE: LlamaSwapManager.warm"
            )
        body = {
            "model": model,
            "messages": [{"role": "user", "content": "."}],
            "max_tokens": WARM_MAX_TOKENS,
            "stream": False,
        }
        try:
            self._request_with_retry(
                "POST",
                CHAT_COMPLETIONS_PATH,
                json_body=body,
                timeout=self._config.start_timeout_s,
            )
        except LlamaSwapError as exc:
            logger.warning("llama_swap_manager: warm %s fallo (%s)", model, exc)
            return False
        logger.info("llama_swap_manager: modelo %s precargado", model)
        return True

    def verify_swap(self, model: str) -> bool:
        """Verifica best-effort que ``model`` quedo residente tras el warm.

        Si ``/running`` no esta o falla, NO se bloquea: se asume exito porque
        el warm ya confirmo que el backend sirvio la peticion.

        Args:
            model: Id del modelo que deberia estar cargado.

        Returns:
            True si el modelo figura en ``/running`` o el endpoint no esta;
            False solo si ``/running`` responde y el modelo no aparece.
        """
        loaded = self.loaded_models()
        if not loaded:
            logger.debug("llama_swap_manager: /running vacio o ausente; verify best-effort")
            return True
        if model in loaded:
            logger.info("llama_swap_manager: swap verificado, %s residente", model)
            return True
        logger.warning(
            "llama_swap_manager: WHAT: %s no figura en /running %s. "
            "WHY: el swap pudo no completar. "
            "WHERE: LlamaSwapManager.verify_swap",
            model,
            loaded,
        )
        return False

    def ensure_model(self, model: str, warm: bool = True) -> bool:
        """Garantiza backend arriba y (si ``warm``) el modelo pedido residente.

        Suicheo robusto: si ``model`` ya esta cargado no se recarga; si hay
        otro modelo residente se descarga (best-effort) antes de precargar,
        para evitar la colision de VRAM en 8GB. ``verify_swap`` es best-effort
        y nunca bloquea el exito del warm.

        Args:
            model: Id del modelo a servir (canonico o alias).
            warm: True = fuerza carga/swap; False = solo garantiza el backend.

        Returns:
            True si el backend esta arriba y (si ``warm``) el modelo cargo.
        """
        if not self.ensure_running():
            return False
        if not warm:
            return True
        loaded = self.loaded_models()
        if model in loaded:
            logger.info("llama_swap_manager: %s ya cargado; sin recarga", model)
            return True
        if loaded:
            logger.info("llama_swap_manager: descargando residentes %s antes de %s", loaded, model)
            self.unload_all()
        if not self.warm(model):
            return False
        self.verify_swap(model)
        return True

    def unload_all(self) -> bool:
        """Descarga todos los modelos residentes (libera VRAM).

        Returns:
            True si el backend acepto la orden; False si fallo o no la expone.
        """
        url = f"{self._config.base_url}{UNLOAD_PATH}"
        # Timeout largo: descargar un 9B de VRAM tarda mas que un health check.
        try:
            response = requests.post(url, timeout=self._config.start_timeout_s)
        except requests.RequestException as exc:
            logger.warning("llama_swap_manager: unload_all fallo (%s)", exc)
            return False
        if response.status_code != 200:
            logger.warning("llama_swap_manager: unload_all -> HTTP %s", response.status_code)
            return False
        logger.info("llama_swap_manager: VRAM liberada (unload all)")
        return True
