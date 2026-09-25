"""Failure Registry — registro estructurado de fallos para aprendizaje autonomo.

Uso: ``from harness.failure_registry import FailureRegistry``.
"""
from harness.failure_registry.registry import (
    FailureRecord,
    FailureRegistry,
    FailureType,
    Severity,
)

__all__ = ["FailureRecord", "FailureRegistry", "FailureType", "Severity"]
