"""Tests para Architectural Guardrails — validacion de reglas en codigo."""
from __future__ import annotations
import pytest
from harness.orchestrator.architectural_guardrails import (
    check_type_hints, check_function_length, check_no_except_pass,
    check_forbidden_imports, check_all, builtin_guardrails,
)


class TestCheckTypeHints:
    def test_pasa_con_type_hints(self):
        """Funcion con type hints completos no debe generar violaciones."""
        codigo = """
def suma(a: int, b: int) -> int:
    return a + b
"""
        result = check_type_hints(codigo, "test.py")
        assert result.passed is True

    def test_falla_sin_type_hints(self):
        """Funcion sin type hints debe generar violacion."""
        codigo = "def suma(a, b):\n    return a + b"
        result = check_type_hints(codigo, "test.py")
        assert result.passed is False

    def test_salta_privados(self):
        """Metodos privados no deben requerir type hints."""
        codigo = "def _helper():\n    return 42"
        result = check_type_hints(codigo, "test.py")
        assert result.passed is True


class TestCheckFunctionLength:
    def test_pasa_funcion_corta(self):
        """Funcion dentro del limite no debe generar violacion."""
        codigo = "def foo():\n    pass\n"
        result = check_function_length(codigo, "test.py", max_lines=60)
        assert result.passed is True

    def test_falla_funcion_larga(self):
        """Funcion que excede el limite debe generar violacion."""
        lines = ["def foo():"] + ["    pass  # line"] * 70
        codigo = "\n".join(lines)
        result = check_function_length(codigo, "test.py", max_lines=60)
        assert result.passed is False


class TestCheckNoExceptPass:
    def test_detecta_except_pass(self):
        """except:pass sin logger debe ser detectado."""
        codigo = "try:\n    x = 1\nexcept:\n    pass\n"
        result = check_no_except_pass(codigo, "test.py")
        assert result.passed is False

    def test_pasa_con_logger(self):
        """except con logger no debe generar violacion."""
        codigo = 'try:\n    x = 1\nexcept Exception as e:\n    logger.warning("fallo: %s", e)\n'
        result = check_no_except_pass(codigo, "test.py")
        assert result.passed is True


class TestCheckForbiddenImports:
    def test_detecta_eval(self):
        """Uso de eval() debe ser detectado."""
        codigo = 'x = eval("1+1")'
        result = check_forbidden_imports(codigo, "test.py")
        assert result.passed is False

    def test_pasa_sin_prohibidos(self):
        """Codigo limpio no debe generar violaciones."""
        codigo = "x = 1 + 1"
        result = check_forbidden_imports(codigo, "test.py")
        assert result.passed is True


class TestCheckAll:
    def test_check_all_ejecuta_todos(self):
        """check_all debe ejecutar todos los guardrails."""
        codigo_bueno = """
def suma(a: int, b: int) -> int:
    return a + b
"""
        result = check_all(codigo_bueno, "test.py")
        assert result.checked_rules >= 4  # 4 guardrails builtin

    def test_check_all_acumula_violaciones(self):
        """check_all debe acumular violaciones de todos los guardrails."""
        codigo_malo = """
def suma(a, b):
    return eval("a + b")
"""
        result = check_all(codigo_malo, "test.py")
        assert len(result.violations) >= 2  # type_hints + eval

    def test_builtin_guardrails_tiene_4(self):
        """builtin_guardrails debe retornar 4 funciones."""
        guards = builtin_guardrails()
        assert len(guards) == 4
