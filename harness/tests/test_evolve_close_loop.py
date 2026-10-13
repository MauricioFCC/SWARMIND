"""Tests TDD del script ``scripts/evolve_close_loop.py`` (cierre determinista EVO).

Contrato RED→GREEN del comando que cierra el loop de auto-mejora (validate →
distill → hash → reporte):

  (a) ``--dry-run`` NO escribe skills y termina con exit 0.
  (b) sin ``--dry-run`` y con fallos resueltos HIGH/CRITICAL, destila y persiste
      1 skill ``.md`` en el ``skills_dir`` inyectado.
  (c) ``--json`` emite JSON parseable con los pasos del loop.

Aislamiento (VER/IDP): el registry y la memoria se inyectan via
``distiller_provider`` con ``tmp_path``; NUNCA se toca el registry real ni
``.opencode/skills/auto``. El validador y el hasher se inyectan para no lanzar
subprocesos en los tests.
"""

from __future__ import annotations

import json
import sys
from collections.abc import Callable
from pathlib import Path

#: ``scripts/`` esta fuera de ``harness/`` -> se agrega al path de import.
_SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"
sys.path.insert(1, str(_SCRIPTS))

import evolve_close_loop as cli

from harness.evolve_loop.failure_distiller import FailureDistiller
from harness.evolve_loop.procedural_memory import ProceduralMemory
from harness.failure_registry.registry import (
    FailureRegistry,
    FailureType,
    Severity,
)

#: Fallo base HIGH y resuelto (destilable por defecto).
_BASE_RECORD: dict[str, object] = {
    "task": "Cierre del loop en CI",
    "failure_type": FailureType.CONFIG,
    "error_msg": "uv.lock desincronizado",
    "root_cause": "El lockfile no se regenero tras anadir una dependencia",
    "resolution": "Ejecutar uv lock y commitear el lockfile",
    "severity": Severity.HIGH,
    "tags": ("ci", "uv"),
}


def _provider(
    tmp_path: Path, records: list[dict[str, object]]
) -> tuple[Callable[[bool], FailureDistiller], Path]:
    """Construye un provider DI de ``FailureDistiller`` aislado en ``tmp_path``.

    Args:
        tmp_path: Directorio temporal de pytest.
        records: Fallos a sembrar en el registry temporal.

    Returns:
        Tupla ``(provider, skills_dir)`` donde ``provider(dry_run)`` devuelve un
        distiller cuyo registry y memoria escriben bajo ``tmp_path``.
    """
    registry = FailureRegistry(path=tmp_path / "failures.jsonl")
    for record in records:
        registry.record(**record)  # type: ignore[arg-type]
    skills_dir = tmp_path / "auto_skills"

    def provider(dry_run: bool) -> FailureDistiller:
        memory = ProceduralMemory(skills_dir=str(skills_dir))
        return FailureDistiller(
            registry=registry, memory=memory, min_severity=Severity.HIGH
        )

    return provider, skills_dir


def _ok_validator() -> cli.StepResult:
    """Validador DI que siempre pasa (evita subproceso)."""
    return cli.StepResult(name="validate", ok=True, detail="ok")


def _ok_hasher() -> cli.StepResult:
    """Hasher DI que no escribe (no-op) para aislar el test."""
    return cli.StepResult(name="hash_registry", ok=True, detail="no-op")


class TestDryRun:
    """``--dry-run``: proyecta sin escribir."""

    def test_dry_run_no_escribe_y_exit_0(
        self, tmp_path: Path, capsys
    ) -> None:
        """1 fallo HIGH resuelto: exit 0 y sin .md en el skills_dir."""
        provider, skills_dir = _provider(tmp_path, [dict(_BASE_RECORD)])

        code = cli.main(
            ["--dry-run"],
            validator=_ok_validator,
            distiller_provider=provider,
            hash_writer=_ok_hasher,
        )
        capsys.readouterr()

        assert code == 0
        assert list(skills_dir.glob("*.md")) == []


class TestDistill:
    """Sin ``--dry-run``: destila y persiste."""

    def test_no_dry_run_destila_skill(
        self, tmp_path: Path, capsys
    ) -> None:
        """1 fallo HIGH resuelto: exit 0 y 1 .md creado."""
        provider, skills_dir = _provider(tmp_path, [dict(_BASE_RECORD)])

        code = cli.main(
            [],
            validator=_ok_validator,
            distiller_provider=provider,
            hash_writer=_ok_hasher,
        )
        capsys.readouterr()

        assert code == 0
        assert len(list(skills_dir.glob("*.md"))) == 1

    def test_es_idempotente(self, tmp_path: Path, capsys) -> None:
        """Ejecutar dos veces NO duplica el skill (dedup determinista)."""
        provider, skills_dir = _provider(tmp_path, [dict(_BASE_RECORD)])

        cli.main([], validator=_ok_validator, distiller_provider=provider, hash_writer=_ok_hasher)
        cli.main([], validator=_ok_validator, distiller_provider=provider, hash_writer=_ok_hasher)
        capsys.readouterr()

        assert len(list(skills_dir.glob("*.md"))) == 1


class TestJsonOutput:
    """Salida machine-readable."""

    def test_json_parseable(
        self, tmp_path: Path, capsys
    ) -> None:
        """``--json`` emite JSON con ``ok`` y los 3 pasos del loop."""
        provider, _ = _provider(tmp_path, [dict(_BASE_RECORD)])

        code = cli.main(
            ["--json"],
            validator=_ok_validator,
            distiller_provider=provider,
            hash_writer=_ok_hasher,
        )
        payload = json.loads(capsys.readouterr().out)

        assert code == 0
        assert payload["ok"] is True
        assert [step["name"] for step in payload["steps"]] == [
            "validate",
            "distill",
            "hash_registry",
        ]

    def test_json_dry_run_sin_hash(
        self, tmp_path: Path, capsys
    ) -> None:
        """En ``--dry-run`` no se ejecuta el hash (no se escribe el registry)."""
        provider, _ = _provider(tmp_path, [dict(_BASE_RECORD)])

        cli.main(
            ["--dry-run", "--json"],
            validator=_ok_validator,
            distiller_provider=provider,
            hash_writer=_ok_hasher,
        )
        payload = json.loads(capsys.readouterr().out)

        assert payload["dry_run"] is True
        hash_step = next(s for s in payload["steps"] if s["name"] == "hash_registry")
        assert hash_step["changed"] is False


class TestValidationGate:
    """La validacion de skills es el gate del cierre del loop."""

    def test_validacion_fallida_exit_1(
        self, tmp_path: Path, capsys
    ) -> None:
        """Vaidador que falla: exit 1 aunque la destilacion no tenga trabajo."""
        provider, _ = _provider(tmp_path, [])

        def failing_validator() -> cli.StepResult:
            """Validador DI que simula un fallo de ``--strict``."""
            return cli.StepResult(name="validate", ok=False, detail="boom")

        code = cli.main(
            [],
            validator=failing_validator,
            distiller_provider=provider,
            hash_writer=_ok_hasher,
        )
        capsys.readouterr()

        assert code == 1

    def test_paso_que_lanza_no_tumba_el_reporte(
        self, tmp_path: Path, capsys
    ) -> None:
        """Un paso con excepcion se reporta como FAIL sin propagar (best-effort)."""
        provider, _ = _provider(tmp_path, [dict(_BASE_RECORD)])

        def exploding_hasher() -> cli.StepResult:
            """Hasher DI que lanza para probar el aislamiento de ``_safe_step``."""
            raise RuntimeError("store caido")

        code = cli.main(
            ["--json"],
            validator=_ok_validator,
            distiller_provider=provider,
            hash_writer=exploding_hasher,
        )
        payload = json.loads(capsys.readouterr().out)

        # El paso hash se ejecuta (hubo cambios), lanza, y se reporta como FAIL.
        hash_step = next(s for s in payload["steps"] if s["name"] == "hash_registry")
        assert code == 1
        assert hash_step["ok"] is False
        assert "store caido" in hash_step["detail"]
