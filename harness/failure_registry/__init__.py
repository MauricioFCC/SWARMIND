"""Failure Registry — registro estructurado de fallos para aprendizaje autónomo.

Patrón: Socratic-SWE (Qu 2026) — failure traces → skills → task generation.
Cada fallo se registra con: qué falló, por qué, cómo se resolvió, qué skill
se derivó. El evolve loop consulta este registro antes de proponer mejoras.

Flujo (Proof-or-Stop, Huang 2026):
  1. Agente produce output → claim
  2. Verificación falla → se registra el failure con evidencia
  3. evolve loop lee failures → distilla en skills → genera tareas dirigidas
  4. Skills se deduplican por similaridad semántica

Uso:
    from harness.failure_registry import FailureRegistry

    registry = FailureRegistry()
    registry.record(
        task="deploy_all.py sync",
        failure_type="runtime",
        error_msg="FileNotFoundError: scripts/deploy_local.json",
        root_cause="Config local no existe en nueva máquina",
        resolution="Fallback a Path.home() cuando JSON no existe",
        skill_derived="config-fallback-pattern",
        severity="medium",
    )
    recent = registry.get_recent(n=10)
    by_type = registry.get_by_type("runtime")
"""
from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from enum import Enum
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class Severity(str, Enum):
    """Nivel de severidad del fallo (MAG: enum sobre int/str magicos)."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class FailureType(str, Enum):
    """Categoría del fallo para agrupación y métricas."""
    RUNTIME = "runtime"
    TEST = "test"
    LINT = "lint"
    SECURITY = "security"
    PERFORMANCE = "performance"
    ARCHITECTURE = "architecture"
    DEPLOY = "deploy"
    CONFIG = "config"


@dataclass(frozen=True)
class FailureRecord:
    """Registro inmutable de un fallo (IMM: frozen dataclass).

    Attributes:
        id: Identificador único del fallo (timestamp + hash corto).
        timestamp: ISO 8601 del momento del fallo.
        task: Descripción de la tarea que falló.
        failure_type: Categoría del fallo.
        error_msg: Mensaje de error original.
        root_cause: Causa raíz identificada (WHY del patrón ERR).
        resolution: Cómo se resolvió (o "pending" si aún no).
        skill_derived: Nombre del skill derivado del fallo (vacío si ninguno).
        severity: Nivel de severidad.
        file_path: Archivo donde ocurrió el fallo (opcional).
        function_name: Función donde ocurrió (opcional).
        tags: Tags adicionales para búsqueda.
    """
    id: str
    timestamp: str
    task: str
    failure_type: FailureType
    error_msg: str
    root_cause: str
    resolution: str
    skill_derived: str
    severity: Severity
    file_path: str = ""
    function_name: str = ""
    tags: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        """Serializa a dict para persistencia JSON."""
        d = asdict(self)
        d["failure_type"] = self.failure_type.value
        d["severity"] = self.severity.value
        d["tags"] = list(self.tags)
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> FailureRecord:
        """Deserializa desde dict (MAN: constructor limpio)."""
        data["failure_type"] = FailureType(data["failure_type"])
        data["severity"] = Severity(data["severity"])
        data["tags"] = tuple(data.get("tags", []))
        return cls(**data)


class FailureRegistry:
    """Registry persistente de fallos para aprendizaje autónomo.

    Almacena en ``harness/db/failures.jsonl`` (formato JSONL, append-only).
    Cada línea es un FailureRecord serializado. Consultas se hacen en memoria
    cargando el archivo completo (aceptable para <10K registros).

    Attributes:
        _path: Ruta al archivo JSONL de fallos.
        _records: Caché en memoria de registros cargados.
    """

    def __init__(self, path: Path | None = None) -> None:
        """Inicializa el registry.

        Args:
            path: Ruta al archivo JSONL. Default: harness/db/failures.jsonl.
        """
        if path is None:
            path = Path(__file__).resolve().parent.parent / "db" / "failures.jsonl"
        self._path = path
        self._records: list[FailureRecord] = []
        self._load()

    def _load(self) -> None:
        """Carga registros existentes desde disco (idempotente)."""
        if not self._path.is_file():
            return
        try:
            for line in self._path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line:
                    self._records.append(FailureRecord.from_dict(json.loads(line)))
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning(
                "No se pudo cargar failures.jsonl: %s | "
                "WHY: archivo corrupto o inaccesible | "
                "WHERE: FailureRegistry._load",
                exc,
            )

    def record(
        self,
        task: str,
        failure_type: FailureType | str,
        error_msg: str,
        root_cause: str,
        resolution: str,
        skill_derived: str = "",
        severity: Severity | str = Severity.MEDIUM,
        file_path: str = "",
        function_name: str = "",
        tags: tuple[str, ...] | list[str] = (),
    ) -> FailureRecord:
        """Registra un nuevo fallo (append-only, inmutable).

        Args:
            task: Descripción de la tarea que falló.
            failure_type: Categoría del fallo.
            error_msg: Mensaje de error original.
            root_cause: Causa raíz identificada.
            resolution: Cómo se resolvió.
            skill_derived: Nombre del skill derivado.
            severity: Nivel de severidad.
            file_path: Archivo donde ocurrió.
            function_name: Función donde ocurrió.
            tags: Tags adicionales.

        Returns:
            El FailureRecord creado.
        """
        if isinstance(failure_type, str):
            failure_type = FailureType(failure_type)
        if isinstance(severity, str):
            severity = Severity(severity)
        tags_tuple = tuple(tags) if isinstance(tags, list) else tags

        record = FailureRecord(
            id=f"{datetime.now(UTC).strftime('%Y%m%dT%H%M%S')}-{abs(hash(error_msg)) % 10000:04d}",
            timestamp=datetime.now(UTC).isoformat(),
            task=task,
            failure_type=failure_type,
            error_msg=error_msg,
            root_cause=root_cause,
            resolution=resolution,
            skill_derived=skill_derived,
            severity=severity,
            file_path=file_path,
            function_name=function_name,
            tags=tags_tuple,
        )

        self._records.append(record)
        self._append_to_disk(record)
        logger.info(
            "Failure registrado: [%s] %s → %s",
            record.severity.value,
            record.failure_type.value,
            record.task,
        )
        return record

    def _append_to_disk(self, record: FailureRecord) -> None:
        """Append un registro al archivo JSONL (idempotente, thread-safe-ish)."""
        self._path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with self._path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(record.to_dict(), ensure_ascii=False) + "\n")
        except OSError as exc:
            logger.warning(
                "No se pudo persistir failure: %s | "
                "WHY: disco lleno o permisos | "
                "WHERE: FailureRegistry._append_to_disk",
                exc,
            )

    def get_recent(self, n: int = 10) -> list[FailureRecord]:
        """Retorna los N fallos más recientes.

        Args:
            n: Número de registros a retornar.

        Returns:
            Lista de FailureRecord ordenados por timestamp descendente.
        """
        return sorted(self._records, key=lambda r: r.timestamp, reverse=True)[:n]

    def get_by_type(self, failure_type: FailureType | str) -> list[FailureRecord]:
        """Retorna fallos de un tipo específico.

        Args:
            failure_type: Tipo de fallo a filtrar.

        Returns:
            Lista de FailureRecord del tipo indicado.
        """
        if isinstance(failure_type, str):
            failure_type = FailureType(failure_type)
        return [r for r in self._records if r.failure_type == failure_type]

    def get_by_severity(self, severity: Severity | str) -> list[FailureRecord]:
        """Retorna fallos de una severidad específica.

        Args:
            severity: Severidad a filtrar.

        Returns:
            Lista de FailureRecord de la severidad indicada.
        """
        if isinstance(severity, str):
            severity = Severity(severity)
        return [r for r in self._records if r.severity == severity]

    def get_unresolved(self) -> list[FailureRecord]:
        """Retorna fallos aún no resueltos (resolution == 'pending').

        Returns:
            Lista de FailureRecord sin resolver.
        """
        return [r for r in self._records if r.resolution == "pending"]

    def get_skills_derived(self) -> list[str]:
        """Retorna nombres de skills derivados de fallos (deduplicados).

        Returns:
            Lista ordenada de nombres de skills únicos.
        """
        skills = {r.skill_derived for r in self._records if r.skill_derived}
        return sorted(skills)

    def stats(self) -> dict[str, Any]:
        """Estadísticas del registry para dashboards y evolve loop.

        Returns:
            Dict con conteos por tipo, severidad, skills derivados, etc.
        """
        by_type: dict[str, int] = {}
        by_severity: dict[str, int] = {}
        for r in self._records:
            by_type[r.failure_type.value] = by_type.get(r.failure_type.value, 0) + 1
            by_severity[r.severity.value] = by_severity.get(r.severity.value, 0) + 1

        return {
            "total": len(self._records),
            "unresolved": len(self.get_unresolved()),
            "by_type": by_type,
            "by_severity": by_severity,
            "skills_derived": self.get_skills_derived(),
            "latest": self._records[-1].timestamp if self._records else None,
        }

    def __len__(self) -> int:
        """Número total de registros."""
        return len(self._records)

    def __repr__(self) -> str:
        """Representación concisa para debugging."""
        return f"FailureRegistry({len(self._records)} records, {self._path})"
