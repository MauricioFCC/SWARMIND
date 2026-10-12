"""Failure distillation — fallos resueltos → skills reutilizables de avoidance.

Cierre del loop Socratic-SWE/SESA: tras registrar un fallo en el
``FailureRegistry``, los fallos RESUELTOS e informativos se destilan en un
``ProceduralSkill`` de tipo avoidance ("que paso, por que, como se resolvio")
que el agente puede reutilizar para no repetir el error.

Diseno:
    - ``FailureDistiller`` recibe registry y memoria por inyeccion (DI).
    - Filtra solo fallos destilables: severity >= ``min_severity`` y
      ``resolution`` no vacia y distinta de ``"pending"``.
    - DEDUP idempotente por nombre determinista del skill.
    - Best-effort: si la memoria falla al persistir, loguea y continua.
"""

from __future__ import annotations

import hashlib
import logging
import re

from harness.evolve_loop.procedural_memory import ProceduralMemory, ProceduralSkill
from harness.failure_registry import registry as _default_registry
from harness.failure_registry.registry import FailureRecord, Severity

logger = logging.getLogger(__name__)

#: Rango numerico para comparar severidades: ``Severity`` es ``str, Enum``,
#: por lo que comparar con ``>=`` usa orden lexicografico (``"critical" < "high"``)
#: y seria incorrecto. Este ranking restaura LOW < MEDIUM < HIGH < CRITICAL.
_SEVERITY_RANK: dict[Severity, int] = {
    Severity.LOW: 0,
    Severity.MEDIUM: 1,
    Severity.HIGH: 2,
    Severity.CRITICAL: 3,
}

#: Agent por defecto para skills derivados de fallos.
_AGENT = "evolve"

#: Longitud maxima del root_cause en la descripcion del skill.
_DESCRIPTION_CAUSE_LIMIT = 120


class FailureDistiller:
    """Destila fallos resueltos del registry en skills reutilizables.

    Attributes:
        _registry: Registry de fallos (inyectado por DI).
        _memory: Memoria procedural donde persistir skills (DI).
        _min_severity: Severidad minima para destilar un fallo.
    """

    def __init__(
        self,
        *,
        registry=None,
        memory: ProceduralMemory | None = None,
        min_severity: Severity = Severity.HIGH,
    ) -> None:
        """Inicializa el distiller.

        Args:
            registry: Registry de fallos. Default: singleton compartido.
            memory: Memoria procedural destino. Default: ``ProceduralMemory()``.
            min_severity: Severidad minima para considerar un fallo destilable.
        """
        self._registry = registry if registry is not None else _default_registry
        self._memory = memory if memory is not None else ProceduralMemory()
        self._min_severity = min_severity

    def distill(self, *, max_skills: int = 10) -> list[ProceduralSkill]:
        """Genera skills de avoidance a partir de fallos resueltos.

        Itera los fallos del registry, filtra los destilables, deduplica
        contra la memoria existente y persiste hasta ``max_skills`` nuevos.

        Args:
            max_skills: Maximo de skills a generar por corrida.

        Returns:
            Lista de los ``ProceduralSkill`` NUEVOS creados (no los ya existentes).
        """
        created: list[ProceduralSkill] = []
        for record in self._select(max_skills=max_skills):
            skill = self._persist(record, self._skill_name(record))
            if skill is not None:
                created.append(skill)
        return created

    def preview(self, *, max_skills: int = 10) -> list[FailureRecord]:
        """Proyecta que fallos se destilarian SIN persistir nada en memoria.

        WHAT: comparte la seleccion (filtro + dedup) con ``distill`` pero no
        escribe; util para el modo ``--dry-run`` del CLI post-merge.
        WHY: exponer un preview real evita tocar ``.opencode/skills/auto/`` al
        simular, manteniendo la deduplicacion idempotente intacta.
        WHERE: ``FailureDistiller.preview`` (invocado por
        ``scripts/distill_failures.py``).

        Args:
            max_skills: Maximo de fallos destilables a proyectar.

        Returns:
            Lista de ``FailureRecord`` que originarian skills nuevos.
        """
        return self._select(max_skills=max_skills)

    def _select(self, *, max_skills: int) -> list[FailureRecord]:
        """Selecciona los fallos destilables (filtro + dedup) sin persistir.

        Emula el estado de la memoria con un set local ``existing`` para
        deduplicar tanto contra los skills previos como DENTRO de la corrida
        (dos fallos que colisionan en nombre generan un solo skill).

        Args:
            max_skills: Maximo de fallos a seleccionar.

        Returns:
            Lista de ``FailureRecord`` destilables, en orden de insercion.
        """
        existing: set[str] = {s.name for s in self._memory.list_skills()}
        selected: list[FailureRecord] = []

        for record in self._registry.get_all():
            if len(selected) >= max_skills:
                break
            if not self._is_distillable(record):
                continue

            name = self._skill_name(record)
            if name in existing:
                continue  # DEDUP idempotente: ya destilado.

            existing.add(name)
            selected.append(record)

        return selected

    def _is_distillable(self, record: FailureRecord) -> bool:
        """Determina si un fallo tiene una leccion cerrada y es destilable.

        Args:
            record: Fallo a evaluar.

        Returns:
            True si severity >= min_severity y la resolucion esta cerrada.
        """
        if _SEVERITY_RANK[record.severity] < _SEVERITY_RANK[self._min_severity]:
            return False
        resolution = record.resolution.strip()
        return bool(resolution) and resolution != "pending"

    def _skill_name(self, record: FailureRecord) -> str:
        """Deriva un nombre determinista y estable para el skill.

        Mismo fallo → mismo nombre, requisito de la deduplicacion idempotente.

        Args:
            record: Fallo de origen.

        Returns:
            Slug determinista con prefijo ``avoid-``.
        """
        base = record.tags[0] if record.tags else record.failure_type.value
        slug = re.sub(r"[^a-z0-9_-]", "", base.lower().replace(" ", "-"))
        digest = hashlib.sha1(record.id.encode("utf-8")).hexdigest()[:8]
        return f"avoid-{slug}-{digest}"

    def _persist(self, record: FailureRecord, name: str) -> ProceduralSkill | None:
        """Persiste el skill en la memoria (best-effort, sin romper el loop).

        Args:
            record: Fallo de origen.
            name: Nombre determinista del skill.

        Returns:
            El ``ProceduralSkill`` creado, o None si la escritura fallo.
        """
        cause = record.root_cause.strip() or "(causa no especificada)"
        steps = [
            f"NO hacer: {record.error_msg}",
            f"Causa: {cause}",
            f"Resolucion aplicada: {record.resolution}",
        ]
        try:
            return self._memory.register_skill(
                name=name,
                description=f"Avoidance: {record.task} — {self._short(cause)}",
                steps=steps,
                agent=_AGENT,
                tags=list(record.tags),
                source_task_id=record.id,
            )
        except Exception as exc:  # noqa: BLE001 — fallo de IO no debe romper el loop
            logger.warning(
                "No se pudo destilar fallo %s a skill: %s | "
                "WHY: error al persistir en ProceduralMemory | "
                "WHERE: FailureDistiller._persist",
                record.id,
                exc,
            )
            return None

    @staticmethod
    def _short(text: str, limit: int = _DESCRIPTION_CAUSE_LIMIT) -> str:
        """Trunca un texto para descripciones concisas.

        Args:
            text: Texto a truncar.
            limit: Longitud maxima permitida.

        Returns:
            Texto truncado con elipsis si excede el limite.
        """
        text = " ".join(text.split())
        return text if len(text) <= limit else f"{text[:limit - 1]}…"
