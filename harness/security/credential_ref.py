"""credential_ref.py — Secretos por referencia nominal (deep-docs, ADR-0098).

WHAT: `register` guarda valores solo en memoria; `resolve` los lee por
operacion (sin cache: la rotacion aplica en el next-request); `describe`
es UI-safe (nunca expone valores); records `<scope/id>`.
WHY: deepseek-harness credentials/: rotacion sin restart, vault futuro
(keyring/KMS), eventos reference/record-updated. Nunca valores en
contexto, logs o prompts (SEG).
WHERE: Tool calls con credenciales (API keys, tokens); `misbehavior_guard`
bloquea valores literales, aqui van las referencias.

Uso:
    store.register("github/token", valor)
    token = resolve_credential(store, "github/token")  # por-op
"""

from __future__ import annotations

import logging

logger = logging.getLogger("harness.security.credential_ref")


class CredentialStore:
    """Store en memoria de secretos por nombre (sin persistencia).

    Attributes:
        count: Referencias registradas (metrica, sin valores).
    """

    def __init__(self) -> None:
        """Inicializa el store vacio."""
        self._values: dict[str, str] = {}

    @property
    def count(self) -> int:
        """Numero de referencias (nunca valores)."""
        return len(self._values)

    def register(self, name: str, value: str) -> None:
        """Registra (o rota) un secreto por nombre.

        Args:
            name: Referencia `<scope/id>` (no vacia).
            value: Secreto (no se loguea jamas).

        Raises:
            ValueError: Si el nombre esta vacio (WHAT+WHY+WHERE).
        """
        if not name.strip():
            raise ValueError(
                "WHAT: nombre de referencia vacio. "
                "WHY: sin nombre no hay referencia que resolver. "
                "WHERE: CredentialStore.register"
            )
        self._values[name.strip()] = value
        logger.info("credential_ref: registrada referencia '%s'", name.strip())

    def describe(self, name: str) -> str:
        """Describe UI-safe (nombre + estado, jamas el valor).

        Args:
            name: Referencia a describir.

        Returns:
            Texto sin secretos (o "desconocida").
        """
        if name in self._values:
            return f"credential[{name}] (registrada)"
        return f"credential[{name}] (desconocida)"


def resolve_credential(store: CredentialStore, name: str) -> str:
    """Resuelve el valor actual por operacion (sin cache).

    Args:
        store: Store con el secreto.
        name: Referencia a resolver.

    Returns:
        Valor vigente (post-rotacion si hubo).

    Raises:
        KeyError: Si la referencia no existe (WHAT+WHY+WHERE).
    """
    try:
        return store._values[name]
    except KeyError as exc:
        raise KeyError(
            f"WHAT: referencia desconocida: '{name}'. "
            f"WHY: no registrada (typo o falta register). "
            f"WHERE: resolve_credential"
        ) from exc
