#!/usr/bin/env python3
"""self_update.py — auto-actualizacion anti-reversion (CLI SWARMIND).

Uso:
  python scripts/self_update.py --check   # solo informa estado vs remoto
  python scripts/self_update.py --apply   # aplica si los guards lo permiten
  python scripts/self_update.py --audit   # verifica monotonicidad del journal
  --allow-downgrade --justification "..." # downgrade deliberado y auditable

Exit: 0 = ok/degradado; 1 = violaciones de audit o ff fallido; 2 = error fatal.
Spec: specs/self-update.md (ciclo 11.21 SDD). Cross-platform sin shells.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # SEG: raiz repo

from harness.self_update import (
    Action,
    UpdateError,
    apply_update,
    audit_log,
    check_remote,
    fmt_version,
)

_REPO = Path(__file__).resolve().parents[1]
_LOG_DEFAULT = _REPO / ".swarmind" / "update_log.jsonl"


def _build_parser() -> argparse.ArgumentParser:
    """Parser CLI: acciones mutuamente exclusivas + opciones comunes."""
    parser = argparse.ArgumentParser(description="Auto-actualizacion anti-reversion")
    acciones = parser.add_mutually_exclusive_group()
    acciones.add_argument("--check", action="store_true", help="Solo informa estado")
    acciones.add_argument("--apply", action="store_true", help="Aplica si es seguro")
    acciones.add_argument("--audit", action="store_true", help="Verifica monotonicidad")
    parser.add_argument("--repo", default=str(_REPO), help="Raiz del repo local")
    parser.add_argument("--remote", default="origin", help="Nombre del remote git")
    parser.add_argument("--branch", default=None, help="Rama objetivo (default: actual)")
    parser.add_argument("--log", default=str(_LOG_DEFAULT), help="Ruta del journal")
    parser.add_argument(
        "--allow-downgrade",
        action="store_true",
        help="Permite downgrade SOLO con --justification (auditable)",
    )
    parser.add_argument("--justification", default="", help="Justificacion del downgrade")
    return parser


def _cmd_audit(log_path: Path) -> int:
    """Imprime violaciones de monotonicidad; exit 1 si hay."""
    violaciones = audit_log(log_path)
    for violacion in violaciones:
        print(f"  REVERSION: {violacion}")
    if violaciones:
        print(f"audit: {len(violaciones)} violacion(es)")
        return 1
    print("audit: OK sin violaciones")
    return 0


def _cmd_check(args: argparse.Namespace) -> int:
    """Informe de estado frente al remoto (sin mutar nada)."""
    check = check_remote(Path(args.repo), remote=args.remote, branch=args.branch)
    remoto = fmt_version(check.remote_version) if check.remote_version else "?"
    print(
        f"estado={check.state.value} behind={check.behind} ahead={check.ahead} "
        f"local={fmt_version(check.local_version)} remote={remoto}"
    )
    if check.detail:
        print(f"detalle={check.detail}")
    return 0


def _cmd_apply(args: argparse.Namespace, log_path: Path) -> int:
    """Aplica con guards anti-reversion; exit 1 solo si el ff falla."""
    repo = Path(args.repo)
    check = check_remote(repo, remote=args.remote, branch=args.branch)
    result = apply_update(
        check,
        repo=repo,
        log_path=log_path,
        allow_downgrade=args.allow_downgrade,
        downgrade_justification=args.justification,
    )
    print(f"accion={result.action.value} changed={result.changed} detail={result.detail}")
    return 1 if result.action is Action.FAILED else 0


def main(argv: list[str] | None = None) -> int:
    """Entrada CLI (exportada para tests); nunca lanza UpdateError."""
    args = _build_parser().parse_args(argv)
    log_path = Path(args.log)
    try:
        if args.audit:
            return _cmd_audit(log_path)
        if args.apply:
            return _cmd_apply(args, log_path)
        return _cmd_check(args)
    except UpdateError as exc:
        print(f"error fatal: {exc}")
        return 2


if __name__ == "__main__":
    sys.exit(main())
