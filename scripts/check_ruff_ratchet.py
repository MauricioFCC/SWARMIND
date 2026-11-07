"""Ratchet de Ruff para reglas preview (PERF/FURB/RUF).

Ruff **no** tiene baseline nativo (issue astral-sh/ruff#1149 abierto). Este
script implementa el patrón recomendado: contar hallazgos por regla con
``ruff check --output-format=json`` y comparar contra un baseline versionado.
El gate **solo falla si un conteo sube**; si baja, se acepta (y se puede
regenerar el baseline).

Uso:

    python scripts/check_ruff_ratchet.py            # reporta conteos
    python scripts/check_ruff_ratchet.py --gate     # falla si sube algún conteo
    python scripts/check_ruff_ratchet.py --write-baseline
    python scripts/check_ruff_ratchet.py --json

El baseline vive en ``scripts/ruff_baseline.json`` (conteo por código, no
líneas ni archivos: un fix que mueve el hallazgo de archivo no cuenta como
regresión).
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
BASELINE_PATH = Path(__file__).with_name("ruff_baseline.json")

#: Reglas objetivo: rendimiento, modernización y refactors de Ruff.
DEFAULT_SELECT = "PERF,FURB,RUF"

#: Rutas analizadas (mismo alcance que el lint del repo).
TARGETS: tuple[str, ...] = ("harness", "scripts")


def run_ruff(select: str = DEFAULT_SELECT, preview: bool = True) -> list[dict[str, Any]]:
    """Ejecuta Ruff y devuelve los hallazgos como JSON.

    Args:
        select: Códigos/selectores de reglas (``"PERF,FURB,RUF"``).
        preview: Si True, habilita reglas en preview.

    Returns:
        Lista de hallazgos (``[]`` si no hay o si Ruff no está disponible).

    Raises:
        RuntimeError: Si Ruff falla con un error no relacionado con hallazgos.
    """
    command = [
        sys.executable,
        "-m",
        "ruff",
        "check",
        *TARGETS,
        "--select",
        select,
        "--output-format",
        "json",
    ]
    if preview:
        command.append("--preview")
    completed = subprocess.run(
        command,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if completed.returncode not in (0, 1):
        raise RuntimeError(
            "check_ruff_ratchet | WHAT=ruff_fallo | "
            f"WHY=exit_{completed.returncode} | WHERE=run_ruff | "
            f"stderr={completed.stderr.strip()[:500]}"
        )
    try:
        findings = json.loads(completed.stdout or "[]")
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            "check_ruff_ratchet | WHAT=json_invalido | "
            f"WHY={exc} | WHERE=run_ruff"
        ) from exc
    return findings if isinstance(findings, list) else []


def count_by_rule(findings: list[dict[str, Any]]) -> dict[str, int]:
    """Cuenta hallazgos por código de regla.

    Args:
        findings: Salida JSON de Ruff.

    Returns:
        Mapa ``codigo -> conteo`` ordenado por código.
    """
    counter = Counter(
        str(finding.get("code") or "SIN_CODIGO") for finding in findings
    )
    return dict(sorted(counter.items()))


def load_baseline() -> dict[str, int]:
    """Lee el baseline versionado (vacío si no existe o está corrupto).

    Returns:
        Mapa ``codigo -> conteo``.
    """
    if not BASELINE_PATH.exists():
        return {}
    try:
        payload = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return {str(key): int(value) for key, value in payload.items()}


def write_baseline(counts: dict[str, int]) -> None:
    """Escribe el baseline actual (ratchet).

    Args:
        counts: Mapa ``codigo -> conteo``.
    """
    BASELINE_PATH.write_text(
        json.dumps(counts, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(f"baseline Ruff escrito: {BASELINE_PATH} ({len(counts)} reglas)")


def evaluate(counts: dict[str, int], baseline: dict[str, int]) -> list[str]:
    """Compara conteos contra el baseline; solo reporta incrementos.

    Args:
        counts: Conteos actuales por regla.
        baseline: Baseline versionado por regla.

    Returns:
        Lista de fallos legibles (vacía si no hay regresiones).
    """
    failures: list[str] = []
    for code, current in counts.items():
        previous = baseline.get(code, 0)
        if current > previous:
            failures.append(
                f"{code}: {previous} -> {current} (+{current - previous})"
            )
    return failures


def main(argv: list[str] | None = None) -> int:
    """Entrypoint del ratchet.

    Args:
        argv: Argumentos CLI (``None`` usa ``sys.argv``).

    Returns:
        Exit code (0 = OK, 1 = regresión).
    """
    parser = argparse.ArgumentParser(description="Ratchet de Ruff (preview)")
    parser.add_argument("--gate", action="store_true", help="falla si sube un conteo")
    parser.add_argument("--write-baseline", action="store_true", help="fija el baseline")
    parser.add_argument("--json", action="store_true", help="salida JSON")
    parser.add_argument(
        "--select", default=DEFAULT_SELECT, help=f"reglas (default {DEFAULT_SELECT})"
    )
    args = parser.parse_args(argv)

    counts = count_by_rule(run_ruff(select=args.select))
    if args.write_baseline:
        write_baseline(counts)
    failures = evaluate(counts, load_baseline())
    total = sum(counts.values())

    if args.json:
        print(
            json.dumps(
                {"counts": counts, "failures": failures, "total": total},
                indent=2,
                sort_keys=True,
            )
        )
    else:
        print(f"Ruff preview ({args.select}): {total} hallazgos en {len(counts)} reglas")
        for code, current in counts.items():
            print(f"  {code:<10} {current}")

    if failures and args.gate:
        print("\nGATE RUFF: FAIL", file=sys.stderr)
        for failure in failures:
            print(f"  - {failure}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
