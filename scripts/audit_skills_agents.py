"""audit_skills_agents.py — Auditoría del checklist de skill-engineering.

Audita TODAS las skills primarias (``.opencode/skills/*/SKILL.md``) y los
agentes primarios (``.opencode/agents/*.md``, excluyendo los compañeros
``*.agent.min.md`` salvo que se use ``--include-min``) contra el checklist
frontera de la skill ``skill-engineering``: frontmatter válido, ``description``
disparador ("Usar cuando ..."), anti-triggers ("cuándo NO usar" / "Alcance:"),
tamaño <500 líneas y presencia de secciones clave.

Salida: tabla por archivo con PASS/WARN/FAIL + resumen por estado y por tipo.
``--json`` exporta la estructura para CI. ``--fix`` aplica SOLO normalizaciones
seguras de frontmatter (añade ``license``/``version``/``compatibility``
ausentes) de forma idempotente; NUNCA reescribe cuerpos ni inventa
anti-triggers.

Uso:
    python scripts/audit_skills_agents.py
    python scripts/audit_skills_agents.py --json
    python scripts/audit_skills_agents.py --strict
    python scripts/audit_skills_agents.py --fix

Exit codes: 0 = sin FAIL (o sin --strict); 1 = hay FAIL con --strict;
2 = error de entrada (I/O).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path

# ---------------------------------------------------------------------------
# Constantes (MAG)
# ---------------------------------------------------------------------------
_ROOT = Path(__file__).resolve().parents[1]
_SKILLS_DIR = _ROOT / ".opencode" / "skills"
_AGENTS_DIR = _ROOT / ".opencode" / "agents"
_MIN_AGENT_SUFFIX = ".agent.min.md"

_MAX_LINES = 500
_MAX_DESCRIPTION_CHARS = 1024
_MIN_H2_SECTIONS = 3

# Normalizaciones seguras de frontmatter (--fix). Orden estable = idempotente.
_FIX_DEFAULTS: tuple[tuple[str, str], ...] = (
    ("license", "MIT"),
    ("version", "1.0.0"),
    ("compatibility", "'Python 3.12+'"),
)

_STATUS_PRIORITY = {"PASS": 0, "WARN": 1, "FAIL": 2}

_FM_RE = re.compile(r"^---\r?\n(.*?)\r?\n---", re.DOTALL)
_H2_RE = re.compile(r"^##\s+", re.MULTILINE)
_CHECKLIST_RE = re.compile(r"^\s*-\s*\[\s*\]", re.MULTILINE)
_ANTIPATTERN_RE = re.compile(r"anti-?patr|prohibid", re.IGNORECASE)
_ANTI_TRIGGER_RE = re.compile(r"alcance:|cu[aá]ndo no usar|no usar cuando", re.IGNORECASE)


@dataclass(frozen=True)
class Check:
    """Resultado de una comprobación individual del checklist.

    Attributes:
        code: Identificador corto de la regla (p. ej. "FE001").
        status: PASS, WARN o FAIL.
        message: Descripción legible del hallazgo.
    """

    code: str
    status: str
    message: str


@dataclass(frozen=True)
class AuditResult:
    """Resultado agregado de auditar un archivo (skill o agente).

    Attributes:
        kind: "skill" o "agent".
        path: Ruta del archivo auditado.
        checks: Comprobaciones individuales (todas, incluidas las PASS).
    """

    kind: str
    path: Path
    checks: tuple[Check, ...]

    @property
    def status(self) -> str:
        """Estado agregado: el peor de sus checks (FAIL > WARN > PASS)."""
        worst = "PASS"
        for check in self.checks:
            if _STATUS_PRIORITY[check.status] > _STATUS_PRIORITY[worst]:
                worst = check.status
        return worst

    @property
    def issues(self) -> tuple[Check, ...]:
        """Checks que no pasaron (WARN o FAIL)."""
        return tuple(check for check in self.checks if check.status != "PASS")


def _parse_frontmatter(text: str) -> tuple[dict[str, str], str, str | None]:
    """Extrae el frontmatter YAML y el cuerpo de un archivo Markdown.

    Args:
        text: Contenido completo del archivo.

    Returns:
        Tupla ``(campos, body, error)``. ``error`` es None si el frontmatter
        existe y puede delimitarse; en caso contrario describe el fallo.
    """
    match = _FM_RE.match(text)
    if not match:
        return {}, text, "frontmatter faltante (el archivo debe iniciar con ---)"
    fields: dict[str, str] = {}
    for line in match.group(1).splitlines():
        stripped = line.lstrip()
        if ":" in line and stripped and not stripped.startswith(("-", "#")):
            key, _, value = line.partition(":")
            fields[key.strip()] = value.strip().strip('"').strip("'")
    return fields, text[match.end():], None


def _audit_file(path: Path, kind: str) -> AuditResult:
    """Audita un archivo contra el checklist de skill-engineering.

    Args:
        path: Ruta del archivo (SKILL.md o agente .md).
        kind: "skill" o "agent".

    Returns:
        AuditResult con todas las comprobaciones.

    Raises:
        OSError: Si el archivo no puede leerse (propagado con contexto).
    """
    text = path.read_text(encoding="utf-8", errors="replace")
    checks: list[Check] = []
    fields, body, error = _parse_frontmatter(text)

    # 1. Frontmatter válido y campos obligatorios.
    if error:
        checks.append(Check("FE001", "FAIL", error))
    if not fields.get("name"):
        checks.append(Check("FE002", "FAIL", "campo 'name' ausente"))
    elif kind == "skill" and fields["name"] != path.parent.name:
        checks.append(Check("FE003", "FAIL", f"name={fields['name']!r} != directorio {path.parent.name!r}"))
    if not fields.get("description"):
        checks.append(Check("FE004", "FAIL", "campo 'description' ausente"))

    # 2. description como único disparador (SDO + anti-triggers).
    description = fields.get("description", "")
    if description:
        if len(description) > _MAX_DESCRIPTION_CHARS:
            checks.append(Check("D001", "WARN", f"description >{_MAX_DESCRIPTION_CHARS} chars ({len(description)})"))
        if not description.lower().startswith("usar cuando"):
            checks.append(Check("D002", "WARN", "description no inicia con 'Usar cuando' (SDO)"))
        if not _ANTI_TRIGGER_RE.search(description):
            checks.append(Check("D003", "WARN", "sin anti-trigger ('Alcance:' o 'cuándo NO usar')"))

    # 3. Campos de convención SWARMIND y opcionales recomendados.
    if kind == "skill" and "version" not in fields:
        checks.append(Check("FM001", "WARN", "campo 'version' ausente"))
    if kind == "skill" and "project_agnostic" not in fields:
        checks.append(Check("FM002", "WARN", "campo 'project_agnostic' ausente"))
    if "license" not in fields:
        checks.append(Check("FM003", "WARN", "campo 'license' ausente"))
    if "compatibility" not in fields:
        checks.append(Check("FM004", "WARN", "campo 'compatibility' ausente"))

    # 4. Tamaño (progressive disclosure: <500 líneas recomendado).
    n_lines = len(text.splitlines())
    if n_lines >= _MAX_LINES:
        checks.append(Check("S001", "WARN", f"{n_lines} líneas >= {_MAX_LINES} (usar references/)"))

    # 5. Secciones clave del cuerpo (contrato + checklist + anti-patrones).
    if len(_H2_RE.findall(body)) < _MIN_H2_SECTIONS:
        checks.append(Check("SEC001", "WARN", f"menos de {_MIN_H2_SECTIONS} secciones '## '"))
    if not _CHECKLIST_RE.search(body):
        checks.append(Check("SEC002", "WARN", "sin checklist verificable ('- [ ]')"))
    if not _ANTIPATTERN_RE.search(body):
        checks.append(Check("SEC003", "WARN", "sin sección de anti-patrones/prohibiciones"))

    return AuditResult(kind=kind, path=path, checks=tuple(checks))


def _collect_targets(include_min: bool) -> list[tuple[Path, str]]:
    """Enumera los archivos a auditar (skills y agentes primarios).

    Args:
        include_min: Si True, incluye los compañeros ``*.agent.min.md``.

    Returns:
        Lista de tuplas ``(ruta, kind)`` ordenada de forma determinista.
    """
    targets: list[tuple[Path, str]] = []
    for skill_dir in sorted(_SKILLS_DIR.iterdir()):
        skill_file = skill_dir / "SKILL.md"
        if skill_dir.is_dir() and skill_file.exists():
            targets.append((skill_file, "skill"))
    for agent_file in sorted(_AGENTS_DIR.glob("*.md")):
        if not include_min and agent_file.name.endswith(_MIN_AGENT_SUFFIX):
            continue
        targets.append((agent_file, "agent"))
    return targets


def _apply_fix(path: Path) -> bool:
    """Añade al frontmatter los campos seguros ausentes (idempotente).

    Args:
        path: Ruta del archivo a normalizar.

    Returns:
        True si el archivo fue modificado; False si ya estaba normalizado o no
        tiene frontmatter delimitables.
    """
    text = path.read_text(encoding="utf-8")
    match = _FM_RE.match(text)
    if match is None:
        return False
    fields, _, _ = _parse_frontmatter(text)
    additions = [f"{key}: {value}" for key, value in _FIX_DEFAULTS if key not in fields]
    if not additions:
        return False
    new_block = match.group(1) + "\n" + "\n".join(additions)
    new_text = f"---\n{new_block}\n---" + text[match.end():]
    path.write_text(new_text, encoding="utf-8")
    return True


def _render_table(results: list[AuditResult]) -> None:
    """Imprime la tabla por archivo y el resumen por estado/tipo.

    Args:
        results: Resultados de la auditoría, en orden determinista.
    """
    width = max((len(str(r.path.relative_to(_ROOT))) for r in results), default=4)
    header = f"{'STATUS':<6} {'KIND':<6} {'ARCHIVO':<{width}}  HALLAZGOS"
    print(header)
    print("-" * len(header))
    for result in results:
        rel = str(result.path.relative_to(_ROOT))
        issues = "; ".join(f"{c.code}" for c in result.issues) or "ok"
        print(f"{result.status:<6} {result.kind:<6} {rel:<{width}}  {issues}")

    print()
    counts: dict[str, int] = {status: 0 for status in ("PASS", "WARN", "FAIL")}
    for result in results:
        counts[result.status] += 1
    print(f"RESUMEN: {len(results)} archivos | PASS={counts['PASS']} WARN={counts['WARN']} FAIL={counts['FAIL']}")
    for kind in ("skill", "agent"):
        subset = [r for r in results if r.kind == kind]
        kcounts = {s: sum(1 for r in subset if r.status == s) for s in ("PASS", "WARN", "FAIL")}
        print(f"  {kind:<6}: {len(subset)} archivos | PASS={kcounts['PASS']} WARN={kcounts['WARN']} FAIL={kcounts['FAIL']}")


def _render_json(results: list[AuditResult]) -> None:
    """Imprime los resultados en formato JSON.

    Args:
        results: Resultados de la auditoría.
    """
    payload = [
        {
            "kind": result.kind,
            "path": str(result.path.relative_to(_ROOT)).replace("\\", "/"),
            "status": result.status,
            "checks": [
                {"code": c.code, "status": c.status, "message": c.message} for c in result.checks
            ],
        }
        for result in results
    ]
    print(json.dumps({"results": payload}, ensure_ascii=False, indent=2))


def main() -> int:
    """Punto de entrada CLI: audita (y opcionalmente normaliza) skills y agentes.

    Returns:
        0 si no hay FAIL (o sin --strict); 1 si hay FAIL con --strict;
        2 si falla la lectura de un archivo.
    """
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="Audita skills y agentes contra el checklist skill-engineering")
    parser.add_argument("--json", action="store_true", help="Salida JSON para CI")
    parser.add_argument("--strict", action="store_true", help="Exit 1 si hay algún FAIL")
    parser.add_argument("--fix", action="store_true", help="Normaliza frontmatter seguro (idempotente)")
    parser.add_argument("--include-min", action="store_true", help="Incluye compañeros *.agent.min.md")
    args = parser.parse_args()

    targets = _collect_targets(args.include_min)

    if args.fix:
        fixed = 0
        for path, _ in targets:
            try:
                fixed += int(_apply_fix(path))
            except OSError as error:
                print(
                    f"ERROR WHAT: no se pudo normalizar {path} "
                    f"WHY: {error} WHERE: audit_skills_agents.py -> _apply_fix()",
                    file=sys.stderr,
                )
                return 2
        print(f"--fix: {fixed} frontmatter(s) normalizado(s) (license/version/compatibility).\n")

    results: list[AuditResult] = []
    for path, kind in targets:
        try:
            results.append(_audit_file(path, kind))
        except OSError as error:
            print(
                f"ERROR WHAT: no se pudo leer {path} "
                f"WHY: {error} WHERE: audit_skills_agents.py -> _audit_file()",
                file=sys.stderr,
            )
            return 2

    if args.json:
        _render_json(results)
    else:
        _render_table(results)

    has_fail = any(result.status == "FAIL" for result in results)
    return 1 if (args.strict and has_fail) else 0


if __name__ == "__main__":
    sys.exit(main())
