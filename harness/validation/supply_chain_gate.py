"""supply_chain_gate.py — Triple audit local: secretos + patrones inseguros (ADR-0097).

WHAT: Escanea archivos buscando secretos hardcodeados (gitleaks-like) y
patrones inseguros (eval/exec/pickle/yaml.load/subprocess shell) con
archivo:linea. Conectable al skill-auditor como fase.
WHY: AI First triple audit: GenTrust/Socket/Snyk en Skills.sh; localmente
cubrimos el mismo hueco sin servicios externos (CI ya corre bandit+safety;
aqui va el secret-scan que falta).
WHERE: Pre-commit de skills, `skill_audit_pipeline` (fase extra) y CI.

Uso:
    report = supply_chain_gate([Path("skill.md")])
    if not report.passed: bloquear(report.findings)
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger("harness.validation.supply_chain_gate")

#: Secretos: claves API, tokens, AWS, GitHub, generic secret=/password=.
_SECRET_RES: tuple[re.Pattern[str], ...] = (
    re.compile(r"sk-[A-Za-z0-9]{6,}"),
    re.compile(r"AKIA[0-9A-Z]{16}"),
    re.compile(r"(ghp|gho|github_pat)_[A-Za-z0-9]{10,}"),
    re.compile(r"xox[bpas]-[A-Za-z0-9-]+"),
    re.compile(r"(?i)(api[_-]?key|secret|password|passwd|token)\s*[:=]\s*\S{4,}"),
)

#: Patrones de codigo inseguro (eval/exec/pickle/load/shell).
_UNSAFE_RES: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\beval\s*\("), "eval() dinamico"),
    (re.compile(r"\bexec\s*\("), "exec() dinamico"),
    (re.compile(r"pickle\.loads?|cPickle"), "pickle (deserializacion insegura)"),
    (re.compile(r"yaml\.load\s*\((?![^)]*Loader)"), "yaml.load sin Loader"),
    (re.compile(r"shell\s*=\s*True"), "subprocess con shell=True"),
)


@dataclass(frozen=True)
class SupplyReport:
    """Reporte del triple audit local.

    Attributes:
        passed: True si 0 hallazgos.
        findings: Tupla "archivo:linea: motivo".
    """

    passed: bool
    findings: tuple[str, ...] = ()


def supply_chain_gate(paths: list[Path]) -> SupplyReport:
    """Escanea archivos (secretos + inseguros), inexistentes se ignoran.

    Args:
        paths: Archivos a auditar.

    Returns:
        SupplyReport con hallazgos archivo:linea: motivo.
    """
    findings: list[str] = []
    for path in paths:
        try:
            text = Path(path).read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for lineno, line in enumerate(text.splitlines(), 1):
            for pattern in _SECRET_RES:
                if pattern.search(line):
                    findings.append(f"{path}:{lineno}: posible secreto hardcodeado")
                    break
            for pattern, reason in _UNSAFE_RES:
                if pattern.search(line):
                    findings.append(f"{path}:{lineno}: {reason}")
                    break
    if findings:
        logger.warning("supply_chain_gate: %d hallazgos", len(findings))
    return SupplyReport(passed=not findings, findings=tuple(findings))
