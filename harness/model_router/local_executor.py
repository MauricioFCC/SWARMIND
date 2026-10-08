"""local_executor.py — Cierra el loop: triviales se EJECUTAN en local (ADR-0077).

WHAT: Ejecuta tareas cerradas (resumir/formatear/extraer/traducir/contar/
convertir/listar) en el modelo local del tier decidido, con allowlist
estricta y fallback a cloud ante cualquier fallo.
WHY: Auditoria 2026-09-08 — la DECISION trivial->local era correcta
(10/10, run.py:420 vivo) pero OllamaClient.generate no tenia callers
productivos: el modelo externo hacia el trabajo y el routing era solo
telemetria. Cerrar el loop convierte triviales en 0 tokens cloud.
WHERE: `run_commands` tras `_apply_model_routing` cuando source == local;
cualquier fan-out de micro-tareas cerradas.

Uso:
    ex = LocalExecutor(OllamaClient(), OllamaTierRouter(client))
    out = ex.execute("resume esto en 2 lineas")
    if out.executed_locally: usar(out.output)  # 0 tokens cloud
"""

from __future__ import annotations

import logging
import re
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

from harness.model_router.fleet_manifest import FLEET
from harness.model_router.gpu_guard import pick_safe_model, safe_num_ctx, should_degrade
from harness.model_router.model_windows import fits_in_window
from harness.model_router.vram_guard import fits_in_vram, footprint_mb, free_vram_mb


def _tier_keep_alive(tiers, tier: object) -> str:
    """keep_alive del tier (default "5m" si el router no lo expone).

    Args:
        tiers: Router con keep_alive_for() opcional.
        tier: Tier decidido.

    Returns:
        keep_alive ("0" descarga inmediata en tiers grandes).
    """
    getter = getattr(tiers, "keep_alive_for", None)
    if getter is None:
        return "5m"
    try:
        return str(getter(tier))
    except (KeyError, AttributeError, TypeError):
        return "5m"


def _fits_vram_for(model: str) -> bool:
    """True si hay VRAM para el modelo (desconocida = permitir).

    Args:
        model: Tag del modelo.

    Returns:
        True si cabe con margen o no hay dato de GPU.
    """
    return fits_in_vram(footprint_mb(model), free_vram_mb())

logger = logging.getLogger("harness.model_router.local_executor")

#: Salida minima aceptable (MetaRoute: verificar al final de la ruta).
MIN_LOCAL_OUTPUT_CHARS = 8
#: Ratio maximo del caracter dominante (degeneracion tipica SLM: "aaaa...").
MAX_REPEAT_RATIO = 0.5
#: Techo de generacion por tarea cerrada (anti-desborde KV: la reserva del
#: gate es RESPONSE_RESERVE_TOKENS; las cerradas son resumentes/cortas).
CLOSED_TASK_NUM_PREDICT = 512
#: Sin reasoning en cerradas: el <think> consume el presupuesto y relentiza
#: (medido: MiniCPM5 vuelca CoT antes de responder); la respuesta directa basta.
CLOSED_TASK_THINK = False
#: Prefijo de tarea cerrada: suprime chachara meta (que agota num_predict
#: y deja la respuesta truncada); el modelo va directo al contenido.
CLOSED_TASK_PREFIX = "Responde de forma directa y breve, sin rodeos: "
#: Tiers generativos validos como destino de degradacion anti-TDR (excluye
#: embedding/vision: no sirven para tareas de texto).
_LOCAL_TEXT_TIERS: tuple[str, ...] = ("fast", "quality", "coding", "reasoning")


def _is_degenerate_output(output: str) -> bool:
    """True si la salida es vacia, enana o repetitiva (verificacion final).

    Barata y sin LLM: las tareas cerradas exigen contenido real; una
    salida degenerada predice alucinacion y debe escalar a cloud.

    Args:
        output: Texto ya generado por el modelo local.

    Returns:
        True si debe descartarse (vacia, <8 chars o repeticion >50%).
    """
    from collections import Counter

    text = output.strip()
    if len(text) < MIN_LOCAL_OUTPUT_CHARS:
        return True
    top_count = Counter(text).most_common(1)[0][1]
    return top_count / len(text) > MAX_REPEAT_RATIO

#: Allowlist de tareas cerradas (substrings ES/EN, documentacion y tests).
CLOSED_TASK_PATTERNS: tuple[str, ...] = (
    "resum", "formatea", "format", "extrae", "extract", "traduce",
    "translat", "cuenta", "count", "convierte", "convert", "lista",
    "list files", "renombra",
)
#: Regex de matching endurecido (B3): exige limite de palabra en el verbo para
#: no matchear por substring ("presume" contiene "resum", pero sin "\b" antes).
_CLOSED_TASK_RE = re.compile(
    r"\b(resum\w*|formate\w*|format\w*|extrae\w*|extract\w*|traduc\w*|"
    r"translat\w*|cuent\w*|count\w*|conviert\w*|convert\w*|list\w*|renombr\w*)\b"
)
#: Falsos positivos conocidos: contienen el verbo como substring sin ser tarea
#: cerrada ("presume", "cuentagotas").
_CLOSED_TASK_FALSE_POSITIVES: tuple[str, ...] = ("presume", "cuentagotas")
#: Senales de contexto financiero/quant: una tarea de dominio financiero NO es
#: cerrada. Sin esto, "position sizing para la cuenta" (donde "cuenta" matchea
#: "cuent\w*" = contar) se clasificaba como cerrada y descartaba TODAS las
#: skills (falso positivo de la sonda adversarial del coordinator).
_FINANCE_CONTEXT_SIGNALS: tuple[str, ...] = (
    "position sizing", "capital", "portfolio", "riesgo", "mandato",
    "stop loss", "drawdown", "alpha", "factor", "backtest", "rebalanceo",
    "asignacion", "asignación",
)
#: Contexto que convierte "cuenta/cuentas" en sustantivo financiero (frente al
#: verbo contar): solo entonces desactiva la clasificacion cerrada.
_FINANCE_ACCOUNT_CONTEXT: tuple[str, ...] = ("fondo", "cartera", "cuenta de")
#: "cuenta"/"cuentas" como palabra (no el verbo "contar\w*").
_FINANCE_ACCOUNT_RE = re.compile(r"\bcuentas?\b")


def _has_finance_context(lowered: str) -> bool:
    """True si la tarea tiene contexto financiero/quant (no es cerrada).

    Desactiva la clasificacion cerrada en tareas de dominio financiero: ni el
    verbo "contar" ni "cuenta" como sustantivo (junto a fondo/cartera/cuenta
    de) deben descartar skills de position sizing, riesgo o cartera.

    Args:
        lowered: Tarea normalizada a minusculas.

    Returns:
        True si aparece una senal financiera, o "cuenta/cuentas" acompanada de
        fondo/cartera/cuenta de.
    """
    if any(signal in lowered for signal in _FINANCE_CONTEXT_SIGNALS):
        return True
    if _FINANCE_ACCOUNT_RE.search(lowered) is None:
        return False
    return any(context in lowered for context in _FINANCE_ACCOUNT_CONTEXT)


@dataclass(frozen=True)
class LocalExecutionResult:
    """Resultado de un intento de ejecucion local.

    Attributes:
        output: Texto del modelo local ("" si no se ejecuto).
        executed_locally: True si se ejecuto en local (0 tokens cloud).
        model: Modelo local usado ("" si no se ejecuto).
        cloud_tokens: Tokens cloud consumidos (0 si local).
        reason: Motivo legible (modelo, fallback o causa).
    """

    output: str
    executed_locally: bool
    model: str = ""
    cloud_tokens: int = 0
    reason: str = ""


def is_closed_task(task: str) -> bool:
    """Detecta si la tarea es cerrada (segura para ejecucion local).

    Matching endurecido (B3): el verbo debe respetar limite de palabra, de
    modo que "presume" (contiene "resum") o "cuentagotas" (contiene "cuenta")
    no disparen falsos positivos; ademas se excluyen los conocidos. El
    contexto financiero/quant (position sizing, capital, riesgo, etc.)
    desactiva la clasificacion: "cuenta" como sustantivo no debe marcar como
    cerrada una tarea substantiva y descartar sus skills.

    Args:
        task: Descripcion de la tarea (case-insensitive).

    Returns:
        True si matchea la allowlist de tareas cerradas sin contexto financiero.
    """
    lowered = task.lower()
    if _CLOSED_TASK_RE.search(lowered) is None:
        return False
    if any(false_positive in lowered for false_positive in _CLOSED_TASK_FALSE_POSITIVES):
        return False
    return not _has_finance_context(lowered)


class LocalExecutor:
    """Ejecutor de tareas cerradas en modelos locales con fallback a cloud.

    Orden de backends: Unsloth (si se inyecta y esta disponible) ->
    Ollama -> cloud. Unsloth primero porque sirve modelos que Ollama no
    carga (forks/quants propios) con el mismo dialecto.

    Args:
        client: OllamaClient (o compatible con is_available/generate).
        tiers: OllamaTierRouter (o compatible con tier_for_task/model_for).
        unsloth_client: UnslothClient opcional (is_available/list_models/
            generate). None = solo Ollama.
        unsloth_model: Modelo a usar en Unsloth (None = primero servido).
        vram_check: Gate anti-OOM (model -> bool). Default el guard real;
            inyectar lambda en tests (hermeticos sin GPU).
        backend_manager: Gestor de ciclo de vida del backend (llama-swap).
            Si el cliente no esta disponible, se le pide arrancarlo y
            precargar el modelo (None = no hay autostart, comportamiento
            previo).
        allow_open_tasks: True = permitir tareas abiertas en local (no solo
            la allowlist cerrada). Default False (retrocompatible).
        max_parallel: Maximo de tareas concurrentes de ``execute_batch``
            (default 4; se acota a >= 1 para no romper el pool).
    """

    def __init__(
        self, client, tiers, unsloth_client=None, unsloth_model=None,
        vram_check=None, free_vram=None, backend_manager=None,
        allow_open_tasks: bool = False, max_parallel: int = 2,
    ) -> None:
        """Inicializa el ejecutor con cliente, router y backend preferente.

        Args:
            client: Cliente Ollama con is_available() y generate().
            tiers: Router con tier_for_task() y model_for().
            unsloth_client: Cliente Unsloth opcional (primero en orden).
            unsloth_model: Override de modelo Unsloth (None = auto).
            vram_check: Gate anti-OOM inyectable (None = guard real).
            free_vram: Proveedor de VRAM libre inyectable (None = nvidia-smi);
                los tests lo fijan para ser hermeticos.
            backend_manager: Gestor de ciclo de vida (ensure_running/
                ensure_model) opcional para arrancar el backend si cayo.
            allow_open_tasks: Politica por defecto para tareas abiertas
                (False = solo la allowlist cerrada).
            max_parallel: Workers del fan-out de ``execute_batch`` (>= 1).
        """
        self._client = client
        self._tiers = tiers
        self._unsloth = unsloth_client
        self._unsloth_model = unsloth_model
        self._vram_check = vram_check or _fits_vram_for
        self._free_vram = free_vram or free_vram_mb
        self._backend_manager = backend_manager
        self._allow_open_tasks = allow_open_tasks
        # Acotar a >= 1: ThreadPoolExecutor exige max_workers >= 1.
        self._max_parallel = max(1, max_parallel)
        self._counter_lock = threading.Lock()
        self._local_tasks = 0
        self._cloud_tasks = 0

    def _ensure_backend(self) -> bool:
        """Intenta levantar el backend local si el cliente no responde.

        Idempotente: delega en ``backend_manager.ensure_running()`` y
        re-verifica ``client.is_available()``. Sin manager devuelve False
        (comportamiento previo: fallback a cloud).

        Returns:
            True si el cliente quedo disponible tras el intento.
        """
        if self._backend_manager is None:
            return False
        try:
            if not self._backend_manager.ensure_running():
                return False
        except Exception as exc:  # noqa: BLE001 - fallback a cloud, no crash
            logger.warning(
                "local_executor: backend_manager no pudo arrancar el backend "
                "(%s); fallback a cloud", exc,
            )
            return False
        return bool(self._client.is_available())

    def _ensure_model(self, model: str) -> bool:
        """Pide al backend precargar el modelo (arranque + swap de VRAM).

        Delega en ``backend_manager.ensure_model()``; sin manager devuelve
        True (no hay nada que garantizar). Nunca lanza: un fallo degrada a
        fallback cloud con log accionable.

        Args:
            model: Id del modelo local a precargar.

        Returns:
            True si el modelo quedo cargado (o no hay manager); False si el
            backend no pudo servirlo.
        """
        if self._backend_manager is None:
            return True
        try:
            return bool(self._backend_manager.ensure_model(model))
        except Exception as exc:  # noqa: BLE001 - fallback a cloud, no crash
            logger.warning(
                "local_executor: backend_manager no pudo precargar %s "
                "(%s); fallback a cloud", model, exc,
            )
            return False

    def _try_unsloth(self, task: str) -> LocalExecutionResult | None:
        """Intenta ejecutar en Unsloth (preferente sobre Ollama).

        Gatea VRAM ANTES de generar: el llama-server carga el modelo al
        servir (sin keep_alive como Ollama) y con Ollama residente + 8GB
        un modelo grande revienta la GPU (nvlddmkm 153). Si no cabe, None
        para seguir a Ollama/cloud (que tienen su propio guard).

        Args:
            task: Tarea cerrada ya validada.

        Returns:
            Resultado si Unsloth respondio, None para seguir a Ollama.
        """
        if self._unsloth is None:
            return None
        try:
            if not self._unsloth.is_available():
                return None
            model = self._unsloth_model
            if model is None:
                models = self._unsloth.list_models()
                if not models:
                    return None
                model = models[0]
            if not self._vram_check(f"unsloth:{model}"):
                logger.warning(
                    "local_executor: Unsloth %s no cabe en VRAM "
                    "(anti-OOM), sigue Ollama", model,
                )
                return None
            output = self._unsloth.generate(model, task)
        except Exception as exc:  # noqa: BLE001 - fallback a Ollama, no crash
            logger.warning("local_executor: Unsloth fallo (%s), sigue Ollama", exc)
            return None
        if _is_degenerate_output(str(output)):
            logger.warning(
                "local_executor: Unsloth %s devolvio salida degenerada, "
                "sigue Ollama", model,
            )
            return None
        self._count_local()
        logger.info("local_executor: tarea cerrada en Unsloth %s (0 tokens cloud)", model)
        return LocalExecutionResult(
            output=str(output), executed_locally=True, model=f"unsloth:{model}",
            reason=f"ejecutada en Unsloth con {model}",
        )

    @property
    def local_tasks(self) -> int:
        """Tareas ejecutadas en local (metrica de ahorro)."""
        return self._local_tasks

    @property
    def cloud_tasks(self) -> int:
        """Tareas derivadas a cloud (metrica)."""
        return self._cloud_tasks

    def execute(self, task: str, allow_open: bool | None = None) -> LocalExecutionResult:
        """Ejecuta la tarea en local si es cerrada, si no deriva a cloud.

        Contrato: NUNCA lanza (B2). La allowlist se evalua fuera del try; toda
        la seleccion + ejecucion (backend, tier, ventana, VRAM y generacion)
        ocurre dentro de un try/except, de modo que un fallo inesperado
        (p. ej. `free_vram` sin nvidia-smi) deriva a cloud con reason
        accionable en lugar de propagar.

        Args:
            task: Descripcion de la tarea.
            allow_open: Override de la politica de tareas abiertas para esta
                llamada; None usa ``self._allow_open_tasks``.

        Returns:
            LocalExecutionResult (nunca lanza).
        """
        if allow_open is None:
            allow_open = self._allow_open_tasks
        if not allow_open and not is_closed_task(task):
            return self._to_cloud(
                "tarea abierta: no esta en la allowlist cerrada (cloud)"
            )
        try:
            return self._select_and_execute(task)
        except Exception as exc:  # noqa: BLE001 - contrato: nunca lanza
            return self._unexpected_failure(exc)

    def execute_batch(self, tasks: list[str]) -> list[LocalExecutionResult]:
        """Ejecuta varias tareas locales en paralelo preservando el orden.

        Fan-out concurrente con
        ``ThreadPoolExecutor(max_workers=self._max_parallel)``; ``pool.map``
        conserva el orden de entrada. Los contadores de ahorro se actualizan
        bajo lock (thread-safe). Contrato: NUNCA lanza (cada tarea ya cae a
        cloud por si misma; se blinda ademas con ``_safe_execute``).

        Args:
            tasks: Descripciones de tarea a ejecutar.

        Returns:
            Lista de resultados en el mismo orden que ``tasks`` (vacia si no
            hay tareas).
        """
        if not tasks:
            return []
        with ThreadPoolExecutor(max_workers=self._max_parallel) as pool:
            return list(pool.map(self._safe_execute, tasks))

    def _safe_execute(self, task: str) -> LocalExecutionResult:
        """Ejecuta una tarea sin propagar excepciones (contrato del batch).

        Args:
            task: Descripcion de la tarea.

        Returns:
            Resultado local o cloud; nunca lanza.
        """
        try:
            return self.execute(task)
        except Exception as exc:  # noqa: BLE001 - contrato: nunca lanza
            return self._unexpected_failure(exc)

    def _select_and_execute(self, task: str) -> LocalExecutionResult:
        """Selecciona backend/modelo y ejecuta la tarea cerrada.

        Orden de gates: Unsloth? -> Ollama disponible? -> tier no-None? ->
        cabe en ventana (anti-loop)? -> VRAM? -> backend precarga? -> generar.

        Args:
            task: Tarea cerrada ya validada por la allowlist.

        Returns:
            Resultado local o cloud con la reason de cada gate.
        """
        unsloth_out = self._try_unsloth(task)
        if unsloth_out is not None:
            return unsloth_out
        if not self._client.is_available() and not self._ensure_backend():
            return self._to_cloud("backend local no disponible: fallback a cloud")
        tier = self._tiers.tier_for_task(task)
        if tier is None:
            return self._to_cloud(
                "tarea frontier-only: requiere cloud (TKN justificado)"
            )
        model = self._tiers.model_for(tier)
        free = self._free_vram()
        model = self._maybe_degrade(model, free)
        window_guard = self._window_guard(model, task)
        if window_guard is not None:
            return window_guard
        if not self._vram_check(model):
            return self._to_cloud(
                f"VRAM insuficiente para {model} (anti-OOM): fallback a cloud"
            )
        if self._backend_manager is not None and not self._ensure_model(model):
            return self._to_cloud(
                f"backend no pudo precargar {model}: fallback a cloud"
            )
        return self._generate_locally(task, model, free, tier)

    def _to_cloud(self, reason: str) -> LocalExecutionResult:
        """Registra la derivacion y devuelve un resultado cloud.

        Args:
            reason: Motivo accionable del fallback.

        Returns:
            LocalExecutionResult no-local con el motivo.
        """
        self._count_cloud()
        return LocalExecutionResult(
            output="", executed_locally=False, reason=reason
        )

    def _count_local(self) -> None:
        """Incrementa el contador de tareas locales de forma thread-safe."""
        with self._counter_lock:
            self._local_tasks += 1

    def _count_cloud(self) -> None:
        """Incrementa el contador de derivaciones a cloud (thread-safe)."""
        with self._counter_lock:
            self._cloud_tasks += 1

    def _unexpected_failure(self, exc: Exception) -> LocalExecutionResult:
        """Deriva a cloud ante un fallo inesperado (contrato: nunca lanza).

        Args:
            exc: Excepcion capturada en la seleccion/ejecucion local.

        Returns:
            LocalExecutionResult cloud con reason WHAT/WHY/WHERE.
        """
        logger.warning(
            "local_executor: WHAT=la ruta local no se pudo completar; "
            "WHY=%s; WHERE=LocalExecutor.execute; fallback a cloud", exc,
        )
        return self._to_cloud(
            "WHAT: la ruta local no se pudo completar; "
            f"WHY: {exc}; WHERE: LocalExecutor.execute; fallback a cloud"
        )

    def _maybe_degrade(self, model: str, free: int | None) -> str:
        """Degrada al texto mas chico que quepa si falta VRAM (anti-TDR).

        Args:
            model: Modelo pedido por el router.
            free: VRAM libre en MB (None = sin dato).

        Returns:
            Modelo seguro (el pedido si ya cabe).
        """
        if not should_degrade(model, free):
            return model
        candidates = [entry.id for entry in FLEET if entry.tier in _LOCAL_TEXT_TIERS]
        safe_model = pick_safe_model(model, candidates, free)
        if safe_model != model:
            logger.warning(
                "local_executor: %s no cabe con %s MB libres (anti-TDR); "
                "degrado a %s", model, free, safe_model,
            )
        return safe_model

    def _window_guard(self, model: str, task: str) -> LocalExecutionResult | None:
        """Deriva a cloud si el prompt excede la ventana (anti-loop/OOM).

        Args:
            model: Modelo elegido.
            task: Tarea original.

        Returns:
            Resultado cloud si no cabe; None si cabe y sigue el flujo.
        """
        if fits_in_window(model, task_chars=len(task)):
            return None
        return self._to_cloud(
            f"prompt excede la ventana de {model} (anti-loop "
            "compactacion/OOM): fallback a cloud"
        )

    def _generate_locally(
        self, task: str, model: str, free: int | None, tier: object,
    ) -> LocalExecutionResult:
        """Genera en el modelo local y valida la salida (verificacion final).

        Args:
            task: Tarea cerrada.
            model: Modelo local elegido.
            free: VRAM libre en MB (None = sin dato).
            tier: Tier decidido (para el keep_alive).

        Returns:
            Resultado local si la salida es sana; cloud si falla o degenera.
        """
        keep_alive = _tier_keep_alive(self._tiers, tier)
        try:
            data = self._client.generate(
                model, CLOSED_TASK_PREFIX + task, keep_alive=keep_alive,
                options={
                    "num_predict": CLOSED_TASK_NUM_PREDICT,
                    "think": CLOSED_TASK_THINK,
                    "num_ctx": safe_num_ctx(model, free),
                },
            )
        except Exception as exc:  # noqa: BLE001 - fallback a cloud, no crash
            logger.warning("local_executor: fallo local (%s), fallback a cloud", exc)
            return self._to_cloud(
                f"fallo del modelo local ({exc}): fallback a cloud"
            )
        output = str(data.get("response", "")) if isinstance(data, dict) else str(data)
        if _is_degenerate_output(output):
            logger.warning(
                "local_executor: %s devolvio salida degenerada "
                "(verificacion final), fallback a cloud", model,
            )
            return self._to_cloud(
                f"salida degenerada de {model} (verificacion final): "
                "fallback a cloud"
            )
        self._count_local()
        logger.info("local_executor: tarea cerrada en %s (0 tokens cloud)", model)
        return LocalExecutionResult(
            output=output, executed_locally=True, model=model,
            reason=f"ejecutada en local con {model}",
        )
