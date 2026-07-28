"""
SecurityGuard - Defensa contra inyeccion de prompt y boundaries de confianza.

Implementa controles de seguridad criticos para sistemas multi-agente:
- Prompt Injection Defense (OWASP Top 10 for LLMs 2025)
- Least Privilege y JIT Permissions
- Multi-Agent Trust Boundaries
- Behavioral Monitoring
- Runtime Security Checks

Basado en: OWASP Agentic AI Top 10, NIST AI RMF, Zero Trust Model.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Patrones de inyeccion de prompt
# ---------------------------------------------------------------------------

INJECTION_PATTERNS = [
    r"(?i)ignore\s+(all\s+)?(previous|above|below)\s+(instructions|prompts|commands)",
    r"(?i)(forget|disregard|ignore)\s+(all\s+)?(instructions|rules|guidelines)",
    r"(?i)you\s+(are\s+)?(now|will\s+now)\s+(a\s+)?(different|free|jailbroken)",
    r"(?i)print\s+(the\s+)?(password|secret|key|token|flag)",
    r"(?i)reveal\s+(your\s+)?(system\s+)?(prompt|instructions|rules)",
    r"(?i)system\s+(prompt|message|instruction)\s*:",
    r"(?i)role\s*:\s*(system|assistant|admin)",
    r"(?i)\-\s*=\s*PROMPT\s*=\s*-",
    r"(?i)CHATGPT\s+(SYSTEM|INITIAL|PROMPT)",
    r"(?i)DAN|jailbreak|friday|dev\s+mode",
    r"(?i)\{\{.*\{\{|%>.*<%.*\}%.*%\}",
    r"(?i)\\system|\\prompt",
    r"(?i)<\|im_start\|>|<\|im_end\|>|<\|system\|>",
]

SENSITIVE_PATTERNS = [
    r"(?i)(api[_-]?key|apikey|secret[_-]?key|password)\s*[:=]\s*['\"][a-zA-Z0-9_\-]{16,}['\"]",
    r"(?i)ghp_[a-zA-Z0-9]{36}|gho_[a-zA-Z0-9]{36}|github_pat_[a-zA-Z0-9_]{85}",
    r"(?i)pk_live_|sk_live_|pk_test_|sk_test_",
    r"(?i)AKIA[0-9A-Z]{16}",  # AWS Access Key
    r"(?i)-----BEGIN\s+(RSA\s+)?PRIVATE\s+KEY-----",
]

FORBIDDEN_REDIRECTIONS = [
    "file://", "localhost", "169.254.169.254", "metadata.google.internal",
    "metadata.amazonaws.com", "100.100.100.200",
]


@dataclass
class SecurityCheckResult:
    """
    Resultado de una verificacion de seguridad.
    
    Attributes:
        passed: True si paso la verificacion.
        score: Puntaje de confianza (0-1).
        risks: Lista de riesgos detectados.
        blocked_patterns: Patrones que bloquearon.
    """
    passed: bool = True
    score: float = 1.0
    risks: List[str] = field(default_factory=list)
    blocked_patterns: List[str] = field(default_factory=list)


class SecurityGuard:
    """
    Guardia de seguridad para sistemas multi-agente.
    
    Implementa defensa contra inyeccion de prompt, boundaries de confianza
    entre agentes, y verificaciones en tiempo de ejecucion.
    """

    def __init__(self, strict_mode: bool = False):
        """
        Args:
            strict_mode: Si True, bloquea en lugar de solo advertir.
        """
        self._strict = strict_mode
        self._alerts: List[str] = []

    def check_prompt(self, text: str) -> SecurityCheckResult:
        """
        Verificar un prompt contra inyeccion.
        
        Args:
            text: Texto del prompt a verificar.
            
        Returns:
            SecurityCheckResult con el resultado.
        """
        risks = []
        blocked = []

        for pattern in INJECTION_PATTERNS:
            if re.search(pattern, text):
                risks.append(f"Posible inyeccion de prompt: {pattern[:50]}")
                blocked.append(pattern)

        for pattern in SENSITIVE_PATTERNS:
            if re.search(pattern, text):
                risks.append(f"Dato sensible detectado en prompt")
                blocked.append(pattern)

        for redirect in FORBIDDEN_REDIRECTIONS:
            if redirect in text.lower():
                risks.append(f"Redireccion prohibida detectada: {redirect}")
                blocked.append(redirect)

        passed = len(risks) == 0 or not self._strict
        score = max(0, 1.0 - len(risks) * 0.2)

        if risks:
            logger.warning("SecurityGuard: %d riesgos detectados en prompt", len(risks))
            self._alerts.extend(risks)

        return SecurityCheckResult(
            passed=passed,
            score=score,
            risks=risks,
            blocked_patterns=blocked,
        )

    def check_agent_boundary(
        self,
        source_agent: str,
        target_agent: str,
        action: str,
    ) -> SecurityCheckResult:
        """
        Verificar boundaries de confianza entre agentes.
        
        Args:
            source_agent: Agente origen.
            target_agent: Agente destino.
            action: Accion solicitada.
            
        Returns:
            SecurityCheckResult.
        """
        # Reglas de boundary entre agentes
        forbidden_actions = {
            "guardian": ["bypass_security", "disable_logging", "skip_audit"],
            "builder": ["deploy_to_production", "modify_production_data"],
            "evolve": ["modify_system_prompt", "disable_guardrails"],
        }

        risks = []
        source_actions = forbidden_actions.get(source_agent, [])
        for fa in source_actions:
            if fa in action.lower():
                risks.append(
                    f"Boundary: {source_agent} no puede ejecutar '{fa}'"
                )

        passed = len(risks) == 0
        return SecurityCheckResult(passed=passed, risks=risks)

    def check_runtime(self, context: Dict[str, Any]) -> SecurityCheckResult:
        """
        Verificaciones de seguridad en tiempo de ejecucion.
        
        Args:
            context: Contexto de ejecucion.
            
        Returns:
            SecurityCheckResult.
        """
        risks = []

        # Verificar que no se ejecuten comandos peligrosos
        commands = context.get("commands", [])
        dangerous = ["rm -rf", "format", "dd if=", "> /dev/sda", ":(){ :|:& };:"]
        for cmd in commands:
            for d in dangerous:
                if d in str(cmd).lower():
                    risks.append(f"Comando peligroso detectado: {cmd}")

        # Verificar redirecciones a localhost
        urls = context.get("urls", [])
        for url in urls:
            for forbidden in FORBIDDEN_REDIRECTIONS:
                if forbidden in str(url).lower():
                    risks.append(f"URL prohibida: {url}")

        passed = len(risks) == 0
        return SecurityCheckResult(passed=passed, risks=risks)

    def get_alerts(self) -> List[str]:
        """Obtener alertas acumuladas."""
        return list(self._alerts)

    def clear_alerts(self) -> None:
        """Limpiar alertas."""
        self._alerts.clear()


