#!/usr/bin/env python3
"""check_skills_standard.py — gate de conformidad Agent Skills (AAIF L1).

WHAT: valida cada ``.opencode/skills/*/SKILL.md`` con el validador oficial
``SkillFrontmatterValidator`` (agentskills.io): ``name`` 1-64 y regex, directorio
coincidente, ``description`` 1-1024, campos opcionales y estructura.
WHY: el estándar Agent Skills fue donado a la Agentic AI Foundation (Linux
Foundation) y lo usan 70+ plataformas; un gate vendor-neutral evita que una
skill nueva rompa la interoperabilidad. Nuestro ``validate_skills --strict``
sigue cubriendo las convenciones SWARMIND (min.md, registry, digest).
WHERE: ``scripts/check_skills_standard.py``; cableado en ``scripts/xtask.py``.

Uso:
    python scripts/check_skills_standard.py
    python scripts/check_skills_standard.py --json
    python scripts/check_skills_standard.py --skills-dir .opencode/skills

Exit: 0 = todas conformes; 1 = al menos una inválida; 2 = error de uso.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(1, str(Path(__file__).resolve().parents[1]))  # SEG: raiz repo

from harness.memory_rag.skill_frontmatter import SkillFrontmatterValidator

#: Directorio por defecto de skills del repo.
DEFAULT_SKILLS_DIR = Path(__file__).resolve().parents[1] / ".opencode" / "skills"


def _summary(reports: tuple) -> dict[str, object]:
    """Resume los reportes del validador (total, válidas, inválidas, warnings)."""
    invalidas = [report for report in reports if not report.valid]
    return {
        "total": len(reports),
        "valid": len(reports) - len(invalidas),
        "warnings": sum(len(report.warnings) for report in reports),
        "invalid": [
            {"skill": report.skill_name, "errors": list(report.errors)}
            for report in invalidas
        ],
    }


def _build_parser() -> argparse.ArgumentParser:
    """Parser CLI del gate."""
    parser = argparse.ArgumentParser(description="Conformidad Agent Skills L1")
    parser.add_argument("--skills-dir", default=str(DEFAULT_SKILLS_DIR))
    parser.add_argument("--json", action="store_true", help="Salida máquina")
    return parser


def main(argv: list[str] | None = None) -> int:
    """Ejecuta el gate y devuelve exit 0/1."""
    args = _build_parser().parse_args(argv)
    reports = SkillFrontmatterValidator().validate_all(args.skills_dir)
    resumen = _summary(reports)
    if args.json:
        print(json.dumps(resumen, indent=2, ensure_ascii=False))
    else:
        for report in reports:
            estado = "OK  " if report.valid else "FAIL"
            print(f"{estado} {report.skill_name:<28} warnings={len(report.warnings)}")
        print(f"Agent Skills L1: {resumen['valid']}/{resumen['total']} conformes")
    invalidas = resumen["invalid"]
    if invalidas:
        for item in invalidas:
            for error in item["errors"]:
                print(f"FAIL {item['skill']}: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
