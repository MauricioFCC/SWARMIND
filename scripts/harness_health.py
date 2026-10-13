"""harness_health.py — CLI del panel de salud del harness (0 LLM, determinista).

WHAT: construye el :class:`harness.observability.harness_health.HarnessHealthReporter`
con los medidores DISPONIBLES y emite el panel unificado de salud. Agrega:
    - Token telemetry, leida desde su JSONL si existe (``--telemetry``).
    - Library Drift, desde su tracker JSONL (``--drift-path``).
    - Skill Lift, con el catalogo/runner DETERMINISTAS reales (o runner delgado
      demo si no estan disponibles).
    - Consistency, con un runner delgado determinista (aun no hay catalogo real).

WHY: los medidores existian pero estaban cableados SIN trafico ni reporte; este
CLI "activa" la telemetria, corre la evaluacion determinista y produce un
veredicto con exit code, para ejecucion programada (CI/periodic). NO requiere
LLM: todos los runners son puros/reproducibles.

WHERE: utilidad operativa; consumido por el workflow ``skills-quality.yml``
(non-blocking por defecto) y el paso ``--check-health`` de
``scripts/evolve_close_loop.py``; ejecutable a mano en local.

Medidores de lift/consistency:
    - Skill Lift usa el catalogo/runner DETERMINISTAS reales
      (``harness.evals.skill_lift_tasks`` / ``skill_lift_runner``) cuando estan
      disponibles; si no, degrada a un runner delgado demo.
    - Consistency usa un runner delgado demo (aun no hay catalogo real); se
      sustituye por un verifier determinista del catalogo cuando exista.

Uso:
    uv run python scripts/harness_health.py --markdown
    uv run python scripts/harness_health.py --json --output harness-health.json
    uv run python scripts/harness_health.py --telemetry harness/db/token_telemetry.json

Exit codes: 0 = healthy/degraded; 1 = unhealthy (gate para CI); 2 = error de
argumentos/entrada.
"""

from __future__ import annotations

import argparse
import itertools
import json
import logging
import sys
from collections.abc import Iterator
from pathlib import Path

#: Raiz del repo en sys.path[1] (SEG: nunca index 0) para importar el harness.
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(1, str(_ROOT))

from harness.evals.consistency import (
    DEFAULT_RUNS,
    ConsistencyEvaluator,
)
from harness.evals.skill_lift import (
    DEFAULT_TRIALS,
    SkillLiftEvaluator,
)
from harness.evolve_loop.library_drift import LibraryDriftManager
from harness.evolve_loop.skill_utility import SkillUtilityTracker
from harness.observability.harness_health import (
    HarnessHealthReporter,
    HealthThresholds,
)
from harness.observability.token_telemetry import TokenTelemetry

logger = logging.getLogger("swarmind.harness_health")

#: Ruta por defecto del JSONL de telemetria de tokens (si no existe => None).
_DEFAULT_TELEMETRY = _ROOT / "harness" / "db" / "token_telemetry.json"

#: Separador de listas en la CLI.
_LIST_SEP = ","

#: Tareas demo del runner delgado de consistencia (estables por defecto).
_DEMO_CONSISTENCY_TASKS: tuple[str, ...] = ("stable-demo",)
#: Tareas que alternan True/False de forma reproducible (pass rate 0.5 => flaky).
_FLAKY_TASKS: frozenset[str] = frozenset({"flaky-demo"})
#: Estado determinista por tarea para la alternancia del runner delgado.
_STATE: dict[str, Iterator[bool]] = {}

#: Skills/tareas demo del runner delgado de skill lift (lift nulo => neutral).
_DEMO_SKILLS: tuple[str, ...] = ("health-demo",)
_DEMO_LIFT_TASKS: tuple[str, ...] = ("task-1",)

_EXIT_OK = 0
_EXIT_UNHEALTHY = 1
_EXIT_ERROR = 2


def _thin_consistency_runner(task_id: str) -> bool:
    """Runner DELGADO determinista de consistencia (0 LLM, 0 red).

    Las tareas de ``_FLAKY_TASKS`` alternan ``True``/``False`` de forma
    reproducible (``pass_rate = 0.5`` => "flaky"); cualquier otra tarea pasa
    siempre (=> "stable"). Permite demostrar el gate de consistencia sin un
    catalogo real de verifiers.

    Args:
        task_id: Identificador de la tarea.

    Returns:
        True si la tarea pasa en este run, False en caso contrario.
    """
    if task_id in _FLAKY_TASKS:
        return next(_STATE.setdefault(task_id, itertools.cycle([True, False])))
    return True


def _thin_lift_runner(task_id: str, skill: str | None) -> bool:
    """Runner DELGADO determinista de skill lift (0 LLM, 0 red).

    Reproduce la MISMA condicion con y sin skill (lift nulo => "neutral"), de
    modo que el catalogo demo no introduzca skills daninas espurias.

    Args:
        task_id: Identificador de la tarea (ignorado: resultado constante).
        skill: Skill activa o ``None`` para la ablacion.

    Returns:
        Siempre ``True`` (lift nulo sobre el catalogo demo).
    """
    del task_id, skill  # API de contrato; el demo es constante.
    return True


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
        Parser configurado con las opciones de medidores, catalogo y salida.
    """
    parser = argparse.ArgumentParser(
        description="Panel unificado de salud del harness (0 LLM, determinista).",
    )
    parser.add_argument(
        "--telemetry",
        default=str(_DEFAULT_TELEMETRY),
        help="Ruta del JSONL de telemetria de tokens (default: harness/db).",
    )
    parser.add_argument(
        "--drift-path",
        default=None,
        help="Ruta del JSONL del tracker de Library Drift (default: real).",
    )
    parser.add_argument(
        "--consistency-tasks",
        default=_LIST_SEP.join(_DEMO_CONSISTENCY_TASKS),
        help="Tareas del runner de consistencia separadas por coma.",
    )
    parser.add_argument(
        "--runs",
        type=int,
        default=DEFAULT_RUNS,
        help=f"Corridas por tarea de consistencia (default: {DEFAULT_RUNS}).",
    )
    parser.add_argument(
        "--skills",
        default=None,
        help="Skills del runner de lift separadas por coma (default: catalogo real).",
    )
    parser.add_argument(
        "--trials",
        type=int,
        default=DEFAULT_TRIALS,
        help=f"Corridas por tarea/condicion de lift (default: {DEFAULT_TRIALS}).",
    )
    output_group = parser.add_mutually_exclusive_group()
    output_group.add_argument(
        "--json",
        action="store_true",
        help="Emite el panel como JSON (default: Markdown).",
    )
    output_group.add_argument(
        "--markdown",
        action="store_true",
        help="Emite el panel como Markdown (default).",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Ruta opcional para persistir el reporte JSON (best-effort).",
    )
    return parser


def _load_telemetry(path: str) -> TokenTelemetry | None:
    """Carga la telemetria desde su JSONL si existe (best-effort).

    Args:
        path: Ruta del archivo de telemetria.

    Returns:
        ``TokenTelemetry`` reconstruido, o ``None`` si el archivo no existe o
        no es legible (``from_json`` ya loguea el detalle).
    """
    if not Path(path).is_file():
        return None
    return TokenTelemetry.from_json(Path(path))


def _build_drift(drift_path: str | None) -> LibraryDriftManager:
    """Construye el medidor de drift (tracker aislable por CLI).

    Args:
        drift_path: Ruta del JSONL del tracker; ``None`` usa el default real.

    Returns:
        ``LibraryDriftManager`` sobre el tracker indicado.
    """
    if drift_path is None:
        return LibraryDriftManager()
    tracker = SkillUtilityTracker(path=Path(drift_path))
    return LibraryDriftManager(tracker=tracker)


def _try_catalog() -> tuple[object, object] | None:
    """Importa (best-effort) el catalogo y runner REALES de Skill Lift.

    WHAT: el catalogo determinista (``harness.evals.skill_lift_tasks``) y su
    runner (``harness.evals.skill_lift_runner``) viven en modulos de frontera;
    se cargan de forma perezosa para que el CLI degrade al runner delgado si no
    estan disponibles. WHY: DI (hexagonal) sin acoplar el CLI a un artefacto
    opcional. WHERE: ``_build_lift_report``.

    Returns:
        Tupla ``(catalog, runner)`` instanciados, o ``None`` si los modulos no
        estan disponibles (ImportError).
    """
    try:
        from harness.evals.skill_lift_runner import SkillLiftRunner
        from harness.evals.skill_lift_tasks import SkillLiftCatalog
    except ImportError:
        return None
    catalog = SkillLiftCatalog()
    return catalog, SkillLiftRunner(catalog=catalog)


def _build_lift_report(args: argparse.Namespace) -> dict[str, float]:
    """Construye el reporte de Skill Lift (catalogo real o runner delgado).

    WHAT: si el catalogo/runner reales estan disponibles, evalua las skills del
    catalogo con su verifier determinista; si no, usa el runner delgado demo.
    WHY: "activar" el medidor de lift con trafico real cuando exista, sin
    romper cuando el catalogo no este instalado. WHERE: ``_build_reporter``.

    Args:
        args: Argumentos parseados de la CLI.

    Returns:
        Reporte de ``SkillLiftEvaluator.report`` (conteos useful/neutral/harmful).
    """
    requested = _parse_csv(args.skills) if args.skills is not None else None
    real = _try_catalog()
    if real is not None:
        catalog, runner = real
        skills = requested if requested else list(catalog.skills())
        evaluator = SkillLiftEvaluator(runner=runner)
        results = [
            evaluator.evaluate(skill, [task.id for task in catalog.tasks_for_skill(skill)], trials=args.trials)
            for skill in skills
            if catalog.tasks_for_skill(skill)
        ]
        return evaluator.report(results)

    evaluator = SkillLiftEvaluator(runner=_thin_lift_runner)
    skills = requested if requested else list(_DEMO_SKILLS)
    return evaluator.report(
        evaluator.evaluate_all(skills, list(_DEMO_LIFT_TASKS), trials=args.trials)
    )


def _build_reporter(args: argparse.Namespace) -> HarnessHealthReporter:
    """Construye el reporter con los medidores DISPONIBLES (DI).

    Args:
        args: Argumentos parseados de la CLI.

    Returns:
        ``HarnessHealthReporter`` con telemetria/drift/consistency/lift.
    """
    telemetry = _load_telemetry(args.telemetry)
    drift = _build_drift(args.drift_path)

    consistency_tasks = _parse_csv(args.consistency_tasks)
    consistency_evaluator = ConsistencyEvaluator(runner=_thin_consistency_runner)
    consistency_report = consistency_evaluator.report(
        consistency_evaluator.evaluate_all(consistency_tasks, runs=args.runs)
    )

    return HarnessHealthReporter(
        telemetry=telemetry,
        drift=drift,
        consistency=consistency_report,
        lift_report=_build_lift_report(args),
        thresholds=HealthThresholds.from_env(),
    )


def main(argv: list[str] | None = None) -> int:
    """Punto de entrada de la CLI.

    Args:
        argv: Argumentos de linea de comandos (``None`` usa ``sys.argv``).

    Returns:
        Codigo de salida: 0 si healthy/degraded, 1 si unhealthy, 2 si hay error
        de argumentos/entrada.
    """
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    args = _build_parser().parse_args(argv)

    if args.runs < 1 or args.trials < 1:
        logger.error(
            "WHAT: --runs y --trials deben ser >= 1 | WHERE: main() "
            "| WHY: sin corridas no hay medicion."
        )
        return _EXIT_ERROR

    if not _parse_csv(args.consistency_tasks) or (
        args.skills is not None and not _parse_csv(args.skills)
    ):
        logger.error(
            "WHAT: --consistency-tasks (y --skills si se indica) deben tener "
            "elementos | WHERE: main() | WHY: sin tareas/skills no hay catalogo "
            "que medir."
        )
        return _EXIT_ERROR

    reporter = _build_reporter(args)
    health = reporter.collect()

    if args.json:
        print(json.dumps(reporter.report(), ensure_ascii=False, indent=2))
    else:
        print(reporter.summary_markdown())

    if args.output is not None:
        reporter.to_json(Path(args.output))

    if health.verdict == "unhealthy":
        return _EXIT_UNHEALTHY
    return _EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
