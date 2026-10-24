"""Guard de skills anti prompt-injection (ciclo 11.18 — arXiv 2608.29596).

WHAT: auditoria determinista de skills contra (1) la spec Agent Skills de
la Linux Foundation (frontmatter obligatorio: name/domain/description/
version/project_agnostic) y (2) prosa hostil de prompt-injection: overrides
de instrucciones previas, override de rol, acceso a system prompt,
ejecucion remota ``curl | sh`` y exfiltracion — patrones en la descripcion
o el cuerpo, case-insensitive.

WHY: los skills se cargan como contexto de sistema confiable; prosa hostil
dentro de un skill = inyeccion persistente que sobrevive sesiones y
maquinas (los skills se sincronizan entre harnesses).

WHERE: ``harness/security/skill_guard.py``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import yaml

#: Campos obligatorios del frontmatter (spec Agent Skills, Linux Foundation).
FRONTMATTER_REQUIRED = (
    "name",
    "domain",
    "description",
    "version",
    "project_agnostic",
)

#: Patrones de prosa hostil: (nombre, regex) — arXiv 2608.29596.
HOSTILE_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "ignore_prior",
        re.compile(
            r"ignore\s+(?:all\s+)?(?:previous|prior|above)\s+"
            r"(?:instructions?|rules?|prompts?)",
            re.IGNORECASE,
        ),
    ),
    (
        "disregard_prior",
        re.compile(r"disregard\s+(?:the\s+)?(?:previous|prior|earlier)", re.IGNORECASE),
    ),
    ("role_override", re.compile(r"you\s+are\s+now\b", re.IGNORECASE)),
    ("system_prompt_access", re.compile(r"system\s+prompt", re.IGNORECASE)),
    (
        "hidden_directive",
        re.compile(r"(?:do not tell|don'?t tell|hide\s+this|keep\s+this\s+secret)", re.IGNORECASE),
    ),
    (
        "exfiltration",
        re.compile(
            r"exfiltrat|(?:send|post|upload|leak)\s+(?:the\s+)?"
            r"(?:contents?\s+of\s+)?(?:~/|\./|\.env\b|credentials?|api\s*keys?|secrets?)",
            re.IGNORECASE,
        ),
    ),
    (
        "remote_exec",
        re.compile(
            r"(?:curl|irm|iwr|invoke-webrequest)\b[^\n]{0,80}"
            r"\|\s*(?:sh|bash|zsh|powershell|pwsh|iex)\b",
            re.IGNORECASE,
        ),
    ),
)


@dataclass(frozen=True)
class SkillFinding:
    """Hallazgo inmutable de una auditoria de skills (orden determinista)."""

    skill: str
    category: str
    severity: str
    detail: str


def parse_frontmatter(text: str) -> dict[str, object]:
    """Parsea el frontmatter YAML delimited por ``---``.

    Raises:
        ValueError: Sin delimitador, sin cierre, YAML corrupto o que no
            resuelve a mapping (errors accionables WHAT/WHY/WHERE).
    """
    if not text.startswith("---"):
        raise ValueError(
            "WHAT: skill sin delimitador '---' de frontmatter. WHY: la "
            "spec Agent Skills exige frontmatter. WHERE: parse_frontmatter."
        )
    lines = text.splitlines()
    end = None
    for index, line in enumerate(lines[1:], start=1):
        if line.strip() == "---":
            end = index
            break
    if end is None:
        raise ValueError(
            "WHAT: frontmatter sin linea de cierre '---'. WHY: el cuerpo "
            "no seria detectable. WHERE: parse_frontmatter."
        )
    try:
        data = yaml.safe_load("\n".join(lines[1:end]))
    except yaml.YAMLError as exc:
        raise ValueError(
            f"WHAT: frontmatter YAML corrupto ({exc}). WHY: se exige "
            "metadata parseable. WHERE: parse_frontmatter."
        ) from None
    if not isinstance(data, dict):
        raise ValueError(  # noqa: TRY004 - ValueError es el contrato del guard
            "WHAT: frontmatter no resuelve a mapping (es "
            f"{type(data).__name__}). WHY: se exigen pares clave-valor. "
            "WHERE: parse_frontmatter."
        )
    return data


def scan_skill_text(skill: str, text: str) -> tuple[SkillFinding, ...]:
    """Audita el texto de un skill: frontmatter + prosa hostil.

    Args:
        skill: Nombre del skill (para el finding).
        text: Contenido completo (frontmatter + cuerpo).

    Returns:
        Tupla de ``SkillFinding`` ordenada por (skill, categoria, detalle).
        Frontmatter invalido corta el scan con un finding de alta severidad.
    """
    try:
        front = parse_frontmatter(text)
    except ValueError as exc:
        return (
            SkillFinding(
                skill=skill,
                category="invalid_frontmatter",
                severity="high",
                detail=str(exc),
            ),
        )
    findings: list[SkillFinding] = []
    for field in FRONTMATTER_REQUIRED:
        if front.get(field) in (None, ""):
            findings.append(
                SkillFinding(
                    skill=skill,
                    category="missing_field",
                    severity="medium",
                    detail=f"campo obligatorio ausente: '{field}'",
                )
            )
    for pattern_name, pattern in HOSTILE_PATTERNS:
        match = pattern.search(text)
        if match:
            findings.append(
                SkillFinding(
                    skill=skill,
                    category="hostile_prose",
                    severity="high",
                    detail=f"patron {pattern_name}: '{match.group(0)[:40]}'",
                )
            )
    return tuple(sorted(findings, key=lambda f: (f.skill, f.category, f.detail)))


def scan_skills_root(root: Path) -> tuple[SkillFinding, ...]:
    """Audita todos los skills descubiertos como ``<root>/<skill>/SKILL.md``.

    Raises:
        ValueError: Si algum SKILL.md no es UTF-8 valido.
    """
    findings: list[SkillFinding] = []
    for skill_md in sorted(root.glob("*/SKILL.md")):
        try:
            text = skill_md.read_text(encoding="utf-8")
        except UnicodeDecodeError as exc:
            raise ValueError(
                f"WHAT: {skill_md} no es UTF-8 valido ({exc}). WHY: los "
                "skills deben ser texto UTF-8. WHERE: scan_skills_root."
            ) from None
        findings.extend(scan_skill_text(skill_md.parent.name, text))
    return tuple(findings)
