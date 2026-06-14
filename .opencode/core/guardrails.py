"""
Guardrail Pipeline: Pre & Post execution checks for architecture, security, commits & docs.
Enterprise-grade validation for AI-generated code and decisions.

Las funciones de chequeo individuales se encuentran en ``guardrails_checks.py``
para mantener este archivo por debajo del limite de 500 lineas.
"""
import re
import json
from typing import Callable, Dict, Any, Tuple, List, Optional
from dataclasses import dataclass, field
from enum import Enum

from .guardrails_base import GuardrailSeverity, GuardrailResult
from .guardrails_checks import (
    check_architecture_pattern, check_dependency_injection, check_resilience_patterns,
    check_no_secrets, check_no_pii_in_logs, check_sql_injection_safe,
    check_conventional_commit, check_docs_for_public_api, check_tests_for_new_features,
    check_discovery_admin, check_discovery_data, check_discovery_infra,
    check_cost_budget, check_cost_usage, check_mcp_connectivity,
    check_three_whys_diagnostic, check_rag_groundedness, check_rag_context_relevance,
    check_rag_faithfulness,
)


class GuardrailPipeline:
    """Pipeline ejecutable de guardrails con soporte para pre/post checks."""

    def __init__(self):
        """Inicializa la instancia de la clase."""
        self._pre_checks: List[Tuple[str, Callable]] = []
        self._post_checks: List[Tuple[str, Callable]] = []
        self._results: List[GuardrailResult] = []

    def add_pre(self, rule_id: str, fn: Callable[[Dict], GuardrailResult]):
        """Anade un check pre-ejecucion."""
        self._pre_checks.append((rule_id, fn))

    def add_post(self, rule_id: str, fn: Callable[[str, Dict], GuardrailResult]):
        """Anade un check post-ejecucion."""
        self._post_checks.append((rule_id, fn))

    def run_pre(self, context: Dict[str, Any]) -> Tuple[bool, List[GuardrailResult]]:
        """Ejecuta todos los checks pre-ejecucion."""
        self._results = []
        blocked = False
        for rule_id, check_fn in self._pre_checks:
            try:
                result = check_fn(context)
                result.rule_id = rule_id
                self._results.append(result)
                if result.severity == GuardrailSeverity.BLOCK and not result.passed:
                    blocked = True
            except Exception as e:
                self._results.append(GuardrailResult(
                    passed=False, severity=GuardrailSeverity.WARN,
                    message=f"Error ejecutando {rule_id}: {str(e)}", rule_id=rule_id
                ))
        return not blocked, self._results

    def run_post(self, output: str, context: Dict[str, Any]) -> Tuple[bool, List[GuardrailResult]]:
        """Ejecuta todos los checks post-ejecucion."""
        results = []
        blocked = False
        for rule_id, check_fn in self._post_checks:
            try:
                result = check_fn(output, context)
                result.rule_id = rule_id
                results.append(result)
                if result.severity == GuardrailSeverity.BLOCK and not result.passed:
                    blocked = True
            except Exception as e:
                results.append(GuardrailResult(
                    passed=False, severity=GuardrailSeverity.WARN,
                    message=f"Error ejecutando {rule_id}: {str(e)}", rule_id=rule_id
                ))
        self._results.extend(results)
        return not blocked, results

    def get_summary(self) -> Dict[str, Any]:
        """Obtiene resumen de resultados para logging/observabilidad."""
        return {
            "total_checks": len(self._results),
            "passed": sum(1 for r in self._results if r.passed),
            "failed": sum(1 for r in self._results if not r.passed),
            "blocked": any(r.severity == GuardrailSeverity.BLOCK and not r.passed
                          for r in self._results),
            "by_severity": {
                s.value: sum(1 for r in self._results if r.severity == s and not r.passed)
                for s in GuardrailSeverity
            },
            "failed_rules": [r.rule_id for r in self._results if not r.passed]
        }


# =============================================================================
# PIPELINE INSTANCIA GLOBAL
# =============================================================================

guardrails = GuardrailPipeline()

# Registrar checks pre-ejecucion (arquitectura + discovery + cost + mcp)
guardrails.add_pre("ARCH-001", check_architecture_pattern)
guardrails.add_pre("ARCH-002", check_dependency_injection)
guardrails.add_pre("ARCH-003", check_resilience_patterns)
guardrails.add_pre("DISC-ADMIN-001", check_discovery_admin)
guardrails.add_pre("DISC-DATA-001", check_discovery_data)
guardrails.add_pre("DISC-INFRA-001", check_discovery_infra)
guardrails.add_pre("COST-001", check_cost_budget)
guardrails.add_pre("MCP-001", check_mcp_connectivity)

# Registrar checks post-ejecucion (seguridad, commits, docs, cost, whys, rag)
guardrails.add_post("SEC-001", check_no_secrets)
guardrails.add_post("SEC-002", check_no_pii_in_logs)
guardrails.add_post("SEC-003", check_sql_injection_safe)
guardrails.add_post("COMMIT-001", check_conventional_commit)
guardrails.add_post("DOCS-001", check_docs_for_public_api)
guardrails.add_post("TEST-001", check_tests_for_new_features)
guardrails.add_post("COST-002", check_cost_usage)
guardrails.add_post("WHYS-001", check_three_whys_diagnostic)
guardrails.add_post("RAG-001", check_rag_groundedness)
guardrails.add_post("RAG-002", check_rag_context_relevance)
guardrails.add_post("RAG-003", check_rag_faithfulness)


def run_full_pipeline(user_message: str, generated_code: str, context: Dict) -> Dict[str, Any]:
    """Ejecuta el pipeline completo de guardrails.

    Returns:
        Dict con: allowed, pre_results, post_results, summary
    """
    ctx = {**context, "generated_code": generated_code, "user_message": user_message}

    pre_ok, pre_results = guardrails.run_pre(ctx)
    if not pre_ok:
        return {
            "allowed": False, "blocked_at": "pre",
            "results": [r.to_dict() for r in pre_results],
            "summary": guardrails.get_summary()
        }

    post_ok, post_results = guardrails.run_post(generated_code, ctx)
    return {
        "allowed": post_ok,
        "blocked_at": None if post_ok else "post",
        "pre_results": [r.to_dict() for r in pre_results],
        "post_results": [r.to_dict() for r in post_results],
        "summary": guardrails.get_summary()
    }
