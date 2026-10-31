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
import hashlib
import re
import sys
from pathlib import Path

from hash_skills_registry import compute_skill_digest

from harness.common import estimate_tokens
from harness.context.skill_contract import load_skill_contract, validate_contract

# ---------------------------------------------------------------------------
# Constantes (MAG)
# ---------------------------------------------------------------------------
_ROOT = Path(__file__).resolve().parent.parent
_SKILLS_DIR = _ROOT / ".opencode" / "skills"
_REGISTRY = _SKILLS_DIR / "skills_registry.yaml"

# Directorios dentro de .opencode/skills que NO son skills del spec Agent Skills:
# - __pycache__: artefactos de Python
# - auto: ProceduralSkills generados por el FailureDistiller (formato propio,
#   consumidos via ProceduralMemory; NO versionados y NO declarables en el registry).
_SKIPPED_DIRS = {"__pycache__", "auto"}

# Hard cap ADR-0048: tokens maximos por skill individual
_MAX_SKILL_TOKENS = 5000

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
    m = re.match(r"^---\n(.*?)\n---", text, re.DOTALL)
    if not m:
        return {}, "frontmatter faltante (debe iniciar con ---)"
    fm = {}
    for line in m.group(1).splitlines():
        if ":" in line and not line.startswith(" ") and not line.startswith("-"):
            key, _, val = line.partition(":")
            fm[key.strip()] = val.strip().strip('"').strip("'")
    return fm, None


def _registry_digests() -> dict[str, str]:
    """Lee el registry y devuelve {skill: sha256} de los que declaran digest.

    Returns:
        Mapa de nombre de skill a digest sha256 declarado (vacío si no hay
        registry o ningún digest declarado).
    """
    if not _REGISTRY.exists():
        return {}
    text = _REGISTRY.read_text(encoding="utf-8", errors="replace")
    digests: dict[str, str] = {}
    current: str | None = None
    for line in text.splitlines():
        name_match = re.match(r"^  - name:\s*(\S+)", line)
        if name_match:
            current = name_match.group(1)
            continue
        sha_match = re.match(r"^\s+sha256:\s*(\S+)", line)
        if sha_match and current:
            digests[current] = sha_match.group(1)
    return digests


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

    # 6b. Contrato SDD (ADR-0048): SKILL.spec.json valido si existe;
    # warning de transicion si aun no migra a contrato formal.
    spec = load_skill_contract(skill_dir)
    if spec is not None:
        errors.extend(validate_contract(spec, skill_dir))
    elif not quiet:
        print(
            f"  ⚠  {name}: sin SKILL.spec.json (ADR-0048 SDD: migrar a "
            f"contrato formal con pre/postcondiciones y failing_test)"
        )

    # 6c. Hard cap de tokens por skill (ADR-0048, leccion Claude Code)
    skill_tokens = estimate_tokens(text)
    if skill_tokens > _MAX_SKILL_TOKENS:
        errors.append(
            f"{name}: {skill_tokens} tokens estimados > cap {_MAX_SKILL_TOKENS} "
            f"(ADR-0048: dividir en core.md/advanced.md con progressive disclosure)"
        )
    elif not quiet:
        print(f"  ℹ  {name}: ~{skill_tokens} tokens (cap {_MAX_SKILL_TOKENS})")

    # 6d. Digest de integridad (FR-D1, ADR-0103): si el registry declara un
    # sha256 para la skill, el estado actual en disco debe coincidir (anti
    # supply-chain / content drift). Sin digest declarado -> warning informativo
    # (migracion progresiva, no error).
    expected_digest = _registry_digests().get(name)
    if expected_digest is None:
        if not quiet:
            print(f"  ⚠  {name}: sin sha256 en registry (migracion progresiva)")
    elif compute_skill_digest(skill_dir) != expected_digest:
        errors.append(f"{name}: sha256 no coincide (content drift)")

    # 7. Tamano (warning spec)
    n_lines = len(text.splitlines())
    if n_lines > _WARN_LINES and not quiet:
        print(f"  ⚠  {name}: SKILL.md {n_lines} lineas (> {_WARN_LINES}; usar references/ para progressive disclosure)")

    # 8. Referencias: rutas en SKILL.md deben existir
    for ref in re.findall(r"references/([a-z0-9_-]+\.md)", text):
        if not (skill_dir / "references" / ref).exists():
            errors.append(f"{name}: referencia rota references/{ref}")

    # 8a. Seccion de ejemplo obligatoria (spec Agent Skills: toda skill debe
    # demostrar el patron con un caso concreto). Gate M6 de test_skill_mutants.
    if "## Ejemplo" not in text:
        errors.append(
            f"{name}: falta la seccion '## Ejemplo' (spec Agent Skills: ejemplo concreto)"
        )

    # 8b. References muertas: archivos en references/ que el SKILL.md NUNCA referencia
    # (progressive disclosure: material no enlazado nunca se carga -> warning).
    refs_dir = skill_dir / "references"
    if refs_dir.is_dir():
        referenced = set(re.findall(r"references/([a-z0-9_-]+\.md)", text))
        dead = sorted(p.name for p in refs_dir.glob("*.md") if p.name not in referenced)
        if dead and not quiet:
            print(f"  ⚠  {name}: references/ no referenciadas en SKILL.md: {', '.join(dead)}")

    # 8c. Progressive disclosure (ADR-0048): si SKILL.md enlaza core.md/advanced.md
    # (split de skill monolítico), ambos archivos deben existir.
    disclosure_links = set(re.findall(r"\[[^\]]+\]\((core|advanced)\.md\)", text))
    for part in sorted(disclosure_links):
        part_path = skill_dir / f"{part}.md"
        if not part_path.exists():
            errors.append(f"{name}: enlace de progressive disclosure a {part}.md roto (archivo faltante)")

    # 9. Frontmatter spec completo (agentskills.io): license/compatibility
    # opcionales recomendados. Warning si el skill tiene scripts/ y no declara
    # compatibility (los scripts suelen tener prerequisitos de entorno).
    has_scripts = (skill_dir / "scripts").is_dir()
    if "license" not in fm and not quiet:
        print(f"  ⚠  {name}: campo 'license' ausente (spec: opcional recomendado)")
    if has_scripts and "compatibility" not in fm and not quiet:
        print(f"  ⚠  {name}: tiene scripts/ pero sin campo 'compatibility' (spec: requisitos de entorno)")

    return errors


def _validate_unique_bodies() -> list[str]:
    """Gate M5: rechaza skills con cuerpo identico (dedup semantico barato).

    Normaliza el cuerpo (sin frontmatter, espacios colapsados, minusculas) y
    compara el sha256: dos skills con el mismo contenido y distinto nombre son
    crowding (la segunda no aporta senal).

    Returns:
        Lista de errores (vacía si todos los cuerpos son distintos).
    """
    seen: dict[str, str] = {}
    errors: list[str] = []
    for skill_dir in sorted(_SKILLS_DIR.iterdir()):
        if not skill_dir.is_dir() or skill_dir.name in _SKIPPED_DIRS:
            continue
        path = skill_dir / "SKILL.md"
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        body = re.sub(r"^---.*?---\n", "", text, count=1, flags=re.DOTALL)
        normalized = re.sub(r"\s+", " ", body).strip().lower()
        # El nombre propio se neutraliza: una copia con otro nombre conserva el
        # cuerpo (M5: duplicado semantico).
        normalized = normalized.replace(skill_dir.name.lower(), "<skill>")
        digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
        previous = seen.get(digest)
        if previous is not None:
            errors.append(
                f"{skill_dir.name}: cuerpo duplicado de {previous!r} "
                "(dedup semantico: mismo contenido, distinto nombre)"
            )
        else:
            seen[digest] = skill_dir.name
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
    registered = set(re.findall(r"^  - name:\s*(\S+)", reg_text, re.MULTILINE))
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
    # Hardening Windows: consolas cp1252 no codifican emojis/avisos unicode.
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="Valida skills segun spec Agent Skills 2026")
    parser.add_argument("--strict", action="store_true", help="Exit code != 0 si hay errores")
    parser.add_argument("--quiet", action="store_true", help="Solo errores, sin warnings")
    args = parser.parse_args()

    errors: list[str] = []
    for skill_dir in sorted(_SKILLS_DIR.iterdir()):
        if not skill_dir.is_dir() or skill_dir.name in _SKIPPED_DIRS:
            continue
        if not args.quiet:
            print(f"• {skill_dir.name}")
        errors.extend(_validate_skill(skill_dir, args.quiet))

    errors.extend(_validate_registry(args.quiet))
    errors.extend(_validate_unique_bodies())

    print()
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
