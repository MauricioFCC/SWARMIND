"""Tests TDD del mini-SWE-bench (fixes reales + modo mutante del oraculo).

`validate_oracle` inyecta la falla y exige que los tests la cacen;
`evaluate_patch` aplica un diff y exige FTP verdes + PTP intactos.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from harness.evals.swebench_mini import (
    MINI_SWE_BENCH,
    FaultSpec,
    SWEInstance,
    evaluate_patch,
    validate_oracle,
)

CALC = "def add(a: int, b: int) -> int:\n    return a + b\n\n\ndef mul(a: int, b: int) -> int:\n    return a * b\n"
TEST_CALC = (
    "from calc import add, mul\n\n\n"
    "def test_add():\n    assert add(2, 3) == 5\n\n\n"
    "def test_mul():\n    assert mul(2, 3) == 6\n"
)
#: Arbol roto: `add` resta (FTP rojo) pero `mul` sigue correcto.
BROKEN_ADD = CALC.replace("return a + b", "return a - b")
#: Objetivo que arregla FTP y rompe PTP (mul suma en vez de multiplicar).
TARGET_BREAK_PTP = CALC.replace("return a * b", "return a + b")

pytestmark = pytest.mark.skipif(
    __import__("shutil").which("git") is None, reason="requiere git"
)


def _write_lf(path: Path, content: str) -> None:
    """Escribe con salto LF explicito (Windows traduce `\\n` a CRLF por defecto)."""
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(content)


def _patch_to(repo: Path, rel: str, *, current: str, target: str) -> str:
    """Diff que lleva la working tree de `current` a `target` (via indice git).

    Stagea `current`, escribe `target`, captura `git diff` (indice->working) y
    deja la working tree de vuelta en `current`. El patch se genera de los
    bytes reales del repo: aplica siempre, sin depender de CRLF ni literales.
    """
    _write_lf(repo / rel, current)
    subprocess.run(["git", "add", "--", rel], cwd=repo, check=True, capture_output=True)
    _write_lf(repo / rel, target)
    diff = subprocess.run(
        ["git", "diff", "--", rel], cwd=repo, capture_output=True, text=True, check=True
    ).stdout
    subprocess.run(
        ["git", "reset", "-q", "HEAD", "--", rel], cwd=repo, check=True, capture_output=True
    )
    _write_lf(repo / rel, current)
    return diff


@pytest.fixture()
def tiny_repo(tmp_path):
    """Repo fixture minimo con git init para `git apply` (saltos LF estables)."""
    _write_lf(tmp_path / "calc.py", CALC)
    _write_lf(tmp_path / "test_calc.py", TEST_CALC)
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "core.autocrlf", "false"], cwd=tmp_path, check=True)
    subprocess.run(
        ["git", "-c", "user.email=t@t", "-c", "user.name=t",
         "add", "-A"], cwd=tmp_path, check=True,
    )
    subprocess.run(
        ["git", "-c", "user.email=t@t", "-c", "user.name=t",
         "commit", "-qm", "base"], cwd=tmp_path, check=True,
    )
    return tmp_path


def _instance(**kwargs) -> SWEInstance:
    """Instancia de prueba sobre el repo fixture."""
    base = {
        "id": "demo",
        "issue": "add resta en vez de sumar",
        "fail_to_pass": ("test_calc.py::test_add",),
        "pass_to_pass": ("test_calc.py::test_mul",),
        "fault": FaultSpec("calc.py", "return a + b", "return a - b"),
    }
    base.update(kwargs)
    return SWEInstance(**base)


def test_validate_oracle_ok_when_tests_catch_fault(tiny_repo) -> None:
    """Falla inyectada que rompe FTP -> ORACLE_OK y repo restaurado."""
    before = (tiny_repo / "calc.py").read_bytes()
    report = validate_oracle(_instance(), tiny_repo)
    assert report.status == "ORACLE_OK"
    assert (tiny_repo / "calc.py").read_bytes() == before


def test_validate_oracle_weak_when_fault_is_silent(tiny_repo) -> None:
    """Falla que no rompe nada -> ORACLE_WEAK (test ciego)."""
    instance = _instance(fault=FaultSpec("calc.py", "return a * b", "return a*b"))
    report = validate_oracle(instance, tiny_repo)
    assert report.status == "ORACLE_WEAK"


def test_evaluate_patch_resolved(tiny_repo) -> None:
    """Parche bueno sobre arbol roto -> RESOLVED y arbol restaurado al pre-call."""
    patch = _patch_to(tiny_repo, "calc.py", current=BROKEN_ADD, target=CALC)
    before = (tiny_repo / "calc.py").read_bytes()
    verdict = evaluate_patch(_instance(), patch, tiny_repo)
    assert verdict.status == "RESOLVED", verdict.detail
    assert (tiny_repo / "calc.py").read_bytes() == before


def test_evaluate_patch_unresolved_when_breaks_ptp(tiny_repo) -> None:
    """Parche que arregla FTP pero rompe PTP -> UNRESOLVED."""
    patch = _patch_to(
        tiny_repo, "calc.py", current=BROKEN_ADD, target=TARGET_BREAK_PTP
    )
    verdict = evaluate_patch(_instance(), patch, tiny_repo)
    assert verdict.status == "UNRESOLVED", verdict.detail


def test_evaluate_patch_malformed_returns_error(tiny_repo) -> None:
    """Un texto que no es un diff -> ERROR (no excepcion ni crash)."""
    verdict = evaluate_patch(_instance(), "esto no es un diff", tiny_repo)
    assert verdict.status == "ERROR", verdict.detail


def test_evaluate_patch_cleans_created_files(tiny_repo) -> None:
    """Un parche que crea un archivo lo elimina al restaurar (sin leftover)."""
    patch = (
        "--- /dev/null\n+++ b/newmod.py\n@@ -0,0 +1,2 @@\n"
        "+def helper() -> int:\n+    return 1\n"
    )
    verdict = evaluate_patch(_instance(), patch, tiny_repo)
    assert verdict.status == "RESOLVED", verdict.detail
    assert not (tiny_repo / "newmod.py").exists()


def test_validate_oracle_error_when_ptp_missing(tiny_repo) -> None:
    """Si PTP no existe, el arbol no queda verde tras restore -> ERROR."""
    instance = _instance(pass_to_pass=("test_calc.py::no_existe",))
    report = validate_oracle(instance, tiny_repo)
    assert report.status == "ERROR", report.detail


def test_seeds_reference_real_files() -> None:
    """Las 3 semillas apuntan a archivos y fallas que existen en el repo."""
    repo_root = Path(__file__).resolve().parents[2]
    assert len(MINI_SWE_BENCH) == 3
    assert len({s.id for s in MINI_SWE_BENCH}) == 3
    for seed in MINI_SWE_BENCH:
        assert seed.fail_to_pass and seed.pass_to_pass
        text = (repo_root / seed.fault.file).read_text(encoding="utf-8")
        assert seed.fault.old in text, seed.id


def test_seeds_alive_on_healthy_tree() -> None:
    """En arbol sano, FTP+PTP de las 3 semillas pasan en una sola corrida."""
    from harness.evals.swebench_mini import run_pytest

    repo_root = Path(__file__).resolve().parents[2]
    nodes: list[str] = []
    for seed in MINI_SWE_BENCH:
        nodes.extend(seed.fail_to_pass)
        nodes.extend(seed.pass_to_pass)
    assert run_pytest(repo_root, nodes).returncode == 0
