"""op_sec.py — Higiene operativa defensiva (deep-docs, ADR-0098).

WHAT: `scrub_secrets` (enmascara KEY/SECRET/TOKEN en logs) + `secure_tmpdir`
(dir 0700 solo-owner). Sin esto: leaks en logs, races en tmp, orphans.
WHY: deepseek-harness defensive-patterns: scrub env, tmp 0700 random,
unlink sin symlinks, dispose->quiescence, dispatcher try/catch.
WHERE: Todo log con datos externos; todo tmp del harness.

Uso:
    logger.info(scrub_secrets(f"llamando {url}"))
    tmp = secure_tmpdir(base / "vault")
"""

from __future__ import annotations

import logging
import os
import re
import stat
from pathlib import Path

logger = logging.getLogger("harness.security.op_sec")

#: Valores sensibles tras clave= o clave: (min 4 chars para no cazar ruido).
_SECRET_RE = re.compile(
    r"(?i)(api[_-]?key|secret|password|passwd|token|bearer)\s*[:=]\s*(\S{4,})"
)


def scrub_secrets(text: str) -> str:
    """Enmascara valores sensibles dejando la clave visible.

    Args:
        text: Texto de log con posibles secretos.

    Returns:
        Texto con valores reemplazados por "***".
    """
    return _SECRET_RE.sub(r"\1=***", text)


def secure_tmpdir(path: str | Path) -> Path:
    """Crea un directorio temporal solo-owner (0700).

    Args:
        path: Ruta a crear (padres incluidos).

    Returns:
        Path creado con modo 0700 (en POSIX; en Windows se crea sin
        modo pero aislado por ACL de usuario).
    """
    target = Path(path)
    target.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(target, 0o700)
    except OSError as exc:
        logger.debug("op_sec: chmod 0700 no aplicado (%s)", exc)
    return target


def current_mode(path: Path) -> int:
    """Modo POSIX actual (para tests/auditoria).

    Args:
        path: Ruta a inspeccionar.

    Returns:
        Modo (st_mode & 0o777).
    """
    return stat.S_IMODE(os.stat(path).st_mode)
