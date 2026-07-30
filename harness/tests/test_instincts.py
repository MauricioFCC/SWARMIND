"""Tests para el sistema de instintos (InstinctSystem).

Cubre: creacion, aprendizaje, evocacion, estadisticas y casos borde.
Sigue los principios de TDAD con Property-Based Testing donde aplica.
"""
from __future__ import annotations

from unittest.mock import patch

import pytest

from harness.orchestrator.instincts import Instinct, InstinctSystem

# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def instinct_system() -> InstinctSystem:
    """Fixture que provee un InstinctSystem vacio para cada test."""
    return InstinctSystem()


@pytest.fixture
def populated_system(instinct_system: InstinctSystem) -> InstinctSystem:
    """Fixture con instintos pre-cargados para tests de integracion."""
    system = instinct_system
    system.learn("cache_hit", "cache", "usar cache compartida", "optimizacion")
    system.learn("error_retry", "timeout", "reintentar con backoff", "resiliencia")
    system.learn("security_check", "vulnerabilidad", "escanear dependencias", "seguridad")
    return system


# ============================================================================
# Test 1: Creacion de InstinctSystem vacio
# ============================================================================


class TestInstinctSystemCreation:
    """Tests de creacion del sistema de instintos."""

    def test_empty_system(self, instinct_system: InstinctSystem) -> None:
        """Verifica que un sistema recien creado esta vacio.

        Args:
            instinct_system: InstinctSystem vacio provisto por fixture.

        Returns:
            None. Asserts que el sistema esta vacio.
        """
        assert len(instinct_system) == 0
        stats = instinct_system.get_stats()
        assert stats["total_instincts"] == 0
        assert stats["total_uses"] == 0

    def test_repr_empty(self, instinct_system: InstinctSystem) -> None:
        """Verifica representacion de sistema vacio.

        Args:
            instinct_system: InstinctSystem vacio.

        Returns:
            None. Asserts que __repr__ es correcto.
        """
        assert repr(instinct_system) == "InstinctSystem(0 instintos)"


# ============================================================================
# Test 2: Aprender nuevos instintos
# ============================================================================


class TestLearnInstincts:
    """Tests de aprendizaje de nuevos instintos."""

    def test_learn_simple(self, instinct_system: InstinctSystem) -> None:
        """Aprende un instinto basico y verifica su estructura.

        Args:
            instinct_system: Sistema vacio.

        Returns:
            None. Asserts que el instinto se creo correctamente.
        """
        instinto = instinct_system.learn(
            "test_instinct",
            "trigger_word",
            "do something",
            "test_context",
        )
        assert isinstance(instinto, Instinct)
        assert instinto.name == "test_instinct"
        assert instinto.trigger_pattern == "trigger_word"
        assert instinto.action == "do something"
        assert instinto.context == "test_context"
        assert instinto.success_rate == 0.0
        assert instinto.times_used == 0
        assert len(instinct_system) == 1

    def test_learn_multiple(self, instinct_system: InstinctSystem) -> None:
        """Aprende multiples instintos y verifica el conteo.

        Args:
            instinct_system: Sistema vacio.

        Returns:
            None. Asserts que todos los instintos se registran.
        """
        nombres = ["a", "b", "c", "d", "e"]
        for n in nombres:
            instinct_system.learn(n, f"pattern_{n}", f"action_{n}", "test")
        assert len(instinct_system) == len(nombres)
        stats = instinct_system.get_stats()
        assert stats["total_instincts"] == len(nombres)

    def test_learn_idempotent(self, instinct_system: InstinctSystem) -> None:
        """Verifica que aprender el mismo instinto dos veces es idempotente.

        Args:
            instinct_system: Sistema vacio.

        Returns:
            None. Asserts que no hay duplicados.
        """
        i1 = instinct_system.learn("dup", "pattern", "action", "ctx")
        i2 = instinct_system.learn("dup", "pattern2", "action2", "ctx2")
        assert i1 is i2  # mismo objeto
        assert len(instinct_system) == 1
        assert i2.trigger_pattern == "pattern"  # mantiene el original

    def test_learn_empty_name_raises(self, instinct_system: InstinctSystem) -> None:
        """Verifica que nombre vacio lanza ValueError.

        Args:
            instinct_system: Sistema vacio.

        Returns:
            None. Asserts que se lanza ValueError.
        """
        with pytest.raises(ValueError, match="nombre del instinto no puede estar vacio"):
            instinct_system.learn("", "pattern", "action")

    def test_learn_empty_pattern_raises(self, instinct_system: InstinctSystem) -> None:
        """Verifica que patron vacio lanza ValueError.

        Args:
            instinct_system: Sistema vacio.

        Returns:
            None. Asserts que se lanza ValueError.
        """
        with pytest.raises(ValueError, match="patron de activacion no puede estar vacio"):
            instinct_system.learn("test", "", "action")


# ============================================================================
# Test 3: Evocar (recall) instintos por contexto
# ============================================================================


class TestRecallInstincts:
    """Tests de evocacion de instintos por matching de contexto."""

    def test_recall_exact_match(self, populated_system: InstinctSystem) -> None:
        """Evoca un instinto por coincidencia exacta del patron.

        Args:
            populated_system: Sistema con instintos pre-cargados.

        Returns:
            None. Asserts que el instinto correcto es evocado.
        """
        instinto = populated_system.recall("usar cache para mejorar rendimiento")
        assert instinto is not None
        assert instinto.name == "cache_hit"

    def test_recall_case_insensitive(self, populated_system: InstinctSystem) -> None:
        """Verifica que la evocacion es case-insensitive.

        Args:
            populated_system: Sistema con instintos pre-cargados.

        Returns:
            None. Asserts que el matching ignora mayusculas/minusculas.
        """
        instinto = populated_system.recall("TIMEOUT en la conexion")
        assert instinto is not None
        assert instinto.name == "error_retry"

    def test_recall_partial_match(self, populated_system: InstinctSystem) -> None:
        """Evoca instinto con coincidencia parcial del patron en el contexto.

        Args:
            populated_system: Sistema con instintos pre-cargados.

        Returns:
            None. Asserts que funciona con substring.
        """
        instinto = populated_system.recall(
            "se detecto una vulnerabilidad critica en la libreria",
        )
        assert instinto is not None
        assert instinto.name == "security_check"

    def test_recall_no_match(self, populated_system: InstinctSystem) -> None:
        """Contexto sin coincidencias debe retornar None.

        Args:
            populated_system: Sistema con instintos pre-cargados.

        Returns:
            None. Asserts que retorna None.
        """
        instinto = populated_system.recall("este contexto no tiene nada que ver")
        assert instinto is None

    def test_recall_empty_system(self, instinct_system: InstinctSystem) -> None:
        """Sistema vacio siempre retorna None.

        Args:
            instinct_system: Sistema vacio.

        Returns:
            None. Asserts que retorna None.
        """
        instinto = instinct_system.recall("cualquier cosa")
        assert instinto is None

    def test_recall_updates_times_used(self, populated_system: InstinctSystem) -> None:
        """Verifica que recall incrementa times_used del instinto.

        Args:
            populated_system: Sistema con instintos pre-cargados.

        Returns:
            None. Asserts que el contador se incrementa.
        """
        instinto = populated_system.recall("timeout en servicio externo")
        assert instinto is not None
        assert instinto.times_used == 1
        # Segunda llamada
        populated_system.recall("otro timeout detectado")
        assert instinto.times_used == 2

    def test_recall_multiple_instincts_first_wins(self, populated_system: InstinctSystem) -> None:
        """Cuando varios instintos coinciden, retorna el primero registrado.

        Args:
            populated_system: Sistema con instintos pre-cargados.

        Returns:
            None. Asserts que retorna el primero.
        """
        # Contexto que contiene "cache" y "vulnerabilidad"
        instinto = populated_system.recall(
            "cache con vulnerabilidad detectada",
        )
        assert instinto is not None
        assert instinto.name == "cache_hit"  # primero en orden de registro

    def test_recall_none_context_raises(self, populated_system: InstinctSystem) -> None:
        """Contexto None debe lanzar ValueError.

        Args:
            populated_system: Sistema con instintos pre-cargados.

        Returns:
            None. Asserts que se lanza ValueError.
        """
        with pytest.raises(ValueError, match="contexto no puede ser None"):
            populated_system.recall(None)  # type: ignore[arg-type]


# ============================================================================
# Test 4: Estadisticas del sistema
# ============================================================================


class TestSystemStats:
    """Tests de estadisticas del sistema de instintos."""

    def test_stats_after_learning(self, instinct_system: InstinctSystem) -> None:
        """Verifica estadisticas tras aprender instintos.

        Args:
            instinct_system: Sistema vacio.

        Returns:
            None. Asserts valores correctos.
        """
        instinct_system.learn("a", "x", "action a", "ctx")
        instinct_system.learn("b", "y", "action b", "ctx")
        stats = instinct_system.get_stats()
        assert stats["total_instincts"] == 2
        assert stats["total_uses"] == 0

    def test_stats_after_recall(self, populated_system: InstinctSystem) -> None:
        """Verifica estadisticas tras evocar instintos.

        Args:
            populated_system: Sistema con instintos pre-cargados.

        Returns:
            None. Asserts total_uses refleja las evocaciones.
        """
        populated_system.recall("timeout en servicio")
        populated_system.recall("cache lleno")
        stats = populated_system.get_stats()
        assert stats["total_instincts"] == 3
        assert stats["total_uses"] == 2

    def test_stats_no_side_effects(self, populated_system: InstinctSystem) -> None:
        """get_stats no debe modificar el estado interno.

        Args:
            populated_system: Sistema con instintos pre-cargados.

        Returns:
            None. Asserts que las estadisticas son consistentes.
        """
        stats1 = populated_system.get_stats()
        stats2 = populated_system.get_stats()
        assert stats1 == stats2


# ============================================================================
# Test 5: Propiedades de Instinct dataclass
# ============================================================================


class TestInstinctDataclass:
    """Tests de la dataclass Instinct."""

    def test_instinct_creation(self) -> None:
        """Crea un Instinct directamente y verifica valores por defecto.

        Returns:
            None. Asserts que los valores por defecto son correctos.
        """
        i = Instinct(name="test", trigger_pattern="pat", action="act")
        assert i.name == "test"
        assert i.trigger_pattern == "pat"
        assert i.action == "act"
        assert i.context == ""
        assert i.success_rate == 0.0
        assert i.times_used == 0

    def test_instinct_with_all_fields(self) -> None:
        """Crea un Instinct con todos los campos especificados.

        Returns:
            None. Asserts que todos los campos se asignan correctamente.
        """
        i = Instinct(
            name="full",
            trigger_pattern="pattern",
            action="action",
            context="context",
            success_rate=0.85,
            times_used=10,
        )
        assert i.success_rate == 0.85
        assert i.times_used == 10


# ============================================================================
# Test 6: Property-based invariants
# ============================================================================


class TestInstinctInvariants:
    """Tests de invariantes del sistema de instintos."""

    def test_invariant_no_duplicate_names(self) -> None:
        """Invariante: no debe haber dos instintos con el mismo nombre.

        Returns:
            None. Asserts idempotencia en learn.
        """
        system = InstinctSystem()
        system.learn("a", "x", "act", "ctx")
        system.learn("a", "y", "act2", "ctx2")  # mismo nombre
        names = [i.name for i in system._instincts]
        assert len(names) == len(set(names))  # sin duplicados

    def test_invariant_times_used_non_negative(self) -> None:
        """Invariante: times_used nunca debe ser negativo.

        Returns:
            None. Asserts que times_used siempre >= 0.
        """
        system = InstinctSystem()
        system.learn("a", "x", "act")
        for _ in range(5):
            system.recall("contexto con x para activar")
        for instinto in system._instincts:
            assert instinto.times_used >= 0

    def test_invariant_learn_does_not_affect_others(self) -> None:
        """Invariante: learn no debe modificar instintos existentes.

        Returns:
            None. Asserts que instintos previos no se modifican.
        """
        system = InstinctSystem()
        i1 = system.learn("a", "x", "act", "ctx")
        system.learn("b", "y", "act2", "ctx2")
        assert i1.trigger_pattern == "x"
        assert i1.context == "ctx"


# ============================================================================
# Test 7: Casos borde (edge cases)
# ============================================================================


class TestEdgeCases:
    """Tests de casos borde del sistema de instintos."""

    def test_learn_whitespace_name_stripped(self, instinct_system: InstinctSystem) -> None:
        """Verifica que nombres con espacios se limpian.

        Args:
            instinct_system: Sistema vacio.

        Returns:
            None. Asserts que el nombre se hace strip.
        """
        instinto = instinct_system.learn("  test  ", "pattern", "action")
        assert instinto.name == "test"

    def test_recall_empty_string(self, instinct_system: InstinctSystem) -> None:
        """Contexto vacio no debe activar ningun instinto.

        Args:
            instinct_system: Sistema vacio.

        Returns:
            None. Asserts que retorna None.
        """
        instinct_system.learn("a", "test", "action")
        resultado = instinct_system.recall("")
        assert resultado is None

    def test_recall_with_special_chars(self, populated_system: InstinctSystem) -> None:
        """Contexto con caracteres especiales debe funcionar.

        Args:
            populated_system: Sistema con instintos.

        Returns:
            None. Asserts que el matching funciona.
        """
        instinto = populated_system.recall(
            "!!! URGENTE: timeout critico en API externa !!!",
        )
        assert instinto is not None
        assert instinto.name == "error_retry"

    def test_many_instincts_performance(self) -> None:
        """Sistema con muchos instintos debe seguir funcionando.

        Returns:
            None. Asserts que el sistema maneja N instintos.
        """
        system = InstinctSystem()
        for i in range(100):
            system.learn(f"instinct_{i}", f"p{i:04d}", f"action_{i}")
        assert len(system) == 100
        # Recall del ultimo con patron unico (sin colision de substring)
        instinto = system.recall("p0099 es el patron")
        assert instinto is not None
        assert instinto.name == "instinct_99"


# ============================================================================
# Test 8: Integracion con logging
# ============================================================================


class TestInstinctLogging:
    """Tests de logging del sistema de instintos."""

    def test_learn_logs_info(self, instinct_system: InstinctSystem) -> None:
        """Verifica que learn registra un log informativo.

        Args:
            instinct_system: Sistema vacio.

        Returns:
            None. Asserts que se llamo a logger.info.
        """
        with patch("harness.orchestrator.instincts.logger") as mock_logger:
            instinct_system.learn("test", "pattern", "action", "ctx")
            mock_logger.info.assert_called_once()

    def test_recall_logs_debug(self, populated_system: InstinctSystem) -> None:
        """Verifica que recall registra un log de debug.

        Args:
            populated_system: Sistema con instintos.

        Returns:
            None. Asserts que se llamo a logger.debug.
        """
        with patch("harness.orchestrator.instincts.logger") as mock_logger:
            populated_system.recall("timeout en la conexion")
            mock_logger.debug.assert_called()

    def test_no_match_logs_debug(self, populated_system: InstinctSystem) -> None:
        """Sin coincidencia debe loggear debug tambien.

        Args:
            populated_system: Sistema con instintos.

        Returns:
            None. Asserts que se llama a logger.debug.
        """
        with patch("harness.orchestrator.instincts.logger") as mock_logger:
            populated_system.recall("sin coincidencia")
            mock_logger.debug.assert_called()
