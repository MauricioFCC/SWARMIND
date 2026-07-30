"""Tests para GovernanceAgent — supervision de decisiones."""
from __future__ import annotations

from pathlib import Path

import pytest

from harness.orchestrator.governance_agent import GovernanceAgent, RiskLevel


@pytest.fixture
def gov(tmp_path: Path) -> GovernanceAgent:
    return GovernanceAgent(log_dir=tmp_path)


class TestRegister:
    """Registro de decisiones."""

    def test_register_decision(self, gov: GovernanceAgent) -> None:
        """Registrar decision debe retornar ID."""
        decision_id = gov.register_decision("builder", "implement_api")
        assert len(decision_id) == 8

    def test_register_with_context(self, gov: GovernanceAgent) -> None:
        """Decision con contexto debe guardarlo."""
        gov.register_decision("scientist", "research_paper", context="analisis de transformers")
        history = gov.get_history("scientist")
        assert len(history) == 1


class TestRiskEvaluation:
    """Evaluacion de riesgo."""

    def test_low_risk(self, gov: GovernanceAgent) -> None:
        """Accion simple debe ser low risk."""
        did = gov.register_decision("builder", "refactor_module",
                                     justification="mejora de legibilidad",
                                     alternatives=["dejarlo igual", "reescribir"])
        assert gov.evaluate_risk(did) == RiskLevel.LOW

    def test_high_risk_deploy(self, gov: GovernanceAgent) -> None:
        """Deploy a produccion debe ser high risk."""
        did = gov.register_decision("builder", "deploy_to_production")
        assert gov.evaluate_risk(did) == RiskLevel.HIGH

    def test_critical_risk(self, gov: GovernanceAgent) -> None:
        """Accion peligrosa y sin alternativas debe ser high+."""
        did = gov.register_decision("builder", "delete_database")
        risk = gov.evaluate_risk(did)
        assert risk in [RiskLevel.HIGH, RiskLevel.CRITICAL]


class TestApproval:
    """Aprobacion de decisiones."""

    def test_approve_decision(self, gov: GovernanceAgent) -> None:
        """Aprobar decision debe cambiar estado."""
        did = gov.register_decision("builder", "implement_api")
        assert gov.approve(did) is True
        history = gov.get_history()
        assert history[0].status.value == "approved"

    def test_reject_decision(self, gov: GovernanceAgent) -> None:
        """Rechazar decision debe cambiar estado."""
        did = gov.register_decision("builder", "implement_api")
        assert gov.reject(did, "falta informacion") is True
        history = gov.get_history()
        assert history[0].status.value == "rejected"

    def test_get_pending(self, gov: GovernanceAgent) -> None:
        """Decisiones pendientes deben listarse."""
        gov.register_decision("builder", "task_a")
        gov.register_decision("builder", "task_b")
        pending = gov.get_pending()
        assert len(pending) == 2
