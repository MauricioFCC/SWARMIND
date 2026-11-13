#!/usr/bin/env python3
"""migrate_skills_metadata.py — migra frontmatter de skills a ``metadata``.

Mueve ``domain``, ``version`` y ``project_agnostic`` del nivel superior al mapa
``metadata`` (string→string, spec Agent Skills), preservando el resto del
frontmatter y el body. Idempotente.

Uso:
    python scripts/migrate_skills_metadata.py              # comprobar (check)
    python scripts/migrate_skills_metadata.py --write      # aplicar
    python scripts/migrate_skills_metadata.py --json       # salida máquina

Exit: 0 = sin cambios pendientes (o write ok); 1 = cambios pendientes/errores.
Spec: docs/specs/skills-metadata-migration.md.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(1, str(Path(__file__).resolve().parents[1]))  # SEG: raiz repo

from harness.context.skills_metadata import migrate_skills

#: Directorio por defecto de skills del repo.
DEFAULT_SKILLS_DIR = Path(__file__).resolve().parents[1] / ".opencode" / "skills"


def _build_parser() -> argparse.ArgumentParser:
    """Parser CLI del migrador."""
    parser = argparse.ArgumentParser(description="Migra frontmatter a metadata")
    parser.add_argument("--skills-dir", default=str(DEFAULT_SKILLS_DIR))
    parser.add_argument("--write", action="store_true", help="Aplicar cambios")
    parser.add_argument("--json", action="store_true", help="Salida máquina")
    return parser


def main(argv: list[str] | None = None) -> int:
    """Ejecuta el migrador y devuelve exit 0/1."""
    args = _build_parser().parse_args(argv)
    report = migrate_skills(Path(args.skills_dir), write=args.write)
    if args.json:
        print(
            json.dumps(
                {
                    "updated": report.updated,
                    "unchanged": report.unchanged,
                    "files": list(report.files),
                    "errors": list(report.errors),
                },
                indent=2,
                ensure_ascii=False,
            )
        )
    else:
        print(
            f"migracion: {report.updated} actualizados, "
            f"{report.unchanged} sin cambios"
        )
        for ruta in report.files:
            print(f"  - {ruta}")
        for error in report.errors:
            print(f"ERROR: {error}", file=sys.stderr)
    if report.errors:
        return 1
    return 0 if args.write or report.updated == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
