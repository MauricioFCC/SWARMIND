"""skill_audit_pipeline.py — Auditoria de skills en 6 fases (ADR-0089).

WHAT: Ejecuta recon->caza->validacion->verificacion->salida->reporte
sobre una skill; la primera fase con hallazgos criticos bloquea.
WHY: Skill auditor (Cloudflare, 6 fases): pipeline fijo evita auditorias
improvisadas (cada auditor mira lo que quiere); el orden importa
(recon antes de cazar, verificar antes de reportar).
WHERE: Tras crear/modificar una skill (pre-commit) y en revision
trimestral del registry.

Uso:
    report = run_skill_audit("security-audit", {AuditPhase.RECON: fn, ...})
"""

from __future__ import annotations

import enum
import logging
from collections.abc import Callable
from dataclasses import dataclass

logger = logging.getLogger("harness.orchestrator.skill_audit_pipeline")


class AuditPhase(enum.Enum):
    """Las 6 fases en orden (enum inmutable)."""

    RECON = "recon"
    HUNT = "hunt"
    VALIDATE = "validate"
    VERIFY = "verify"
    OUTPUT = "output"
    REPORT = "report"


@dataclass(frozen=True)
class SkillAuditReport:
    """Reporte de auditoria de una skill.

    Attributes:
        skill: Nombre auditado.
        phases: Fases ejecutadas (orden).
        passed: True si ninguna fase reporto criticos.
        blocked_at: Fase que bloqueo ("" si paso).
    """

    skill: str
    phases: tuple[str, ...]
    passed: bool
    blocked_at: str = ""


def _is_critical(findings: list[str]) -> bool:
    """True si algun hallazgo es critico (prefijo CRITICAL:).

    Args:
        findings: Hallazgos de la fase.

    Returns:
        True si hay al menos un critico.
    """
    return any(f.strip().upper().startswith("CRITICAL") for f in findings)


def run_skill_audit(
    skill: str, phase_fns: dict[AuditPhase, Callable[[str], list[str]]]
) -> SkillAuditReport:
    """Ejecuta las 6 fases en orden sobre la skill.

    Args:
        skill: Nombre de la skill (no vacio).
        phase_fns: Mapa fase -> fn(skill) -> hallazgos (puede ser parcial;
            fases sin fn se consideran limpias).

    Returns:
        SkillAuditReport (blocked_at = primera fase con criticos).

    Raises:
        ValueError: Si skill esta vacio (WHAT+WHY+WHERE).
    """
    if not skill.strip():
        raise ValueError(
            "WHAT: skill vacia. "
            "WHY: sin skill no hay auditoria. "
            "WHERE: run_skill_audit"
        )
    done: list[str] = []
    for phase in AuditPhase:
        fn = phase_fns.get(phase)
        findings = fn(skill) if fn is not None else []
        done.append(phase.value)
        if _is_critical(findings):
            logger.warning(
                "skill_audit_pipeline: %s bloqueada en %s", skill, phase.value
            )
            return SkillAuditReport(
                skill=skill, phases=tuple(done),
                passed=False, blocked_at=phase.value,
            )
    return SkillAuditReport(skill=skill, phases=tuple(done), passed=True)
