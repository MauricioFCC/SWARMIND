"""Whitelist de vulture — símbolos legítimos que vulture no debe reportar.

Vulture reporta como "código muerto" símbolos que en realidad forman parte de
contratos públicos, hooks dinámicos o compatibilidad. Este archivo se pasa a
vulture como whitelist (vía `[tool.vulture].whitelist` en pyproject.toml) para
marcarlos como usados.

Casos cubiertos:
  1. Parámetros de firma de compatibilidad (select.select fallback) y de API
     pública con docstring "ignorado" -> se gestionan con `ignore_names` en
     `[tool.vulture]` (no son eliminables sin romper contratos).
  2. Símbolos de módulo referenciados dinámicamente (registros, getattr por
     nombre) -> se listan aquí para que vulture los considere usados.

Regla del proyecto (base_principles AGR): está prohibido añadir entradas a este
whitelist para código muerto real; solo se admiten falsos positivos con
justificación WHAT+WHY+WHERE (ver cada entrada).
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Símbolos de módulo referenciados dinámicamente (registro por nombre)
# ---------------------------------------------------------------------------
# WHAT: ninguno por ahora.
# WHY: si un módulo registra clases/funciones por nombre (factory patterns,
#      plugin discovery), añadirlas aquí como atributos de módulo.
# WHERE: N/A.

# ---------------------------------------------------------------------------
# Parámetros de compatibilidad gestionados vía ignore_names
# ---------------------------------------------------------------------------
# rlist, wlist, xlist: harness/orchestrator/hitl_guard.py:384 — firma del
#   fallback _SelectFallback.select (API select.select del stdlib).
# base_id: harness/orchestrator/scope_analyzer.py:205 — parámetro documentado
#   como "Ignorado (usamos indices 0-based para compatibilidad)".
