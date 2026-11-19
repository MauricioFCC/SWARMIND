"""blind_review.py — CLI del paquete de revisión ciega (EGM + Binnacle).

Genera un paquete reproducible (intención + criterios + diff redactado) para
que otro agente o persona revise **sin** la conversación del autor, y aplica
gates deterministas antes de cualquier juicio de modelo.

Exit code: 0 = aprobado para revisión, 1 = bloqueado por un gate.

Uso:
    python scripts/blind_review.py --spec docs/specs/x.md --diff change.diff
    git diff HEAD | python scripts/blind_review.py --spec docs/specs/x.md --git-diff
    python scripts/blind_review.py --spec s.md --diff d.diff --out packet.md
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from harness.validation.blind_review import build_blind_packet, render_markdown


def _decode(data: bytes, origin: str) -> str:
    """Decodifica el diff como UTF-8 (tolera BOM) con error legible.

    Args:
        data: Bytes leídos del archivo o de stdin.
        origin: Origen del contenido, para el mensaje de error.

    Returns:
        Diff en texto.

    Raises:
        ValueError: Si el contenido no es UTF-8 (WHAT/WHY/WHERE).
    """
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ValueError(
            f"WHAT: {origin} no es UTF-8 ({exc.reason} en byte {exc.start})\n"
            "WHY: el paquete de revisión exige texto reproducible\n"
            "WHERE: guarda el diff como UTF-8 antes de revisarlo"
        ) from exc


def _read_diff(args: argparse.Namespace) -> str:
    """Lee el diff desde un archivo o desde stdin según los argumentos.

    Args:
        args: Argumentos ya parseados (``--diff`` o ``--git-diff``).

    Returns:
        Contenido del diff en texto.

    Raises:
        SystemExit: Si no se indicó ninguna fuente de diff.
        ValueError: Si el diff no es UTF-8.
    """
    if args.git_diff:
        return _decode(sys.stdin.buffer.read(), "stdin")
    if args.diff:
        return _decode(Path(args.diff).read_bytes(), str(args.diff))
    raise SystemExit("WHAT: falta el diff\nWHY: sin cambio no hay revisión\nWHERE: --diff <archivo> | --git-diff")


def main() -> int:
    """Punto de entrada de la CLI.

    Returns:
        0 si el paquete está aprobado para revisión, 1 si algún gate bloquea.
    """
    parser = argparse.ArgumentParser(
        description="Paquete de revisión ciega con gates deterministas (EGM/Binnacle)",
    )
    parser.add_argument("--spec", required=True, help="Spec con criterios de aceptación")
    parser.add_argument("--diff", default="", help="Archivo con el diff a revisar")
    parser.add_argument(
        "--git-diff",
        action="store_true",
        help="Leer el diff de stdin (git diff | ...)",
    )
    parser.add_argument("--max-diff-chars", type=int, default=20_000, help="Tope de caracteres del diff")
    parser.add_argument("--max-files", type=int, default=25, help="Tope de archivos tocados")
    parser.add_argument("--out", default="", help="Escribir el paquete en este archivo")
    args = parser.parse_args()

    spec_md = Path(args.spec).read_text(encoding="utf-8")
    packet = build_blind_packet(
        spec_md,
        _read_diff(args),
        max_diff_chars=args.max_diff_chars,
        max_files=args.max_files,
    )
    markdown = render_markdown(packet)

    if args.out:
        Path(args.out).write_text(markdown, encoding="utf-8")
    else:
        print(markdown)

    return 0 if packet.approved_for_review else 1


if __name__ == "__main__":
    sys.exit(main())
