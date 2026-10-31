"""Tests de `scripts/verify_global_sync.py` (comparación por hash)."""

from __future__ import annotations

from scripts import verify_global_sync as verify


class TestCompareTree:
    """Comparación fuente -> global."""

    def test_identical_tree_is_clean(self, tmp_path):
        """Archivos idénticos no generan faltantes ni divergencias."""
        source = tmp_path / "src"
        target = tmp_path / "dst"
        source.mkdir()
        target.mkdir()
        (source / "a.py").write_text("x = 1\n", encoding="utf-8")
        (target / "a.py").write_text("x = 1\n", encoding="utf-8")
        assert verify.compare_tree(source, target) == ([], [])

    def test_missing_file(self, tmp_path):
        """Un archivo no copiado se reporta como faltante."""
        source = tmp_path / "src"
        target = tmp_path / "dst"
        source.mkdir()
        target.mkdir()
        (source / "a.py").write_text("x = 1\n", encoding="utf-8")
        assert verify.compare_tree(source, target, prefix="harness/") == (
            ["harness/a.py"],
            [],
        )

    def test_diverged_file(self, tmp_path):
        """Mismo nombre, contenido distinto: drift."""
        source = tmp_path / "src"
        target = tmp_path / "dst"
        source.mkdir()
        target.mkdir()
        (source / "a.py").write_text("x = 1\n", encoding="utf-8")
        (target / "a.py").write_text("x = 2\n", encoding="utf-8")
        assert verify.compare_tree(source, target) == ([], ["a.py"])

    def test_pycache_and_pyc_are_ignored(self, tmp_path):
        """Cachés de Python no cuentan como drift."""
        source = tmp_path / "src"
        target = tmp_path / "dst"
        (source / "__pycache__").mkdir(parents=True)
        target.mkdir()
        (source / "__pycache__" / "a.pyc").write_bytes(b"x")
        (source / "b.pyc").write_bytes(b"x")
        assert verify.compare_tree(source, target) == ([], [])


class TestMain:
    """Exit code según el resultado de la verificación."""

    def test_clean_returns_0(self, monkeypatch, capsys):
        """Sin drift el comando sale 0 y lo reporta."""
        monkeypatch.setattr(verify, "verify", lambda: {"missing": [], "diverged": []})
        assert verify.main([]) == 0
        assert "SINCRONIZADO" in capsys.readouterr().out

    def test_drift_returns_1(self, monkeypatch, capsys):
        """Con faltantes el comando sale 1 y lista el archivo."""
        monkeypatch.setattr(
            verify, "verify", lambda: {"missing": ["harness/x.py"], "diverged": []}
        )
        assert verify.main([]) == 1
        assert "FALTA  harness/x.py" in capsys.readouterr().out

    def test_quiet_suppresses_detail(self, monkeypatch, capsys):
        """--quiet no imprime detalle (solo exit code)."""
        monkeypatch.setattr(
            verify, "verify", lambda: {"missing": ["x"], "diverged": []}
        )
        assert verify.main(["--quiet"]) == 1
        assert capsys.readouterr().out == ""
