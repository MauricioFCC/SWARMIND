"""
Security Scan CLI — politica de seguridad de paths portables (ADR-0035).

Escanea el repositorio en busca de:
  - Rutas absolutas con nombre de usuario de la maquina (PATHS_NO_PORTABLES)
  - $HOME literal en codigo Python (HOME_LITERAL_PY)
  - Secretos hardcodeados: API keys, tokens, passwords, PEM (SECRETO)
  - Archivos .env con credenciales trackeados en git (ENV_TRACKEADO)

Exit code: 0 = sin violaciones, 1 = violaciones encontradas (integra con CI
y pre-commit hooks).

Uso:
    python scripts/security_scan.py              # Escanear repo actual
    python scripts/security_scan.py --repo ../x  # Otro repositorio
    python scripts/security_scan.py --quiet      # Solo exit code
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from harness.qa.security_policy import SecurityPolicyScanner


def main() -> int:
    """Punto de entrada de la CLI.

    Returns:
        0 si no hay violaciones, 1 si hay (para CI).
    """
    parser = argparse.ArgumentParser(
        description="Security policy scan (ADR-0035): paths portables + secretos",
    )
    parser.add_argument(
        "--repo", type=str, default=".",
        help="Ruta del repositorio a escanear (default: .)",
    )
    parser.add_argument(
        "--quiet", action="store_true",
        help="No imprimir el reporte, solo exit code",
    )
    args = parser.parse_args()

    scanner = SecurityPolicyScanner(repo_root=Path(args.repo))
    findings = scanner.scan()

    if not args.quiet:
        print(scanner.print_report(findings))

    return 1 if scanner.has_violations(findings) else 0


if __name__ == "__main__":
    sys.exit(main())
