"""
OpenTelemetry Agent — Trazabilidad distribuida para sistemas multi-agente.

Integra OpenTelemetry con semantic conventions para spans de agentes.
Provee decoradores para automaticamente trazar llamadas de agentes.

Usage:
    from harness.observability.opentelemetry_agent import AgentTracer, trace_agent

    tracer = AgentTracer(service_name="agentic")

    @trace_agent("builder", "implement_api")
    def implement_api():
        pass
"""
from __future__ import annotations

import functools
import logging
from typing import Any, Callable, Dict, Optional

logger = logging.getLogger(__name__)

try:
    from opentelemetry import trace
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
    HAVE_OTEL = True
except ImportError:
    HAVE_OTEL = False
    trace = None


class AgentTracer:
    """
    Tracer para sistemas multi-agente con semantic conventions.

    Atributos de span (semantic conventions gen_ai.agent.*):
    - agent.id: Identificador del agente
    - agent.type: Tipo de agente
    - agent.input_tokens: Tokens de entrada
    - agent.output_tokens: Tokens de salida
    - agent.delegation_depth: Profundidad de delegacion
    """

    def __init__(self, service_name: str = "agentic", otlp_endpoint: Optional[str] = None):
        """
        Inicializa el tracer OpenTelemetry.

        Args:
            service_name: Nombre del servicio para identificar la fuente de trazas.
            otlp_endpoint: Endpoint OTLP HTTP para exportar trazas.
                          Si es None, solo se usa el TracerProvider local.
        """
        self._enabled = HAVE_OTEL
        if not self._enabled:
            logger.info("OpenTelemetry not installed. Install with: pip install opentelemetry-api opentelemetry-sdk opentelemetry-exporter-otlp")
            return

        resource = Resource.create({"service.name": service_name})
        provider = TracerProvider(resource=resource)

        if otlp_endpoint:
            exporter = OTLPSpanExporter(endpoint=otlp_endpoint)
            processor = BatchSpanProcessor(exporter)
            provider.add_span_processor(processor)

        trace.set_tracer_provider(provider)
        self._tracer = trace.get_tracer(service_name)

    @property
    def enabled(self) -> bool:
        """
        Indica si OpenTelemetry esta habilitado.

        Returns:
            True si las dependencias OTel estan instaladas, False en caso contrario.
        """
        return self._enabled

    @property
    def tracer(self):
        """
        Retorna el tracer subyacente.

        Returns:
            El tracer de OpenTelemetry si habilitado, None en caso contrario.
        """
        if not self._enabled:
            return None
        return self._tracer

    def start_span(self, name: str, attributes: Optional[Dict[str, Any]] = None):
        """
        Iniciar un span.

        Args:
            name: Nombre del span.
            attributes: Atributos opcionales para el span.

        Returns:
            Context manager del span si OTel habilitado, None en caso contrario.
        """
        if not self._enabled:
            return None
        return self._tracer.start_as_current_span(name, attributes=attributes)


def trace_agent(agent_type: str, action: str = "execute"):
    """
    Decorador para trazar automaticamente llamadas de agentes.

    Args:
        agent_type: Tipo de agente (builder, scientist, etc.).
        action: Accion (implement, research, audit, etc.).

    Returns:
        Decorador que envuelve la funcion con tracing OpenTelemetry.

    Raises:
        Cualquier excepcion lanzada por la funcion decorada, registrada en el span.
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            tracer = AgentTracer()
            if not tracer.enabled:
                return func(*args, **kwargs)

            span_name = f"{agent_type}.{action}"
            attrs = {
                "agent.id": agent_type,
                "agent.type": agent_type,
                "agent.delegation_depth": 1,
            }
            with tracer.start_span(span_name, attributes=attrs) as span:
                try:
                    result = func(*args, **kwargs)
                    span.set_attribute("agent.success", True)
                    return result
                except Exception as e:
                    span.set_attribute("agent.success", False)
                    span.set_attribute("agent.error", str(e))
                    raise
        return wrapper
    return decorator
