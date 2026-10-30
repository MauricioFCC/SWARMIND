"""Errores del AgentBus (modulo sin dependencias internas).

Viven aqui —y no en ``core.py``— para romper el ciclo
``core <-> messaging``: ``messaging`` necesita ``AgentBusError`` y ``core``
necesita el mixin de ``messaging``. ``core`` los re-exporta para conservar la
API publica historica.
"""

from __future__ import annotations


class AgentBusError(Exception):
    """Error base del AgentBus."""


class InvalidMessageError(AgentBusError):
    """El mensaje no cumple con el esquema requerido."""


__all__ = ["AgentBusError", "InvalidMessageError"]
