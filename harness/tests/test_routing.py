"""Tests para routing y auto-deteccion."""
from __future__ import annotations


class TestRouting:
    def test_auto_builder(self, delegation_engine):
        assert delegation_engine.auto_route("implementa una API en Rust") == "builder"

    def test_auto_scientist(self, delegation_engine):
        assert delegation_engine.auto_route("investiga este paper") == "scientist"

    def test_auto_guardian(self, delegation_engine):
        assert delegation_engine.auto_route("testing y cobertura") == "guardian"

    def test_auto_evolve(self, delegation_engine):
        assert delegation_engine.auto_route("!evolve run") == "evolve"

    def test_auto_default(self, delegation_engine):
        assert delegation_engine.auto_route("hola mundo") == "coordinator"

    def test_explicit_at_builder(self, delegation_engine):
        assert delegation_engine.route_message("@builder: create") == "builder"

    def test_old_alias_swe(self, delegation_engine):
        assert delegation_engine.route_message("@swe: fix bug") == "builder"

    def test_old_alias_pm(self, delegation_engine):
        assert delegation_engine.route_message("@pm: plan") == "coordinator"

    def test_old_alias_qa(self, delegation_engine):
        assert delegation_engine.route_message("@qa: test") == "guardian"
