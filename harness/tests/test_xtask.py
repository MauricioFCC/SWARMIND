"""Tests de ``scripts/xtask.py``: la política única de gates y trinquetes.

Contratos cubiertos:
  1. La política real es válida: ids únicos, ``kind`` conocido y scripts que
     existen (un gate roto por typo se detecta sin ejecutar nada).
  2. ``select`` respeta modo (``check|gate|ratchet``), ``--fast`` (pre-commit),
     ``--only`` y ``--skip`` sin sorpresas.
  3. ``run_gate`` clasifica PASS/FAIL/SKIP y un timeout es FAIL (nunca cuelga).
  4. ``main`` devuelve 2 si la política es inválida, 1 si algún gate falla y
     0 solo si todo pasa (contrato de exit codes para pre-commit y CI).
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import xtask


def _gate(
    gate_id: str = "demo",
    kind: str = "gate",
    cmd: tuple[str, ...] = ("{py}", "-c", "print('ok')"),
    fast: bool = False,
    timeout: int = 30,
    why: str = "demo",
) -> xtask.Gate:
    """Construye un ``Gate`` de prueba con defaults inocuos."""
    return xtask.Gate(gate_id, kind, cmd, fast, timeout, why)


# ---------------------------------------------------------------------------
# 1. Validación de la política
# ---------------------------------------------------------------------------


def test_politica_real_es_valida() -> None:
    """La POLICY versionada no tiene ids duplicados, kinds ni scripts rotos."""
    assert xtask.validate_policy() == []


def test_politica_detecta_id_duplicado() -> None:
    """Dos gates con el mismo id hacen la selección ambigua."""
    errores = xtask.validate_policy((_gate("dup"), _gate("dup")))

    assert any("id duplicado" in e for e in errores)


def test_politica_detecta_kind_invalido() -> None:
    """Un ``kind`` fuera de {gate, ratchet, security} es un error de política."""
    errores = xtask.validate_policy((_gate("x", kind="lint"),))

    assert any("kind inválido" in e for e in errores)


def test_politica_detecta_script_inexistente() -> None:
    """Un ``scripts/no_existe.py`` debe fallar en validación, no en ejecución."""
    errores = xtask.validate_policy(
        (_gate("x", cmd=("{py}", "scripts/no_existe_jamas.py")),)
    )

    assert any("no existe" in e for e in errores)


def test_politica_detecta_cmd_vacio() -> None:
    """Una política sin comando no puede ejecutarse."""
    errores = xtask.validate_policy((_gate("x", cmd=()),))

    assert any("cmd vacío" in e for e in errores)


# ---------------------------------------------------------------------------
# 2. Selección por modo y filtros
# ---------------------------------------------------------------------------


def test_select_ratchet_solo_trinquetes() -> None:
    """``ratchet`` corre solo los gates decrease-only."""
    politica = (
        _gate("lint", kind="gate"),
        _gate("arch", kind="ratchet"),
        _gate("sec", kind="security"),
    )

    elegidas = xtask.select(politica, "ratchet")

    assert [g.id for g in elegidas] == ["arch"]


def test_select_gate_excluye_tests_por_defecto() -> None:
    """``gate`` (pre-commit) no paga la suite completa."""
    politica = (_gate("arch", kind="ratchet"), _gate("tests", kind="gate"))

    assert [g.id for g in xtask.select(politica, "gate")] == ["arch"]


def test_select_gate_con_tests_los_incluye() -> None:
    """``--with-tests`` añade la suite al modo gate."""
    politica = (_gate("arch", kind="ratchet"), _gate("tests", kind="gate"))

    ids = [g.id for g in xtask.select(politica, "gate", with_tests=True)]

    assert ids == ["arch", "tests"]


def test_select_check_incluye_todo() -> None:
    """``check`` es el conjunto completo (tests incluidos)."""
    politica = (
        _gate("lint", kind="gate"),
        _gate("arch", kind="ratchet"),
        _gate("tests", kind="gate"),
    )

    assert len(xtask.select(politica, "check")) == 3


def test_select_fast_solo_subconjunto_precommit() -> None:
    """``--fast`` limita a los gates marcados como rápidos."""
    politica = (_gate("rapido", fast=True), _gate("lento", fast=False))

    assert [g.id for g in xtask.select(politica, "gate", fast=True)] == ["rapido"]


def test_select_only_manda_sobre_el_resto() -> None:
    """``--only`` restringe la ejecución a los ids pedidos."""
    politica = (_gate("a"), _gate("b"), _gate("c"))

    assert [g.id for g in xtask.select(politica, "check", only=frozenset({"b"}))] == ["b"]


def test_select_skip_excluye_ids() -> None:
    """``--skip`` quita ids del conjunto ya seleccionado."""
    politica = (_gate("a"), _gate("b"))

    assert [g.id for g in xtask.select(politica, "check", skip=frozenset({"a"}))] == ["b"]


# ---------------------------------------------------------------------------
# 3. Ejecución y clasificación
# ---------------------------------------------------------------------------


def test_command_sustituye_interprete() -> None:
    """``{py}`` se reemplaza por el intérprete actual (portabilidad)."""
    comando = xtask._command(_gate(cmd=("{py}", "-c", "pass")))

    assert comando[0] == sys.executable


def test_run_gate_pass_con_exit_0(monkeypatch: pytest.MonkeyPatch) -> None:
    """Exit 0 del subproceso => PASS."""
    monkeypatch.setattr(
        xtask.subprocess, "run", lambda *a, **k: subprocess.CompletedProcess(a, 0, "", "")
    )

    assert xtask.run_gate(_gate()).status == "PASS"


def test_run_gate_fail_con_exit_distinto_de_0(monkeypatch: pytest.MonkeyPatch) -> None:
    """Un código de salida != 0 => FAIL y se conserva el detalle."""
    monkeypatch.setattr(
        xtask.subprocess,
        "run",
        lambda *a, **k: subprocess.CompletedProcess(a, 1, "", "boom: 3 errores"),
    )

    resultado = xtask.run_gate(_gate())

    assert resultado.status == "FAIL"
    assert "boom" in resultado.detail


def test_run_gate_skip_si_falta_herramienta(monkeypatch: pytest.MonkeyPatch) -> None:
    """Exit 127 (herramienta ausente) degrada a SKIP, no a FAIL."""
    monkeypatch.setattr(
        xtask.subprocess, "run", lambda *a, **k: subprocess.CompletedProcess(a, 127, "", "")
    )

    assert xtask.run_gate(_gate()).status == "SKIP"


def test_run_gate_timeout_es_fail(monkeypatch: pytest.MonkeyPatch) -> None:
    """Un timeout no bloquea el runner: se reporta FAIL con el límite."""

    def _expira(*_a, **_k):
        raise subprocess.TimeoutExpired(cmd="x", timeout=30)

    monkeypatch.setattr(xtask.subprocess, "run", _expira)

    resultado = xtask.run_gate(_gate(timeout=30))

    assert resultado.status == "FAIL"
    assert "timeout" in resultado.detail


# ---------------------------------------------------------------------------
# 4. Contrato de exit codes de main()
# ---------------------------------------------------------------------------


def _resultado(gate_id: str, status: str) -> xtask.Result:
    """``Result`` mínimo para simular corridas sin subprocesos."""
    return xtask.Result(gate_id, "gate", status, 0.0)


def test_main_exit_0_cuando_todo_pasa(monkeypatch: pytest.MonkeyPatch) -> None:
    """Todos PASS => exit 0."""
    monkeypatch.setattr(xtask, "run_all", lambda gates: [_resultado("a", "PASS")])

    assert xtask.main(["check"]) == 0


def test_main_exit_1_si_algun_gate_falla(monkeypatch: pytest.MonkeyPatch) -> None:
    """Un solo FAIL => exit 1 (pre-commit/CI se detienen)."""
    monkeypatch.setattr(
        xtask, "run_all", lambda gates: [_resultado("a", "PASS"), _resultado("b", "FAIL")]
    )

    assert xtask.main(["check"]) == 1


def test_main_exit_2_si_la_politica_es_invalida(monkeypatch: pytest.MonkeyPatch) -> None:
    """Política inválida => exit 2 sin ejecutar gates."""
    monkeypatch.setattr(xtask, "validate_policy", lambda policy=xtask.POLICY: ["roto"])
    monkeypatch.setattr(xtask, "run_all", lambda gates: pytest.fail("no debe correr"))

    assert xtask.main(["check"]) == 2


def test_main_exit_2_si_la_seleccion_queda_vacia() -> None:
    """Filtrar hasta no dejar gates es un error de uso, no un falso verde."""
    assert xtask.main(["check", "--only", "id-que-no-existe"]) == 2


def test_summarize_cuenta_estados() -> None:
    """``summarize`` agrega PASS/FAIL/SKIP y calcula ``ok``."""
    resumen = xtask.summarize(
        [_resultado("a", "PASS"), _resultado("b", "SKIP"), _resultado("c", "FAIL")]
    )

    assert resumen["total"] == 3
    assert resumen["counts"] == {"PASS": 1, "FAIL": 1, "SKIP": 1}
    assert resumen["ok"] is False
