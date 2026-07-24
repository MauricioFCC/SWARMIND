"""Tests de precision del enrutamiento automatico."""
from __future__ import annotations

import pytest

from harness.orchestrator.delegation_engine import DelegationEngine


@pytest.fixture
def engine() -> DelegationEngine:
    return DelegationEngine()


# Casos de prueba: (mensaje, agente_esperado)
TEST_CASES = [
    # --- Builder (implementacion) ---
    ("implementa una funcion de ordenamiento en Go", "builder"),
    ("crea un modulo de autenticacion JWT en Python", "builder"),
    ("implementa una API REST en Rust", "builder"),
    ("crea un frontend web con React", "builder"),
    ("desarrolla un microservicio en Go", "builder"),
    ("implementa una trading strategy en Python", "builder"),
    ("crea un CLI tool para procesar datos", "builder"),
    
    # --- Scientist (investigacion) ---
    ("investiga papers sobre transformers 2026", "scientist"),
    ("analiza la arquitectura del sistema", "scientist"),
    ("investiga patrones de diseno", "scientist"),
    ("disena un experimento estadistico", "scientist"),
    ("literature review sobre machine learning", "scientist"),
    ("propuesta de arquitectura hexagonal", "scientist"),
    ("trade-off analysis entre SQL y NoSQL", "scientist"),
    
    # --- Guardian (calidad/seguridad) ---
    ("audita la seguridad del sistema", "guardian"),
    ("haz una auditoria de seguridad", "guardian"),
    ("escribe documentacion tecnica de la API", "guardian"),
    ("ejecuta pruebas de rendimiento", "guardian"),
    ("revisa la cobertura de tests", "guardian"),
    ("hardening de seguridad del servidor", "guardian"),
    ("threat model de la aplicacion", "guardian"),
    
    # --- Evolve (auto-mejora) ---
    ("mejora el rendimiento del sistema", "evolve"),
    ("auto-mejora del skill de trading", "evolve"),
    ("evolve loop de optimizacion", "evolve"),
    ("asi-evolve para mejorar accuracy", "evolve"),
    
    # --- Coordinator (default) ---
    ("organiza el sprint de la semana", "coordinator"),
    ("que es este sistema", "coordinator"),
    ("hola", "coordinator"),
    ("ayuda", "coordinator"),
]


class TestRoutingAccuracy:
    """Verifica que el enrutamiento automatico sea correcto."""

    @pytest.mark.parametrize("message,expected", TEST_CASES)
    def test_route(self, engine: DelegationEngine, message: str, expected: str) -> None:
        """Mensaje debe enrutar al agente correcto."""
        result = engine.auto_route(message)
        assert result == expected, (
            f"FALLO: '{message}' -> '{result}' (esperado: '{expected}')"
        )
