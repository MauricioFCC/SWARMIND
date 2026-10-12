"""Failure Registry — registro estructurado de fallos para aprendizaje autonomo.

Uso: ``from harness.failure_registry import FailureRegistry``.

Tambien expone ``registry``, el singleton compartido (append-only sobre
``harness/db/failures.jsonl``) que los modulos del harness inyectan por DI
para drenar fallos al registro central.
"""
from harness.failure_registry.registry import (
    FailureRecord,
    FailureRegistry,
    FailureType,
    Severity,
)

# Singleton compartido: los modulos lo reciben por inyeccion (DI) y pueden
# sustituirlo en tests por un registry aislado.
registry = FailureRegistry()

__all__ = ["FailureRecord", "FailureRegistry", "FailureType", "Severity", "registry"]
