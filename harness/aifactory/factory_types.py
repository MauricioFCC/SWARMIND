"""Factory types - Enums, dataclasses and simulation functions."""
from __future__ import annotations

import enum
import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

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


import threading



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


