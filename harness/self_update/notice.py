"""Aviso de update en runtime (spec ``self-update-notice.md``).

Responde al escenario: una instalacion nueva mientras el repo remoto avanza.
El arranque (``python -m harness``) y el comando ``!update`` muestran un aviso
**una vez por cooldown**; no mutan el repo ni gastan tokens.

Invariantes (spec):

- Nunca lanza: toda excepcion degrada a ``None`` (el arranque es sagrado).
- ``OFFLINE``/``NO_GIT``/``NO_REMOTE`` -> ``None`` y **sin** escribir el state
  (así un fallo de red no fija el cooldown y el reintento es pronto).
- Cooldown: fetch solo fuera de la ventana; state JSON versionado bajo
  ``.swarmind/`` junto al journal de updates del CLI standalone.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .core import CheckState, RunGit, UpdateCheck, check_remote, default_run_git
from .versions import fmt_version

logger = logging.getLogger(__name__)

#: Ventana por defecto en horas entre fetches de aviso.
DEFAULT_COOLDOWN_HOURS = 24.0

#: Version del formato del state (invalida caches de formatos viejos).
NOTICE_STATE_VERSION = "notice_state_version"
#: Valor de la version del formato.
FORMAT_VERSION = 1

#: Estado deklarado en el state cuando hubo fetch exitoso.
STATE_FILENAME = "update_notice.json"

#: Comando CLI con el que el usuario decide (SSOT de la accion).
ACTION_COMMAND = "!update check"


@dataclass(frozen=True)
class UpdateNotice:
    """Aviso de update para mostrar al usuario (inmutable).

    Args:
        kind: ``update`` (hay commits nuevos), ``diverged`` (abortar y decidir)
            o ``current`` (sin commits nuevos; no se muestra normalmente).
        message: Texto legible para descar el usuario.
        command: Comando CLI recomendado.
        behind: Commits que faltan (0 salvo ``BEHIND``).
    """

    kind: str
    message: str
    command: str
    behind: int = 0


def _repo_root() -> Path:
    """Raiz del repo de instalacion (la que contiene el journal)."""
    return Path(__file__).resolve().parents[2]


def notice_default_path(repo: Path | None = None) -> Path:
    """Ruta por defecto del state (junto al journal, no se toca hasta fetch)."""
    return (repo or _repo_root()) / ".swarmind" / STATE_FILENAME


def load_notice_state(state_path: Path) -> dict[str, Any]:
    """Lee el state ({} si falta o esta corrupto; nunca lanza)."""
    try:
        payload = json.loads(state_path.read_text(encoding="utf-8"))
    except (OSError, KeyError, ValueError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _save_notice_state(
    state_path: Path, kind: str, *, epoch: float | None = None
) -> None:
    """Persiste el cooldown tras un fetch exitoso (create_dirs, atomic-ish)."""
    payload = {
        "checked_epoch": float(epoch if epoch is not None else time.time()),
        "last_kind": kind,
        NOTICE_STATE_VERSION: FORMAT_VERSION,
    }
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(json.dumps(payload) + "\n", encoding="utf-8")


def _notice_for(check: UpdateCheck, kind: str) -> UpdateNotice | None:
    """Construye el mensaje plano para el estado descrito.

    ``current`` devuelve ``None``: al dia no genera ruido (spec SU-02), aunque
    se guarda el state para consumir el cooldown normal.
    """
    if kind == "current":
        return None
    if kind == "update":
        remota = fmt_version(check.remote_version) if check.remote_version else "?"
        plural = "es" if check.behind else ""
        message = (
            f"update disponible: {check.behind} commit{plural} en origin "
            f"(version remota {remota}). {ACTION_COMMAND}"
        )
        return UpdateNotice(
            kind=kind, message=message, command=ACTION_COMMAND, behind=check.behind
        )
    message = (
        "repo divergido del remoto: el update no se aplica automaticamente. "
        f"Usa {ACTION_COMMAND} (los guards anti-reversion aplican)."
    )
    return UpdateNotice(kind=kind, message=message, command=ACTION_COMMAND)


def _classify(check: UpdateCheck) -> str | None:
    """Clasifica un ``UpdateCheck`` en kind de aviso (None = degradado)."""
    if check.state in (CheckState.OFFLINE, CheckState.NO_GIT, CheckState.NO_REMOTE):
        return None
    if check.state is CheckState.DIVERGED:
        return "diverged"
    if check.state is CheckState.BEHIND:
        return "update"
    return "current"


def update_notice(
    repo: Path,
    *,
    state_path: Path | None = None,
    cooldown_hours: float = DEFAULT_COOLDOWN_HOURS,
    run_git: RunGit | None = None,
) -> UpdateNotice | None:
    """Aviso de update con rate-limit (spec SU-01..SU-05).

    Args:
        repo: Raiz del repositorio local.
        state_path: Ruta del state (default ``<repo>/.swarmind/notice.json``).
        cooldown_hours: Horas entre fetches (``0`` anula el rate-limit).
        run_git: Runner DI para tests sin red.

    Returns:
        ``UpdateNotice`` si toca avisar; ``None`` si esta en cooldown, es
        degradado (SU-03) o falla algo (SU-05: nunca lanza).
    """
    try:
        return _next_notice(repo, state_path, cooldown_hours, run_git)
    except Exception:
        logger.debug("update_notice degradado (excepcion)", exc_info=True)
        return None


def _next_notice(
    repo: Path,
    state_path: Path | None,
    cooldown_hours: float,
    run_git: RunGit | None,
) -> UpdateNotice | None:
    """Flujo interno: cooldown -> fetch -> clasificar -> guardar -> avisar."""
    path = state_path or notice_default_path(repo)
    state = load_notice_state(path)
    elapsed = time.time() - float(state.get("checked_epoch", 0.0))
    if cooldown_hours > 0 and state and elapsed < cooldown_hours * 3600.0:
        return None  # rate-limit: ni fetch ni aviso (SU-02)
    check = check_remote(Path(repo), run_git=run_git or default_run_git)
    kind = _classify(check)
    if kind is None:
        return None  # degradado: NO cachea el fallo (SU-03)
    _save_notice_state(path, kind)
    return _notice_for(check, kind)
