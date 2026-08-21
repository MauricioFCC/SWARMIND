"""task_protocol — Ciclo de vida de tareas federadas (ADR-0058).

Estados de tarea alineados con A2A v1.0 y store persistente idempotente
en `.opencode/federated/tasks/`. Cada tarea es inmutable: las
transiciones crean una nueva instancia con dataclasses.replace.

Ejemplo::

    store = TaskStore(base_dir)
    task = FederatedTask.create(origin="onyx", target="cqe",
                                skill_id="quant-lib-extension",
                                prompt="implementa sharpe_ratio en metrics.py")
    store.save(task)
    store.update(task.task_id, TaskState.WORKING)
"""
from __future__ import annotations

import json
import logging
import uuid
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from enum import Enum
from pathlib import Path

logger = logging.getLogger(__name__)

#: Directorio de tareas federadas dentro del mirror .opencode.
TASKS_DIR = ".opencode/federated/tasks"


class TaskState(Enum):
    """Estados del ciclo de vida A2A v1.0."""

    SUBMITTED = "submitted"
    WORKING = "working"
    INPUT_REQUIRED = "input-required"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELED = "canceled"

    @property
    def is_terminal(self) -> bool:
        """True si el estado es terminal (no admite transiciones)."""
        return self in _TERMINAL_STATES


#: Estados terminales (fuente única de la máquina de estados).
_TERMINAL_STATES: frozenset[TaskState] = frozenset(
    {TaskState.COMPLETED, TaskState.FAILED, TaskState.CANCELED}
)


@dataclass(frozen=True)
class FederatedTask:
    """Tarea de delegación entre proyectos (inmutable).

    Args:
        task_id: UUID único (idempotencia).
        origin_project: Proyecto que solicita (p. ej. onyx).
        target_project: Proyecto que ejecuta (p. ej. cqe).
        skill_id: Skill de la card destino que se invoca.
        prompt: Instrucción concreta para el agente destino.
        state: Estado actual en el lifecycle.
        created_at / updated_at: Timestamps UTC ISO-8601.
        artifacts: Salidas producidas (rutas o contenidos JSON).
        error: Mensaje WHAT+WHY+WHERE si falló.
    """

    task_id: str
    origin_project: str
    target_project: str
    skill_id: str
    prompt: str
    state: TaskState = TaskState.SUBMITTED
    created_at: str = field(
        default_factory=lambda: datetime.now(UTC).isoformat()
    )
    updated_at: str = field(
        default_factory=lambda: datetime.now(UTC).isoformat()
    )
    artifacts: tuple[str, ...] = field(default=())
    error: str = ""

    @staticmethod
    def create(
        origin_project: str,
        target_project: str,
        skill_id: str,
        prompt: str,
    ) -> FederatedTask:
        """Crea una tarea en estado SUBMITTED con UUID nuevo.

        Args:
            origin_project: Proyecto solicitante.
            target_project: Proyecto ejecutor.
            skill_id: Skill invocada de la card destino.
            prompt: Instrucción para el agente destino.

        Returns:
            FederatedTask nueva.

        Raises:
            ValueError: si algún campo textual es vacío
                (WHAT vacío / WHY contrato / WHERE argumento).
        """
        for arg_name, value in (
            ("origin_project", origin_project),
            ("target_project", target_project),
            ("skill_id", skill_id),
            ("prompt", prompt),
        ):
            if not value or not str(value).strip():
                raise ValueError(
                    f"ValueError: '{arg_name}' está vacío. WHY: una tarea "
                    "federada sin origen/destino/skill/prompt no es "
                    "ejecutable ni auditable. WHERE: FederatedTask.create."
                )
        return FederatedTask(
            task_id=uuid.uuid4().hex[:12],
            origin_project=origin_project.strip(),
            target_project=target_project.strip(),
            skill_id=skill_id.strip(),
            prompt=prompt.strip(),
        )

    def transition(self, new_state: TaskState) -> FederatedTask:
        """Retorna una copia con el nuevo estado (máquina de estados).

        Args:
            new_state: Estado destino de la transición.

        Returns:
            Nueva instancia con updated_at refrescado.

        Raises:
            ValueError: si se parte de un estado terminal o la transición
                no es válida según A2A (WHAT ilegal / WHY lifecycle /
                WHERE transición actual→nueva).
        """
        if self.state.is_terminal:
            raise ValueError(
                f"ValueError: transición desde estado terminal "
                f"'{self.state.value}'. WHY: los estados terminales "
                "(completed/failed/canceled) no admiten cambios. WHERE: "
                f"tarea {self.task_id} ({self.state.value}→{new_state.value})."
            )
        if new_state not in _ALLOWED_TRANSITIONS[self.state]:
            raise ValueError(
                f"ValueError: transición ilegal "
                f"'{self.state.value}'→'{new_state.value}'. WHY: el lifecycle "
                "A2A solo permite transiciones declaradas. WHERE: tarea "
                f"{self.task_id}."
            )
        return replace(
            self,
            state=new_state,
            updated_at=datetime.now(UTC).isoformat(),
        )


#: Transiciones válidas del lifecycle (fuente única, estilo A2A).
_ALLOWED_TRANSITIONS: dict[TaskState, frozenset[TaskState]] = {
    TaskState.SUBMITTED: frozenset(
        {TaskState.WORKING, TaskState.CANCELED}
    ),
    TaskState.WORKING: frozenset(
        {
            TaskState.COMPLETED,
            TaskState.FAILED,
            TaskState.INPUT_REQUIRED,
            TaskState.CANCELED,
        }
    ),
    TaskState.INPUT_REQUIRED: frozenset(
        {TaskState.WORKING, TaskState.CANCELED}
    ),
    TaskState.COMPLETED: frozenset(),
    TaskState.FAILED: frozenset(),
    TaskState.CANCELED: frozenset(),
}


class TaskStore:
    """Store persistente de tareas federadas (JSON por tarea).

    Args:
        base_dir: Raíz del proyecto dueño del store; las tareas viven en
            `<base_dir>/.opencode/federated/tasks/`.
    """

    def __init__(self, base_dir: Path) -> None:
        """Inicializa el store y crea el directorio si falta."""
        self._dir = Path(base_dir) / TASKS_DIR
        self._dir.mkdir(parents=True, exist_ok=True)

    def _path(self, task_id: str) -> Path:
        """Ruta del archivo JSON de una tarea.

        Args:
            task_id: ID de la tarea.

        Returns:
            Ruta `<dir>/<task_id>.json`.
        """
        return self._dir / f"{task_id}.json"

    def save(self, task: FederatedTask) -> Path:
        """Persiste una tarea; si el ID ya existe, lanza (idempotencia).

        Args:
            task: Tarea a guardar.

        Returns:
            Ruta escrita.

        Raises:
            ValueError: si ya existe una tarea con ese ID
                (WHAT duplicado / WHY idempotencia keep-first / WHERE store).
        """
        path = self._path(task.task_id)
        if path.exists():
            raise ValueError(
                f"ValueError: la tarea {task.task_id} ya existe en {path}. "
                "WHY: idempotencia keep-first; use update() para transiciones. "
                "WHERE: TaskStore.save."
            )
        path.write_text(
            json.dumps(self._serialize(task), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return path

    def update(self, task_id: str, new_state: TaskState) -> FederatedTask:
        """Aplica una transición y persiste el resultado.

        Args:
            task_id: ID de la tarea existente.
            new_state: Estado destino.

        Returns:
            Tarea actualizada.

        Raises:
            FileNotFoundError: si el ID no existe (WHAT+WHY+WHERE).
            ValueError: si la transición es ilegal (delegado a transition()).
        """
        current = self.load(task_id)
        updated = current.transition(new_state)
        self._path(task_id).write_text(
            json.dumps(self._serialize(updated), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return updated

    def load(self, task_id: str) -> FederatedTask:
        """Carga una tarea por ID.

        Args:
            task_id: ID buscado.

        Returns:
            Tarea reconstruida.

        Raises:
            FileNotFoundError: si no existe (WHAT inexistente / WHY no se
                puede actualizar lo que no existe / WHERE TaskStore.load).
        """
        path = self._path(task_id)
        if not path.is_file():
            raise FileNotFoundError(
                f"FileNotFoundError: tarea {task_id} no existe en {path}. "
                "WHY: no se puede cargar/actualizar una tarea inexistente. "
                "WHERE: TaskStore.load."
            )
        return self._deserialize(json.loads(path.read_text(encoding="utf-8")))

    def list_tasks(
        self, target_project: str | None = None
    ) -> list[FederatedTask]:
        """Lista tareas, opcionalmente filtradas por proyecto destino.

        Args:
            target_project: Filtro opcional por destino.

        Returns:
            Lista ordenada por created_at ascendente.
        """
        tasks = [
            self._deserialize(json.loads(p.read_text(encoding="utf-8")))
            for p in sorted(self._dir.glob("*.json"))
        ]
        if target_project is not None:
            tasks = [t for t in tasks if t.target_project == target_project]
        return sorted(tasks, key=lambda t: t.created_at)

    @staticmethod
    def _serialize(task: FederatedTask) -> dict[str, object]:
        """Serializa una tarea a dict JSON.

        Args:
            task: Tarea a serializar.

        Returns:
            Dict con estados como string.
        """
        return {
            "task_id": task.task_id,
            "origin_project": task.origin_project,
            "target_project": task.target_project,
            "skill_id": task.skill_id,
            "prompt": task.prompt,
            "state": task.state.value,
            "created_at": task.created_at,
            "updated_at": task.updated_at,
            "artifacts": list(task.artifacts),
            "error": task.error,
        }

    @staticmethod
    def _deserialize(data: dict[str, object]) -> FederatedTask:
        """Reconstruye una tarea desde dict JSON.

        Args:
            data: Dict persistido.

        Returns:
            Instancia FederatedTask.

        Raises:
            ValueError: si el estado persistido es desconocido
                (WHAT corrupto / WHY enum estricto / WHERE archivo).
        """
        try:
            state = TaskState(str(data.get("state")))
        except ValueError as exc:
            raise ValueError(
                f"ValueError: estado desconocido '{data.get('state')}'. WHY: "
                "el store solo acepta estados del lifecycle A2A. WHERE: "
                "TaskStore._deserialize."
            ) from exc
        return FederatedTask(
            task_id=str(data["task_id"]),
            origin_project=str(data["origin_project"]),
            target_project=str(data["target_project"]),
            skill_id=str(data["skill_id"]),
            prompt=str(data["prompt"]),
            state=state,
            created_at=str(data["created_at"]),
            updated_at=str(data["updated_at"]),
            artifacts=tuple(str(a) for a in data.get("artifacts", [])),
            error=str(data.get("error", "")),
        )
