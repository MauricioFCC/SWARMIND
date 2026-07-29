"""
Tests del modulo RiskAnalyzer — cobertura de registro, filtros, resumen y casos borde.

Cubre: defaults, filtros por dominio/nivel, insercion, resumen estadistico, enums, edge cases.
"""
import pytest
from harness.orchestrator.risk_analyzer import (
    Risk,
    RiskAnalyzer,
    RiskDomain,
    RiskLevel,
)


class TestRiskDomain:
    """Tests del enum RiskDomain."""

    def test_domain_values(self) -> None:
        """Verifica que RiskDomain contenga los 5 dominios esperados."""
        expected = {"technology", "geopolitics", "climate", "health", "finance"}
        actual = {d.value for d in RiskDomain}
        assert actual == expected, f"Dominios incorrectos: {actual}"


class TestRiskLevel:
    """Tests del enum RiskLevel."""

    def test_level_ordering(self) -> None:
        """Verifica que RiskLevel tenga orden creciente LOW < MEDIUM < HIGH < CRITICAL."""
        levels = list(RiskLevel)
        assert levels == [RiskLevel.LOW, RiskLevel.MEDIUM, RiskLevel.HIGH, RiskLevel.CRITICAL]


class TestRiskDataclass:
    """Tests del dataclass Risk."""

    def test_default_values(self) -> None:
        """Verifica que Risk asigne valores por defecto correctos."""
        r = Risk(name="Test", domain=RiskDomain.HEALTH, description="Riesgo de prueba")
        assert r.level == RiskLevel.MEDIUM
        assert r.impact_score == 0.5
        assert r.likelihood == 0.5
        assert r.mitigations == []

    def test_custom_values(self) -> None:
        """Verifica que Risk acepte valores personalizados en todos los campos."""
        r = Risk(
            name="Custom Risk",
            domain=RiskDomain.FINANCE,
            description="Riesgo personalizado",
            level=RiskLevel.CRITICAL,
            impact_score=0.99,
            likelihood=0.85,
            mitigations=["Mit1", "Mit2"],
        )
        assert r.name == "Custom Risk"
        assert r.domain == RiskDomain.FINANCE
        assert r.level == RiskLevel.CRITICAL
        assert r.impact_score == 0.99
        assert r.likelihood == 0.85
        assert r.mitigations == ["Mit1", "Mit2"]


class TestRiskAnalyzer:
    """Tests del analizador de riesgos RiskAnalyzer."""

    def setup_method(self) -> None:
        """Inicializa una instancia fresca de RiskAnalyzer por test."""
        self.analyzer = RiskAnalyzer()

    # --- Test 1 ---
    def test_default_risks_count(self) -> None:
        """Verifica que se registren exactamente 5 riesgos por defecto."""
        assert len(self.analyzer._risks) == 5

    # --- Test 2 ---
    def test_get_risks_no_filters(self) -> None:
        """Verifica que get_risks sin filtros retorne todos los riesgos."""
        all_risks = self.analyzer.get_risks()
        assert len(all_risks) == 5

    # --- Test 3 ---
    def test_get_risks_filter_by_domain(self) -> None:
        """Verifica el filtro por dominio de riesgo."""
        tech_risks = self.analyzer.get_risks(domain=RiskDomain.TECHNOLOGY)
        assert len(tech_risks) == 2
        for r in tech_risks:
            assert r.domain == RiskDomain.TECHNOLOGY

        climate_risks = self.analyzer.get_risks(domain=RiskDomain.CLIMATE)
        assert len(climate_risks) == 1
        assert climate_risks[0].name == "Climate Damage"

    # --- Test 4 ---
    def test_get_risks_filter_by_min_level(self) -> None:
        """Verifica el filtro por nivel minimo de riesgo."""
        critical = self.analyzer.get_risks(min_level=RiskLevel.CRITICAL)
        assert len(critical) == 2
        for r in critical:
            assert r.level == RiskLevel.CRITICAL

        high_and_above = self.analyzer.get_risks(min_level=RiskLevel.HIGH)
        assert len(high_and_above) == 5
        for r in high_and_above:
            assert r.level in (RiskLevel.HIGH, RiskLevel.CRITICAL)

    # --- Test 5 ---
    def test_get_risks_filter_by_domain_and_level(self) -> None:
        """Verifica el filtro combinado por dominio y nivel minimo."""
        result = self.analyzer.get_risks(
            domain=RiskDomain.TECHNOLOGY, min_level=RiskLevel.CRITICAL
        )
        assert len(result) == 1
        assert result[0].name == "Cyber Systemic Failure"

    # --- Test 6 ---
    def test_add_risk(self) -> None:
        """Verifica que add_risk incorpore correctamente un nuevo riesgo."""
        new_risk = Risk(
            name="Pandemic Outbreak",
            domain=RiskDomain.HEALTH,
            description="Nueva pandemia con alto impacto global",
            level=RiskLevel.CRITICAL,
            impact_score=0.95,
            likelihood=0.4,
            mitigations=["Vigilancia epidemiologica", "Reservas estrategicas"],
        )
        self.analyzer.add_risk(new_risk)
        assert len(self.analyzer._risks) == 6

        health_risks = self.analyzer.get_risks(domain=RiskDomain.HEALTH)
        assert len(health_risks) == 1
        assert health_risks[0].name == "Pandemic Outbreak"

    # --- Test 7 ---
    def test_get_summary_structure(self) -> None:
        """Verifica que get_summary retorne la estructura esperada con valores correctos."""
        summary = self.analyzer.get_summary()
        assert summary["total_risks"] == 5
        assert summary["by_domain"]["technology"] == 2
        assert summary["by_domain"]["geopolitics"] == 1
        assert summary["by_domain"]["climate"] == 1
        assert summary["by_domain"]["finance"] == 1
        assert summary["by_domain"]["health"] == 0
        assert summary["by_level"]["critical"] == 2
        assert summary["by_level"]["high"] == 3
        assert summary["by_level"]["medium"] == 0
        assert summary["by_level"]["low"] == 0

    # --- Test 8 ---
    def test_get_risks_domain_no_match(self) -> None:
        """Verifica que filtrar por dominio sin riesgos retorne lista vacia."""
        health_risks = self.analyzer.get_risks(domain=RiskDomain.HEALTH)
        assert health_risks == []

    # --- Test 9 ---
    def test_get_risks_min_level_low(self) -> None:
        """Verifica que min_level=LOW retorne todos los riesgos."""
        all_risks = self.analyzer.get_risks(min_level=RiskLevel.LOW)
        assert len(all_risks) == 5

    # --- Test 10 ---
    def test_get_summary_after_add(self) -> None:
        """Verifica que el resumen se actualice correctamente al agregar riesgos."""
        self.analyzer.add_risk(
            Risk("Regulatory Shift", RiskDomain.GEOPOLITICS, "Cambio regulatorio", RiskLevel.MEDIUM, 0.6, 0.5)
        )
        self.analyzer.add_risk(
            Risk("Bio Threat", RiskDomain.HEALTH, "Amenaza biologica", RiskLevel.HIGH, 0.7, 0.3)
        )
        summary = self.analyzer.get_summary()
        assert summary["total_risks"] == 7
        assert summary["by_domain"]["geopolitics"] == 2
        assert summary["by_domain"]["health"] == 1
        assert summary["by_level"]["medium"] == 1
        assert summary["by_level"]["high"] == 4
        assert summary["by_level"]["critical"] == 2
