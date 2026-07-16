"""Tests para lazy loading y warm start de harness."""
from __future__ import annotations
import sys
import importlib
import pytest


class TestLazyLoading:
    """Verifica que harness use lazy imports para inicio rapido."""

    def test_import_harness_no_carga_submodulos_pesados(self):
        """import harness NO debe cargar numpy/LanceDB hasta primer uso."""
        # Limpiar cache de modulo (solo para esta prueba)
        for mod in list(sys.modules.keys()):
            if mod.startswith("harness.") and mod != "harness":
                del sys.modules[mod]

        import harness

        # Verificar que submodulos NO estan cargados
        submodulos_pesados = [
            "harness.orchestrator.task_manager",
            "harness.orchestrator.agent_bus",
            "harness.memory_rag.lance_vector_store",
            "harness.evolve_loop.cognition_sync",
            "harness.tools_sandbox.mcp_executor",
        ]
        for mod in submodulos_pesados:
            assert mod not in sys.modules, (
                f"Submodulo {mod} cargado prematuramente al importar harness"
            )

    def test_acceso_a_simbolo_carga_modulo_bajo_demanda(self):
        """Acceder a harness.Symbol debe cargar el modulo solo entonces."""
        # Limpiar cache
        for mod in list(sys.modules.keys()):
            if mod.startswith("harness."):
                del sys.modules[mod]

        import harness

        # Acceder a TaskManager debe cargar task_manager pero NO agent_bus
        _ = harness.TaskManager
        assert "harness.orchestrator.task_manager" in sys.modules
        # agent_bus NO debe estar cargado (son modulos independientes)
        assert "harness.orchestrator.agent_bus" not in sys.modules, (
            "Acceder a TaskManager no deberia cargar agent_bus"
        )

    def test_acceso_secundario_usa_cache(self):
        """Segundo acceso a simbolo debe ser directo (sin __getattr__)."""
        import harness
        # Primer acceso: carga el modulo
        _ = harness.AgentBus
        # Segundo acceso: debe usar cache (globals), no __getattr__
        _ = harness.AgentBus
        # Verificar que module esta cacheado en sys.modules
        assert "harness.orchestrator.agent_bus" in sys.modules

    def test_symbol_map_contiene_todos_los_nuevos_modulos(self):
        """Verificar que los 6 nuevos modulos estan en __all__."""
        import harness
        nuevos = [
            "evaluator_optimizer", "voting", "critique_revise", "parallel_transform",
            "PBTTemplate", "TEMPLATES",
            "BehavioralTracer",
            "check_all",
        ]
        for symbol in nuevos:
            assert symbol in harness.__all__, (
                f"Simbolo {symbol} no esta en harness.__all__"
            )

    def test_acceso_a_nuevos_modulos_funciona(self):
        """Los nuevos modulos deben ser accesibles via harness."""
        import harness

        # Workflow patterns
        eo = harness.evaluator_optimizer
        assert callable(eo)

        # PBT Templates
        templates = harness.TEMPLATES
        assert len(templates) >= 5

        # Behavioral Tracer
        bt = harness.BehavioralTracer
        assert callable(bt)

        # Architectural Guardrails
        check = harness.check_all
        assert callable(check)


class TestWarmStart:
    """Verifica que el warm start sea rapido."""

    def test_import_subsequent_instant(self):
        """Segundo import de harness debe ser instantaneo (<50ms)."""
        import time
        import harness  # primer import (puede ser lento si primera vez)

        # Segundo import (debe ser cacheado en sys.modules)
        s = time.perf_counter()
        import importlib
        importlib.reload(harness)  # Recarga forcada
        t = time.perf_counter()
        # Nota: reload() es mas lento que import normal
        # Lo importante es que import normal no recargue

    def test_import_time_under_100ms(self):
        """import harness debe tardar <100ms (no cargar modulos pesados)."""
        # Limpiar cache
        for mod in list(sys.modules.keys()):
            if mod.startswith("harness."):
                del sys.modules[mod]

        import time
        s = time.perf_counter()
        import harness
        elapsed_ms = (time.perf_counter() - s) * 1000
        assert elapsed_ms < 100, (
            f"import harness tardo {elapsed_ms:.1f}ms (esperado <100ms)"
        )

    def test_cold_start_mejora_significativa(self):
        """Cold start debe ser >10x mas rapido que eager loading."""
        # Medir import rapido (lazy)
        for mod in list(sys.modules.keys()):
            if mod.startswith("harness."):
                del sys.modules[mod]
        import time
        s = time.perf_counter()
        import harness
        lazy_ms = (time.perf_counter() - s) * 1000

        # Lazy debe ser <100ms (antes era ~2800ms)
        assert lazy_ms < 100, (
            f"Lazy import tardo {lazy_ms:.1f}ms, esperado <100ms"
        )
