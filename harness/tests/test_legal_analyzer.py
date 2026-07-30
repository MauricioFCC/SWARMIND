"""
Tests para LegalAnalyzer — NLP juridico colombiano.

Cobertura: extraccion de entidades, argumentos, clasificacion,
resumen y comparacion de documentos legales.
"""

from __future__ import annotations

import pytest

from harness.memory_rag.legal_analyzer import LegalAnalyzer

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def analyzer() -> LegalAnalyzer:
    """Fixture basico de LegalAnalyzer."""
    return LegalAnalyzer()


# ---------------------------------------------------------------------------
# Tests: Extraccion de entidades
# ---------------------------------------------------------------------------


class TestExtractEntities:
    """Suite de pruebas para extraccion de entidades juridicas."""

    def test_extract_normas(self, analyzer: LegalAnalyzer) -> None:
        """
        Extraer leyes, decretos y sentencias.
        
        Verifica que el patron reconoce:
        - Ley 100 de 1993
        - Decreto 410 de 1971
        - Sentencia C-123 de 2024
        - Constitucion Politica
        - Codigo Civil
        """
        text = (
            "La Ley 100 de 1993 establece el sistema de seguridad social. "
            "El Decreto 410 de 1971 expide el Codigo de Comercio. "
            "La Sentencia C-123 de 2024 fija precedente. "
            "La Constitucion Politica es norma de normas. "
            "El Codigo Civil regula las relaciones privadas."
        )
        entities = analyzer.extract_entities(text)
        normas = [e for e in entities if e.type == "norma"]
        texts = {e.text for e in normas}

        assert len(normas) >= 5, f"Esperaba >=5 normas, obtuve {len(normas)}"
        assert "Ley 100 de 1993" in texts
        assert "Decreto 410 de 1971" in texts
        assert "Sentencia C-123 de 2024" in texts
        assert "Constitucion Politica" in texts
        assert any("Codigo Civil" in t or "Código Civil" in t for t in texts)

    def test_extract_cortes(self, analyzer: LegalAnalyzer) -> None:
        """
        Extraer nombres de cortes y tribunales.
        
        Verifica:
        - Corte Constitucional
        - Corte Suprema de Justicia
        - Consejo de Estado
        - Juzgado 3
        - Tribunal Superior
        """
        text = (
            "La Corte Constitucional decidio la tutela. "
            "La Corte Suprema de Justicia conoce del recurso. "
            "El Consejo de Estado resuelve la nulidad. "
            "El Juzgado 3 Civil del Circuito admitio la demanda. "
            "El Tribunal Superior confirmo la sentencia."
        )
        entities = analyzer.extract_entities(text)
        cortes = [e for e in entities if e.type == "corte"]
        texts = {e.text for e in cortes}

        assert len(cortes) >= 4, f"Esperaba >=4 cortes, obtuve {len(cortes)}"
        assert "Corte Constitucional" in texts
        assert "Corte Suprema de Justicia" in texts
        assert "Consejo de Estado" in texts
        assert "Juzgado 3" in texts or "Juzgado  3" in texts
        assert "Tribunal Superior" in texts

    def test_extract_fechas(self, analyzer: LegalAnalyzer) -> None:
        """
        Extraer fechas en formato textual y numerico.
        
        Verifica:
        - 15 de enero de 2024
        - 2024/03/20
        """
        text = (
            "El auto fue proferido el 15 de enero de 2024. "
            "La demanda se presento el 2024/03/20."
        )
        entities = analyzer.extract_entities(text)
        fechas = [e for e in entities if e.type == "fecha"]
        texts = {e.text for e in fechas}

        assert len(fechas) >= 2, f"Esperaba >=2 fechas, obtuve {len(fechas)}"
        assert "15 de enero de 2024" in texts
        assert "2024/03/20" in texts


# ---------------------------------------------------------------------------
# Tests: Extraccion de argumentos
# ---------------------------------------------------------------------------


class TestExtractArguments:
    """Suite de pruebas para extraccion de argumentos juridicos."""

    def test_extract_arguments(self, analyzer: LegalAnalyzer) -> None:
        """
        Extraer argumentos juridicos de un texto estructurado.
        
        Verifica que se detecten premisas y conclusiones a partir
        de secciones numeradas.
        """
        text = (
            "II. FUNDAMENTOS JURIDICOS\n"
            "La Ley 100 de 1993 regula el tema. "
            "El Decreto 410 de 1971 es aplicable. "
            "Por tanto, la pretension debe ser concedida.\n\n"
            "III. ANALISIS\n"
            "La Sentencia C-123 de 2024 fija precedente. "
            "Se concluye que el actor tiene derecho."
        )
        arguments = analyzer.extract_arguments(text)

        assert len(arguments) >= 1, f"Esperaba >=1 argumento, obtuve {len(arguments)}"
        # Verificar que se extrajo al menos una premisa
        assert any(arg.premise_major for arg in arguments)
        # Verificar que hay una conclusion
        assert any(arg.conclusion for arg in arguments)


# ---------------------------------------------------------------------------
# Tests: Clasificacion de documentos
# ---------------------------------------------------------------------------


class TestClassifyDocument:
    """Suite de pruebas para clasificacion de documentos legales."""

    def test_classify_sentencia(self, analyzer: LegalAnalyzer) -> None:
        """
        Clasificar texto como sentencia.
        
        Verifica que palabras clave como 'sentencia', 'fallo', 'condena'
        llevan a la clasificacion 'sentencia'.
        """
        text = (
            "La sentencia condena al demandado al pago de perjuicios. "
            "El fallo de primera instancia sera apelado."
        )
        assert analyzer.classify_document(text) == "sentencia"

    def test_classify_demanda(self, analyzer: LegalAnalyzer) -> None:
        """
        Clasificar texto como demanda.
        
        Verifica que palabras clave como 'demanda', 'pretension'
        llevan a la clasificacion 'demanda'.
        """
        text = (
            "La demanda fue admitida por el juzgado. "
            "La pretension principal es la nulidad del acto."
        )
        assert analyzer.classify_document(text) == "demanda"

    def test_classify_contrato(self, analyzer: LegalAnalyzer) -> None:
        """
        Clasificar texto como contrato.
        
        Verifica que palabras clave como 'contrato', 'clausula'
        llevan a la clasificacion 'contrato'.
        """
        text = (
            "El contrato de prestacion de servicios incluye "
            "una clausula de confidencialidad."
        )
        assert analyzer.classify_document(text) == "contrato"

    def test_classify_norma(self, analyzer: LegalAnalyzer) -> None:
        """
        Clasificar texto como norma.
        
        Verifica que palabras clave como 'ley', 'decreto'
        llevan a la clasificacion 'norma'.
        """
        text = "La Ley 100 de 1993 establece el sistema de salud."
        assert analyzer.classify_document(text) == "norma"

    def test_classify_generico(self, analyzer: LegalAnalyzer) -> None:
        """
        Clasificar texto generico.
        
        Verifica que un texto sin palabras clave legales
        retorna 'documento_general'.
        """
        text = "El sistema operativo gestiona los recursos del computador."
        assert analyzer.classify_document(text) == "documento_general"


# ---------------------------------------------------------------------------
# Tests: Resumen
# ---------------------------------------------------------------------------


class TestSummarize:
    """Suite de pruebas para generacion de resumenes."""

    def test_summarize(self, analyzer: LegalAnalyzer) -> None:
        """
        Generar resumen de un documento legal.
        
        Verifica que el resumen:
        - No excede la longitud maxima
        - Contiene palabras clave relevantes
        """
        text = (
            "OBJETO: La presente demanda tiene por objeto "
            "la declaracion de nulidad del acto administrativo. "
            "La pretension se fundamenta en la Ley 100 de 1993. "
            "El Decreto 410 de 1971 resulta aplicable. "
            "Se solicita condena en costas. "
            "Fallo de primera instancia favorable al demandante."
        )
        summary = analyzer.summarize(text, max_length=200)

        assert len(summary) <= 200, f"Resumen excede 200 chars: {len(summary)}"
        assert "OBJETO" in summary or "objeto" in summary.lower()

    def test_summarize_empty(self, analyzer: LegalAnalyzer) -> None:
        """
        Resumir texto vacio retorna cadena vacia.
        """
        assert analyzer.summarize("") == ""


# ---------------------------------------------------------------------------
# Tests: Comparacion de documentos
# ---------------------------------------------------------------------------


class TestCompareDocuments:
    """Suite de pruebas para comparacion de documentos."""

    def test_compare_documents(self, analyzer: LegalAnalyzer) -> None:
        """
        Comparar dos documentos legales.
        
        Verifica que el resultado contiene:
        - shared_entities (list)
        - unique_entities_1 (list)
        - unique_entities_2 (list)
        - similarity (float)
        - type_1 y type_2 (str)
        """
        doc1 = (
            "La Corte Constitucional en Sentencia C-123 de 2024 "
            "aplico la Ley 100 de 1993."
        )
        doc2 = (
            "La Corte Constitucional en Sentencia T-456 de 2024 "
            "aplico el Decreto 410 de 1971."
        )
        result = analyzer.compare_documents(doc1, doc2)

        assert "shared_entities" in result
        assert "unique_entities_1" in result
        assert "unique_entities_2" in result
        assert "similarity" in result
        assert "type_1" in result
        assert "type_2" in result
        # Comparten "Corte Constitucional"
        assert "Corte Constitucional" in result["shared_entities"]
        assert isinstance(result["similarity"], float)
        assert 0.0 <= result["similarity"] <= 1.0


# ---------------------------------------------------------------------------
# Tests: Casos borde
# ---------------------------------------------------------------------------


class TestEdgeCases:
    """Suite de pruebas para casos borde."""

    def test_empty_text(self, analyzer: LegalAnalyzer) -> None:
        """
        Texto vacio retorna listas vacias y tipo generico.
        
        Verifica que extract_entities, extract_arguments,
        classify_document y compare_documents manejan texto vacio.
        """
        assert analyzer.extract_entities("") == []
        assert analyzer.extract_arguments("") == []
        assert analyzer.classify_document("") == "documento_general"

        result = analyzer.compare_documents("", "")
        assert result["shared_entities"] == []
        assert result["similarity"] == 0.0
