"""
Tests para BusinessContext — Glosario y contexto de negocio.

Verifica carga de terminos por defecto, enriquecimiento de prompts,
filtrado por industria y gestion de terminos personalizados.
"""
from __future__ import annotations

from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from harness.orchestrator.business_context import BusinessContext, BusinessTerm


class TestBusinessContextInit:
    """Tests de inicializacion del contexto de negocio."""

    def test_default_terms_loaded(self):
        """Debe cargar los terminos por defecto al inicializar."""
        ctx = BusinessContext()
        assert ctx.get_definition("cliente activo") is not None
        assert ctx.get_definition("churn") is not None
        assert ctx.get_definition("ROAS") is not None

    def test_default_industry_is_general(self):
        """La industria por defecto debe ser 'general'."""
        ctx = BusinessContext()
        assert ctx.get_industry() == "general"

    def test_unknown_term_returns_none(self):
        """Termino no registrado debe retornar None."""
        ctx = BusinessContext()
        assert ctx.get_definition("termino_inexistente") is None


class TestBusinessContextTermManagement:
    """Tests de gestion de terminos (alta, consulta, eliminacion)."""

    def setup_method(self):
        self.ctx = BusinessContext()

    def test_add_custom_term(self):
        """Agregar un termino personalizado debe funcionar."""
        self.ctx.add_term("NPS", "Net Promoter Score", industry="marketing")
        assert self.ctx.get_definition("nps") == "Net Promoter Score"

    def test_add_term_with_aliases(self):
        """Agregar un termino con alias debe almacenar los alias."""
        self.ctx.add_term(
            "CAC",
            "Customer Acquisition Cost",
            industry="marketing",
            aliases=["costo adquisicion", "coste captacion"],
        )
        term = self.ctx.get_term("cac")
        assert term is not None
        assert "costo adquisicion" in term.aliases

    def test_add_empty_term_raises(self):
        """Agregar un termino vacio debe lanzar ValueError."""
        with pytest.raises(ValueError, match="El termino no puede estar vacio"):
            self.ctx.add_term("", "definicion")

    def test_add_term_empty_definition_raises(self):
        """Agregar un termino con definicion vacia debe lanzar ValueError."""
        with pytest.raises(ValueError, match="La definicion no puede estar vacia"):
            self.ctx.add_term("algo", "")

    def test_get_term_returns_none_for_missing(self):
        """get_term debe retornar None para terminos inexistentes."""
        assert self.ctx.get_term("no_existe") is None

    def test_remove_existing_term(self):
        """Eliminar un termino existente debe retornar True."""
        self.ctx.add_term("test_term", "definicion de prueba")
        assert self.ctx.remove_term("test_term") is True
        assert self.ctx.get_definition("test_term") is None

    def test_remove_nonexistent_term_returns_false(self):
        """Eliminar un termino inexistente debe retornar False."""
        assert self.ctx.remove_term("no_existe") is False

    def test_list_terms_all(self):
        """list_terms sin filtro debe retornar todos los terminos."""
        terms = self.ctx.list_terms()
        assert len(terms) >= 5  # 5 defaults

    def test_list_terms_by_industry(self):
        """list_terms con industria debe filtrar correctamente."""
        marketing_terms = self.ctx.list_terms(industry="marketing")
        assert all(t.industry == "marketing" for t in marketing_terms)
        assert any(t.term == "ROAS" for t in marketing_terms)
        general_terms = self.ctx.list_terms(industry="general")
        assert any(t.term == "cliente activo" for t in general_terms)
        assert all(t.industry == "general" for t in general_terms)


class TestBusinessContextIndustry:
    """Tests de configuracion de industria activa."""

    def setup_method(self):
        self.ctx = BusinessContext()

    def test_set_industry(self):
        """Cambiar la industria activa debe reflejarse."""
        self.ctx.set_industry("marketing")
        assert self.ctx.get_industry() == "marketing"

    def test_set_empty_industry_raises(self):
        """Establecer industria vacia debe lanzar ValueError."""
        with pytest.raises(ValueError, match="La industria no puede ser una cadena vacia"):
            self.ctx.set_industry("")

    def test_set_industry_with_spaces(self):
        """Industria con espacios debe ser aceptada."""
        self.ctx.set_industry("health tech")
        assert self.ctx.get_industry() == "health tech"


class TestBusinessContextEnrichPrompt:
    """Tests de enriquecimiento de prompts con contexto de negocio."""

    def setup_method(self):
        self.ctx = BusinessContext()

    def test_enrich_with_known_term(self):
        """Prompt con termino conocido debe ser enriquecido."""
        result = self.ctx.enrich_prompt("Analiza el churn del ultimo mes")
        assert "[Contexto: churn = Tasa de cancelacion" in result

    def test_enrich_without_known_terms(self):
        """Prompt sin terminos conocidos no debe modificarse."""
        original = "Cual es el clima de hoy?"
        result = self.ctx.enrich_prompt(original)
        assert result == original

    def test_enrich_respects_industry_filter(self):
        """Solo deben incluirse terminos de la industria activa o general."""
        # Con industria 'general', terminos marketing NO deben incluirse
        result = self.ctx.enrich_prompt("Calcula el ROAS y el churn")
        # churn (general) debe incluirse
        assert "[Contexto: churn" in result
        # ROAS (marketing) NO debe incluirse en industria general
        assert "[Contexto: ROAS" not in result

    def test_enrich_with_marketing_industry(self):
        """En industria marketing, deben incluirse terminos de marketing y general."""
        self.ctx.set_industry("marketing")
        result = self.ctx.enrich_prompt("Revisa ROAS y cliente activo")
        assert "[Contexto: ROAS" in result
        assert "[Contexto: cliente activo" in result

    def test_enrich_multiple_terms_in_prompt(self):
        """Prompt con multiples terminos debe incluir todos."""
        result = self.ctx.enrich_prompt("Analiza churn y cliente activo")
        assert "[Contexto: churn" in result
        assert "[Contexto: cliente activo" in result

    def test_enrich_case_insensitive(self):
        """La busqueda de terminos debe ser case-insensitive."""
        result = self.ctx.enrich_prompt("CHURN alto")
        assert "[Contexto: churn" in result

    def test_enrich_with_added_term(self):
        """Terminos agregados despues de inicializar deben enriquecer."""
        self.ctx.add_term("ARR", "Annual Recurring Revenue", industry="saas")
        self.ctx.set_industry("saas")
        result = self.ctx.enrich_prompt("Cual es el ARR actual?")
        assert "[Contexto: ARR" in result


class TestBusinessContextBusinessTerm:
    """Tests del dataclass BusinessTerm."""

    def test_business_term_defaults(self):
        """BusinessTerm debe tener valores por defecto correctos."""
        term = BusinessTerm(term="test", definition="def")
        assert term.industry == "general"
        assert term.aliases == []

    def test_business_term_custom_values(self):
        """BusinessTerm debe aceptar valores personalizados."""
        term = BusinessTerm(
            term="test",
            definition="def",
            industry="fintech",
            aliases=["alias1", "alias2"],
        )
        assert term.industry == "fintech"
        assert len(term.aliases) == 2
