"""
Resiliencia de 3 scopes — ADR-0033 (conceptos de OmniRoute).

Capas independientes de fallo sobre el routing:
  - Scope 1: CircuitBreaker por proveedor (reutiliza
    harness.orchestrator.self_healing.CircuitBreaker, lazy por provider).
  - Scope 2: ConnectionCooldown — backoff exponencial x2 por conexion con
    guard anti-thundering-herd.
  - Scope 3: ModelLockout — lockout por tripla (recurso+agente+modelo) con
    success-decay: cada exito divide el contador a la mitad; a 0 se borra.

Uso:
    governance = ResilienceGovernance()
    if governance.can_proceed(resource, agent, model):
        governance.record_success(resource, agent, model)
    else:
        governance.record_failure(resource, agent, model)
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable

from harness.orchestrator.self_healing import CircuitBreaker

# ---------------------------------------------------------------------------
# Scope 2: ConnectionCooldown
# ---------------------------------------------------------------------------


class ConnectionCooldown:
    """
    Cooldown por conexion/instancia con backoff exponencial x2.

    Cada fallo consecutivo duplica el cooldown (base, base*2, base*4, ...)
    hasta el tope max_cooldown. El guard anti-thundering-herd registra el
    timestamp de cada fallo: si la manada golpea durante el cooldown, se
    rearma la ventana de espera. Thread-safe con threading.Lock.
    """

    def __init__(
        self,
        base_cooldown: float = 5.0,
        max_cooldown: float = 300.0,
        clock: Callable[[], float] = time.time,
    ) -> None:
        """
        Args:
            base_cooldown: cooldown inicial en segundos tras el primer fallo.
            max_cooldown: tope del backoff exponencial en segundos.
            clock: funcion sin argumentos del tiempo actual (inyectable).

        Raises:
            ValueError: si base_cooldown <= 0 o max_cooldown < base_cooldown.
        """
        if base_cooldown <= 0:
            raise ValueError(
                f"base_cooldown debe ser > 0, recibido {base_cooldown} "
                "(WHY: un cooldown no positivo desactiva la proteccion; "
                "WHERE: ConnectionCooldown.__init__)"
            )
        if max_cooldown < base_cooldown:
            raise ValueError(
                f"max_cooldown ({max_cooldown}) menor que base_cooldown "
                f"({base_cooldown}) (WHY: el tope seria menor que el inicio "
                "del backoff; WHERE: ConnectionCooldown.__init__)"
            )
        self.base_cooldown: float = base_cooldown
        self.max_cooldown: float = max_cooldown
        self._clock: Callable[[], float] = clock
        self._failure_counts: dict[str, int] = {}
        self._cooldowns: dict[str, float] = {}
        self._last_failure: dict[str, float] = {}
        self._lock = threading.Lock()

    def record_failure(self, connection: str) -> None:
        """
        Registra un fallo y aplica backoff x2 con tope max_cooldown.

        Refresca el timestamp del ultimo fallo (guard anti-thundering-herd).

        Args:
            connection: identificador de la conexion o instancia.
        """
        with self._lock:
            count = self._failure_counts.get(connection, 0) + 1
            self._failure_counts[connection] = count
            self._cooldowns[connection] = min(
                self.base_cooldown * (2 ** (count - 1)), self.max_cooldown
            )
            self._last_failure[connection] = self._clock()

    def is_cooling_down(self, connection: str) -> bool:
        """
        Indica si la conexion esta en periodo de cooldown.

        Args:
            connection: identificador de la conexion o instancia.

        Returns:
            True si el tiempo transcurrido desde el ultimo fallo es menor
            al cooldown actual.
        """
        with self._lock:
            last = self._last_failure.get(connection)
            if last is None:
                return False
            return self._clock() - last < self._cooldowns.get(connection, 0.0)

    def record_success(self, connection: str) -> None:
        """
        Limpia todo el estado de cooldown de la conexion.

        Args:
            connection: identificador de la conexion o instancia.
        """
        with self._lock:
            self._failure_counts.pop(connection, None)
            self._cooldowns.pop(connection, None)
            self._last_failure.pop(connection, None)

    def get_remaining_seconds(self, connection: str) -> float:
        """
        Devuelve los segundos restantes de cooldown de la conexion.

        Args:
            connection: identificador de la conexion o instancia.

        Returns:
            Segundos restantes (>= 0); 0.0 si no hay cooldown activo.
        """
        with self._lock:
            last = self._last_failure.get(connection)
            if last is None:
                return 0.0
            remaining = (
                self._cooldowns.get(connection, 0.0) - (self._clock() - last)
            )
            return max(remaining, 0.0)

    def active_cooldowns(self) -> dict[str, float]:
        """
        Reporta los cooldowns activos en este instante.

        Returns:
            dict {connection: segundos restantes} con cooldowns activos.
        """
        with self._lock:
            now = self._clock()
            result: dict[str, float] = {}
            for connection, cooldown in self._cooldowns.items():
                remaining = cooldown - (now - self._last_failure[connection])
                if remaining > 0:
                    result[connection] = round(remaining, 3)
            return result


# ---------------------------------------------------------------------------
# Scope 3: ModelLockout
# ---------------------------------------------------------------------------


class ModelLockout:
    """
    Lockout por tripla (recurso, agente, modelo) con success-decay.

    Al alcanzar failure_threshold fallos la tripla queda bloqueada. Cada
    exito divide el contador a la mitad (floor(f/2)); al llegar a 0 el
    lockout se borra: un exito cura sin esperar timers. Thread-safe.
    """

    def __init__(self, failure_threshold: int = 3, decay_on_success: bool = True) -> None:
        """
        Args:
            failure_threshold: fallos acumulados que activan el lockout.
            decay_on_success: si True, los exitos dividen el contador.

        Raises:
            ValueError: si failure_threshold es menor a 1.
        """
        if failure_threshold < 1:
            raise ValueError(
                f"failure_threshold debe ser >= 1, recibido {failure_threshold} "
                "(WHY: umbral cero bloquearia todo desde el inicio; "
                "WHERE: ModelLockout.__init__)"
            )
        self.failure_threshold: int = failure_threshold
        self.decay_on_success: bool = decay_on_success
        self._failures: dict[tuple[str, str, str], int] = {}
        self._lock = threading.Lock()

    @staticmethod
    def _key(resource: str, agent: str, model: str) -> tuple[str, str, str]:
        """Normaliza la tripla a la clave interna del contador."""
        return (resource, agent, model)

    def record_failure(self, resource: str, agent: str, model: str) -> None:
        """
        Incrementa el contador de fallos de la tripla.

        Args:
            resource: recurso o proveedor implicado.
            agent: agente implicado.
            model: modelo implicado.
        """
        with self._lock:
            key = self._key(resource, agent, model)
            self._failures[key] = self._failures.get(key, 0) + 1

    def is_locked(self, resource: str, agent: str, model: str) -> bool:
        """
        Indica si la tripla esta en lockout.

        Args:
            resource: recurso o proveedor implicado.
            agent: agente implicado.
            model: modelo implicado.

        Returns:
            True si el contador de la tripla alcanzo failure_threshold.
        """
        with self._lock:
            count = self._failures.get(self._key(resource, agent, model), 0)
            return count >= self.failure_threshold

    def record_success(self, resource: str, agent: str, model: str) -> None:
        """
        Aplica success-decay: divide el contador a la mitad (floor f/2).

        Si el resultado es 0 se borra el lockout de la tripla. No opera
        si decay_on_success es False.

        Args:
            resource: recurso o proveedor implicado.
            agent: agente implicado.
            model: modelo implicado.
        """
        with self._lock:
            if not self.decay_on_success:
                return
            key = self._key(resource, agent, model)
            count = self._failures.get(key, 0)
            if count == 0:
                return
            count //= 2
            if count == 0:
                self._failures.pop(key, None)
            else:
                self._failures[key] = count

    def active_lockouts(self) -> list[tuple[str, str, str]]:
        """
        Devuelve las triplas actualmente en lockout.

        Returns:
            lista de triplas (resource, agent, model) bloqueadas.
        """
        with self._lock:
            return [
                key
                for key, count in self._failures.items()
                if count >= self.failure_threshold
            ]


# ---------------------------------------------------------------------------
# Orquestacion de los 3 scopes
# ---------------------------------------------------------------------------


class ResilienceGovernance:
    """
    Orquesta las 3 capas de resiliencia (OmniRoute) sobre el routing.

    Scope 1: circuit breaker por proveedor (lazy, clase existente).
    Scope 2: cooldown por conexion/instancia (ConnectionCooldown).
    Scope 3: lockout por tripla con success-decay (ModelLockout).
    """

    def __init__(self, clock: Callable[[], float] = time.time) -> None:
        """
        Args:
            clock: funcion sin argumentos del tiempo actual, propagada a
                ConnectionCooldown (inyectable en tests).
        """
        self.connection_cooldown: ConnectionCooldown = ConnectionCooldown(clock=clock)
        self.model_lockout: ModelLockout = ModelLockout()
        self._circuit_breakers: dict[str, CircuitBreaker] = {}
        self._lock = threading.Lock()

    def record_failure(
        self, resource: str, agent: str = "", model: str = ""
    ) -> None:
        """
        Registra un fallo en cooldown (por recurso) y lockout (por tripla).

        Args:
            resource: recurso o proveedor implicado.
            agent: agente implicado (vacio para fallos solo de recurso).
            model: modelo implicado (vacio para fallos solo de recurso).
        """
        self.connection_cooldown.record_failure(resource)
        self.model_lockout.record_failure(resource, agent, model)

    def record_success(
        self, resource: str, agent: str = "", model: str = ""
    ) -> None:
        """
        Cura ambas capas: limpia el cooldown y aplica success-decay.

        Args:
            resource: recurso o proveedor implicado.
            agent: agente implicado (vacio para exitos solo de recurso).
            model: modelo implicado (vacio para exitos solo de recurso).
        """
        self.connection_cooldown.record_success(resource)
        self.model_lockout.record_success(resource, agent, model)

    def can_proceed(
        self, resource: str, agent: str = "", model: str = ""
    ) -> bool:
        """
        Determina si una operacion puede ejecutarse para el recurso/tripla.

        Args:
            resource: recurso o proveedor implicado.
            agent: agente implicado.
            model: modelo implicado.

        Returns:
            False si hay cooldown activo para el recurso O lockout activo
            para la tripla; True en caso contrario.
        """
        if self.connection_cooldown.is_cooling_down(resource):
            return False
        return not self.model_lockout.is_locked(resource, agent, model)

    def get_circuit_breaker(self, provider: str) -> CircuitBreaker:
        """
        Obtiene (o crea) el CircuitBreaker existente para un proveedor.

        Args:
            provider: identificador del proveedor de LLM.

        Returns:
            CircuitBreaker de harness.orchestrator.self_healing.
        """
        with self._lock:
            if provider not in self._circuit_breakers:
                self._circuit_breakers[provider] = CircuitBreaker()
            return self._circuit_breakers[provider]

    def get_status(self) -> dict:
        """
        Reporta el estado completo de las capas de resiliencia.

        Returns:
            dict con cooldowns activos (con segundos restantes), triplas en
            lockout y estados de los circuit breakers por proveedor.
        """
        with self._lock:
            breakers = {
                provider: {
                    "state": breaker.state,
                    "failures": breaker.failure_count,
                }
                for provider, breaker in self._circuit_breakers.items()
            }
        return {
            "cooldowns": self.connection_cooldown.active_cooldowns(),
            "lockouts": self.model_lockout.active_lockouts(),
            "circuit_breakers": breakers,
        }

    def __repr__(self) -> str:
        """
        Representacion descriptiva del estado de la gobernanza.

        Returns:
            String con conteos de cooldowns, lockouts y circuit breakers.
        """
        status = self.get_status()
        return (
            f"ResilienceGovernance(cooldowns={len(status['cooldowns'])}, "
            f"lockouts={len(status['lockouts'])}, "
            f"circuit_breakers={list(self._circuit_breakers)})"
        )


__all__ = [
    "ConnectionCooldown",
    "ModelLockout",
    "ResilienceGovernance",
]
