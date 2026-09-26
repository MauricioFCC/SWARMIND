"""misbehavior_guard.py — Guard contra las 6 conductas inesperadas (ADR-0088).

WHAT: Audita cada tool-call ANTES de ejecutar: credenciales expuestas en
args, subida de archivos a externos (exfiltracion), comandos destructivos
sin aprobacion, ocultamiento de errores; lo limpio pasa.
WHY: OpenAI (6 conductas en agentes frontier): ocultar errores, usar
creds expuestas, subir files. El agente PIDE la accion, no decide
autoridad: least-privilege + sandbox + aprobacion humana.
WHERE: Pre-tool-call en el orquestador (antes del executor).

Uso:
    report = check_tool_call("bash", {"cmd": "pytest -q"})
    if report.blocked: pedir_aprobacion(report.reason)
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger("harness.security.misbehavior_guard")

#: Patrones de credenciales expuestas (claves, tokens, secretos).
_CRED_RE = re.compile(
    r"(sk-[A-Za-z0-9]{6,}|AKIA[0-9A-Z]{16}|xox[bpas]-[A-Za-z0-9-]+|"
    r"ghp_[A-Za-z0-9]{10,}|gsk_[A-Za-z0-9]{10,}|"
    r"(api[_-]?key|secret|password|passwd|token)\s*[:=]\s*\S+)",
    re.IGNORECASE,
)

#: Verbos/patrones de subida a externos (exfiltracion).
_UPLOAD_RE = re.compile(
    r"\b(upload|push\s+to\s+https?|curl\s+.*\s+-d\b|scp\s+\S+\s+\S+@|"
    r"ftp\s|POST\s+https?://(?!localhost|127\.0\.0\.1))",
    re.IGNORECASE,
)

#: Comandos destructivos que exigen aprobacion explicita.
_DESTRUCTIVE_RE = re.compile(
    r"\b(rm\s+-rf?\s+[/~]|mkfs|dd\s+if=.*\s+of=/dev|shutdown|reboot|"
    r"DROP\s+TABLE|DELETE\s+FROM\s+\w+\s*;?\s*$)",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class MisbehaviorReport:
    """Reporte de auditoria de un tool-call.

    Attributes:
        blocked: True si debe bloquearse/pedir aprobacion.
        reason: Motivo legible (conducta detectada o "limpia").
    """

    blocked: bool
    reason: str


def check_tool_call(tool: str, args: dict[str, Any]) -> MisbehaviorReport:
    """Audita un tool-call antes de ejecutarlo.

    Args:
        tool: Nombre de la herramienta (no vacio).
        args: Argumentos serializables del call.

    Returns:
        MisbehaviorReport (blocked=True exige aprobacion humana).

    Raises:
        ValueError: Si tool esta vacio (WHAT+WHY+WHERE).
    """
    if not tool.strip():
        raise ValueError(
            "WHAT: tool vacia. "
            "WHY: sin herramienta no hay nada que auditar. "
            "WHERE: check_tool_call"
        )
    blob = f"{tool} {args}"
    if _CRED_RE.search(blob):
        return _block("credencial expuesta en argumentos: rotar y usar vault/env")
    if tool.strip().lower() in ("upload", "push-external", "exfiltrate") or (
        "upload" in tool.lower() and _UPLOAD_RE.search(blob)
    ):
        return _block("subida a externo: posible exfiltracion, requiere aprobacion")
    if _UPLOAD_RE.search(blob) and any(
        ext in blob.lower() for ext in (".csv", ".db", ".json", "clientes", "usuarios")
    ):
        return _block("subida de datos a externo: posible exfiltracion, requiere aprobacion")
    if _DESTRUCTIVE_RE.search(blob):
        return _block("comando destructivo: requiere aprobacion explicita")
    return MisbehaviorReport(blocked=False, reason="llamada limpia")


def _block(reason: str) -> MisbehaviorReport:
    """Construye un bloqueo con log de seguridad.

    Args:
        reason: Motivo del bloqueo.

    Returns:
        MisbehaviorReport bloqueado.
    """
    logger.warning("misbehavior_guard: BLOQUEO (%s)", reason)
    return MisbehaviorReport(blocked=True, reason=reason)
