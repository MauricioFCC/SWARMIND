"""Tests TDD del paso ``--check-lift`` en ``scripts/evolve_close_loop.py``.

Verifica la integracion del Skill Lift REAL al cierre del loop EVO:

    (a) ``--check-lift`` agrega el paso ``check_lift`` al reporte (dry-run, DI).
    (b) el paso NO bloquea: una skill harmful se reporta pero el exit code
        sigue siendo 0 (avisa, no aplica retiro).
    (c) sin ``--check-lift`` el paso no aparece.
    (d) el checker por defecto corre el catalogo real y no hay harmful.

Aislamiento (VER/IDP): el validador, el distiller y el hasher se inyectan via DI
para no lanzar subprocesos ni tocar el registry real.
"""

from __future__ import annotations

import importlib.util
import io
import json
import sys
from pathlib import Path
from types import ModuleType

#: ``scripts/`` esta fuera de ``harness/`` -> se carga el modulo por ruta para
#: evitar tocar ``sys.path`` (E402) en este archivo de tests.
_SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "evolve_close_loop.py"


def _load_module() -> ModuleType:
    """Carga ``scripts/evolve_close_loop.py`` como modulo aislado.

    Returns:
        El modulo ejecutable (con su ``main``/``StepResult``).
    """
    spec = importlib.util.spec_from_file_location("evolve_close_loop_lift", _SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class _StubDistiller:
    """Distiller no-op para tests (no toca el registry real)."""

    def preview(self, *, max_skills: int = 10) -> list[object]:
        """No hay fallos destilables en el test."""
        return []

    def distill(self, *, max_skills: int = 10) -> list[object]:
        """No crea skills en el test."""
        return []


def _ok_validator(module: ModuleType) -> object:
    """Validador DI que siempre pasa (sin subproceso)."""
    return module.StepResult(name="validate", ok=True, detail="stub")


class _Capture:
    """stdout falsa que soporta ``reconfigure`` (hardening Windows del CLI)."""

    def __init__(self) -> None:
        self._buffer = io.StringIO()

    def write(self, text: str) -> int:
        """Escribe al buffer interno y devuelve los caracteres escritos."""
        return self._buffer.write(text)

    def flush(self) -> None:
        """No-op (el buffer es en memoria)."""

    def reconfigure(self, **kwargs: object) -> None:
        """No-op: emula ``TextIOWrapper.reconfigure`` sin efectos."""

    def getvalue(self) -> str:
        """Devuelve el texto capturado."""
        return self._buffer.getvalue()


def _run(module: ModuleType, argv: list[str], *, lift_checker: object) -> tuple[int, dict]:
    """Ejecuta ``main`` con DI y devuelve (exit code, payload JSON)."""
    capture = _Capture()
    original = sys.stdout
    sys.stdout = capture  # type: ignore[assignment]
    try:
        code = module.main(
            argv,
            validator=lambda: _ok_validator(module),
            distiller_provider=lambda _dry: _StubDistiller(),
            hash_writer=lambda: module.StepResult(name="hash_registry", ok=True),
            lift_checker=lift_checker,
        )
    finally:
        sys.stdout = original
    return code, json.loads(capture.getvalue())


def test_a_check_lift_agrega_el_paso() -> None:
    """(a) --check-lift incluye el paso check_lift en el reporte JSON."""
    module = _load_module()

    def checker() -> object:
        """Stub DI: paso check_lift sin harmful."""
        return module.StepResult(name="check_lift", ok=True, detail="0 harmful", data={"harmful": []})

    code, payload = _run(module, ["--dry-run", "--check-lift", "--json"], lift_checker=checker)

    names = [step["name"] for step in payload["steps"]]
    assert code == 0
    assert "check_lift" in names
    assert all(step["ok"] for step in payload["steps"])


def test_b_harmful_no_bloquea() -> None:
    """(b) una skill harmful se reporta pero el exit code sigue siendo 0."""
    module = _load_module()

    def checker() -> object:
        """Stub DI: paso check_lift con una skill harmful (no bloqueante)."""
        return module.StepResult(
            name="check_lift",
            ok=True,
            detail="1 skill(s) harmful de 7",
            data={"harmful": ["demo-mala"]},
        )

    code, payload = _run(module, ["--dry-run", "--check-lift", "--json"], lift_checker=checker)

    step = next(s for s in payload["steps"] if s["name"] == "check_lift")
    assert code == 0
    assert step["data"]["harmful"] == ["demo-mala"]


def test_c_sin_flag_no_aparece() -> None:
    """(c) sin --check-lift el paso check_lift no se ejecuta."""
    module = _load_module()
    code, payload = _run(
        module,
        ["--dry-run", "--json"],
        lift_checker=lambda: module.StepResult(name="check_lift", ok=True),
    )

    names = [step["name"] for step in payload["steps"]]
    assert code == 0
    assert "check_lift" not in names


def test_d_checker_por_defecto_usa_el_catalogo_real() -> None:
    """(d) el checker por defecto evalua el catalogo real sin harmful."""
    module = _load_module()
    step = module._default_lift_checker()

    assert step.ok is True
    assert step.data["harmful"] == []
    assert len(step.data["verdicts"]) >= 6
    assert set(step.data["verdicts"].values()) == {"useful"}
