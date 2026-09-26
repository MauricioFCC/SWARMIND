"""attachment_gate.py — Attachments: admit + verify-on-read, fail-closed (ADR-0098).

WHAT: `admit_attachment` registra digest SHA-256 al publicar contenido;
`verify_attachment` lo re-verifica al leer; si cambio -> False (fail-closed
ante swap/troyano).
WHY: deepseek-harness attachments: admitPromptContent antes de publicar +
verify-on-read con digest + variantes route-sized; multimodal durable sin
inyectar bytes crudos al contexto.
WHERE: Ingesta multimodal (docs/imagenes) antes de RAG.

Uso:
    rec = admit_attachment(path)
    if not verify_attachment(rec): rechazar()
"""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger("harness.orchestrator.attachment_gate")


@dataclass(frozen=True)
class AttachmentRecord:
    """Registro de admision de un attachment.

    Attributes:
        path: Ruta admitida (string).
        digest: SHA-256 hex del contenido al admitir.
        size: Bytes al admitir.
    """

    path: str
    digest: str
    size: int


def admit_attachment(path: str | Path) -> AttachmentRecord:
    """Admite un archivo registrando su digest (fail si no existe).

    Args:
        path: Archivo a admitir.

    Returns:
        AttachmentRecord con digest y tamano.

    Raises:
        FileNotFoundError: Si no existe (WHAT+WHY+WHERE).
    """
    target = Path(path)
    if not target.is_file():
        raise FileNotFoundError(
            f"WHAT: attachment inexistente: {target}. "
            "WHY: no se puede admitir lo que no existe. "
            "WHERE: admit_attachment"
        )
    data = target.read_bytes()
    digest = hashlib.sha256(data).hexdigest()
    logger.info("attachment_gate: admitido %s (%d bytes)", target, len(data))
    return AttachmentRecord(path=str(target), digest=digest, size=len(data))


def verify_attachment(record: AttachmentRecord) -> bool:
    """Verifica que el archivo no cambio desde admit (fail-closed).

    Args:
        record: Registro de admision.

    Returns:
        True si digest y tamano coinciden; False en cualquier cambio
        (swap, append, truncate) o si desaparecio.
    """
    target = Path(record.path)
    try:
        data = target.read_bytes()
    except OSError:
        logger.warning("attachment_gate: desaparecio %s", record.path)
        return False
    if len(data) != record.size:
        logger.warning("attachment_gate: tamano cambio en %s", record.path)
        return False
    ok = hashlib.sha256(data).hexdigest() == record.digest
    if not ok:
        logger.warning("attachment_gate: digest cambio en %s", record.path)
    return ok
