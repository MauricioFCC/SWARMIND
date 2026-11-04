"""Contrato del instalador Python (alternativa a los .ps1 bloqueados por policy).

WHAT: ``scripts/install.py`` debe existir, ejecutar ``--dry-run`` sin efectos y
cubrir los 6 pasos del instalador PowerShell. ``--help`` debe documentar
``--dry-run``.

WHY: en Windows la política de ejecución bloquea los ``.ps1``; el instalador
Python permite `python scripts/install.py` sin cambiar la policy.

WHERE: ``harness/tests`` — verifica el script de instalación del repo.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
INSTALLER = ROOT / "scripts" / "install.py"


def _run(*args: str) -> subprocess.CompletedProcess[str]:
    """Ejecuta el instalador con el intérprete actual y captura salida."""
    return subprocess.run(
        [sys.executable, str(INSTALLER), *args],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )


def test_installer_existe() -> None:
    """El instalador Python está versionado junto al .ps1/.sh y no invoca pwsh."""
    assert INSTALLER.is_file()
    text = INSTALLER.read_text(encoding="utf-8")
    assert "ExecutionPolicy" not in text
    assert "pwsh" not in text.lower()


def test_dry_run_no_falla_y_cubre_los_seis_pasos() -> None:
    """`--dry-run` termina en 0 y anuncia los 6 pasos del instalador."""
    result = _run("--dry-run")
    assert result.returncode == 0, result.stderr
    assert "INSTALACION FALLIDA" not in result.stdout
    for step in range(1, 7):
        assert f"[{step}/6]" in result.stdout


def test_help_documenta_dry_run() -> None:
    """`--help` expone `--dry-run` (descubrible sin leer el código)."""
    result = _run("--help")
    assert result.returncode == 0
    assert "--dry-run" in result.stdout
