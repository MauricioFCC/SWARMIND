"""Evidencia verificable: el tipo de resultado que produce toda observación.

Réplica del modelo de `craft-anything` (`crates/evidence`): un registro dice qué
se miró (`subject`), qué operación se ejecutó, qué devolvió, con qué confianza y
autoridad, qué no se pudo comprobar (`limitations`, `coverage`) y dónde apunta
(`locations`). Su id es el SHA-256 del JSON canónico, así que:
- la misma observación produce siempre el mismo id (deduplicación idempotente);
- cualquier edición de un registro almacenado es detectable al importar.
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

from .canonical import canonical_json, sha256_hex


class Confidence(str, Enum):
    """Grado de certeza de una evidencia."""

    OBSERVED = "observed"
    DERIVED = "derived"
    INFERRED = "inferred"


class Authority(str, Enum):
    """Origen de la autoridad de una evidencia."""

    ORIGINAL_FILES = "original-files"
    OUR_RUN = "our-run"
    EARLIER_RECORD = "earlier-record"
    OUTSIDE_SERVICE = "outside-service"
    REASONING = "reasoning"


class CoverageStatus(str, Enum):
    """Cobertura del espacio examinado."""

    COMPLETE = "complete"
    PARTIAL = "partial"
    UNKNOWN = "unknown"


class EvidenceTampered(ValueError):
    """El id almacenado no coincide con el contenido (posible manipulación)."""


@dataclass
class Limitation:
    """Algo que el análisis no pudo establecer o dejó fuera a propósito."""

    code: str
    message: str


@dataclass
class Coverage:
    """Cuánto del espacio se examinó."""

    status: CoverageStatus = CoverageStatus.UNKNOWN
    examined: int | None = None
    total: int | None = None
    next_offset: int | None = None


@dataclass
class Location:
    """Un lugar del artefacto al que apunta la evidencia."""

    kind: str
    value: str
    label: str | None = None


@dataclass
class Subject:
    """Sobre qué es la evidencia."""

    kind: str
    sha256: str | None = None
    name: str | None = None


@dataclass
class Environment:
    """Condiciones en las que se hizo la observación."""

    clean_room: bool
    engine: str
    host: str
    engine_version: str | None = None
    language_id: str | None = None


@dataclass
class Evidence:
    """Una observación con id derivado del contenido."""

    subject: Subject
    operation: str
    environment: Environment
    params: Any = None
    result: Any = None
    summary: str = ""
    confidence: Confidence = Confidence.OBSERVED
    authority: Authority = Authority.ORIGINAL_FILES
    limitations: list[Limitation] = field(default_factory=list)
    coverage: Coverage = field(default_factory=Coverage)
    locations: list[Location] = field(default_factory=list)
    links: list[str] = field(default_factory=list)
    carries_target_content: bool = False
    id: str = ""

    def compute_id(self) -> str:
        """Calcula ``ev_<sha256>`` excluyendo campos de presentación."""
        payload = self.to_dict()
        payload.pop("id", None)
        payload.pop("summary", None)
        payload.pop("carries_target_content", None)
        subject = payload.get("subject")
        if isinstance(subject, dict):
            subject.pop("name", None)
        digest = sha256_hex(canonical_json(payload).encode("utf-8"))
        return f"ev_{digest}"

    def verify(self) -> bool:
        """True si el ``id`` guardado coincide con el contenido actual."""
        return bool(self.id) and self.compute_id() == self.id

    def seal(self) -> Evidence:
        """Asigna el id calculado (idempotente)."""
        self.id = self.compute_id()
        return self

    def to_dict(self) -> dict[str, Any]:
        """Serializa la evidencia (omite campos opcionales vacíos como Rust)."""
        data: dict[str, Any] = {
            "subject": _subject_dict(self.subject),
            "operation": self.operation,
            "params": self.params,
            "result": self.result,
            "summary": self.summary,
            "confidence": self.confidence.value,
            "authority": self.authority.value,
            "environment": _environment_dict(self.environment),
            "limitations": [{"code": item.code, "message": item.message} for item in self.limitations],
            "coverage": _coverage_dict(self.coverage),
            "locations": [_location_dict(item) for item in self.locations],
            "links": list(self.links),
        }
        if self.carries_target_content:
            data["carries_target_content"] = True
        if self.id:
            data["id"] = self.id
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Evidence:
        """Reconstruye una evidencia desde su representación serializada."""
        return cls(
            id=str(data.get("id", "")),
            subject=_subject_from(data["subject"]),
            operation=str(data["operation"]),
            params=data.get("params"),
            result=data.get("result"),
            summary=str(data.get("summary", "")),
            confidence=Confidence(data.get("confidence", "observed")),
            authority=Authority(data.get("authority", "original-files")),
            environment=_environment_from(data["environment"]),
            limitations=[
                Limitation(str(item["code"]), str(item["message"]))
                for item in data.get("limitations", [])
            ],
            coverage=_coverage_from(data.get("coverage", {})),
            locations=[
                Location(str(item["kind"]), str(item["value"]), item.get("label"))
                for item in data.get("locations", [])
            ],
            links=[str(link) for link in data.get("links", [])],
            carries_target_content=bool(data.get("carries_target_content")),
        )


def _subject_from(data: dict[str, Any]) -> Subject:
    """Reconstruye ``Subject`` desde JSON."""
    return Subject(
        kind=str(data["kind"]),
        sha256=data.get("sha256"),
        name=data.get("name"),
    )


def _environment_from(data: dict[str, Any]) -> Environment:
    """Reconstruye ``Environment`` desde JSON."""
    return Environment(
        clean_room=bool(data["clean_room"]),
        engine=str(data["engine"]),
        host=str(data["host"]),
        engine_version=data.get("engine_version"),
        language_id=data.get("language_id"),
    )


def _coverage_from(data: dict[str, Any]) -> Coverage:
    """Reconstruye ``Coverage`` desde JSON."""
    return Coverage(
        status=CoverageStatus(data.get("status", "unknown")),
        examined=data.get("examined"),
        total=data.get("total"),
        next_offset=data.get("next_offset"),
    )


def _subject_dict(subject: Subject) -> dict[str, Any]:
    """Serializa ``Subject`` omitiendo ``name`` si no existe."""
    data: dict[str, Any] = {"kind": subject.kind}
    if subject.sha256:
        data["sha256"] = subject.sha256
    if subject.name:
        data["name"] = subject.name
    return data


def _environment_dict(environment: Environment) -> dict[str, Any]:
    """Serializa ``Environment`` omitiendo opcionales vacíos."""
    data: dict[str, Any] = {
        "clean_room": environment.clean_room,
        "engine": environment.engine,
        "host": environment.host,
    }
    if environment.engine_version:
        data["engine_version"] = environment.engine_version
    if environment.language_id:
        data["language_id"] = environment.language_id
    return data


def _coverage_dict(coverage: Coverage) -> dict[str, Any]:
    """Serializa ``Coverage`` omitiendo contadores ausentes."""
    data: dict[str, Any] = {"status": coverage.status.value}
    for key in ("examined", "total", "next_offset"):
        value = getattr(coverage, key)
        if value is not None:
            data[key] = value
    return data


def _location_dict(location: Location) -> dict[str, Any]:
    """Serializa ``Location`` omitiendo ``label`` si no existe."""
    data: dict[str, Any] = {"kind": location.kind, "value": location.value}
    if location.label:
        data["label"] = location.label
    return data


@dataclass
class EvidenceLedger:
    """Registro append-only de evidencias, indexado por id."""

    records: dict[str, Evidence] = field(default_factory=dict)

    def add(self, evidence: Evidence) -> str:
        """Añade (o reutiliza) una evidencia y devuelve su id.

        Args:
            evidence: Registro a añadir; si no tiene id se sella.

        Returns:
            Id ``ev_...`` de la evidencia.

        Raises:
            EvidenceTampered: Si el id no corresponde al contenido.
        """
        if not evidence.id:
            evidence.seal()
        elif not evidence.verify():
            raise EvidenceTampered(
                f"WHAT: id {evidence.id!r} no coincide con el contenido "
                f"WHY: evidencia manipulada o serializada de forma distinta "
                f"WHERE: EvidenceLedger.add({evidence.operation!r})"
            )
        self.records.setdefault(evidence.id, evidence)
        return evidence.id

    def get(self, evidence_id: str) -> Evidence | None:
        """Devuelve la evidencia por id o ``None``."""
        return self.records.get(evidence_id)

    def require(self, evidence_id: str) -> Evidence:
        """Devuelve la evidencia o lanza ``KeyError`` con remediación."""
        record = self.records.get(evidence_id)
        if record is None:
            raise KeyError(
                f"WHAT: evidencia desconocida {evidence_id!r} "
                f"WHY: solo se pueden citar ids devueltos por una observación "
                f"WHERE: EvidenceLedger.require"
            )
        return record

    def ids(self) -> list[str]:
        """Ids registrados (orden de inserción)."""
        return list(self.records)

    def extend(self, records: Iterable[Evidence]) -> None:
        """Añade varias evidencias (falla si alguna está manipulada)."""
        for record in records:
            self.add(record)

    def to_jsonl(self) -> str:
        """Exporta el ledger como JSON Lines (un registro por línea)."""
        return "\n".join(
            json.dumps(record.to_dict(), ensure_ascii=False, sort_keys=True)
            for record in self.records.values()
        ) + ("\n" if self.records else "")

    def save(self, path: Path) -> None:
        """Escribe el ledger en ``path`` de forma atómica."""
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(path.name + ".tmp")
        temporary.write_text(self.to_jsonl(), encoding="utf-8")
        temporary.replace(path)

    @classmethod
    def load(cls, path: Path) -> EvidenceLedger:
        """Carga y verifica un ledger JSONL (detecta manipulación)."""
        ledger = cls()
        if not path.is_file():
            return ledger
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if not line.strip():
                continue
            record = Evidence.from_dict(json.loads(line))
            if not record.verify():
                raise EvidenceTampered(
                    f"WHAT: evidencia manipulada en {path} línea {number} "
                    f"WHY: id {record.id!r} != sha256 del contenido "
                    f"WHERE: EvidenceLedger.load"
                )
            ledger.add(record)
        return ledger
