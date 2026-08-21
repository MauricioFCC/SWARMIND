"""sandbox_guard — Guardián anti reward-hacking de comandos (ADR-0055).

Basado en Agent Lightning v1.0 (arXiv 2608.17528, §4.3.2): durante el
entrenamiento/evaluación agéntica se observaron 4 vectores reales de
reward hacking — leer `.git` para recuperar la solución del commit,
descargar el patch con wget/curl, traer el fix con pip download/install,
y fetch remoto vía urllib. Este módulo filtra el CONTENIDO del comando
(la whitelist de tools filtra solo el nombre) y deniega con mensajes
WHAT+WHY+WHERE accionables.

Ejemplo::

    decision = check_command("git log --oneline")
    if not decision.allowed:
        print(decision.reason)  # WHAT+WHY+WHERE
"""
from __future__ import annotations

import re
from dataclasses import dataclass

# ---------------------------------------------------------------------------
# Patrones de bloqueo (fuente unica, ADR-0055)
# ---------------------------------------------------------------------------

#: Lectura del historial/solución git (vector #1: recuperar el fix del commit).
GIT_HISTORY_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\bgit\s+(log|show|diff|reflog|blame)\b", re.IGNORECASE),
    re.compile(r"(^|[\s\"'=])\.git[/\\]", re.IGNORECASE),
    re.compile(r"\bcat\s+\.git\b", re.IGNORECASE),
)

#: Red saliente y descarga de artefactos (vectores #2-#4).
NETWORK_BLOCKLIST_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\bwget\b", re.IGNORECASE),
    re.compile(r"\bcurl\b", re.IGNORECASE),
    re.compile(r"\b(iwr|invoke-webrequest|invoke-restmethod)\b", re.IGNORECASE),
    re.compile(r"\b(scp|sftp|ssh|nc|netcat)\b", re.IGNORECASE),
    re.compile(r"\bpip\d*\s+(download|install)\b", re.IGNORECASE),
    re.compile(r"\buv\s+(pip\s+)?(add|install)\b", re.IGNORECASE),
    re.compile(r"\bnpm\s+(i|install)\b", re.IGNORECASE),
    re.compile(r"\bgit\s+(fetch|pull|push|clone)\b", re.IGNORECASE),
    re.compile(
        r"python[^&|]*\b(import\s+urllib|import\s+requests|urlopen)\b",
        re.IGNORECASE,
    ),
)


@dataclass(frozen=True)
class SandboxDecision:
    """Decisión del guard sobre un comando.

    Args:
        allowed: True si el comando puede ejecutarse.
        reason: Mensaje WHAT+WHY+WHERE cuando se deniega; "" si se permite.
        matched_rule: Nombre de la regla que disparó la denegación.
    """

    allowed: bool
    reason: str
    matched_rule: str


def _first_match(
    command: str,
    patterns: tuple[re.Pattern[str], ...],
    rule_name: str,
) -> SandboxDecision | None:
    """Retorna la decisión de denegación del primer patrón que coincida.

    Args:
        command: Comando a inspeccionar.
        patterns: Patrones compilados de la regla.
        rule_name: Nombre semántico de la regla.

    Returns:
        SandboxDecision denegatoria o None si ningún patrón coincide.
    """
    for pattern in patterns:
        if pattern.search(command):
            return SandboxDecision(
                allowed=False,
                reason=(
                    f"SandboxGuard denegó el comando por la regla "
                    f"'{rule_name}': patrón {pattern.pattern!r}. WHY: vector "
                    "documentado de reward hacking (Agent Lightning §4.3.2); "
                    "el agente no debe acceder al historial git ni a la red "
                    "saliente sin autorización explícita. WHERE: "
                    "sandbox_guard.check_command."
                ),
                matched_rule=rule_name,
            )
    return None


def check_command(
    command: str,
    *,
    allow_network: bool = False,
) -> SandboxDecision:
    """Evalúa si un comando shell puede ejecutarse en el sandbox.

    Args:
        command: Línea de comando completa que el agente quiere ejecutar.
        allow_network: Override explícito que desactiva SOLO las reglas de
            red (las reglas git-history siguen activas).

    Returns:
        SandboxDecision inmutable; `allowed=True` con reason vacía si pasa.

    Raises:
        ValueError: si command es vacío o no es string no-blank
            (WHAT vacío / WHY nada que evaluar / WHERE argumento).
    """
    if not isinstance(command, str) or not command.strip():
        raise ValueError(
            f"ValueError: comando inválido ({command!r}). WHY: check_command "
            "requiere una línea de comando no vacía que evaluar. WHERE: "
            "argumento 'command' de sandbox_guard.check_command."
        )
    git_hit = _first_match(command, GIT_HISTORY_PATTERNS, "git_history_read")
    if git_hit is not None:
        return git_hit
    if not allow_network:
        net_hit = _first_match(
            command, NETWORK_BLOCKLIST_PATTERNS, "network_egress"
        )
        if net_hit is not None:
            return net_hit
    return SandboxDecision(allowed=True, reason="", matched_rule="")
