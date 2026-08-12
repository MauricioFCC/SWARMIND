"""AIFactory pipeline — mixin con el pipeline principal ``process()``.

Extraccion mecanica del metodo ``process()`` de la clase ``AIFactory``
del modulo original ``harness/aifactory/factory.py`` (sin cambios de
logica ni firmas). La clase ``AIFactory`` lo hereda via mixin.
"""

from __future__ import annotations

import logging
import time
import uuid
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


class _PipelineMixin:
    """Mixin con el pipeline principal de 7 capas (sync)."""

    def process(
        self,
        input_text: str,
        config: FactoryConfig | None = None,
    ) -> FactoryResult:
        """Ejecuta el pipeline completo de 7 capas sobre el texto de entrada.

        Pipeline flow:
        1. GUARDRAIL_INPUT: Validacion de seguridad del prompt
        2. INTELLIGENCE (LLM): Generacion de respuesta inicial
        3. KNOWLEDGE (RAG): Enriquecimiento con base de conocimiento
        4. EXECUTION (Agent): Planificacion y ejecucion de tareas
        5. INTEGRATION (MCP): Llamadas a herramientas externas
        6. GUARDRAIL_OUTPUT: Validacion de seguridad de la respuesta
        7. EVALS: Evaluacion continua de calidad

        Cada capa registra una LayerTrace con latencia, estado y errores.
        Si una capa falla y compensation_enabled=True, se intenta
        compensar en lugar de abortar todo el pipeline.

        Args:
            input_text: Texto de entrada a procesar.
            config: Configuracion opcional para esta ejecucion.
                Si no se provee, usa la config del factory.

        Returns:
            FactoryResult con el output, trazas, metricas y evaluacion.

        Raises:
            ValueError: Si input_text esta vacio o es solo espacios.
            RuntimeError: Si el factory ya esta ejecutando un pipeline.
        """
        # --- Validacion pre-ejecucion ---
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

        # --- Configuracion de ejecucion ---
        active_config = config or self._config
        pipeline_id = uuid.uuid4().hex[:12]
        self._status = FactoryStatus.PROCESSING
        self._is_locked = True
        pipeline_start = time.perf_counter()

        layers: list[LayerTrace] = []
        guardrail_results: list[dict[str, Any]] = []
        current_input: str = input_text
        current_output: str | None = None
        pipeline_error: str | None = None
        final_status: FactoryStatus = FactoryStatus.COMPLETED
        context: dict[str, Any] = {"docs": [], "tools": []}

        logger.info(
            "[AIFactory] Pipeline iniciado | id=%s input_len=%d config=%s",
            pipeline_id,
            len(input_text),
            "custom" if config else "default",
        )

        try:
            # ===============================================================
            # CAPA 1: GUARDRAIL INPUT
            # ===============================================================
            if active_config.guardrails_enabled:
                self._status = FactoryStatus.GUARDRAIL_BLOCKED
                trace, blocked = self._execute_guardrail_input(current_input)
                layers.append(trace)
                guardrail_results.append({
                    "layer": "input",
                    "blocked": blocked,
                    "reason": trace.error,
                    "latency_ms": trace.latency_ms,
                })

                if blocked:
                    final_status = FactoryStatus.GUARDRAIL_BLOCKED
                    current_output = (
                        f"Input bloqueado por guardrails de seguridad.\n"
                        f"Motivo: {trace.error}"
                    )
                    logger.warning(
                        "[AIFactory] Pipeline bloqueado | id=%s reason=%s",
                        pipeline_id,
                        trace.error,
                    )
                    self._metrics["blocked"] += 1
                    # Si esta bloqueado, no continuamos con las demas capas
                    return self._build_result(
                        input_text=input_text,
                        output=current_output,
                        status=final_status,
                        layers=layers,
                        pipeline_start=pipeline_start,
                        guardrail_results=guardrail_results,
                        pipeline_id=pipeline_id,
                    )
            else:
                layers.append(LayerTrace(
                    layer_name="GuardrailInput",
                    layer_type=LayerType.GUARDRAIL_INPUT,
                    status="skipped",
                    latency_ms=0.0,
                ))

            # ===============================================================
            # CAPA 2: INTELLIGENCE (LLM)
            # ===============================================================
            self._status = FactoryStatus.LLM_CALL
            llm_trace = self._execute_llm(
                current_input, active_config.default_model
            )
            layers.append(llm_trace)

            if llm_trace.status == "error" and active_config.compensation_enabled:
                logger.info(
                    "[AIFactory] Compensando fallo LLM | "
                    "id=%s retry_model=gpt-4o-mini",
                    pipeline_id,
                )
                llm_trace = self._execute_llm(
                    current_input, "gpt-4o-mini", retry=True
                )
                layers[-1] = llm_trace

            if llm_trace.status == "error":
                final_status = FactoryStatus.FAILED
                pipeline_error = llm_trace.error
                current_output = f"Error en capa LLM: {llm_trace.error}"
            else:
                current_output = llm_trace.output

            # ===============================================================
            # CAPA 3: KNOWLEDGE (RAG + VectorDB)
            # ===============================================================
            self._status = FactoryStatus.RAG_RETRIEVAL
            rag_trace = self._execute_rag(
                current_input if current_output is None else str(current_output)
            )
            layers.append(rag_trace)

            if rag_trace.status == "ok" and rag_trace.output:
                context["docs"] = rag_trace.output
                # Enriquecer el output con conocimiento recuperado
                docs_text = "\n".join(
                    f"- [{d.get('id','?')}] (score={d.get('score','N/A')}): "
                    f"{d.get('content','')[:100]}"
                    for d in (rag_trace.output if isinstance(rag_trace.output, list) else [])
                )
                if current_output:
                    current_output += (
                        f"\n\n[Conocimiento recuperado]\n{docs_text}"
                    )
                else:
                    current_output = f"[Conocimiento recuperado]\n{docs_text}"

            # ===============================================================
            # CAPA 4: EXECUTION (AI Agent)
            # ===============================================================
            self._status = FactoryStatus.AGENT_EXECUTION
            agent_trace = self._execute_agent(
                current_input, context
            )
            layers.append(agent_trace)

            if agent_trace.status == "ok" and agent_trace.output:
                current_output = agent_trace.output

            # ===============================================================
            # CAPA 5: INTEGRATION (MCP)
            # ===============================================================
            self._status = FactoryStatus.MCP_CALL
            mcp_trace = self._execute_mcp(current_input, context)
            layers.append(mcp_trace)

            if mcp_trace.status == "ok" and mcp_trace.output:
                context["tools"] = mcp_trace.output
                if current_output:
                    current_output += (
                        f"\n\n[Herramientas MCP ejecutadas]\n"
                        f"{mcp_trace.output}"
                    )

            # ===============================================================
            # CAPA 6: GUARDRAIL OUTPUT
            # ===============================================================
            if active_config.guardrails_enabled and current_output:
                output_trace, output_blocked = self._execute_guardrail_output(
                    current_output
                )
                layers.append(output_trace)
                guardrail_results.append({
                    "layer": "output",
                    "blocked": output_blocked,
                    "reason": output_trace.error,
                    "latency_ms": output_trace.latency_ms,
                })

                if output_blocked:
                    final_status = FactoryStatus.GUARDRAIL_BLOCKED
                    logger.warning(
                        "[AIFactory] Output bloqueado por guardrails | "
                        "id=%s reason=%s",
                        pipeline_id,
                        output_trace.error,
                    )
                    self._metrics["blocked"] += 1
                    current_output = (
                        f"Output bloqueado por guardrails de seguridad.\n"
                        f"Motivo: {output_trace.error}"
                    )
            else:
                layers.append(LayerTrace(
                    layer_name="GuardrailOutput",
                    layer_type=LayerType.GUARDRAIL_OUTPUT,
                    status="skipped",
                    latency_ms=0.0,
                ))

            # ===============================================================
            # CAPA 7: EVALS (Evaluacion continua)
            # ===============================================================
            eval_report = EvalReport()
            if active_config.evals_enabled and current_output:
                eval_trace, eval_report = self._execute_evals(
                    input_text, current_output, layers
                )
                layers.append(eval_trace)
            else:
                layers.append(LayerTrace(
                    layer_name="Evals",
                    layer_type=LayerType.EVALS,
                    status="skipped",
                    latency_ms=0.0,
                ))

            # ===============================================================
            # Estado final: COMPLETED o COMPENSATED
            # ===============================================================
            if final_status == FactoryStatus.FAILED:
                # Verificar si podemos compensar
                if active_config.compensation_enabled and current_output:
                    final_status = FactoryStatus.COMPENSATED
                    self._metrics["compensated"] += 1
                    logger.info(
                        "[AIFactory] Pipeline compensado | id=%s",
                        pipeline_id,
                    )
                else:
                    self._metrics["failed"] += 1
            else:
                final_status = FactoryStatus.COMPLETED
                self._metrics["completed"] += 1

            self._status = final_status
            total_latency = (time.perf_counter() - pipeline_start) * 1000
            self._metrics["total_latency_ms"] += total_latency
            self._metrics["total_pipelines"] += 1

            logger.info(
                "[AIFactory] Pipeline finalizado | id=%s status=%s "
                "latency_ms=%.1f layers=%d",
                pipeline_id,
                final_status.value,
                total_latency,
                len(layers),
            )

            return self._build_result(
                input_text=input_text,
                output=current_output,
                status=final_status,
                layers=layers,
                pipeline_start=pipeline_start,
                eval_report=eval_report,
                guardrail_results=guardrail_results,
                pipeline_id=pipeline_id,
                error=pipeline_error,
            )

        except Exception as exc:
            # Error no manejado: registrar y retornar FAILED
            self._status = FactoryStatus.FAILED
            self._metrics["failed"] += 1
            self._metrics["total_pipelines"] += 1

            error_msg = (
                f"[AIFactory] Error no manejado en pipeline | "
                f"id={pipeline_id} error={exc}"
            )
            logger.exception(error_msg)

            total_latency = (time.perf_counter() - pipeline_start) * 1000
            return self._build_result(
                input_text=input_text,
                output=None,
                status=FactoryStatus.FAILED,
                layers=layers,
                pipeline_start=pipeline_start,
                guardrail_results=guardrail_results,
                pipeline_id=pipeline_id,
                error=str(exc),
            )

        finally:
            self._lock.release()
