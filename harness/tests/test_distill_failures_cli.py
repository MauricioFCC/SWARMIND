"""Tests TDD del CLI ``scripts/distill_failures.py`` (failure distillation post-merge).

Contrato RED→GREEN del comando invocable que aterriza el loop de destilacion
failure→skill (Socratic-SWE):

  (a) ``--dry-run`` NO escribe skills y reporta los fallos destilables
      (task y root_cause visibles en la salida).
  (b) sin flags destila y persiste 1 skill ``.md`` en el ``skills_dir`` inyectado.
  (c) ``--json`` emite JSON parseable con el campo ``"created"``.
  (d) ``--min-severity low`` incluye un fallo MEDIUM que el default ``high`` excluye.

Aislamiento (VER/IDP): el registry y la memoria se inyectan via
``distiller_factory`` con ``tmp_path``; NUNCA se toca el registry real ni
``.opencode/skills/auto``.
"""

from __future__ import annotations

import json
import sys
from collections.abc import Callable
from pathlib import Path

import pytest

#: ``scripts/`` esta fuera de ``harness/`` -> se agrega al path de import.
_SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"
sys.path.insert(1, str(_SCRIPTS))

import distill_failures as cli

from harness.evolve_loop.failure_distiller import FailureDistiller
from harness.evolve_loop.procedural_memory import ProceduralMemory
from harness.failure_registry.registry import (
    FailureRegistry,
    FailureType,
    Severity,
)

#: Campos base reutilizables de un fallo destilable.
_BASE_RECORD: dict[str, object] = {
    "task": "Deploy pipeline",
    "failure_type": FailureType.CONFIG,
    "error_msg": "env var DB_URL missing",
    "root_cause": "Variable de entorno no definida en CI",
    "resolution": "Declarar DB_URL en secrets del workflow",
    "severity": Severity.HIGH,
    "tags": ("ci", "config"),
}


def _make_factory(
    tmp_path: Path, records: list[dict[str, object]]
) -> tuple[Callable[[Severity], FailureDistiller], Path]:
    """Construye un factory DI de ``FailureDistiller`` aislado en ``tmp_path``.

    Args:
        tmp_path: Directorio temporal de pytest.
        records: Fallos a sembrar en el registry temporal.

    Returns:
        Tupla ``(factory, skills_dir)`` donde ``factory(severity)`` devuelve un
        distiller cuyo registry y memoria escriben bajo ``tmp_path``.
    """
    registry = FailureRegistry(path=tmp_path / "failures.jsonl")
    for record in records:
        registry.record(**record)  # type: ignore[arg-type]
    skills_dir = tmp_path / "auto_skills"

    def factory(min_severity: Severity) -> FailureDistiller:
        memory = ProceduralMemory(skills_dir=str(skills_dir))
        return FailureDistiller(
            registry=registry, memory=memory, min_severity=min_severity
        )

    return factory, skills_dir


class TestDryRun:
    """``--dry-run``: proyecta sin escribir."""

    def test_dry_run_no_escribe_y_reporta(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """1 fallo HIGH resuelto: exit 0, sin .md y salida con task y causa."""
        factory, skills_dir = _make_factory(tmp_path, [dict(_BASE_RECORD)])

        code = cli.main(["--dry-run"], distiller_factory=factory)
        out = capsys.readouterr().out

        assert code == 0
        assert list(skills_dir.glob("*.md")) == []
        assert "Deploy pipeline" in out
        assert "Variable de entorno no definida en CI" in out


class TestDistill:
    """Sin ``--dry-run``: persiste el skill."""

    def test_distill_escribe_skill(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """1 fallo HIGH resuelto: exit 0 y 1 .md creado en el skills_dir."""
        factory, skills_dir = _make_factory(tmp_path, [dict(_BASE_RECORD)])

        code = cli.main([], distiller_factory=factory)
        capsys.readouterr()

        assert code == 0
        created = list(skills_dir.glob("*.md"))
        assert len(created) == 1


class TestJsonOutput:
    """Salida machine-readable."""

    def test_json_salida_parseable(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """``--json`` emite JSON con el campo ``created`` y 1 elemento."""
        factory, _ = _make_factory(tmp_path, [dict(_BASE_RECORD)])

        code = cli.main(["--json"], distiller_factory=factory)
        payload = json.loads(capsys.readouterr().out)

        assert code == 0
        assert "created" in payload
        assert len(payload["created"]) == 1


class TestMinSeverity:
    """El umbral de severidad filtra los fallos destilables."""

    @staticmethod
    def _high_and_medium() -> list[dict[str, object]]:
        """Devuelve un par de fallos resueltos HIGH y MEDIUM.

        Returns:
            Lista con un fallo HIGH y uno MEDIUM, ambos resueltos.
        """
        high = dict(_BASE_RECORD, error_msg="hi-err", tags=("hi",))
        medium = dict(
            _BASE_RECORD, error_msg="med-err", tags=("med",), severity=Severity.MEDIUM
        )
        return [high, medium]

    def test_min_severity_low_incluye_medium(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """``--min-severity low`` destila ambos (HIGH + MEDIUM)."""
        factory, _ = _make_factory(tmp_path, self._high_and_medium())

        code = cli.main(["--min-severity", "low", "--json"], distiller_factory=factory)
        payload = json.loads(capsys.readouterr().out)

        assert code == 0
        assert len(payload["created"]) == 2

    def test_min_severity_high_excluye_medium(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """El default ``high`` destila solo el fallo HIGH."""
        factory, _ = _make_factory(tmp_path, self._high_and_medium())

        code = cli.main(["--json"], distiller_factory=factory)
        payload = json.loads(capsys.readouterr().out)

        assert code == 0
        assert len(payload["created"]) == 1
