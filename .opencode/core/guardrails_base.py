"""
Base types for the guardrails system.
Extracted from guardrails.py to break circular imports with guardrails_checks.py.
"""
from dataclasses import dataclass
from enum import Enum
from typing import Any


class GuardrailSeverity(Enum):
    """Niveles de severidad para resultados de guardrails."""
    BLOCK = "block"      # Detener ejecucion inmediatamente
    WARN = "warn"        # Advertir pero continuar
    INFO = "info"        # Solo registrar para observabilidad


@dataclass
class GuardrailResult:
    """Resultado de una verificacion de guardrail."""
    passed: bool
    severity: GuardrailSeverity
    message: str
    suggestion: str | None = None
    rule_id: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Convierte el resultado a diccionario para serializacion."""
        return {
            "passed": self.passed,
            "severity": self.severity.value,
            "message": self.message,
            "suggestion": self.suggestion,
            "rule_id": self.rule_id
        }
