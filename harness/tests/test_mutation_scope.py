"""Tests del scoping de mutación por diff y umbrales por paquete."""

from __future__ import annotations

import json

import pytest

from scripts import mutation_scope as scope_mod


class TestPackageMapping:
    """Selección de paquete y umbral."""

    @pytest.mark.parametrize(
        ("path", "package"),
        [
            ("harness/kernel/loop.py", "harness/kernel"),
            ("harness/domain/ports.py", "harness/domain"),
            ("harness/memory_rag/ruscadb_store.py", "harness/memory_rag"),
            ("harness/orchestrator/agent_bus/core.py", "harness"),
        ],
    )
    def test_package_for_uses_most_specific_prefix(self, path, package):
        """El prefijo más específico gana (sin confundir memory_rag con harness)."""
        assert scope_mod.package_for(path) == package

    @pytest.mark.parametrize(
        ("package", "expected"),
        [
            ("harness/kernel", 0.90),
            ("harness/domain", 0.75),
            ("harness/memory_rag", 0.70),
            ("harness", 0.40),
        ],
    )
    def test_thresholds_by_package(self, package, expected):
        """Kernel exige más que adapters; el default es 40 %."""
        assert scope_mod.threshold_for(package) == pytest.approx(expected)


class TestMutableFiles:
    """Filtro de archivos mutables."""

    def test_only_harness_python_outside_tests(self):
        """Solo .py de harness fuera de tests."""
        assert scope_mod.is_mutable("harness/kernel/loop.py")
        assert not scope_mod.is_mutable("harness/tests/test_kernel.py")
        assert not scope_mod.is_mutable("scripts/check.py")
        assert not scope_mod.is_mutable("docs/specs/x.md")
        assert not scope_mod.is_mutable("harness/data.json")

    def test_windows_separators_are_normalized(self):
        """Rutas con backslash se normalizan."""
        assert scope_mod.is_mutable("harness\\kernel\\loop.py")
        assert scope_mod.package_for("harness\\kernel\\loop.py") == "harness/kernel"


class TestFindTests:
    """Mapeo fuente -> tests por nombre o import."""

    def test_direct_name_and_import_matches(self, tmp_path):
        """Un test homónimo y otro que importa el módulo se incluyen."""
        tests_root = tmp_path / "harness" / "tests"
        tests_root.mkdir(parents=True)
        (tests_root / "test_loop.py").write_text("def test_x(): pass\n", encoding="utf-8")
        (tests_root / "test_extra.py").write_text(
            "from harness.kernel.loop import KernelLoop\n", encoding="utf-8"
        )
        (tests_root / "test_other.py").write_text("x = 1\n", encoding="utf-8")

        found = scope_mod.find_tests(
            "harness/kernel/loop.py", tests_root, root=tmp_path
        )

        assert found == ["harness/tests/test_extra.py", "harness/tests/test_loop.py"]

    def test_no_tests_returns_empty(self, tmp_path):
        """Sin coincidencias devuelve lista vacía (no rompe)."""
        tests_root = tmp_path / "harness" / "tests"
        tests_root.mkdir(parents=True)
        assert scope_mod.find_tests("harness/kernel/x.py", tests_root, root=tmp_path) == []


class TestBuildScope:
    """Agrupación por paquete con tests deduplicados."""

    def test_groups_and_dedupes_tests(self, tmp_path):
        """Dos fuentes del mismo paquete comparten tests sin duplicarlos."""
        tests_root = tmp_path / "harness" / "tests"
        tests_root.mkdir(parents=True)
        (tests_root / "test_a.py").write_text(
            "from harness.kernel.a import A\nfrom harness.kernel.b import B\n",
            encoding="utf-8",
        )
        scope = scope_mod.build_scope(
            ["harness/kernel/a.py", "harness/kernel/b.py"],
            tests_root,
            root=tmp_path,
        )
        assert scope["harness/kernel"]["sources"] == [
            "harness/kernel/a.py",
            "harness/kernel/b.py",
        ]
        assert scope["harness/kernel"]["tests"] == ["harness/tests/test_a.py"]


class TestConfig:
    """Config de mutmut 3.x generada."""

    def test_render_config_has_required_keys(self):
        """Incluye source_paths, only_mutate y la selección de tests."""
        text = scope_mod.render_config(
            ["harness/kernel/loop.py"], ["harness/tests/test_loop.py"]
        )
        assert "[mutmut]" in text
        assert "source_paths =" in text
        assert "harness/kernel/loop.py" in text
        assert "pytest_add_cli_args_test_selection =" in text
        assert "harness/tests/test_loop.py" in text

    def test_write_config_roundtrip(self, tmp_path):
        """El archivo escrito contiene las fuentes del scope."""
        target = tmp_path / "setup.cfg"
        scope_mod.write_config(
            target,
            {"sources": ["harness/kernel/x.py"], "tests": ["harness/tests/test_x.py"]},
        )
        assert "harness/kernel/x.py" in target.read_text(encoding="utf-8")


class TestScores:
    """Cálculo y evaluación del mutation score."""

    def test_score_formula_excludes_no_tests_and_skipped(self):
        """killed / (total - no_tests - skipped)."""
        stats = {"total": 10, "killed": 6, "no_tests": 2, "skipped": 0}
        assert scope_mod.score_from_stats(stats) == pytest.approx(0.75)

    def test_no_evaluable_mutants_returns_none(self):
        """Denominador cero no es un score (no se puede gatear)."""
        stats = {"total": 3, "killed": 0, "no_tests": 3, "skipped": 0}
        assert scope_mod.score_from_stats(stats) is None

    def test_evaluate_uses_package_threshold(self):
        """Kernel al 85 % falla (umbral 90 %); memory_rag al 85 % pasa."""
        scope = {
            "harness/kernel": {"sources": ["a"], "tests": []},
            "harness/memory_rag": {"sources": ["b"], "tests": []},
        }
        failures = scope_mod.evaluate(
            scope, {"harness/kernel": 0.85, "harness/memory_rag": 0.85}
        )
        assert failures == ["harness/kernel: mutation score 85.0% < 90%"]

    def test_evaluate_skips_none_scores(self):
        """Sin mutantes evaluables no se inventa un fallo."""
        scope = {"harness/kernel": {"sources": ["a"], "tests": []}}
        assert scope_mod.evaluate(scope, {"harness/kernel": None}) == []


class TestAllCore:
    """Modo nocturno: selección sin diff de kernel+domain."""

    def test_lists_kernel_and_domain_files(self):
        """Devuelve al menos loop.py y ports.py, todos bajo core."""
        files = scope_mod.files_for_packages()
        assert "harness/kernel/loop.py" in files
        assert "harness/domain/ports.py" in files
        assert all(
            name.startswith(("harness/kernel/", "harness/domain/")) for name in files
        )

    def test_missing_package_is_ignored(self, tmp_path):
        """Un paquete inexistente devuelve lista vacía (no rompe)."""
        assert scope_mod.files_for_packages(("harness/nope",), root=tmp_path) == []


class TestCheckStatsCli:
    """Modo `--check-stats` (usado en CI para depurar)."""

    def test_below_threshold_exits_1(self, tmp_path, capsys):
        """Un stats por debajo del umbral del paquete devuelve 1."""
        stats = tmp_path / "stats.json"
        stats.write_text(
            json.dumps({"total": 10, "killed": 5, "no_tests": 0, "skipped": 0}),
            encoding="utf-8",
        )
        code = scope_mod.main(
            ["--check-stats", str(stats), "--package", "harness/kernel"]
        )
        assert code == 1
        assert "FAIL" in capsys.readouterr().err

    def test_above_threshold_exits_0(self, tmp_path):
        """Un stats que cumple el umbral devuelve 0."""
        stats = tmp_path / "stats.json"
        stats.write_text(
            json.dumps({"total": 10, "killed": 9, "no_tests": 0, "skipped": 0}),
            encoding="utf-8",
        )
        assert (
            scope_mod.main(["--check-stats", str(stats), "--package", "harness/kernel"])
            == 0
        )
