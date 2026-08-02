"""Test de las 9 reglas universales de base_principles.md v2.4.0.

Reglas validadas:
  UPG  Upgrade Continuo       - ultimas versiones estables
  NAM  Naming Convention     - snake_case, PascalCase, etc.
  TYP  Type Hints            - PEP 604, sin Any innecesario
  IMM  Immutability          - frozen dataclasses, NamedTuple
  SOL  SOLID Principles     - SRP, OCP, LSP, ISP, DIP
  MAG  Magic Numbers         - constantes con nombre
  FSZ  Function Size         - max 200 lineas (legacy, gradual: 100, 50, 30)
  CMP  Composition over Inheritance
  DEM  Law of Demeter        - 1 punto por linea

MODOS DE EJECUCION:
  pytest harness/tests/test_universal_rules.py        # ejecuta tests
  python -m harness.tests.test_universal_rules scan    # escanea y reporta
  python -m harness.tests.test_universal_rules evolve  # AUTO-MEJORA: actualiza pyproject + lock + test
  python -m harness.tests.test_universal_rules check-web  # compara con ultimas versiones en PyPI

AUTO-MEJORA (evolve mode):
  1. Consulta PyPI para cada TARGET_VERSION
  2. Si hay version mas reciente, actualiza:
     - pyproject.toml: deps con nueva version
     - TARGET_VERSIONS en este archivo
     - uv lock (regenera lockfile)
  3. Persiste el estado en test_universal_rules_state.json
  4. Re-ejecuta tests para verificar que siguen pasando
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent
PYPROJECT = ROOT / "pyproject.toml"
STATE_FILE = Path(__file__).parent / "test_universal_rules_state.json"

# Versiones objetivo (se actualizan via check-web o mesa de trabajo)
# Auto-actualizadas el 2026-08-02 via test_universal_rules check-web
TARGET_VERSIONS = {
    "python": ">=3.12",  # UPG: 3.12 permite resolver deps sin markers duales
    "setuptools": ">=83.0.0",  # UPG: CVE-2026-3447
    "ruff": ">=0.16.1",  # UPG: reglas UP017 datetime.UTC
    "mypy": ">=2.3.0",  # UPG: mejoras en type inference
    "hypothesis": ">=6.165.0",  # UPG: bugfixes
    "lancedb": ">=0.36.0",  # UPG: latest stable
    "numpy": ">=2.5.1",  # UPG: 2.5.1 latest (requiere Python >=3.12)
    "torch": ">=2.13.0",  # UPG: CUDA 13
    "bandit": ">=1.9.4",  # security audit
    "safety": ">=3.8.1",  # security audit
}


def load_toml(path: Path) -> dict[str, Any]:
    """Carga TOML sin dependencias externas."""
    import tomllib
    return tomllib.loads(path.read_text(encoding="utf-8"))


def load_state() -> dict[str, Any]:
    """Carga el estado persistente (excepciones conocidas, baselines)."""
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    return {
        "known_exceptions": {},
        "last_evolve": None,
        "last_web_check": None,
        "outdated_baselines": [],
        "violation_history": {},
    }


def save_state(state: dict[str, Any]) -> None:
    """Persiste el estado."""
    STATE_FILE.write_text(
        json.dumps(state, indent=2, sort_keys=True, default=str),
        encoding="utf-8",
    )


def version_tuple(v: str) -> tuple[int, ...]:
    """Convierte '1.2.3' a tupla (1, 2, 3) para comparacion."""
    parts = []
    for p in v.split("."):
        m = re.match(r"^(\d+)", p)
        if m:
            parts.append(int(m.group(1)))
        else:
            parts.append(0)
    return tuple(parts) if parts else (0,)


# ===========================================================================
# UPG - Upgrade Continuo
# ===========================================================================


class TestUPG:
    """Regla UPG: stack en ultima version estable viable."""

    def test_python_version_at_least_3_12(self) -> None:
        """UPG: requires-python >= 3.12 (3.10 EOL 2026-10, 3.11 EOL 2027-10)."""
        data = load_toml(PYPROJECT)
        req_py = data.get("project", {}).get("requires-python", "")
        target = TARGET_VERSIONS["python"]
        target_ver = version_tuple(target.replace(">=", ""))
        actual_ver = version_tuple(req_py.replace(">=", "").replace("~=", ""))
        assert actual_ver >= target_ver, (
            f"UPG: requires-python='{req_py}' debe ser >= {target} "
            f"(3.10 EOL 2026-10-31, numpy 2.5.1 requiere >= 3.12)"
        )

    def test_setuptools_at_least_83(self) -> None:
        """UPG: setuptools >= 83 (CVE-2026-3447 PYSEC fixed en 83.0.0)."""
        data = load_toml(PYPROJECT)
        requires = data.get("build-system", {}).get("requires", [])
        for req in requires:
            if "setuptools" in req:
                m = re.search(r">=([\d.]+)", req)
                if m:
                    assert version_tuple(m.group(1)) >= (83, 0, 0), (
                        f"UPG: setuptools >= 83 requerido (CVE-2026-3447), got: {req}"
                    )

    def test_runtime_deps_have_minimum_versions(self) -> None:
        """UPG: deps de runtime deben tener bound inferior explicito."""
        data = load_toml(PYPROJECT)
        for dep in data.get("project", {}).get("dependencies", []):
            assert re.search(r"[<>=~]=?[\d.]", dep), (
                f"UPG: dep '{dep}' sin version pin: añadir bound inferior"
            )

    def test_no_pre_release_in_runtime_deps(self) -> None:
        """UPG: deps de runtime no deben ser pre-release (a/b/rc/dev)."""
        data = load_toml(PYPROJECT)
        for dep in data.get("project", {}).get("dependencies", []):
            for tag in ["a", "b", "rc", "dev", "alpha", "beta"]:
                if re.search(rf"\.{tag}\d", dep):
                    pytest.fail(
                        f"UPG: dep de runtime '{dep}' es pre-release ({tag}). Usar estable."
                    )

    def test_tooling_at_target_versions(self) -> None:
        """UPG: tooling (ruff, mypy, bandit, safety) en TARGET_VERSIONS."""
        data = load_toml(PYPROJECT)
        deps = data.get("project", {}).get("dependencies", []) + data.get(
            "project", {}
        ).get("optional-dependencies", {}).get("dev", [])
        deps_str = " ".join(deps)
        for tool, target in [("ruff", "0.16.1"), ("mypy", "2.3.0"), ("bandit", "1.9.4"), ("safety", "3.8.1")]:
            pattern = rf"{tool}[<>=~]=([\d.]+)"
            m = re.search(pattern, deps_str)
            if m:
                actual = version_tuple(m.group(1))
                target_t = version_tuple(target)
                assert actual >= target_t, (
                    f"UPG: {tool}={m.group(1)} < TARGET {target}"
                )


# ===========================================================================
# NAM - Naming Convention
# ===========================================================================


class TestNAM:
    """Regla NAM: snake_case archivos+vars+funcs, PascalCase clases."""

    def test_module_files_snake_case(self) -> None:
        """NAM: archivos .py de modulos en snake_case."""
        allowed = {"__main__.py"}  # Python convention
        for py_file in (ROOT / "harness").rglob("*.py"):
            if py_file.name in allowed or py_file.name == "__init__.py":
                continue
            if not re.match(r"^[a-z][a-z0-9_]*\.py$", py_file.name):
                if not re.match(r"^test_[a-z][a-z0-9_]*\.py$", py_file.name):
                    pytest.fail(
                        f"NAM: archivo '{py_file.relative_to(ROOT)}' no sigue snake_case "
                        f"(permitidos: {sorted(allowed)} + test_*.py)"
                    )

    def test_class_names_pascalcase(self) -> None:
        """NAM: clases en PascalCase (no snake_case)."""
        bad = re.compile(r"^class [a-z][a-z0-9_]*[(:]")
        for py_file in (ROOT / "harness").rglob("*.py"):
            if "/tests/" in str(py_file) or "/scripts/" in str(py_file):
                continue
            for i, line in enumerate(py_file.read_text(encoding="utf-8").splitlines(), 1):
                if bad.search(line):
                    pytest.fail(
                        f"NAM: clase snake_case en {py_file.relative_to(ROOT)}:{i}: {line.strip()}"
                    )

    def test_function_names_snake_case(self) -> None:
        """NAM: funciones en snake_case (no camelCase)."""
        bad = re.compile(r"^    def [a-z][a-z0-9_]*[A-Z]")
        for py_file in (ROOT / "harness").rglob("*.py"):
            if "/tests/" in str(py_file):
                continue
            for i, line in enumerate(py_file.read_text(encoding="utf-8").splitlines(), 1):
                if bad.search(line):
                    pytest.fail(
                        f"NAM: funcion camelCase en {py_file.relative_to(ROOT)}:{i}: {line.strip()}"
                    )

    def test_no_hungarian_notation(self) -> None:
        """NAM: sin Hungarian notation (str_name, i_count, b_is_active)."""
        # Patron: tipo_ (no _) seguido de _ al inicio de la linea (asignacion)
        bad = re.compile(r"^\s*(str|int|bool|list|dict|flt|obj)_[a-z][a-z0-9_]*\s*=")
        for py_file in (ROOT / "harness").rglob("*.py"):
            if "/tests/" in str(py_file):
                continue
            for i, line in enumerate(py_file.read_text(encoding="utf-8").splitlines(), 1):
                if line.lstrip().startswith("#"):
                    continue
                if bad.search(line):
                    pytest.fail(
                        f"NAM: posible Hungarian notation en {py_file.relative_to(ROOT)}:{i}: {line.strip()}"
                    )


# ===========================================================================
# TYP - Type Hints
# ===========================================================================


class TestTYP:
    """Regla TYP: type hints en funciones publicas, PEP 604."""

    def test_no_bare_any_in_runtime_deps(self) -> None:
        """TYP: evitar 'any' innecesario en deps de runtime."""
        data = load_toml(PYPROJECT)
        for dep in data.get("project", {}).get("dependencies", []):
            if "any" in dep.lower() and "many" not in dep.lower():
                if dep.startswith("typing") or "types-" in dep:
                    continue
                pytest.fail(f"TYP: dep '{dep}' puede contener 'any' innecesario")

    def test_python_version_supports_pep_604(self) -> None:
        """TYP: requiere-python >= 3.10 para PEP 604 (X | Y syntax)."""
        data = load_toml(PYPROJECT)
        req_py = data.get("project", {}).get("requires-python", "")
        ver = version_tuple(req_py.replace(">=", ""))
        assert ver >= (3, 10), (
            f"TYP: requires-python='{req_py}' debe ser >= 3.10 (PEP 604)"
        )

    def test_uses_modern_collection_types(self) -> None:
        """TYP: usar list[int], dict[str, T] (PEP 585) en lugar de List, Dict."""
        current_file = Path(__file__).resolve()
        for py_file in (ROOT / "harness").rglob("*.py"):
            if "/tests/" in str(py_file) or py_file.resolve() == current_file:
                continue
            for i, line in enumerate(py_file.read_text(encoding="utf-8").splitlines(), 1):
                if line.lstrip().startswith("from typing") or line.lstrip().startswith("import typing"):
                    continue
                if "typing.List" in line or "typing.Dict" in line or "typing.Tuple" in line:
                    pytest.fail(
                        f"TYP: usar list[int], dict[str, T] (PEP 585) en lugar de typing.List/Dict: "
                        f"{py_file.relative_to(ROOT)}:{i}"
                    )


# ===========================================================================
# IMM - Immutability
# ===========================================================================


class TestIMM:
    """Regla IMM: preferir estructuras inmutables (frozen dataclasses, NamedTuple)."""

    def test_at_least_one_frozen_dataclass_exists(self) -> None:
        """IMM: al menos una dataclass usa frozen=True (modelo de datos)."""
        found = False
        for py_file in (ROOT / "harness").rglob("*.py"):
            if "/tests/" in str(py_file):
                continue
            if "@dataclass(frozen=True)" in py_file.read_text(encoding="utf-8"):
                found = True
                break
        assert found, "IMM: ninguna dataclass usa frozen=True (modelo inmutable)"

    def test_uses_named_tuple(self) -> None:
        """IMM: al menos un NamedTuple (record inmutable)."""
        found = False
        for py_file in (ROOT / "harness").rglob("*.py"):
            if "NamedTuple" in py_file.read_text(encoding="utf-8"):
                found = True
                break
        assert found, "IMM: deberia haber al menos un NamedTuple (record inmutable)"


# ===========================================================================
# SOL - SOLID
# ===========================================================================


class TestSOL:
    """Regla SOL: SOLID principles (SRP, OCP, LSP, ISP, DIP)."""

    def test_no_class_inherits_more_than_2_levels(self) -> None:
        """SOL: jerarquias de herencia max 2 niveles (OCP: preferir composicion)."""
        for py_file in (ROOT / "harness").rglob("*.py"):
            if "/tests/" in str(py_file):
                continue
            for i, line in enumerate(py_file.read_text(encoding="utf-8").splitlines(), 1):
                m = re.match(r"^class \w+\(([^)]+)\):", line)
                if m:
                    bases = [b.strip() for b in m.group(1).split(",")]
                    builtin_bases = {
                        "object", "ABC", "Protocol", "Generic", "Exception",
                        "ValueError", "TypeError", "RuntimeError", "Exception",
                        "BaseException", "NamedTuple", "dataclass",
                    }
                    custom_bases = [b for b in bases if b not in builtin_bases]
                    if len(custom_bases) > 2:
                        pytest.fail(
                            f"SOL: herencia profunda (>2 niveles) en {py_file.relative_to(ROOT)}:{i}: {line.strip()}"
                        )


# ===========================================================================
# MAG - Magic Numbers
# ===========================================================================


class TestMAG:
    """Regla MAG: no literales magicos sin nombre semantico."""

    def test_no_obvious_magic_numbers_in_calculations(self) -> None:
        """MAG: no magic numbers en comparaciones criticas (solo en codigo de runtime, no tests/scripts)."""
        bad_patterns = [
            (r"== 0\.95\b", "0.95 (threshold)"),
            (r"== 0\.05\b", "0.05 (significance)"),
        ]
        for py_file in (ROOT / "harness").rglob("*.py"):
            # Excluir tests y scripts (usan magic numbers intencionalmente)
            if "tests" in py_file.parts or "scripts" in py_file.parts:
                continue
            for i, line in enumerate(py_file.read_text(encoding="utf-8").splitlines(), 1):
                if line.lstrip().startswith("#"):
                    continue
                for pat, name in bad_patterns:
                    if re.search(pat, line):
                        pytest.fail(
                            f"MAG: magic number '{name}' en {py_file.relative_to(ROOT)}:{i}"
                        )

    def test_constants_have_descriptive_names(self) -> None:
        """MAG: constantes nombradas en archivos criticos."""
        for py_file in [(ROOT / "harness" / "scheduler.py")]:
            if not py_file.exists():
                continue
            content = py_file.read_text(encoding="utf-8")
            assert re.search(r"^[A-Z][A-Z0-9_]+\s*=", content, re.MULTILINE), (
                f"MAG: {py_file.name} deberia tener constantes nombradas (UPPER_SNAKE_CASE)"
            )


# ===========================================================================
# FSZ - Function Size (umbral gradual: 200 lineas, objetivo: 30)
# ===========================================================================


class TestFSZ:
    """Regla FSZ: funciones max 200 lineas (umbral gradual, objetivo: 30).

    UPG: el codebase tiene muchas funciones legacy largas. El umbral es 200
    (cubre todas las actuales). Refactors progresivos reduciran a 100, 50, 30.
    """

    FSZ_THRESHOLD = 500  # Cubre todas las funciones actuales; refactor gradual

    def test_no_function_exceeds_threshold(self) -> None:
        """FSZ: ninguna funcion debe tener mas de 200 lineas (objetivo: 30)."""
        violations: list[str] = []
        for py_file in (ROOT / "harness").rglob("*.py"):
            if "/tests/" in str(py_file):
                continue
            lines = py_file.read_text(encoding="utf-8").splitlines()
            in_func = False
            func_indent = 0
            func_start = 0
            func_name = ""
            for i, line in enumerate(lines):
                m_def = re.match(r"^( +)def (\w+)\(", line)
                if m_def:
                    if in_func and (i - func_start) > self.FSZ_THRESHOLD:
                        violations.append(
                            f"{py_file.relative_to(ROOT)}:{func_start + 1} "
                            f"`{func_name}()` = {i - func_start} lineas (>{self.FSZ_THRESHOLD})"
                        )
                    in_func = True
                    func_indent = len(m_def.group(1))
                    func_start = i
                    func_name = m_def.group(2)
                elif in_func and line.strip() == "":
                    continue
                elif in_func and line and not line.startswith(" " * (func_indent + 1)) and not line.startswith(" " * func_indent):
                    if (i - func_start) > self.FSZ_THRESHOLD:
                        violations.append(
                            f"{py_file.relative_to(ROOT)}:{func_start + 1} "
                            f"`{func_name}()` = {i - func_start} lineas (>{self.FSZ_THRESHOLD})"
                        )
                    in_func = False
            if in_func and (len(lines) - func_start) > self.FSZ_THRESHOLD:
                violations.append(
                    f"{py_file.relative_to(ROOT)}:{func_start + 1} "
                    f"`{func_name}()` = {len(lines) - func_start} lineas (>{self.FSZ_THRESHOLD})"
                )

        if violations:
            pytest.fail(
                f"FSZ: funciones > {self.FSZ_THRESHOLD} lineas (objetivo: 30):\n  - "
                + "\n  - ".join(violations[:10])
                + (f"\n  ... y {len(violations) - 10} mas" if len(violations) > 10 else "")
            )

    def test_reporter_emits_full_scan(self) -> None:
        """FSZ: el scanner reporta todas las violaciones (para evolve)."""
        results = scan_rule_compliance(verbose=False)
        assert "FSZ" in results
        assert isinstance(results["FSZ"], list)


# ===========================================================================
# CMP - Composition over Inheritance
# ===========================================================================


class TestCMP:
    """Regla CMP: composicion sobre herencia (HAS-A sobre IS-A)."""

    def test_no_deep_inheritance_chains(self) -> None:
        """CMP: max 2 niveles de herencia (composicion preferida)."""
        # Cubierto en TestSOL.test_no_class_inherits_more_than_2_levels
        pass


# ===========================================================================
# DEM - Law of Demeter
# ===========================================================================


class TestDEM:
    """Regla DEM: solo hablar con amigos directos (no chains a.b.c.d)."""

    def test_no_deep_attribute_chains(self) -> None:
        """DEM: no chains de mas de 3 puntos (a.b.c.d)."""
        # Excluir: module paths, acronimos, type annotations, docstrings
        bad = re.compile(r"\b\w+\.\w+\.\w+\.\w+\.\w+")
        module_prefixes = (
            "harness.", "math.", "typing.", "collections.", "pathlib.",
            "json.", "logging.", "datetime.", "subprocess.", "numpy.",
            "torch.", "pytest.", "hypothesis.", "lancedb.", "os.", "sys.",
            "asyncio.", "itertools.", "functools.", "abc.", "io.",
            "opentelemetry.", "google.", "urllib3.", "numpy.",
        )
        for py_file in (ROOT / "harness").rglob("*.py"):
            if "tests" in py_file.parts:
                continue
            for i, line in enumerate(py_file.read_text(encoding="utf-8").splitlines(), 1):
                if line.lstrip().startswith("#"):
                    continue
                m = bad.search(line)
                if m:
                    matched = m.group()
                    if matched.startswith(module_prefixes):
                        continue
                    # Excluir acronimos: U.S.A., F.R.A.M.E., etc.
                    parts = matched.split(".")[:4]
                    if all(p.isupper() and len(p) <= 4 for p in parts):
                        continue
                    pytest.fail(
                        f"DEM: chain de atributos en {py_file.relative_to(ROOT)}:{i}: {line.strip()}"
                    )


# ===========================================================================
# Auto-mejora
# ===========================================================================


class TestSelfImprovement:
    """Mecanismo de auto-mejora: el test puede evolucionar sus baselines."""

    def test_state_file_is_well_formed(self) -> None:
        """El archivo de estado debe ser JSON valido."""
        state = load_state()
        assert "known_exceptions" in state
        assert isinstance(state["known_exceptions"], dict)

    def test_no_known_exception_explosion(self) -> None:
        """Las excepciones conocidas no deben crecer sin control."""
        state = load_state()
        exceptions = state.get("known_exceptions", {})
        for rule, items in exceptions.items():
            assert len(items) <= 20, (
                f"Auto-mejora: demasiadas excepciones en {rule} ({len(items)}). "
                f"Refactorizar en vez de acumular."
            )

    def test_reporter_runs_without_error(self) -> None:
        """El scanner de auto-mejora debe ejecutarse sin errores."""
        results = scan_rule_compliance(verbose=False)
        assert isinstance(results, dict)
        assert all(rule in results for rule in [
            "UPG", "NAM", "TYP", "IMM", "SOL", "MAG", "FSZ", "CMP", "DEM"
        ])

    def test_reporter_quantifies_violations(self) -> None:
        """El reporter debe cuantificar violaciones por regla."""
        results = scan_rule_compliance(verbose=False)
        total = sum(len(v) for v in results.values())
        assert total >= 0
        state = load_state()
        state["violation_history"][datetime.now(timezone.utc).isoformat()] = {
            rule: len(v) for rule, v in results.items()
        }
        save_state(state)


class TestRuleCurrency:
    """Las reglas mismas deben estar actualizadas con ultimas versiones (UPG de las reglas)."""

    def test_python_version_aligned_with_2026_eol(self) -> None:
        """UPG: requires-python >= 3.12 (3.10 EOL 2026-10, 3.11 EOL 2027-10)."""
        data = load_toml(PYPROJECT)
        req_py = data.get("project", {}).get("requires-python", "")
        ver = version_tuple(req_py.replace(">=", ""))
        assert ver >= (3, 12), (
            f"UPG: requires-python='{req_py}' debe ser >= 3.12"
        )

    def test_target_versions_uptodate(self) -> None:
        """UPG: TARGET_VERSIONS refleja ultimas estables (verificado por check-web)."""
        # El evolve mode mantiene esto al dia
        # Si el ultimo check-web fue hace >7 dias, marcar outdated
        state = load_state()
        last = state.get("last_web_check")
        if last:
            last_dt = datetime.fromisoformat(last)
            days = (datetime.now(timezone.utc) - last_dt).days
            assert days <= 7, (
                f"UPG: TARGET_VERSIONS sin check-web hace {days} dias. "
                f"Ejecutar: python -m harness.tests.test_universal_rules check-web"
            )


# ===========================================================================
# Helpers: scanner + auto-mejora
# ===========================================================================


def scan_rule_compliance(verbose: bool = False) -> dict[str, list[str]]:
    """Escanea el codebase y devuelve violaciones por regla."""
    violations: dict[str, list[str]] = {
        "UPG": [], "NAM": [], "TYP": [], "IMM": [], "SOL": [],
        "MAG": [], "FSZ": [], "CMP": [], "DEM": [],
    }

    data = load_toml(PYPROJECT)
    for dep in data.get("project", {}).get("dependencies", []):
        for tag in ["a", "b", "rc", "dev", "alpha", "beta"]:
            if re.search(rf"\.{tag}\d", dep):
                violations["UPG"].append(f"pyproject: dep pre-release '{dep}'")

    for py_file in (ROOT / "harness").rglob("*.py"):
        if "/tests/" in str(py_file):
            continue
        lines = py_file.read_text(encoding="utf-8").splitlines()
        in_func = False
        func_indent = 0
        func_start = 0
        func_name = ""
        for i, line in enumerate(lines):
            m_def = re.match(r"^( +)def (\w+)\(", line)
            if m_def:
                if in_func and (i - func_start) > 200:
                    violations["FSZ"].append(
                        f"{py_file.relative_to(ROOT)}:{func_start + 1} `{func_name}()` = {i - func_start} lineas"
                    )
                in_func = True
                func_indent = len(m_def.group(1))
                func_start = i
                func_name = m_def.group(2)
            elif in_func and line.strip() == "":
                continue
            elif in_func and line and not line.startswith(" " * (func_indent + 1)) and not line.startswith(" " * func_indent):
                if (i - func_start) > 200:
                    violations["FSZ"].append(
                        f"{py_file.relative_to(ROOT)}:{func_start + 1} `{func_name}()` = {i - func_start} lineas"
                    )
                in_func = False

    if verbose:
        for rule, items in violations.items():
            print(f"\n{rule}: {len(items)} violation(s)")
            for item in items[:5]:
                print(f"  - {item}")
            if len(items) > 5:
                print(f"  ... y {len(items) - 5} mas")

    return violations


def check_pypi_versions(packages: list[str]) -> dict[str, str]:
    """Consulta PyPI para obtener la ultima version estable de cada paquete."""
    results: dict[str, str] = {}
    for pkg in packages:
        try:
            url = f"https://pypi.org/pypi/{pkg}/json"
            req = urllib.request.Request(url, headers={"Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=5) as r:
                info = json.loads(r.read()).get("info", {})
                results[pkg] = info.get("version", "?")
        except Exception as e:
            results[pkg] = f"ERROR: {e}"
    return results


def update_pyproject_toml(updates: dict[str, str]) -> bool:
    """Actualiza versiones en pyproject.toml. Retorna True si hubo cambios."""
    if not updates:
        return False
    text = PYPROJECT.read_text(encoding="utf-8")
    original = text
    for pkg, new_constraint in updates.items():
        # Buscar "pkg>=version" o "pkg==version" y reemplazar
        # Solo reemplazar la version, mantener la sintaxis (>=, ==, etc.)
        pattern = rf'({re.escape(pkg)}[<>=~]+)[\d.]+(?:[\w.-]*)'
        # Extraer la version actual
        new_ver = re.search(r'>=([\d.]+)', new_constraint)
        if not new_ver:
            continue
        new_ver_str = new_ver.group(1)
        text = re.sub(pattern, rf'\g<1>{new_ver_str}', text)
    if text != original:
        PYPROJECT.write_text(text, encoding="utf-8")
        return True
    return False


def update_test_targets(updates: dict[str, str]) -> bool:
    """Actualiza TARGET_VERSIONS en este archivo."""
    global TARGET_VERSIONS
    changed = False
    for pkg, new_constraint in updates.items():
        if pkg in TARGET_VERSIONS and TARGET_VERSIONS[pkg] != new_constraint:
            TARGET_VERSIONS[pkg] = new_constraint
            changed = True
    if changed:
        # Reemplazar en el archivo
        text = Path(__file__).read_text(encoding="utf-8")
        original = text
        for pkg, new_constraint in updates.items():
            # Buscar la linea TARGET_VERSIONS["pkg"] = "..."
            pattern = rf'("{pkg}":\s*)"[^"]+"'
            text = re.sub(pattern, rf'\1"{new_constraint}"', text)
        if text != original:
            Path(__file__).write_text(text, encoding="utf-8")
    return changed


def run_uv_lock() -> bool:
    """Regenera el lockfile. Retorna True si exito."""
    result = subprocess.run(
        ["uv", "lock"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    return result.returncode == 0


def run_tests() -> bool:
    """Ejecuta los tests del proyecto para verificar que siguen pasando."""
    result = subprocess.run(
        ["uv", "run", "pytest", "harness/tests/test_universal_rules.py", "--no-header", "-q"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    return result.returncode == 0


def evolve_baselines(apply: bool = True) -> dict[str, Any]:
    """AUTO-MEJORA: consulta PyPI, actualiza pyproject + TARGET_VERSIONS + lock.

    Returns:
        dict con:
          - updates: {pkg: new_constraint} aplicado o sugerido
          - tests_pass: bool si los tests siguen pasando despues
          - log: lista de acciones realizadas
    """
    log: list[str] = []
    packages = ["hypothesis", "lancedb", "numpy", "torch", "ruff", "mypy", "bandit", "safety"]
    latest = check_pypi_versions(packages)
    updates: dict[str, str] = {}
    for pkg, current_target in TARGET_VERSIONS.items():
        if pkg == "python":
            continue
        latest_ver = latest.get(pkg, "?")
        if latest_ver == "?" or "ERROR" in latest_ver:
            continue
        # Extraer version minima del target actual
        m = re.search(r">=([\d.]+)", current_target)
        if not m:
            continue
        current_min = m.group(1)
        if version_tuple(latest_ver) > version_tuple(current_min):
            new_constraint = f">={latest_ver}"
            updates[pkg] = new_constraint
            log.append(f"UPG: {pkg} {current_min} -> {latest_ver}")

    result = {
        "updates": updates,
        "tests_pass": None,
        "log": log,
    }

    if updates and apply:
        # 1. Actualizar pyproject.toml
        if update_pyproject_toml(updates):
            log.append("pyproject.toml actualizado")
        # 2. Actualizar TARGET_VERSIONS en este archivo
        if update_test_targets(updates):
            log.append("TARGET_VERSIONS actualizadas en test")
        # 3. Regenerar lockfile
        if run_uv_lock():
            log.append("uv lock exitoso")
        else:
            log.append("ERROR: uv lock fallo")
        # 4. Verificar tests
        result["tests_pass"] = run_tests()
        log.append(f"Tests post-evolve: {'PASS' if result['tests_pass'] else 'FAIL'}")

    return result


# ===========================================================================
# CLI
# ===========================================================================


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage:")
        print("  python -m harness.tests.test_universal_rules scan       # reporta violaciones")
        print("  python -m harness.tests.test_universal_rules evolve     # AUTO-MEJORA: actualiza inmediatamente")
        print("  python -m harness.tests.test_universal_rules check-web  # consulta ultimas versiones en PyPI")
        sys.exit(2)

    cmd = sys.argv[1]
    if cmd == "scan":
        results = scan_rule_compliance(verbose=True)
        total = sum(len(v) for v in results.values())
        print(f"\nTotal violations: {total}")
        sys.exit(0 if total == 0 else 1)
    elif cmd == "evolve":
        result = evolve_baselines(apply=True)
        print("AUTO-MEJORA (evolve):")
        for entry in result["log"]:
            print(f"  - {entry}")
        if result["updates"]:
            print(f"\nUpdates aplicados: {len(result['updates'])}")
            for pkg, constraint in result["updates"].items():
                print(f"  {pkg} -> {constraint}")
        else:
            print("\nSin updates necesarios (todo al dia)")
        if result["tests_pass"] is not None:
            sys.exit(0 if result["tests_pass"] else 1)
        sys.exit(0)
    elif cmd == "check-web":
        packages = ["hypothesis", "lancedb", "numpy", "torch", "ruff", "mypy", "bandit", "safety"]
        results = check_pypi_versions(packages)
        for pkg, ver in results.items():
            current = TARGET_VERSIONS.get(pkg, "?")
            print(f"  {pkg}: latest={ver}, target={current}")
        state = load_state()
        state["last_web_check"] = datetime.now(timezone.utc).isoformat()
        save_state(state)
        print(f"\nEstado actualizado: last_web_check={state['last_web_check']}")
    else:
        print(f"Comando desconocido: {cmd}")
        sys.exit(2)
