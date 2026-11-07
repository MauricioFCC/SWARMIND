"""Tests de la allowlist de reglas Ruff preview."""

from __future__ import annotations

import re

from scripts import check_ruff_preview as preview


class TestAllowlist:
    """La allowlist debe ser estable y explicita."""

    def test_codes_are_unique(self):
        """Sin duplicados: cada regla se enuncia una vez."""
        assert len(preview.ALLOWLIST) == len(set(preview.ALLOWLIST))

    def test_codes_have_ruff_format(self):
        """Los codigos siguen el patron letra+digitos de Ruff."""
        assert all(re.fullmatch(r"[A-Z]{2,5}\d{3}", code) for code in preview.ALLOWLIST)

    def test_targets_are_repo_paths(self):
        """El gate analiza harness y scripts (mismo alcance que el lint)."""
        assert set(preview.TARGETS) == {"harness", "scripts"}


class TestFailures:
    """Formato de los mensajes de regresion."""

    def test_empty_findings(self):
        """Sin hallazgos no hay mensajes."""
        assert preview.failures([]) == []

    def test_maps_location_and_code(self):
        """Un hallazgo se reporta como archivo:linea codigo mensaje."""
        findings = [
            {
                "code": "FURB101",
                "filename": "harness/x.py",
                "location": {"row": 7, "column": 1},
                "message": "usa Path.read_text",
            }
        ]
        assert preview.failures(findings) == [
            "harness/x.py:7 FURB101 usa Path.read_text"
        ]

    def test_missing_fields_do_not_crash(self):
        """Un hallazgo incompleto se reporta con placeholders."""
        assert preview.failures([{}]) == ["?:? SIN_CODIGO "]
