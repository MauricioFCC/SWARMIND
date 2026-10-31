"""Gate de reglas Ruff en preview con allowlist explícita.

`preview = true` global habilita reglas preview de categorías no seleccionadas
(medido en Ruff 0.16.6: 138 hallazgos nuevos en UP/SIM/NPY/C4/PLW/D301/PT/...),
así que el repo NO lo activa. Este gate corre Ruff con `--preview` y una
selección explícita de códigos que ya están en cero: si alguna vuelve a
aparecer, falla. El resto de la deuda preview la vigila
`scripts/check_ruff_ratchet.py` (solo falla si un conteo sube).

Uso:

    python scripts/check_ruff_preview.py            # reporta
    python scripts/check_ruff_preview.py --gate     # falla si hay hallazgos
    python scripts/check_ruff_preview.py --list     # imprime la allowlist
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent

#: Reglas preview ya en cero (se aplicaron sus fixes seguros en 11.62).
#: Al llegar a cero un código nuevo, se añade aquí y queda bloqueado.
ALLOWLIST: tuple[str, ...] = (
    "FURB101",  # read-whole-file
    "FURB103",  # write-whole-file
    "FURB110",  # if-exp-instead-of-or-operator
    "FURB140",  # reimplemented-starmap
    "FURB142",  # for-loop-set-mutations
    "FURB152",  # math-constant
    "FURB154",  # duplicated-union-members
    "RUF021",   # parenthesize-chained-operators
    "RUF031",   # incorrectly-parenthesized-tuple-in-subscript
    "RUF056",   # falsy-dict-get-fallback
)

#: Rutas analizadas (mismo alcance que el lint del repo).
TARGETS: tuple[str, ...] = ("harness", "scripts")


def run_ruff(selectors: tuple[str, ...] = ALLOWLIST) -> list[dict[str, Any]]:
    """Ejecuta Ruff en preview con la allowlist y devuelve los hallazgos.

    Args:
        selectors: Códigos de regla a comprobar.

    Returns:
        Lista de hallazgos JSON (vacía si todo está en cero).

    Raises:
        RuntimeError: Si Ruff falla con un error distinto de "hay hallazgos".
    """
    command = [
        sys.executable,
        "-m",
        "ruff",
        "check",
        *TARGETS,
        "--preview",
        "--select",
        ",".join(selectors),
        "--output-format",
        "json",
    ]
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
            "check_ruff_preview | WHAT=ruff_fallo | "
            f"WHY=exit_{completed.returncode} | WHERE=run_ruff | "
            f"stderr={completed.stderr.strip()[:500]}"
        )
    try:
        findings = json.loads(completed.stdout or "[]")
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            "check_ruff_preview | WHAT=json_invalido | "
            f"WHY={exc} | WHERE=run_ruff"
        ) from exc
    return findings if isinstance(findings, list) else []


def failures(findings: list[dict[str, Any]]) -> list[str]:
    """Convierte los hallazgos en mensajes accionables.

    Args:
        findings: Salida JSON de Ruff.

    Returns:
        Lista de mensajes ``archivo:linea codigo mensaje``.
    """
    messages: list[str] = []
    for finding in findings:
        code = str(finding.get("code") or "SIN_CODIGO")
        location = finding.get("location") or {}
        filename = str(finding.get("filename") or "?")
        line = location.get("row", "?") if isinstance(location, dict) else "?"
        text = str(finding.get("message") or "")
        messages.append(f"{filename}:{line} {code} {text}")
    return messages


def main(argv: list[str] | None = None) -> int:
    """Entrypoint del gate.

    Args:
        argv: Argumentos CLI (``None`` usa ``sys.argv``).

    Returns:
        Exit code (0 = allowlist limpia, 1 = regresión).
    """
    parser = argparse.ArgumentParser(description="Allowlist de reglas Ruff preview")
    parser.add_argument("--gate", action="store_true", help="falla si hay hallazgos")
    parser.add_argument("--json", action="store_true", help="salida JSON")
    parser.add_argument("--list", action="store_true", help="imprime la allowlist")
    args = parser.parse_args(argv)

    if args.list:
        print("\n".join(ALLOWLIST))
        return 0

    messages = failures(run_ruff())
    if args.json:
        print(json.dumps({"allowlist": list(ALLOWLIST), "failures": messages}, indent=2))
    elif messages:
        print(f"Ruff preview allowlist: {len(messages)} hallazgos")
        for message in messages:
            print(f"  {message}")
    else:
        print(f"Ruff preview allowlist limpia ({len(ALLOWLIST)} reglas)")

    if messages and args.gate:
        print("\nGATE RUFF PREVIEW: FAIL", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
