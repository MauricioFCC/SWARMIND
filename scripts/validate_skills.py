"""validate_skills.py — Validador de skills segun spec Agent Skills 2026 + convenciones SWARMIND.

Implementa las practicas frontier de Anthropic (agentskills.io/specification)
y cathrynlavery/diagram-design: frontmatter obligatorio, description
"pushy" con trigger keywords, SKILL.min.md presente, nombre coincide con el
directorio, limite de tamano, registry sincronizado.

Uso:
    python scripts/validate_skills.py                # Valida todos los skills
    python scripts/validate_skills.py --strict       # Errores como exit code != 0
    python scripts/validate_skills.py --quiet        # Solo errores
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Constantes (MAG)
# ---------------------------------------------------------------------------
_ROOT = Path(__file__).resolve().parent.parent
_SKILLS_DIR = _ROOT / ".opencode" / "skills"
_REGISTRY = _SKILLS_DIR / "skills_registry.yaml"

# Spec Anthropic: name <=64 chars, minusculas/digitos/hifens
_NAME_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
_MAX_NAME_LEN = 64
# Spec Anthropic: description <=1024 chars
_MAX_DESC_LEN = 1024
# Recomendacion spec: SKILL.md <500 lineas (skills con references pueden exceder)
_WARN_LINES = 500

# Descripciones que no incluyen keyword de disparo clara (spec: "pushy")
_TRIGGER_HINTS = ("diagrama", "campana", "factore", "estrategia", "comportamiento",
                  "comunicacion", "creatividad", "data", "devops", "educacion",
                  "etica", "evolucion", "ui/ux", "salud", "hedge", "legal",
                  "linguistica", "matematic", "ciencias", "punto de venta",
                  "proyecto", "psicologia", "trading", "responsive", "riesgo",
                  "rust", "cientific", "seguridad", "sociologia", "sostenibilidad",
                  "release", "alpha", "quant", "frontend", "usar con", "experiencia",
                  "interfaces", "visual")


def _parse_frontmatter(text: str) -> tuple[dict[str, str], str | None]:
    """Extrae el frontmatter YAML de un SKILL.md.

    Args:
        text: Contenido del archivo.

    Returns:
        Tupla (dict de campos, error o None).
    """
    m = re.match(r"^---\n(.*?)\n---", text, re.S)
    if not m:
        return {}, "frontmatter faltante (debe iniciar con ---)"
    fm = {}
    for line in m.group(1).splitlines():
        if ":" in line and not line.startswith(" ") and not line.startswith("-"):
            key, _, val = line.partition(":")
            fm[key.strip()] = val.strip().strip('"').strip("'")
    return fm, None


def _validate_skill(skill_dir: Path, quiet: bool) -> list[str]:
    """Valida un skill completo.

    Args:
        skill_dir: Directorio del skill (.opencode/skills/<name>).
        quiet: Si True, omite logs informativos.

    Returns:
        Lista de errores (vacía si el skill es válido).
    """
    errors: list[str] = []
    name = skill_dir.name
    sk = skill_dir / "SKILL.md"
    smin = skill_dir / "SKILL.min.md"

    # 1. SKILL.md obligatorio
    if not sk.exists():
        return [f"{name}: SKILL.md faltante"]

    text = sk.read_text(encoding="utf-8", errors="replace")
    fm, err = _parse_frontmatter(text)
    if err:
        errors.append(f"{name}: {err}")

    # 2. name: coincide con directorio, formato spec
    if "name" in fm:
        if fm["name"] != name:
            errors.append(f"{name}: frontmatter name={fm['name']!r} != directorio {name!r}")
        if not _NAME_RE.match(fm["name"]):
            errors.append(f"{name}: name invalido (solo minusculas/digitos/hifens)")
        if len(fm["name"]) > _MAX_NAME_LEN:
            errors.append(f"{name}: name excede {_MAX_NAME_LEN} chars")
    else:
        errors.append(f"{name}: campo 'name' faltante")

    # 3. description obligatoria, "pushy" con triggers, <=1024
    desc = fm.get("description", "")
    if not desc:
        errors.append(f"{name}: campo 'description' faltante (obligatorio, debe incluir keywords de disparo)")
    elif len(desc) > _MAX_DESC_LEN:
        errors.append(f"{name}: description excede {_MAX_DESC_LEN} chars ({len(desc)})")
    else:
        dl = desc.lower()
        has_trigger = any(h in dl for h in _TRIGGER_HINTS)
        if not has_trigger and not quiet:
            print(f"  ⚠  {name}: description sin keyword de disparo explicita (spec: pushy)")
        # SDO (Skill Discovery Optimization, patron obra/superpowers 2026):
        # la description DEBE empezar con la condicion de disparo ("Usar cuando"),
        # NO resumir el workflow del skill (el agente sigue la description y salta el body).
        if not dl.startswith("usar cuando"):
            errors.append(
                f"{name}: description debe empezar con 'Usar cuando <condicion>' (patron SDO); "
                f"empieza con: {desc[:50]!r}"
            )

    # 4. version presente (convencion SWARMIND)
    if "version" not in fm:
        errors.append(f"{name}: campo 'version' faltante (convencion SWARMIND)")

    # 5. project_agnostic presente (convencion SWARMIND)
    if "project_agnostic" not in fm:
        errors.append(f"{name}: campo 'project_agnostic' faltante (convencion SWARMIND)")

    # 6. SKILL.min.md presente (convencion SWARMIND)
    if not smin.exists():
        errors.append(f"{name}: SKILL.min.md faltante (convencion SWARMIND)")

    # 7. Tamano (warning spec)
    n_lines = len(text.splitlines())
    if n_lines > _WARN_LINES and not quiet:
        print(f"  ⚠  {name}: SKILL.md {n_lines} lineas (> {_WARN_LINES}; usar references/ para progressive disclosure)")

    # 8. Referencias: rutas en SKILL.md deben existir
    for ref in re.findall(r"references/([a-z0-9_-]+\.md)", text):
        if not (skill_dir / "references" / ref).exists():
            errors.append(f"{name}: referencia rota references/{ref}")

    return errors


def _validate_registry(quiet: bool) -> list[str]:
    """Valida que el registry liste todos los skills del directorio.

    Args:
        quiet: Si True, omite logs informativos.

    Returns:
        Lista de errores.
    """
    if not _REGISTRY.exists():
        return ["skills_registry.yaml faltante"]
    reg_text = _REGISTRY.read_text(encoding="utf-8", errors="replace")
    registered = set(re.findall(r"^  - name:\s*(\S+)", reg_text, re.M))
    on_disk = {d.name for d in _SKILLS_DIR.iterdir()
               if d.is_dir() and (d / "SKILL.md").exists()}
    errors = []
    for missing in sorted(on_disk - registered):
        errors.append(f"registry: skill {missing!r} en disco pero no en skills_registry.yaml")
    for extra in sorted(registered - on_disk):
        errors.append(f"registry: skill {extra!r} en registry pero no en disco")
    return errors


def main() -> None:
    """CLI principal del validador."""
    parser = argparse.ArgumentParser(description="Valida skills segun spec Agent Skills 2026")
    parser.add_argument("--strict", action="store_true", help="Exit code != 0 si hay errores")
    parser.add_argument("--quiet", action="store_true", help="Solo errores, sin warnings")
    args = parser.parse_args()

    errors: list[str] = []
    for skill_dir in sorted(_SKILLS_DIR.iterdir()):
        if not skill_dir.is_dir() or skill_dir.name == "__pycache__":
            continue
        if not args.quiet:
            print(f"• {skill_dir.name}")
        errors.extend(_validate_skill(skill_dir, args.quiet))

    errors.extend(_validate_registry(args.quiet))

    print("")
    if errors:
        print(f"❌ {len(errors)} error(es):")
        for e in errors:
            print(f"   - {e}")
        if args.strict:
            sys.exit(1)
    else:
        print("✅ Todos los skills validos (frontmatter, min.md, registry, referencias)")


if __name__ == "__main__":
    main()
