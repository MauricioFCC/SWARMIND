"""idempotency_guard.py — Guard de efectos distribuidos por idempotency key (ADR-0076).

WHAT: Deduplica efectos por (idempotency_key, hash del payload): retry con
el mismo key y el mismo payload devuelve el resultado cacheado sin
re-ejecutar; mismo key con payload distinto lanza KeyPayloadMismatch.
WHY: Frontera (dump 9-8-2026): "un workflow puede quedar en limbo cuando
una mutacion de estado intermedio falla sin idempotency key" — tratar la
coordinacion agéntica como sistemas distribuidos, no prompt engineering
(transacciones compensadas, guards de boundary tipados, DLQ).
WHERE: ``ParallelExecutor``/tool calls con efectos (DB, API externa,
escrituras); retries del orquestador.

Uso:
    guard = IdempotencyGuard()
    out = guard.run("txn-1", payload, execute_fn)
    # retry: guard.run("txn-1", payload, execute_fn) -> replay cacheado
"""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger("harness.orchestrator.idempotency_guard")

_HASH_LEN = 16


def _payload_hash(payload: str) -> str:
    """Hash corto del payload (SHA-256 truncado).

    Args:
        payload: Payload serializado del efecto.

    Returns:
        Hash hexadecimal determinista.
    """
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:_HASH_LEN]


class KeyPayloadMismatch(RuntimeError):
    """El idempotency key se reuso con un payload distinto (efecto ambiguo)."""


@dataclass(frozen=True)
class GuardedResult:
    """Resultado de una ejecucion guardada.

    Attributes:
        output: Salida del efecto (ejecutado o cacheado).
        replayed: True si vino de la cache (sin re-ejecutar).
    """

    output: Any
    replayed: bool


class IdempotencyGuard:
    """Guard de idempotencia: 1 efecto por (key, payload), replays medidos.

    Attributes:
        replays: Numero de reintentos servidos desde cache (metrica).
    """

    def __init__(self) -> None:
        """Inicializa la cache vacia (key -> (payload_hash, output))."""
        self._cache: dict[str, tuple[str, Any]] = {}
        self.replays = 0

    def run(
        self,
        idempotency_key: str,
        payload: str,
        execute_fn,
    ) -> GuardedResult:
        """Ejecuta (o replay) el efecto con guard de idempotencia.

        Args:
            idempotency_key: Clave unica del efecto (no vacia).
            payload: Payload serializado del efecto.
            execute_fn: Callable (payload) -> resultado; SOLO se llama en
                el primer intento del par (key, payload).

        Returns:
            GuardedResult con la salida y flag replayed.

        Raises:
            ValueError: Si el key esta vacio (WHAT+WHY+WHERE).
            KeyPayloadMismatch: Si el key se reuso con payload distinto.
        """
        if not idempotency_key.strip():
            raise ValueError(
                "WHAT: idempotency_key vacia. "
                "WHY: sin key no hay deduplicacion de efectos (retry = "
                "doble efecto). "
                "WHERE: IdempotencyGuard.run"
            )
        digest = _payload_hash(payload)
        cached = self._cache.get(idempotency_key)
        if cached is not None:
            cached_hash, output = cached
            if cached_hash != digest:
                raise KeyPayloadMismatch(
                    f"WHAT: idempotency_key '{idempotency_key}' reusada con "
                    f"payload distinto. "
                    f"WHY: el guard no puede saber si el efecto previo "
                    f"aplica; reusar la key con otro payload es un bug "
                    f"(retry ambiguo). WHERE: IdempotencyGuard.run"
                )
            self.replays += 1
            logger.debug("idempotency_guard: replay de '%s' (sin re-ejecutar)", idempotency_key)
            return GuardedResult(output=output, replayed=True)
        output = execute_fn(payload)
        self._cache[idempotency_key] = (digest, output)
        return GuardedResult(output=output, replayed=False)
