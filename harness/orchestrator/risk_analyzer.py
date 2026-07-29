"""
RiskAnalyzer — Identificacion y analisis de riesgos emergentes.

Basado en CRO Forum 2026: Major Trends and Emerging Risk Radar.
Analiza riesgos tecnologicos, geopoliticos, climaticos, de salud y financieros.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class RiskDomain(str, Enum):
    TECHNOLOGY = "technology"
    GEOPOLITICS = "geopolitics"
    CLIMATE = "climate"
    HEALTH = "health"
    FINANCE = "finance"


class RiskLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class Risk:
    """Representa un riesgo identificado con su dominio, nivel y medidas de mitigacion."""

    name: str
    domain: RiskDomain
    description: str
    level: RiskLevel = RiskLevel.MEDIUM
    impact_score: float = 0.5
    likelihood: float = 0.5
    mitigations: List[str] = field(default_factory=list)


class RiskAnalyzer:
    """Analizador de riesgos emergentes multi-dominio con registro y consulta."""

    def __init__(self):
        self._risks: List[Risk] = []
        self._register_defaults()

    def _register_defaults(self) -> None:
        """Registra riesgos por defecto basados en tendencias CRO Forum 2026."""
        defaults = [
            Risk(
                "AI Concentration", RiskDomain.TECHNOLOGY,
                "Concentracion de poder en pocos proveedores cloud/AI",
                RiskLevel.HIGH, 0.8, 0.7,
                ["Diversificar proveedores", "Estandares abiertos"],
            ),
            Risk(
                "Cyber Systemic Failure", RiskDomain.TECHNOLOGY,
                "Fallo sistemico por dependencia tecnologica",
                RiskLevel.CRITICAL, 0.9, 0.6,
                ["Arquitectura resiliente", "Backups descentralizados"],
            ),
            Risk(
                "Supply Chain Disruption", RiskDomain.GEOPOLITICS,
                "Disrupcion por guerra, sanciones o aranceles",
                RiskLevel.HIGH, 0.8, 0.8,
                ["Diversificacion de proveedores", "Inventarios de seguridad"],
            ),
            Risk(
                "Climate Damage", RiskDomain.CLIMATE,
                "Danos climaticos que aumentan presion sobre seguros",
                RiskLevel.HIGH, 0.7, 0.9,
                ["Adaptacion climatica", "Modelos de riesgo actualizados"],
            ),
            Risk(
                "Debt Crisis", RiskDomain.FINANCE,
                "Crisis de deuda global con alto impacto",
                RiskLevel.CRITICAL, 0.9, 0.5,
                ["Gestion de liquidez", "Cobertura de riesgos"],
            ),
        ]
        self._risks.extend(defaults)

    def get_risks(
        self,
        domain: Optional[RiskDomain] = None,
        min_level: Optional[RiskLevel] = None,
    ) -> List[Risk]:
        """Obtiene riesgos filtrados opcionalmente por dominio y nivel minimo.

        Args:
            domain: Filtro por dominio de riesgo. Si es None, incluye todos.
            min_level: Nivel minimo de riesgo (inclusivo). Si es None, incluye todos.

        Returns:
            Lista de riesgos que cumplen los filtros aplicados.
        """
        results = self._risks
        if domain:
            results = [r for r in results if r.domain == domain]
        if min_level:
            levels = list(RiskLevel)
            min_idx = levels.index(min_level)
            results = [r for r in results if levels.index(r.level) >= min_idx]
        return results

    def add_risk(self, risk: Risk) -> None:
        """Agrega un nuevo riesgo al analizador.

        Args:
            risk: Instancia de Risk a registrar.
        """
        self._risks.append(risk)

    def get_summary(self) -> Dict[str, Any]:
        """Retorna un resumen estadistico de los riesgos registrados.

        Returns:
            Diccionario con total de riesgos, conteo por dominio y por nivel.
        """
        return {
            "total_risks": len(self._risks),
            "by_domain": {
                d.value: sum(1 for r in self._risks if r.domain == d)
                for d in RiskDomain
            },
            "by_level": {
                l.value: sum(1 for r in self._risks if r.level == l)
                for l in RiskLevel
            },
        }
