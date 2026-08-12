"""Registros de datos de MetaClaw (extraccion mecanica).

ToolRecord (rendimiento historico de una herramienta) y
SelectionRecord (decision de seleccion con reward compuesto).
"""
from __future__ import annotations

import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ToolRecord:
    """Registro de rendimiento historico de una herramienta.

    Attributes:
        tool_name: Identificador unico de la herramienta.
        total_calls: Numero total de invocaciones.
        successes: Numero de invocaciones exitosas.
        failures: Numero de invocaciones fallidas.
        total_latency: Suma acumulada de latencia (segundos).
        total_cost: Suma acumulada de costo (tokens).
        last_used: Timestamp de la ultima invocacion.
        task_types: Contador de tipos de tarea atendidos.
    """

    tool_name: str
    total_calls: int = 0
    successes: int = 0
    failures: int = 0
    total_latency: float = 0.0
    total_cost: float = 0.0
    last_used: float = 0.0
    task_types: dict[str, int] = field(default_factory=lambda: defaultdict(int))

@dataclass
class SelectionRecord:
    """Registro de una decision de seleccion de herramienta.

    Attributes:
        task_type: Tipo de tarea clasificado.
        context: Vector/contexto de la tarea.
        selected_tool: Herramienta elegida.
        success: Si la ejecucion fue exitosa.
        latency: Latencia de la ejecucion (segundos).
        cost: Costo en tokens.
        confidence: Confianza reportada por el agente.
        reward: Reward compuesto calculado.
        timestamp: Momento de la decision.
    """

    task_type: str
    context: dict[str, Any]
    selected_tool: str
    success: bool
    latency: float
    cost: float
    confidence: float = 0.0
    reward: float = 0.0
    timestamp: float = field(default_factory=time.time)
