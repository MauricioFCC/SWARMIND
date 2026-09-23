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
from dataclasses import dataclass

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

#: Allowlist de tareas cerradas (substrings ES/EN, sin fragmentos ambiguos).
CLOSED_TASK_PATTERNS: tuple[str, ...] = (
    "resum", "formatea", "format", "extrae", "extract", "traduce",
    "translat", "cuenta", "count", "convierte", "convert", "lista",
    "list files", "renombra",
)


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

    Args:
        task: Descripcion de la tarea (case-insensitive).

    Returns:
        True si matchea la allowlist de tareas cerradas.
    """
    lowered = task.lower()
    return any(pattern in lowered for pattern in CLOSED_TASK_PATTERNS)


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
    """

    def __init__(
        self, client, tiers, unsloth_client=None, unsloth_model=None,
        vram_check=None,
    ) -> None:
        """Inicializa el ejecutor con cliente, router y backend preferente.

        Args:
            client: Cliente Ollama con is_available() y generate().
            tiers: Router con tier_for_task() y model_for().
            unsloth_client: Cliente Unsloth opcional (primero en orden).
            unsloth_model: Override de modelo Unsloth (None = auto).
            vram_check: Gate anti-OOM inyectable (None = guard real).
        """
        self._client = client
        self._tiers = tiers
        self._unsloth = unsloth_client
        self._unsloth_model = unsloth_model
        self._vram_check = vram_check or _fits_vram_for
        self._local_tasks = 0
        self._cloud_tasks = 0

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
        self._local_tasks += 1
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

    def execute(self, task: str) -> LocalExecutionResult:
        """Ejecuta la tarea en local si es cerrada, si no deriva a cloud.

        Orden de gates: tarea cerrada? -> Ollama disponible? -> tier no-None?
        -> cabe en ventana (anti-loop compactacion)? Cualquier fallo
        (incluida excepcion del modelo) deriva a cloud con reason
        accionable, sin lanzar.

        Args:
            task: Descripcion de la tarea.

        Returns:
            LocalExecutionResult (nunca lanza).
        """
        if not is_closed_task(task):
            self._cloud_tasks += 1
            return LocalExecutionResult(
                output="", executed_locally=False,
                reason="tarea abierta: no esta en la allowlist cerrada (cloud)",
            )
        unsloth_out = self._try_unsloth(task)
        if unsloth_out is not None:
            return unsloth_out
        if not self._client.is_available():
            self._cloud_tasks += 1
            return LocalExecutionResult(
                output="", executed_locally=False,
                reason="Ollama no disponible: fallback a cloud",
            )
        tier = self._tiers.tier_for_task(task)
        if tier is None:
            self._cloud_tasks += 1
            return LocalExecutionResult(
                output="", executed_locally=False,
                reason="tarea frontier-only: requiere cloud (TKN justificado)",
            )
        model = self._tiers.model_for(tier)
        if not fits_in_window(model, task_chars=len(task)):
            self._cloud_tasks += 1
            return LocalExecutionResult(
                output="", executed_locally=False,
                reason=(
                    f"prompt excede la ventana de {model} (anti-loop "
                    "compactacion/OOM): fallback a cloud"
                ),
            )
        if not self._vram_check(model):
            self._cloud_tasks += 1
            return LocalExecutionResult(
                output="", executed_locally=False,
                reason=(
                    f"VRAM insuficiente para {model} (anti-OOM): "
                    "fallback a cloud"
                ),
            )
        keep_alive = _tier_keep_alive(self._tiers, tier)
        try:
            data = self._client.generate(model, task, keep_alive=keep_alive)
        except Exception as exc:  # noqa: BLE001 - fallback a cloud, no crash
            self._cloud_tasks += 1
            logger.warning("local_executor: fallo local (%s), fallback a cloud", exc)
            return LocalExecutionResult(
                output="", executed_locally=False,
                reason=f"fallo del modelo local ({exc}): fallback a cloud",
            )
        output = str(data.get("response", "")) if isinstance(data, dict) else str(data)
        self._local_tasks += 1
        logger.info("local_executor: tarea cerrada en %s (0 tokens cloud)", model)
        return LocalExecutionResult(
            output=output, executed_locally=True, model=model,
            reason=f"ejecutada en local con {model}",
        )
