"""Tests para PBT Templates — property-based testing con templates."""
from __future__ import annotations

import pytest

from harness.orchestrator.pbt_templates import (
    TEMPLATES,
    PBTTemplate,
    get_template,
    suggest_templates,
    templates_by_tag,
)


class TestPBTTemplate:
    def test_fill_rellena_holes(self):
        """fill debe reemplazar {holes} con valores."""
        t = PBTTemplate(
            name="test",
            description="test",
            template_code="def test_{name}(): pass",
        )
        result = t.fill(name="mi_funcion")
        assert "test_mi_funcion" in result

    def test_required_holes_detecta(self):
        """required_holes debe extraer nombres de holes."""
        t = PBTTemplate(
            name="test",
            description="test",
            template_code="{a} + {b} = {c}",
        )
        holes = t.required_holes()
        assert sorted(holes) == ["a", "b", "c"]

    def test_required_holes_vacio(self):
        """Sin holes, retorna lista vacia."""
        t = PBTTemplate(name="t", description="d", template_code="sin holes")
        assert t.required_holes() == []


class TestTemplates:
    def test_templates_predefinidos_existen(self):
        """Deben existir al menos 5 templates predefinidos."""
        assert len(TEMPLATES) >= 5

    def test_sorting_stable_tiene_invariants(self):
        """sorting_stable debe tener invariants definidos."""
        t = get_template("sorting_stable")
        assert t is not None
        assert len(t.invariants) >= 2

    def test_get_template_inexistente(self):
        """get_template debe retornar None para nombre invalido."""
        assert get_template("no_existe") is None

    def test_suggest_templates_por_keyword(self):
        """suggest_templates debe encontrar templates relevantes."""
        suggestions = suggest_templates("ordenar lista de numeros")
        assert len(suggestions) >= 1
        assert any(t.name == "sorting_stable" for t in suggestions)

    def test_templates_by_tag(self):
        """templates_by_tag debe filtrar por tag."""
        sorting = templates_by_tag("sorting")
        assert len(sorting) >= 1
        assert all("sorting" in t.tags for t in sorting)

    def test_cada_template_tiene_name_y_description(self):
        """Todo template debe tener name y description no vacios."""
        for name, t in TEMPLATES.items():
            assert t.name, f"Template {name} sin name"
            assert t.description, f"Template {name} sin description"

    def test_cada_template_genera_codigo_valido(self):
        """Todo template debe generar codigo Python sintacticamente valido."""
        import ast
        for name, t in TEMPLATES.items():
            holes = t.required_holes()
            kwargs = {h: "dummy_val" for h in holes}
            code = t.fill(**kwargs)
            try:
                ast.parse(code)
            except SyntaxError as e:
                pytest.fail(f"Template {name} genera codigo invalido: {e}")
