"""federation_bus — Activación gobernada de agentes entre proyectos (ADR-0058).

Envía tareas federadas al proyecto destino ejecutando su harness en el
directorio raíz del destino (transporte local, patrón delegate.py).
Gobernanza deny-by-default con matriz allowlist origen→destinos y audit
trail con parámetros enmascarados (mismo patrón que MCPGovernor ADR-0049).

Ejemplo::

    policy = GovernancePolicy(allowlist={"onyx-quan-aibot": {"core-quant-engine"}})
    bus = FederationBus(projects_root=Path("C:/DEV-SPACE"), policy=policy)
    result = bus.send_task(task)
    print(result.state)  # completed | failed
"""
from __future__ import annotations

import logging
import subprocess
import sys
import time
from dataclasses import dataclass, field, replace
from pathlib import Path

from harness.federation.agent_card import load_agent_card
from harness.federation.task_protocol import (
    FederatedTask,
    TaskState,
    TaskStore,
)

logger = logging.getLogger(__name__)

#: Timeout por defecto para la ejecución remota (segundos; regla OPS >=30s).
DEFAULT_TASK_TIMEOUT_SECONDS = 600

#: Máscara aplicada a prompts en el audit trail (privacidad SEG).
_PROMPT_MASK_PREVIEW_CHARS = 80


@dataclass(frozen=True)
class GovernancePolicy:
    """Matriz allowlist origen→destinos (deny-by-default).

    Args:
        allowlist: Mapa proyecto origen → conjunto de proyectos destino
            permitidos. Un origen ausente no puede delegar a nadie.
        max_concurrent_tasks: Cota de tareas WORKING simultáneas.
    """

    allowlist: dict[str, frozenset[str]] = field(default_factory=dict)
    max_concurrent_tasks: int = 3

    def can_delegate(self, origin: str, target: str) -> bool:
        """Indica si origin tiene permiso de delegar hacia target.

        Args:
            origin: Proyecto solicitante.
            target: Proyecto destino.

        Returns:
            True solo si existe la entrada explícita en la allowlist.
        """
        return target in self.allowlist.get(origin, frozenset())


@dataclass(frozen=True)
class AuditEntry:
    """Registro inmutable de una decisión/envío federado.

    Args:
        task_id: Tarea involucrada.
        origin / target: Par de proyectos.
        action: authorize-deny | send | complete | fail.
        detail: Detalle sin datos sensibles (prompt enmascarado).
    """

    task_id: str
    origin: str
    target: str
    action: str
    detail: str


@dataclass(frozen=True)
class SendResult:
    """Resultado terminal de un envío federado.

    Args:
        task: Tarea en estado terminal.
        stdout_preview: Primeros caracteres de la salida del agente destino.
        exit_code: Código de salida del proceso remoto.
    """

    task: FederatedTask
    stdout_preview: str
    exit_code: int


def _mask_prompt(prompt: str) -> str:
    """Enmascara un prompt dejando solo un preview corto.

    Args:
        prompt: Prompt completo.

    Returns:
        Preview truncado seguro para logs.
    """
    flat = " ".join(prompt.split())
    if len(flat) <= _PROMPT_MASK_PREVIEW_CHARS:
        return flat
    return flat[:_PROMPT_MASK_PREVIEW_CHARS] + "..."


class FederationBus:
    """Bus de delegación entre proyectos con gobernanza y auditoría.

    Args:
        projects_root: Directorio que contiene los proyectos hermanos.
        policy: Matriz de gobernanza deny-by-default.
        store_dir: Proyecto dueño del TaskStore (default: projects_root
            no aplica; se pasa explícito en tests). Si None usa el
            directorio de trabajo actual.
        timeout_seconds: Timeout de cada ejecución remota.
    """

    def __init__(
        self,
        projects_root: Path,
        policy: GovernancePolicy | None = None,
        store_dir: Path | None = None,
        timeout_seconds: int = DEFAULT_TASK_TIMEOUT_SECONDS,
    ) -> None:
        """Inicializa bus, store y política."""
        self._projects_root = Path(projects_root)
        self._policy = policy or GovernancePolicy()
        self._store = TaskStore(store_dir or Path.cwd())
        self._timeout = timeout_seconds
        self._audit: list[AuditEntry] = []

    @property
    def audit_trail(self) -> tuple[AuditEntry, ...]:
        """Audit trail inmutable de decisiones y envíos."""
        return tuple(self._audit)

    def _audit_log(self, task: FederatedTask, action: str, detail: str) -> None:
        """Registra una entrada de auditoría.

        Args:
            task: Tarea relacionada.
            action: Acción realizada o denegada.
            detail: Detalle ya enmascarado por el llamador.
        """
        self._audit.append(
            AuditEntry(
                task_id=task.task_id,
                origin=task.origin_project,
                target=task.target_project,
                action=action,
                detail=detail,
            )
        )

    def _target_path(self, project_name: str) -> Path:
        """Resuelve la raíz de un proyecto destino.

        Args:
            project_name: Nombre del directorio del proyecto.

        Returns:
            Ruta raíz.

        Raises:
            FileNotFoundError: si el proyecto no existe bajo projects_root
                (WHAT inexistente / WHY sin raíz no hay transporte /
                WHERE FederationBus._target_path).
        """
        path = self._projects_root / project_name
        if not path.is_dir():
            raise FileNotFoundError(
                f"FileNotFoundError: proyecto destino '{project_name}' no "
                f"existe en {self._projects_root}. WHY: el transporte local "
                "ejecuta el harness dentro de la raíz del destino. WHERE: "
                "FederationBus._target_path."
            )
        return path

    def _authorize(self, task: FederatedTask) -> None:
        """Valida la gobernanza y el estado de la tarea.

        Args:
            task: Tarea a autorizar.

        Raises:
            PermissionError: si la política deniega origen→destino.
            ValueError: si la tarea no está en SUBMITTED.
        """
        if task.state is not TaskState.SUBMITTED:
            raise ValueError(
                f"ValueError: tarea {task.task_id} en estado "
                f"'{task.state.value}'. WHY: send_task exige tareas nuevas "
                "(SUBMITTED). WHERE: FederationBus._authorize."
            )
        if not self._policy.can_delegate(task.origin_project, task.target_project):
            reason = (
                f"PermissionError: delegación '{task.origin_project}'→"
                f"'{task.target_project}' denegada. WHY: la matriz de "
                "gobernanza es deny-by-default y no existe entrada explícita. "
                "WHERE: GovernancePolicy.can_delegate."
            )
            logger.warning("%s (task=%s)", reason, task.task_id)
            self._audit_log(task, "authorize-deny", reason)
            raise PermissionError(reason)

    def _validate_target(self, task: FederatedTask) -> Path:
        """Resuelve la raíz destino y valida su Agent Card/skill.

        Args:
            task: Tarea autorizada.

        Returns:
            Ruta raíz del proyecto destino.

        Raises:
            ValueError: si la skill no está declarada en la card.
            FileNotFoundError: si el proyecto no existe (delegado).
        """
        target_root = self._target_path(task.target_project)
        card = load_agent_card(target_root)
        if not card.has_skill(task.skill_id):
            raise ValueError(
                f"ValueError: la card de '{task.target_project}' no declara "
                f"la skill '{task.skill_id}'. WHY: solo se delegan skills "
                "publicadas en la Agent Card. WHERE: FederationBus.send_task."
            )
        return target_root

    def _run_remote(self, working: FederatedTask) -> tuple[int, str, str]:
        """Ejecuta el harness del proyecto destino con el prompt.

        Args:
            working: Tarea en estado WORKING.

        Returns:
            Tupla (exit_code, stdout, stderr).
        """
        target_root = self._projects_root / working.target_project
        proc = subprocess.run(
            [sys.executable, "-m", "harness.run"],
            input=working.prompt,
            capture_output=True,
            text=True,
            cwd=str(target_root),
            timeout=self._timeout,
            check=False,
        )
        return proc.returncode, proc.stdout or "", proc.stderr or ""

    def _finalize_timeout(self, working: FederatedTask) -> SendResult:
        """Marca FAILED por timeout y persiste.

        Args:
            working: Tarea en WORKING que excedió el timeout.

        Returns:
            SendResult con estado terminal FAILED.
        """
        failed = replace(
            working.transition(TaskState.FAILED),
            error=(
                f"FederationBus: timeout de {self._timeout}s ejecutando la "
                f"tarea {working.task_id} en '{working.target_project}'. "
                "WHY: el agente destino excedió el presupuesto de tiempo. "
                "WHERE: FederationBus.send_task."
            ),
        )
        self._store.save(failed)
        self._audit_log(failed, "fail", "timeout")
        return SendResult(task=failed, stdout_preview="", exit_code=-1)

    def _finalize(
        self, working: FederatedTask, exit_code: int, stdout: str, stderr: str
    ) -> SendResult:
        """Aplica el estado terminal según exit code y persiste.

        Args:
            working: Tarea en WORKING ya ejecutada.
            exit_code: Código de salida del proceso remoto.
            stdout / stderr: Salidas del proceso remoto.

        Returns:
            SendResult con estado terminal COMPLETED o FAILED.
        """
        success = exit_code == 0
        final = working.transition(
            TaskState.COMPLETED if success else TaskState.FAILED
        )
        if not success:
            stderr_tail = stderr.strip().splitlines()
            detail = stderr_tail[-1] if stderr_tail else "sin stderr"
            final = replace(final, error=(
                f"FederationBus: el agente destino terminó con exit code "
                f"{exit_code}. WHY: {detail[:200]}. WHERE: subprocess en "
                f"'{final.target_project}'."
            ))
        final = replace(final, artifacts=(f"exit_code={exit_code}",))
        self._store.save(final)
        self._audit_log(
            final, "complete" if success else "fail", f"exit={exit_code}"
        )
        return SendResult(task=final, stdout_preview=stdout[:200], exit_code=exit_code)

    def send_task(self, task: FederatedTask) -> SendResult:
        """Ejecuta una tarea federada en el proyecto destino.

        Flujo: autorización → validación de card/skill → working →
        subprocess en la raíz del destino → estado terminal + artifact.

        Args:
            task: Tarea en estado SUBMITTED registrada previamente en el
                store del bus.

        Returns:
            SendResult con la tarea en estado terminal.

        Raises:
            PermissionError: si la gobernanza deniega el par origen→destino.
            ValueError: si la tarea no está en SUBMITTED o la skill no está
                declarada en la card destino.
        """
        self._authorize(task)
        self._validate_target(task)
        working = task.transition(TaskState.WORKING)
        self._audit_log(
            working, "send",
            f"skill={working.skill_id} prompt={_mask_prompt(working.prompt)}",
        )
        started = time.perf_counter()
        try:
            exit_code, stdout, stderr = self._run_remote(working)
        except subprocess.TimeoutExpired:
            logger.error(
                "FederationBus: timeout tarea %s tras %.1fs",
                working.task_id, time.perf_counter() - started,
            )
            return self._finalize_timeout(working)
        elapsed = time.perf_counter() - started
        logger.info(
            "FederationBus: tarea %s terminó exit=%d (%.1fs)",
            working.task_id, exit_code, elapsed,
        )
        return self._finalize(working, exit_code, stdout, stderr)
