"""skill_lift_runner.py — Runner REAL y determinista para Paired Evaluation (Skill Lift).

WHAT: :class:`SkillLiftRunner` implementa la firma de runner que consume
:class:`harness.evals.skill_lift.SkillLiftEvaluator`,
``(task_id: str, skill: str | None) -> bool``. Carga el ``SKILL.md`` de la skill
(DI ``skill_loader``), sintetiza una respuesta con un ``solver`` (DI) y corre el
``verifier`` determinista de la tarea.

WHY: el evaluador necesita un runner inyectado; sin uno real solo habia runners
dummy. Este runner modela el lift de forma REPRODUCIBLE para CI: con el contexto
REAL de la skill produce la ``reference`` de la tarea (PASS) y sin contexto (o con
un contexto que NO aporta las instrucciones) produce una salida naive (FAIL). En
produccion se inyecta un ``solver`` LLM real con la MISMA firma.

Modelado del lift determinista:
    - ``skill_loader(skill)`` devuelve el contenido del ``SKILL.md``. El baseline
      comprueba que el contexto contiene la marca de frontmatter ``name: <skill>``
      (la "keyword clave" que prueba que el skill SI aporta sus instrucciones).
    - Con la marca presente => ``reference`` => verifier True (skill-on).
    - Sin contexto (ablacion) o sin marca => salida naive => verifier False.

WHERE: consumido por ``scripts/skill_lift.py`` y ``scripts/evolve_close_loop.py``.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from pathlib import Path

from harness.evals.skill_lift_tasks import (
    SKILLS_DIR,
    LiftTask,
    SkillLiftCatalog,
)

logger = logging.getLogger(__name__)

#: Ruta SSOT de skills del repo (``.opencode/skills``).
_SKILLS_DIR: Path = SKILLS_DIR
#: Archivo de skill dentro de cada directorio.
_SKILL_FILE_NAME: str = "SKILL.md"
#: Salida "naive" que produce el baseline SIN instrucciones del skill. Ningun
#: verifier del catalogo la acepta (no contiene sus keywords), por lo que el lift
#: es observable y determinista.
_NAIVE_OUTPUT: str = "No dispongo de las instrucciones necesarias para completar la tarea."

#: Cargador de contexto: ``skill_name -> contenido SKILL.md`` (cadena vacia si falla).
SkillLoader = Callable[[str], str]
#: Solver: ``(prompt, skill_context | None) -> salida``. En produccion, un LLM real.
Solver = Callable[[str, str | None], str]


def skill_marker(skill: str) -> str:
    """Token de frontmatter que identifica el contexto como perteneciente a la skill.

    Args:
        skill: Nombre de la skill.

    Returns:
        La linea de frontmatter ``name: <skill>``.
    """
    return f"name: {skill}"


def default_skill_loader(skill_name: str) -> str:
    """Carga ``.opencode/skills/<name>/SKILL.md`` (best-effort, sin excepcion).

    Args:
        skill_name: Nombre de la skill (== nombre de directorio).

    Returns:
        Contenido UTF-8 del ``SKILL.md``; cadena vacia si no existe o no se lee.
    """
    path = _SKILLS_DIR / skill_name / _SKILL_FILE_NAME
    try:
        return path.read_text(encoding="utf-8")
    except OSError as exc:
        logger.warning(
            "skill_lift_runner: no se pudo cargar %s (%s). WHAT: skill sin contexto "
            "| WHY: archivo ausente o ilegible | WHERE: default_skill_loader",
            path,
            exc,
        )
        return ""


class SkillLiftRunner:
    """Runner determinista: carga skill, resuelve output y corre el verifier de la tarea.

    Inyecta las dependencias via DI (hexagonal): el runner no conoce LLM ni IO
    concretos; ambos son callables sustituibles. El baseline por defecto es
    determinista (0 LLM, 0 red) para que el lift sea reproducible en CI.
    """

    def __init__(
        self,
        *,
        catalog: SkillLiftCatalog,
        skill_loader: SkillLoader | None = None,
        solver: Solver | None = None,
    ) -> None:
        """Inicializa el runner con el catalogo y los callables inyectables.

        Args:
            catalog: Catalogo de tareas con verifier determinista.
            skill_loader: Cargador de contexto (default: lee el ``SKILL.md`` real).
            solver: Solver alternativo (default: baseline determinista).

        Raises:
            TypeError: Si ``catalog`` no es un :class:`SkillLiftCatalog` o si
                ``skill_loader``/``solver`` no son callables.
        """
        if not isinstance(catalog, SkillLiftCatalog):
            raise TypeError(
                f"catalog debe ser SkillLiftCatalog, recibio {type(catalog).__name__}. "
                "WHAT: dependencia invalida | WHERE: SkillLiftRunner.__init__() "
                "| WHY: se requiere el catalogo de tareas."
            )
        if skill_loader is not None and not callable(skill_loader):
            raise TypeError(
                "skill_loader debe ser callable o None. WHAT: loader invalido "
                "| WHERE: SkillLiftRunner.__init__()"
            )
        if solver is not None and not callable(solver):
            raise TypeError(
                "solver debe ser callable o None. WHAT: solver invalido "
                "| WHERE: SkillLiftRunner.__init__()"
            )
        self._catalog: SkillLiftCatalog = catalog
        self._skill_loader: SkillLoader = skill_loader or default_skill_loader
        self._solver: Solver | None = solver

    def __call__(self, task_id: str, skill: str | None) -> bool:
        """Corre una tarea en una condicion y devuelve el PASS/FAIL del verifier.

        Args:
            task_id: Identificador de la tarea (debe existir en el catalogo).
            skill: Skill activa; ``None`` representa la ablacion (sin skill).

        Returns:
            True si la salida del solver satisface el verifier de la tarea.

        Raises:
            KeyError: Si ``task_id`` no existe en el catalogo.
        """
        task = self._catalog.get(task_id)
        context = self._resolve_context(skill)
        output = self._synthesize(task, context)
        return task.verifier(output)

    def _resolve_context(self, skill: str | None) -> str | None:
        """Carga el contexto de la skill (``None`` en la ablacion).

        Args:
            skill: Skill activa o ``None``.

        Returns:
            Contenido del ``SKILL.md`` o ``None`` si no hay skill.
        """
        if skill is None:
            return None
        return self._skill_loader(skill)

    def _synthesize(self, task: LiftTask, context: str | None) -> str:
        """Produce la salida con el solver inyectado o el baseline determinista.

        Args:
            task: Tarea a resolver.
            context: Contexto de skill o ``None``.

        Returns:
            Salida del solver inyectado, o del baseline si no hay solver.
        """
        if self._solver is not None:
            return self._solver(task.prompt, context)
        return self._baseline(task, context)

    @staticmethod
    def _baseline(task: LiftTask, context: str | None) -> str:
        """Baseline determinista: reference si el skill aporta instrucciones, si no naive.

        Args:
            task: Tarea a resolver (aporta prompt, reference y skill esperada).
            context: Contexto de skill o ``None``.

        Returns:
            La ``reference`` de la tarea si el contexto contiene la marca de
            frontmatter de la skill; en caso contrario, la salida naive.
        """
        if context and skill_marker(task.skill) in context:
            return task.reference
        return _NAIVE_OUTPUT


__all__ = [
    "SkillLiftRunner",
    "SkillLoader",
    "Solver",
    "default_skill_loader",
    "skill_marker",
]
