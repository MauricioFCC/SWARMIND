"""AIFactory — Orquestador del AI Factory Stack 7-capas.

Integra y orquesta las 7 capas de produccion AI:

1. INTELLIGENCE: LLM (reasoning, generation)
2. KNOWLEDGE: RAG + VectorDB (retrieval, memory)
3. EXECUTION: AI Agent (planning, tool use)
4. INTEGRATION: MCP (connections, protocols)
5. TRUST_INPUT: Guardrails Input (prompt safety)
6. TRUST_OUTPUT: Guardrails Output (response safety)
7. EVALS: Continuous evaluation (metrics, improvement)

Capa 0: ORCHESTRATOR (el propio AIFactory)

Arquitectura Pipeline:
Input -> Guardrails(Input) -> LLM -> RAG/VectorDB -> Agent -> MCP -> Guardrails(Output) -> Output
                                        ^                                    |
                                        |________Evals_______________________|

Estados:
- IDLE: Esperando input
- PROCESSING: Ejecutando pipeline
- GUARDRAIL_BLOCKED: Input bloqueado por guardrails
- LLM_CALL: Consultando LLM
- RAG_RETRIEVAL: Buscando en knowledge base
- AGENT_EXECUTION: Ejecutando agente
- MCP_CALL: Llamando herramientas externas
- COMPLETED: Pipeline exitoso
- FAILED: Pipeline fallido
- COMPENSATED: Pipeline con fallos compensados

Uso:
    factory = AIFactory()
    result = factory.process("Crea una API REST en Python")
    print(f"Estado: {result.status}")
    print(f"Output: {result.output}")
    print(f"Evals: {result.eval_report.pass_rate}")
"""

from __future__ import annotations

import enum
import logging
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, AsyncGenerator, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


# ===========================================================================
# Enums
# ===========================================================================


class FactoryStatus(enum.Enum):
    """Estados del ciclo de vida del pipeline AIFactory.

    Cada estado representa una etapa en el procesamiento del pipeline
    de 7 capas. La transicion natural es:
    IDLE -> PROCESSING -> [capas individuales] -> COMPLETED | FAILED | COMPENSATED
    """

    IDLE = "idle"
    PROCESSING = "processing"
    GUARDRAIL_BLOCKED = "guardrail_blocked"
    LLM_CALL = "llm_call"
    RAG_RETRIEVAL = "rag_retrieval"
    AGENT_EXECUTION = "agent_execution"
    MCP_CALL = "mcp_call"
    COMPLETED = "completed"
    FAILED = "failed"
    COMPENSATED = "compensated"


class LayerType(enum.Enum):
    """Tipos de capa en el stack AI Factory.

    Cada LayerType corresponde a una de las 7 capas funcionales
    del pipeline de produccion AI, mas la capa 0 de orquestacion.
    """

    ORCHESTRATOR = "orchestrator"
    GUARDRAIL_INPUT = "guardrail_input"
    INTELLIGENCE = "intelligence"
    KNOWLEDGE = "knowledge"
    EXECUTION = "execution"
    INTEGRATION = "integration"
    GUARDRAIL_OUTPUT = "guardrail_output"
    EVALS = "evals"


# ===========================================================================
# Dataclasses
# ===========================================================================


@dataclass(frozen=True)
class FactoryConfig:
    """Configuracion inmutable del AIFactory.

    Define los parametros globales de operacion del orquestador,
    incluyendo defaults de LLM, habilitacion de guardrails/evals,
    y politicas de reintento.

    Args:
        default_llm: Proveedor LLM por defecto (ej: 'openai/gpt-4o').
        default_model: Modelo por defecto (ej: 'gpt-4o-mini').
        guardrails_enabled: Si True, ejecuta capas de guardrails input/output.
        evals_enabled: Si True, ejecuta evaluacion continua al final del pipeline.
        max_retries: Numero maximo de reintentos por capa fallida.
        compensation_enabled: Si True, activa modo compensacion en fallos parciales.
        timeout_ms: Timeout global del pipeline en milisegundos.
        verbose_trace: Si True, incluye input/output completos en LayerTrace.
    """

    default_llm: str = "openai/gpt-4o"
    default_model: str = "gpt-4o-mini"
    guardrails_enabled: bool = True
    evals_enabled: bool = True
    max_retries: int = 3
    compensation_enabled: bool = True
    timeout_ms: int = 60000
    verbose_trace: bool = False


@dataclass(frozen=True)
class LayerTrace:
    """Traza de ejecucion de una capa individual del pipeline.

    Captura el resultado, latencia, y datos de entrada/salida de
    cada capa para propósitos de monitoreo, debugging y evaluacion.

    Args:
        layer_name: Nombre legible de la capa.
        layer_type: Tipo de capa del enum LayerType.
        status: Estado de la capa ('ok', 'error', 'blocked', 'skipped').
        latency_ms: Tiempo de ejecucion en milisegundos.
        input: Texto de entrada a la capa (solo si verbose_trace=True).
        output: Texto de salida de la capa (solo si verbose_trace=True).
        error: Mensaje de error si la capa fallo.
        retries: Numero de reintentos realizados.
    """

    layer_name: str
    layer_type: LayerType
    status: str = "ok"
    latency_ms: float = 0.0
    input: Optional[str] = None
    output: Optional[str] = None
    error: Optional[str] = None
    retries: int = 0


@dataclass(frozen=True)
class EvalReport:
    """Reporte de evaluacion continua del pipeline.

    Provee metricas de calidad sobre el resultado del pipeline,
    incluyendo tasa de aprobacion, puntuaciones por dimension,
    y recomendaciones de mejora.

    Args:
        pass_rate: Proporcion de checks aprobados (0.0 a 1.0).
        dimensions: Diccionario con puntuaciones por dimension de evaluacion.
        recommendations: Lista de recomendaciones de mejora.
        total_checks: Numero total de checks ejecutados.
        passed_checks: Numero de checks aprobados.
    """

    pass_rate: float = 0.0
    dimensions: Dict[str, float] = field(default_factory=dict)
    recommendations: List[str] = field(default_factory=list)
    total_checks: int = 0
    passed_checks: int = 0


@dataclass(frozen=True)
class FactoryResult:
    """Resultado completo del pipeline AIFactory.

    Contiene el output final, el estado de ejecucion, las trazas
    de cada capa, latencia total, reporte de evaluacion y resultados
    de guardrails.

    Args:
        input: Texto de entrada original.
        output: Texto de salida del pipeline.
        status: Estado final del pipeline (FactoryStatus).
        layers: Lista ordenada de LayerTrace por capa ejecutada.
        latency_ms: Latencia total del pipeline en milisegundos.
        eval_report: Reporte de evaluacion (EvalReport).
        guardrail_results: Lista de resultados de guardrails (aprobado/rechazado).
        pipeline_id: Identificador unico del pipeline execution.
        error: Mensaje de error global si el pipeline fallo.
    """

    input: str
    output: Optional[str] = None
    status: FactoryStatus = FactoryStatus.IDLE
    layers: List[LayerTrace] = field(default_factory=list)
    latency_ms: float = 0.0
    eval_report: EvalReport = field(default_factory=EvalReport)
    guardrail_results: List[Dict[str, Any]] = field(default_factory=list)
    pipeline_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    error: Optional[str] = None


# ===========================================================================
# Simuladores de capas (stubs para integracion real)
# ===========================================================================


def _simulate_guardrail(text: str, role: str) -> Tuple[bool, Optional[str]]:
    """Simula la evaluacion de un guardrail de seguridad.

    En produccion, esto se conectaria a un servicio de guardrails
    (ej: Guardrails AI, NVIDIA NeMo, LLM Guard) que verifica:
    - Injection de prompts
    - Contenido prohibido (PII, hate speech, violencia)
    - Desviacion de tema (topic drift)
    - Alucinaciones factuales (solo en output guardrails)

    Args:
        text: Texto a evaluar (prompt o respuesta).
        role: Rol del guardrail ('input' o 'output').

    Returns:
        Tupla de (aprobado: bool, razon: Optional[str]).
        Si aprobado=True, el texto pasa el guardrail.
        Si aprobado=False, razon contiene el motivo de bloqueo.
    """
    # Palabras/gatillos que activan el bloqueo en modo simulacion
    _TRIGGERS: Dict[str, List[str]] = {
        "input": [
            "ignora instrucciones",
            "olvida tu prompt",
            "system override",
            "dame acceso root",
            "DROP TABLE",
            "rm -rf /",
        ],
        "output": [
            "token de acceso",
            "sk-",
            "api_key=",
            "password123",
            "secret_codigo",
        ],
    }

    triggers = _TRIGGERS.get(role, [])
    text_lower = text.lower()
    for trigger in triggers:
        if trigger in text_lower:
            motivo = (
                f"Guardrail {role} bloqueado por gatillo: '{trigger}'"
            )
            logger.warning(
                "[AIFactory] %s | text_preview=%s trigger=%s",
                motivo,
                text[:80],
                trigger,
            )
            return False, motivo

    return True, None


def _simulate_llm_call(prompt: str, model: str) -> Tuple[str, float]:
    """Simula una llamada a un LLM (OpenAI, Anthropic, local, etc.).

    En produccion, esto se conectaria al API del LLM configurado
    gestionando: rate limiting, retry con backoff, timeout, y
    cache semantico de respuestas.

    Args:
        prompt: Prompt de entrada para el LLM.
        model: Identificador del modelo (ej: 'gpt-4o-mini').

    Returns:
        Tupla de (respuesta: str, latencia_ms: float).
    """
    _start = time.perf_counter()
    # Simula procesamiento LLM con latencia variable
    time.sleep(0.05)
    respuesta = (
        f"[LLM:{model}] Respuesta simulada para:\n"
        f"{prompt[:200]}{'...' if len(prompt) > 200 else ''}\n\n"
        f"---\n"
        f"Output generado por {model}. "
        f"En produccion este texto seria la respuesta real del LLM."
    )
    latency = (time.perf_counter() - _start) * 1000
    logger.debug(
        "[AIFactory] LLM call | model=%s latency_ms=%.1f input_len=%d",
        model,
        latency,
        len(prompt),
    )
    return respuesta, latency


def _simulate_rag_retrieval(query: str, top_k: int = 3) -> Tuple[List[Dict[str, Any]], float]:
    """Simula una busqueda en base de conocimiento vectorial (RAG).

    En produccion, esto consultaria LanceDB, Pinecone, Weaviate, etc.
    usando el embedding del query para busqueda por similitud coseno,
    con filtros de metadata y reranking.

    Args:
        query: Texto de consulta para retrieval.
        top_k: Numero maximo de documentos a recuperar.

    Returns:
        Tupla de (documentos: List[Dict], latencia_ms: float).
        Cada documento tiene 'id', 'content', 'score', 'source'.
    """
    _start = time.perf_counter()
    time.sleep(0.03)

    docs = [
        {
            "id": f"doc_{i}",
            "content": (
                f"Documento simulado #{i} relevante a: '{query[:60]}'. "
                f"Contiene informacion contextual para la tarea solicitada."
            ),
            "score": round(0.95 - (i * 0.05), 2),
            "source": "simulated_knowledge_base",
        }
        for i in range(top_k)
    ]

    latency = (time.perf_counter() - _start) * 1000
    logger.debug(
        "[AIFactory] RAG retrieval | query=%s top_k=%d latency_ms=%.1f",
        query[:60],
        top_k,
        latency,
    )
    return docs, latency


def _simulate_agent_execution(task: str, context: Dict[str, Any]) -> Tuple[str, float]:
    """Simula la ejecucion de un agente AI con planificacion y herramientas.

    En produccion, el agente ejecutaria un ciclo de razonamiento-accion
    (ReAct, Plan-and-Solve, Tree-of-Thought) usando herramientas
    registradas en el sistema de tools del harness.

    Args:
        task: Descripcion de la tarea a ejecutar.
        context: Contexto enriquecido (docs RAG, historial, etc.).

    Returns:
        Tupla de (resultado: str, latencia_ms: float).
    """
    _start = time.perf_counter()
    time.sleep(0.08)

    plan = (
        "1. Analizar requerimientos\n"
        "2. Disenar arquitectura\n"
        "3. Implementar solucion\n"
        "4. Verificar resultado"
    )

    resultado = (
        f"[AGENT] Plan de ejecucion:\n{plan}\n\n"
        f"Tarea: {task[:150]}\n"
        f"Contexto disponible: {len(context.get('docs', []))} documentos, "
        f"herramientas: {context.get('tools', 'ninguna')}\n\n"
        f"---\n"
        f"Resultado simulado de ejecucion del agente."
    )

    latency = (time.perf_counter() - _start) * 1000
    logger.debug(
        "[AIFactory] Agent execution | task=%s latency_ms=%.1f",
        task[:60],
        latency,
    )
    return resultado, latency


def _simulate_mcp_call(tool_name: str, params: Dict[str, Any]) -> Tuple[Dict[str, Any], float]:
    """Simula una llamada a una herramienta externa via MCP.

    En produccion, esto se conectaria al MCP Manager del harness
    (tools_sandbox/mcp_manager.py) que gestiona conexiones a
    APIs externas, ejecucion de codigo, acceso a bases de datos, etc.

    Args:
        tool_name: Nombre de la herramienta MCP a invocar.
        params: Parametros de la llamada.

    Returns:
        Tupla de (respuesta: Dict, latencia_ms: float).
    """
    _start = time.perf_counter()
    time.sleep(0.04)

    respuesta = {
        "tool": tool_name,
        "status": "ok",
        "result": f"Ejecucion simulada de '{tool_name}' con params={params}",
        "params_received": params,
    }

    latency = (time.perf_counter() - _start) * 1000
    logger.debug(
        "[AIFactory] MCP call | tool=%s latency_ms=%.1f",
        tool_name,
        latency,
    )
    return respuesta, latency


def _simulate_evals(
    input_text: str, output_text: str, layers: List[LayerTrace]
) -> EvalReport:
    """Simula la evaluacion continua del pipeline.

    En produccion, esto ejecutaria un conjunto de evaluadores:
    - Relevance: Coherencia input-output
    - Factuality: Consistencia factual contra knowledge base
    - Safety: Ausencia de contenido dañino
    - Helpfulness: Utilidad de la respuesta
    - Cost: Eficiencia de tokens usados

    Args:
        input_text: Texto de entrada original.
        output_text: Texto de salida generado.
        layers: Lista de trazas de capas ejecutadas.

    Returns:
        EvalReport con metricas de calidad.
    """
    # Simula 5 checks de evaluacion
    dimensions = {
        "relevance": 0.95,
        "factuality": 0.88,
        "safety": 1.0,
        "helpfulness": 0.92,
        "coherence": 0.90,
    }
    total = len(dimensions)
    passed = sum(1 for v in dimensions.values() if v >= 0.7)
    pass_rate = passed / total if total > 0 else 0.0

    recommendations = []
    if dimensions.get("factuality", 1.0) < 0.9:
        recommendations.append(
            "Mejorar verificacion factual: habilitar grounding check "
            "contra knowledge base."
        )
    if dimensions.get("coherence", 1.0) < 0.85:
        recommendations.append(
            "Revisar coherencia del output: considerar aumento de "
            "temperatura del LLM o refinamiento del prompt."
        )

    latency_total = sum(l.latency_ms for l in layers)

    logger.info(
        "[AIFactory] Evals | pass_rate=%.2f passed=%d/%d "
        "total_latency_ms=%.1f recommendations=%d",
        pass_rate,
        passed,
        total,
        latency_total,
        len(recommendations),
    )

    return EvalReport(
        pass_rate=round(pass_rate, 2),
        dimensions=dimensions,
        recommendations=recommendations,
        total_checks=total,
        passed_checks=passed,
    )


# ===========================================================================
# AIFactory — Orquestador Principal
# ===========================================================================


class AIFactory:
    """Orquestador del pipeline AI Factory de 7 capas.

    Coordina la ejecucion secuencial de las capas de inteligencia,
    conocimiento, ejecucion, integracion, confianza y evaluacion.
    Implementa el patron Pipeline con trazabilidad completa,
    compensacion de fallos y metricas en tiempo real.

    La arquitectura sigue el principio de Separacion de Concerns:
    cada capa es independiente y se comunica via el contexto del
    pipeline, permitiendo reemplazo individual sin afectar las demas.

    Attributes:
        config: Configuracion activa del factory.
        status: Estado actual del pipeline.
    """

    def __init__(self, config: Optional[FactoryConfig] = None) -> None:
        """Inicializa el AIFactory con configuracion opcional.

        Si no se provee config, se usa FactoryConfig con valores
        por defecto: guardrails y evals habilitados, max_retries=3.

        Args:
            config: Configuracion del factory. Si es None, usa defaults.
        """
        self._config: FactoryConfig = config or FactoryConfig()
        self._status: FactoryStatus = FactoryStatus.IDLE
        self._metrics: Dict[str, Any] = {
            "total_pipelines": 0,
            "completed": 0,
            "failed": 0,
            "blocked": 0,
            "compensated": 0,
            "total_latency_ms": 0.0,
            "layer_metrics": {},
        }
        self._lock: threading.Lock = threading.Lock()
        self._is_locked: bool = False
        logger.info(
            "[AIFactory] Inicializado | config=guardrails:%s evals:%s "
            "max_retries:%d",
            self._config.guardrails_enabled,
            self._config.evals_enabled,
            self._config.max_retries,
        )

    # ------------------------------------------------------------------
    # Propiedades publicas
    # ------------------------------------------------------------------

    @property
    def config(self) -> FactoryConfig:
        """Configuracion activa del factory (inmutable).

        Returns:
            FactoryConfig con la configuracion actual.
        """
        return self._config

    @property
    def status(self) -> FactoryStatus:
        """Estado actual del pipeline.

        Returns:
            FactoryStatus indicando la etapa actual de ejecucion.
        """
        return self._status

    # ------------------------------------------------------------------
    # Pipeline principal
    # ------------------------------------------------------------------

    def process(
        self,
        input_text: str,
        config: Optional[FactoryConfig] = None,
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

        layers: List[LayerTrace] = []
        guardrail_results: List[Dict[str, Any]] = []
        current_input: str = input_text
        current_output: Optional[str] = None
        pipeline_error: Optional[str] = None
        final_status: FactoryStatus = FactoryStatus.COMPLETED
        context: Dict[str, Any] = {"docs": [], "tools": []}

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

            if llm_trace.status == "error":
                # Intento de compensacion: reintento con modelo alternativo
                if active_config.compensation_enabled:
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

    # ------------------------------------------------------------------
    # Streaming del pipeline (AsyncGenerator)
    # ------------------------------------------------------------------

    async def process_stream(
        self, input_text: str, config: Optional[FactoryConfig] = None
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
                "[AIFactory] Error en streaming | id=%s error=%s",
                pipeline_id,
                exc,
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

    # ------------------------------------------------------------------
    # Metodos de gestion de estado
    # ------------------------------------------------------------------

    def get_status(self) -> FactoryStatus:
        """Retorna el estado actual del pipeline.

        Util para monitoreo externo, health checks y dashboards.

        Returns:
            FactoryStatus actual del orquestador.
        """
        return self._status

    def get_metrics(self) -> Dict[str, Any]:
        """Retorna las metricas acumuladas de todas las ejecuciones.

        Incluye conteo de pipelines completados, fallidos, bloqueados,
        compensados, latencia total y metricas desglosadas por capa.

        Returns:
            Diccionario con metricas del factory.
        """
        return dict(self._metrics)

    def reset(self) -> None:
        """Reinicia el estado del factory a valores iniciales.

        Resetea el estado a IDLE, libera el lock y limpia las metricas
        acumuladas. Util para comenzar un nuevo ciclo de ejecuciones
        sin crear una nueva instancia.

        No afecta la configuracion activa (self._config).
        """
        self._status = FactoryStatus.IDLE
        self._lock = False
        self._metrics = {
            "total_pipelines": 0,
            "completed": 0,
            "failed": 0,
            "blocked": 0,
            "compensated": 0,
            "total_latency_ms": 0.0,
            "layer_metrics": {},
        }
        logger.info("[AIFactory] Estado reseteado a IDLE.")

    # ------------------------------------------------------------------
    # Metodos privados de ejecucion por capa
    # ------------------------------------------------------------------

    def _execute_guardrail_input(
        self, text: str
    ) -> Tuple[LayerTrace, bool]:
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
    ) -> Tuple[LayerTrace, bool]:
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
        except Exception as exc:
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
        except Exception as exc:
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
        self, task: str, context: Dict[str, Any]
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
        except Exception as exc:
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
        self, context: str, params: Dict[str, Any]
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
        except Exception as exc:
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
        self, input_text: str, output_text: str, layers: List[LayerTrace]
    ) -> Tuple[LayerTrace, EvalReport]:
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
        except Exception as exc:
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

    # ------------------------------------------------------------------
    # Metodos auxiliares
    # ------------------------------------------------------------------

    @staticmethod
    def _build_result(
        input_text: str,
        output: Optional[str],
        status: FactoryStatus,
        layers: List[LayerTrace],
        pipeline_start: float,
        eval_report: EvalReport = EvalReport(),
        guardrail_results: Optional[List[Dict[str, Any]]] = None,
        pipeline_id: str = "",
        error: Optional[str] = None,
    ) -> FactoryResult:
        """Construye un FactoryResult con los parametros dados.

        Args:
            input_text: Texto de entrada.
            output: Texto de salida (puede ser None si fallo).
            status: Estado final del pipeline.
            layers: Lista de trazas de capas.
            pipeline_start: Timestamp de inicio del pipeline.
            eval_report: Reporte de evaluacion.
            guardrail_results: Resultados de guardrails.
            pipeline_id: Identificador del pipeline.
            error: Mensaje de error global.

        Returns:
            FactoryResult completo y congelado.
        """
        total_latency = (time.perf_counter() - pipeline_start) * 1000
        return FactoryResult(
            input=input_text,
            output=output,
            status=status,
            layers=layers,
            latency_ms=round(total_latency, 2),
            eval_report=eval_report,
            guardrail_results=guardrail_results or [],
            pipeline_id=pipeline_id,
            error=error,
        )


__all__ = [
    "AIFactory",
    "FactoryConfig",
    "FactoryResult",
    "LayerTrace",
    "FactoryStatus",
    "LayerType",
    "EvalReport",
]
