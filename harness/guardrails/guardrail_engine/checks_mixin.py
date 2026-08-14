"""Evaluacion de checks del GuardrailEngine.

Submodulo interno del paquete :mod:`harness.guardrails.guardrail_engine`.

Extraido de forma mecanica desde ``guardrail_engine.py`` (regla AGR: archivos
< 500 lineas). Define ``_ChecksMixin`` con la API publica de checks
(``check_input``, ``check_output``, ``check_content``, ``check_tool``,
``check_policy``), la evaluacion interna ``_check_layer`` y el wrapper
``_check_governance``. Los cuerpos son identicos al original; solo cambia
la ubicacion fisica del codigo.
"""

from __future__ import annotations

import logging
import time
from typing import Any

from harness.guardrails.guardrail_content import check_content
from harness.guardrails.guardrail_tool import check_policy, check_tool
from harness.guardrails.guardrail_types import (
    GuardrailLayer,
    GuardrailResult,
    GuardrailRule,
    GuardrailVerdict,
)

logger = logging.getLogger(__name__)


class _ChecksMixin:
    """Checks principales del motor de guardrails (capas 1-5)."""

    def check_input(self, text: str) -> GuardrailResult:
        """Evalua un prompt de entrada contra Input Guardrails (Capa 1).

        Verifica:
            - Prompt injection (BLOCK si detecta jailbreak).
            - Longitud excesiva (FLAG si > 8192 tokens).
            - Toxicidad (FLAG si detecta lenguaje ofensivo).

        Args:
            text: Texto del prompt a evaluar.

        Returns:
            GuardrailResult con el resultado acumulado de todas las reglas
            de la capa INPUT.
        """
        start: float = time.perf_counter()
        result: GuardrailResult = self._check_layer(
            GuardrailLayer.INPUT, text,
        )
        self._update_stats(GuardrailLayer.INPUT, result, start)
        return result

    def check_output(self, text: str) -> GuardrailResult:
        """Evalua una respuesta de salida contra Output Guardrails (Capa 2).

        Verifica:
            - Code injection (BLOCK si detecta eval/exec/subprocess).
            - PII leak (REWRITE si detecta emails/tarjetas/SSN).
            - Longitud excesiva (FLAG si > max_output_tokens).
            - Toxicidad (REWRITE si detecta lenguaje ofensivo).

        Args:
            text: Texto de la respuesta a evaluar.

        Returns:
            GuardrailResult con el resultado acumulado de todas las reglas
            de la capa OUTPUT.
        """
        start: float = time.perf_counter()
        result: GuardrailResult = self._check_layer(
            GuardrailLayer.OUTPUT, text,
        )
        self._update_stats(GuardrailLayer.OUTPUT, result, start)
        return result

    def check_content(self, text: str) -> GuardrailResult:
        """Evalua contenido arbitrario contra Content Guardrails (Capa 3).

        Delega en ``guardrail_content.check_content``.

        Verifica:
            - PII leak (REWRITE si detecta datos personales).
            - Code injection (BLOCK si detecta codigo peligroso).
            - Toxicidad (FLAG si detecta lenguaje ofensivo).

        Args:
            text: Texto del contenido a evaluar.

        Returns:
            GuardrailResult con el resultado acumulado de las reglas CONTENT.
        """
        return check_content(self, text)

    def check_tool(
        self,
        tool_name: str,
        args: dict[str, Any] | None = None,
    ) -> GuardrailResult:
        """Valida una llamada a herramienta contra Tool Guardrails (Capa 4).

        Delega en ``guardrail_tool.check_tool``.

        Args:
            tool_name: Nombre de la herramienta a validar.
            args: Argumentos de la llamada (para validacion contextual).

        Returns:
            GuardrailResult con BLOCK si no esta permitida, PASS si es segura.
        """
        return check_tool(self, tool_name, args)

    def check_policy(self, code: str) -> GuardrailResult:
        """Evalua codigo/politicas contra Policy Guardrails (Capa 5).

        Delega en ``guardrail_tool.check_policy``.

        Args:
            code: Codigo fuente a evaluar contra politicas de governance.

        Returns:
            GuardrailResult con FLAG si hay violaciones, PASS si cumple.
        """
        return check_policy(self, code)

    def _check_layer(
        self,
        layer: GuardrailLayer,
        text: str,
    ) -> GuardrailResult:
        """Evalua todas las reglas habilitadas de una capa contra el texto.

        Acumula violaciones y determina el veredicto final:
            - Si hay alguna regla CRITICAL violada -> BLOCK.
            - Si hay reglas HIGH violadas y action=BLOCK -> BLOCK.
            - Si hay reglas con action=REWRITE violadas -> REWRITE.
            - Si hay reglas con action=FLAG violadas -> FLAG.
            - Si no hay violaciones -> PASS.

        Args:
            layer: Capa a evaluar.
            text: Texto a evaluar.

        Returns:
            GuardrailResult acumulado de todas las reglas de la capa.
        """
        violations: list[str] = []
        max_severity: int = 0
        has_block: bool = False
        has_rewrite: bool = False
        has_flag: bool = False
        rule_hits: list[str] = []

        rules: list[GuardrailRule] = self._rules.get(layer, [])
        for rule in rules:
            if not rule.enabled:
                continue

            try:
                violated: bool
                reason: str
                violated, reason = rule.check_fn(text)
            except Exception as exc:  # noqa: BLE001
                logger.error(
                    "[GuardrailEngine] Error en regla '%s' (capa %s): "
                    "WHAT=excepcion en check_fn, "
                    "WHY=la funcion de evaluacion lanzo error, "
                    "WHERE=rule.check_fn(%s), error=%s",
                    rule.name, layer.value, rule.name, exc,
                )
                violated = True
                reason = f"Error interno en regla '{rule.name}': {exc}"

            if violated:
                violations.append(f"[{rule.severity.value}] {rule.name}: {reason}")
                rule_hits.append(rule.name)

                with self._lock:
                    self._stats["rule_hits"][rule.name] = \
                        self._stats["rule_hits"].get(rule.name, 0) + 1

                if rule.action == GuardrailVerdict.BLOCK:
                    has_block = True
                elif rule.action == GuardrailVerdict.REWRITE:
                    has_rewrite = True
                elif rule.action == GuardrailVerdict.FLAG:
                    has_flag = True

                sev_map: dict[str, int] = {
                    "critical": 4, "high": 3, "medium": 2, "low": 1, "info": 0,
                }
                sev_val: int = sev_map.get(rule.severity.value, 0)
                max_severity = max(max_severity, sev_val)

        # Determinar veredicto final
        verdict: GuardrailVerdict
        if has_block or max_severity >= 4:
            verdict = GuardrailVerdict.BLOCK
        elif has_rewrite:
            verdict = GuardrailVerdict.REWRITE
        elif has_flag:
            verdict = GuardrailVerdict.FLAG
        else:
            verdict = GuardrailVerdict.PASS

        # Calcular score
        score: float = 0.0
        if violations:
            total_enabled: int = sum(1 for r in rules if r.enabled)
            score = min(1.0, len(violations) / max(total_enabled, 1))
            score = min(1.0, score + (max_severity * 0.15))

        return GuardrailResult(
            verdict=verdict,
            score=round(score, 3),
            violations=tuple(violations),
            metadata={
                "layer": layer.value,
                "rules_checked": len(rules),
                "rules_violated": rule_hits,
                "max_severity": max_severity,
            },
        )

    def _check_governance(self, text: str) -> tuple[bool, str]:
        """Wrapper que evalua GovernanceGuard contra el texto.

        Delega en ``guardrail_tool._check_governance``.

        Args:
            text: Codigo fuente a evaluar.

        Returns:
            tuple[bool, str]: (True si hay violaciones, detalle).
        """
        from harness.guardrails.guardrail_tool import _check_governance as _cg
        return _cg(self, text)

    def _update_stats(
        self,
        layer: GuardrailLayer,
        result: GuardrailResult,
        start_time: float,
    ) -> None:
        """Actualiza las estadisticas internas con un resultado.

        Args:
            layer: Capa evaluada.
            result: Resultado obtenido.
            start_time: Timestamp de inicio de la evaluacion.
        """
        elapsed_ms: float = (time.perf_counter() - start_time) * 1000

        with self._lock:
            self._stats["total_checks"] += 1
            self._stats["last_checked"] = time.time()

            layer_stats: dict[str, Any] = self._stats["by_layer"][layer.value]
            layer_stats["checks"] += 1

            if result.verdict == GuardrailVerdict.BLOCK:
                self._stats["blocked"] += 1
                layer_stats["blocked"] += 1
            elif result.verdict == GuardrailVerdict.FLAG:
                self._stats["flagged"] += 1
            elif result.verdict == GuardrailVerdict.REWRITE:
                self._stats["rewrites"] += 1
            else:
                self._stats["passed"] += 1

            prev_avg: float = self._stats["avg_check_time_ms"]
            total: int = self._stats["total_checks"]
            self._stats["avg_check_time_ms"] = prev_avg + (
                (elapsed_ms - prev_avg) / min(total, 100)
            )

    def get_stats(self) -> dict[str, Any]:
        """Obtiene estadisticas de uso del motor de guardrails.

        Retorna un diccionario con:
            - total_checks, blocked, flagged, passed, rewrites
            - by_layer, rule_hits, last_checked, avg_check_time_ms

        Returns:
            Dict con las estadisticas actuales.
        """
        with self._lock:
            return {
                "total_checks": self._stats["total_checks"],
                "blocked": self._stats["blocked"],
                "flagged": self._stats["flagged"],
                "passed": self._stats["passed"],
                "rewrites": self._stats["rewrites"],
                "by_layer": {
                    layer: dict(stats)
                    for layer, stats in self._stats["by_layer"].items()
                },
                "rule_hits": dict(self._stats["rule_hits"]),
                "last_checked": self._stats["last_checked"],
                "avg_check_time_ms": round(self._stats["avg_check_time_ms"], 2),
            }

    def reset_stats(self) -> None:
        """Resetea todas las estadisticas de uso a cero."""
        with self._lock:
            self._stats["total_checks"] = 0
            self._stats["blocked"] = 0
            self._stats["flagged"] = 0
            self._stats["passed"] = 0
            self._stats["rewrites"] = 0
            self._stats["last_checked"] = 0.0
            self._stats["avg_check_time_ms"] = 0.0
            self._stats["rule_hits"].clear()
            for layer in GuardrailLayer:
                self._stats["by_layer"][layer.value] = {"checks": 0, "blocked": 0}
            logger.info("[GuardrailEngine] Estadisticas reseteadas")
