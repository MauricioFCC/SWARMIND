"""AIFactory layers — mixin con los ejecutores de cada capa.

Extraccion mecanica de los metodos privados ``_execute_*`` de la clase
``AIFactory`` del modulo original ``harness/aifactory/factory.py``
(sin cambios de logica ni firmas). La clase ``AIFactory`` los hereda
via mixin. Incluye tambien ``process_stream()`` (pipeline async) que
originalmente vivia en ``stream.py``/``_StreamMixin`` (fusionado aqui
por cohesion: ambos son ejecucion de capas; reduce la herencia a 2
mixins, regla SOL del repo).
"""

from __future__ import annotations

import logging
import time
import uuid
from collections.abc import AsyncGenerator
from typing import Any

from harness.aifactory.factory_types import (
    EvalReport,
    FactoryConfig,
    FactoryStatus,
    LayerTrace,
    LayerType,
    _simulate_agent_execution,
    _simulate_evals,
    _simulate_guardrail,
    _simulate_llm_call,
    _simulate_mcp_call,
    _simulate_rag_retrieval,
)

logger = logging.getLogger("harness.aifactory.factory")


class _LayerExecutorMixin:
    """Mixin con la ejecucion de las 7 capas del pipeline."""

    def _execute_guardrail_input(
        self, text: str
    ) -> tuple[LayerTrace, bool]:
        """Ejecuta la capa de guardrail de entrada.

        Args:
            text: Texto de entrada a validar.

        Returns:
            Tupla de (LayerTrace, blocked: bool).
        """
        start = time.perf_counter()
        passed, reason = _simulate_guardrail(text, "input")
        latency = (time.perf_counter() - start) * 1000

        trace = LayerTrace(
            layer_name="GuardrailInput",
            layer_type=LayerType.GUARDRAIL_INPUT,
            status="blocked" if not passed else "ok",
            latency_ms=round(latency, 2),
            input=text if self._config.verbose_trace else None,
            error=reason,
        )
        return trace, not passed

    def _execute_guardrail_output(
        self, text: str
    ) -> tuple[LayerTrace, bool]:
        """Ejecuta la capa de guardrail de salida.

        Args:
            text: Texto de salida a validar.

        Returns:
            Tupla de (LayerTrace, blocked: bool).
        """
        start = time.perf_counter()
        passed, reason = _simulate_guardrail(text, "output")
        latency = (time.perf_counter() - start) * 1000

        trace = LayerTrace(
            layer_name="GuardrailOutput",
            layer_type=LayerType.GUARDRAIL_OUTPUT,
            status="blocked" if not passed else "ok",
            latency_ms=round(latency, 2),
            output=text if self._config.verbose_trace else None,
            error=reason,
        )
        return trace, not passed

    def _execute_llm(self, prompt: str, model: str, retry: bool = False) -> LayerTrace:
        """Ejecuta la capa de inteligencia (LLM).

        Args:
            prompt: Prompt de entrada para el LLM.
            model: Modelo a utilizar.
            retry: Si es True, indica que es un reintento.

        Returns:
            LayerTrace con el resultado de la llamada LLM.
        """
        start = time.perf_counter()
        try:
            response, latency = _simulate_llm_call(prompt, model)
            return LayerTrace(
                layer_name=f"LLM:{model}" + ("(retry)" if retry else ""),
                layer_type=LayerType.INTELLIGENCE,
                status="ok",
                latency_ms=round(latency, 2),
                input=prompt if self._config.verbose_trace else None,
                output=response if self._config.verbose_trace else None,
                retries=1 if retry else 0,
            )
        except Exception as exc:  # noqa: BLE001
            latency = (time.perf_counter() - start) * 1000
            error_msg = f"Error en LLM call: {exc}"
            logger.error(
                "[AIFactory] %s | model=%s WHAT=LLM call failed "
                "WHY=%s WHERE=_execute_llm",
                error_msg,
                model,
                exc,
            )
            return LayerTrace(
                layer_name=f"LLM:{model}",
                layer_type=LayerType.INTELLIGENCE,
                status="error",
                latency_ms=round(latency, 2),
                error=error_msg,
                retries=1 if retry else 0,
            )

    def _execute_rag(self, query: str) -> LayerTrace:
        """Ejecuta la capa de conocimiento (RAG + VectorDB).

        Args:
            query: Consulta para retrieval en la base de conocimiento.

        Returns:
            LayerTrace con los documentos recuperados.
        """
        start = time.perf_counter()
        try:
            docs, latency = _simulate_rag_retrieval(query)
            output_data = docs if self._config.verbose_trace else (
                f"{len(docs)} documentos recuperados"
            )
            return LayerTrace(
                layer_name="RAG:VectorDB",
                layer_type=LayerType.KNOWLEDGE,
                status="ok",
                latency_ms=round(latency, 2),
                input=query if self._config.verbose_trace else None,
                output=output_data,
            )
        except Exception as exc:  # noqa: BLE001
            latency = (time.perf_counter() - start) * 1000
            error_msg = f"Error en RAG retrieval: {exc}"
            logger.error(
                "[AIFactory] %s | query=%s WHAT=RAG retrieval failed "
                "WHY=%s WHERE=_execute_rag",
                error_msg,
                query[:60],
                exc,
            )
            return LayerTrace(
                layer_name="RAG:VectorDB",
                layer_type=LayerType.KNOWLEDGE,
                status="error",
                latency_ms=round(latency, 2),
                error=error_msg,
            )

    def _execute_agent(
        self, task: str, context: dict[str, Any]
    ) -> LayerTrace:
        """Ejecuta la capa de agente (planning + tool use).

        Args:
            task: Descripcion de la tarea a ejecutar.
            context: Contexto enriquecido del pipeline.

        Returns:
            LayerTrace con el resultado de la ejecucion del agente.
        """
        start = time.perf_counter()
        try:
            result, latency = _simulate_agent_execution(task, context)
            return LayerTrace(
                layer_name="Agent:ReAct",
                layer_type=LayerType.EXECUTION,
                status="ok",
                latency_ms=round(latency, 2),
                input=task if self._config.verbose_trace else None,
                output=result if self._config.verbose_trace else None,
            )
        except Exception as exc:  # noqa: BLE001
            latency = (time.perf_counter() - start) * 1000
            error_msg = f"Error en Agent execution: {exc}"
            logger.error(
                "[AIFactory] %s | task=%s WHAT=Agent execution failed "
                "WHY=%s WHERE=_execute_agent",
                error_msg,
                task[:60],
                exc,
            )
            return LayerTrace(
                layer_name="Agent:ReAct",
                layer_type=LayerType.EXECUTION,
                status="error",
                latency_ms=round(latency, 2),
                error=error_msg,
            )

    def _execute_mcp(
        self, context: str, params: dict[str, Any]
    ) -> LayerTrace:
        """Ejecuta la capa de integracion (MCP).

        Args:
            context: Contexto de la tarea para determinar herramienta.
            params: Parametros adicionales para la llamada MCP.

        Returns:
            LayerTrace con el resultado de la llamada MCP.
        """
        start = time.perf_counter()
        tool_name = "code_interpreter"
        try:
            response, latency = _simulate_mcp_call(tool_name, params)
            output_str = (
                f"Tool '{tool_name}' ejecutada: "
                f"{response.get('result', 'sin resultado')}"
            )
            return LayerTrace(
                layer_name=f"MCP:{tool_name}",
                layer_type=LayerType.INTEGRATION,
                status="ok",
                latency_ms=round(latency, 2),
                input=context if self._config.verbose_trace else None,
                output=output_str if self._config.verbose_trace else None,
            )
        except Exception as exc:  # noqa: BLE001
            latency = (time.perf_counter() - start) * 1000
            error_msg = f"Error en MCP call '{tool_name}': {exc}"
            logger.error(
                "[AIFactory] %s | tool=%s WHAT=MCP call failed "
                "WHY=%s WHERE=_execute_mcp",
                error_msg,
                tool_name,
                exc,
            )
            return LayerTrace(
                layer_name=f"MCP:{tool_name}",
                layer_type=LayerType.INTEGRATION,
                status="error",
                latency_ms=round(latency, 2),
                error=error_msg,
            )

    def _execute_evals(
        self, input_text: str, output_text: str, layers: list[LayerTrace]
    ) -> tuple[LayerTrace, EvalReport]:
        """Ejecuta la capa de evaluacion continua.

        Args:
            input_text: Texto de entrada original.
            output_text: Texto de salida generado.
            layers: Trazas de capas ejecutadas.

        Returns:
            Tupla de (LayerTrace, EvalReport).
        """
        start = time.perf_counter()
        try:
            report = _simulate_evals(input_text, output_text, layers)
            latency = (time.perf_counter() - start) * 1000
            trace = LayerTrace(
                layer_name="Evals:Continuous",
                layer_type=LayerType.EVALS,
                status="ok",
                latency_ms=round(latency, 2),
                output=(
                    f"pass_rate={report.pass_rate}, "
                    f"passed={report.passed_checks}/{report.total_checks}"
                ),
            )
            return trace, report
        except Exception as exc:  # noqa: BLE001
            latency = (time.perf_counter() - start) * 1000
            error_msg = f"Error en Evals: {exc}"
            logger.error(
                "[AIFactory] %s WHAT=Evals execution failed "
                "WHY=%s WHERE=_execute_evals",
                error_msg,
                exc,
            )
            return LayerTrace(
                layer_name="Evals:Continuous",
                layer_type=LayerType.EVALS,
                status="error",
                latency_ms=round(latency, 2),
                error=error_msg,
            ), EvalReport()

    async def process_stream(
        self, input_text: str, config: FactoryConfig | None = None
    ) -> AsyncGenerator[LayerTrace, None]:
        """Ejecuta el pipeline en modo streaming, yield por capa.

        Permite a los consumidores recibir resultados parciales a
        medida que cada capa se completa, ideal para UI en tiempo real
        o dashboards de monitoreo.

        Args:
            input_text: Texto de entrada a procesar.
            config: Configuracion opcional para esta ejecucion.

        Yields:
            LayerTrace por cada capa completada, en orden de ejecucion.

        Raises:
            ValueError: Si input_text esta vacio.
        """
        if not input_text or not input_text.strip():
            error_msg = (
                "[AIFactory] Input vacio en process_stream: "
                "se requiere texto no vacio."
            )
            logger.error(error_msg)
            raise ValueError(error_msg)

        active_config = config or self._config
        pipeline_id = uuid.uuid4().hex[:12]
        self._status = FactoryStatus.PROCESSING
        self._lock.acquire()

        try:
            # Capa 1: Guardrail Input
            if active_config.guardrails_enabled:
                self._status = FactoryStatus.GUARDRAIL_BLOCKED
                trace, blocked = self._execute_guardrail_input(input_text)
                yield trace
                if blocked:
                    self._status = FactoryStatus.GUARDRAIL_BLOCKED
                    self._metrics["blocked"] += 1
                    return
            else:
                yield LayerTrace(
                    layer_name="GuardrailInput",
                    layer_type=LayerType.GUARDRAIL_INPUT,
                    status="skipped",
                )

            # Capa 2: LLM
            self._status = FactoryStatus.LLM_CALL
            llm_trace = self._execute_llm(input_text, active_config.default_model)
            yield llm_trace

            # Capa 3: RAG
            self._status = FactoryStatus.RAG_RETRIEVAL
            rag_trace = self._execute_rag(input_text)
            yield rag_trace

            # Capa 4: Agent
            self._status = FactoryStatus.AGENT_EXECUTION
            agent_trace = self._execute_agent(input_text, {"docs": [], "tools": []})
            yield agent_trace

            # Capa 5: MCP
            self._status = FactoryStatus.MCP_CALL
            mcp_trace = self._execute_mcp(input_text, {})
            yield mcp_trace

            # Capa 6: Guardrail Output
            if active_config.guardrails_enabled and llm_trace.output:
                output_trace, _ = self._execute_guardrail_output(
                    llm_trace.output
                )
                yield output_trace
            else:
                yield LayerTrace(
                    layer_name="GuardrailOutput",
                    layer_type=LayerType.GUARDRAIL_OUTPUT,
                    status="skipped",
                )

            # Capa 7: Evals
            if active_config.evals_enabled and llm_trace.output:
                eval_trace, _ = self._execute_evals(
                    input_text, llm_trace.output, []
                )
                yield eval_trace
            else:
                yield LayerTrace(
                    layer_name="Evals",
                    layer_type=LayerType.EVALS,
                    status="skipped",
                )

            self._status = FactoryStatus.COMPLETED
            self._metrics["completed"] += 1

        except Exception as exc:
            logger.exception(
                "[AIFactory] Error en streaming | id=%s", pipeline_id,
            )
            self._status = FactoryStatus.FAILED
            yield LayerTrace(
                layer_name="StreamingError",
                layer_type=LayerType.ORCHESTRATOR,
                status="error",
                error=str(exc),
            )

        finally:
            self._lock.release()
            self._metrics["total_pipelines"] += 1
