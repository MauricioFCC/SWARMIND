"""
guardrail_content — Validacion de contenido (Content Guardrails, Capa 3).

Extraido de guardrail_engine.py para mantener modulos < 900 lines.

La funcion recibe ``self`` como primer argumento (la instancia de
GuardrailEngine) para acceder a sus atributos internos.
"""

from __future__ import annotations

import time
from typing import Any

from harness.guardrails.guardrail_types import GuardrailLayer, GuardrailResult


def check_content(self: Any, text: str) -> GuardrailResult:
    """Evalua contenido arbitrario contra Content Guardrails (Capa 3).

    Verifica:
        - PII leak (REWRITE si detecta datos personales).
        - Code injection (BLOCK si detecta codigo peligroso).
        - Toxicidad (FLAG si detecta lenguaje ofensivo).

    Nota: Esta capa es para contenido interno que no es input directo
    ni output final, como datos de memoria intermedia o logs.

    Args:
        self: Instancia de GuardrailEngine.
        text: Texto del contenido a evaluar.

    Returns:
        GuardrailResult con el resultado acumulado de las reglas CONTENT.
    """
    start: float = time.perf_counter()
    result: GuardrailResult = self._check_layer(
        GuardrailLayer.CONTENT, text,
    )
    self._update_stats(GuardrailLayer.CONTENT, result, start)
    return result
