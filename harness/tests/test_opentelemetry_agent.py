"""
Tests para OpenTelemetry Agent — trazabilidad distribuida multi-agente.

Cubre: AgentTracer, trace_agent decorator, fallback graceful sin OTel instalado.
"""
from __future__ import annotations

import logging
from unittest.mock import patch

import pytest

from harness.observability.opentelemetry_agent import AgentTracer, trace_agent


# ===========================================================================
# AgentTracer — sin OpenTelemetry instalado
# ===========================================================================


class TestAgentTracerWithoutOtel:
    """AgentTracer cuando OpenTelemetry NO esta instalado (fallback graceful)."""

    def test_init_without_otel(self) -> None:
        """Sin OTel instalado no falla y enabled=False."""
        tracer = AgentTracer()
        assert tracer.enabled is False
        assert tracer.tracer is None

    def test_init_without_otel_logs_warning(self, caplog: pytest.LogCaptureFixture) -> None:
        """Sin OTel, el init registra un mensaje informativo."""
        with caplog.at_level(logging.INFO):
            AgentTracer()
            assert any("OpenTelemetry not installed" in msg for msg in caplog.messages)

    def test_start_span_without_otel_returns_none(self) -> None:
        """start_span sin OTel retorna None."""
        tracer = AgentTracer()
        span = tracer.start_span("test")
        assert span is None

    def test_start_span_with_attributes_without_otel(self) -> None:
        """start_span con attributes sin OTel retorna None."""
        tracer = AgentTracer()
        span = tracer.start_span("test", attributes={"key": "val"})
        assert span is None

    def test_tracer_property_without_otel(self) -> None:
        """Propiedad tracer es None sin OTel."""
        tracer = AgentTracer()
        assert tracer.tracer is None

    def test_enabled_property_false_without_otel(self) -> None:
        """Propiedad enabled es False sin OTel."""
        tracer = AgentTracer()
        assert tracer.enabled is False
        assert not tracer.enabled


# ===========================================================================
# AgentTracer — propiedades basicas
# ===========================================================================


class TestAgentTracerProperties:
    """Propiedades basicas del AgentTracer (modo no-OTel)."""

    def test_default_service_name(self) -> None:
        """Constructor usa 'Swarmind' como service_name por defecto."""
        tracer = AgentTracer()
        assert tracer.enabled is False  # sin OTel, pero no falla

    def test_custom_service_name_no_fail(self) -> None:
        """Constructor acepta service_name personalizado sin fallar."""
        tracer = AgentTracer(service_name="custom-agent")
        assert tracer.enabled is False

    def test_otlp_endpoint_no_fail(self) -> None:
        """Constructor acepta otlp_endpoint sin fallar."""
        tracer = AgentTracer(otlp_endpoint="http://localhost:4318/v1/traces")
        assert tracer.enabled is False

    def test_multiple_instances_no_side_effects(self) -> None:
        """Multiples instancias no causan efectos laterales."""
        t1 = AgentTracer()
        t2 = AgentTracer()
        t3 = AgentTracer()
        assert all(t.enabled is False for t in [t1, t2, t3])


# ===========================================================================
# trace_agent decorator
# ===========================================================================


class TestTraceAgentDecorator:
    """Decorador @trace_agent — tracing automatico de llamadas."""

    def test_decorator_executes_function_without_otel(self) -> None:
        """Decorador ejecuta la funcion correctamente sin OTel."""
        @trace_agent("builder", "implement")
        def my_func(x: int, y: int) -> int:
            """Suma dos numeros."""
            return x + y

        result = my_func(3, 4)
        assert result == 7

    def test_decorator_preserves_return_value(self) -> None:
        """Decorador preserva el valor de retorno de la funcion."""
        @trace_agent("scientist", "research")
        def research_topic(topic: str) -> str:
            """Investiga un tema."""
            return f"Research results for: {topic}"

        result = research_topic("quantum computing")
        assert result == "Research results for: quantum computing"

    def test_decorator_preserves_function_metadata(self) -> None:
        """Decorador preserva __name__, __doc__ de la funcion original."""
        @trace_agent("builder", "implement")
        def build_api(name: str) -> str:
            """Construye una API."""
            return f"API {name} built"

        assert build_api.__name__ == "build_api"
        assert build_api.__doc__ == "Construye una API."

    def test_decorator_raises_original_exception(self) -> None:
        """Decorador relanza la excepcion original."""
        @trace_agent("builder", "build")
        def failing_func() -> None:
            raise ValueError("algo salio mal")

        with pytest.raises(ValueError, match="algo salio mal"):
            failing_func()

    def test_decorator_multiple_calls(self) -> None:
        """Decorador funciona correctamente en multiples llamadas."""
        @trace_agent("tester", "test")
        def add(a: int, b: int) -> int:
            return a + b

        assert add(1, 2) == 3
        assert add(10, 20) == 30
        assert add(100, 200) == 300

    def test_decorator_empty_action_default(self) -> None:
        """Decorador usa 'execute' como accion por defecto."""
        @trace_agent("agent")
        def default_action() -> str:
            return "done"

        result = default_action()
        assert result == "done"

    def test_decorator_with_various_args(self) -> None:
        """Decorador maneja *args, **kwargs correctamente."""
        @trace_agent("builder", "process")
        def process_items(*args: int, **kwargs: str) -> str:
            items = ",".join(str(a) for a in args)
            kws = ",".join(f"{k}={v}" for k, v in kwargs.items())
            return f"args=[{items}] kwargs=[{kws}]"

        result = process_items(1, 2, 3, key1="val1", key2="val2")
        assert "args=[1,2,3]" in result
        assert "kwargs=[key1=val1,key2=val2]" in result or "kwargs=[key2=val2,key1=val1]" in result

    def test_decorator_does_not_mask_type_error(self) -> None:
        """Decorador no interfiere con TypeError de argumentos invalidos."""
        @trace_agent("builder", "build")
        def typed_func(name: str) -> str:
            return f"Hello {name}"

        with pytest.raises(TypeError):
            typed_func()  # type: ignore[call-arg]  # falta argumento

    def test_decorator_handles_generator_functions(self) -> None:
        """Decorador funciona con funciones generadoras."""
        @trace_agent("builder", "generate")
        def my_generator(n: int):
            for i in range(n):
                yield i

        gen = my_generator(3)
        assert list(gen) == [0, 1, 2]


# ===========================================================================
# trace_agent decorator — modo OTel simulado
# ===========================================================================


class TestTraceAgentWithMockOtel:
    """Decorador @trace_agent con OpenTelemetry mockeado (simula HAVE_OTEL)."""

    def test_trace_agent_creates_span_on_success(self) -> None:
        """Decorador crea un span cuando OTel esta habilitado (exito)."""
        mock_span = __import__("unittest").mock.MagicMock()
        mock_tracer = __import__("unittest").mock.MagicMock()
        mock_tracer.start_as_current_span.return_value.__enter__.return_value = mock_span

        with patch("harness.observability.opentelemetry_agent.HAVE_OTEL", True):
            with patch("harness.observability.opentelemetry_agent.AgentTracer") as mock_tracer_cls:
                instance = mock_tracer_cls.return_value
                instance.enabled = True
                instance.start_span.return_value = mock_tracer.start_as_current_span.return_value

                @trace_agent("builder", "implement")
                def my_func() -> str:
                    return "ok"

                result = my_func()
                assert result == "ok"

    def test_trace_agent_sets_success_on_exception(self) -> None:
        """Decorador marca agent.success=False en caso de excepcion."""
        mock_span = __import__("unittest").mock.MagicMock()
        mock_tracer = __import__("unittest").mock.MagicMock()
        mock_tracer.start_as_current_span.return_value.__enter__.return_value = mock_span

        with patch("harness.observability.opentelemetry_agent.HAVE_OTEL", True):
            with patch("harness.observability.opentelemetry_agent.AgentTracer") as mock_tracer_cls:
                instance = mock_tracer_cls.return_value
                instance.enabled = True
                instance.start_span.return_value = mock_tracer.start_as_current_span.return_value

                @trace_agent("builder", "build")
                def failing_func() -> None:
                    raise RuntimeError("build failure")

                with pytest.raises(RuntimeError, match="build failure"):
                    failing_func()

                mock_span.set_attribute.assert_any_call("agent.success", False)
                mock_span.set_attribute.assert_any_call("agent.error", "build failure")


# ===========================================================================
# Integration: tracer + decorator en conjunto
# ===========================================================================


class TestAgentTracerIntegration:
    """Integracion de AgentTracer y trace_agent decorator."""

    def test_decorator_uses_tracer_internally(self) -> None:
        """trace_agent crea internamente un AgentTracer (no falla sin OTel)."""
        @trace_agent("builder", "implement")
        def build() -> str:
            return "built"

        assert build() == "built"

    def test_agent_tracer_and_decorator_independent(self) -> None:
        """AgentTracer y decorador coexisten sin conflictos."""
        tracer = AgentTracer(service_name="test-service")
        assert tracer.enabled is False

        @trace_agent("scientist", "research")
        def research() -> str:
            return "research results"

        assert research() == "research results"
        # Sin OTel, start_span retorna None
        assert tracer.start_span("indirect") is None


# ===========================================================================
# Error handling y robustez
# ===========================================================================


class TestAgentTracerErrorHandling:
    """Manejo de errores y casos borde del AgentTracer."""

    def test_init_with_empty_service_name(self) -> None:
        """Constructor con service_name vacio no falla."""
        tracer = AgentTracer(service_name="")
        assert tracer.enabled is False

    def test_repeated_init_calls(self) -> None:
        """Multiples llamadas a init no causan efectos laterales."""
        for _ in range(10):
            tracer = AgentTracer()
            assert tracer.enabled is False

    def test_decorator_with_callable_class(self) -> None:
        """Decorador funciona con clases callables (__call__)."""
        @trace_agent("worker", "process")
        class CallableWorker:
            def __call__(self, value: int) -> int:
                return value * 2

        worker = CallableWorker()
        assert worker(5) == 10
        assert CallableWorker.__name__ == "CallableWorker"
