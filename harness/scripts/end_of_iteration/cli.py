"""
CLI — Argument parsing for the end-of-iteration pipeline.

Extraído de __init__.py para reducir el monolito.
"""
from __future__ import annotations

import argparse


def build_parser() -> argparse.ArgumentParser:
    """Construye el parser de argumentos para el pipeline de fin de iteracion."""
    parser = argparse.ArgumentParser(
        description="End of Iteration Pipeline - Calidad, Seguridad, Docs, Tokens",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Ejemplos:\n"
            "  python harness/scripts/end_of_iteration.py\n"
            "  python harness/scripts/end_of_iteration.py --quick\n"
            "  python harness/scripts/end_of_iteration.py --auto\n"
            "  python harness/scripts/end_of_iteration.py --skip-bugs\n"
            "  python harness/scripts/end_of_iteration.py --skip-sec\n"
            "  python harness/scripts/end_of_iteration.py --skip-docs\n"
            "  python harness/scripts/end_of_iteration.py --dry-run\n"
            "  python harness/scripts/end_of_iteration.py --report\n"
            "  python harness/scripts/end_of_iteration.py --pre-commit\n"
            "  python harness/scripts/end_of_iteration.py --pre-commit --quick\n"
            "  python harness/scripts/end_of_iteration.py --watch\n"
        ),
    )
    parser.add_argument("--quick", action="store_true",
                        help="Modo rapido: solo bugs + tokens, salta security y docs")
    parser.add_argument("--auto", action="store_true",
                        help="Modo automatico: pipeline completo + commit si no hay criticals")
    parser.add_argument("--skip-bugs", action="store_true", help="Salta bug hunting")
    parser.add_argument("--skip-sec", "--skip-security", action="store_true",
                        dest="skip_security", help="Salta security scan")
    parser.add_argument("--skip-docs", action="store_true", help="Salta docs update")
    parser.add_argument("--dry-run", action="store_true", help="Solo muestra que haria")
    parser.add_argument("--report", action="store_true", help="Muestra el ultimo reporte guardado")
    parser.add_argument("--pre-commit", action="store_true",
                        help="Modo pre-commit: solo staged files, silencioso, no interactivo")
    parser.add_argument("--watch", action="store_true",
                        help="Modo watch: solo fases 1, 2, 4, salida concisa")
    return parser


def parse_args(argv=None) -> argparse.Namespace:
    """Parsea argumentos y retorna namespace."""
    parser = build_parser()
    return parser.parse_args(argv)
