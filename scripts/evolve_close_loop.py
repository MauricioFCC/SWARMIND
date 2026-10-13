"""evolve_close_loop.py — Cierre determinista del loop EVO (validate → distill → hash → reporte).

WHAT: aterriza en un unico comando la secuencia determinista que cierra el loop
de auto-mejora cuando un humano o un workflow de CI lo invoca EXPLICITAMENTE:

    (a) valida los skills (``scripts/validate_skills.py --strict``);
    (b) si ``harness/db/failures.jsonl`` tiene fallos RESUELTOS HIGH/CRITICAL,
        los destila en skills de avoidance (``FailureDistiller``);
    (c) re-sincroniza los digests sha256 del registry SOLO si hubo cambios
        (``scripts/hash_skills_registry.py --write``);
    (d) emite un reporte JSON machine-readable (``--json``).

WHY: hoy ninguna automatizacion invoca estos scripts; el give-loop de evolve es
manual y los fallos resueltos nunca se convierten en skills ejecutables. Este
script es el PUNTO DE ENTRADA que conecta las piezas existentes sin inventar
infraestructura.

WHERE: ``uv run python scripts/evolve_close_loop.py [--dry-run] [--json]``.

IMPORTANTE — NO es un daemon: no corre en background, no hace polling ni
watchers. Es el comando que un humano (o el job de CI ``skills-quality``) dispara
de forma deliberada. Es IDEMPOTENTE: repetirlo no crea skills duplicados
(dedup por nombre determinista del ``FailureDistiller``) ni reescribe el
registry si no hay cambios.

Exit codes: 0 = OK (aunque no se destile nada, best-effort como el resto del
loop); 1 = la validacion de skills fallo (gate ``--strict``) o un paso reporto
error; 2 = error de argumentos (argparse).
"""

from __future__ import annotations

import argparse
import json
import logging
import subprocess
import sys
import tempfile
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from pathlib import Path

#: Raiz del repo en ``sys.path[1]`` (SEG: nunca index 0) para importar el harness.
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(1, str(_ROOT))

from harness.evolve_loop.failure_distiller import FailureDistiller
from harness.evolve_loop.procedural_memory import AUTO_SKILLS_DIR, ProceduralMemory
from harness.failure_registry.registry import Severity

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("evolve_close_loop")

# ---------------------------------------------------------------------------
# Constantes (MAG)
# ---------------------------------------------------------------------------
_SCRIPTS_DIR = Path(__file__).resolve().parent
_VALIDATE_SCRIPT = _SCRIPTS_DIR / "validate_skills.py"
_HASH_SCRIPT = _SCRIPTS_DIR / "hash_skills_registry.py"
_FAILURES_PATH = _ROOT / "harness" / "db" / "failures.jsonl"

#: Severidad minima (HIGH/CRITICAL) para destilar un fallo resuelto.
_MIN_SEVERITY = Severity.HIGH
#: Maximo de skills por corrida (evita corridas patologicas).
_MAX_SKILLS = 10

#: Firmas de inyeccion de dependencias (DI) — permiten test y dry-run sin IO.
Validator = Callable[[], "StepResult"]
HashWriter = Callable[[], "StepResult"]
DistillerProvider = Callable[[bool], FailureDistiller]


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------


@dataclass
class StepResult:
    """Resultado de un paso del cierre del loop.

    Attributes:
        name: Nombre del paso (``validate``, ``distill``, ``hash_registry``).
        ok: True si el paso termino sin error.
        detail: Mensaje legible (resumen o salida del subproceso).
        changed: True si el paso modifico artefactos (gate para el hash).
        data: Payload estructurado para el reporte JSON.
    """

    name: str
    ok: bool
    detail: str = ""
    changed: bool = False
    data: dict[str, object] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        """Serializa el resultado a un dict JSON-safe.

        Returns:
            Diccionario plano con los campos del paso.
        """
        return asdict(self)


# ---------------------------------------------------------------------------
# Pasos por defecto (subproceso / distiller real)
# ---------------------------------------------------------------------------


def _run_script(script: Path, *args: str) -> subprocess.CompletedProcess[str]:
    """Ejecuta un script del repo con el interprete actual.

    Args:
        script: Ruta del script a ejecutar.
        *args: Argumentos adicionales para el script.

    Returns:
        El ``CompletedProcess`` con stdout/stderr capturados (encoding UTF-8).
    """
    return subprocess.run(
        [sys.executable, str(script), *args],
        cwd=str(_ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )


def _default_validator() -> StepResult:
    """Valida los skills ejecutando ``validate_skills.py --strict``.

    Returns:
        ``StepResult`` con ``ok`` = exit code 0 del validador.
    """
    proc = _run_script(_VALIDATE_SCRIPT, "--strict")
    detail = (proc.stdout or proc.stderr or "").strip().splitlines()
    return StepResult(
        name="validate",
        ok=proc.returncode == 0,
        detail=detail[-1] if detail else "",
    )


def _default_hash_writer() -> StepResult:
    """Re-sincroniza los digests del registry con ``hash_skills_registry.py --write``.

    Returns:
        ``StepResult`` con ``ok`` = exit code 0 del script de digests.
    """
    proc = _run_script(_HASH_SCRIPT, "--write")
    detail = (proc.stdout or proc.stderr or "").strip().splitlines()
    return StepResult(
        name="hash_registry",
        ok=proc.returncode == 0,
        changed=True,
        detail=detail[-1] if detail else "",
    )


def _preview_memory() -> ProceduralMemory:
    """Construye una memoria para el dry-run sin efectos sobre el dir real.

    WHAT: en ``--dry-run`` no se debe crear ``.opencode/skills/auto/``.
    WHY: ``ProceduralMemory`` hace ``mkdir`` en su constructor; si el dir real
    no existe se usa uno efimero (set de skills previos vacio, equivalente).
    WHERE: ``scripts/evolve_close_loop.py,_preview_memory``.

    Returns:
        Memoria apuntando al dir real si existe; si no, a uno temporal efimero.
    """
    auto_dir = Path(AUTO_SKILLS_DIR)
    if auto_dir.is_dir():
        return ProceduralMemory(skills_dir=str(auto_dir))
    return ProceduralMemory(skills_dir=tempfile.mkdtemp(prefix="swarmind_closeloop_"))


def _default_distiller_provider(dry_run: bool) -> FailureDistiller:
    """Provider por defecto: registry/memoria reales (memoria segura en dry-run).

    Args:
        dry_run: Si True, el distiller usa una memoria que no toca el dir real.

    Returns:
        ``FailureDistiller`` con ``min_severity=HIGH`` (HIGH/CRITICAL).
    """
    memory = _preview_memory() if dry_run else None
    return FailureDistiller(memory=memory, min_severity=_MIN_SEVERITY)


# ---------------------------------------------------------------------------
# Orquestacion
# ---------------------------------------------------------------------------


def _safe_step(step: Callable[[], StepResult], name: str) -> StepResult:
    """Ejecuta un paso aislando fallos (ERR: error legible, sin except silencioso).

    Args:
        step: Callable que produce el ``StepResult``.
        name: Nombre del paso (para el reporte si el callable falla).

    Returns:
        El ``StepResult`` del paso, o uno ``ok=False`` con el error capturado.
    """
    try:
        return step()
    except Exception as exc:  # noqa: BLE001 — un paso no debe tumbar el reporte
        logger.error(
            "Paso '%s' fallo: %s | WHY: excepcion no controlada en el paso | "
            "WHERE: evolve_close_loop._safe_step",
            name,
            exc,
        )
        return StepResult(name=name, ok=False, detail=f"error: {exc}")


def _step_distill(dry_run: bool, provider: DistillerProvider) -> StepResult:
    """Destila fallos resueltos HIGH/CRITICAL en skills de avoidance.

    Args:
        dry_run: Si True, proyecta sin persistir (``preview``).
        provider: Provider DI ``(dry_run) -> FailureDistiller``.

    Returns:
        ``StepResult``; ``changed=True`` si creo al menos un skill nuevo.
    """
    distiller = provider(dry_run)
    if dry_run:
        pending = distiller.preview(max_skills=_MAX_SKILLS)
        return StepResult(
            name="distill",
            ok=True,
            changed=False,
            detail=f"{len(pending)} fallo(s) destilable(s) (dry-run, sin escribir)",
            data={"distillable": len(pending)},
        )

    created = distiller.distill(max_skills=_MAX_SKILLS)
    return StepResult(
        name="distill",
        ok=True,
        changed=bool(created),
        detail=f"{len(created)} skill(s) de avoidance creados",
        data={"created": [skill.name for skill in created]},
    )


def _build_parser() -> argparse.ArgumentParser:
    """Construye el parser de argumentos del CLI.

    Returns:
        Parser con ``--dry-run`` y ``--json``.
    """
    parser = argparse.ArgumentParser(
        description=(
            "Cierra el loop EVO: valida skills, destila fallos resueltos, "
            "re-sincroniza digests y reporta."
        )
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="no escribe skills ni registry; solo reporta lo que haria",
    )
    parser.add_argument(
        "--json", action="store_true", help="salida machine-readable (JSON)"
    )
    return parser


def _emit(payload: dict[str, object], *, as_json: bool) -> None:
    """Imprime el reporte del cierre del loop (humano o JSON).

    Args:
        payload: Reporte agregado (``dry_run``, ``ok``, ``steps``).
        as_json: True para emitir JSON machine-readable.
    """
    if as_json:
        print(json.dumps(payload, ensure_ascii=False))
        return

    suffix = " (dry-run)" if payload["dry_run"] else ""
    print(f"Cierre del loop EVO{suffix}")
    for step in payload["steps"]:  # type: ignore[union-attr]
        mark = "OK" if step["ok"] else "FAIL"
        print(f"  [{mark}] {step['name']}: {step['detail']}")
    print(f"Resultado global: {'OK' if payload['ok'] else 'FALLO'}")


def main(
    argv: list[str] | None = None,
    *,
    validator: Validator | None = None,
    distiller_provider: DistillerProvider | None = None,
    hash_writer: HashWriter | None = None,
) -> int:
    """Punto de entrada: cierra el loop EVO de forma determinista e idempotente.

    Un humano o el job de CI lo invoca explicitamente (NO es un daemon).

    Args:
        argv: Argumentos (None = ``sys.argv[1:]``).
        validator: Paso DI de validacion (default: subproceso ``--strict``).
        distiller_provider: Provider DI de distiller (default: registry real).
        hash_writer: Paso DI de digests (default: subproceso ``--write``).

    Returns:
        Exit code: 0 si la validacion paso y todo OK; 1 si la validacion fallo
        o algun paso reporto error.
    """
    # Hardening Windows: consolas cp1252 no codifican emojis del validador (✅).
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    args = _build_parser().parse_args(argv)

    validator = validator or _default_validator
    distiller_provider = distiller_provider or _default_distiller_provider
    hash_writer = hash_writer or _default_hash_writer

    steps: list[StepResult] = []

    # (a) Validacion de skills (gate).
    validation = _safe_step(validator, "validate")
    steps.append(validation)

    # (b) Destilacion de fallos resueltos HIGH/CRITICAL.
    steps.append(_safe_step(lambda: _step_distill(args.dry_run, distiller_provider), "distill"))

    # (c) Re-sincronizacion de digests SOLO si hubo cambios y no es dry-run.
    changed = any(step.changed for step in steps)
    if changed and not args.dry_run:
        steps.append(_safe_step(hash_writer, "hash_registry"))
    else:
        reason = "dry-run: no escribe" if args.dry_run else "sin cambios"
        steps.append(StepResult(name="hash_registry", ok=True, changed=False, detail=reason))

    ok = validation.ok and all(step.ok for step in steps)
    payload: dict[str, object] = {
        "dry_run": args.dry_run,
        "ok": ok,
        "steps": [step.to_dict() for step in steps],
    }
    _emit(payload, as_json=args.json)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
