"""Gestion de reglas del GuardrailEngine.

Submodulo interno del paquete :mod:`harness.guardrails.guardrail_engine`.

Extraido de forma mecanica desde ``guardrail_engine.py`` (regla AGR: archivos
< 500 lineas). Define ``_RulesMixin`` con la carga de reglas built-in y la
API de gestion de reglas (add/remove/get). Los cuerpos son identicos al
original; solo cambia la ubicacion fisica del codigo.
"""

from __future__ import annotations

import logging

from harness.guardrails.builtin_rules import (
    anti_code_injection,
    anti_pii_leak,
    anti_prompt_injection,
    toxicity,
)
from harness.guardrails.builtin_rules import (
    max_length as _max_length_fn,
)
from harness.guardrails.builtin_rules import (
    tool_allowlist as _tool_allowlist_fn,
)
from harness.guardrails.guardrail_types import (
    GuardrailLayer,
    GuardrailRule,
    GuardrailSeverity,
    GuardrailVerdict,
)

logger = logging.getLogger(__name__)


class _RulesMixin:
    """Carga de reglas built-in y API de gestion de reglas del motor."""

    def _load_builtin_rules(self) -> None:
        """Carga las reglas built-in en cada capa del sistema.

        Las reglas se distribuyen asi:
            INPUT:    anti_prompt_injection, max_length, toxicity
            OUTPUT:   anti_code_injection, anti_pii_leak, max_length, toxicity
            CONTENT:  anti_pii_leak, anti_code_injection, toxicity
            TOOL:     tool_allowlist (wrapper)
            POLICY:   governance_constraints (wrapper)

        Raises:
            RuntimeError: Si hay conflicto de nombres al cargar reglas.
        """
        # Capa 1: Input Guardrails
        self._add_rule_unchecked(GuardrailRule(
            name="anti_prompt_injection",
            layer=GuardrailLayer.INPUT,
            severity=GuardrailSeverity.CRITICAL,
            action=GuardrailVerdict.BLOCK,
            check_fn=anti_prompt_injection,
        ))
        self._add_rule_unchecked(GuardrailRule(
            name="input_max_length",
            layer=GuardrailLayer.INPUT,
            severity=GuardrailSeverity.MEDIUM,
            action=GuardrailVerdict.FLAG,
            check_fn=lambda t: _max_length_fn(t, max_tokens=8192),
        ))
        self._add_rule_unchecked(GuardrailRule(
            name="input_toxicity",
            layer=GuardrailLayer.INPUT,
            severity=GuardrailSeverity.HIGH,
            action=GuardrailVerdict.FLAG,
            check_fn=toxicity,
        ))

        # Capa 2: Output Guardrails
        self._add_rule_unchecked(GuardrailRule(
            name="output_code_injection",
            layer=GuardrailLayer.OUTPUT,
            severity=GuardrailSeverity.CRITICAL,
            action=GuardrailVerdict.BLOCK,
            check_fn=anti_code_injection,
        ))
        self._add_rule_unchecked(GuardrailRule(
            name="output_pii_leak",
            layer=GuardrailLayer.OUTPUT,
            severity=GuardrailSeverity.HIGH,
            action=GuardrailVerdict.REWRITE,
            check_fn=anti_pii_leak,
        ))
        self._add_rule_unchecked(GuardrailRule(
            name="output_max_length",
            layer=GuardrailLayer.OUTPUT,
            severity=GuardrailSeverity.MEDIUM,
            action=GuardrailVerdict.FLAG,
            check_fn=lambda t: _max_length_fn(t, max_tokens=self._max_output_tokens),
        ))
        self._add_rule_unchecked(GuardrailRule(
            name="output_toxicity",
            layer=GuardrailLayer.OUTPUT,
            severity=GuardrailSeverity.HIGH,
            action=GuardrailVerdict.REWRITE,
            check_fn=toxicity,
        ))

        # Capa 3: Content Guardrails
        self._add_rule_unchecked(GuardrailRule(
            name="content_pii_leak",
            layer=GuardrailLayer.CONTENT,
            severity=GuardrailSeverity.HIGH,
            action=GuardrailVerdict.REWRITE,
            check_fn=anti_pii_leak,
        ))
        self._add_rule_unchecked(GuardrailRule(
            name="content_code_injection",
            layer=GuardrailLayer.CONTENT,
            severity=GuardrailSeverity.CRITICAL,
            action=GuardrailVerdict.BLOCK,
            check_fn=anti_code_injection,
        ))
        self._add_rule_unchecked(GuardrailRule(
            name="content_toxicity",
            layer=GuardrailLayer.CONTENT,
            severity=GuardrailSeverity.HIGH,
            action=GuardrailVerdict.FLAG,
            check_fn=toxicity,
        ))

        # Capa 4: Tool Guardrails (wrapper sobre ToolGuardian)
        self._add_rule_unchecked(GuardrailRule(
            name="tool_allowlist",
            layer=GuardrailLayer.TOOL,
            severity=GuardrailSeverity.CRITICAL,
            action=GuardrailVerdict.BLOCK,
            check_fn=lambda t: _tool_allowlist_fn(t, allowed_tools=self._allowed_tools),
        ))

        # Capa 5: Policy Guardrails (wrapper sobre GovernanceGuard)
        self._add_rule_unchecked(GuardrailRule(
            name="governance_constraints",
            layer=GuardrailLayer.POLICY,
            severity=GuardrailSeverity.HIGH,
            action=GuardrailVerdict.FLAG,
            check_fn=lambda t: self._check_governance(t),
        ))

    def _add_rule_unchecked(self, rule: GuardrailRule) -> None:
        """Agrega una regla sin validacion de duplicados (uso interno).

        Args:
            rule: Regla a agregar.
        """
        self._rules[rule.layer].append(rule)

    def add_rule(self, rule: GuardrailRule) -> None:
        """Agrega una regla personalizada al motor.

        La regla se asigna a su capa correspondiente. Si ya existe una
        regla con el mismo nombre en la misma capa, se sobrescribe.

        Args:
            rule: Regla a agregar.

        Raises:
            ValueError: Si el nombre de la regla esta vacio o si la capa
                no es valida.
        """
        if not rule.name or not rule.name.strip():
            raise ValueError("El nombre de la regla no puede estar vacio")

        with self._lock:
            self._rules[rule.layer] = [
                r for r in self._rules[rule.layer] if r.name != rule.name
            ]
            self._rules[rule.layer].append(rule)
            logger.info(
                "[GuardrailEngine] Regla '%s' agregada en capa %s",
                rule.name, rule.layer.value,
            )

    def remove_rule(self, name: str, layer: GuardrailLayer) -> bool:
        """Elimina una regla por nombre y capa.

        Args:
            name: Nombre de la regla a eliminar.
            layer: Capa donde buscar.

        Returns:
            True si se elimino correctamente, False si no se encontro.
        """
        with self._lock:
            initial_count: int = len(self._rules[layer])
            self._rules[layer] = [
                r for r in self._rules[layer] if r.name != name
            ]
            removed: bool = len(self._rules[layer]) < initial_count
            if removed:
                logger.info(
                    "[GuardrailEngine] Regla '%s' eliminada de capa %s",
                    name, layer.value,
                )
            return removed

    def get_rules(self, layer: GuardrailLayer | None = None) -> list[GuardrailRule]:
        """Obtiene las reglas de una capa especifica o todas.

        Args:
            layer: Capa a consultar. Si es None, retorna todas las reglas.

        Returns:
            Lista de reglas en la capa solicitada (o todas).
        """
        if layer is not None:
            return list(self._rules.get(layer, []))
        all_rules: list[GuardrailRule] = []
        for rules in self._rules.values():
            all_rules.extend(rules)
        return all_rules
