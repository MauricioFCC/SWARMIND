"""Memoria de investigación durable: brief, plan, hipótesis, hallazgos y unknowns.

Réplica del protocolo de `craft-anything`
(`crates/engine/src/tools/investigation_tools.rs`): el estado estructurado vive
en ``<proyecto>/investigation/state.json`` (revisionado) y se renderiza a
Markdown legible (``brief.md``, ``plan.md``, ``hypotheses.md``, ``findings.md``,
``handoff.md``). Así una investigación larga sobrevive a límites de contexto,
reinicios y handoffs entre agentes.

Reglas duras:
- un hallazgo exige al menos una evidencia existente en el ledger;
- un unknown resuelto exige resolución y evidencia a favor;
- toda actualización exige ``based_on_revision`` (concurrencia optimista).
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from pathlib import Path
from typing import Any

from .canonical import canonical_json, sha256_hex
from .evidence import EvidenceLedger
from .rendering import (
    render_brief,
    render_findings,
    render_handoff,
    render_hypotheses,
    render_plan,
)


class InvestigationError(ValueError):
    """Error base de la memoria de investigación."""


class StaleRevision(InvestigationError):
    """La revisión enviada no coincide con la actual (actualización obsoleta)."""


class UnknownEvidence(InvestigationError):
    """Se citó un id de evidencia que no está en el ledger."""


class StepStatus(str, Enum):
    """Estado de un paso del plan."""

    TODO = "todo"
    DOING = "doing"
    DONE = "done"
    BLOCKED = "blocked"


class HypothesisStatus(str, Enum):
    """Estado de una hipótesis."""

    TESTING = "testing"
    SUPPORTED = "supported"
    REFUTED = "refuted"
    ABANDONED = "abandoned"


class UnknownStatus(str, Enum):
    """Estado de una pregunta abierta."""

    OPEN = "open"
    INVESTIGATING = "investigating"
    RESOLVED = "resolved"
    ABANDONED = "abandoned"


class Severity(str, Enum):
    """Severidad de un unknown."""

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


@dataclass
class Brief:
    """Pregunta, propósito, objetivos, restricciones y criterio de cierre."""

    question: str
    purpose: str | None = None
    targets: list[str] = field(default_factory=list)
    constraints: list[str] = field(default_factory=list)
    done_when: str | None = None


@dataclass
class PlanStep:
    """Paso del plan con estado y razón."""

    title: str
    status: StepStatus = StepStatus.TODO
    why: str | None = None


@dataclass
class Hypothesis:
    """Afirmación en prueba con predicción y evidencia a favor/en contra."""

    id: str
    claim: str
    status: HypothesisStatus = HypothesisStatus.TESTING
    prediction: str | None = None
    supporting: list[str] = field(default_factory=list)
    contradicting: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


@dataclass
class Finding:
    """Respuesta asentada; exige evidencia existente."""

    id: str
    statement: str
    evidence_ids: list[str]
    confidence: str = "observed"


@dataclass
class Unknown:
    """Pregunta abierta y qué la resolvería ("la ausencia no es prueba")."""

    id: str
    question: str
    domain: str
    severity: Severity = Severity.MEDIUM
    status: UnknownStatus = UnknownStatus.OPEN
    probes: list[str] = field(default_factory=list)
    evidence_for: list[str] = field(default_factory=list)
    evidence_against: list[str] = field(default_factory=list)
    resolution: str | None = None

    @classmethod
    def new(
        cls, question: str, domain: str, severity: Severity = Severity.MEDIUM
    ) -> Unknown:
        """Crea un unknown con id determinista a partir de pregunta y dominio."""
        seed = canonical_json({"question": question, "domain": domain})
        return cls(
            id=f"unk_{sha256_hex(seed.encode('utf-8'))[:16]}",
            question=question,
            domain=domain,
            severity=severity,
        )


def _now_utc() -> str:
    """Marca temporal ISO-8601 UTC (segundos)."""
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _check_ids(ledger: EvidenceLedger, ids: list[str]) -> None:
    """Verifica que todos los ids citados existen en el ledger."""
    missing = [item for item in ids if ledger.get(item) is None]
    if missing:
        raise UnknownEvidence(
            f"WHAT: evidencia desconocida {missing} "
            f"WHY: solo se citan ids devueltos por una observación "
            f"WHERE: investigation._check_ids"
        )


@dataclass
class Investigation:
    """Estado estructurado y revisionado de una investigación."""

    revision: int = 0
    updated: str | None = None
    brief: Brief | None = None
    plan: list[PlanStep] = field(default_factory=list)
    hypotheses: list[Hypothesis] = field(default_factory=list)
    findings: list[Finding] = field(default_factory=list)
    unknowns: list[Unknown] = field(default_factory=list)
    handoff: str | None = None

    def check_revision(self, expected: int | None) -> None:
        """Falla si ``expected`` no es la revisión actual."""
        if expected is not None and expected != self.revision:
            raise StaleRevision(
                f"WHAT: la investigación está en revisión {self.revision}, no {expected} "
                f"WHY: otra actualización ocurrió entre lectura y escritura "
                f"WHERE: Investigation.check_revision (relee y reintenta)"
            )

    def set_brief(self, brief: Brief, based_on_revision: int | None = None) -> None:
        """Reemplaza el brief de la investigación."""
        self.check_revision(based_on_revision)
        if not brief.question.strip():
            raise InvestigationError("WHAT: brief sin pregunta WHY: sin pregunta no hay investigación")
        self.brief = brief

    def set_plan(self, steps: list[PlanStep], based_on_revision: int | None = None) -> None:
        """Reemplaza el plan numerado."""
        self.check_revision(based_on_revision)
        self.plan = list(steps)

    def add_hypothesis(
        self,
        claim: str,
        ledger: EvidenceLedger,
        prediction: str | None = None,
        supporting: list[str] | None = None,
        contradicting: list[str] | None = None,
        based_on_revision: int | None = None,
    ) -> str:
        """Registra una hipótesis (valida la evidencia citada)."""
        self.check_revision(based_on_revision)
        support = list(supporting or [])
        against = list(contradicting or [])
        _check_ids(ledger, support + against)
        hypothesis_id = f"hyp_{sha256_hex(canonical_json({'claim': claim}).encode())[:16]}"
        self.hypotheses.append(
            Hypothesis(
                id=hypothesis_id,
                claim=claim,
                prediction=prediction,
                supporting=support,
                contradicting=against,
            )
        )
        return hypothesis_id

    def update_hypothesis(
        self,
        hypothesis_id: str,
        status: HypothesisStatus,
        based_on_revision: int | None = None,
        notes: list[str] | None = None,
    ) -> None:
        """Cambia el estado de una hipótesis y añade notas."""
        self.check_revision(based_on_revision)
        for hypothesis in self.hypotheses:
            if hypothesis.id == hypothesis_id:
                hypothesis.status = status
                hypothesis.notes.extend(notes or [])
                return
        raise InvestigationError(f"WHAT: hipótesis {hypothesis_id!r} inexistente")

    def add_finding(
        self,
        statement: str,
        evidence_ids: list[str],
        ledger: EvidenceLedger,
        confidence: str = "observed",
        based_on_revision: int | None = None,
    ) -> str:
        """Registra un hallazgo; exige al menos una evidencia existente."""
        self.check_revision(based_on_revision)
        if not statement.strip() or not evidence_ids:
            raise InvestigationError(
                "WHAT: hallazgo sin statement o sin evidencia "
                "WHY: un hallazgo sin prueba no es un hallazgo"
            )
        _check_ids(ledger, evidence_ids)
        finding_id = f"fnd_{sha256_hex(canonical_json({'statement': statement}).encode())[:16]}"
        self.findings.append(
            Finding(
                id=finding_id,
                statement=statement,
                evidence_ids=list(evidence_ids),
                confidence=confidence,
            )
        )
        return finding_id

    def add_unknown(
        self, unknown: Unknown, based_on_revision: int | None = None
    ) -> str:
        """Añade una pregunta abierta."""
        self.check_revision(based_on_revision)
        self.unknowns.append(unknown)
        return unknown.id

    def resolve_unknown(
        self,
        unknown_id: str,
        resolution: str,
        evidence_for: list[str],
        ledger: EvidenceLedger,
        based_on_revision: int | None = None,
    ) -> None:
        """Resuelve un unknown con resolución y evidencia a favor."""
        self.check_revision(based_on_revision)
        if not resolution.strip() or not evidence_for:
            raise InvestigationError(
                "WHAT: unknown resuelto sin resolución o sin evidencia "
                "WHY: la ausencia de evidencia no es prueba"
            )
        _check_ids(ledger, evidence_for)
        for unknown in self.unknowns:
            if unknown.id == unknown_id:
                unknown.status = UnknownStatus.RESOLVED
                unknown.resolution = resolution
                unknown.evidence_for = list(evidence_for)
                return
        raise InvestigationError(f"WHAT: unknown {unknown_id!r} inexistente")

    def set_handoff(self, note: str, based_on_revision: int | None = None) -> None:
        """Reescribe la nota de handoff."""
        self.check_revision(based_on_revision)
        self.handoff = note

    def save(self, project_dir: Path) -> None:
        """Persiste ``state.json`` y los Markdown de forma atómica.

        Args:
            project_dir: Raíz del proyecto; se crea ``investigation/`` dentro.
        """
        directory = project_dir / "investigation"
        directory.mkdir(parents=True, exist_ok=True)
        self.revision += 1
        self.updated = _now_utc()
        payload = json.dumps(self.to_dict(), ensure_ascii=False, indent=2, sort_keys=True)
        _atomic_write(directory / "state.json", payload + "\n")
        for name, body in self.render().items():
            _atomic_write(directory / name, body)

    @classmethod
    def load(cls, project_dir: Path) -> Investigation:
        """Carga ``state.json`` (investigación vacía si no existe)."""
        path = project_dir / "investigation" / "state.json"
        if not path.is_file():
            return cls()
        data = json.loads(path.read_text(encoding="utf-8"))
        return cls.from_dict(data)

    def to_dict(self) -> dict[str, Any]:
        """Serializa el estado completo."""
        return {
            "revision": self.revision,
            "updated": self.updated,
            "brief": _brief_dict(self.brief),
            "plan": [_plan_dict(step) for step in self.plan],
            "hypotheses": [_hypothesis_dict(item) for item in self.hypotheses],
            "findings": [_finding_dict(item) for item in self.findings],
            "unknowns": [_unknown_dict(item) for item in self.unknowns],
            "handoff": self.handoff,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Investigation:
        """Reconstruye el estado desde JSON."""
        brief_data = data.get("brief")
        return cls(
            revision=int(data.get("revision", 0)),
            updated=data.get("updated"),
            brief=None if brief_data is None else _brief_from(brief_data),
            plan=[_plan_from(item) for item in data.get("plan", [])],
            hypotheses=[_hypothesis_from(item) for item in data.get("hypotheses", [])],
            findings=[_finding_from(item) for item in data.get("findings", [])],
            unknowns=[_unknown_from(item) for item in data.get("unknowns", [])],
            handoff=data.get("handoff"),
        )

    def render(self) -> dict[str, str]:
        """Renderiza los Markdown legibles desde el estado estructurado."""
        return {
            "brief.md": render_brief(self.brief),
            "plan.md": render_plan(self.plan),
            "hypotheses.md": render_hypotheses(self.hypotheses),
            "findings.md": render_findings(self.findings),
            "handoff.md": render_handoff(self.handoff),
        }


def _atomic_write(path: Path, text: str) -> None:
    """Escribe ``text`` en ``path`` con reemplazo atómico."""
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(text, encoding="utf-8")
    os.replace(temporary, path)


def _brief_dict(brief: Brief | None) -> dict[str, Any] | None:
    """Serializa ``Brief`` o ``None``."""
    if brief is None:
        return None
    return {
        "question": brief.question,
        "purpose": brief.purpose,
        "targets": list(brief.targets),
        "constraints": list(brief.constraints),
        "done_when": brief.done_when,
    }


def _brief_from(data: dict[str, Any]) -> Brief:
    """Reconstruye ``Brief`` desde JSON."""
    return Brief(
        question=str(data["question"]),
        purpose=data.get("purpose"),
        targets=[str(item) for item in data.get("targets", [])],
        constraints=[str(item) for item in data.get("constraints", [])],
        done_when=data.get("done_when"),
    )


def _plan_dict(step: PlanStep) -> dict[str, Any]:
    """Serializa un paso del plan."""
    return {"title": step.title, "status": step.status.value, "why": step.why}


def _plan_from(data: dict[str, Any]) -> PlanStep:
    """Reconstruye un paso del plan."""
    return PlanStep(str(data["title"]), StepStatus(data.get("status", "todo")), data.get("why"))


def _hypothesis_dict(item: Hypothesis) -> dict[str, Any]:
    """Serializa una hipótesis."""
    return {
        "id": item.id,
        "claim": item.claim,
        "status": item.status.value,
        "prediction": item.prediction,
        "supporting": list(item.supporting),
        "contradicting": list(item.contradicting),
        "notes": list(item.notes),
    }


def _hypothesis_from(data: dict[str, Any]) -> Hypothesis:
    """Reconstruye una hipótesis."""
    return Hypothesis(
        id=str(data["id"]),
        claim=str(data["claim"]),
        status=HypothesisStatus(data.get("status", "testing")),
        prediction=data.get("prediction"),
        supporting=[str(item) for item in data.get("supporting", [])],
        contradicting=[str(item) for item in data.get("contradicting", [])],
        notes=[str(item) for item in data.get("notes", [])],
    )


def _finding_dict(item: Finding) -> dict[str, Any]:
    """Serializa un hallazgo."""
    return {
        "id": item.id,
        "statement": item.statement,
        "evidence_ids": list(item.evidence_ids),
        "confidence": item.confidence,
    }


def _finding_from(data: dict[str, Any]) -> Finding:
    """Reconstruye un hallazgo."""
    return Finding(
        id=str(data["id"]),
        statement=str(data["statement"]),
        evidence_ids=[str(item) for item in data.get("evidence_ids", [])],
        confidence=str(data.get("confidence", "observed")),
    )


def _unknown_dict(item: Unknown) -> dict[str, Any]:
    """Serializa un unknown."""
    return {
        "id": item.id,
        "question": item.question,
        "domain": item.domain,
        "severity": item.severity.value,
        "status": item.status.value,
        "probes": list(item.probes),
        "evidence_for": list(item.evidence_for),
        "evidence_against": list(item.evidence_against),
        "resolution": item.resolution,
    }


def _unknown_from(data: dict[str, Any]) -> Unknown:
    """Reconstruye un unknown."""
    return Unknown(
        id=str(data["id"]),
        question=str(data["question"]),
        domain=str(data["domain"]),
        severity=Severity(data.get("severity", "medium")),
        status=UnknownStatus(data.get("status", "open")),
        probes=[str(item) for item in data.get("probes", [])],
        evidence_for=[str(item) for item in data.get("evidence_for", [])],
        evidence_against=[str(item) for item in data.get("evidence_against", [])],
        resolution=data.get("resolution"),
    )
