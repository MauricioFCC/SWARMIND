"""Benchmark: Routing precision y velocidad."""
from __future__ import annotations

import time
from typing import Any

from harness.orchestrator.delegation_engine import DelegationEngine

GOLDEN_SET: list[tuple[str, str]] = [
    ("implementa una API en Rust", "builder"),
    ("crea un endpoint REST en Go", "builder"),
    ("desarrolla una app Android", "builder"),
    ("despliega en Docker con CI/CD", "builder"),
    ("implementa un trading strategy", "builder"),
    ("investiga este paper sobre transformers", "scientist"),
    ("arquitectura del sistema C4", "scientist"),
    ("entrena un modelo ML", "scientist"),
    ("auditoria de seguridad OWASP", "guardian"),
    ("testing y cobertura de codigo", "guardian"),
    ("documentacion de la API", "guardian"),
    ("monitoreo de produccion", "guardian"),
    ("!evolve run", "evolve"),
    ("mejora este skill", "evolve"),
    ("!iteration end", "coordinator"),
    ("hola que tal", "coordinator"),
    ("organiza las tareas", "coordinator"),
    ("ayuda con este proyecto", "coordinator"),
]


def bench_routing() -> dict[str, Any]:
    engine = DelegationEngine()
    correct = 0
    errors: list[tuple[str, str, str]] = []
    t0 = time.perf_counter()
    for msg, expected in GOLDEN_SET:
        result = engine.auto_route(msg)
        if result == expected:
            correct += 1
        else:
            errors.append((msg, expected, result))
    elapsed = time.perf_counter() - t0
    return {
        "name": "Routing Precision",
        "total_tests": len(GOLDEN_SET),
        "correct": correct,
        "accuracy_pct": round(correct / len(GOLDEN_SET) * 100, 1),
        "total_time_ms": round(elapsed * 1000, 2),
        "throughput_tps": round(len(GOLDEN_SET) / elapsed, 1) if elapsed > 0 else 0,
        "errors": errors[:5],
    }
