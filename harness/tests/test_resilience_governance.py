"""Tests para Resilience Governance de 3 scopes (ADR-0033, OmniRoute)."""
from __future__ import annotations

import pytest

from harness.orchestrator.resilience_governance import (
    ConnectionCooldown,
    ModelLockout,
    ResilienceGovernance,
)
from harness.orchestrator.self_healing import CircuitBreaker


class FakeClock:
    """Reloj inyectable para controlar el tiempo en los tests."""

    def __init__(self, start: float = 1000.0) -> None:
        self.now = start

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


@pytest.fixture
def clock() -> FakeClock:
    """FakeClock compartido por los tests sensibles al tiempo."""
    return FakeClock()


# ===========================================================================
# Test: ConnectionCooldown (Scope 2)
# ===========================================================================


class TestConnectionCooldown:
    """Backoff exponencial por conexion/instancia."""

    def test_initial_state_allows_proceed(self, clock: FakeClock) -> None:
        """Sin fallos no debe haber cooldown activo."""
        cooldown = ConnectionCooldown(clock=clock)
        assert cooldown.is_cooling_down("conn-1") is False
        assert cooldown.get_remaining_seconds("conn-1") == 0.0

    def test_exponential_backoff_sequence(self, clock: FakeClock) -> None:
        """1 fallo -> base; 2 fallos -> base*2; 3 fallos -> base*4 (5s/10s/20s)."""
        cooldown = ConnectionCooldown(base_cooldown=5.0, clock=clock)
        cooldown.record_failure("conn-1")
        assert cooldown.get_remaining_seconds("conn-1") == pytest.approx(5.0)
        cooldown.record_failure("conn-1")
        assert cooldown.get_remaining_seconds("conn-1") == pytest.approx(10.0)
        cooldown.record_failure("conn-1")
        assert cooldown.get_remaining_seconds("conn-1") == pytest.approx(20.0)

    def test_cooldown_capped_at_max(self, clock: FakeClock) -> None:
        """El backoff no debe superar max_cooldown."""
        cooldown = ConnectionCooldown(
            base_cooldown=5.0, max_cooldown=25.0, clock=clock
        )
        for _ in range(6):  # 5, 10, 20, 40, 80, 160 -> tope 25
            cooldown.record_failure("conn-1")
        assert cooldown.get_remaining_seconds("conn-1") == pytest.approx(25.0)

    def test_is_cooling_down_until_time_elapses(self, clock: FakeClock) -> None:
        """is_cooling_down debe ser True hasta que pase el cooldown."""
        cooldown = ConnectionCooldown(base_cooldown=5.0, clock=clock)
        cooldown.record_failure("conn-1")
        assert cooldown.is_cooling_down("conn-1") is True
        clock.advance(4.0)
        assert cooldown.is_cooling_down("conn-1") is True
        clock.advance(1.5)  # 5.5s transcurridos > 5s
        assert cooldown.is_cooling_down("conn-1") is False

    def test_record_success_clears_all_state(self, clock: FakeClock) -> None:
        """record_success debe limpiar el estado completo de la conexion."""
        cooldown = ConnectionCooldown(base_cooldown=5.0, clock=clock)
        cooldown.record_failure("conn-1")
        cooldown.record_failure("conn-1")
        cooldown.record_success("conn-1")
        assert cooldown.is_cooling_down("conn-1") is False
        assert cooldown.get_remaining_seconds("conn-1") == 0.0
        # El backoff se reinicia: un nuevo fallo vuelve a base, no a base*4
        cooldown.record_failure("conn-1")
        assert cooldown.get_remaining_seconds("conn-1") == pytest.approx(5.0)

    def test_connections_are_isolated(self, clock: FakeClock) -> None:
        """El estado de una conexion no debe afectar a otra."""
        cooldown = ConnectionCooldown(base_cooldown=5.0, clock=clock)
        cooldown.record_failure("conn-a")
        assert cooldown.is_cooling_down("conn-a") is True
        assert cooldown.is_cooling_down("conn-b") is False

    def test_anti_thundering_herd_refreshes_timestamp(self, clock: FakeClock) -> None:
        """Un fallo adicional durante el cooldown refresca el reloj de espera."""
        cooldown = ConnectionCooldown(base_cooldown=5.0, clock=clock)
        cooldown.record_failure("conn-1")
        clock.advance(4.5)
        cooldown.record_failure("conn-1")  # la manada golpea de nuevo: se refresca
        assert cooldown.is_cooling_down("conn-1") is True
        clock.advance(10.0)  # nuevo cooldown de 10s
        assert cooldown.is_cooling_down("conn-1") is False


# ===========================================================================
# Test: ModelLockout (Scope 3)
# ===========================================================================


class TestModelLockout:
    """Lockout por tripla recurso+agente+modelo con success-decay."""

    def test_below_threshold_not_locked(self) -> None:
        """Por debajo del umbral la tripla no debe estar bloqueada."""
        lockout = ModelLockout(failure_threshold=3)
        lockout.record_failure("res-1", "agent-a", "model-x")
        lockout.record_failure("res-1", "agent-a", "model-x")
        assert lockout.is_locked("res-1", "agent-a", "model-x") is False

    def test_threshold_reached_locks(self) -> None:
        """Al alcanzar el umbral la tripla debe quedar bloqueada."""
        lockout = ModelLockout(failure_threshold=3)
        for _ in range(3):
            lockout.record_failure("res-1", "agent-a", "model-x")
        assert lockout.is_locked("res-1", "agent-a", "model-x") is True
        assert ("res-1", "agent-a", "model-x") in lockout.active_lockouts()

    def test_success_decay_halves_counter(self) -> None:
        """4 fallos (locked) + 2 exitos -> 4//2=2 -> 2//2=1 -> NOT locked."""
        lockout = ModelLockout(failure_threshold=3)
        for _ in range(4):
            lockout.record_failure("res-1", "agent-a", "model-x")
        assert lockout.is_locked("res-1", "agent-a", "model-x") is True
        lockout.record_success("res-1", "agent-a", "model-x")  # 4 -> 2
        assert lockout.is_locked("res-1", "agent-a", "model-x") is False
        lockout.record_success("res-1", "agent-a", "model-x")  # 2 -> 1
        assert lockout.active_lockouts() == []

    def test_success_to_zero_removes_lockout(self) -> None:
        """Exitos repetidos llevan el contador a 0 y borran el estado."""
        lockout = ModelLockout(failure_threshold=3)
        lockout.record_failure("res-1", "agent-a", "model-x")
        lockout.record_failure("res-1", "agent-a", "model-x")
        lockout.record_success("res-1", "agent-a", "model-x")  # 2 -> 1
        lockout.record_success("res-1", "agent-a", "model-x")  # 1 -> 0 -> eliminado
        assert lockout.is_locked("res-1", "agent-a", "model-x") is False
        assert lockout.active_lockouts() == []

    def test_decay_disabled_keeps_counter(self) -> None:
        """Con decay_on_success=False el exito no debe curar el contador."""
        lockout = ModelLockout(failure_threshold=3, decay_on_success=False)
        for _ in range(4):
            lockout.record_failure("res-1", "agent-a", "model-x")
        lockout.record_success("res-1", "agent-a", "model-x")
        assert lockout.is_locked("res-1", "agent-a", "model-x") is True

    def test_lockout_triples_are_independent(self) -> None:
        """Cambiar agente o modelo debe crear una tripla independiente."""
        lockout = ModelLockout(failure_threshold=2)
        lockout.record_failure("res-1", "agent-a", "model-x")
        lockout.record_failure("res-1", "agent-a", "model-x")
        assert lockout.is_locked("res-1", "agent-a", "model-x") is True
        assert lockout.is_locked("res-1", "agent-b", "model-x") is False


# ===========================================================================
# Test: ResilienceGovernance (orquestacion de los 3 scopes)
# ===========================================================================


class TestResilienceGovernance:
    """Orquestacion de cooldown + lockout + circuit breaker existente."""

    def test_record_failure_blocks_can_proceed(self, clock: FakeClock) -> None:
        """Tras un fallo, can_proceed debe ser False para la misma tripla."""
        governance = ResilienceGovernance(clock=clock)
        assert governance.can_proceed("res-1") is True
        governance.record_failure("res-1", agent="agent-a", model="model-x")
        assert (
            governance.can_proceed("res-1", agent="agent-a", model="model-x") is False
        )

    def test_record_success_restores_can_proceed(self, clock: FakeClock) -> None:
        """Tras curacion por success-decay y expiracion del cooldown, True."""
        governance = ResilienceGovernance(clock=clock)
        for _ in range(3):
            governance.record_failure("res-1", agent="agent-a", model="model-x")
        assert (
            governance.can_proceed("res-1", agent="agent-a", model="model-x") is False
        )
        governance.record_success("res-1", agent="agent-a", model="model-x")  # 3 -> 1
        governance.record_success("res-1", agent="agent-a", model="model-x")  # 1 -> 0
        clock.advance(100.0)  # deja expirar el cooldown de la conexion
        assert (
            governance.can_proceed("res-1", agent="agent-a", model="model-x") is True
        )

    def test_lockout_blocks_after_cooldown_expires(self, clock: FakeClock) -> None:
        """El lockout persiste aunque el cooldown transitorio haya expirado."""
        governance = ResilienceGovernance(clock=clock)
        for _ in range(3):
            governance.record_failure("res-1", agent="agent-a", model="model-x")
        clock.advance(1000.0)  # cooldown expirado
        assert (
            governance.can_proceed("res-1", agent="agent-a", model="model-x") is False
        )
        assert (
            governance.can_proceed("res-1", agent="agent-b", model="model-x") is True
        )

    def test_cooling_down_blocks_any_triple_of_resource(
        self, clock: FakeClock
    ) -> None:
        """El cooldown por recurso bloquea aunque la tripla sea desconocida."""
        governance = ResilienceGovernance(clock=clock)
        governance.record_failure("res-1")
        assert governance.can_proceed("res-1") is False
        assert governance.can_proceed("res-2") is True

    def test_get_status_reports_cooldowns_and_lockouts(
        self, clock: FakeClock
    ) -> None:
        """get_status debe reportar cooldowns activos y lockouts."""
        governance = ResilienceGovernance(clock=clock)
        assert governance.get_status()["lockouts"] == []
        for _ in range(3):
            governance.record_failure("res-1", agent="agent-a", model="model-x")
        status = governance.get_status()
        assert "res-1" in status["cooldowns"]
        assert ("res-1", "agent-a", "model-x") in status["lockouts"]

    def test_repr_descriptive(self) -> None:
        """__repr__ debe describir el estado de la gobernanza."""
        governance = ResilienceGovernance()
        assert "ResilienceGovernance" in repr(governance)

    def test_get_circuit_breaker_lazy_creation(self) -> None:
        """El circuit breaker existente se integra de forma perezosa."""
        governance = ResilienceGovernance()
        breaker = governance.get_circuit_breaker("provider-1")
        assert isinstance(breaker, CircuitBreaker)
        assert governance.get_circuit_breaker("provider-1") is breaker
