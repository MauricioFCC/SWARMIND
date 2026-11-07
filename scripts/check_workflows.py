"""Valida los workflows de GitHub Actions (claves invalidas a nivel de paso).

GitHub rechaza un workflow con ``Invalid workflow file: ... Unexpected value
'x'`` en el arranque: el run falla sin jobs y sin check-runs, así que el error
no lo ve ningún required check. Este gate reproduce esa clase de error de forma
determinista (``release.yml`` tuvo ``path`` fuera de ``with:``).

Uso:
    python scripts/check_workflows.py            # valida .github/workflows
    python scripts/check_workflows.py rutas...   # valida rutas explicitas

Exit codes:
    0 = sin problemas, 1 = claves invalidas o YAML ilegible.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml

#: Claves permitidas en un paso de un job.
ALLOWED_STEP_KEYS: frozenset[str] = frozenset(
    {
        "continue-on-error",
        "env",
        "id",
        "if",
        "name",
        "run",
        "secrets",
        "shell",
        "timeout-minutes",
        "uses",
        "with",
        "working-directory",
    }
)

#: Claves permitidas en un job (incluye ``environment``: usado por release/docs
#: y ``steps``, la lista de pasos).
ALLOWED_JOB_KEYS: frozenset[str] = ALLOWED_STEP_KEYS | {
    "concurrency",
    "container",
    "defaults",
    "environment",
    "needs",
    "outputs",
    "permissions",
    "runs-on",
    "services",
    "steps",
    "strategy",
}


def check_workflow(path: Path) -> list[str]:
    """Valida un archivo de workflow.

    Args:
        path: Ruta al ``*.yml`` de workflows.

    Returns:
        Lista de hallazgos legibles (``archivo:job: detalle``); vacía si el
        archivo es válido. Nunca lanza: YAML ilegible, no UTF-8 o archivo
        ausente se reportan como hallazgo.
    """
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except UnicodeDecodeError:
        return [f"{path.name}: no es UTF-8 valido"]
    except OSError as exc:
        return [f"{path.name}: ilegible ({type(exc).__name__}: {exc})"]
    except yaml.YAMLError as exc:
        return [f"{path.name}: YAML ilegible ({type(exc).__name__})"]
    if not isinstance(data, dict):
        return [f"{path.name}: el workflow no es un mapping"]

    findings: list[str] = []
    jobs = data.get("jobs")
    if not isinstance(jobs, dict):
        return findings
    for job_name, job in jobs.items():
        if not isinstance(job, dict):
            findings.append(f"{path.name}:{job_name}: el job no es un mapping")
            continue
        findings.extend(
            f"{path.name}:{job_name}: clave de job invalida {key!r}"
            for key in job
            if key not in ALLOWED_JOB_KEYS
        )
        steps = job.get("steps")
        if not isinstance(steps, list):
            continue
        for index, step in enumerate(steps, start=1):
            if not isinstance(step, dict):
                findings.append(f"{path.name}:{job_name}: paso {index} no es un mapping")
                continue
            findings.extend(
                f"{path.name}:{job_name}: paso {index} clave invalida {key!r}"
                for key in step
                if key not in ALLOWED_STEP_KEYS
            )
    return findings


def default_paths() -> list[Path]:
    """Workflows por defecto (``.github/workflows``) si existen.

    Returns:
        Lista de ``*.yml`` del directorio de workflows (vacía si no existe).
    """
    directory = Path(".github/workflows")
    return sorted(directory.glob("*.yml")) if directory.is_dir() else []


def main(argv: list[str] | None = None) -> int:
    """Ejecuta el gate sobre los workflows indicados.

    Args:
        argv: Argumentos de CLI (rutas opcionales).

    Returns:
        0 si todo es válido, 1 si hay hallazgos.
    """
    parser = argparse.ArgumentParser(description="Valida workflows de GitHub Actions")
    parser.add_argument("paths", nargs="*", help="rutas a *.yml (default: workflows)")
    args = parser.parse_args(argv)
    paths = [Path(item) for item in args.paths] or default_paths()
    if not paths:
        print("check_workflows: sin workflows que validar")
        return 0

    findings: list[str] = []
    for path in paths:
        if not path.is_file():
            findings.append(f"{path}: no existe")
            continue
        findings.extend(check_workflow(path))

    if findings:
        print(f"check_workflows: {len(findings)} hallazgo(s)")
        for item in findings:
            print(" -", item)
        return 1
    print(f"check_workflows: {len(paths)} workflow(s) validos")
    return 0


if __name__ == "__main__":
    sys.exit(main())
