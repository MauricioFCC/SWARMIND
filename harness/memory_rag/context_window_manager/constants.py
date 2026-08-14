"""Constantes para el paquete ``context_window_manager``.

Extraido mecanicamente de ``context_window_manager.py`` (regla AGR < 500
lineas). Contiene prioridades de secciones, presupuestos por defecto y
limites de la ventana de contexto.
"""
from __future__ import annotations

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Prioridades de secciones (mas bajo = se trunca primero)
PRIORITY_CRITICAL = 0     # Nunca se trunca
PRIORITY_HIGH = 1         # Solo se trunca si es absolutamente necesario
PRIORITY_NORMAL = 2       # Se trunca normalmente
PRIORITY_LOW = 3          # Se trunca primero
PRIORITY_BACKGROUND = 4   # Se elimina primero

SECTION_PRIORITIES: dict[str, int] = {
    "system_identity": PRIORITY_CRITICAL,
    "system_rules": PRIORITY_CRITICAL,
    "system_guardrails": PRIORITY_CRITICAL,
    "current_instruction": PRIORITY_HIGH,
    "session_context": PRIORITY_HIGH,
    "skill_context": PRIORITY_NORMAL,
    "rag_context": PRIORITY_LOW,
    "conversation_history": PRIORITY_LOW,
    "tool_outputs": PRIORITY_BACKGROUND,
}

DEFAULT_BUDGETS: dict[str, int] = {
    "system_identity": 500,
    "system_rules": 1000,
    "system_guardrails": 500,
    "current_instruction": 400,
    "session_context": 800,
    "skill_context": 2000,
    "rag_context": 2000,
    "conversation_history": 3000,
    "tool_outputs": 2000,
}

MAX_SUMMARY_CHARS = 500
SLIDING_WINDOW_SIZE = 6
