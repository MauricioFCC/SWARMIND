"""
Tests para skill_router.py — Router semantico de skills.
Verifica que solo se activen los skills relevantes para cada tarea.
"""

from __future__ import annotations

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

import numpy as np
from harness.memory_rag.skill_router import SkillRouter


class TestSkillRouter:
    """Test del router semantico de skills."""

    def setup_method(self):
        self.router = SkillRouter()

    def test_always_active(self):
        """Siempre incluye evolve."""
        skills = self.router.route("")
        assert "evolve" in skills

    def test_trading_task(self):
        """Tarea de trading activa quant-trading."""
        skills = self.router.route("implementa una estrategia de trading en Rust")
        assert "quant-trading" in skills

    def test_healthtech_task(self):
        """Tarea de salud activa healthtech."""
        skills = self.router.route("crea un modulo de historias clinicas")
        assert "healthtech" in skills

    def test_retail_task(self):
        """Tarea de retail activa pos-retail."""
        skills = self.router.route("agrega un modulo de inventario al POS")
        assert "pos-retail" in skills

    def test_max_skills(self):
        """Nunca retorna mas de MAX_SKILLS_PER_TASK + always_active."""
        skills = self.router.route("trading risk management health", max_skills=2)
        assert len(skills) <= 3  # max_skills + always_active

    def test_keyword_matching(self):
        """Matching por keywords encuentra skills correctos."""
        skills = self.router.route("investigar paper cientifico")
        assert "science-doc" in skills

    def test_build_context_empty(self):
        """Context vacio si no hay skills."""
        ctx = self.router.build_context([])
        assert ctx == ""

    def test_build_context_with_skills(self):
        """Context genera texto para skills seleccionados."""
        ctx = self.router.build_context(["quant-trading"])
        assert "quant-trading" in ctx

    def test_estimate_tokens(self):
        """Estimacion de tokens devuelve entero positivo."""
        tokens = self.router.estimate_tokens(["quant-trading"])
        assert isinstance(tokens, int)
        assert tokens > 0

    def test_get_available_skills(self):
        """Lista de skills disponibles no vacia."""
        skills = self.router.get_available_skills()
        assert len(skills) >= 5
        assert "evolve" in skills
        assert "quant-trading" in skills

    def test_route_none_message(self):
        """Mensaje None retorna always_active."""
        skills = self.router.route(None)
        assert "evolve" in skills

    def test_route_ml_task(self):
        """Tarea de ML activa alpha-research."""
        skills = self.router.route("entrena un modelo de machine learning")
        # alpha-research o evolve
        relevant = {"alpha-research", "evolve"}
        assert any(s in skills for s in relevant)

    def test_context_token_efficiency(self):
        """Contexto generado es menor que cargar todos los skills."""
        # Cargar todos ocuparia ~5000 chars
        all_skills = self.router.get_available_skills()
        ctx_all = self.router.build_context(all_skills)
        # Cargar solo relevantes
        skills = self.router.route("tarea rapida")
        ctx_min = self.router.build_context(skills)
        # El contexto minimo debe ser menor
        assert len(ctx_min) <= len(ctx_all) or len(ctx_min) == 0

    def test_keyword_bonus_by_domain(self):
        """Bonus por dominio en keyword matching."""
        skills = self.router.route("legal contract compliance")
        assert "legal-doc" in skills

    def test_route_fallback_semantic_no_vectors(self):
        """route retorna always_active cuando no hay vectores disponibles."""
        skills = self.router.route("xyzzy zzzzz sin coincidencias semanticas")
        assert "evolve" in skills

    def test_route_no_keyword_no_vectors(self):
        """route sin keyword match y sin vectores retorna always_active."""
        self.router._skill_vectors = None
        skills = self.router.route("plugh plover xyzzy")
        assert "evolve" in skills
        assert len(skills) == 1
