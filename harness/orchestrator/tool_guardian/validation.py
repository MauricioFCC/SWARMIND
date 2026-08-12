"""ToolGuardian validation — mixin con validacion de llamadas a tools.

Extraccion mecanica del modulo original
``harness/orchestrator/tool_guardian.py`` (sin cambios de logica
ni firmas): validate_tool_call y validaciones contextuales.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from .constants import DANGEROUS_PATTERNS, OBFUSCATION_PATTERNS
from .models import ToolPolicy, ToolRiskLevel

logger = logging.getLogger(__name__)


class _ValidationMixin:
    """Mixin con la API publica de validacion de llamadas."""

    # ------------------------------------------------------------------
    # API publica — Validacion de llamadas
    # ------------------------------------------------------------------

    def validate_tool_call(
        self,
        tool_name: str,
        action: str,
        args: dict[str, Any] | None = None,
    ) -> bool:
        """Validar si una llamada a tool esta permitida segun la politica.

        Evalua la accion contra la politica de la tool, verificando
        acciones bloqueadas, permitidas y reglas adicionales (dominios,
        rutas, tiempo maximo).

        Args:
            tool_name: Nombre de la tool.
            action: Accion a ejecutar.
            args: Argumentos de la llamada (para validaciones
                  contextuales como rutas o dominios).

        Returns:
            True si la llamada esta permitida, False en caso contrario.
        """
        policy = self._policies.get(tool_name)
        if policy is None:
            logger.warning("ToolGuardian: sin politica para tool '%s'", tool_name)
            return False

        action_lower = action.lower()

        # Verificar acciones bloqueadas (prioridad maxima)
        for blocked in policy.blocked_actions:
            if blocked.lower() in action_lower:
                logger.warning(
                    "ToolGuardian: accion bloqueada '%s' en tool '%s'",
                    action, tool_name,
                )
                return False

        # Verificar acciones permitidas
        if action_lower in [a.lower() for a in policy.allowed_actions]:
            # Validaciones contextuales adicionales
            return not (args and not self._validate_contextual(policy, action_lower, args))

        # Modo estricto: solo acciones explicitamente permitidas
        if self._strict:
            logger.warning(
                "ToolGuardian: accion '%s' no permitida en tool '%s' (strict)",
                action, tool_name,
            )
            return False

        # Modo normal: acciones desconocidas se permiten con advertencia
        logger.info(
            "ToolGuardian: accion '%s' en tool '%s' no listada, permitida",
            action, tool_name,
        )
        return True

    def _validate_contextual(
        self,
        policy: ToolPolicy,
        action: str,
        args: dict[str, Any],
    ) -> bool:
        """Validaciones contextuales adicionales (rutas, dominios, etc.).

        Args:
            policy: Politica activa.
            action: Accion en minusculas.
            args: Argumentos de la llamada.

        Returns:
            True si las validaciones contextuales pasan.
        """
        # Validar rutas permitidas (filesystem)
        if policy.allowed_paths and "path" in args:
            path = args["path"]
            if not any(path.startswith(allowed) for allowed in policy.allowed_paths):
                logger.warning(
                    "ToolGuardian: ruta '%s' no permitida para tool '%s'",
                    path, policy.name,
                )
                return False

        # Validar dominios permitidos (network)
        if policy.allowed_domains and "url" in args:
            url = args["url"]
            domain_match = any(domain in url for domain in policy.allowed_domains)
            if not domain_match:
                logger.warning(
                    "ToolGuardian: dominio en '%s' no permitido para tool '%s'",
                    url, policy.name,
                )
                return False

        return True

    def analyze_tool(self, tool_name: str, tool_code: str) -> ToolRiskLevel:
        """Analiza el riesgo de una tool mediante analisis estatico.

        Es el Stage 4 del pipeline progresivo de caracterizacion.

        Args:
            tool_name: Nombre de la tool (para contexto).
            tool_code: Codigo fuente de la tool.

        Returns:
            ToolRiskLevel: SAFE, SUSPICIOUS o MALICIOUS.
        """
        return self._analyze_tool_risk(tool_name, tool_code)

    def _analyze_tool_risk(self, tool_name: str, tool_code: str) -> ToolRiskLevel:
        """Realiza analisis estatico basado en patrones peligrosos y
        ofuscacion. Es el Stage 4 del pipeline progresivo.

        Args:
            tool_name: Nombre de la tool (para contexto).
            tool_code: Codigo fuente de la tool.

        Returns:
            ToolRiskLevel: SAFE, SUSPICIOUS o MALICIOUS.
        """
        if not tool_code or not tool_code.strip():
            logger.info("ToolGuardian: tool '%s' sin codigo, SAFE", tool_name)
            return ToolRiskLevel.SAFE

        risk_score = 0
        matched_patterns: list[str] = []

        # Analizar patrones peligrosos
        for pattern in DANGEROUS_PATTERNS:
            matches = re.findall(pattern, tool_code, re.IGNORECASE)
            if matches:
                count = len(matches)
                risk_score += count * 2
                matched_patterns.append(pattern)

        # Analizar ofuscacion
        for ob_pattern in OBFUSCATION_PATTERNS:
            if re.search(ob_pattern, tool_code, re.IGNORECASE):
                risk_score += 3
                matched_patterns.append(ob_pattern)

        # Penalizar si no hay docstring (falta de transparencia)
        if '"""' not in tool_code and "'''" not in tool_code:
            risk_score += 1

        # Penalizar codigo excesivamente denso (menos de 50% de lineas en blanco/comentarios)
        total_lines = tool_code.strip().split("\n")
        code_no_comment = [line for line in total_lines if line.strip() and not line.strip().startswith("#")]
        if len(total_lines) > 20 and len(code_no_comment) / len(total_lines) > 0.85:
            risk_score += 1

        if matched_patterns:
            logger.info(
                "ToolGuardian: tool '%s' matched %d patrones peligrosos",
                tool_name, len(matched_patterns),
            )

        # Asignar nivel de riesgo
        if risk_score >= 6:
            return ToolRiskLevel.MALICIOUS
        elif risk_score >= 3:
            return ToolRiskLevel.SUSPICIOUS
        return ToolRiskLevel.SAFE
