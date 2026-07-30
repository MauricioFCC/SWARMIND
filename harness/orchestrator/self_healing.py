"""
Circuit Breaker y Self-Healing Context para el Task Orchestrator.

Implementa el patrón Circuit Breaker (closed → open → half-open) para
proteger operaciones sobre agentes, y SelfHealingContext para detectar
timeouts por nivel, estancamiento de progreso y gestión de fallos.

Uso:
    cb = CircuitBreaker(failure_threshold=3, recovery_timeout=30.0)
    if cb.is_available:
        # ejecutar operación
        cb.record_success()
    else:
        cb.record_failure()

    healing = SelfHealingContext(session_id="abc-123")
    healing.advance_level(1)
    issue = healing.check_timeout()  # None si ok
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field

from harness.orchestrator.structured_log import StructuredLogRecord

# ---------------------------------------------------------------------------
# Circuit Breaker
# ---------------------------------------------------------------------------


@dataclass
class CircuitBreaker:
    """
    Circuit Breaker pattern para operaciones sobre agentes.

    Estados:
      - closed:   operación normal, failures count
      - open:     umbral de fallos alcanzado, rechaza operaciones
      - half-open: periodo de recuperación, permite 1 intento

    Attributes:
        failure_threshold: N fallos consecutivos para abrir el circuito
        recovery_timeout:  segundos hasta pasar a half-open
        failure_count:     contador actual de fallos consecutivos
        state:             estado actual
        last_failure_time: timestamp del último fallo
    """
    failure_threshold: int = 3
    recovery_timeout: float = 30.0
    failure_count: int = 0
    state: str = "closed"
    last_failure_time: float = 0.0
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def record_failure(self) -> None:
        """Registra un fallo. Abre el circuito si se excede el umbral."""
        with self._lock:
            self.failure_count += 1
            self.last_failure_time = time.time()
            if self.failure_count >= self.failure_threshold:
                self.state = "open"
                StructuredLogRecord.warning(
                    "circuit_breaker_open",
                    message=f"Circuit abierto tras {self.failure_count} fallos",
                    failure_count=self.failure_count,
                    threshold=self.failure_threshold,
                )

    def record_success(self) -> None:
        """Registra un éxito. Cierra/resetea el circuito."""
        with self._lock:
            self.failure_count = 0
            if self.state == "half-open":
                self.state = "closed"
                StructuredLogRecord.info(
                    "circuit_breaker_closed",
                    message="Circuit cerrado tras recuperación exitosa",
                )
            elif self.state == "open":
                self.state = "half-open"
                StructuredLogRecord.info(
                    "circuit_breaker_half_open",
                    message="Circuit en half-open, intentando recuperación",
                )

    @property
    def is_available(self) -> bool:
        """Checkea si el circuito permite ejecutar operaciones."""
        with self._lock:
            if self.state == "closed":
                return True
            if self.state == "open":
                # Check if recovery timeout has elapsed
                if time.time() - self.last_failure_time >= self.recovery_timeout:
                    self.state = "half-open"
                    StructuredLogRecord.info(
                        "circuit_breaker_half_open",
                        message="Circuit pasó a half-open por timeout",
                    )
                    return True
                return False
            # half-open: allow one attempt
            return True

    def __repr__(self) -> str:
        return (
            f"CircuitBreaker(state={self.state}, "
            f"failures={self.failure_count}/{self.failure_threshold})"
        )


# ---------------------------------------------------------------------------
# Self-Healing Context
# ---------------------------------------------------------------------------


@dataclass
class SelfHealingContext:
    """
    Contexto de self-healing para una sesión activa.

    Trackea:
      - Tiempo transcurrido por nivel (timeout detection)
      - Último progreso registrado (stall detection)
      - Circuit breaker por agente
    """
    session_id: str
    level_start_time: float = field(default_factory=time.time)
    last_progress_time: float = field(default_factory=time.time)
    current_level: int = 0
    level_timeout_sec: float = 300.0
    stall_timeout_sec: float = 120.0
    circuit_breakers: dict[str, CircuitBreaker] = field(default_factory=dict)
    stalled_warnings: int = 0
    max_stalled_warnings: int = 3

    def get_circuit_breaker(self, agent: str) -> CircuitBreaker:
        """Obtiene (o crea) el circuit breaker para un agente."""
        if agent not in self.circuit_breakers:
            self.circuit_breakers[agent] = CircuitBreaker()
        return self.circuit_breakers[agent]

    def record_progress(self) -> None:
        """Registra que hubo progreso."""
        self.last_progress_time = time.time()

    def advance_level(self, level: int) -> None:
        """Avanza a un nuevo nivel."""
        self.current_level = level
        self.level_start_time = time.time()
        self.record_progress()

    def check_timeout(self) -> str | None:
        """Checkea timeout del nivel actual."""
        elapsed = time.time() - self.level_start_time
        if elapsed > self.level_timeout_sec:
            return (
                f"LEVEL_TIMEOUT: Nivel {self.current_level} "
                f"excedió {self.level_timeout_sec}s ({elapsed:.0f}s transcurridos)"
            )
        return None

    def check_stalled(self) -> str | None:
        """Checkea si el progreso está estancado."""
        elapsed = time.time() - self.last_progress_time
        if elapsed > self.stall_timeout_sec:
            self.stalled_warnings += 1
            return (
                f"STALL_DETECTED: Sin progreso por {elapsed:.0f}s "
                f"(umbral: {self.stall_timeout_sec}s, "
                f"advertencia {self.stalled_warnings}/{self.max_stalled_warnings})"
            )
        return None

    def is_critical(self) -> bool:
        """Determina si la sesión está en estado crítico."""
        return self.stalled_warnings >= self.max_stalled_warnings

    def to_dict(self) -> dict:
        return {
            "session_id": self.session_id,
            "level": self.current_level,
            "level_age_sec": round(time.time() - self.level_start_time, 1),
            "last_progress_sec": round(time.time() - self.last_progress_time, 1),
            "stalled_warnings": self.stalled_warnings,
            "circuit_breakers": {
                k: {"state": v.state, "failures": v.failure_count}
                for k, v in self.circuit_breakers.items()
            },
        }


__all__ = ["CircuitBreaker", "SelfHealingContext"]
