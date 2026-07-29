"""Tests para el sistema LegalVerifier — Framework Legal AI Enterprise (LuMay AI)."""
from __future__ import annotations

import pytest

from harness.memory_rag.legal_verifier import LegalAnswer, LegalSource, LegalVerifier


class TestLegalVerifier:
    """Suite de pruebas para LegalVerifier."""

    # ------------------------------------------------------------------
    # Fixtures de ayuda
    # ------------------------------------------------------------------

    @pytest.fixture
    def verifier(self) -> LegalVerifier:
        """Fixture: Verificador legal vacio."""
        return LegalVerifier()

    @pytest.fixture
    def colombia_source(self) -> LegalSource:
        """Fixture: Fuente legal colombiana vigente."""
        return LegalSource(
            title="Codigo Civil Colombiano",
            content="Art 1: ...",
            version="2.0",
            jurisdiction="Colombia",
            is_latest=True,
        )

    @pytest.fixture
    def mexico_source(self) -> LegalSource:
        """Fixture: Fuente legal mexicana."""
        return LegalSource(
            title="Codigo Civil Federal MX",
            content="Art 1: ...",
            version="1.0",
            jurisdiction="Mexico",
            is_latest=True,
        )

    @pytest.fixture
    def outdated_source(self) -> LegalSource:
        """Fixture: Fuente desactualizada."""
        return LegalSource(
            title="Decreto Obsoleto",
            content="...",
            version="0.5",
            jurisdiction="Colombia",
            is_latest=False,
        )

    # ------------------------------------------------------------------
    # Tests
    # ------------------------------------------------------------------

    def test_verify_valid_answer(
        self, verifier: LegalVerifier, colombia_source: LegalSource
    ) -> None:
        """Verifica que una respuesta con fuente valida pase la verificacion.

        Arrange: Fuente colombiana vigente registrada.
        Act: Se verifica respuesta con esa fuente.
        Assert: verified=True, confidence>=0.7, sin warnings.
        """
        answer = LegalAnswer(
            question="Cual es el art 1 del Codigo Civil?",
            answer="El Codigo Civil establece...",
            sources=[colombia_source],
            jurisdiction="Colombia",
        )
        result = verifier.verify(answer)

        assert result.verified is True
        assert result.confidence >= 0.7
        assert len(result.warnings) == 0

    def test_verify_no_sources(
        self, verifier: LegalVerifier
    ) -> None:
        """Verifica que una respuesta sin fuentes no pase verificacion.

        Arrange: Respuesta sin fuentes.
        Act: Se verifica.
        Assert: verified=False, warning de fuentes faltantes.
        """
        answer = LegalAnswer(
            question="Que dice la ley?",
            answer="No lo se.",
            sources=[],
        )
        result = verifier.verify(answer)

        assert result.verified is False
        assert result.confidence < 0.7
        assert any("fuentes" in w.lower() for w in result.warnings)

    def test_verify_jurisdiction_mismatch(
        self, verifier: LegalVerifier, mexico_source: LegalSource
    ) -> None:
        """Verifica que una respuesta con jurisdiccion diferente genere warning.

        Arrange: Respuesta con jurisdiccion Colombia pero fuente mexicana.
        Act: Se verifica.
        Assert: warning de jurisdiccion, verified=False.
        """
        answer = LegalAnswer(
            question="Aplicacion del Codigo Civil?",
            answer="Se aplica el codigo...",
            sources=[mexico_source],
            jurisdiction="Colombia",
        )
        result = verifier.verify(answer)

        assert any("jurisdiccion" in w.lower() for w in result.warnings)
        assert result.verified is False

    def test_verify_outdated_sources(
        self, verifier: LegalVerifier, outdated_source: LegalSource
    ) -> None:
        """Verifica que fuentes desactualizadas generen advertencia.

        Arrange: Fuente con is_latest=False.
        Act: Se verifica respuesta.
        Assert: warning de fuente desactualizada.
        """
        answer = LegalAnswer(
            question="Vigencia del decreto?",
            answer="El decreto establece...",
            sources=[outdated_source],
            jurisdiction="Colombia",
        )
        result = verifier.verify(answer)

        assert any("desactualizada" in w.lower() for w in result.warnings)
        assert result.verified is False

    def test_verify_multiple_warnings(
        self,
        verifier: LegalVerifier,
        mexico_source: LegalSource,
        outdated_source: LegalSource,
    ) -> None:
        """Verifica que multiples problemas generen warnings acumulativos.

        Arrange: Dos fuentes problemáticas (mexicana + desactualizada).
        Act: Se verifica respuesta con jurisdiccion Colombia.
        Assert: Al menos 2 warnings, confianza menor.
        """
        answer = LegalAnswer(
            question="Ley aplicable?",
            answer="Se aplican varias fuentes...",
            sources=[mexico_source, outdated_source],
            jurisdiction="Colombia",
        )
        result = verifier.verify(answer)

        assert len(result.warnings) >= 2
        assert result.confidence < 0.7

    def test_add_source_and_verify(
        self, verifier: LegalVerifier, colombia_source: LegalSource
    ) -> None:
        """Verifica que agregar fuentes al repositorio funcione.

        Arrange: Verificador vacio.
        Act: Se agrega fuente y se verifica respuesta usandola.
        Assert: verified=True.
        """
        verifier.add_source(colombia_source)
        answer = LegalAnswer(
            question="Que dice la ley?",
            answer="Respuesta correcta.",
            sources=[colombia_source],
            jurisdiction="Colombia",
        )
        result = verifier.verify(answer)

        assert result.verified is True

    def test_get_explainability_report_no_warnings(
        self, verifier: LegalVerifier, colombia_source: LegalSource
    ) -> None:
        """Verifica que el reporte de explicabilidad incluya toda la metadata.

        Arrange: Respuesta verificada sin advertencias.
        Act: Se genera reporte.
        Assert: Titulo, pregunta, confianza, fuentes presentes.
        """
        answer = LegalAnswer(
            question="Articulo 1?",
            answer="Respuesta.",
            sources=[colombia_source],
            jurisdiction="Colombia",
        )
        result = verifier.verify(answer)
        report = verifier.get_explainability_report(result)

        assert "Reporte de Explicabilidad Legal" in report
        assert answer.question in report
        assert "Confianza" in report
        assert colombia_source.title in report

    def test_get_explainability_report_with_warnings(
        self, verifier: LegalVerifier
    ) -> None:
        """Verifica que el reporte incluya advertencias cuando existen.

        Arrange: Respuesta sin fuentes (con advertencias).
        Act: Se genera reporte.
        Assert: Advertencias visibles en el reporte.
        """
        answer = LegalAnswer(
            question="Caso sin fuentes?",
            answer="No respaldado.",
            sources=[],
        )
        result = verifier.verify(answer)
        report = verifier.get_explainability_report(result)

        assert "Advertencias" in report
        assert "No hay fuentes" in report
        assert "Confianza: 70%" in report or "Confianza:" in report

    @pytest.mark.parametrize(
        "question,confidence_threshold",
        [
            ("Caso con fuente perfecta", 0.9),
            ("Caso sin fuentes", 0.6),
            ("Caso con fuente desactualizada", 0.8),
        ],
        ids=["perfect", "no_sources", "outdated"],
    )
    def test_verify_confidence_thresholds(
        self,
        verifier: LegalVerifier,
        colombia_source: LegalSource,
        outdated_source: LegalSource,
        question: str,
        confidence_threshold: float,
    ) -> None:
        """Verifica que los niveles de confianza se calculen correctamente.

        Parametriza 3 escenarios:
            - perfect: fuente valida -> confianza >= 0.9
            - no_sources: respuesta sin fuentes -> confianza <= 0.6
            - outdated: fuente desactualizada -> confianza <= 0.8

        Args:
            question: Pregunta parametrizada.
            confidence_threshold: Limite superior/inferior segun caso.
        """
        sources: list[LegalSource] = []
        if "perfect" in question:
            sources = [colombia_source]
        elif "outdated" in question:
            sources = [outdated_source]

        answer = LegalAnswer(
            question=question,
            answer="Respuesta de prueba.",
            sources=sources,
            jurisdiction="Colombia",
        )
        result = verifier.verify(answer)

        if "perfect" in question:
            assert result.confidence >= confidence_threshold
        else:
            assert result.confidence <= confidence_threshold
