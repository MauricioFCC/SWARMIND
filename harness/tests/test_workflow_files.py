"""Gate de workflows de GitHub Actions (claves invalidas a nivel de paso).

Reproduce el error de GitHub ``Invalid workflow file: ... Unexpected value
'path'`` que fallaba en ``release.yml`` sin dejar check-runs (invisible para
los required checks).
"""

from __future__ import annotations

from pathlib import Path

from scripts.check_workflows import check_workflow, default_paths

VALID_WORKFLOW = """name: ok
on: push
jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v7
      - name: run
        run: echo hi
        with: {}
"""

INVALID_WORKFLOW = """name: bad
on: push
jobs:
  release:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/download-artifact@v4
        with:
          name: dist
        path: dist/
"""


def test_repos_workflows_are_valid() -> None:
    """Ningun workflow del repo tiene claves invalidas a nivel de paso."""
    paths = default_paths()
    assert paths, "no se encontraron workflows en .github/workflows"
    findings = [item for path in paths for item in check_workflow(path)]
    assert findings == [], f"workflows invalidos: {findings}"


def test_invalid_step_key_is_reported(tmp_path: Path) -> None:
    """Un ``path`` fuera de ``with:`` se reporta (el bug original de release)."""
    path = tmp_path / "bad.yml"
    path.write_text(INVALID_WORKFLOW, encoding="utf-8")
    findings = check_workflow(path)
    assert any("clave invalida 'path'" in item for item in findings), findings


def test_valid_step_keys_are_accepted(tmp_path: Path) -> None:
    """Claves legitimas de job/paso (``steps``, ``environment``) no reportan."""
    path = tmp_path / "ok.yml"
    path.write_text(VALID_WORKFLOW, encoding="utf-8")
    assert check_workflow(path) == []


def test_unreadable_file_is_reported_not_raised(tmp_path: Path) -> None:
    """Un archivo no UTF-8 se reporta como hallazgo, no propaga excepcion."""
    path = tmp_path / "binary.yml"
    path.write_bytes(b"\xff\xfe\x00\x00")
    findings = check_workflow(path)
    assert findings and "UTF-8" in findings[0]
