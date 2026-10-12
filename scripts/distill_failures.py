"""distill_failures.py — CLI de destilacion failure→skill (cierre Socratic-SWE).

WHAT: aterriza en un comando invocable el loop de destilacion que hoy no tenia
disparador: lee el ``FailureRegistry`` real (``harness/db/failures.jsonl``),
filtra los fallos RESUELTOS con severidad ``>= --min-severity`` y persiste un
``ProceduralSkill`` de avoidance por cada uno via ``FailureDistiller``
(dedup idempotente por nombre determinista).
WHY: el ``FailureDistiller`` existia pero nada lo invocaba post-merge; el skill
evolve declaraba ``!evolve failures distill`` sin implementacion de CLI.
WHERE: ``uv run python scripts/distill_failures.py [--dry-run|--json]``.

Uso:
    python scripts/distill_failures.py                      # destila (severity high por defecto)
    python scripts/distill_failures.py --dry-run            # lista sin escribir en skills/auto/
    python scripts/distill_failures.py --min-severity low   # incluye fallos MEDIUM
    python scripts/distill_failures.py --max-skills 5       # limita la corrida
    python scripts/distill_failures.py --json               # salida machine-readable

Exit codes: 0 = OK (incluso si no se destila ninguno, best-effort como el
resto del loop); 1 = error fatal (registry o memoria inaccesibles).
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import tempfile
from collections.abc import Callable
from pathlib import Path

#: Raiz del repo en sys.path[1] (SEG: nunca index 0) para importar el harness.
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(1, str(_ROOT))

from harness.evolve_loop.failure_distiller import FailureDistiller
from harness.evolve_loop.procedural_memory import AUTO_SKILLS_DIR, ProceduralMemory
from harness.failure_registry.registry import FailureRecord, Severity

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("distill_failures")

#: Firma del factory de distillers (punto de inyeccion para tests y dry-run).
DistillerFactory = Callable[[Severity], FailureDistiller]

#: Mapa choice CLI -> ``Severity`` (MAG: sin strings magicos dispersos).
_SEVERITY_CHOICES: dict[str, Severity] = {s.value: s for s in Severity}


def _preview_memory() -> ProceduralMemory:
    """Construye una memoria para el preview sin efectos sobre el dir real.

    WHAT: en ``--dry-run`` no se debe crear ``.opencode/skills/auto/``.
    WHY: ``ProceduralMemory`` hace ``mkdir`` en su constructor; si el dir real
    no existe se usa uno efimero, cuyo set de skills previos (vacio) es
    equivalente al estado real.
    WHERE: ``scripts/distill_failures.py,_preview_memory``.

    Returns:
        Memoria apuntando al dir real si existe; si no, a uno temporal efimero.
    """
    auto_dir = Path(AUTO_SKILLS_DIR)
    if auto_dir.is_dir():
        return ProceduralMemory(skills_dir=str(auto_dir))
    return ProceduralMemory(skills_dir=tempfile.mkdtemp(prefix="swarmind_preview_"))


def _default_factory(*, dry_run: bool) -> DistillerFactory:
    """Factory por defecto: registry/memoria reales, memoria segura en dry-run.

    Args:
        dry_run: Si True, el distiller usa una memoria que no toca el dir real.

    Returns:
        Callable ``(Severity) -> FailureDistiller`` con las dependencias reales.
    """
    if dry_run:
        return lambda severity: FailureDistiller(
            memory=_preview_memory(), min_severity=severity
        )
    return lambda severity: FailureDistiller(min_severity=severity)


def _build_parser() -> argparse.ArgumentParser:
    """Construye el parser de argumentos del CLI.

    Returns:
        Parser con ``--max-skills``, ``--min-severity``, ``--dry-run`` y ``--json``.
    """
    parser = argparse.ArgumentParser(
        description=(
            "Destila fallos resueltos del FailureRegistry en skills de avoidance."
        )
    )
    parser.add_argument(
        "--max-skills", type=int, default=10, help="maximo de skills por corrida"
    )
    parser.add_argument(
        "--min-severity",
        choices=list(_SEVERITY_CHOICES),
        default=Severity.HIGH.value,
        help="severidad minima para destilar un fallo",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="lista los fallos destilables sin escribir en skills/auto/",
    )
    parser.add_argument(
        "--json", action="store_true", help="salida machine-readable (JSON)"
    )
    return parser


def _emit_preview(records: list[FailureRecord], *, as_json: bool) -> None:
    """Imprime el resultado del dry-run (humano o JSON).

    Args:
        records: Fallos que originarian skills nuevos.
        as_json: True para emitir JSON machine-readable.
    """
    if as_json:
        payload = {
            "dry_run": True,
            "count": len(records),
            "preview": [
                {
                    "task": record.task,
                    "root_cause": record.root_cause,
                    "severity": record.severity.value,
                }
                for record in records
            ],
        }
        print(json.dumps(payload, ensure_ascii=False))
        return

    print(f"[DRY-RUN] Fallos destilables: {len(records)}")
    for record in records:
        print(f"  - [{record.severity.value}] {record.task} :: {record.root_cause}")


def _emit_created(created: list, *, as_json: bool) -> None:
    """Imprime el resumen de skills creados (humano o JSON).

    Args:
        created: Skills nuevos devueltos por ``distill``.
        as_json: True para emitir JSON machine-readable (campo ``created``).
    """
    if as_json:
        payload = {
            "count": len(created),
            "created": [
                {
                    "name": skill.name,
                    "description": skill.description,
                    "source_task_id": skill.source_task_id,
                }
                for skill in created
            ],
        }
        print(json.dumps(payload, ensure_ascii=False))
        return

    print(f"[OK] Skills creados: {len(created)}")
    for skill in created:
        print(f"  - {skill.name}")


def main(
    argv: list[str] | None = None, *, distiller_factory: DistillerFactory | None = None
) -> int:
    """CLI entry point: destila fallos resueltos en skills de avoidance.

    Args:
        argv: Argumentos (None = ``sys.argv[1:]``).
        distiller_factory: Factory DI ``(Severity) -> FailureDistiller`` para
            tests; None usa registry/memoria reales (memoria efimera en
            ``--dry-run`` para no tocar ``.opencode/skills/auto/``).

    Returns:
        Exit code: 0 exito (aunque no cree ningun skill); 1 error fatal.
    """
    args = _build_parser().parse_args(argv)
    min_severity = _SEVERITY_CHOICES[args.min_severity]
    factory = (
        distiller_factory
        if distiller_factory is not None
        else _default_factory(dry_run=args.dry_run)
    )

    try:
        distiller = factory(min_severity)
        if args.dry_run:
            _emit_preview(distiller.preview(max_skills=args.max_skills), as_json=args.json)
            return 0
        _emit_created(distiller.distill(max_skills=args.max_skills), as_json=args.json)
        return 0
    except Exception as exc:  # noqa: BLE001 — error fatal: best-effort no aplica
        logger.error(
            "Destilacion abortada: %s | WHY: registry o memoria inaccesibles | "
            "WHERE: scripts/distill_failures.py,main",
            exc,
        )
        return 1


if __name__ == "__main__":
    sys.exit(main())
