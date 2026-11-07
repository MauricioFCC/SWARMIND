"""skill_lift.py — CLI de Paired Evaluation / Skill Lift (runner REAL determinista).

WHAT: corre :class:`harness.evals.skill_lift.SkillLiftEvaluator` con el runner
REAL :class:`harness.evals.skill_lift_runner.SkillLiftRunner` sobre el catalogo
de tareas :class:`harness.evals.skill_lift_tasks.SkillLiftCatalog`. Mide el delta
de pass rate (Δpp) con/sin skill sobre las MISMAS tareas (SkillsBench,
arXiv:2602.12670) y clasifica cada skill como useful/neutral/harmful.

WHY: el evaluador NO ejecuta LLM; el runner por defecto es DETERMINISTA (carga el
SKILL.md real del repo, produce la reference de la tarea y corre su verifier puro).
Asi el lift es reproducible en CI (0 LLM, 0 red). En produccion se inyecta un
solver LLM con la misma firma (``solver(prompt, contexto) -> salida``).

WHERE: utilidad operativa sobre ``harness/evals/``. NO aplica retiro de skills
(eso es Library Drift); solo MIDE y clasifica.

Uso:
    uv run python scripts/skill_lift.py
    uv run python scripts/skill_lift.py --skill atdd-spec,agent-rigor
    uv run python scripts/skill_lift.py --skill atdd-spec --tasks atdd-spec-cycle --trials 3
    uv run python scripts/skill_lift.py --json

Exit codes: 0 = OK; 1 = error de argumentos/entrada.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

#: Raiz del repo en sys.path[1] (SEG: nunca index 0) para importar el harness.
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(1, str(_ROOT))

from harness.evals.skill_lift import (
    DEFAULT_TRIALS,
    LiftResult,
    SkillLiftEvaluator,
)
from harness.evals.skill_lift_runner import SkillLiftRunner
from harness.evals.skill_lift_tasks import SkillLiftCatalog

logger = logging.getLogger("swarmind.skill_lift")

#: Separador de listas en la CLI.
_LIST_SEP = ","
_EXIT_OK = 0
_EXIT_ERROR = 1


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
        Parser con las opciones de skills, tareas, trials y salida JSON.
    """
    parser = argparse.ArgumentParser(
        description="Paired Evaluation / Skill Lift con runner real determinista.",
    )
    parser.add_argument(
        "--skill",
        default="",
        help="Skills a evaluar separadas por coma (default: todas las del catalogo).",
    )
    parser.add_argument(
        "--tasks",
        default="",
        help="Tareas separadas por coma (default: las tareas de cada skill).",
    )
    parser.add_argument(
        "--trials",
        type=int,
        default=DEFAULT_TRIALS,
        help=f"Corridas por tarea y condicion (default: {DEFAULT_TRIALS}).",
    )
    parser.add_argument(
        "--json", action="store_true", help="Salida machine-readable (JSON)."
    )
    return parser


def _result_payload(result: LiftResult) -> dict[str, object]:
    """Serializa un LiftResult a un dict JSON-safe.

    Args:
        result: Resultado de lift a serializar.

    Returns:
        Diccionario plano con las metricas y el veredicto.
    """
    return {
        "skill": result.skill,
        "trials": result.trials,
        "pass_with": result.pass_with,
        "pass_without": result.pass_without,
        "delta_pp": result.delta_pp,
        "verdict": result.verdict,
    }


def main(argv: list[str] | None = None) -> int:
    """Punto de entrada de la CLI.

    Args:
        argv: Argumentos de linea de comandos (``None`` usa ``sys.argv``).

    Returns:
        Codigo de salida: 0 si OK, 1 si hay error de argumentos.
    """
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    args = _build_parser().parse_args(argv)

    catalog = SkillLiftCatalog()
    skills = _parse_csv(args.skill) or catalog.skills()
    if not skills:
        logger.error(
            "WHAT: sin skills a evaluar | WHERE: main() | WHY: el catalogo esta vacio."
        )
        return _EXIT_ERROR
    if args.trials < 1:
        logger.error(
            "WHAT: --trials debe ser >= 1, recibio %d | WHERE: main()", args.trials
        )
        return _EXIT_ERROR

    explicit_tasks = _parse_csv(args.tasks)
    evaluator = SkillLiftEvaluator(runner=SkillLiftRunner(catalog=catalog))

    results: list[LiftResult] = []
    for skill in skills:
        tasks = explicit_tasks or [task.id for task in catalog.tasks_for_skill(skill)]
        if not tasks:
            logger.warning(
                "WHAT: skill sin tareas en el catalogo, se omite | WHERE: main() "
                "| skill=%s",
                skill,
            )
            continue
        results.append(evaluator.evaluate(skill, tasks, trials=args.trials))

    summary = evaluator.report(results)

    if args.json:
        print(
            json.dumps(
                {
                    "results": [_result_payload(result) for result in results],
                    "summary": summary,
                },
                ensure_ascii=False,
            )
        )
        return _EXIT_OK

    for result in results:
        logger.info(
            "%-32s delta=%+7.2fpp verdict=%-8s",
            result.skill,
            result.delta_pp,
            result.verdict,
        )
    logger.info(
        "Resumen: useful=%d neutral=%d harmful=%d mean_delta=%.2fpp",
        summary["useful"],
        summary["neutral"],
        summary["harmful"],
        summary["mean_delta_pp"],
    )
    return _EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
