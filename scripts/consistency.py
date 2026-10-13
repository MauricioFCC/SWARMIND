"""consistency.py — CLI de consistencia run-to-run (dry-run reproducible).

WHAT: corre :class:`harness.evals.consistency.ConsistencyEvaluator` con un runner
DUMMY determinista para demostrar el flujo y el reporte de estabilidad. Sigue la
tecnica frontera arXiv:2607.27942 (guia #4): medir la consistencia run-to-run
JUNTO a la accuracy. Reporta ``consistency_score`` = fraccion de tareas "stable".

WHY: el evaluador NO ejecuta LLM; el verifier real se inyecta como runner. Este
script no depende de LLM alguno: usa un dummy reproducible (misma secuencia de
resultados en cada corrida) para que el flujo sea verificable en CI y sirva de
plantilla.

WHERE: utilidad operativa sobre ``harness/evals/consistency.py``.

Como inyectar el runner REAL:
    Sustituye ``dummy_runner`` por un callable con la firma
    ``(task_id: str) -> bool`` que corra la tarea y devuelva el pass/fail de un
    verifier DETERMINISTA. Por ejemplo:

        def real_runner(task_id: str) -> bool:
            return verificar(task_id)   # bool determinista

        evaluator = ConsistencyEvaluator(runner=real_runner)

    Mantener el runner puro/determinista para que la consistencia sea
    reproducible (una varianza alta con runner aleatorio mide ruido, no la
    estabilidad del sistema bajo prueba).

Uso:
    uv run python scripts/consistency.py
    uv run python scripts/consistency.py --tasks t1,t2,t3 --runs 10
    uv run python scripts/consistency.py --dry-run

Exit codes: 0 = OK; 1 = error de argumentos/entrada.
"""

from __future__ import annotations

import argparse
import itertools
import logging
import sys
from pathlib import Path

#: Raiz del repo en sys.path[1] (SEG: nunca index 0) para importar el harness.
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(1, str(_ROOT))

from harness.evals.consistency import (
    DEFAULT_RUNS,
    ConsistencyEvaluator,
)

logger = logging.getLogger("swarmind.consistency")

#: Tareas de ejemplo para el dry-run (una por veredicto).
_DEMO_TASKS: tuple[str, ...] = ("stable-demo", "flaky-demo", "broken-demo")
#: Separador de listas en la CLI.
_LIST_SEP = ","
_EXIT_OK = 0
_EXIT_ERROR = 1
#: Tareas del dummy que alternan True/False (pass rate 0.5 => "flaky").
_ALTERNATING_TASKS: frozenset[str] = frozenset({"flaky-demo"})


def dummy_runner(task_id: str) -> bool:
    """Runner DUMMY determinista para el dry-run (0 LLM, 0 red).

    Cada tarea demuestra un veredicto:
        - ``stable-demo``: pasa siempre (pass rate 1.0).
        - ``flaky-demo``: alterna True/False (pass rate 0.5).
        - ``broken-demo``: falla siempre (pass rate 0.0).
        - Cualquier otra tarea de ``--tasks`` se trata como stable (True).

    La alternancia es reproducible: el estado (un ``itertools.cycle``) se guarda
    por tarea en ``_STATE`` y se consume en orden determinista.

    Args:
        task_id: Identificador de la tarea.

    Returns:
        True si la tarea pasa en este run, False en caso contrario.
    """
    if task_id in _ALTERNATING_TASKS:
        return next(_STATE.setdefault(task_id, itertools.cycle([True, False])))
    return task_id != "broken-demo"


#: Estado determinista por tarea para el runner dummy (solo alternancia).
_STATE: dict[str, itertools.cycle[bool]] = {}


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
        Parser configurado con las opciones de tareas, corridas y dry-run.
    """
    parser = argparse.ArgumentParser(
        description="Consistencia run-to-run (dry-run por defecto).",
    )
    parser.add_argument(
        "--tasks",
        default=_LIST_SEP.join(_DEMO_TASKS),
        help="Tareas separadas por coma (default: demo).",
    )
    parser.add_argument(
        "--runs",
        type=int,
        default=DEFAULT_RUNS,
        help=f"Corridas por tarea (default: {DEFAULT_RUNS}).",
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

    tasks = _parse_csv(args.tasks)
    if not tasks:
        logger.error(
            "WHAT: --tasks debe tener elementos | WHERE: main() "
            "| WHY: sin tareas no hay medicion de consistencia."
        )
        return _EXIT_ERROR
    if args.runs < 1:
        logger.error(
            "WHAT: --runs debe ser >= 1, recibio %d | WHERE: main()",
            args.runs,
        )
        return _EXIT_ERROR

    evaluator = ConsistencyEvaluator(runner=dummy_runner)
    results = evaluator.evaluate_all(tasks, runs=args.runs)
    summary = evaluator.report(results)

    for result in results:
        logger.info(
            "%-14s p=%.2f var=%.4f verdict=%-7s (%s)",
            result.task_id,
            result.pass_rate,
            result.variance,
            result.verdict,
            result.notes,
        )
    logger.info(
        "Resumen: stable=%d flaky=%d broken=%d consistency_score=%.4f mean_var=%.4f",
        summary["stable"],
        summary["flaky"],
        summary["broken"],
        summary["consistency_score"],
        summary["mean_variance"],
    )
    logger.info(
        "Nota: runner DUMMY. Inyecta el runner real (task_id) -> bool para medir "
        "consistencia con verifier determinista (ver docstring del modulo)."
    )
    return _EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
