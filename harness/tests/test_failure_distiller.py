"""Tests TDD de FailureDistiller (failure distillation → skills de avoidance).

Contrato:
  (a) un fallo HIGH resuelto genera 1 skill con root_cause y resolution.
  (b) un fallo con resolution="pending" NO se destila (leccion no cerrada).
  (c) un fallo LOW/MEDIUM (bajo min_severity) NO se destila.
  (d) idempotencia: la 2da corrida sobre la misma memoria genera 0 nuevos.
  (e) max_skills limita cuantos skills se generan por corrida.
  (f) el nombre del skill es determinista (mismo fallo → mismo nombre).

Aislamiento: registry y memory se inyectan con tmp_path; NUNCA se toca el
registry real ni ``.opencode/skills/auto``.
"""

from __future__ import annotations

from pathlib import Path

from harness.evolve_loop.failure_distiller import FailureDistiller
from harness.evolve_loop.procedural_memory import ProceduralMemory
from harness.failure_registry.registry import (
    FailureRegistry,
    FailureType,
    Severity,
)


def _make_registry(tmp_path: Path) -> FailureRegistry:
    """Crea un FailureRegistry aislado en disco.

    Args:
        tmp_path: Directorio temporal de pytest.

    Returns:
        Registry apuntando a un JSONL aislado.
    """
    return FailureRegistry(path=tmp_path / "failures.jsonl")


def _make_memory(tmp_path: Path) -> ProceduralMemory:
    """Crea un ProceduralMemory aislado en disco.

    Args:
        tmp_path: Directorio temporal de pytest.

    Returns:
        Memoria escribiendo en un directorio de skills temporal.
    """
    return ProceduralMemory(skills_dir=str(tmp_path / "auto_skills"))


def _record_high(registry: FailureRegistry, **overrides) -> object:
    """Registra un fallo HIGH resuelto reutilizable por los tests.

    Args:
        registry: Registry donde persistir.
        **overrides: Campos a sobreescribir del fallo base.

    Returns:
        El FailureRecord creado.
    """
    base = {
        "task": "Deploy pipeline",
        "failure_type": FailureType.CONFIG,
        "error_msg": "env var DB_URL missing",
        "root_cause": "Variable de entorno no definida en CI",
        "resolution": "Declarar DB_URL en secrets del workflow",
        "severity": Severity.HIGH,
        "tags": ("ci", "config"),
    }
    base.update(overrides)
    return registry.record(**base)


class TestDistillGenerates:
    """Casos donde el fallo SI es destilable."""

    def test_high_resuelto_genera_un_skill(self, tmp_path: Path) -> None:
        """Falló HIGH resuelto → genera 1 skill con causa y resolucion."""
        registry = _make_registry(tmp_path)
        memory = _make_memory(tmp_path)
        _record_high(registry)

        distiller = FailureDistiller(registry=registry, memory=memory)
        created = distiller.distill()

        assert len(created) == 1
        skill = created[0]
        assert skill.steps[1] == "Causa: Variable de entorno no definida en CI"
        assert (
            skill.steps[2]
            == "Resolucion aplicada: Declarar DB_URL en secrets del workflow"
        )
        assert skill.agent == "evolve"
        assert skill.tags == ["ci", "config"]
        # Persistido en disco
        assert (tmp_path / "auto_skills" / f"{skill.name}.md").exists()

    def test_nombre_determinista(self, tmp_path: Path) -> None:
        """Mismo fallo → mismo nombre de skill (estable entre corridas)."""
        registry = _make_registry(tmp_path)
        memory = _make_memory(tmp_path)
        record = _record_high(registry)
        distiller = FailureDistiller(registry=registry, memory=memory)

        name_a = distiller._skill_name(record)
        name_b = distiller._skill_name(record)
        assert name_a == name_b
        assert name_a.startswith("avoid-")


class TestDistillFilters:
    """Casos donde el fallo NO debe destilarse."""

    def test_resolution_pending_no_genera(self, tmp_path: Path) -> None:
        """resolution="pending" → no hay leccion cerrada, no genera."""
        registry = _make_registry(tmp_path)
        memory = _make_memory(tmp_path)
        _record_high(registry, resolution="pending")

        created = FailureDistiller(registry=registry, memory=memory).distill()
        assert created == []

    def test_severidad_baja_no_genera(self, tmp_path: Path) -> None:
        """Severidad LOW/MEDIUM (< min_severity) → no genera."""
        registry = _make_registry(tmp_path)
        memory = _make_memory(tmp_path)
        _record_high(registry, severity=Severity.LOW, error_msg="e1")
        _record_high(registry, severity=Severity.MEDIUM, error_msg="e2")

        created = FailureDistiller(registry=registry, memory=memory).distill()
        assert created == []


class TestDistillIdempotencia:
    """Dedup y limites."""

    def test_segunda_corrida_no_duplica(self, tmp_path: Path) -> None:
        """La 2da corrida sobre la misma memoria genera 0 nuevos."""
        registry = _make_registry(tmp_path)
        memory = _make_memory(tmp_path)
        _record_high(registry)
        distiller = FailureDistiller(registry=registry, memory=memory)

        first = distiller.distill()
        second = distiller.distill()

        assert len(first) == 1
        assert second == []

    def test_max_skills_limita(self, tmp_path: Path) -> None:
        """max_skills=1 con 2 destilables → genera solo 1."""
        registry = _make_registry(tmp_path)
        memory = _make_memory(tmp_path)
        _record_high(registry, error_msg="e1", tags=("a",))
        _record_high(registry, error_msg="e2", tags=("b",))
        distiller = FailureDistiller(registry=registry, memory=memory)

        created = distiller.distill(max_skills=1)
        assert len(created) == 1


class TestDistillBestEffort:
    """La escritura fallida no debe romper el loop."""

    def test_escritura_fallida_no_rompe(self, tmp_path: Path) -> None:
        """Si register_skill lanza, distill loguea y continua sin excepcion."""

        class _FailingMemory(ProceduralMemory):
            def register_skill(self, *args, **kwargs):  # type: ignore[override]
                raise OSError("disco lleno")

        registry = _make_registry(tmp_path)
        memory = _FailingMemory(skills_dir=str(tmp_path / "auto_skills"))
        _record_high(registry)

        created = FailureDistiller(registry=registry, memory=memory).distill()
        assert created == []
