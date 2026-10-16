"""Ejecucion durable con Resume Contract (spec frontera 11.15).

WHAT: ``DurableRunStore`` implementa el subset verificable del Resume Contract
(arXiv 2608.03836, "Resume Means Resume", 2026-08) que los frameworks
deployados (LangGraph 1.2.9, CrewAI 1.15.2, pydantic-graph 1.x) INCUMPLEN en
medida:

- **Prefix continuation**: ``resume_plan`` re-ejecuta SOLO pasos ``PENDING``.
- **Effect exactly-once**: cada efecto se RECLAMA (``claim_step``) ANTES de
  ejecutarse y el claim se persiste ANTES de devolver control; un crash entre
  claim y complete deja el paso ``RUNNING`` y resume lo expone como
  ``indeterminate`` — nunca lo re-ejecuta a ciegas (duplicaria pagos/mensajes).
- **Consume-once cross-process**: el segundo claim de un paso reclamado
  devuelve False ANTES de ejecutar; el gate vive en el journal durable, no en
  memoria (el paper midio saturacion 1.0 de efectos duplicados cuando el gate
  era solo en memoria).
- **Recovery determinism**: el plan es funcion SOLO del estado durable (sin
  reloj ni azar): mismo journal -> mismo plan.
- **Checkpoint validity**: un journal corrupto se rechaza con error legible
  (WHAT+WHY+WHERE); jamas se opera sobre estado invalido.

WHY: el orquestador SWARMIND delega efectos no-idempotentes (cobros, avisos,
escalaciones HITL); sin un contrato de resume testeado, crash y doble
respuesta disparan efectos dos veces.

WHERE: ``harness/orchestrator/durable_run.py`` (consumido por el
orquestador y por ``hitl_guard`` para respuestas consume-once).
"""

from __future__ import annotations

import json
import logging
import os
from collections.abc import Sequence
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class StepStatus(str, Enum):
    """Estado durable de un paso dentro de un run."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"


@dataclass(frozen=True)
class ResumePlan:
    """Plan de reanudacion derivado SOLO del estado durable (determinista).

    Attributes:
        run_id: Run planificado.
        reexecute: Pasos PENDING: seguros de re-ejecutar (nunca dispararon).
        indeterminate: Pasos RUNNING al crash: el efecto PUDO haber disparado;
            jamas entran en re-ejecucion automatica.
        completed: Pasos COMPLETED: jamas se re-ejecutan (prefix).
    """

    run_id: str
    reexecute: tuple[str, ...]
    indeterminate: tuple[str, ...]
    completed: tuple[str, ...]


class DurableRunStore:
    """Journal durable de runs con transiciones persistidas atomicamente.

    Cada transicion (start/claim/complete/consume) se escribe con
    tmp + ``os.replace`` ANTES de devolver control: el estado durable nunca
    queda a medio escribir y un crash posterior siempre deja un checkpoint
    valido del que derivar el plan.
    """

    def __init__(self, path: Path) -> None:
        """Carga (o crea) el journal en ``path``.

        Args:
            path: Ruta del journal JSON (``{"runs": {...}}``).

        Raises:
            ValueError: Si el journal existe pero esta corrupto/ilegible.
            TypeError: Si el journal no tiene la forma esperada (Checkpoint
                Validity: nunca se opera sobre estado invalido).
        """
        self._path = path
        self._state = self._load()

    def start_run(self, run_id: str, steps: Sequence[str]) -> None:
        """Crea un run con todos sus pasos en PENDING (checkpoint inicial).

        Args:
            run_id: Identificador unico del run.
            steps: Pasos del run en orden de ejecucion.

        Raises:
            ValueError: Si el run ya existe (no se pisa estado durable).
        """
        if run_id in self._state["runs"]:
            raise ValueError(
                f"WHAT: run '{run_id}' ya existe en el journal. "
                "WHY: start_run no pisa estado durable (idempotencia). "
                f"WHERE: DurableRunStore.start_run({self._path})."
            )
        self._state["runs"][run_id] = {
            "steps": {step: {"status": StepStatus.PENDING.value} for step in steps},
            "events": {},
        }
        self._persist()

    def claim_step(self, run_id: str, step_id: str) -> bool:
        """Reclama un paso ANTES de ejecutar su efecto (consume-once).

        El claim se persiste durablemente antes de devolver: un crash
        posterior deja el paso RUNNING y ``resume_plan`` lo expone como
        indeterminado en lugar de re-ejecutarlo.

        Args:
            run_id: Run del paso.
            step_id: Paso a reclamar.

        Returns:
            True si este caller gano el claim; False si el paso ya estaba
            reclamado (otro racer o proceso): el perdedor NO ejecuta el efecto.
        """
        step = self._step(run_id, step_id)
        if step["status"] != StepStatus.PENDING.value:
            return False
        step["status"] = StepStatus.RUNNING.value
        self._persist()
        return True

    def complete_step(
        self, run_id: str, step_id: str, result: Any | None = None
    ) -> None:
        """Confirma un paso RUNNING como COMPLETED (efecto ya disparado).

        Args:
            run_id: Run del paso.
            step_id: Paso completado.
            result: Resultado JSON-serializable opcional del paso.

        Raises:
            ValueError: Si el paso no esta RUNNING (complete sin claim rompe
                effect exactly-once).
        """
        step = self._step(run_id, step_id)
        if step["status"] != StepStatus.RUNNING.value:
            raise ValueError(
                f"WHAT: complete_step('{step_id}') con status="
                f"{step['status']} (se exige RUNNING via claim). "
                "WHY: effect exactly-once exige claim ANTES de ejecutar. "
                f"WHERE: DurableRunStore.complete_step({self._path})."
            )
        step["status"] = StepStatus.COMPLETED.value
        if result is not None:
            step["result"] = result
        self._persist()

    def resume_plan(self, run_id: str) -> ResumePlan:
        """Deriva el plan de reanudacion SOLO del estado durable.

        Args:
            run_id: Run a planificar.

        Returns:
            Plan determinista: PENDING -> ``reexecute``, RUNNING ->
            ``indeterminate`` (posible efecto a medias, decision del caller),
            COMPLETED -> ``completed``.

        Raises:
            ValueError: Si el run no existe.
        """
        steps = self._run(run_id)["steps"]
        by_status = {status.value: [] for status in StepStatus}
        for step_id, record in steps.items():
            by_status[record["status"]].append(step_id)
        return ResumePlan(
            run_id=run_id,
            reexecute=tuple(by_status[StepStatus.PENDING.value]),
            indeterminate=tuple(by_status[StepStatus.RUNNING.value]),
            completed=tuple(by_status[StepStatus.COMPLETED.value]),
        )

    def consume_event(self, run_id: str, event_id: str, answer: Any) -> bool:
        """Persiste la respuesta a un evento HITL (consume-once).

        El paper 2608.03836 midio saturacion 1.0 de efectos duplicados cuando
        N procesos respondian el mismo interrupt sin gate durable: aqui el
        primer racer gana y los demas son rechazados ANTES de ejecutar.

        Args:
            run_id: Run dueno del evento.
            event_id: Evento/interupcion (p. ej. ``approval-1``).
            answer: Respuesta JSON-serializable del racer ganador.

        Returns:
            True si esta respuesta fue la primera (y unica persistida);
            False si el evento ya tenia respuesta.
        """
        events = self._run(run_id)["events"]
        if event_id in events:
            return False
        events[event_id] = answer
        self._persist()
        return True

    def event_answer(self, run_id: str, event_id: str) -> Any | None:
        """Devuelve la respuesta persistida de un evento HITL (o None).

        Args:
            run_id: Run dueno del evento.
            event_id: Evento consultado.

        Returns:
            Respuesta del racer ganador; None si nadie ha respondido.
        """
        return self._run(run_id)["events"].get(event_id)

    def _load(self) -> dict[str, Any]:
        """Carga y valida el journal desde disco.

        Returns:
            Estado durable ``{"runs": {...}}`` (vacio si el archivo no existe).

        Raises:
            ValueError: Si el journal esta corrupto o sin la forma esperada.
        """
        if not self._path.exists():
            return {"runs": {}}
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError(
                f"WHAT: journal durable corrupto/ilegible ({exc}). "
                "WHY: operar sobre estado invalido rompe el Resume Contract. "
                f"WHERE: DurableRunStore({self._path})."
            ) from exc
        if not isinstance(data, dict) or not isinstance(data.get("runs"), dict):
            raise TypeError(
                "WHAT: journal sin la forma esperada {\"runs\": {...}}. "
                "WHY: Checkpoint Validity — se rechaza estado invalido. "
                f"WHERE: DurableRunStore({self._path})."
            )
        return data

    def _persist(self) -> None:
        """Escribe el estado atomicamente (tmp + os.replace)."""
        tmp = self._path.with_suffix(self._path.suffix + ".tmp")
        tmp.write_text(
            json.dumps(self._state, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        os.replace(tmp, self._path)

    def _run(self, run_id: str) -> dict[str, Any]:
        """Devuelve el registro durable de un run.

        Raises:
            ValueError: Si el run no existe.
        """
        run = self._state["runs"].get(run_id)
        if run is None:
            raise ValueError(
                f"WHAT: run '{run_id}' inexistente en el journal. "
                "WHY: no se planifica ni responde sobre estado desconocido. "
                f"WHERE: DurableRunStore({self._path})."
            )
        return run

    def _step(self, run_id: str, step_id: str) -> dict[str, Any]:
        """Devuelve el registro durable de un paso.

        Raises:
            ValueError: Si el paso no existe en el run.
        """
        step = self._run(run_id)["steps"].get(step_id)
        if step is None:
            raise ValueError(
                f"WHAT: paso '{step_id}' inexistente en run '{run_id}'. "
                "WHY: transicion sobre paso desconocido es un bug del caller. "
                f"WHERE: DurableRunStore({self._path})."
            )
        return step
