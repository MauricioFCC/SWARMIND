"""Tests para ContextInjector — inyeccion de estandares + validate_docstrings."""
from __future__ import annotations
import pytest


class TestContextInjector:
    """Verifica inyeccion de estandares y validacion de docstrings."""

    def test_inject_contains_doc_es_oblig(self, context_injector):
        """La inyeccion debe contener !DOC_ES_OBLIG! como primer token."""
        injected = context_injector.inject("implementar modulo X", "builder")
        assert "!DOC_ES_OBLIG!" in injected, (
            "La inyeccion no contiene el marcador !DOC_ES_OBLIG!"
        )
        # Debe aparecer ANTES que CleanCode (es el primer token)
        doc_pos = injected.index("!DOC_ES_OBLIG!")
        cc_pos = injected.index("CleanCode")
        assert doc_pos < cc_pos, (
            "!DOC_ES_OBLIG! debe ir ANTES que CleanCode"
        )

    def test_inject_contains_err_action(self, context_injector):
        """La inyeccion debe contener !ERR_ACTION! como segundo token."""
        injected = context_injector.inject("analizar datos", "scientist")
        assert "!ERR_ACTION!" in injected, (
            "La inyeccion no contiene el marcador !ERR_ACTION!"
        )

    def test_inject_all_agents_have_directives(self, context_injector):
        """Todos los roles deben tener !DOC_ES_OBLIG! y !ERR_ACTION!."""
        for role in ["builder", "scientist", "guardian", "coordinator", "evolve"]:
            injected = context_injector.inject("test", role)
            assert "!DOC_ES_OBLIG!" in injected, f"Rol {role} sin !DOC_ES_OBLIG!"
            assert "!ERR_ACTION!" in injected, f"Rol {role} sin !ERR_ACTION!"

    def test_validate_docstrings_detecta_faltantes(self, context_injector):
        """validate_docstrings debe detectar funciones sin docstring."""
        codigo_mal = """
def funcion_sin_doc():
    pass

class ClaseSinDoc:
    def metodo_sin_doc(self):
        pass
"""
        faltantes = context_injector.validate_docstrings(codigo_mal, "test.py")
        assert len(faltantes) >= 2, f"Deberia detectar al menos 2 faltantes: {faltantes}"
        # Debe mencionar las funciones sin docstring
        nombres = " ".join(faltantes)
        assert "funcion_sin_doc" in nombres, "No detecto funcion_sin_doc"
        assert "ClaseSinDoc" in nombres, "No detecto ClaseSinDoc"

    def test_validate_docstrings_pasa_codigo_bueno(self, context_injector):
        """validate_docstrings no debe reportar codigo con docstrings completos."""
        codigo_bueno = """
def funcion_con_doc(param1: str, param2: int) -> bool:
    '''Descripcion breve.

    Args:
        param1: Descripcion del primer parametro.
        param2: Descripcion del segundo parametro.

    Returns:
        Descripcion del valor de retorno.
    '''
    return True

class ClaseConDoc:
    '''Descripcion de la clase.'''

    def metodo_con_doc(self) -> str:
        '''Descripcion del metodo.

        Returns:
            Un string de resultado.
        '''
        return "ok"
"""
        faltantes = context_injector.validate_docstrings(codigo_bueno, "test_bueno.py")
        assert len(faltantes) == 0, f"No deberia haber faltantes: {faltantes}"

    def test_validate_docstrings_detecta_incompletos(self, context_injector):
        """validate_docstrings debe detectar docstrings sin Args/Returns."""
        codigo_incompleto = """
def funcion_incompleta(x: int) -> str:
    '''Solo texto sin Args ni Returns.'''
    return str(x)
"""
        faltantes = context_injector.validate_docstrings(codigo_incompleto, "test_incompleto.py")
        assert len(faltantes) >= 1, (
            f"Deberia detectar docstring incompleto: {faltantes}"
        )
        assert "INCOMPLETO" in faltantes[0] or "incompleto" in faltantes[0].lower(), (
            f"Deberia marcar como incompleto: {faltantes[0]}"
        )

    def test_validate_docstrings_salta_privados(self, context_injector):
        """validate_docstrings no debe quejarse de métodos privados (_) ni dunder (__)."""
        codigo = """
class MiClase:
    '''Clase con docstring.'''

    def _privado(self):
        pass

    def __dunder_method__(self):
        pass
"""
        faltantes = context_injector.validate_docstrings(codigo, "test_priv.py")
        # Los métodos privados y dunder no deben reportarse
        assert len(faltantes) == 0, f"No deberia reportar privados: {faltantes}"

    def test_validate_docstrings_syntax_error(self, context_injector):
        """validate_docstrings debe manejar codigo con errores de sintaxis."""
        codigo_roto = "def foo( bar )"
        faltantes = context_injector.validate_docstrings(codigo_roto, "test_roto.py")
        assert len(faltantes) >= 1
        assert "SyntaxError" in faltantes[0] or "parsear" in faltantes[0].lower()

    def test_get_reminder_formato_correcto(self, context_injector):
        """get_reminder debe devolver formato [F]... con los tokens esperados."""
        for role in ["builder", "scientist", "guardian", "coordinator", "evolve"]:
            reminder = context_injector.get_reminder(role)
            assert reminder.startswith("[F]"), f"Reminder para {role} no empieza con [F]"
            assert len(reminder) > 10, f"Reminder para {role} demasiado corto"

    def test_inject_no_duplica_si_ya_presente(self, context_injector):
        """inject no debe duplicar el reminder si la descripcion ya lo contiene."""
        reminder = context_injector.get_reminder("builder")
        descripcion = f"{reminder} | hacer tarea X"
        resultado = context_injector.inject(descripcion, "builder")
        # No debe agregar otro reminder encima
        assert resultado == descripcion, "No deberia duplicar el reminder"
