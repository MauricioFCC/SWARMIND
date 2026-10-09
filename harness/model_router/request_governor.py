"""request_governor.py — Governor de requests locales (anti-tormenta/TDR).

WHAT: serializa la inferencia local (max-1 a la vez), presupuesta el prompt
    contra la ventana del modelo y la VRAM (fail-fast SIN tocar el backend),
    y abre un circuit breaker por modelo tras fallos consecutivos. Evita la
    tormenta observada: opencode reintenta 4x un request de 33.451 tokens
    contra ctx 32.768 (siempre falla) -> prefills largos -> inestabilidad/TDR;
    ademas los swaps rapidos entre modelos distintos desestabilizan la GPU.
WHERE: ``LlamaSwapManager.warm`` (gate + slot antes del POST) y
    ``LocalExecutor`` (slot + admit antes de generar). Singleton compartido
    via ``get_default_governor()`` para que el max-1 sea global.
"""

from __future__ import annotations

import logging
import os
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager

logger = logging.getLogger("harness.model_router.request_governor")

#: VRAM libre (MB) que debe quedar SIEMPRE tras admitir un modelo.
SAFETY_MARGIN_MB = 1500
#: Fallos consecutivos del mismo modelo que abren el circuito.
CB_MAX_FAILURES = 3
#: Segundos que el circuito queda abierto antes de dejar pasar 1 probe.
CB_COOLDOWN_S = 60.0
#: Timeout por defecto al esperar el slot de inferencia (segundos).
DEFAULT_ACQUIRE_TIMEOUT_S = 120.0
#: Reserva de respuesta por defecto al admitir (techo de generacion local).
DEFAULT_RESERVED_TOKENS = 1024

#: Override del margen de VRAM (MB).
ENV_SAFETY_MARGIN_MB = "SWARMIND_VRAM_SAFETY_MARGIN_MB"
#: Override de fallos para abrir el circuito.
ENV_CB_MAX_FAILURES = "SWARMIND_CB_MAX_FAILURES"
#: Override del cooldown del circuito (segundos).
ENV_CB_COOLDOWN_S = "SWARMIND_CB_COOLDOWN_S"
#: Override del timeout de espera del slot (segundos).
ENV_ACQUIRE_TIMEOUT_S = "SWARMIND_GOVERNOR_ACQUIRE_TIMEOUT_S"


def _env_int(name: str, default: int) -> int:
    """Lee un entero de entorno (default si ausente o invalido).

    Args:
        name: Nombre de la variable.
        default: Valor si no existe o no parsea.

    Returns:
        Entero leido o default.
    """
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return int(raw)
    except ValueError:
        logger.warning("request_governor: %s=%r no es entero; uso %s", name, raw, default)
        return default


def _env_float(name: str, default: float) -> float:
    """Lee un float de entorno (default si ausente o invalido).

    Args:
        name: Nombre de la variable.
        default: Valor si no existe o no parsea.

    Returns:
        Float leido o default.
    """
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return float(raw)
    except ValueError:
        logger.warning("request_governor: %s=%r no es float; uso %s", name, raw, default)
        return default


def safety_margin_mb() -> int:
    """Margen de VRAM (MB) efectivo (env o default).

    Returns:
        MB a reservar siempre (minimo 0).
    """
    return max(0, _env_int(ENV_SAFETY_MARGIN_MB, SAFETY_MARGIN_MB))


def estimate_prompt_tokens(text: str) -> int:
    """Estima tokens del prompt como ``ceil(len(bytes UTF-8) / 4)``.

    COTA (no conteo exacto): ~4 chars/token ingles; en codigo/ES/multibyte
    suele SUBestimar, asi que solo sirve como gate rapido fail-fast (si esta
    cota ya excede la ventana, el conteo real tambien). El backend valida el
    limite exacto.

    Args:
        text: Prompt a estimar.

    Returns:
        Tokens estimados (>= 0; 0 si vacio).
    """
    if not text:
        return 0
    size = len(text.encode("utf-8"))
    return (size + 3) // 4


class CircuitBreaker:
    """Corta reintentos contra un modelo roto (fail-fast con probe).

    Tras ``max_failures`` fallos consecutivos del MISMO modelo el circuito
    abre por ``cooldown_s`` (``allow`` -> False, sin tocar el backend); al
    vencer deja pasar 1 probe (half-open) y solo ese: si triunfa cierra, si
    falla reabre por otro cooldown.

    Args:
        max_failures: Fallos consecutivos que abren el circuito.
        cooldown_s: Segundos abierto antes del probe.
        time_fn: Reloj monotono inyectable (tests); default ``time.monotonic``.
    """

    def __init__(
        self,
        max_failures: int | None = None,
        cooldown_s: float | None = None,
        time_fn: object | None = None,
    ) -> None:
        """Guarda umbrales (env si no se pasan) e inicializa el estado."""
        self._max = max_failures if max_failures is not None else _env_int(
            ENV_CB_MAX_FAILURES, CB_MAX_FAILURES
        )
        self._cooldown = cooldown_s if cooldown_s is not None else _env_float(
            ENV_CB_COOLDOWN_S, CB_COOLDOWN_S
        )
        self._now = time_fn if callable(time_fn) else time.monotonic  # type: ignore[assignment]
        self._lock = threading.Lock()
        self._failures: dict[str, int] = {}
        self._opened_at: dict[str, float] = {}
        self._probing: set[str] = set()

    def allow(self, model: str) -> bool:
        """True si el modelo puede intentar (cerrado o probe half-open).

        Args:
            model: Id del modelo.

        Returns:
            False si el circuito esta abierto (dentro del cooldown) o si ya
            hay un probe en vuelo para ese modelo.
        """
        with self._lock:
            return self._allow_locked(model)

    def is_open(self, model: str) -> bool:
        """True si el circuito del modelo esta abierto ahora.

        Args:
            model: Id del modelo.

        Returns:
            True si hay ventana de cooldown activa (sin contar probes).
        """
        with self._lock:
            return self._is_open_locked(model)

    def record_success(self, model: str) -> None:
        """Cierra el circuito del modelo (resetea fallos y probes).

        Args:
            model: Id del modelo que triunfo.
        """
        with self._lock:
            self._failures.pop(model, None)
            self._opened_at.pop(model, None)
            self._probing.discard(model)

    def record_failure(self, model: str) -> None:
        """Suma un fallo; abre el circuito al llegar al umbral.

        Args:
            model: Id del modelo que fallo.
        """
        with self._lock:
            count = self._failures.get(model, 0) + 1
            self._failures[model] = count
            self._probing.discard(model)
            if count >= max(1, self._max):
                self._opened_at[model] = self._now()

    def _allow_locked(self, model: str) -> bool:
        """Evalua el permiso asumiendo el lock tomado (ver ``allow``)."""
        if self._failures.get(model, 0) < max(1, self._max):
            return True
        opened = self._opened_at.get(model)
        if opened is None:
            return True
        if self._now() - opened < max(0.0, self._cooldown):
            return False
        if model in self._probing:
            return False
        self._probing.add(model)
        return True

    def _is_open_locked(self, model: str) -> bool:
        """Dice si hay cooldown activo asumiendo el lock tomado."""
        if self._failures.get(model, 0) < max(1, self._max):
            return False
        opened = self._opened_at.get(model)
        if opened is None:
            return False
        return self._now() - opened < max(0.0, self._cooldown)


class RequestGovernor:
    """Serializa + presupuesta + protege la inferencia local (thread-safe).

    Un ``threading.Semaphore(1)`` garantiza max-1 inferencia local a la vez
    (evita swaps rapidos entre modelos). ``admit`` rechaza fail-fast los
    requests imposibles (prompt > ventana o VRAM insuficiente) SIN tocar el
    backend, devolviendo un motivo accionable para que el llamador NO
    reintente lo mismo. El ``CircuitBreaker`` interno corta el modelo roto.

    Args:
        safety_margin_mb: VRAM a reservar siempre (None = env o 1500).
        acquire_timeout_s: Espera maxima del slot (None = env o 120s).
        breaker: CircuitBreaker inyectable (None = uno nuevo por defecto).
        semaphore: Semaforo inyectable (None = el GLOBAL de clase: max-1 en
            todo el proceso aunque haya varios governors/componentes).
    """

    #: Semaforo GLOBAL de proceso (max-1 inferencia local a la vez entre
    #: managers y ejecutores que no inyecten uno propio). El breaker, en
    #: cambio, es por instancia (conteo de fallos hermetico por componente).
    _global_sem: threading.Semaphore | None = None
    _global_sem_lock = threading.Lock()

    def __init__(
        self,
        safety_margin_mb: int | None = None,
        acquire_timeout_s: float | None = None,
        breaker: CircuitBreaker | None = None,
        semaphore: threading.Semaphore | None = None,
    ) -> None:
        """Inicializa semaforo (global si no se inyecta), margen y breaker."""
        self._margin = safety_margin_mb if safety_margin_mb is not None else _env_int(
            ENV_SAFETY_MARGIN_MB, SAFETY_MARGIN_MB
        )
        self._timeout = (
            acquire_timeout_s
            if acquire_timeout_s is not None
            else _env_float(ENV_ACQUIRE_TIMEOUT_S, DEFAULT_ACQUIRE_TIMEOUT_S)
        )
        self._sem = semaphore if semaphore is not None else self._shared_sem()
        self._breaker = breaker if breaker is not None else CircuitBreaker()

    @classmethod
    def _shared_sem(cls) -> threading.Semaphore:
        """Semaforo global del proceso (creacion thread-safe).

        Returns:
            El ``threading.Semaphore(1)`` compartido por todos los governors
            que no inyecten uno propio.
        """
        if cls._global_sem is None:
            with cls._global_sem_lock:
                if cls._global_sem is None:
                    cls._global_sem = threading.Semaphore(1)
        assert cls._global_sem is not None
        return cls._global_sem

    @property
    def breaker(self) -> CircuitBreaker:
        """CircuitBreaker interno (para inspeccion/tests)."""
        return self._breaker

    def acquire(self, timeout: float | None = None) -> bool:
        """Toma el slot de inferencia (max-1 local a la vez).

        Args:
            timeout: Espera maxima en segundos (None = default del governor).

        Returns:
            True si obtuvo el slot; False si vencio el timeout.
        """
        wait = self._timeout if timeout is None else timeout
        return self._sem.acquire(timeout=max(0.0, wait))

    def release(self) -> None:
        """Libera el slot de inferencia (siempre parear con ``acquire``)."""
        self._sem.release()

    @contextmanager
    def slot(self, timeout: float | None = None) -> Iterator[bool]:
        """Context manager del slot: ``with gov.slot() as ok: ...``.

        Args:
            timeout: Espera maxima en segundos (None = default).

        Yields:
            True si se obtuvo el slot (hacer la inferencia); False si
            vencio (el llamador debe derivar a cloud sin reintentar).
        """
        held = self.acquire(timeout)
        try:
            yield held
        finally:
            if held:
                self.release()

    def allow(self, model: str) -> bool:
        """True si el circuito del modelo deja intentar (ver CircuitBreaker).

        Args:
            model: Id del modelo.

        Returns:
            False si el modelo esta en cooldown o con probe en vuelo.
        """
        return self._breaker.allow(model)

    def record_success(self, model: str) -> None:
        """Registra exito del modelo (cierra su circuito).

        Args:
            model: Id del modelo que triunfo.
        """
        self._breaker.record_success(model)

    def record_failure(self, model: str) -> None:
        """Registra fallo del modelo (puede abrir su circuito).

        Args:
            model: Id del modelo que fallo.
        """
        self._breaker.record_failure(model)

    def admit(
        self,
        prompt_tokens: int,
        model_ctx: int,
        free_vram_mb: int | None,
        model_footprint_mb: int,
        *,
        reserved_tokens: int = DEFAULT_RESERVED_TOKENS,
        unloadable_mb: int = 0,
    ) -> tuple[bool, str]:
        """Decide fail-fast si el request puede intentar en local.

        Rechaza SIN tocar el backend (el llamador NO debe reintentar lo
        mismo: achicar el prompt o cambiar de modelo/tier): (1) si el prompt
        no cabe en ``model_ctx - reserved_tokens``; (2) si
        ``free + unloadable < footprint + margen``. Sin dato de VRAM (None)
        se permite (ciego, como ``vram_guard``).

        Args:
            prompt_tokens: Tokens estimados del prompt (>= 0).
            model_ctx: Ventana del modelo en tokens (> 0).
            free_vram_mb: VRAM libre (None = desconocida -> se permite).
            model_footprint_mb: VRAM estimada del modelo en MB.
            reserved_tokens: Reserva de respuesta dentro de la ventana.
            unloadable_mb: VRAM liberable descargando residentes.

        Returns:
            (True, motivo-ok) si puede intentar; (False, "WHAT... accionable
            + NO reintentar") si debe derivar a cloud.
        """
        if prompt_tokens < 0 or model_ctx <= 0 or model_footprint_mb <= 0:
            return False, self._invalid_reason(prompt_tokens, model_ctx, model_footprint_mb)
        usable = model_ctx - max(0, reserved_tokens)
        if prompt_tokens > usable:
            return False, self._ctx_reason(prompt_tokens, model_ctx, usable)
        if free_vram_mb is None:
            return True, "OK: admitido sin dato de VRAM (ciego, no reintentar a ciegas en loop)"
        need = model_footprint_mb + max(0, self._margin)
        avail = free_vram_mb + max(0, unloadable_mb)
        if avail < need:
            return False, self._vram_reason(free_vram_mb, unloadable_mb, need)
        return True, f"OK: admitido (prompt {prompt_tokens}<=ctx {usable}, vram {avail}>={need} MB)"

    def _invalid_reason(self, prompt_tokens: int, model_ctx: int, footprint: int) -> str:
        """Motivo accionable para parametros invalidos (no reintentar igual)."""
        return (
            f"WHAT: presupuesto invalido (prompt={prompt_tokens}, ctx={model_ctx}, "
            f"footprint={footprint}). WHY: valores fuera de rango. "
            "WHERE: RequestGovernor.admit. NO reintentar: corregir el llamador."
        )

    def _ctx_reason(self, prompt_tokens: int, model_ctx: int, usable: int) -> str:
        """Motivo accionable cuando el prompt excede la ventana."""
        return (
            f"WHAT: prompt de ~{prompt_tokens} tokens no cabe en ctx {model_ctx} "
            f"(util {usable} con reserva). WHY: el backend lo rechazaria siempre "
            "(prefill imposible). WHERE: RequestGovernor.admit. "
            "NO reintentar igual: achicar el prompt (lean/perfil corto) o ir a cloud."
        )

    def _vram_reason(self, free_mb: int, unloadable: int, need: int) -> str:
        """Motivo accionable cuando la VRAM no alcanza con margen."""
        return (
            f"WHAT: VRAM insuficiente (libre {free_mb} + liberable {unloadable} < "
            f"necesarios {need} MB con margen). WHY: cargarlo provocaria swap/OOM/TDR. "
            "WHERE: RequestGovernor.admit. NO reintentar igual: descargar residentes, "
            "usar un modelo menor o ir a cloud."
        )


#: Singleton compartido (el max-1 debe ser GLOBAL entre managers/ejecutores).
_default_governor: RequestGovernor | None = None
_default_lock = threading.Lock()


def get_default_governor() -> RequestGovernor:
    """Devuelve el governor global compartido (creacion thread-safe).

    Returns:
        El ``RequestGovernor`` singleton del proceso.
    """
    global _default_governor
    if _default_governor is None:
        with _default_lock:
            if _default_governor is None:
                _default_governor = RequestGovernor()
    return _default_governor
