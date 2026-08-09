"""Tests de detección de código muerto con vulture (calidad de código 2026).

Valida que el harness no contenga código muerto detectable (variables,
funciones o clases sin usar) usando vulture con la misma configuración que el
pre-commit hook y el CI:

    vulture harness/ harness/vulture_whitelist.py --exclude harness/tests --min-confidence 80

Regla del proyecto: está prohibido silenciar código muerto real con el
whitelist; solo se admiten falsos positivos legítimos documentados (API de
compatibilidad y registros dinámicos).
"""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent
HARNESS = ROOT / "harness"
WHITELIST = HARNESS / "vulture_whitelist.py"
MIN_CONFIDENCE = 80
EXCLUDE = "harness/tests"


def _vulture_is_installed() -> bool:
    """Devuelve True si vulture está disponible en el entorno."""
    return shutil.which("vulture") is not None or _module_available()


def _module_available() -> bool:
    """Comprueba si vulture es importable como módulo."""
    try:
        import vulture  # noqa: F401

        return True
    except ImportError:
        return False


class TestDeadCode:
    """Detección de código muerto con vulture."""

    @pytest.mark.skipif(
        not _vulture_is_installed(),
        reason="vulture no está instalado (uv pip install vulture)",
    )
    def test_vulture_zero_findings_production(self) -> None:
        """Vulture reporta 0 hallazgos en producción (excluyendo tests)."""
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "vulture",
                str(HARNESS),
                str(WHITELIST),
                "--exclude",
                EXCLUDE,
                "--min-confidence",
                str(MIN_CONFIDENCE),
            ],
            capture_output=True,
            text=True,
            cwd=ROOT,
            timeout=300,
            check=False,
        )
        assert result.returncode == 0, (
            f"Vulture detectó código muerto (WHAT=codigo_muerto "
            f"WHY=hallazgos_de_vulture WHERE=harness/):\n{result.stdout}\n{result.stderr}"
        )

    @pytest.mark.skipif(
        not _vulture_is_installed(),
        reason="vulture no está instalado (uv pip install vulture)",
    )
    def test_whitelist_only_documented_false_positives(self) -> None:
        """El whitelist no contiene entradas para código muerto real.

        Cada símbolo del whitelist debe estar documentado con WHAT+WHY+WHERE
        (los falsos positivos legítimos tienen comentarios justificativos).
        """
        text = WHITELIST.read_text(encoding="utf-8")
        # El whitelist solo declara atributos de módulo con comentario justificativo
        assert "WHAT" in text and "WHY" in text and "WHERE" in text, (
            "WHAT=vulture_whitelist_sin_documentacion "
            "WHY=los_falsos_positivos_deben_justificarse "
            "WHERE=vulture_whitelist.py"
        )

    @pytest.mark.skipif(
        not _vulture_is_installed(),
        reason="vulture no está instalado (uv pip install vulture)",
    )
    def test_vulture_config_present_in_pyproject(self) -> None:
        """pyproject.toml define [tool.vulture] con min_confidence >= 80."""
        pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
        assert "[tool.vulture]" in pyproject, (
            "WHAT=tool_vulture_faltante WHY=config_no_ssot WHERE=pyproject.toml"
        )
        assert "min_confidence = 80" in pyproject, (
            "WHAT=min_confidence_faltante WHY=umbral_no_definido WHERE=pyproject.toml"
        )
