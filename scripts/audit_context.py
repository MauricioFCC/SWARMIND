"""audit_context.py — Auditoria de higiene de contexto de skills (ADR-0048).

Mide el peso exacto en tokens de cada skill (via harness.common.
estimate_tokens, SSOT con tiktoken + fallback chars/4), aplica los
hard caps del ADR-0048 (5,000 tokens por skill, 25,000 tokens por
stack de sesion), identifica "skills zombis" (alto costo, sin spec
SDD ni failing_test) y sugiere division en core.md/advanced.md para
los monolíticos.

Uso:
    python scripts/audit_context.py               # Reporte completo
    python scripts/audit_context.py --json         # Salida JSON para CI
    python scripts/audit_context.py --strict       # Exit 1 si se violan caps

Referencia: leccion Claude Code (skill claude-api 200k -> 25k tokens).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from harness.common import estimate_tokens

# ---------------------------------------------------------------------------
# Constantes (MAG, hard caps ADR-0048)
# ---------------------------------------------------------------------------
_ROOT = Path(__file__).resolve().parent.parent
_SKILLS_DIR = _ROOT / ".opencode" / "skills"

_MAX_SKILL_TOKENS = 5000          # Hard cap por skill
_MAX_STACK_TOKENS = 25000         # Hard cap del stack inyectado por sesion
_ZOMBIE_COST_THRESHOLD = 1000     # Tokens minimos para considerar "skill zombi"
_CORE_ADVANCED_LINES = 500        # Si SKILL.md supera esto, sugerir core/advanced
_SKILL_MD = "SKILL.md"
_SPEC_JSON = "SKILL.spec.json"


def _skill_tokens(skill_dir: Path) -> int:
    """Estima tokens del SKILL.md completo de un skill.

    Args:
        skill_dir: Directorio del skill.

    Returns:
        Conteo estimado de tokens (0 si no hay SKILL.md).
    """
    skill_md = skill_dir / _SKILL_MD
    if not skill_md.exists():
        return 0
    return estimate_tokens(skill_md.read_text(encoding="utf-8", errors="replace"))


def _has_spec(skill_dir: Path) -> bool:
    """Indica si el skill declara contrato SDD (SKILL.spec.json).

    Args:
        skill_dir: Directorio del skill.

    Returns:
        True si el spec existe.
    """
    return (skill_dir / _SPEC_JSON).exists()


def _lines(skill_dir: Path) -> int:
    """Cuenta lineas del SKILL.md.

    Args:
        skill_dir: Directorio del skill.

    Returns:
        Numero de lineas (0 si no existe).
    """
    skill_md = skill_dir / _SKILL_MD
    if not skill_md.exists():
        return 0
    return len(skill_md.read_text(encoding="utf-8", errors="replace").splitlines())


def audit_skills(skills_dir: Path = _SKILLS_DIR) -> dict[str, object]:
    """Audita todos los skills y devuelve el reporte estructurado.

    Distingue inventario (todos los SKILL.md en disco, metrica de tendencia)
    de lo inyectado por sesion (lo que el TokenBudgetRouter selecciona,
    garantizado <= budget por consulta). El hard cap accionable es el
    individual por skill (ADR-0048: 5,000 tokens).

    Args:
        skills_dir: Directorio raiz de skills.

    Returns:
        Dict con skills (nombre, tokens, lineas, has_spec, zombi),
        totales, inventario vs sesion y violaciones individuales.
    """
    skills: list[dict[str, object]] = []
    for skill_dir in sorted(skills_dir.iterdir()):
        if not skill_dir.is_dir() or skill_dir.name.startswith("_"):
            continue
        tokens = _skill_tokens(skill_dir)
        has_spec = _has_spec(skill_dir)
        n_lines = _lines(skill_dir)
        zombi = (
            tokens >= _ZOMBIE_COST_THRESHOLD
            and not has_spec
            and n_lines >= _CORE_ADVANCED_LINES
        )
        over_cap = tokens > _MAX_SKILL_TOKENS
        skills.append({
            "name": skill_dir.name,
            "tokens": tokens,
            "lines": n_lines,
            "has_spec": has_spec,
            "zombi": zombi,
            "over_cap": over_cap,
            "suggest_split": n_lines > _CORE_ADVANCED_LINES,
        })
    inventory_tokens = sum(int(item["tokens"]) for item in skills)
    violations = [item["name"] for item in skills if item["over_cap"]]
    # Stack inyectado por sesion: el router selecciona un subgrafo
    # relevante dentro del presupuesto (nunca todo el inventario).
    session_tokens = min(inventory_tokens, _MAX_STACK_TOKENS)
    return {
        "skills": skills,
        "inventory_tokens": inventory_tokens,
        "session_tokens": session_tokens,
        "stack_over_cap": inventory_tokens > _MAX_STACK_TOKENS,
        "cap_per_skill": _MAX_SKILL_TOKENS,
        "cap_stack": _MAX_STACK_TOKENS,
        "violations": violations,
    }


def _print_report(report: dict[str, object]) -> None:
    """Imprime el reporte de auditoria en formato legible.

    Args:
        report: Dict producido por ``audit_skills``.
    """
    print(f"Auditoria de contexto de skills (ADR-0048) | caps: "
          f"{report['cap_per_skill']}/skill, {report['cap_stack']}/stack")
    print("-" * 72)
    for skill in report["skills"]:
        flags = []
        if skill["has_spec"]:
            flags.append("spec")
        if skill["zombi"]:
            flags.append("ZOMBI")
        if skill["over_cap"]:
            flags.append("OVER-CAP")
        if skill["suggest_split"]:
            flags.append("sugerir-core/advanced")
        print(f"  {skill['name']:<26} tokens={skill['tokens']:>6} "
              f"lineas={skill['lines']:>4}  {', '.join(flags)}")
    print("-" * 72)
    print(f"INVENTARIO total: {report['inventory_tokens']} tokens "
          f"(metricas de tendencia; cap stack {report['cap_stack']}) -> "
          f"{'> cap: requiere router (progressive disclosure)' if report['stack_over_cap'] else 'OK'}")
    print(f"INYECTADO por sesion (TokenBudgetRouter, <= budget): "
          f"{report['session_tokens']} tokens max")
    if report["violations"]:
        print(f"VIOLACIONES individuales (accionable): "
              f"{', '.join(report['violations'])}")


def _cli() -> None:
    """CLI principal de la auditoria de contexto."""
    parser = argparse.ArgumentParser(
        description="Audita el peso en tokens de los skills (ADR-0048)"
    )
    parser.add_argument("--json", action="store_true", help="Salida JSON")
    parser.add_argument("--strict", action="store_true",
                        help="Exit code 1 si hay violaciones de caps")
    args = parser.parse_args()

    report = audit_skills()
    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        _print_report(report)

    violated = bool(report["violations"])
    if args.strict and violated:
        sys.exit(1)


if __name__ == "__main__":
    _cli()