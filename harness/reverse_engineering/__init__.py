"""Operaciones de ingeniería inversa con evidencia verificable (ADR-0048/0103).

Paquete inspirado en `craft-anything` (storytold/craft-anything): protocolo de
investigación durable (brief, plan, hipótesis, hallazgos, unknowns, handoff),
ledger de evidencia con id = SHA-256 del JSON canónico, triaje de artefactos por
bytes, política clean-room vs deep y puente opcional a sus 301 herramientas.
"""

from __future__ import annotations

from .bridge import BridgeCallError, BridgeResult, BridgeUnavailable, CraftAnythingBridge
from .canonical import canonical_json, sha256_hex, stable_id
from .evidence import (
    Authority,
    Confidence,
    Coverage,
    CoverageStatus,
    Environment,
    Evidence,
    EvidenceLedger,
    EvidenceTampered,
    Limitation,
    Location,
    Subject,
)
from .investigation import (
    Brief,
    Finding,
    Hypothesis,
    HypothesisStatus,
    Investigation,
    InvestigationError,
    PlanStep,
    Severity,
    StaleRevision,
    StepStatus,
    Unknown,
    UnknownEvidence,
    UnknownStatus,
)
from .policy import Mode, Policy, PolicyViolation
from .triage import ArtifactInfo, fingerprint, inventory_archive, triage_evidence

__all__ = [
    "ArtifactInfo",
    "Authority",
    "BridgeCallError",
    "BridgeResult",
    "BridgeUnavailable",
    "Brief",
    "Confidence",
    "Coverage",
    "CoverageStatus",
    "CraftAnythingBridge",
    "Environment",
    "Evidence",
    "EvidenceLedger",
    "EvidenceTampered",
    "Finding",
    "Hypothesis",
    "HypothesisStatus",
    "Investigation",
    "InvestigationError",
    "Limitation",
    "Location",
    "Mode",
    "PlanStep",
    "Policy",
    "PolicyViolation",
    "Severity",
    "StaleRevision",
    "StepStatus",
    "Subject",
    "Unknown",
    "UnknownEvidence",
    "UnknownStatus",
    "canonical_json",
    "fingerprint",
    "inventory_archive",
    "sha256_hex",
    "stable_id",
    "triage_evidence",
]
