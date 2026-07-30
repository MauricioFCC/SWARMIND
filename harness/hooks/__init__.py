"""Sistema de Hooks deterministas para Swarmind.

Los hooks son puntos de extension deterministas que se ejecutan antes/despues
de operaciones clave. A diferencia de los agentes LLM, los hooks son 100%
deterministas y no pueden ser controlados por el modelo.

Basado en: AI agents.txt — "Hooks = AUTOMATION. Pre-tool, post-tool, on-edit,
on-notification. Deterministic — the LLM doesn't control them."

Tipos de hooks:
- pre_tool: Se ejecuta ANTES de una herramienta. Puede validar, rechazar o modificar.
- post_tool: Se ejecuta DESPUES de una herramienta. Puede validar resultados.
- on_edit: Se ejecuta cuando un archivo es modificado. Puede formatear, lintear.
- on_notification: Se ejecuta cuando ocurre un evento del sistema.

Arquitectura:
- HookRegistry: Registro central de hooks (singleton).
- HookManager: Orquestador que ejecuta hooks en el orden correcto.
- Hooks individuales: Funciones o clases que implementan la logica.
"""

from harness.hooks.hook_manager import HookManager, HookPriority, HookResult, HookType
from harness.hooks.hook_registry import HookRegistry

__all__ = [
    "HookManager",
    "HookPriority",
    "HookRegistry",
    "HookResult",
    "HookType",
]
