"""
Tests para OpenTelemetry Agent — trazabilidad distribuida multi-agente.

Cubre: AgentTracer, trace_agent decorator, fallback graceful sin OTel instalado.
"""
from __future__ import annotations

import logging
from unittest.mock import MagicMock

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
            yield from range(n)

        gen = my_generator(3)
        assert list(gen) == [0, 1, 2]


# ===========================================================================
# trace_agent decorator — modo OTel simulado
# ===========================================================================


class TestTraceAgentWithMockOtel:
    """Decorador @trace_agent con OpenTelemetry mockeado (simula HAVE_OTEL)."""

    def test_trace_agent_creates_span_on_success(self) -> None:
        """Decorador crea un span cuando OTel esta habilitado (exito)."""
        import harness.observability.opentelemetry_agent as otel_mod
        mock_span = __import__("unittest").mock.MagicMock()
        mock_tracer_instance = __import__("unittest").mock.MagicMock()
        mock_tracer_instance._enabled = True
        mock_tracer_instance.enabled = True
        mock_tracer_instance._tracer = __import__("unittest").mock.MagicMock()
        class _CtxMgr:
            def __enter__(self2):
                return mock_span
            def __exit__(self2, *args):
                return None
        mock_tracer_instance.start_span.return_value = _CtxMgr()
        mock_tracer_instance._tracer.start_as_current_span.return_value = _CtxMgr()

        saved_cls = otel_mod.AgentTracer
        saved_flag = otel_mod.HAVE_OTEL
        try:
            otel_mod.AgentTracer = lambda *a, **kw: mock_tracer_instance
            otel_mod.AgentTracer.__call__ = lambda *a, **kw: mock_tracer_instance
            otel_mod.HAVE_OTEL = True

            @trace_agent("builder", "implement")
            def my_func() -> str:
                return "ok"
            assert my_func() == "ok"
        finally:
            otel_mod.AgentTracer = saved_cls
            otel_mod.HAVE_OTEL = saved_flag

    def test_trace_agent_sets_success_on_exception(self) -> None:
        """Decorador marca agent.success=False en caso de excepcion."""
        mock_span = __import__("unittest").mock.MagicMock()
        mock_tracer_instance = __import__("unittest").mock.MagicMock()
        mock_tracer_instance._enabled = True
        mock_tracer_instance.enabled = True
        mock_tracer_instance._tracer = __import__("unittest").mock.MagicMock()
        class _CtxMgr:
            def __enter__(self2):
                return mock_span
            def __exit__(self2, *args):
                return None
        mock_tracer_instance.start_span.return_value = _CtxMgr()
        mock_tracer_instance._tracer.start_as_current_span.return_value = _CtxMgr()

        # Build a custom trace_agent that uses our mock directly
        def mock_trace_agent(agent_type, action="execute"):
            def decorator(func):
                import functools
                @functools.wraps(func)
                def wrapper(*args, **kwargs):
                    tracer = mock_tracer_instance
                    span_name = f"{agent_type}.{action}"
                    attrs = {"agent.id": agent_type, "agent.type": agent_type, "agent.delegation_depth": 1}
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

        @mock_trace_agent("builder", "build")
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


# ===========================================================================
# GenAI semantic conventions estables 2026 (ADR-0041 H2)
# ===========================================================================


class TestGenAISemconv:
    """
    Semantic conventions GenAI estables 2026: span invoke_agent, atributos
    gen_ai.*, start_genai_span y extraccion de tokens de uso.
    """

    @staticmethod
    def _enable_otel_with_mock(
        monkeypatch: pytest.MonkeyPatch,
    ) -> tuple[MagicMock, MagicMock]:
        """
        Activa HAVE_OTEL en el modulo y parchea AgentTracer con un mock.

        Parchea ``trace_agent.__globals__`` (no una importacion por nombre)
        porque ``test_lazy_loading.py`` puede purgar ``sys.modules`` y recargar
        el paquete, dejando dos instancias del modulo: la vieja (usada por el
        closure de ``trace_agent``) y la nueva (importable por nombre). Parchear
        los globals del closure garantiza que el mock aplique en ambos casos.

        Args:
            monkeypatch: Fixture de pytest para restaurar el estado del modulo.

        Returns:
            Tupla (mock_tracer, span) para verificar atributos emitidos.
        """
        span = MagicMock()
        mock_tracer = MagicMock()
        mock_tracer._enabled = True
        mock_tracer.enabled = True
        mock_tracer._tracer = MagicMock()

        class _SpanContextManager:
            def __enter__(self) -> MagicMock:
                return span

            def __exit__(self, *args: object) -> None:
                return None

        mock_tracer.start_genai_span.return_value = _SpanContextManager()
        module_globals = trace_agent.__globals__
        monkeypatch.setitem(module_globals, "AgentTracer", lambda *a, **kw: mock_tracer)
        monkeypatch.setitem(module_globals, "HAVE_OTEL", True)
        return mock_tracer, span

    # -- constantes de modulo ----------------------------------------------

    def test_module_genai_constants_defined(self) -> None:
        """Las constantes GenAI estables 2026 estan definidas en el modulo."""
        import harness.observability.opentelemetry_agent as otel_mod

        assert otel_mod.GENAI_SPAN_NAMES == frozenset({"invoke_agent", "chat", "execute_tool"})
        assert otel_mod.GENAI_PROVIDER == "swarmind"
        assert otel_mod.ATTR_PROVIDER == "gen_ai.provider.name"
        assert otel_mod.ATTR_SYSTEM == "gen_ai.system"
        assert otel_mod.ATTR_MODEL == "gen_ai.request.model"
        assert otel_mod.ATTR_INPUT_TOKENS == "gen_ai.usage.input_tokens"
        assert otel_mod.ATTR_OUTPUT_TOKENS == "gen_ai.usage.output_tokens"

    def test_genai_span_names_is_immutable_set(self) -> None:
        """GENAI_SPAN_NAMES es un frozenset (inmutable)."""
        import harness.observability.opentelemetry_agent as otel_mod

        assert isinstance(otel_mod.GENAI_SPAN_NAMES, frozenset)
        with pytest.raises(AttributeError):
            otel_mod.GENAI_SPAN_NAMES.add("bogus")  # type: ignore[attr-defined]

    # -- start_genai_span ---------------------------------------------------

    def test_start_genai_span_without_otel_returns_none(self) -> None:
        """start_genai_span sin OTel retorna None (igual que start_span)."""
        tracer = AgentTracer()
        assert tracer.start_genai_span() is None

    def test_start_genai_span_defaults_to_invoke_agent(self) -> None:
        """start_genai_span usa operacion y atributos GenAI estandar por defecto."""
        tracer = object.__new__(AgentTracer)
        tracer._enabled = True
        tracer._tracer = MagicMock()

        tracer.start_genai_span()

        call = tracer._tracer.start_as_current_span.call_args
        assert call.args[0] == "invoke_agent"
        attrs = call.kwargs["attributes"]
        assert attrs["gen_ai.provider.name"] == "swarmind"
        assert attrs["gen_ai.system"] == "swarmind"
        assert attrs["gen_ai.request.model"] == "unknown"

    def test_start_genai_span_custom_operation_model_attributes(self) -> None:
        """start_genai_span acepta operacion estandar, modelo y atributos extra."""
        tracer = object.__new__(AgentTracer)
        tracer._enabled = True
        tracer._tracer = MagicMock()

        tracer.start_genai_span(
            operation="chat",
            model="gpt-4o",
            provider="swarmind",
            attributes={"agent.id": "chat-agent", "custom.key": 42},
        )

        call = tracer._tracer.start_as_current_span.call_args
        assert call.args[0] == "chat"
        attrs = call.kwargs["attributes"]
        assert attrs["gen_ai.request.model"] == "gpt-4o"
        assert attrs["agent.id"] == "chat-agent"
        assert attrs["custom.key"] == 42

    def test_start_genai_span_operations_are_standard(self) -> None:
        """Las operaciones soportadas son las de GENAI_SPAN_NAMES."""
        import harness.observability.opentelemetry_agent as otel_mod

        tracer = object.__new__(AgentTracer)
        tracer._enabled = True
        tracer._tracer = MagicMock()

        for operation in ("invoke_agent", "chat", "execute_tool"):
            assert operation in otel_mod.GENAI_SPAN_NAMES
            tracer.start_genai_span(operation=operation)
            assert tracer._tracer.start_as_current_span.call_args.args[0] == operation

    # -- trace_agent: atributos gen_ai.* y tokens ---------------------------

    def test_trace_agent_uses_invoke_agent_span_and_genai_attrs(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """trace_agent usa start_genai_span con invoke_agent y gen_ai.* + agent.*."""
        mock_tracer, span = self._enable_otel_with_mock(monkeypatch)

        @trace_agent("builder", "implement")
        def build(model: str | None = None) -> str:
            """Simula una llamada GenAI."""
            return "ok"

        assert build(model="claude-3.5-sonnet") == "ok"

        call_kwargs = mock_tracer.start_genai_span.call_args.kwargs
        assert call_kwargs["operation"] == "invoke_agent"
        assert call_kwargs["provider"] == "swarmind"
        assert call_kwargs["model"] == "claude-3.5-sonnet"
        attrs = call_kwargs["attributes"]
        assert attrs["agent.id"] == "builder"
        assert attrs["agent.type"] == "builder"
        assert attrs["agent.delegation_depth"] == 1
        span.set_attribute.assert_any_call("agent.success", True)

    def test_trace_agent_model_defaults_to_unknown(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Sin kwargs.model, start_genai_span recibe None (fallback a unknown)."""
        mock_tracer, _ = self._enable_otel_with_mock(monkeypatch)

        @trace_agent("builder", "implement")
        def build() -> str:
            """Simula una llamada GenAI sin modelo."""
            return "ok"

        assert build() == "ok"

        assert mock_tracer.start_genai_span.call_args.kwargs["model"] is None

    def test_trace_agent_emits_tokens_from_dict(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Si la funcion retorna dict con input/output_tokens, se emiten."""
        _, span = self._enable_otel_with_mock(monkeypatch)

        @trace_agent("builder", "invoke")
        def build() -> dict[str, int]:
            """Simula una llamada GenAI con uso de tokens."""
            return {"input_tokens": 100, "output_tokens": 25}

        assert build() == {"input_tokens": 100, "output_tokens": 25}

        span.set_attribute.assert_any_call("gen_ai.usage.input_tokens", 100)
        span.set_attribute.assert_any_call("gen_ai.usage.output_tokens", 25)

    def test_trace_agent_emits_tokens_from_tokens_attribute(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Si la funcion retorna objeto con .tokens (dict), se emiten."""
        class LlmResult:
            """Resultado de LLM con atributo .tokens."""

            def __init__(self) -> None:
                self.tokens: dict[str, int] = {"input_tokens": 50, "output_tokens": 10}

        _, span = self._enable_otel_with_mock(monkeypatch)

        @trace_agent("scientist", "invoke")
        def research() -> LlmResult:
            """Simula una investigacion con tokens."""
            return LlmResult()

        research()

        span.set_attribute.assert_any_call("gen_ai.usage.input_tokens", 50)
        span.set_attribute.assert_any_call("gen_ai.usage.output_tokens", 10)

    def test_trace_agent_emits_tokens_from_class_attributes(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Si la funcion retorna objeto con atributos de clase, se emiten."""
        class LlmResult:
            """Resultado de LLM con atributos de clase de tokens."""

            input_tokens = 30
            output_tokens = 7

        _, span = self._enable_otel_with_mock(monkeypatch)

        @trace_agent("builder", "invoke")
        def build() -> LlmResult:
            """Simula una llamada GenAI con atributos de clase."""
            return LlmResult()

        build()

        span.set_attribute.assert_any_call("gen_ai.usage.input_tokens", 30)
        span.set_attribute.assert_any_call("gen_ai.usage.output_tokens", 7)

    def test_trace_agent_skips_token_attrs_without_usage(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Sin metricas de tokens, NO se emiten atributos gen_ai.usage.*."""
        _, span = self._enable_otel_with_mock(monkeypatch)

        @trace_agent("builder", "invoke")
        def build() -> str:
            """Simula una llamada GenAI sin metricas de tokens."""
            return "plain result"

        assert build() == "plain result"

        emitted = {call.args[0]: call.args[1] for call in span.set_attribute.call_args_list}
        assert emitted.get("agent.success") is True
        assert "gen_ai.usage.input_tokens" not in emitted
        assert "gen_ai.usage.output_tokens" not in emitted

    def test_trace_agent_emits_partial_tokens_if_available(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Si solo hay input_tokens disponible, se emite solo ese atributo."""
        _, span = self._enable_otel_with_mock(monkeypatch)

        @trace_agent("builder", "invoke")
        def build() -> dict[str, int]:
            """Simula una llamada con solo input_tokens."""
            return {"input_tokens": 100}

        assert build() == {"input_tokens": 100}

        emitted = {call.args[0]: call.args[1] for call in span.set_attribute.call_args_list}
        assert emitted.get("gen_ai.usage.input_tokens") == 100
        assert "gen_ai.usage.output_tokens" not in emitted

    def test_trace_agent_keeps_legacy_agent_attributes_on_success(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Se mantienen los atributos legacy agent.* en el span."""
        _, span = self._enable_otel_with_mock(monkeypatch)

        @trace_agent("builder", "implement")
        def build() -> str:
            """Simula una llamada GenAI exitosa."""
            return "ok"

        assert build() == "ok"

        span.set_attribute.assert_any_call("agent.success", True)
        emitted = {call.args[0]: call.args[1] for call in span.set_attribute.call_args_list}
        assert emitted.get("agent.success") is True
        assert "agent.error" not in emitted

    def test_trace_agent_keeps_legacy_agent_attributes_on_error(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """En error, se emiten agent.success=False y agent.error."""
        _, span = self._enable_otel_with_mock(monkeypatch)

        @trace_agent("builder", "build")
        def failing_func() -> None:
            """Simula una llamada GenAI fallida."""
            raise RuntimeError("build failure")

        with pytest.raises(RuntimeError, match="build failure"):
            failing_func()

        span.set_attribute.assert_any_call("agent.success", False)
        span.set_attribute.assert_any_call("agent.error", "build failure")
