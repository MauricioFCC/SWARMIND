"""AIFactory pipeline — mixin con el pipeline principal ``process()``.

Extraccion mecanica del metodo ``process()`` de la clase ``AIFactory``
del modulo original ``harness/aifactory/factory.py`` (sin cambios de
logica ni firmas). La clase ``AIFactory`` lo hereda via mixin.

El metodo ``process()`` actua como orquestador (FSZ: <=30 lineas) y
delega cada capa en un helper ``_run_layer_*``; el estado mutable de la
ejecucion viaja en ``_PipelineRun`` para preservar el orden de efectos.
"""

from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from harness.aifactory.factory_types import (
    EvalReport,
    FactoryConfig,
    FactoryResult,
    FactoryStatus,
    LayerTrace,
    LayerType,
)

logger = logging.getLogger("harness.aifactory.factory")


@dataclass
class _PipelineRun:
    """Estado mutable compartido durante una ejecucion del pipeline.

    Attributes:
        input_text: Texto de entrada original.
        active_config: Configuracion efectiva de la ejecucion.
        pipeline_id: Identificador corto del pipeline.
        pipeline_start: Timestamp de inicio (para medir latencia).
        layers: Trazas de las capas ejecutadas, en orden.
        guardrail_results: Resultados crudos de los guardrails.
        current_input: Entrada vigente para las capas.
        current_output: Salida vigente del pipeline.
        pipeline_error: Error global detectado (si aplica).
        final_status: Estado final acumulado.
        context: Contexto enriquecido (docs y tools).
        eval_report: Reporte de evaluacion de la capa 7.
    """

    input_text: str
    active_config: FactoryConfig
    pipeline_id: str
    pipeline_start: float
    layers: list[LayerTrace] = field(default_factory=list)
    guardrail_results: list[dict[str, Any]] = field(default_factory=list)
    current_input: str = ""
    current_output: str | None = None
    pipeline_error: str | None = None
    final_status: FactoryStatus = FactoryStatus.COMPLETED
    context: dict[str, Any] = field(default_factory=lambda: {"docs": [], "tools": []})
    eval_report: EvalReport = field(default_factory=EvalReport)


def _append_skipped_layer(
    run: _PipelineRun, layer_name: str, layer_type: LayerType
) -> None:
    """Agrega una LayerTrace marcada como 'skipped' a la ejecucion.

    Args:
        run: Estado mutable de la ejecucion en curso.
        layer_name: Nombre legible de la capa omitida.
        layer_type: Tipo de capa a registrar.
    """
    run.layers.append(
        LayerTrace(
            layer_name=layer_name,
            layer_type=layer_type,
            status="skipped",
            latency_ms=0.0,
        )
    )


def _record_guardrail_result(
    run: _PipelineRun, layer: str, blocked: bool, trace: LayerTrace
) -> None:
    """Registra el resultado crudo de un guardrail en la ejecucion.

    Args:
        run: Estado mutable de la ejecucion en curso.
        layer: Identificador de la capa ("input" u "output").
        blocked: Indica si el guardrail bloqueo el texto.
        trace: Traza generada por el guardrail.
    """
    run.guardrail_results.append(
        {
            "layer": layer,
            "blocked": blocked,
            "reason": trace.error,
            "latency_ms": trace.latency_ms,
        }
    )


def _blocked_input_message(reason: str | None) -> str:
    """Construye el output cuando el guardrail de entrada bloquea.

    Args:
        reason: Motivo del bloqueo reportado por el guardrail.

    Returns:
        Mensaje de output para el resultado bloqueado.
    """
    return (
        f"Input bloqueado por guardrails de seguridad.\n"
        f"Motivo: {reason}"
    )


def _blocked_output_message(reason: str | None) -> str:
    """Construye el output cuando el guardrail de salida bloquea.

    Args:
        reason: Motivo del bloqueo reportado por el guardrail.

    Returns:
        Mensaje de output para el resultado bloqueado.
    """
    return (
        f"Output bloqueado por guardrails de seguridad.\n"
        f"Motivo: {reason}"
    )


def _format_retrieved_docs(output: Any) -> str:
    """Formatea los documentos recuperados para enriquecer el output.

    Args:
        output: Salida de la capa RAG (lista de dicts u otro valor).

    Returns:
        Texto con un item por documento recuperado.
    """
    docs = output if isinstance(output, list) else []
    return "\n".join(
        f"- [{doc.get('id', '?')}] (score={doc.get('score', 'N/A')}): "
        f"{doc.get('content', '')[:100]}"
        for doc in docs
    )


class _PipelineMixin:
    """Mixin con el pipeline principal de 7 capas (sync)."""

    def process(
        self, input_text: str, config: FactoryConfig | None = None
    ) -> FactoryResult:
        """Ejecuta el pipeline completo de 7 capas en modo sincrono.

        Args:
            input_text: Texto de entrada a procesar.
            config: Configuracion opcional para esta ejecucion.

        Returns:
            FactoryResult con el output, trazas y evaluacion.

        Raises:
            ValueError: Si input_text esta vacio o es solo espacios.
            RuntimeError: Si el factory ya esta ejecutando un pipeline.
        """
        self._acquire_run_lock(input_text)
        run = self._start_run(input_text, config)
        try:
            if self._run_layer_guardrail_input(run):
                return self._build_blocked_result(run)
            self._run_layer_intelligence(run)
            self._run_layer_knowledge(run)
            self._run_layer_execution(run)
            self._run_layer_integration(run)
            self._run_layer_guardrail_output(run)
            self._run_layer_evals(run)
            return self._finalize_pipeline(run)
        except Exception as exc:  # noqa: BLE001
            return self._handle_unexpected_error(run, exc)
        finally:
            self._lock.release()

    def _acquire_run_lock(self, input_text: str) -> None:
        """Valida la entrada y adquiere el lock de ejecucion.

        Args:
            input_text: Texto de entrada a validar.

        Raises:
            ValueError: Si input_text esta vacio o es solo espacios.
            RuntimeError: Si el factory ya esta ejecutando un pipeline.
        """
        if not input_text or not input_text.strip():
            error_msg = (
                "[AIFactory] Input vacio: se requiere texto no vacio para procesar."
            )
            logger.error(error_msg)
            raise ValueError(error_msg)
        if not self._lock.acquire(blocking=False):
            error_msg = (
                "[AIFactory] Factory ocupado: ya hay un pipeline en ejecucion. "
                "Use reset() o espere a que finalice."
            )
            logger.error(error_msg)
            raise RuntimeError(error_msg)

    def _start_run(
        self, input_text: str, config: FactoryConfig | None
    ) -> _PipelineRun:
        """Inicializa el estado mutable de una ejecucion del pipeline.

        Args:
            input_text: Texto de entrada a procesar.
            config: Configuracion opcional para esta ejecucion.

        Returns:
            _PipelineRun con el estado inicial (sin capas ejecutadas).
        """
        active_config = config or self._config
        pipeline_id = uuid.uuid4().hex[:12]
        self._status = FactoryStatus.PROCESSING
        self._is_locked = True
        pipeline_start = time.perf_counter()
        logger.info(
            "[AIFactory] Pipeline iniciado | id=%s input_len=%d config=%s",
            pipeline_id,
            len(input_text),
            "custom" if config else "default",
        )
        return _PipelineRun(
            input_text=input_text,
            active_config=active_config,
            pipeline_id=pipeline_id,
            pipeline_start=pipeline_start,
            current_input=input_text,
        )

    def _run_layer_guardrail_input(self, run: _PipelineRun) -> bool:
        """Ejecuta la capa 1 (guardrail de entrada).

        Args:
            run: Estado mutable de la ejecucion en curso.

        Returns:
            True si el input fue bloqueado y el pipeline debe abortar.
        """
        if not run.active_config.guardrails_enabled:
            _append_skipped_layer(run, "GuardrailInput", LayerType.GUARDRAIL_INPUT)
            return False
        self._status = FactoryStatus.GUARDRAIL_BLOCKED
        trace, blocked = self._execute_guardrail_input(run.current_input)
        run.layers.append(trace)
        _record_guardrail_result(run, "input", blocked, trace)
        if not blocked:
            return False
        run.final_status = FactoryStatus.GUARDRAIL_BLOCKED
        run.current_output = _blocked_input_message(trace.error)
        logger.warning(
            "[AIFactory] Pipeline bloqueado | id=%s reason=%s",
            run.pipeline_id,
            trace.error,
        )
        self._metrics["blocked"] += 1
        return True

    def _run_layer_intelligence(self, run: _PipelineRun) -> None:
        """Ejecuta la capa 2 (inteligencia/LLM) con compensacion opcional.

        Args:
            run: Estado mutable de la ejecucion en curso.
        """
        self._status = FactoryStatus.LLM_CALL
        llm_trace = self._execute_llm(
            run.current_input, run.active_config.default_model
        )
        run.layers.append(llm_trace)
        if llm_trace.status == "error" and run.active_config.compensation_enabled:
            logger.info(
                "[AIFactory] Compensando fallo LLM | "
                "id=%s retry_model=gpt-4o-mini",
                run.pipeline_id,
            )
            llm_trace = self._execute_llm(
                run.current_input, "gpt-4o-mini", retry=True
            )
            run.layers[-1] = llm_trace
        if llm_trace.status == "error":
            run.final_status = FactoryStatus.FAILED
            run.pipeline_error = llm_trace.error
            run.current_output = f"Error en capa LLM: {llm_trace.error}"
        else:
            run.current_output = llm_trace.output

    def _run_layer_knowledge(self, run: _PipelineRun) -> None:
        """Ejecuta la capa 3 (conocimiento/RAG) y enriquece el output.

        Args:
            run: Estado mutable de la ejecucion en curso.
        """
        self._status = FactoryStatus.RAG_RETRIEVAL
        query = (
            run.current_input
            if run.current_output is None
            else str(run.current_output)
        )
        rag_trace = self._execute_rag(query)
        run.layers.append(rag_trace)
        if rag_trace.status != "ok" or not rag_trace.output:
            return
        run.context["docs"] = rag_trace.output
        docs_text = _format_retrieved_docs(rag_trace.output)
        if run.current_output:
            run.current_output += f"\n\n[Conocimiento recuperado]\n{docs_text}"
        else:
            run.current_output = f"[Conocimiento recuperado]\n{docs_text}"

    def _run_layer_execution(self, run: _PipelineRun) -> None:
        """Ejecuta la capa 4 (agente) y actualiza el output si aplica.

        Args:
            run: Estado mutable de la ejecucion en curso.
        """
        self._status = FactoryStatus.AGENT_EXECUTION
        agent_trace = self._execute_agent(run.current_input, run.context)
        run.layers.append(agent_trace)
        if agent_trace.status == "ok" and agent_trace.output:
            run.current_output = agent_trace.output

    def _run_layer_integration(self, run: _PipelineRun) -> None:
        """Ejecuta la capa 5 (integracion/MCP) y anexa su resultado.

        Args:
            run: Estado mutable de la ejecucion en curso.
        """
        self._status = FactoryStatus.MCP_CALL
        mcp_trace = self._execute_mcp(run.current_input, run.context)
        run.layers.append(mcp_trace)
        if mcp_trace.status == "ok" and mcp_trace.output:
            run.context["tools"] = mcp_trace.output
            if run.current_output:
                run.current_output += (
                    f"\n\n[Herramientas MCP ejecutadas]\n"
                    f"{mcp_trace.output}"
                )

    def _run_layer_guardrail_output(self, run: _PipelineRun) -> None:
        """Ejecuta la capa 6 (guardrail de salida).

        Args:
            run: Estado mutable de la ejecucion en curso.
        """
        if not (run.active_config.guardrails_enabled and run.current_output):
            _append_skipped_layer(run, "GuardrailOutput", LayerType.GUARDRAIL_OUTPUT)
            return
        output_trace, output_blocked = self._execute_guardrail_output(
            run.current_output
        )
        run.layers.append(output_trace)
        _record_guardrail_result(run, "output", output_blocked, output_trace)
        if not output_blocked:
            return
        run.final_status = FactoryStatus.GUARDRAIL_BLOCKED
        logger.warning(
            "[AIFactory] Output bloqueado por guardrails | id=%s reason=%s",
            run.pipeline_id,
            output_trace.error,
        )
        self._metrics["blocked"] += 1
        run.current_output = _blocked_output_message(output_trace.error)

    def _run_layer_evals(self, run: _PipelineRun) -> None:
        """Ejecuta la capa 7 (evaluacion continua) si aplica.

        Args:
            run: Estado mutable de la ejecucion en curso.
        """
        if not (run.active_config.evals_enabled and run.current_output):
            _append_skipped_layer(run, "Evals", LayerType.EVALS)
            return
        eval_trace, run.eval_report = self._execute_evals(
            run.input_text, run.current_output, run.layers
        )
        run.layers.append(eval_trace)

    def _build_blocked_result(self, run: _PipelineRun) -> FactoryResult:
        """Construye el resultado cuando el guardrail de entrada bloquea.

        Args:
            run: Estado mutable de la ejecucion en curso.

        Returns:
            FactoryResult con el bloqueo registrado.
        """
        return self._build_result(
            input_text=run.input_text,
            output=run.current_output,
            status=run.final_status,
            layers=run.layers,
            pipeline_start=run.pipeline_start,
            guardrail_results=run.guardrail_results,
            pipeline_id=run.pipeline_id,
        )

    def _resolve_final_status(self, run: _PipelineRun) -> None:
        """Resuelve el estado final y actualiza las metricas asociadas.

        Args:
            run: Estado mutable de la ejecucion en curso.
        """
        if run.final_status != FactoryStatus.FAILED:
            run.final_status = FactoryStatus.COMPLETED
            self._metrics["completed"] += 1
            return
        if run.active_config.compensation_enabled and run.current_output:
            run.final_status = FactoryStatus.COMPENSATED
            self._metrics["compensated"] += 1
            logger.info(
                "[AIFactory] Pipeline compensado | id=%s",
                run.pipeline_id,
            )
            return
        self._metrics["failed"] += 1

    def _finalize_pipeline(self, run: _PipelineRun) -> FactoryResult:
        """Cierra el pipeline: estado final, metricas y resultado.

        Args:
            run: Estado mutable de la ejecucion en curso.

        Returns:
            FactoryResult consolidado de la ejecucion.
        """
        self._resolve_final_status(run)
        self._status = run.final_status
        total_latency = (time.perf_counter() - run.pipeline_start) * 1000
        self._metrics["total_latency_ms"] += total_latency
        self._metrics["total_pipelines"] += 1
        logger.info(
            "[AIFactory] Pipeline finalizado | id=%s status=%s "
            "latency_ms=%.1f layers=%d",
            run.pipeline_id,
            run.final_status.value,
            total_latency,
            len(run.layers),
        )
        return self._build_result(
            input_text=run.input_text,
            output=run.current_output,
            status=run.final_status,
            layers=run.layers,
            pipeline_start=run.pipeline_start,
            eval_report=run.eval_report,
            guardrail_results=run.guardrail_results,
            pipeline_id=run.pipeline_id,
            error=run.pipeline_error,
        )

    def _handle_unexpected_error(
        self, run: _PipelineRun, exc: Exception
    ) -> FactoryResult:
        """Registra un error no manejado y retorna un resultado FAILED.

        Args:
            run: Estado mutable de la ejecucion en curso.
            exc: Excepcion capturada durante el pipeline.

        Returns:
            FactoryResult con estado FAILED y el error registrado.
        """
        self._status = FactoryStatus.FAILED
        self._metrics["failed"] += 1
        self._metrics["total_pipelines"] += 1
        error_msg = (
            f"[AIFactory] Error no manejado en pipeline | "
            f"id={run.pipeline_id} error={exc}"
        )
        logger.exception(error_msg)
        return self._build_result(
            input_text=run.input_text,
            output=None,
            status=FactoryStatus.FAILED,
            layers=run.layers,
            pipeline_start=run.pipeline_start,
            guardrail_results=run.guardrail_results,
            pipeline_id=run.pipeline_id,
            error=str(exc),
        )
