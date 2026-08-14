"""
OpenTelemetry Agent — Trazabilidad distribuida para sistemas multi-agente.

Integra OpenTelemetry con semantic conventions para spans de agentes.
Provee decoradores para automaticamente trazar llamadas de agentes.

Usage:
    from harness.observability.opentelemetry_agent import AgentTracer, trace_agent

    tracer = AgentTracer(service_name="Swarmind")

    @trace_agent("builder", "implement_api")
    def implement_api():
        pass
"""
from __future__ import annotations

import functools
import logging
from collections.abc import Callable
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Semantic conventions GenAI estables 2026 (ADR-0041 H2)
# ---------------------------------------------------------------------------
GENAI_SPAN_NAMES = frozenset({"invoke_agent", "chat", "execute_tool"})
GENAI_PROVIDER = "swarmind"
ATTR_PROVIDER = "gen_ai.provider.name"
ATTR_SYSTEM = "gen_ai.system"
ATTR_MODEL = "gen_ai.request.model"
ATTR_INPUT_TOKENS = "gen_ai.usage.input_tokens"
ATTR_OUTPUT_TOKENS = "gen_ai.usage.output_tokens"

try:
    from opentelemetry import trace
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor
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

    def __init__(self, service_name: str = "Swarmind", otlp_endpoint: str | None = None):
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

    def start_span(self, name: str, attributes: dict[str, Any] | None = None):
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

    def start_genai_span(
        self,
        operation: str = "invoke_agent",
        model: str | None = None,
        provider: str = GENAI_PROVIDER,
        attributes: dict[str, Any] | None = None,
    ):
        """
        Iniciar un span con semantic conventions GenAI estables 2026.

        Emite los atributos gen_ai.provider.name, gen_ai.system y
        gen_ai.request.model (fallback "unknown" si no hay modelo).

        Args:
            operation: Nombre de operacion estandar (invoke_agent, chat, execute_tool).
            model: Modelo LLM usado; se emite "unknown" si es None.
            provider: Proveedor, usado en gen_ai.provider.name y gen_ai.system.
            attributes: Atributos adicionales del span (ej. agent.*, negocio).

        Returns:
            Context manager del span si OTel habilitado, None en caso contrario.
        """
        if not self._enabled:
            return None
        span_attributes: dict[str, Any] = {
            ATTR_PROVIDER: provider,
            ATTR_SYSTEM: provider,
            ATTR_MODEL: model if model is not None else "unknown",
        }
        if attributes:
            span_attributes.update(attributes)
        return self._tracer.start_as_current_span(operation, attributes=span_attributes)


def _extract_token_usage(result: Any) -> dict[str, Any]:
    """
    Extraer metricas de tokens del resultado de una llamada GenAI.

    Busca en orden: dict de retorno, atributo .tokens (dict) o atributos
    de clase input_tokens/output_tokens.

    Args:
        result: Valor de retorno de la funcion decorada.

    Returns:
        Dict con input_tokens/output_tokens solo si estan disponibles.
    """
    candidates: list[dict[str, Any]] = []
    if isinstance(result, dict):
        candidates.append(result)
    tokens_attr = getattr(result, "tokens", None)
    if isinstance(tokens_attr, dict):
        candidates.append(tokens_attr)
    candidates.append(
        {
            "input_tokens": getattr(result, "input_tokens", None),
            "output_tokens": getattr(result, "output_tokens", None),
        }
    )
    for candidate in candidates:
        usage = {key: value for key, value in candidate.items() if value is not None}
        if usage:
            return usage
    return {}


def trace_agent(agent_type: str, action: str = "execute"):
    """
    Decorador para trazar automaticamente llamadas de agentes.

    Crea un span GenAI estandar llamado "invoke_agent" con atributos
    gen_ai.* y legacy agent.*. Emite gen_ai.usage.* si el resultado
    expone metricas de tokens.

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

            attrs = {
                "agent.id": agent_type,
                "agent.type": agent_type,
                "agent.delegation_depth": 1,
            }
            with tracer.start_genai_span(
                operation="invoke_agent",
                model=kwargs.get("model"),
                provider=GENAI_PROVIDER,
                attributes=attrs,
            ) as span:
                try:
                    result = func(*args, **kwargs)
                    span.set_attribute("agent.success", True)
                    usage = _extract_token_usage(result)
                    if "input_tokens" in usage:
                        span.set_attribute(ATTR_INPUT_TOKENS, usage["input_tokens"])
                    if "output_tokens" in usage:
                        span.set_attribute(ATTR_OUTPUT_TOKENS, usage["output_tokens"])
                    return result
                except Exception as e:
                    span.set_attribute("agent.success", False)
                    span.set_attribute("agent.error", str(e))
                    raise
        return wrapper
    return decorator
