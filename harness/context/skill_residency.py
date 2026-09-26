"""skill_residency — Presupuesto de residencia de skills y tiering (ADR-0053).

Basado en "@skills: Attention Is All You Have" (arXiv 2608.12610): las
descripciones de skills instaladas pagan 50-280 tokens en CADA mensaje y
compiten por menos de 100 slots confiables de auto-trigger. Este modulo
audita el costo residente real de la libreria de skills y recomienda tiers:

- REFERENCE: se lee en el punto de uso, 0 tokens residentes.
- SAVED: copia en el arbol git del proyecto, 0 tokens residentes.
- INSTALLED: frontmatter residente (50-100 tok), unico tier que dispara
  sin ser pedido; reservar para las skills esenciales (< TARGET_RESIDENT_MAX).

Ejemplo::

    report = audit_residency(Path(".opencode/skills"))
    print(report.total_skills, report.resident_if_all_tokens)
    tiers = recommend_tiers(report, essential={"swarm-release-ops"})
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constantes del paper (fuente unica de verdad, ADR-0053)
# ---------------------------------------------------------------------------

#: Slots confiables de auto-trigger por agente (cota superior del paper).
RESIDENT_SLOT_BUDGET = 100

#: Maximo recomendado de skills INSTALLED (residentes) por proyecto.
TARGET_RESIDENT_MAX = 10

#: Rango observado de tokens que cuesta la descripcion de una skill instalada.
DESC_TOKEN_RANGE = (50, 280)

#: Heuristica de tokenizacion: ~4 caracteres por token (GPT-style).
CHARS_PER_TOKEN = 4

#: Nombre estandar del archivo de skill (formato Agent Skills).
SKILL_FILENAME = "SKILL.md"


class SkillTier(Enum):
    """Tier de residencia de una skill (ADR-0053)."""

    REFERENCE = "reference"
    SAVED = "saved"
    INSTALLED = "installed"


# ---------------------------------------------------------------------------
# Tipos inmutables
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SkillResidency:
    """Residencia estimada de una skill individual.

    Args:
        name: Nombre de la skill (nombre del directorio).
        path: Ruta al SKILL.md.
        description_tokens: Tokens estimados del frontmatter (name+description).
    """

    name: str
    path: Path
    description_tokens: int


@dataclass(frozen=True)
class ResidencyReport:
    """Reporte de auditoria de residencia de toda la libreria.

    Args:
        skills: Residencia por skill, ordenada alfabeticamente.
        total_skills: Numero total de skills encontradas.
        resident_if_all_tokens: Costo residente total si TODAS fueran instaladas.
        warnings: Advertencias accionables detectadas.
    """

    skills: tuple[SkillResidency, ...]
    total_skills: int
    resident_if_all_tokens: int
    warnings: tuple[str, ...]


# ---------------------------------------------------------------------------
# API publica
# ---------------------------------------------------------------------------


def estimate_tokens(text: str) -> int:
    """Estima el numero de tokens de un texto (~4 chars/token).

    Args:
        text: Texto a medir.

    Returns:
        Tokens estimados (minimo 0).
    """
    return max(0, len(text) // CHARS_PER_TOKEN)


def _extract_frontmatter(skill_md: Path) -> str:
    """Extrae el bloque frontmatter YAML de un SKILL.md.

    Args:
        skill_md: Ruta al archivo SKILL.md.

    Returns:
        Contenido del frontmatter (sin delimitadores) o "" si no tiene.
    """
    try:
        raw = skill_md.read_text(encoding="utf-8")
    except OSError as exc:
        logger.warning(
            "skill_residency: no se pudo leer %s: %s (WHERE: _extract_frontmatter)",
            skill_md, exc,
        )
        return ""
    lines = raw.splitlines()
    if not lines or lines[0].strip() != "---":
        return ""
    closing = next(
        (i for i in range(1, len(lines)) if lines[i].strip() == "---"), None
    )
    if closing is None:
        return ""
    return "\n".join(lines[1:closing])


def audit_residency(skills_dir: Path) -> ResidencyReport:
    """Audita el presupuesto de residencia de una libreria de skills.

    Args:
        skills_dir: Directorio raiz con subdirectorios de skills
            (cada uno con su SKILL.md).

    Returns:
        ResidencyReport inmutable con el costo por skill y advertencias.

    Raises:
        ValueError: si skills_dir no existe o no es directorio
            (WHAT falta / WHY contrato / WHERE argumento).
    """
    root = Path(skills_dir)
    if not root.is_dir():
        raise ValueError(
            f"ValueError: el directorio de skills {root!s} no existe o no es "
            "directorio. WHY: audit_residency requiere un directorio valido "
            "con subdirectorios SKILL.md. WHERE: argumento 'skills_dir'."
        )
    entries: list[SkillResidency] = []
    for skill_md in sorted(root.glob(f"*/{SKILL_FILENAME}")):
        frontmatter = _extract_frontmatter(skill_md)
        entries.append(
            SkillResidency(
                name=skill_md.parent.name,
                path=skill_md,
                description_tokens=estimate_tokens(frontmatter),
            )
        )
    total_cost = sum(s.description_tokens for s in entries)
    warnings: list[str] = []
    if len(entries) > RESIDENT_SLOT_BUDGET:
        warnings.append(
            f"Libreria ({len(entries)}) excede el presupuesto de slots "
            f"auto-trigger ({RESIDENT_SLOT_BUDGET}): podar antes de instalar."
        )
    if len(entries) > TARGET_RESIDENT_MAX:
        warnings.append(
            f"Si todas fueran INSTALLED superarian el objetivo "
            f"(<{TARGET_RESIDENT_MAX} residentes): clasificar en tiers."
        )
    logger.info(
        "skill_residency: %d skills auditadas, costo si-todas-instaladas=%d tok",
        len(entries), total_cost,
    )
    return ResidencyReport(
        skills=tuple(entries),
        total_skills=len(entries),
        resident_if_all_tokens=total_cost,
        warnings=tuple(warnings),
    )


def recommend_tiers(
    report: ResidencyReport, essential: set[str]
) -> dict[str, SkillTier]:
    """Recomienda un tier para cada skill del reporte.

    Args:
        report: Reporte producido por audit_residency.
        essential: Nombres de skills que deben disparar sin ser pedidas
            (INSTALLED). El resto se recomienda como REFERENCE.

    Returns:
        Dict nombre -> SkillTier recomendado.

    Raises:
        ValueError: si `essential` excede TARGET_RESIDENT_MAX
            (WHAT exceso / WHY presupuesto residente / WHERE argumento).
    """
    if len(essential) > TARGET_RESIDENT_MAX:
        raise ValueError(
            f"ValueError: essential={len(essential)} excede "
            f"TARGET_RESIDENT_MAX={TARGET_RESIDENT_MAX}. WHY: solo las skills "
            "que deben disparar sin ser pedidas merecen residencia en prompt. "
            "WHERE: argumento 'essential' de recommend_tiers."
        )
    unknown = essential - {s.name for s in report.skills}
    if unknown:
        raise ValueError(
            f"ValueError: skills esenciales inexistentes: {sorted(unknown)}. "
            "WHY: no se puede instalar lo que no existe en la libreria. "
            "WHERE: argumento 'essential' de recommend_tiers."
        )
    return {
        s.name: (SkillTier.INSTALLED if s.name in essential else SkillTier.REFERENCE)
        for s in report.skills
    }
