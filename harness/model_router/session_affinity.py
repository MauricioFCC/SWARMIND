"""session_affinity.py — Routing sticky por sesion (ADR-0073, patron SAAR).

WHAT: Fija el tier de modelo por session_id con TTL; las tareas
siguientes de la sesion reutilizan la decision sin re-clasificar.
WHY: vLLM SAAR (frontera 2026) — la afinidad de sesion evita switches
de modelo repetidos: -79% switches y -78.7% costo en deployments
multi-agente; cada switch pierde cache de prefijo y re-paga prefill.
WHERE: Delante del ComplexityRouter/CascadeRouter en sesiones
continuas (chat, workflows largos); metrica switches_avoided auditable.

Uso:
    router = SessionAffinityRouter(complexity_router.decide_tier)
    result = router.route(session_id, task)
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass

logger = logging.getLogger("harness.model_router.session_affinity")

#: Tiers validos (alineados con cascade_router.TIER_ORDER).
VALID_TIERS: frozenset[str] = frozenset({"small", "frontier"})

#: TTL por defecto de la afinidad de sesion (segundos).
DEFAULT_TTL_S = 1800.0


@dataclass(frozen=True)
class AffinityConfig:
    """Config de afinidad de sesion.

    Attributes:
        ttl_s: Segundos de vida de la afinidad (renovable en cada uso).
        max_sessions: Tope de sesiones memorizadas (evita leak).
    """

    ttl_s: float = DEFAULT_TTL_S
    max_sessions: int = 256


@dataclass(frozen=True)
class AffinityResult:
    """Resultado de routing con afinidad.

    Attributes:
        tier: Tier servido.
        from_cache: True si vino de afinidad (sin re-decidir).
    """

    tier: str
    from_cache: bool


@dataclass
class _SessionEntry:
    """Entrada mutable interna (no expuesta)."""

    tier: str
    last_seen: float


def _default_clock() -> float:
    """Reloj por defecto (time.monotonic)."""
    return time.monotonic()


class SessionAffinityRouter:
    """Router sticky: 1 decision por sesion, TTL, switches evitados medidos.

    Args:
        decide_fn: (task) -> tier ("small"|"frontier").
        config: Config de afinidad (TTL, max_sessions).
        clock: Fuente de tiempo inyectable (tests).
    """

    def __init__(
        self,
        decide_fn: Callable[[str], str],
        config: AffinityConfig | None = None,
        clock: Callable[[], float] | None = None,
    ) -> None:
        self._decide_fn = decide_fn
        self._config = config or AffinityConfig()
        self._clock = clock or _default_clock
        self._sessions: dict[str, _SessionEntry] = {}
        self._switches_avoided = 0

    @property
    def switches_avoided(self) -> int:
        """Switches de modelo evitados por afinidad (metrica SAAR)."""
        return self._switches_avoided

    def route(self, session_id: str, task: str) -> AffinityResult:
        """Enruta la tarea con afinidad de sesion.

        Args:
            session_id: Identificador de sesion (no vacio).
            task: Texto de la tarea (no vacio).

        Returns:
            AffinityResult con tier y flag from_cache.

        Raises:
            ValueError: Si session_id/task vacios o tier desconocido
                (WHAT+WHY+WHERE).
        """
        if not session_id.strip():
            raise ValueError(
                "WHAT: session_id vacio. "
                "WHY: la afinidad se define por sesion. "
                "WHERE: SessionAffinityRouter.route"
            )
        if not task.strip():
            raise ValueError(
                "WHAT: task vacia. "
                "WHY: sin tarea no hay routing. "
                "WHERE: SessionAffinityRouter.route"
            )
        now = self._clock()
        entry = self._sessions.get(session_id)
        if entry is not None and now - entry.last_seen <= self._config.ttl_s:
            entry.last_seen = now
            self._switches_avoided += 1
            return AffinityResult(tier=entry.tier, from_cache=True)
        tier = self._decide_fn(task)
        if tier not in VALID_TIERS:
            raise ValueError(
                f"WHAT: tier desconocido: {tier}. "
                f"WHY: debe ser uno de {sorted(VALID_TIERS)}. "
                "WHERE: SessionAffinityRouter.route"
            )
        self._remember(session_id, tier, now)
        return AffinityResult(tier=tier, from_cache=False)

    def _remember(self, session_id: str, tier: str, now: float) -> None:
        """Guarda la afinidad con evict simple al superar max_sessions.

        Args:
            session_id: Sesion a memorizar.
            tier: Tier decidido.
            now: Timestamp actual del clock.
        """
        if len(self._sessions) >= self._config.max_sessions and session_id not in self._sessions:
            oldest = min(self._sessions.items(), key=lambda kv: kv[1].last_seen)
            del self._sessions[oldest[0]]
            logger.info("session_affinity: evict de sesion mas vieja")
        self._sessions[session_id] = _SessionEntry(tier=tier, last_seen=now)
