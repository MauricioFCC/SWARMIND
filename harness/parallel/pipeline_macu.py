"""PipelineMACU — DAG vivo con replanning continuo.

Implementa el patron del paper MACU (arXiv:2606.01533):
- Manager descompone tarea en DAG
- Subagentes ejecutan nodos del ready frontier en paralelo
- Manager replanifica continuamente basado en resultados parciales

Diferencias con TaskOrchestrator actual:
- DAG vivo (no niveles fijos): nodos se agregan/cancelan/reescriben en caliente
- Ready frontier dispatch: nodos individuales ejecutan tan pronto esten listos
- Information passing: resultados parciales se propagan a downstream

Referencia: arXiv:2606.01533 — Multi-Agent Computer Use (MACU)
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Callable, Dict, List, Optional, Set

logger = logging.getLogger(__name__)


class TaskStatus(Enum):
    """Estado de un nodo en el DAG."""
    PENDING = auto()
    READY = auto()
    RUNNING = auto()
    COMPLETED = auto()
    FAILED = auto()
    CANCELLED = auto()


@dataclass
class PipelineTask:
    """Nodo individual en el pipeline DAG.

    Attributes:
        task_id: Identificador unico del nodo.
        name: Nombre descriptivo de la tarea.
        agent: Agente que ejecutara la tarea.
        description: Descripcion detallada.
        depends_on: IDs de tareas de las que depende.
        status: Estado actual.
        result: Resultado de la ejecucion.
        error: Mensaje de error si fallo.
        created_at: Timestamp de creacion.
        started_at: Timestamp de inicio.
        completed_at: Timestamp de finalizacion.
        priority: Prioridad (mayor = mas prioritario).
        metadata: Datos adicionales.
    """
    task_id: str
    name: str
    agent: str
    description: str
    depends_on: Set[str] = field(default_factory=set)
    status: TaskStatus = TaskStatus.PENDING
    result: Optional[Any] = None
    error: Optional[str] = None
    created_at: float = field(default_factory=time.time)
    started_at: Optional[float] = None
    completed_at: Optional[float] = None
    priority: int = 5
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class PipelineResult:
    """Resultado de la ejecucion del pipeline completo.

    Attributes:
        pipeline_id: Identificador del pipeline.
        total_tasks: Total de tareas en el DAG.
        completed: Tareas completadas exitosamente.
        failed: Tareas fallidas.
        cancelled: Tareas canceladas.
        total_time: Tiempo total de ejecucion.
        outputs: Mapa de task_id -> resultado.
    """
    pipeline_id: str
    total_tasks: int
    completed: int
    failed: int
    cancelled: int
    total_time: float
    outputs: Dict[str, Any] = field(default_factory=dict)


class PipelineMACU:
    """Orquestador DAG con replanning continuo (MACU).

    Gestiona un grafo aciclico dirigido (DAG) de tareas donde:
    - El manager agrega/replanifica nodos basado en resultados parciales.
    - Los subagentes ejecutan nodos del ready frontier en paralelo.
    - Las dependencias se resuelven automaticamente.

    Args:
        max_parallel: Maximo tareas en paralelo (default: 4).
        replan_fn: Funcion opcional de replanificacion.
            Recibe (task_id, result) y retorna lista de nuevos PipelineTask.
    """

    def __init__(
        self,
        max_parallel: int = 4,
        replan_fn: Optional[Callable[[str, Any], List[PipelineTask]]] = None,
    ) -> None:
        """Inicializa el pipeline MACU.

        Args:
            max_parallel: Tareas maximas en paralelo.
            replan_fn: Funcion de replanificacion (task_id, result) -> [PipelineTask].
        """
        self._max_parallel: int = max(max_parallel, 1)
        self._replan_fn: Optional[Callable[[str, Any], List[PipelineTask]]] = replan_fn
        self._tasks: Dict[str, PipelineTask] = {}
        self._dependencies: Dict[str, Set[str]] = {}  # task_id -> dependencias
        self._dependents: Dict[str, Set[str]] = {}  # task_id -> tareas que dependen de ella
        self._lock: asyncio.Lock = asyncio.Lock()

    async def add_task(self, task: PipelineTask) -> str:
        """Agrega un nodo al DAG.

        Args:
            task: Tarea a agregar.

        Returns:
            task_id de la tarea agregada.

        Raises:
            ValueError: Si task_id ya existe o dependencia ciclica.
        """
        async with self._lock:
            if task.task_id in self._tasks:
                raise ValueError(f"Task ID duplicado: {task.task_id}")

            # Validar dependencias
            for dep_id in task.depends_on:
                if dep_id not in self._tasks:
                    raise ValueError(f"Dependencia inexistente: {dep_id}")
                if dep_id == task.task_id:
                    raise ValueError(f"Dependencia ciclica: {task.task_id} depende de si mismo")

            self._tasks[task.task_id] = task
            self._dependencies[task.task_id] = set(task.depends_on)

            # Registrar dependientes
            for dep_id in task.depends_on:
                if dep_id not in self._dependents:
                    self._dependents[dep_id] = set()
                self._dependents[dep_id].add(task.task_id)

            # Marcar como READY si no tiene dependencias
            if not task.depends_on:
                task.status = TaskStatus.READY
                logger.debug("[MACU] Tarea READY: %s", task.name)

        return task.task_id

    async def get_ready_tasks(self) -> List[PipelineTask]:
        """Retorna las tareas listas para ejecutar (ready frontier).

        Returns:
            Lista de tareas con status READY.
        """
        async with self._lock:
            ready: List[PipelineTask] = [
                task for task in self._tasks.values()
                if task.status == TaskStatus.READY
            ]
            # Ordenar por prioridad (mayor primero)
            ready.sort(key=lambda t: t.priority, reverse=True)
            return ready[:self._max_parallel]

    async def mark_running(self, task_id: str) -> bool:
        """Marca una tarea como RUNNING.

        Args:
            task_id: ID de la tarea.

        Returns:
            True si se marco exitosamente.
        """
        async with self._lock:
            task = self._tasks.get(task_id)
            if task is None or task.status != TaskStatus.READY:
                return False
            task.status = TaskStatus.RUNNING
            task.started_at = time.time()
            return True

    async def mark_completed(self, task_id: str, result: Any = None) -> List[PipelineTask]:
        """Marca una tarea como COMPLETED y actualiza dependencias.

        Si hay replan_fn, la invoca con el resultado para generar nuevas tareas.
        Las tareas downstream que ya no tienen dependencias pendientes se marcan READY.

        Args:
            task_id: ID de la tarea completada.
            result: Resultado de la ejecucion.

        Returns:
            Lista de nuevas tareas generadas por replanning (si aplica).
        """
        new_tasks: List[PipelineTask] = []

        async with self._lock:
            task = self._tasks.get(task_id)
            if task is None:
                return []

            task.status = TaskStatus.COMPLETED
            task.result = result
            task.completed_at = time.time()

            logger.info("[MACU] Tarea COMPLETED: %s (%.1fs)",
                        task.name, task.completed_at - (task.started_at or task.created_at))

            # Replanificar si hay funcion
            if self._replan_fn:
                try:
                    new_tasks = self._replan_fn(task_id, result) or []
                    for new_task in new_tasks:
                        if new_task.task_id not in self._tasks:
                            self._tasks[new_task.task_id] = new_task
                            self._dependencies[new_task.task_id] = set(new_task.depends_on)
                            for dep_id in new_task.depends_on:
                                if dep_id not in self._dependents:
                                    self._dependents[dep_id] = set()
                                self._dependents[dep_id].add(new_task.task_id)
                            # Si no tiene dependencias, ready
                            if not new_task.depends_on:
                                new_task.status = TaskStatus.READY
                except Exception as exc:
                    logger.error("[MACU] Error en replanning para %s: %s", task_id, exc)

            # Actualizar dependencias de tareas downstream
            downstream: Set[str] = self._dependents.get(task_id, set())
            for dep_id in downstream:
                dep_task = self._tasks.get(dep_id)
                if dep_task and dep_task.status == TaskStatus.PENDING:
                    # Remover esta dependencia
                    self._dependencies[dep_id].discard(task_id)
                    # Si ya no tiene dependencias, ready
                    if not self._dependencies[dep_id]:
                        dep_task.status = TaskStatus.READY
                        logger.debug("[MACU] Tarea READY (dep satisfecha): %s", dep_task.name)

        return new_tasks

    async def mark_failed(self, task_id: str, error: str) -> None:
        """Marca una tarea como FAILED y sus dependientes como CANCELLED.

        Args:
            task_id: ID de la tarea fallida.
            error: Mensaje de error.
        """
        async with self._lock:
            task = self._tasks.get(task_id)
            if task is None:
                return

            task.status = TaskStatus.FAILED
            task.error = error
            task.completed_at = time.time()

            logger.error("[MACU] Tarea FAILED: %s: %s", task.name, error)

            # Cancelar dependientes
            downstream: Set[str] = self._dependents.get(task_id, set())
            for dep_id in downstream:
                dep_task = self._tasks.get(dep_id)
                if dep_task and dep_task.status in (TaskStatus.PENDING, TaskStatus.READY):
                    dep_task.status = TaskStatus.CANCELLED
                    logger.debug("[MACU] Tarea CANCELLED (dependencia fallida): %s", dep_task.name)

    async def execute(
        self,
        dispatch_fn: Callable[[PipelineTask], Any],
    ) -> PipelineResult:
        """Ejecuta el pipeline completo.

        Itera: obtiene ready frontier, ejecuta en paralelo, procesa resultados,
        replanifica, repite hasta que todas las tareas esten terminales.

        Args:
            dispatch_fn: Funcion que ejecuta una tarea.
                Recibe PipelineTask, retorna Any (resultado).

        Returns:
            PipelineResult con el resumen de ejecucion.
        """
        pipeline_id: str = f"pipeline_{uuid.uuid4().hex[:8]}"
        start_time: float = time.time()
        logger.info("[MACU] Pipeline iniciado: %s (%d tareas)", pipeline_id, len(self._tasks))

        while True:
            # Obtener ready frontier
            ready: List[PipelineTask] = await self.get_ready_tasks()
            if not ready:
                # Verificar si todas las tareas estan terminales
                async with self._lock:
                    all_terminal: bool = all(
                        t.status in (TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED)
                        for t in self._tasks.values()
                    )
                if all_terminal:
                    break
                # Esperar un poco antes de reintentar
                await asyncio.sleep(0.1)
                continue

            # Ejecutar ready frontier en paralelo
            async def _execute_one(task: PipelineTask) -> tuple:
                await self.mark_running(task.task_id)
                try:
                    result: Any = await dispatch_fn(task) if asyncio.iscoroutinefunction(dispatch_fn) else dispatch_fn(task)
                    new_tasks: List[PipelineTask] = await self.mark_completed(task.task_id, result)
                    return task.task_id, result, new_tasks
                except Exception as exc:
                    await self.mark_failed(task.task_id, str(exc))
                    return task.task_id, None, []

            results: List[tuple] = await asyncio.gather(*[_execute_one(t) for t in ready])

        # Construir resultado
        total_time: float = time.time() - start_time
        async with self._lock:
            completed: int = sum(1 for t in self._tasks.values() if t.status == TaskStatus.COMPLETED)
            failed: int = sum(1 for t in self._tasks.values() if t.status == TaskStatus.FAILED)
            cancelled: int = sum(1 for t in self._tasks.values() if t.status == TaskStatus.CANCELLED)
            outputs: Dict[str, Any] = {
                tid: t.result for tid, t in self._tasks.items()
                if t.status == TaskStatus.COMPLETED and t.result is not None
            }

        result: PipelineResult = PipelineResult(
            pipeline_id=pipeline_id,
            total_tasks=len(self._tasks),
            completed=completed,
            failed=failed,
            cancelled=cancelled,
            total_time=total_time,
            outputs=outputs,
        )

        logger.info(
            "[MACU] Pipeline completado: %s — %d/%d ok, %d failed, %d cancelled (%.1fs)",
            pipeline_id, completed, len(self._tasks), failed, cancelled, total_time,
        )

        return result

    def get_task(self, task_id: str) -> Optional[PipelineTask]:
        """Retorna una tarea por su ID.

        Args:
            task_id: ID de la tarea.

        Returns:
            PipelineTask o None.
        """
        return self._tasks.get(task_id)

    def get_status_summary(self) -> Dict[str, int]:
        """Retorna resumen de estados del pipeline.

        Returns:
            Dict con conteo por status.
        """
        summary: Dict[str, int] = {}
        for task in self._tasks.values():
            summary[task.status.name] = summary.get(task.status.name, 0) + 1
        return summary
