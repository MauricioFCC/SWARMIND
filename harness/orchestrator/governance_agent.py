"""
Governance Agent — Framework de supervision para decisiones autonomicas.

Implementa el marco de gobernanza para agentes autonomos:
- Registro de decisiones con contexto y justificacion
- Evaluacion de riesgos pre-deploy
- Trazabilidad completa de acciones de agentes
- Auditoria de decisiones post-hoc

Basado en principios de orquestacion agentica empresarial.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class DecisionStatus(str, Enum):
    PROPOSED = "proposed"
    APPROVED = "approved"
    REJECTED = "rejected"
    DEPLOYED = "deployed"
    ROLLED_BACK = "rolled_back"


class RiskLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class GovernanceRecord:
    """
    Registro de una decision de gobierno.
    
    Attributes:
        decision_id: ID unico de la decision.
        agent: Agente que tomo la decision.
        action: Accion propuesta.
        context: Contexto de la decision.
        alternatives: Alternativas consideradas.
        justification: Justificacion de la decision.
        risk_level: Nivel de riesgo evaluado.
        status: Estado actual de la decision.
        timestamp: Cuando se tomo la decision.
        approved_by: Quien aprobo (humano o sistema).
    """
    decision_id: str
    agent: str
    action: str
    context: str
    alternatives: List[str] = field(default_factory=list)
    justification: str = ""
    risk_level: RiskLevel = RiskLevel.LOW
    status: DecisionStatus = DecisionStatus.PROPOSED
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    approved_by: str = "system"


class GovernanceAgent:
    """
    Agente de gobernanza para supervision de decisiones autonomicas.
    
    Cada decision de agente se registra, evalua y audita.
    Las decisiones de alto riesgo requieren aprobacion humana.
    
    Usage:
        gov = GovernanceAgent()
        gov.register_decision("builder", "deploy_to_production", version="v2.1")
        if gov.evaluate_risk(decision_id) == RiskLevel.HIGH:
            gov.request_approval(decision_id)
        gov.approve(decision_id)
    """
    
    def __init__(self, log_dir: Optional[Path] = None):
        self._log_dir = log_dir or Path("data/governance")
        self._log_dir.mkdir(parents=True, exist_ok=True)
        self._records: Dict[str, GovernanceRecord] = {}
        self._load()

    def register_decision(
        self,
        agent: str,
        action: str,
        context: str = "",
        alternatives: Optional[List[str]] = None,
        justification: str = "",
    ) -> str:
        """
        Registrar una decision de un agente.
        
        Args:
            agent: Agente que toma la decision.
            action: Accion propuesta.
            context: Contexto situacional.
            alternatives: Alternativas consideradas.
            justification: Justificacion de la decision.
            
        Returns:
            ID de la decision registrada.
        """
        import uuid
        decision_id = str(uuid.uuid4())[:8]
        
        record = GovernanceRecord(
            decision_id=decision_id,
            agent=agent,
            action=action,
            context=context,
            alternatives=alternatives or [],
            justification=justification,
        )
        
        self._records[decision_id] = record
        self._save()
        logger.info(f"Governance: decision {decision_id} registered by {agent}: {action}")
        return decision_id

    def evaluate_risk(self, decision_id: str) -> RiskLevel:
        """
        Evaluar el nivel de riesgo de una decision.
        
        Args:
            decision_id: ID de la decision.
            
        Returns:
            Nivel de riesgo evaluado.
        """
        record = self._records.get(decision_id)
        if not record:
            return RiskLevel.LOW
        
        risk_score = 0
        
        # Factores que aumentan el riesgo
        high_risk_actions = [
            "deploy", "delete", "drop", "alter", "modify_production",
            "change_config", "restart_service", "rollback",
        ]
        for action in high_risk_actions:
            if action in record.action.lower():
                risk_score += 2
        
        # Acciones sin alternativas son mas riesgosas
        if not record.alternatives:
            risk_score += 1
        
        # Sin justificacion aumenta el riesgo
        if not record.justification:
            risk_score += 1
        
        # Clasificar riesgo
        if risk_score >= 5:
            return RiskLevel.CRITICAL
        elif risk_score >= 3:
            return RiskLevel.HIGH
        elif risk_score >= 1:
            return RiskLevel.MEDIUM
        return RiskLevel.LOW

    def approve(self, decision_id: str, approved_by: str = "system") -> bool:
        """
        Aprobar una decision.
        
        Args:
            decision_id: ID de la decision.
            approved_by: Quien aprueba.
            
        Returns:
            True si se aprobo correctamente.
        """
        record = self._records.get(decision_id)
        if not record:
            return False
        
        record.status = DecisionStatus.APPROVED
        record.approved_by = approved_by
        self._save()
        logger.info(f"Governance: decision {decision_id} approved by {approved_by}")
        return True

    def reject(self, decision_id: str, reason: str = "") -> bool:
        """
        Rechazar una decision.
        
        Args:
            decision_id: ID de la decision.
            reason: Motivo del rechazo.
            
        Returns:
            True si se rechazo correctamente.
        """
        record = self._records.get(decision_id)
        if not record:
            return False
        
        record.status = DecisionStatus.REJECTED
        record.justification = reason
        self._save()
        logger.info(f"Governance: decision {decision_id} rejected: {reason}")
        return True

    def get_pending(self) -> List[GovernanceRecord]:
        """Obtener decisiones pendientes de aprobacion."""
        return [r for r in self._records.values() if r.status == DecisionStatus.PROPOSED]

    def get_history(self, agent: Optional[str] = None) -> List[GovernanceRecord]:
        """Obtener historial de decisiones."""
        if agent:
            return [r for r in self._records.values() if r.agent == agent]
        return list(self._records.values())

    def _save(self) -> None:
        path = self._log_dir / "governance_log.json"
        data = {k: {
            "decision_id": v.decision_id,
            "agent": v.agent,
            "action": v.action,
            "context": v.context,
            "alternatives": v.alternatives,
            "justification": v.justification,
    "risk_level": v.risk_level.value if hasattr(v.risk_level, 'value') else v.risk_level,
    "status": v.status.value if hasattr(v.status, 'value') else v.status,
            "timestamp": v.timestamp,
            "approved_by": v.approved_by,
        } for k, v in self._records.items()}
        path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

    def _load(self) -> None:
        path = self._log_dir / "governance_log.json"
        if path.exists():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                for k, v in data.items():
                    v['risk_level'] = RiskLevel(v['risk_level']) if isinstance(v.get('risk_level'), str) else v.get('risk_level', RiskLevel.LOW)
                    v['status'] = DecisionStatus(v['status']) if isinstance(v.get('status'), str) else v.get('status', DecisionStatus.PROPOSED)
                    self._records[k] = GovernanceRecord(**v)
            except Exception as e:
                logger.warning(f"Failed to load governance log: {e}")
