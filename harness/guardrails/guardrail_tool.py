"""
guardrail_tool — Validacion de herramientas (Tool Guardrails) y
politicas (Policy Guardrails) para el sistema de guardrails.

Extraido de guardrail_engine.py para mantener modulos < 900 lines.

Cada funcion recibe ``self`` como primer argumento (la instancia de
GuardrailEngine) para acceder a sus atributos internos.
"""

from __future__ import annotations

import time
from typing import Any, Dict, List, Optional, Tuple

from harness.guardrails.guardrail_types import GuardrailLayer, GuardrailResult, GuardrailVerdict


def check_tool(
    self: Any,
    tool_name: str,
    args: Optional[Dict[str, Any]] = None,
) -> GuardrailResult:
    """Valida una llamada a herramienta contra Tool Guardrails (Capa 4).

    Reusa ToolGuardian para validar la tool contra politicas de seguridad
    declarativas (acciones bloqueadas, permitidas, contexto).

    Args:
        self: Instancia de GuardrailEngine.
        tool_name: Nombre de la herramienta a validar.
        args: Argumentos de la llamada (para validacion contextual).

    Returns:
        GuardrailResult con:
            - BLOCK si la tool no esta permitida.
            - PASS si la tool es segura y permitida.
    """
    start: float = time.perf_counter()
    violations: List[str] = []

    # 1. Validar contra ToolGuardian
    is_allowed: bool = self._tool_guardian.validate_tool_call(
        tool_name=tool_name,
        action=args.get("action", "execute") if args else "execute",
        args=args,
    )
    if not is_allowed:
        violations.append(
            f"Tool '{tool_name}' bloqueada por ToolGuardian "
            "(accion no permitida o politica violada)"
        )

    # 2. Ejecutar reglas de capa TOOL (tool_allowlist)
    tool_text: str = f"tool_name={tool_name}, args={args}"
    layer_result: GuardrailResult = self._check_layer(
        GuardrailLayer.TOOL, tool_text,
    )
    violations.extend(layer_result.violations)

    if violations:
        result: GuardrailResult = GuardrailResult(
            verdict=GuardrailVerdict.BLOCK,
            score=min(1.0, len(violations) * 0.4),
            violations=tuple(violations),
            metadata={
                "tool_name": tool_name,
                "args": args,
                "checked_layer": GuardrailLayer.TOOL.value,
            },
        )
    else:
        result = GuardrailResult.pass_result({
            "tool_name": tool_name,
            "args": args,
            "checked_layer": GuardrailLayer.TOOL.value,
        })

    self._update_stats(GuardrailLayer.TOOL, result, start)
    return result


def check_policy(
    self: Any,
    code: str,
) -> GuardrailResult:
    """Evalua codigo/politicas contra Policy Guardrails (Capa 5).

    Reusa GovernanceGuard para verificar constraints de governance
    como no_except_pass, docstrings, no_eval_exec, etc.

    Args:
        self: Instancia de GuardrailEngine.
        code: Codigo fuente a evaluar contra politicas de governance.

    Returns:
        GuardrailResult con:
            - FLAG si hay violaciones de governance.
            - PASS si cumple todas las politicas.
    """
    start: float = time.perf_counter()
    violations: List[str] = []

    # 1. GovernanceGuard check
    governance_violations: List[str] = self._governance_guard.check(code)
    violations.extend(governance_violations)

    # 2. Reglas de capa POLICY
    layer_result: GuardrailResult = self._check_layer(
        GuardrailLayer.POLICY, code,
    )
    violations.extend(layer_result.violations)

    if violations:
        result = GuardrailResult(
            verdict=GuardrailVerdict.FLAG,
            score=min(1.0, len(violations) * 0.2),
            violations=tuple(violations),
            metadata={
                "governance_violations": len(governance_violations),
                "checked_layer": GuardrailLayer.POLICY.value,
            },
        )
    else:
        result = GuardrailResult.pass_result({
            "checked_layer": GuardrailLayer.POLICY.value,
        })

    self._update_stats(GuardrailLayer.POLICY, result, start)
    return result


def _check_governance(self: Any, text: str) -> Tuple[bool, str]:
    """Wrapper que evalua GovernanceGuard contra el texto.

    Convierte la salida de GovernanceGuard.check() en el formato
    (violated, reason) esperado por las reglas.

    Args:
        self: Instancia de GuardrailEngine.
        text: Codigo fuente a evaluar.

    Returns:
        tuple[bool, str]: (True si hay violaciones, detalle).
    """
    violations: List[str] = self._governance_guard.check(text)
    if violations:
        detail: str = "; ".join(violations[:5])
        if len(violations) > 5:
            detail += f" (y {len(violations) - 5} mas)"
        return True, detail
    return False, ""
