"""
Sandbox Loop Autonomo — Quality Gate - Sandbox Loop

Orquesta el bucle autonomo de calidad para codigo generado por agentes:

1. El @software-engineer genera codigo
2. El SandboxLoop ejecuta ``pytest`` (o el comando configurado) via MCPExecutor
3. Si los tests PASAN:
   - Se notifica a @quality-gate para revision final de seguridad
4. Si los tests FALLAN:
   - Se envia mensaje de error a @software-engineer
   - Se cuenta la iteracion en el AgentBus
   - Si el circuit breaker se dispara (max_iterations alcanzado):
     - Se escala a humano (canal #escalations)
     - Se registra una leccion en asi_cognition_store

Ejemplo de uso::

    loop = SandboxLoop()
    exito, resultado = loop.run_autonomous(
        task_id="abc123",
        code="def test_foo(): assert 1 + 1 == 2",
        test_command="pytest",
        max_iterations=5,
    )
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Tuple

from harness.orchestrator.agent_bus import AgentBus
from harness.tools_sandbox.mcp_executor import MCPExecutor, SandboxResult
from harness.evolve_loop.cognition_sync import CognitionSync
from harness.memory_rag.lance_vector_store import LanceVectorStore

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constantes
# ---------------------------------------------------------------------------

_DEFAULT_CHANNEL = "#swe-sandbox"
_DEFAULT_MAX_ITERATIONS = 5
_DEFAULT_TEST_COMMAND = "pytest"


# ---------------------------------------------------------------------------
# SandboxLoop
# ---------------------------------------------------------------------------


class SandboxLoop:
    """Bucle autonomo de calidad para codigo generado por agentes.

    Orquesta el ciclo: test -> exito|fallo -> notificacion -> iteracion -> escalacion.
    Integra AgentBus para mensajeria, MCPExecutor para ejecucion de tests,
    Circuit Breaker para control de iteraciones y CognitionSync para registrar
    lecciones aprendidas.
    """

    def __init__(
        self,
        vector_store: Optional[LanceVectorStore] = None,
        agent_bus: Optional[AgentBus] = None,
        executor: Optional[MCPExecutor] = None,
        cognition: Optional[CognitionSync] = None,
    ) -> None:
        """
        Args:
            vector_store: Instancia de LanceVectorStore. Por defecto crea una nueva.
            agent_bus: Instancia de AgentBus. Por defecto crea una nueva.
            executor: Instancia de MCPExecutor. Por defecto crea una nueva.
            cognition: Instancia de CognitionSync. Por defecto crea una nueva.
        """
        self.store = vector_store or LanceVectorStore()
        self.bus = agent_bus or AgentBus(vector_store=self.store)
        self.executor = executor or MCPExecutor()
        self.cognition = cognition or CognitionSync(vector_store=self.store)

    # ------------------------------------------------------------------
    # API publica
    # ------------------------------------------------------------------

    def execute_cycle(
        self,
        task_description: str,
        code: str,
        test_command: str = _DEFAULT_TEST_COMMAND,
        task_id: Optional[str] = None,
        channel: str = _DEFAULT_CHANNEL,
    ) -> Tuple[bool, SandboxResult]:
        """Ejecuta un ciclo completo del sandbox.

        1. Ejecuta el comando de test via MCPExecutor.
        2. Si los tests pasan:
           - Envia notificacion a @quality-gate para revision final.
           - Retorna ``(True, resultado)``.
        3. Si los tests fallan:
           - Envia mensaje de error a @software-engineer.
           - Verifica el circuit breaker.
           - Retorna ``(False, resultado)``.

        Args:
            task_description: Descripcion de la tarea en lenguaje natural.
            code: Codigo fuente a testear (string o ruta de archivo).
            test_command: Comando de test a ejecutar (``"pytest"``, ``"python"``, etc.).
            task_id: ID de la tarea en TaskManager (opcional).
            channel: Canal de comunicacion (defecto: ``#swe-sandbox``).

        Returns:
            Tupla ``(exito: bool, resultado: SandboxResult)``.
        """
        logger.info(
            "SandboxCycle iniciado para task=%s command=%s",
            task_id or "sin-task", test_command,
        )

        # Ejecutar test via MCPExecutor
        try:
            result = self.executor.run_test(code, test_type=test_command)
        except Exception as exc:
            logger.exception("Error en MCPExecutor.run_test")
            result = SandboxResult(
                success=False,
                output="",
                error=f"Error en el sandbox executor: {exc}",
                execution_time=0.0,
            )

        if result.success:
            # ----------------------------------------------------------
            # TESTS PASAN -> Notificar a @quality-gate
            # ----------------------------------------------------------
            self._notify_quality_gate(
                channel=channel,
                task_description=task_description,
                task_id=task_id,
                code=code,
                output=result.output,
                execution_time=result.execution_time,
            )
            logger.info(
                "SandboxCycle EXITO task=%s (%.2fs)",
                task_id or "?", result.execution_time,
            )
            return True, result

        # ----------------------------------------------------------
        # TESTS FALLAN -> Notificar a @software-engineer + circuit breaker
        # ----------------------------------------------------------
        iteration = self.bus.count_iterations(task_id) + 1 if task_id else 1

        self._notify_software_engineer(
            channel=channel,
            task_description=task_description,
            task_id=task_id,
            code=code,
            iteration=iteration,
            error=result.error,
            execution_time=result.execution_time,
        )

        # Verificar circuit breaker si tenemos task_id
        if task_id and self.bus.check_circuit_breaker(
            task_id, max_iterations=_DEFAULT_MAX_ITERATIONS,
        ):
            self._handle_escalation(
                task_id=task_id,
                task_description=task_description,
                code=code,
                iteration=iteration,
                last_error=result.error,
                channel=channel,
            )
            logger.warning(
                "SandboxCycle CIRCUIT BREAKER task=%s iter=%d",
                task_id, iteration,
            )
        else:
            logger.info(
                "SandboxCycle FALLO task=%s iter=%d (%.2fs)",
                task_id or "?", iteration, result.execution_time,
            )

        return False, result

    def run_autonomous(
        self,
        task_id: str,
        code: str = "",
        test_command: str = _DEFAULT_TEST_COMMAND,
        max_iterations: int = _DEFAULT_MAX_ITERATIONS,
        channel: str = _DEFAULT_CHANNEL,
    ) -> Tuple[bool, Optional[SandboxResult]]:
        """Bucle autonomo completo: ejecuta ciclos hasta exito o escalacion.

        Itera hasta ``max_iterations`` veces ejecutando tests, notificando
        resultados y verificando el circuit breaker en cada fallo.

        Args:
            task_id: ID de la tarea en TaskManager.
            code: Codigo fuente a testear.
            test_command: Comando de test (``"pytest"``, ``"python"``, etc.).
            max_iterations: Maximo de iteraciones antes de escalar (defecto: 5).
            channel: Canal de comunicacion (defecto: ``#swe-sandbox``).

        Returns:
            Tupla ``(exito: bool, resultado: SandboxResult | None)``.

            - ``(True, resultado)`` si los tests pasaron.
            - ``(False, resultado_del_ultimo_fallo)`` si se agoto o escalo.
        """
        logger.info(
            "SandboxLoop.run_autonomous task=%s max_iter=%d channel=%s",
            task_id, max_iterations, channel,
        )

        if not code:
            logger.warning(
                "SandboxLoop: codigo vacio para task=%s. "
                "Notificando al canal y saliendo.", task_id,
            )
            self.bus.post_message(
                channel=channel,
                from_agent="@sandbox",
                to_agent="@software-engineer",
                message=(
                    f"[SandboxLoop] Tarea {task_id} iniciada sin codigo.\n"
                    f"Esperando que @software-engineer genere el codigo para testear."
                ),
                message_type="notification",
                task_id=task_id,
                iteration=0,
            )
            return False, None

        last_result: Optional[SandboxResult] = None

        for iteration in range(1, max_iterations + 1):
            logger.info(
                "SandboxLoop iteracion %d/%d para task=%s",
                iteration, max_iterations, task_id,
            )

            exito, last_result = self.execute_cycle(
                task_description=f"Task {task_id} (iter {iteration})",
                code=code,
                test_command=test_command,
                task_id=task_id,
                channel=channel,
            )

            if exito:
                logger.info(
                    "SandboxLoop COMPLETADO con exito task=%s tras %d iteraciones",
                    task_id, iteration,
                )
                return True, last_result

            # Si el circuit breaker se disparo, execute_cycle ya escalo
            if self.bus.check_circuit_breaker(task_id, max_iterations):
                logger.warning(
                    "SandboxLoop CIRCUIT BREAKER task=%s en iteracion %d",
                    task_id, iteration,
                )
                return False, last_result

        # Si llegamos aqui, max_iterations alcanzado sin exito
        logger.warning(
            "SandboxLoop AGOTADO task=%s tras %d iteraciones sin exito",
            task_id, max_iterations,
        )

        # Escalacion final
        self._handle_escalation(
            task_id=task_id,
            task_description=f"Task {task_id}",
            code=code,
            iteration=max_iterations,
            last_error=last_result.error if last_result else "Desconocido",
            channel=channel,
        )

        return False, last_result

    # ------------------------------------------------------------------
    # Metodos internos: notificaciones
    # ------------------------------------------------------------------

    def _notify_quality_gate(
        self,
        channel: str,
        task_description: str,
        task_id: Optional[str],
        code: str,
        output: str,
        execution_time: float,
    ) -> str:
        """Notifica a @quality-gate que los tests pasaron."""
        msg = (
            f"✅ Tests SUPERADOS para: {task_description}\n\n"
            f"```\n{output[:1500]}\n```\n\n"
            f"Tiempo de ejecucion: {execution_time:.2f}s\n"
            f"Se requiere revision final de @quality-gate."
        )
        attachments = [code] if code else None
        return self.bus.post_message(
            channel=channel,
            from_agent="@sandbox",
            to_agent="@quality-gate",
            message=msg,
            message_type="response",
            task_id=task_id,
            attachments=attachments,
        )

    def _notify_software_engineer(
        self,
        channel: str,
        task_description: str,
        task_id: Optional[str],
        code: str,
        iteration: int,
        error: str,
        execution_time: float,
    ) -> str:
        """Notifica a @software-engineer que los tests fallaron."""
        msg = (
            f"❌ Tests FALLIDOS (intento {iteration}) para: {task_description}\n\n"
            f"```\n{error[:1500]}\n```\n\n"
            f"Tiempo de ejecucion: {execution_time:.2f}s\n"
            f"@software-engineer debe corregir el codigo."
        )
        attachments = [code] if code else None
        return self.bus.post_message(
            channel=channel,
            from_agent="@sandbox",
            to_agent="@software-engineer",
            message=msg,
            message_type="error",
            task_id=task_id,
            iteration=iteration,
            attachments=attachments,
        )

    def _handle_escalation(
        self,
        task_id: str,
        task_description: str,
        code: str,
        iteration: int,
        last_error: str,
        channel: str,
    ) -> None:
        """Maneja la escalacion cuando el circuit breaker se dispara.

        1. Envia mensaje de escalacion al canal humano.
        2. Registra leccion en asi_cognition_store.
        """
        # 1. Escalar a humano
        escalation_msg = (
            f"🚨 CIRCUIT BREAKER DISPARADO para tarea: {task_id}\n\n"
            f"Descripcion: {task_description}\n"
            f"Intentos fallidos: {iteration}\n"
            f"Ultimo error: {last_error[:500]}\n\n"
            f"Se requiere intervencion humana urgente."
        )
        self.bus.post_message(
            channel=channel,
            from_agent="@sandbox",
            to_agent="@human",
            message=escalation_msg,
            message_type="escalation",
            task_id=task_id,
            iteration=iteration,
        )

        # 2. Registrar leccion en cognition store
        try:
            self.cognition.add_lesson(
                title=f"Circuit Breaker - Task {task_id}",
                content=(
                    f"El circuit breaker se disparo para la tarea {task_id} "
                    f"tras {iteration} intentos fallidos.\n\n"
                    f"Descripcion: {task_description}\n"
                    f"Ultimo error: {last_error[:500]}\n\n"
                    f"Se requiere intervencion humana."
                ),
                domain="harness.sandbox",
                tags=["circuit-breaker", "escalation", task_id],
                metrics={
                    "task_id": task_id,
                    "iterations": iteration,
                    "max_iterations": _DEFAULT_MAX_ITERATIONS,
                },
            )
            logger.info(
                "Leccion de escalacion registrada en cognition para task=%s",
                task_id,
            )
        except Exception as exc:
            logger.warning(
                "No se pudo registrar leccion de escalacion: %s", exc,
            )

    # ------------------------------------------------------------------
    # Metodos de utilidad
    # ------------------------------------------------------------------

    def get_status(self, task_id: str) -> Dict[str, Any]:
        """Retorna el estado actual del sandbox para una tarea.

        Args:
            task_id: ID de la tarea.

        Returns:
            Dict con: error_count, circuit_breaker_open, ultimo_mensaje.
        """
        error_count = self.bus.count_iterations(task_id)
        circuit_open = self.bus.check_circuit_breaker(task_id)

        # Obtener ultimo mensaje relacionado
        ultimo = None
        try:
            dummy = __import__("numpy").zeros(384, dtype=__import__("numpy").float32)
            results = self.bus.store.search(
                "agent_workspace_logs", dummy, top_k=1,
                filters={"task_id": task_id},
            )
            if results:
                ultimo = self.bus._deserialize_message(results[0])
                ultimo.pop("vector", None)
        except Exception:
            pass

        return {
            "task_id": task_id,
            "error_count": error_count,
            "circuit_breaker_open": circuit_open,
            "max_iterations": _DEFAULT_MAX_ITERATIONS,
            "ultimo_mensaje": ultimo,
        }
