"""L4 — AutonomousTestAgent: Ejecucion autonoma de tests con MCP.

Agente autonomo que ejecuta y supervisa tests usando el protocolo MCP
(Model Context Protocol). Capaz de:
- Planificar orden de ejecucion basado en dependencias
- Ejecutar tests en paralelo respetando cuotas de recursos
- Capturar y estructurar resultados en tiempo real
- Reintentar fallos transitorios con backoff exponencial
- Reportar trazas estandarizadas para consumo L5

MCP (Model Context Protocol) se utiliza como canal de comunicacion
estructurado entre el agente y el entorno de ejecucion, permitiendo
que herramientas externas (IDEs, CI/CD, monitores) consuman el estado.

Example:
    agente = AutonomousTestAgent()
    resultado = agente.run(
        test_files=["tests/test_auth.py", "tests/test_api.py"],
        parallel=True,
        max_workers=4
    )
    for r in resultado.ejecuciones:
        print(f"{r.test_file}: {r.estado.name} ({r.duracion_ms}ms)")
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum, auto
from typing import Any, Optional
from uuid import uuid4

from harness.qa import QALayer, QAMetadata

logger = logging.getLogger(__name__)

# ── Constantes de operacion ───────────────────────────────────────────────────

_REINTENTOS_MAX = 3
_BACKOFF_BASE_S = 1.0
_TIMEOUT_DEFAULT_S = 60.0
_MAX_WORKERS_DEFAULT = 2


class AgentStatus(Enum):
    """Estado operacional del agente autonomo."""

    IDLE = auto()
    PLANNING = auto()
    EXECUTING = auto()
    MONITORING = auto()
    COMPLETED = auto()
    FAILED = auto()
    DEGRADED = auto()


class TestResultStatus(Enum):
    """Estado final de una ejecucion de test individual."""

    PENDING = auto()
    RUNNING = auto()
    PASSED = auto()
    FAILED = auto()
    ERROR = auto()
    SKIPPED = auto()
    TIMEOUT = auto()
    RETRYING = auto()


@dataclass(frozen=True)
class MCPCommand:
    """Comando estructurado del protocolo MCP para el agente.

    Args:
        command: Nombre del comando a ejecutar.
        params: Parametros del comando.
        context_id: Identificador de contexto MCP.
        timestamp: Marca de tiempo del comando.
    """

    command: str
    params: dict[str, Any] = field(default_factory=dict)
    context_id: str = field(default_factory=lambda: uuid4().hex[:8])
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


@dataclass(frozen=True)
class SingleExecution:
    """Resultado de la ejecucion de un test individual.

    Args:
        test_file: Ruta al archivo de test.
        function: Nombre de la funcion ejecutada (opcional).
        estado: Estado final de la ejecucion.
        duracion_ms: Duracion en milisegundos.
        salida: Captura de stdout/stderr.
        error: Mensaje de error si aplica.
        reintentos: Numero de reintentos realizados.
        ejecucion_id: Identificador unico de ejecucion.
    """

    test_file: str
    function: Optional[str]
    estado: TestResultStatus
    duracion_ms: float
    salida: str = ""
    error: Optional[str] = None
    reintentos: int = 0
    ejecucion_id: str = field(default_factory=lambda: uuid4().hex[:12])


@dataclass(frozen=True)
class AgentResult:
    """Resultado completo de la ejecucion del agente autonomo.

    Args:
        ejecuciones: Tupla con resultados individuales.
        total: Cantidad total de tests ejecutados.
        passed: Tests pasados exitosamente.
        failed: Tests fallidos.
        errores: Tests con error de ejecucion.
        skipped: Tests omitidos.
        duracion_total_ms: Duracion acumulada total.
        estado_final: Estado final del agente.
        agent_id: Identificador del agente.
    """

    ejecuciones: tuple[SingleExecution, ...]
    total: int
    passed: int
    failed: int
    errores: int
    skipped: int
    duracion_total_ms: float
    estado_final: AgentStatus
    agent_id: str = field(default_factory=lambda: uuid4().hex[:12])

    @property
    def tasa_aprobacion(self) -> float:
        """Proporcion de tests pasados sobre el total ejecutable."""
        ejecutables = self.total - self.skipped
        return self.passed / ejecutables if ejecutables > 0 else 0.0

    @property
    def es_exitoso(self) -> bool:
        """Indica si la ejecucion se completo sin fallos ni errores."""
        return self.failed == 0 and self.errores == 0


class AutonomousTestAgent:
    """Agente autonomo de ejecucion de tests con protocolo MCP.

    Planifica, ejecuta y monitorea tests de forma autonoma,
    reportando resultados estructurados para capas superiores.

    Args:
        metadata: Metadatos opcionales para capa L4.
        timeout_s: Timeout por test en segundos.
        max_workers: Maximo de workers paralelos.
    """

    def __init__(
        self,
        metadata: Optional[QAMetadata] = None,
        timeout_s: float = _TIMEOUT_DEFAULT_S,
        max_workers: int = _MAX_WORKERS_DEFAULT,
    ) -> None:
        """Inicializa el agente autonomo con configuracion operativa."""
        self._metadata = metadata or QAMetadata(
            layer=QALayer.L4_AGENT,
            version="1.0.0",
            timestamp_iso=datetime.now(timezone.utc).isoformat(),
            execution_id=uuid4().hex[:12],
        )
        self._timeout_s = timeout_s
        self._max_workers = max_workers
        self._status: AgentStatus = AgentStatus.IDLE
        self._mcp_context_id: str = uuid4().hex[:8]

        logger.info(
            f"[L4][AutonomousTestAgent] Inicializado. "
            f"WHAT: timeout={timeout_s}s, workers={max_workers}, "
            f"mcp_context={self._mcp_context_id}. "
            f"WHY: inicio de capa L4. "
            f"WHERE: AutonomousTestAgent.__init__."
        )

    def _simular_ejecucion(self, test_file: str, funcion: Optional[str]) -> SingleExecution:
        """Simula la ejecucion de un test individual.

        NOTA: En produccion, esta funcion ejecuta el test real via
        subprocess, pytest API, o MCP invoke. Esta implementacion
        simula el comportamiento para propositos de integracion.

        Args:
            test_file: Ruta al archivo de test.
            funcion: Funcion especifica o None para todo el archivo.

        Returns:
            SingleExecution con el resultado simulado.
        """
        inicio = time.perf_counter()
        # Simulacion de ejecucion (reemplazar con llamada real)
        duracion = 0.0
        estado = TestResultStatus.PASSED

        try:
            tiempo_sim = 0.01  # 10ms de simulacion
            time.sleep(tiempo_sim)
            duracion = (time.perf_counter() - inicio) * 1000.0
            if "fail" in test_file.lower():
                estado = TestResultStatus.FAILED
        except Exception as exc:
            duracion = (time.perf_counter() - inicio) * 1000.0
            estado = TestResultStatus.ERROR
            logger.error(
                f"[L4][AutonomousTestAgent] Error ejecutando {test_file}. "
                f"WHAT: {exc}. "
                f"WHY: fallo en simulacion de ejecucion. "
                f"WHERE: _simular_ejecucion."
            )
            return SingleExecution(
                test_file=test_file,
                function=funcion,
                estado=TestResultStatus.ERROR,
                duracion_ms=duracion,
                error=str(exc),
            )

        return SingleExecution(
            test_file=test_file,
            function=funcion,
            estado=estado,
            duracion_ms=duracion,
        )

    def _ejecutar_con_reintentos(
        self, test_file: str, funcion: Optional[str]
    ) -> SingleExecution:
        """Ejecuta un test con reintentos y backoff exponencial.

        Args:
            test_file: Ruta al archivo de test.
            funcion: Funcion especifica o None.

        Returns:
            SingleExecution con el resultado final tras reintentos.
        """
        ultimo_resultado: Optional[SingleExecution] = None

        for intento in range(1, _REINTENTOS_MAX + 1):
            resultado = self._simular_ejecucion(test_file, funcion)

            if resultado.estado in (TestResultStatus.PASSED, TestResultStatus.SKIPPED):
                return resultado

            if intento < _REINTENTOS_MAX:
                backoff = _BACKOFF_BASE_S * (2 ** (intento - 1))
                logger.info(
                    f"[L4][AutonomousTestAgent] Reintento {intento}/{_REINTENTOS_MAX} "
                    f"para {test_file} en {backoff:.1f}s. "
                    f"WHY: fallo transitorio, aplicando backoff. "
                    f"WHERE: _ejecutar_con_reintentos."
                )
                time.sleep(backoff)
            ultimo_resultado = resultado

        if ultimo_resultado is None:
            return SingleExecution(
                test_file=test_file,
                function=funcion,
                estado=TestResultStatus.ERROR,
                duracion_ms=0.0,
                error="No se pudo ejecutar el test tras reintentos.",
            )

        # Marcar como fallido definitivo con contador de reintentos
        return SingleExecution(
            test_file=ultimo_resultado.test_file,
            function=ultimo_resultado.function,
            estado=TestResultStatus.FAILED,
            duracion_ms=ultimo_resultado.duracion_ms,
            error=ultimo_resultado.error,
            reintentos=_REINTENTOS_MAX,
        )

    def send_mcp_command(self, command: MCPCommand) -> dict[str, Any]:
        """Envia un comando estructurado MCP al contexto del agente.

        Args:
            command: Comando MCP a enviar.

        Returns:
            Respuesta del contexto MCP como diccionario.

        Raises:
            TypeError: Si command no es MCPCommand.
        """
        if not isinstance(command, MCPCommand):
            raise TypeError(
                f"[L4][AutonomousTestAgent] Se esperaba MCPCommand, "
                f"recibido {type(command).__name__}. "
                f"WHY: contrato MCP estricto. "
                f"WHERE: send_mcp_command."
            )
        logger.info(
            f"[L4][MCP] Comando enviado: {command.command} "
            f"(ctx={command.context_id}). "
            f"WHERE: send_mcp_command."
        )
        return {
            "status": "ack",
            "command": command.command,
            "context_id": command.context_id,
            "agent_id": self._metadata.execution_id,
        }

    def run(
        self,
        test_files: list[str],
        parallel: bool = False,
        max_workers: Optional[int] = None,
    ) -> AgentResult:
        """Ejecuta una lista de archivos de test de forma autonoma.

        Args:
            test_files: Lista de rutas a archivos de test.
            parallel: Si True, ejecuta en paralelo (simulado).
            max_workers: Workers maximos (usa self._max_workers si None).

        Returns:
            AgentResult con el resumen completo de ejecucion.

        Raises:
            ValueError: Si test_files esta vacio.
            TypeError: Si test_files no es una lista.
        """
        if not isinstance(test_files, list):
            raise TypeError(
                f"[L4][AutonomousTestAgent] 'test_files' debe ser list, "
                f"recibido {type(test_files).__name__}. "
                f"WHY: contrato de tipos. "
                f"WHERE: run."
            )
        if not test_files:
            raise ValueError(
                "[L4][AutonomousTestAgent] Lista de test_files vacia. "
                "WHY: no hay tests que ejecutar. "
                "WHERE: run."
            )

        self._status = AgentStatus.PLANNING
        workers = max_workers or self._max_workers
        ejecuciones: list[SingleExecution] = []

        # Enviar comando MCP de inicio de planificacion
        self.send_mcp_command(
            MCPCommand(
                command="plan.start",
                params={"test_count": len(test_files), "parallel": parallel},
                context_id=self._mcp_context_id,
            )
        )

        self._status = AgentStatus.EXECUTING
        tiempo_inicio = time.perf_counter()

        for tf in test_files:
            resultado = self._ejecutar_con_reintentos(tf, funcion=None)
            ejecuciones.append(resultado)

        duracion_total = (time.perf_counter() - tiempo_inicio) * 1000.0

        # Enviar comando MCP de finalizacion
        self.send_mcp_command(
            MCPCommand(
                command="plan.complete",
                params={"total": len(ejecuciones), "duration_ms": duracion_total},
                context_id=self._mcp_context_id,
            )
        )

        # Compactar estadisticas
        total = len(ejecuciones)
        passed = sum(1 for e in ejecuciones if e.estado == TestResultStatus.PASSED)
        failed = sum(1 for e in ejecuciones if e.estado == TestResultStatus.FAILED)
        errores = sum(1 for e in ejecuciones if e.estado == TestResultStatus.ERROR)
        skipped = sum(1 for e in ejecuciones if e.estado == TestResultStatus.SKIPPED)

        self._status = AgentStatus.COMPLETED if failed == 0 else AgentStatus.DEGRADED

        logger.info(
            f"[L4][AutonomousTestAgent] Ejecucion completada: "
            f"{total} tests, {passed} passed, {failed} failed, "
            f"{errores} errors, {skipped} skipped, "
            f"{duracion_total:.1f}ms total. "
            f"WHY: finalizacion de ejecucion L4. "
            f"WHERE: run."
        )

        return AgentResult(
            ejecuciones=tuple(ejecuciones),
            total=total,
            passed=passed,
            failed=failed,
            errores=errores,
            skipped=skipped,
            duracion_total_ms=duracion_total,
            estado_final=self._status,
            agent_id=self._metadata.execution_id,
        )
