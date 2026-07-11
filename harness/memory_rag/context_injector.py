"""
context_injector.py — Inyeccion automatica de contexto en subtareas.

Resuelve el problema de que el LLM "olvida" los estandares durante
sesiones largas de refactorizacion. La clave: inyectar un recordatorio
ultra-compacto en CADA subtarea, no solo al inicio de la sesion.

Formato: 1 linea, ~100 chars, <25 tokens.
No reemplaza los agent prompts, los REFUERZA en cada interaccion.

Uso:
    injector = ContextInjector()
    descripcion = injector.inject("implementar modulo X")
    # → "[FIJOS] CleanCode+DRY+KISS+SSOT+<900LC | implementar modulo X"

    record = injector.get_reminder("builder")
    # → "FIJOS: CleanCode+DRY+KISS+SSOT+<900LC+Patrones+DocStringsES+tests>80+Seg"
"""

from __future__ import annotations

from typing import Dict, List, Optional

# ---------------------------------------------------------------------------
# Codificacion ultra-compacta de estandares (<100 chars cada uno)
# ---------------------------------------------------------------------------
# Formato: siglas sin espacios, + como separador
# Cada entry: [nombre_corto] = [significado]

STANDARDS_ENCODED: Dict[str, str] = {
    "builder": "CleanCode+DRY+KISS+SSOT+<900LC+Patrones+DocStringsES+tests>80+Seg+YAGNI",
    "scientist": "MetodoCientifico+Fuentes+Analisis+Conclusiones+DocumentarES",
    "guardian": "Tests>80+OWASP+DocStringsES+CommitsConvencionales+SinVulns",
    "coordinator": "SwissWatch+Paralelo+CalidadAutomatica+Consolidar",
    "evolve": "Cognition+MejoraContinua+Skills+Optimizacion",
}

# Firma universal aplica a TODOS los agentes siempre
UNIVERSAL_FIRMA = "CleanCode+DRY+KISS+SSOT+<900LC+Patrones+DocStringsES+tests>80+Seg"

# Tamaño en chars de la firma (para calculo de tokens)
FIRMA_LENGTH = len(UNIVERSAL_FIRMA)

# Maximo de caracteres para la inyeccion (limitar impacto tokens)
MAX_INJECTION_CHARS = 120


class ContextInjector:
    """
    Inyecta recordatorio de estandares en descripciones de subtareas.

    El recordatorio es UNA SOLA LINEA ultra-compacta que se antepone
    a la descripcion real. Esto asegura que el LLM vea los estandares
    en CADA interaccion, no solo al inicio de la sesion.
    """

    def __init__(self, always_inject: bool = True):
        """
        Args:
            always_inject: Si True, siempre inyecta (incluso en tareas simples).
                          Si False, solo inyecta en tareas complejas.
        """
        self._always_inject = always_inject

    def inject(self, description: str, agent_role: str = "builder") -> str:
        """
        Inyecta estandares en una descripcion de subtarea.

        Args:
            description: Descripcion original de la subtarea.
            agent_role: Rol del agente (builder, scientist, guardian, etc).

        Returns:
            Descripcion con recordatorio de estandares antepuesto.
        """
        if not description:
            return description

        reminder = self.get_reminder(agent_role)
        # Solo inyectar si la descripcion no lo contiene ya
        if reminder in description:
            return description

        # Formato: recordatorio + " | " + descripcion original
        # Mantener la descripcion original legible
        if self._always_inject:
            return f"{reminder} | {description}"
        else:
            return description

    def get_reminder(self, agent_role: str = "builder") -> str:
        """
        Obtiene recordatorio de estandares para un rol.

        Args:
            agent_role: Rol del agente.

        Returns:
            String con estandares codificados.
        """
        specific = STANDARDS_ENCODED.get(agent_role, UNIVERSAL_FIRMA)
        return f"[F]{specific}"

    def estimate_tokens(self, agent_role: str = "builder") -> int:
        """Estima tokens adicionales por inyeccion."""
        reminder = self.get_reminder(agent_role)
        return len(reminder) // 4  # ~1 token cada 4 chars

    def batch_inject(
        self, descriptions: List[str], agent_role: str = "builder"
    ) -> List[str]:
        """Inyecta estandares en multiples descripciones."""
        return [self.inject(d, agent_role) for d in descriptions]

    @property
    def universal_firma(self) -> str:
        """Retorna la firma universal."""
        return UNIVERSAL_FIRMA
