"""Tests TDD del RepoMap con budget (repo-level understanding).

Mapa `clase/funciones` rankeado por menciones, cortado por presupuesto de
tokens, determinista y sin dependencias.
"""

from __future__ import annotations

from harness.context.repomap import RepoMapStats, build_repomap, extract_symbols


def _write(path, name: str, content: str) -> None:
    """Escribe un .py en el repo fixture."""
    (path / name).write_text(content, encoding="utf-8")


def test_extract_class_and_functions(tmp_path) -> None:
    """Extrae clase, metodos y funciones con firmas."""
    target = tmp_path / "mod.py"
    target.write_text(
        "class Greeter:\n"
        "    def hello(self, name: str) -> str:\n"
        "        return name\n"
        "\n"
        "\n"
        "def add(a: int, b: int) -> int:\n"
        "    return a + b\n",
        encoding="utf-8",
    )
    symbols = {(s.kind, s.name) for s in extract_symbols(target)}
    assert ("class", "Greeter") in symbols
    assert ("def", "hello") in symbols
    assert ("def", "add") in symbols
    sigs = {s.name: s.signature for s in extract_symbols(target)}
    assert "name" in sigs["hello"]


def test_syntax_error_does_not_break_map(tmp_path) -> None:
    """Archivo con sintaxis rota se omite sin tumbar el mapa."""
    _write(tmp_path, "good.py", "def ok() -> int:\n    return 1\n")
    _write(tmp_path, "broken.py", "def broken(:\n  ???\n")
    repomap = build_repomap(tmp_path, budget_tokens=1000)
    assert "ok" in repomap.text
    assert "broken" not in repomap.text


def test_budget_cuts_by_rank_and_reports(tmp_path) -> None:
    """El budget corta por ranking y las stats lo reflejan."""
    for i in range(6):
        _write(tmp_path, f"mod{i}.py", f"def func{i}(x: int) -> int:\n    return x\n")
    # mod0 es el mas mencionado -> debe sobrevivir a un budget minimo.
    _write(tmp_path, "user.py", "import mod0\n" * 20)
    full = build_repomap(tmp_path, budget_tokens=10_000)
    tiny = build_repomap(tmp_path, budget_tokens=30)
    assert isinstance(full.stats, RepoMapStats)
    assert tiny.stats.kept < full.stats.symbols
    assert "mod0" in tiny.text


def test_deterministic_output(tmp_path) -> None:
    """Mismo input -> mismo output."""
    _write(tmp_path, "a.py", "def f1() -> None:\n    pass\n")
    _write(tmp_path, "b.py", "class C:\n    pass\n")
    first = build_repomap(tmp_path, budget_tokens=500)
    second = build_repomap(tmp_path, budget_tokens=500)
    assert first.text == second.text


def test_excludes_tests_by_default(tmp_path) -> None:
    """Sin include_tests, test_*.py y tests/ quedan fuera."""
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    _write(tests_dir, "test_x.py", "def test_y() -> None:\n    pass\n")
    _write(tmp_path, "real.py", "def real_fn() -> None:\n    pass\n")
    repomap = build_repomap(tmp_path, budget_tokens=1000)
    assert "real_fn" in repomap.text
    assert "test_y" not in repomap.text


def test_empty_repo_gives_empty_map(tmp_path) -> None:
    """Repo vacio o budget 0 -> mapa vacio con stats coherentes."""
    repomap = build_repomap(tmp_path, budget_tokens=1000)
    assert repomap.text == ""
    assert repomap.stats.symbols == 0
    assert build_repomap(tmp_path, budget_tokens=0).text == ""


def test_skip_dirs_excluded(tmp_path) -> None:
    """Directorios de ruido (.git, .venv, __pycache__) nunca entran al mapa."""
    for noise in (".git", ".venv", "__pycache__"):
        noise_dir = tmp_path / noise
        noise_dir.mkdir()
        _write(noise_dir, "hidden.py", "def hidden_fn() -> None:\n    pass\n")
    _write(tmp_path, "real.py", "def real_fn() -> None:\n    pass\n")
    repomap = build_repomap(tmp_path, budget_tokens=1000)
    assert "real_fn" in repomap.text
    assert "hidden_fn" not in repomap.text


def test_include_tests_flag(tmp_path) -> None:
    """include_tests=True incorpora los tests al mapa."""
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    _write(tests_dir, "test_x.py", "def test_y() -> None:\n    pass\n")
    _write(tmp_path, "real.py", "def real_fn() -> None:\n    pass\n")
    repomap = build_repomap(tmp_path, budget_tokens=1000, include_tests=True)
    assert "test_y" in repomap.text


def test_extract_symbols_accepts_preloaded_text(tmp_path) -> None:
    """Pasar `text` evita releer y produce los mismos simbolos."""
    target = tmp_path / "m.py"
    source = "def pre(x: int) -> int:\n    return x\n"
    target.write_text(source, encoding="utf-8")
    assert extract_symbols(target, "m.py", text=source) == extract_symbols(target, "m.py")
