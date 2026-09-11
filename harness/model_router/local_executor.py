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

    Args:
        client: OllamaClient (o compatible con is_available/generate).
        tiers: OllamaTierRouter (o compatible con tier_for_task/model_for).
    """

    def __init__(self, client, tiers) -> None:
        """Inicializa el ejecutor con cliente y router de tiers.

        Args:
            client: Cliente Ollama con is_available() y generate().
            tiers: Router con tier_for_task() y model_for().
        """
        self._client = client
        self._tiers = tiers
        self._local_tasks = 0
        self._cloud_tasks = 0

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
        Cualquier fallo (incluida excepcion del modelo) deriva a cloud con
        reason accionable, sin lanzar.

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
        try:
            data = self._client.generate(model, task)
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
