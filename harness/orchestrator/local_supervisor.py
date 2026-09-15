"""local_supervisor.py — Cloud como guia: audita muestras locales (ADR-0084).

WHAT: Observa salidas de agentes locales y audita una fraccion
(sample_rate) con un juez cloud; cada veredicto alimenta el
CompetenceModel (cierra el loop local->evidencia->routing).
WHY: Frontera — el cloud como guia/supervisor (no redactor) maximiza
ahorro sin perder calidad: la mayoria ejecuta local, el cloud solo
muestrea y calibra; la evidencia recalibra el routing (UCCI/Thompson).
WHERE: Tras `LocalExecutor`/draft-review en produccion; `sample_rate`
configurable (0.0 = 0 tokens cloud, 1.0 = auditoria total en pruebas).

Uso:
    sup = LocalSupervisor(judge_fn=cloud_judge, sample_rate=0.1,
                          competence=model)
    sup.observe(task_id, agent, output, skill="code")
"""

from __future__ import annotations

import logging
import random
from collections.abc import Callable

logger = logging.getLogger("harness.orchestrator.local_supervisor")


class LocalSupervisor:
    """Supervisor cloud por muestreo con feedback a competencia.

    Args:
        judge_fn: (task_id, output) -> True si la salida es aceptable.
        sample_rate: Fraccion a auditar en [0, 1].
        competence: CompetenceModel opcional para registrar veredictos.
        rng: Generador inyectable (tests deterministas).
    """

    def __init__(
        self,
        judge_fn: Callable[[str, str], bool],
        sample_rate: float = 0.1,
        competence=None,
        rng: random.Random | None = None,
    ) -> None:
        """Inicializa el supervisor con tasa validada.

        Args:
            judge_fn: Juez cloud (solo se llama en muestras).
            sample_rate: Tasa en [0, 1].
            competence: Modelo a alimentar (o None).
            rng: RNG inyectable.

        Raises:
            ValueError: Si sample_rate fuera de [0, 1] (WHAT+WHY+WHERE).
        """
        if not (0.0 <= sample_rate <= 1.0):
            raise ValueError(
                f"WHAT: sample_rate invalido: {sample_rate}. "
                "WHY: es una fraccion, debe estar en [0, 1]. "
                "WHERE: LocalSupervisor.__init__"
            )
        self._judge_fn = judge_fn
        self._sample_rate = sample_rate
        self._competence = competence
        self._rng = rng or random.Random()
        self._audited = 0

    @property
    def audited(self) -> int:
        """Salidas auditadas (metrica de costo de supervision)."""
        return self._audited

    def observe(
        self, task_id: str, agent: str, output: str, skill: str = "general"
    ) -> bool | None:
        """Observa una salida local; audita segun sample_rate.

        Args:
            task_id: ID de la tarea (para el juez).
            agent: Agente local que produjo la salida.
            output: Texto producido.
            skill: Skill para el registro de competencia.

        Returns:
            Veredicto (True/False) si se audito; None si no toco muestreo.
        """
        if self._rng.random() >= self._sample_rate:
            return None
        verdict = bool(self._judge_fn(task_id, output))
        self._audited += 1
        logger.info(
            "local_supervisor: auditada salida de %s (veredicto=%s)", agent, verdict
        )
        if self._competence is not None:
            try:
                self._competence.update(agent, skill, success=verdict)
            except ValueError:
                logger.debug(
                    "local_supervisor: par (%s, %s) fuera del modelo; veredicto no registrado",
                    agent, skill,
                )
        return verdict
