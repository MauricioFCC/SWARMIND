"""Tests para PerformanceCache — Cache predictivo para respuestas de agentes."""

from __future__ import annotations

import time

import pytest

from harness.orchestrator.performance_cache import PerformanceCache


class TestPerformanceCache:
    """Suite de pruebas para la clase PerformanceCache."""

    # ----------------------------------------------------------------
    # Test 1: Inicialización básica
    # ----------------------------------------------------------------
    def test_init_defaults(self) -> None:
        """Verifica valores por defecto del constructor."""
        cache = PerformanceCache()
        assert cache._max_size == 100
        assert cache._ttl == 300.0
        assert cache.size == 0
        assert cache.hit_rate == 0.0

    # ----------------------------------------------------------------
    # Test 2: Set y Get básico
    # ----------------------------------------------------------------
    def test_set_and_get(self) -> None:
        """Verifica almacenar y recuperar un valor."""
        cache = PerformanceCache(max_size=10, ttl=60.0)
        cache.set("clave1", 42)
        assert cache.get("clave1") == 42
        assert cache.size == 1

    # ----------------------------------------------------------------
    # Test 3: Get de clave inexistente retorna None
    # ----------------------------------------------------------------
    def test_get_miss_returns_none(self) -> None:
        """Verifica que una clave ausente retorne None."""
        cache = PerformanceCache()
        assert cache.get("no_existe") is None

    # ----------------------------------------------------------------
    # Test 4: Hit rate después de accesos
    # ----------------------------------------------------------------
    def test_hit_rate(self) -> None:
        """Verifica el cálculo correcto de la tasa de aciertos."""
        cache = PerformanceCache(max_size=10, ttl=60.0)
        cache.set("a", 1)
        cache.set("b", 2)

        # 2 hits
        cache.get("a")
        cache.get("b")
        # 1 miss
        cache.get("z")

        assert cache.hit_rate == pytest.approx(2 / 3, rel=1e-6)
        assert cache._hits == 2
        assert cache._misses == 1

    # ----------------------------------------------------------------
    # Test 5: Desalojo LRU cuando se excede max_size
    # ----------------------------------------------------------------
    def test_lru_eviction(self) -> None:
        """Verifica que se desaloje la entrada menos reciente al exceder max_size."""
        cache = PerformanceCache(max_size=3, ttl=60.0)
        cache.set("a", 1)
        cache.set("b", 2)
        cache.set("c", 3)
        cache.set("d", 4)  # esto debe desalojar "a"

        assert cache.get("a") is None  # desalojado
        assert cache.get("b") == 2
        assert cache.get("c") == 3
        assert cache.get("d") == 4
        assert cache.size == 3

    # ----------------------------------------------------------------
    # Test 6: Expiración por TTL
    # ----------------------------------------------------------------
    def test_ttl_expiry(self) -> None:
        """Verifica que las entradas expiren después del TTL."""
        cache = PerformanceCache(max_size=10, ttl=0.1)  # 100ms
        cache.set("a", "valor")
        assert cache.get("a") == "valor"
        time.sleep(0.15)  # esperar a que expire
        assert cache.get("a") is None
        assert cache.size == 0

    # ----------------------------------------------------------------
    # Test 7: Clear resetea todo
    # ----------------------------------------------------------------
    def test_clear(self) -> None:
        """Verifica que clear() vacíe el caché y resetee estadísticas."""
        cache = PerformanceCache(max_size=10, ttl=60.0)
        cache.set("a", 1)
        cache.set("b", 2)
        cache.get("a")  # hit
        cache.get("z")  # miss
        cache.clear()

        assert cache.size == 0
        assert cache._hits == 0
        assert cache._misses == 0
        assert cache.hit_rate == 0.0

    # ----------------------------------------------------------------
    # Test 8: Invalidate elimina una clave específica
    # ----------------------------------------------------------------
    def test_invalidate(self) -> None:
        """Verifica que invalidate() elimine una clave y retorne indicador."""
        cache = PerformanceCache(max_size=10, ttl=60.0)
        cache.set("x", 100)
        assert cache.get("x") == 100

        # invalidar clave existente
        assert cache.invalidate("x") is True
        assert cache.get("x") is None
        assert cache.size == 0

        # invalidar clave inexistente
        assert cache.invalidate("no_existe") is False

    # ----------------------------------------------------------------
    # Test 9: Constructor valida parámetros
    # ----------------------------------------------------------------
    def test_invalid_constructor_args(self) -> None:
        """Verifica que el constructor rechace parámetros inválidos."""
        with pytest.raises(ValueError, match="max_size debe ser positivo"):
            PerformanceCache(max_size=0)
        with pytest.raises(ValueError, match="max_size debe ser positivo"):
            PerformanceCache(max_size=-5)
        with pytest.raises(ValueError, match="ttl debe ser positivo"):
            PerformanceCache(ttl=0.0)
        with pytest.raises(ValueError, match="ttl debe ser positivo"):
            PerformanceCache(ttl=-1.0)

    # ----------------------------------------------------------------
    # Test 10: Hit rate con cero accesos
    # ----------------------------------------------------------------
    def test_hit_rate_no_accesses(self) -> None:
        """Verifica que hit_rate sea 0.0 cuando no ha habido accesos."""
        cache = PerformanceCache()
        assert cache.hit_rate == 0.0
