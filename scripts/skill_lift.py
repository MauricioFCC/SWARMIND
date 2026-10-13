"""skill_lift.py — CLI de Paired Evaluation / Skill Lift (dry-run).

WHAT: corre :class:`harness.evals.skill_lift.SkillLiftEvaluator` con un runner
DUMMY determinista para demostrar el flujo y el reporte por veredicto. Mide el
delta de pass rate (Δpp) con/sin skill sobre las mismas tareas (SkillsBench,
arXiv:2602.12670) y clasifica cada skill como useful/neutral/harmful.

WHY: el evaluador NO ejecuta LLM; el verifier real se inyecta como runner. Este
script no depende de LLM alguno: usa un dummy reproducible para que el flujo
sea verificable en CI y sirva de plantilla.

WHERE: utilidad operativa sobre ``harness/evals/skill_lift.py``. NO aplica
retiro de skills (eso es Library Drift); solo MIDE y clasifica.

Como inyectar el runner REAL:
    Sustituye ``dummy_runner`` por un callable con la firma
    ``(task_id: str, skill: str | None) -> bool`` que corra la tarea con/sin la
    skill y devuelva el pass/fail de un verifier DETERMINISTA. Por ejemplo:

        def real_runner(task_id: str, skill: str | None) -> bool:
            contexto = cargar_contexto(task_id, skill)   # skill=None => sin skill
            return verificar(task_id, contexto)          # bool determinista

        evaluator = SkillLiftEvaluator(runner=real_runner)

    ``skill=None`` es la condicion de ablacion (sin skill activa). Mantener el
    runner puro/determinista para que el lift sea reproducible.

Uso:
    uv run python scripts/skill_lift.py --skills pdf-forms,data-cleaning
    uv run python scripts/skill_lift.py --skills a,b --tasks t1,t2,t3 --trials 5
    uv run python scripts/skill_lift.py --dry-run

Exit codes: 0 = OK; 1 = error de argumentos/entrada.
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

#: Raiz del repo en sys.path[1] (SEG: nunca index 0) para importar el harness.
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(1, str(_ROOT))

from harness.evals.skill_lift import (
    DEFAULT_TRIALS,
    SkillLiftEvaluator,
)

logger = logging.getLogger("swarmind.skill_lift")

#: Skills de ejemplo para el dry-run.
_DEMO_SKILLS: tuple[str, ...] = ("useful-demo", "neutral-demo", "harmful-demo")
#: Tareas de ejemplo para el dry-run (2 tareas => ablacion = 0.5).
_DEMO_TASKS: tuple[str, ...] = ("task-1", "task-2")
#: Separador de listas en la CLI.
_LIST_SEP = ","
_EXIT_OK = 0
_EXIT_ERROR = 1


def _ablation_passes(task_id: str) -> bool:
    """Patron base de la condicion sin skill (la ablacion es compartida).

    Args:
        task_id: Identificador de la tarea.

    Returns:
        True solo para ``task-1`` (=> pass rate de ablacion = 0.5).
    """
    return task_id == "task-1"


def dummy_runner(task_id: str, skill: str | None) -> bool:
    """Runner DUMMY determinista para el dry-run (0 LLM, 0 red).

    La condicion de ablacion (``skill is None``) es la MISMA para todas las
    skills (mismas tareas). Sobre esa base el dummy demuestra las tres
    clasificaciones: ``useful-demo`` pasa siempre con skill (lift positivo),
    ``harmful-demo`` falla siempre con skill (lift negativo) y
    ``neutral-demo`` reproduce la ablacion (lift nulo).

    Args:
        task_id: Identificador de la tarea.
        skill: Skill activa o ``None`` para la ablacion.

    Returns:
        True si la tarea pasa en esa condicion, False en caso contrario.
    """
    if skill == "useful-demo":
        return True
    if skill == "harmful-demo":
        return False
    return _ablation_passes(task_id)


def _parse_csv(raw: str) -> list[str]:
    """Convierte una cadena ``a,b,c`` en lista de valores no vacios.

    Args:
        raw: Cadena separada por comas.

    Returns:
        Lista de elementos sin espacios alrededor, ignorando vacios.
    """
    return [item.strip() for item in raw.split(_LIST_SEP) if item.strip()]


def _build_parser() -> argparse.ArgumentParser:
    """Construye el parser de argumentos de la CLI.

    Returns:
        Parser configurado con las opciones de skills, tareas, trials y dry-run.
    """
    parser = argparse.ArgumentParser(
        description="Paired Evaluation / Skill Lift (dry-run por defecto).",
    )
    parser.add_argument(
        "--skills",
        default=_LIST_SEP.join(_DEMO_SKILLS),
        help="Skills a evaluar separadas por coma (default: demo).",
    )
    parser.add_argument(
        "--tasks",
        default=_LIST_SEP.join(_DEMO_TASKS),
        help="Tareas separadas por coma (default: demo).",
    )
    parser.add_argument(
        "--trials",
        type=int,
        default=DEFAULT_TRIALS,
        help=f"Corridas por tarea y condicion (default: {DEFAULT_TRIALS}).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Usa el runner dummy (default: siempre dry-run en este CLI).",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Punto de entrada de la CLI.

    Args:
        argv: Argumentos de linea de comandos (``None`` usa ``sys.argv``).

    Returns:
        Codigo de salida: 0 si OK, 1 si hay error de argumentos.
    """
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    args = _build_parser().parse_args(argv)

    skills = _parse_csv(args.skills)
    tasks = _parse_csv(args.tasks)
    if not skills or not tasks:
        logger.error(
            "WHAT: --skills y --tasks deben tener elementos | WHERE: main() "
            "| WHY: sin skills o sin tareas no hay ablacion."
        )
        return _EXIT_ERROR
    if args.trials < 1:
        logger.error(
            "WHAT: --trials debe ser >= 1, recibio %d | WHERE: main()",
            args.trials,
        )
        return _EXIT_ERROR

    evaluator = SkillLiftEvaluator(runner=dummy_runner)
    results = evaluator.evaluate_all(skills, tasks, trials=args.trials)
    summary = evaluator.report(results)

    for result in results:
        logger.info(
            "%-16s delta=%+7.2fpp verdict=%-8s (%s)",
            result.skill,
            result.delta_pp,
            result.verdict,
            result.notes,
        )
    logger.info(
        "Resumen: useful=%d neutral=%d harmful=%d mean_delta=%.2fpp",
        summary["useful"],
        summary["neutral"],
        summary["harmful"],
        summary["mean_delta_pp"],
    )
    logger.info(
        "Nota: runner DUMMY. Inyecta el runner real (task_id, skill|None) -> bool "
        "para medir lift con verifier determinista (ver docstring del modulo)."
    )
    return _EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
