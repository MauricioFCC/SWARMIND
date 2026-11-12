#!/usr/bin/env python3
"""tutor.py — modo tutor socrático opt-in (aprender > delegar).

Uso:
    python scripts/tutor.py start "closures en Rust" --mode guide
    python scripts/tutor.py status
    python scripts/tutor.py attempt --wrong --note "no entendí el borrow"
    python scripts/tutor.py hint
    python scripts/tutor.py solve --confirm
    python scripts/tutor.py review
    python scripts/tutor.py off

Exit: 0 = ok; 1 = sin sesión / operación inválida; 2 = uso inválido.
Spec: docs/specs/socratic-tutor.md.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(1, str(Path(__file__).resolve().parents[1]))  # SEG: raiz repo

from harness.tutor import (
    TutorMode,
    TutorPolicy,
    TutorSession,
    TutorStore,
)


def _load(store: TutorStore, topic: str | None) -> TutorSession | None:
    """Carga la sesión pedida o la activa; avisa si no hay."""
    session = store.load(topic) if topic else store.active()
    if session is None:
        print(
            "No hay sesión de tutoría. Ejecuta: tutor start <tema>",
            file=sys.stderr,
        )
    return session


def _cmd_start(args: argparse.Namespace) -> int:
    """Crea una sesión y muestra su directiva."""
    session = TutorPolicy.start(args.topic, args.mode)
    TutorStore().save(session)
    print(TutorPolicy.directive(session))
    return 0


def _cmd_status(args: argparse.Namespace) -> int:
    """Muestra el estado (JSON o directiva)."""
    session = _load(TutorStore(), args.topic)
    if session is None:
        return 1
    print(json.dumps(session.to_dict(), indent=2, ensure_ascii=False)
          if args.json else TutorPolicy.directive(session))
    return 0


def _cmd_attempt(args: argparse.Namespace) -> int:
    """Registra un intento del alumno."""
    store = TutorStore()
    session = _load(store, args.topic)
    if session is None:
        return 1
    actualizada = TutorPolicy.record_attempt(
        session, correct=bool(args.correct), note=args.note
    )
    store.save(actualizada)
    print(json.dumps(actualizada.to_dict(), indent=2, ensure_ascii=False))
    return 0


def _cmd_hint(args: argparse.Namespace) -> int:
    """Sube una pista (nunca hasta la solución)."""
    store = TutorStore()
    session = _load(store, args.topic)
    if session is None:
        return 1
    actualizada = TutorPolicy.next_hint(session)
    store.save(actualizada)
    print(TutorPolicy.directive(actualizada))
    return 0


def _cmd_solve(args: argparse.Namespace) -> int:
    """Revela la solución solo con ``--confirm``."""
    store = TutorStore()
    session = _load(store, args.topic)
    if session is None:
        return 1
    try:
        actualizada = TutorPolicy.reveal_solution(session, confirm=args.confirm)
    except ValueError as exc:
        print(f"BLOQUEADO: {exc}", file=sys.stderr)
        return 1
    store.save(actualizada)
    print("Solución revelada. Programa un repaso: tutor review")
    return 0


def _cmd_review(args: argparse.Namespace) -> int:
    """Muestra las fechas de revisión espaciada."""
    session = _load(TutorStore(), args.topic)
    if session is None:
        return 1
    fechas = TutorPolicy.review_schedule(session)
    print(json.dumps({"topic": session.topic, "next_review": list(fechas)},
                     indent=2, ensure_ascii=False))
    return 0


def _cmd_off(args: argparse.Namespace) -> int:
    """Desactiva (borra) la sesión activa o la indicada."""
    store = TutorStore()
    session = _load(store, args.topic)
    if session is None:
        return 1
    store.clear(session.topic)
    print(f"Modo tutor desactivado para «{session.topic}».")
    return 0


def _build_parser() -> argparse.ArgumentParser:
    """Parser CLI con subcomandos del tutor."""
    parser = argparse.ArgumentParser(description="Modo tutor socrático SWARMIND")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_start = sub.add_parser("start", help="inicia una sesión")
    p_start.add_argument("topic")
    p_start.add_argument("--mode", choices=[m.value for m in TutorMode if m is not TutorMode.OFF],
                         default=TutorMode.GUIDE.value)
    p_start.set_defaults(func=_cmd_start)

    p_status = sub.add_parser("status", help="estado de la sesión")
    p_status.add_argument("--topic", default=None)
    p_status.add_argument("--json", action="store_true")
    p_status.set_defaults(func=_cmd_status)

    p_attempt = sub.add_parser("attempt", help="registra un intento")
    p_attempt.add_argument("--topic", default=None)
    grupo = p_attempt.add_mutually_exclusive_group(required=True)
    grupo.add_argument("--correct", action="store_true")
    grupo.add_argument("--wrong", dest="correct", action="store_false")
    p_attempt.add_argument("--note", default="")
    p_attempt.set_defaults(func=_cmd_attempt)

    p_hint = sub.add_parser("hint", help="sube una pista")
    p_hint.add_argument("--topic", default=None)
    p_hint.set_defaults(func=_cmd_hint)

    p_solve = sub.add_parser("solve", help="revela la solución (confirmar)")
    p_solve.add_argument("--topic", default=None)
    p_solve.add_argument("--confirm", action="store_true")
    p_solve.set_defaults(func=_cmd_solve)

    p_review = sub.add_parser("review", help="fechas de repaso")
    p_review.add_argument("--topic", default=None)
    p_review.set_defaults(func=_cmd_review)

    p_off = sub.add_parser("off", help="desactiva el modo tutor")
    p_off.add_argument("--topic", default=None)
    p_off.set_defaults(func=_cmd_off)
    return parser


def main(argv: list[str] | None = None) -> int:
    """Entrada CLI: despacha al subcomando."""
    args = _build_parser().parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
