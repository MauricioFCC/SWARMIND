"""Excepciones del AgentBus (extraidas tal cual del modulo original)."""

from __future__ import annotations


class AgentBusError(Exception):
    """Error base del AgentBus."""


class InvalidMessageError(AgentBusError):
    """El mensaje no cumple con el esquema requerido."""
