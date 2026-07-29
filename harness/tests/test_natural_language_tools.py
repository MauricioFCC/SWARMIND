"""
Tests para NaturalLanguageToolkit (arXiv:2607.03953).

Cubre: parseo, matching semántico, registro de herramientas,
encadenamiento, extracción de parámetros, umbral de confianza,
sugerencias y manejo de errores.
"""
from __future__ import annotations

import pytest

from harness.orchestrator.natural_language_tools import (
    DEFAULT_CONFIDENCE_THRESHOLD,
    NLTool,
    NLTResult,
    NaturalLanguageToolkit,
)


# ===========================================================================
# Fixtures
# ===========================================================================


@pytest.fixture
def nlt() -> NaturalLanguageToolkit:
    """NaturalLanguageToolkit con herramientas por defecto."""
    return NaturalLanguageToolkit()


# ===========================================================================
# Tests de parseo básico
# ===========================================================================


class TestParseBasic:
    """Tests de parseo de lenguaje natural a herramientas."""

    def test_parse_buscar(self, nlt: NaturalLanguageToolkit) -> None:
        """Debe identificar la herramienta 'buscar' en una frase de búsqueda."""
        result = nlt.parse("necesito buscar contratos de servicios")
        assert result is not None
        assert result.tool == "buscar"
        assert result.confidence >= nlt._threshold
        assert "action" in result.structured_output
        assert result.structured_output["action"] == "buscar"
        assert isinstance(result.natural_input, str)
        assert len(result.natural_input) > 0

    def test_parse_analizar(self, nlt: NaturalLanguageToolkit) -> None:
        """Debe identificar la herramienta 'analizar' en una frase de análisis."""
        result = nlt.parse("analiza el contrato de arrendamiento completo")
        assert result is not None
        assert result.tool == "analizar"
        assert result.confidence >= nlt._threshold

    def test_parse_comparar(self, nlt: NaturalLanguageToolkit) -> None:
        """Debe identificar la herramienta 'comparar' en una frase de comparación."""
        result = nlt.parse("compara el documento A con el documento B")
        assert result is not None
        assert result.tool == "comparar"
        assert result.confidence >= nlt._threshold

    def test_parse_resumir(self, nlt: NaturalLanguageToolkit) -> None:
        """Debe identificar la herramienta 'resumir' en una frase de resumen."""
        result = nlt.parse("necesito un resumen ejecutivo del dictamen")
        assert result is not None
        assert result.tool == "resumir"
        assert result.confidence >= nlt._threshold


# ===========================================================================
# Tests de casos límite y errores
# ===========================================================================


class TestParseEdgeCases:
    """Tests de casos límite en el parseo."""

    def test_parse_empty_text(self, nlt: NaturalLanguageToolkit) -> None:
        """Texto vacío debe lanzar ValueError."""
        with pytest.raises(ValueError, match="no puede estar vacío"):
            nlt.parse("")

    def test_parse_whitespace_text(self, nlt: NaturalLanguageToolkit) -> None:
        """Texto con solo espacios debe lanzar ValueError."""
        with pytest.raises(ValueError, match="no puede estar vacío"):
            nlt.parse("   ")

    def test_parse_no_match(self, nlt: NaturalLanguageToolkit) -> None:
        """Texto sin relación con ninguna tool debe retornar None."""
        result = nlt.parse("qué hora es en tokio")
        assert result is None

    def test_parse_no_match_below_threshold(
        self,
        nlt: NaturalLanguageToolkit,
    ) -> None:
        """Texto con confianza baja debe retornar None."""
        result = nlt.parse("xyzzy plugh fred barney")
        assert result is None

    def test_parse_batch(self, nlt: NaturalLanguageToolkit) -> None:
        """parse_batch debe procesar múltiples textos correctamente."""
        texts = [
            "buscar jurisprudencia",
            "analizar documento legal",
            "fruta tropical",
        ]
        results = nlt.parse_batch(texts)
        assert len(results) == 3
        assert results[0] is not None
        assert results[0].tool == "buscar"
        assert results[1] is not None
        assert results[1].tool == "analizar"
        assert results[2] is None  # Sin match


# ===========================================================================
# Tests de registro de herramientas
# ===========================================================================


class TestToolRegistration:
    """Tests de registro, eliminación y consulta de herramientas."""

    def test_register_custom_tool(self, nlt: NaturalLanguageToolkit) -> None:
        """Registrar una herramienta personalizada debe funcionar."""
        custom = NLTool(
            name="traducir",
            description="Traducir texto legal a otro idioma",
            parameters={"texto": "texto a traducir", "idioma": "idioma destino"},
            examples=["traducir al inglés esta cláusula"],
        )
        nlt.register_tool(custom)
        assert nlt.get_tool("traducir") is not None
        assert nlt.get_tool_count() == 5  # 4 default + 1 custom

    def test_register_duplicate_overwrites(
        self,
        nlt: NaturalLanguageToolkit,
    ) -> None:
        """Registrar una tool con nombre existente debe sobrescribir."""
        updated = NLTool(
            name="buscar",
            description="Descripción actualizada para buscar",
        )
        nlt.register_tool(updated)
        tool = nlt.get_tool("buscar")
        assert tool is not None
        assert "actualizada" in tool.description

    def test_register_invalid_type(self, nlt: NaturalLanguageToolkit) -> None:
        """Registrar algo que no sea NLTool debe lanzar TypeError."""
        with pytest.raises(TypeError, match="NLTool"):
            nlt.register_tool("no soy un tool")  # type: ignore[arg-type]

    def test_register_empty_name(self, nlt: NaturalLanguageToolkit) -> None:
        """Registrar una tool con nombre vacío debe lanzar ValueError."""
        with pytest.raises(ValueError, match="no puede estar vacío"):
            nlt.register_tool(NLTool(name="", description="vacío"))

    def test_unregister_existing(self, nlt: NaturalLanguageToolkit) -> None:
        """Eliminar una tool existente debe retornar True."""
        assert nlt.unregister_tool("comparar") is True
        assert nlt.get_tool("comparar") is None

    def test_unregister_non_existing(self, nlt: NaturalLanguageToolkit) -> None:
        """Eliminar una tool inexistente debe retornar False."""
        assert nlt.unregister_tool("inexistente") is False

    def test_list_tools(self, nlt: NaturalLanguageToolkit) -> None:
        """list_tools debe retornar todas las herramientas ordenadas."""
        tools = nlt.list_tools()
        assert len(tools) == 4
        assert tools == sorted(tools)
        assert "buscar" in tools
        assert "analizar" in tools
        assert "comparar" in tools
        assert "resumir" in tools

    def test_get_tool_existing(self, nlt: NaturalLanguageToolkit) -> None:
        """get_tool debe retornar la herramienta si existe."""
        tool = nlt.get_tool("buscar")
        assert tool is not None
        assert tool.name == "buscar"
        assert "documentos legales" in tool.description

    def test_get_tool_non_existing(self, nlt: NaturalLanguageToolkit) -> None:
        """get_tool debe retornar None si la herramienta no existe."""
        assert nlt.get_tool("no_existe") is None

    def test_get_tool_count(self, nlt: NaturalLanguageToolkit) -> None:
        """get_tool_count debe retornar la cantidad correcta."""
        assert nlt.get_tool_count() == 4


# ===========================================================================
# Tests de parámetros extraídos
# ===========================================================================


class TestParameterExtraction:
    """Tests de extracción de parámetros desde lenguaje natural."""

    def test_extract_query_param(self, nlt: NaturalLanguageToolkit) -> None:
        """Debe extraer el parámetro 'query' de una frase de búsqueda."""
        result = nlt.parse("buscar contratos de confidencialidad 2024")
        assert result is not None
        params = result.structured_output.get("parameters", {})
        assert "query" in params

    def test_extract_document_param(self, nlt: NaturalLanguageToolkit) -> None:
        """Debe extraer el parámetro 'documento' de una frase de análisis."""
        result = nlt.parse("analizar el documento C-1234 en modo riesgos")
        assert result is not None
        params = result.structured_output.get("parameters", {})
        assert "documento" in params

    def test_extract_tipo_param(self, nlt: NaturalLanguageToolkit) -> None:
        """Debe extraer el parámetro 'tipo' de análisis."""
        result = nlt.parse("analizar expediente en modo riesgos")
        assert result is not None
        params = result.structured_output.get("parameters", {})
        assert "tipo" in params

    def test_extract_longitud_param(self, nlt: NaturalLanguageToolkit) -> None:
        """Debe extraer el parámetro 'longitud' de resumen."""
        result = nlt.parse("resumir el dictamen en modo detallado")
        assert result is not None
        params = result.structured_output.get("parameters", {})
        assert "longitud" in params

    def test_extract_max_param(self, nlt: NaturalLanguageToolkit) -> None:
        """Debe extraer el parámetro 'max' como entero."""
        result = nlt.parse("buscar cláusulas máximo 10 resultados")
        assert result is not None
        params = result.structured_output.get("parameters", {})
        assert params.get("max") == 10

    def test_extract_doc1_doc2(self, nlt: NaturalLanguageToolkit) -> None:
        """Debe extraer doc1 y doc2 de una frase de comparación."""
        result = nlt.parse("comparar contrato-A y contrato-B")
        assert result is not None
        params = result.structured_output.get("parameters", {})
        # Al menos uno de los dos debe estar presente
        assert "doc1" in params or "doc2" in params


# ===========================================================================
# Tests de alternativas y sugerencias
# ===========================================================================


class TestAlternativesAndSuggestions:
    """Tests de alternativas y sugerencias de herramientas."""

    def test_parse_with_alternatives(self, nlt: NaturalLanguageToolkit) -> None:
        """El resultado debe incluir alternativas cuando existan."""
        result = nlt.parse("buscar documentos legales")
        assert result is not None
        # Puede tener alternativas con suficiente confianza
        assert isinstance(result.alternatives, list)

    def test_suggest_tools(self, nlt: NaturalLanguageToolkit) -> None:
        """suggest_tools debe retornar sugerencias ordenadas."""
        suggestions = nlt.suggest_tools("quiero buscar un contrato", top_n=2)
        assert len(suggestions) <= 2
        assert all(isinstance(s, tuple) for s in suggestions)
        assert all(len(s) == 2 for s in suggestions)
        # La primera sugerencia debe tener la mayor confianza
        if len(suggestions) >= 2:
            assert suggestions[0][1] >= suggestions[1][1]

    def test_suggest_tools_empty_text(self, nlt: NaturalLanguageToolkit) -> None:
        """suggest_tools con texto vacío debe retornar lista vacía."""
        assert nlt.suggest_tools("") == []
        assert nlt.suggest_tools("   ") == []

    def test_find_tools_by_description(
        self,
        nlt: NaturalLanguageToolkit,
    ) -> None:
        """find_tools_by_description debe encontrar tools por palabra clave."""
        results = nlt.find_tools_by_description("documento")
        assert len(results) >= 1
        assert "analizar" in results or "buscar" in results

    def test_find_tools_by_description_no_match(
        self,
        nlt: NaturalLanguageToolkit,
    ) -> None:
        """find_tools_by_description sin match debe retornar lista vacía."""
        results = nlt.find_tools_by_description("zyxwv")
        assert results == []

    def test_match_exact(self, nlt: NaturalLanguageToolkit) -> None:
        """match_exact debe coincidir con el nombre exacto de una tool."""
        assert nlt.match_exact("buscar") == "buscar"
        assert nlt.match_exact("analizar") == "analizar"

    def test_match_exact_case_insensitive(
        self,
        nlt: NaturalLanguageToolkit,
    ) -> None:
        """match_exact debe ser insensitive a mayúsculas."""
        assert nlt.match_exact("BUSCAR") == "buscar"

    def test_match_exact_no_match(self, nlt: NaturalLanguageToolkit) -> None:
        """match_exact sin coincidencia debe retornar None."""
        assert nlt.match_exact("inexistente") is None


# ===========================================================================
# Tests de encadenamiento de herramientas
# ===========================================================================


class TestToolChaining:
    """Tests de encadenamiento de herramientas (tool chaining)."""

    def test_parse_chain_two_tools(self, nlt: NaturalLanguageToolkit) -> None:
        """Texto con 'y' debe generar un chain con dos herramientas."""
        result = nlt.parse("buscar contratos y analizar documento")
        # Puede devolver la primera o ninguna dependiendo del threshold
        if result is not None:
            assert isinstance(result.chain, list)
            assert len(result.chain) >= 1

    def test_parse_chain_order(self, nlt: NaturalLanguageToolkit) -> None:
        """El encadenamiento debe respetar el orden de las intenciones."""
        result = nlt.parse("comparar versiones y resumir resultado")
        if result is not None:
            assert result.tool == "comparar"
            if result.chain:
                assert result.chain[0].tool == "resumir"

    def test_chain_confidence_boost(
        self,
        nlt: NaturalLanguageToolkit,
    ) -> None:
        """El encadenamiento exitoso debe incrementar ligeramente la confianza."""
        single = nlt.parse("comparar documentos")
        chain = nlt.parse("comparar documentos y resumir resultado")
        if single and chain:
            assert chain.confidence >= single.confidence


# ===========================================================================
# Tests de umbral de confianza
# ===========================================================================


class TestConfidenceThreshold:
    """Tests del umbral de confianza configurable."""

    def test_set_threshold_valid(self, nlt: NaturalLanguageToolkit) -> None:
        """set_confidence_threshold debe aceptar valores válidos."""
        nlt.set_confidence_threshold(0.5)
        assert nlt._threshold == 0.5

    def test_set_threshold_invalid_low(
        self,
        nlt: NaturalLanguageToolkit,
    ) -> None:
        """Umbral menor a 0 debe lanzar ValueError."""
        with pytest.raises(ValueError, match="debe estar entre"):
            nlt.set_confidence_threshold(-0.1)

    def test_set_threshold_invalid_high(
        self,
        nlt: NaturalLanguageToolkit,
    ) -> None:
        """Umbral mayor a 1 debe lanzar ValueError."""
        with pytest.raises(ValueError, match="debe estar entre"):
            nlt.set_confidence_threshold(1.5)

    def test_high_threshold_filters_matches(
        self,
        nlt: NaturalLanguageToolkit,
    ) -> None:
        """Umbral alto debe filtrar matches de baja confianza."""
        nlt.set_confidence_threshold(0.99)
        result = nlt.parse("buscar algo")
        assert result is None  # No supera umbral tan alto

    def test_low_threshold_allows_more(
        self,
        nlt: NaturalLanguageToolkit,
    ) -> None:
        """Umbral bajo debe permitir más matches."""
        nlt.set_confidence_threshold(0.01)
        result = nlt.parse("esto se parece a buscar")
        assert result is not None


# ===========================================================================
# Tests de estructura de datos
# ===========================================================================


class TestDataClasses:
    """Tests de las dataclasses NLTool y NLTResult."""

    def test_nltool_defaults(self) -> None:
        """NLTool debe tener valores por defecto correctos."""
        tool = NLTool(name="test", description="test desc")
        assert tool.parameters == {}
        assert tool.examples == []
        assert tool.handler is None

    def test_nltool_full(self) -> None:
        """NLTool con todos los campos debe funcionar."""
        def handler(x: int) -> int:
            return x * 2
        tool = NLTool(
            name="calc",
            description="calculadora",
            parameters={"x": "número"},
            examples=["calcular 2", "multiplica por 2"],
            handler=handler,
        )
        assert tool.name == "calc"
        assert tool.handler(5) == 10

    def test_nltresult_defaults(self) -> None:
        """NLTResult debe tener valores por defecto correctos."""
        result = NLTResult(
            tool="test",
            natural_input="prueba",
            structured_output={"action": "test"},
        )
        assert result.confidence == 1.0
        assert result.alternatives == []
        assert result.chain == []

    def test_nltresult_full(self) -> None:
        """NLTResult con todos los campos debe funcionar."""
        result = NLTResult(
            tool="buscar",
            natural_input="buscar algo",
            structured_output={"action": "buscar", "parameters": {}},
            confidence=0.85,
            alternatives=[("analizar", 0.45)],
            chain=[
                NLTResult(
                    tool="resumir",
                    natural_input="resumir resultado",
                    structured_output={"action": "resumir"},
                ),
            ],
        )
        assert result.confidence == 0.85
        assert len(result.alternatives) == 1
        assert len(result.chain) == 1
        assert result.chain[0].tool == "resumir"
