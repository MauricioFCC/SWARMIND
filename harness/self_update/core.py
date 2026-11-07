"""Auto-actualizacion desde remoto anti-reversion (spec specs/self-update.md).

WHAT: detecta el estado del repo contra el remoto y aplica updates SOLO
forward (``merge --ff-only``) con gate de monotonicidad (floor =
max(local, max_seen del journal)) y journal JSONL append-only auditable.
WHY: mandato del usuario — las instalaciones locales (win/linux/mac) deben
leer el remoto y actualizarse solas, con un log que impida reversiones.
ff-only garantiza la propiedad de prefijo (si existe un update, existen
todos los anteriores) y ``audit_log`` verifica la monotonicidad historica.
WHERE: paquete harness/self_update/ (core + journal + versions) + CLI
scripts/self_update.py; cableado suave en scripts/setup_swarmind.py.
"""
from __future__ import annotations

import platform
import shutil
import subprocess
import sys
import tomllib
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import Enum
from pathlib import Path

from harness.self_update.journal import append_log, max_seen_version
from harness.self_update.versions import NO_VERSION, fmt_version, parse_semver

_DEFAULT_TIMEOUT = 60

RunGit = Callable[..., "GitResult"]


class UpdateError(Exception):
    """Error fatal de la capa de auto-actualizacion (sin fuente version)."""


class CheckState(Enum):
    """Estado inmutable del repo local respecto al remoto."""

    UP_TO_DATE = "up_to_date"
    BEHIND = "behind"
    AHEAD = "ahead"
    DIVERGED = "diverged"
    OFFLINE = "offline"
    NO_GIT = "no_git"
    NO_REMOTE = "no_remote"


class Action(Enum):
    """Accion efectuada (o bloqueada) por apply_update."""

    UPDATED = "updated"
    NOOP = "noop"
    BLOCKED_DOWNGRADE = "blocked_downgrade"
    DOWNGRADE_FORCED = "downgrade_forced"
    DIRTY_WORKTREE = "dirty_worktree"
    DIVERGED = "diverged"
    OFFLINE = "offline"
    NO_GIT = "no_git"
    NO_REMOTE = "no_remote"
    FAILED = "failed"


_EARLY_ACTIONS: dict[CheckState, Action] = {
    CheckState.OFFLINE: Action.OFFLINE,
    CheckState.NO_GIT: Action.NO_GIT,
    CheckState.NO_REMOTE: Action.NO_REMOTE,
}


@dataclass(frozen=True)
class GitResult:
    """Resultado inmutable de una invocacion de git."""

    code: int
    out: str
    err: str


@dataclass(frozen=True)
class UpdateCheck:
    """Estado del repo local vs remoto (resultado de check_remote)."""

    state: CheckState
    behind: int = 0
    ahead: int = 0
    local_version: tuple[int, ...] = NO_VERSION
    remote_version: tuple[int, ...] | None = None
    remote_url: str = ""
    local_commit: str = ""
    remote_commit: str = ""
    detail: str = ""


@dataclass(frozen=True)
class UpdateResult:
    """Resultado inmutable de apply_update."""

    action: Action
    changed: bool
    detail: str
    from_version: tuple[int, ...] = NO_VERSION
    to_version: tuple[int, ...] = NO_VERSION
    from_commit: str = ""
    to_commit: str = ""
    justification: str = ""


def default_run_git(
    args: list[str] | tuple[str, ...], cwd: Path, timeout: int = _DEFAULT_TIMEOUT
) -> GitResult:
    """Ejecuta git SIN shell; code=127 si el binario falta (0 shell injection)."""
    if shutil.which("git") is None:
        return GitResult(127, "", "git no encontrado en PATH")
    try:
        proc = subprocess.run(
            ["git", *args],
            cwd=cwd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return GitResult(124, "", f"git timeout tras {timeout}s en {' '.join(args)}")
    return GitResult(proc.returncode, proc.stdout.strip(), proc.stderr.strip())


def _version_from_pyproject(pyproject: Path) -> str | None:
    """Lee project.version del pyproject; None si falta, error si esta roto."""
    if not pyproject.is_file():
        return None
    try:
        data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
    except (tomllib.TOMLDecodeError, OSError) as exc:
        raise UpdateError(f"pyproject ilegible en {pyproject}: {exc}") from exc
    version = data.get("project", {}).get("version")
    return str(version) if version else None


def parse_version(repo: Path, run_git: RunGit | None = None) -> tuple[int, ...]:
    """Version semver del repo: pyproject.toml > git describe --tags.

    Args:
        repo: Raiz del repositorio local.
        run_git: Runner DI (default: git real via subprocess).

    Returns:
        Tupla numerica comparable, p. ej. (0, 2, 0).

    Raises:
        UpdateError: sin pyproject.version y git describe sin tag util.
    """
    runner = run_git or default_run_git
    version = _version_from_pyproject(repo / "pyproject.toml")
    if version:
        parsed = parse_semver(version)
        if parsed:
            return parsed
    descrito = runner(["describe", "--tags", "--abbrev=0"], cwd=repo)
    if descrito.code == 0 and descrito.out:
        parsed = parse_semver(descrito.out)
        if parsed:
            return parsed
    raise UpdateError(
        f"sin fuente de version en {repo}: falta pyproject.toml "
        "[project.version] y git describe no devolvio tag (parse_version)"
    )


def _head(runner: RunGit, repo: Path) -> str:
    """SHA de HEAD ('' si git falla)."""
    res = runner(["rev-parse", "HEAD"], cwd=repo)
    return res.out if res.code == 0 else ""


def _current_branch(runner: RunGit, repo: Path) -> str:
    """Rama actual ('main' si HEAD detached o git falla)."""
    res = runner(["symbolic-ref", "--short", "HEAD"], cwd=repo)
    return res.out if res.code == 0 and res.out else "main"


def _rev_count(runner: RunGit, repo: Path, spec: str) -> int:
    """Conteo rev-list; -1 si falla (nunca confiar en 0 silencioso)."""
    res = runner(["rev-list", "--count", spec], cwd=repo)
    if res.code == 0 and res.out.isdigit():
        return int(res.out)
    return -1


def _fetch_head_sha(runner: RunGit, repo: Path) -> str:
    """SHA de FETCH_HEAD (tip remoto tras el fetch)."""
    res = runner(["rev-parse", "FETCH_HEAD"], cwd=repo)
    return res.out if res.code == 0 else ""


def _remote_version(
    runner: RunGit, repo: Path, ref: str = "FETCH_HEAD"
) -> tuple[int, ...] | None:
    """Version del pyproject en el remoto sin checkout; None si es ilegible."""
    res = runner(["show", f"{ref}:pyproject.toml"], cwd=repo)
    if res.code != 0:
        return None
    try:
        data = tomllib.loads(res.out)
    except tomllib.TOMLDecodeError:
        return None
    version = data.get("project", {}).get("version")
    return parse_semver(str(version)) if version else None


def _degraded(
    state: CheckState,
    local_version: tuple[int, ...],
    local_commit: str,
    remote_url: str,
    detail: str,
) -> UpdateCheck:
    """UpdateCheck degradado (offline/no_git/no_remote) sin excepciones."""
    return UpdateCheck(
        state=state,
        local_version=local_version,
        local_commit=local_commit,
        remote_url=remote_url,
        detail=detail,
    )


def check_remote(
    repo: Path,
    remote: str = "origin",
    branch: str | None = None,
    run_git: RunGit | None = None,
) -> UpdateCheck:
    """Fetch solo-lectura del remoto y clasificacion de estado (sin excepcion).

    Args:
        repo: Raiz del repositorio local.
        remote: Nombre del remote git (default origin).
        branch: Rama objetivo (default: rama actual del repo).
        run_git: Runner DI para tests sin red.

    Returns:
        UpdateCheck con estado, contadores behind/ahead y versiones.
    """
    runner = run_git or default_run_git
    local_v = parse_version(repo, runner)
    local_c = _head(runner, repo)
    url = runner(["remote", "get-url", remote], cwd=repo)
    if url.code == 127:
        return _degraded(CheckState.NO_GIT, local_v, local_c, "", url.err)
    if url.code != 0:
        return _degraded(CheckState.NO_REMOTE, local_v, local_c, "", url.err)
    rama = branch or _current_branch(runner, repo)
    fetched = runner(["fetch", remote, rama], cwd=repo)
    if fetched.code != 0:
        return _degraded(CheckState.OFFLINE, local_v, local_c, url.out, fetched.err)
    return _counted_check(runner, repo, local_v, local_c, url.out)


def _counted_check(
    runner: RunGit, repo: Path, local_v: tuple[int, ...], local_c: str, remote_url: str
) -> UpdateCheck:
    """UpdateCheck completo tras un fetch exitoso (behind/ahead via rev-list)."""
    behind = _rev_count(runner, repo, "HEAD..FETCH_HEAD")
    ahead = _rev_count(runner, repo, "FETCH_HEAD..HEAD")
    if behind < 0 or ahead < 0:
        return _degraded(
            CheckState.OFFLINE, local_v, local_c, remote_url, "rev-list fallo tras fetch"
        )
    return UpdateCheck(
        state=_classify(behind, ahead),
        behind=behind,
        ahead=ahead,
        local_version=local_v,
        remote_version=_remote_version(runner, repo),
        remote_url=remote_url,
        local_commit=local_c,
        remote_commit=_fetch_head_sha(runner, repo),
    )


def _classify(behind: int, ahead: int) -> CheckState:
    """Clasifica ahead/behind en estado (divergido > behind > ahead)."""
    if behind > 0 and ahead > 0:
        return CheckState.DIVERGED
    if behind > 0:
        return CheckState.BEHIND
    if ahead > 0:
        return CheckState.AHEAD
    return CheckState.UP_TO_DATE


def _is_dirty(runner: RunGit, repo: Path) -> bool:
    """True si el worktree tiene cambios (duda => abortar, jamas mutar)."""
    res = runner(["status", "--porcelain"], cwd=repo)
    return res.code != 0 or bool(res.out.strip())


def _downgrade_blocked(check: UpdateCheck, log_path: Path) -> bool:
    """Gate de monotonicidad: floor = max(version local, max_seen journal)."""
    if check.remote_version is None:
        return True
    floor = max(check.local_version, max_seen_version(log_path))
    return check.remote_version < floor


def apply_update(
    check: UpdateCheck,
    *,
    repo: Path,
    log_path: Path,
    run_git: RunGit | None = None,
    allow_downgrade: bool = False,
    downgrade_justification: str = "",
) -> UpdateResult:
    """Aplica el update con guards anti-reversion + WAL de log (spec).

    Nunca lanza: degrada a Action.* registrandolo. Solo muta el worktree
    en los caminos UPDATED / DOWNGRADE_FORCED (merge --ff-only limpio).
    """
    runner = run_git or default_run_git
    temprano = _EARLY_ACTIONS.get(check.state)
    if temprano is not None:
        return _finish(temprano, check, log_path, detail=check.detail or check.state.value)
    if check.state is CheckState.DIVERGED:
        return _finish(
            Action.DIVERGED,
            check,
            log_path,
            detail="commits locales no empujados + remoto avanzado; nunca reset",
        )
    return _apply_decision(
        check, repo, log_path, runner, allow_downgrade, downgrade_justification
    )


def _apply_decision(
    check: UpdateCheck,
    repo: Path,
    log_path: Path,
    runner: RunGit,
    allow: bool,
    justification: str,
) -> UpdateResult:
    """Guards (noop/dirty/gate) antes del merge ff-only."""
    if check.state is not CheckState.BEHIND:
        return _finish(Action.NOOP, check, log_path, detail="sin commits nuevos en remoto")
    if _is_dirty(runner, repo):
        return _finish(
            Action.DIRTY_WORKTREE, check, log_path, detail="worktree sucio; abortar sin stash"
        )
    bloqueado = _downgrade_blocked(check, log_path)
    if bloqueado and not (allow and justification.strip()):
        return _finish(
            Action.BLOCKED_DOWNGRADE,
            check,
            log_path,
            detail=(
                f"remote {fmt_version(check.remote_version or NO_VERSION)} < floor; "
                f"local {fmt_version(check.local_version)} "
                f"max_seen {fmt_version(max_seen_version(log_path))}"
            ),
        )
    return _merge(check, repo, log_path, runner, forced=bloqueado, justification=justification)


def _merge(
    check: UpdateCheck,
    repo: Path,
    log_path: Path,
    runner: RunGit,
    *,
    forced: bool,
    justification: str,
) -> UpdateResult:
    """WAL: intento registrado ANTES del merge, resultado DESPUES."""
    _append_attempt(check, log_path, justification if forced else "")
    merged = runner(["merge", "--ff-only", "FETCH_HEAD"], cwd=repo)
    if merged.code != 0:
        return _finish(
            Action.FAILED, check, log_path, detail=merged.err or "merge --ff-only rechazado"
        )
    return _finish(
        Action.DOWNGRADE_FORCED if forced else Action.UPDATED,
        check,
        log_path,
        detail="merge --ff-only aplicado",
        changed=True,
        to_version=check.remote_version or check.local_version,
        to_commit=_head(runner, repo),
        justification=justification if forced else "",
    )


def _append_attempt(check: UpdateCheck, log_path: Path, justification: str) -> None:
    """Entrada WAL 'attempt' previa a la mutacion (crash-safe)."""
    append_log(
        {
            "ts": datetime.now(UTC).isoformat(),
            "machine": platform.node(),
            "os": sys.platform,
            "action": "attempt",
            "from_version": fmt_version(check.local_version),
            "to_version": fmt_version(check.remote_version or check.local_version),
            "from_commit": check.local_commit,
            "to_commit": check.remote_commit,
            "remote_url": check.remote_url,
            "detail": "intencion de merge --ff-only",
            "justification": justification,
        },
        log_path,
    )


def _journal_entry(result: UpdateResult, check: UpdateCheck) -> dict:
    """Entrada JSON final del journal a partir del resultado construido."""
    return {
        "ts": datetime.now(UTC).isoformat(),
        "machine": platform.node(),
        "os": sys.platform,
        "action": result.action.value,
        "from_version": fmt_version(result.from_version),
        "to_version": fmt_version(result.to_version),
        "from_commit": result.from_commit,
        "to_commit": result.to_commit,
        "remote_url": check.remote_url,
        "detail": result.detail,
        "justification": result.justification,
    }


def _finish(
    action: Action,
    check: UpdateCheck,
    log_path: Path,
    *,
    detail: str,
    changed: bool = False,
    to_version: tuple[int, ...] | None = None,
    to_commit: str = "",
    justification: str = "",
) -> UpdateResult:
    """Construye UpdateResult y persiste la entrada final en el journal."""
    result = UpdateResult(
        action=action,
        changed=changed,
        detail=detail,
        from_version=check.local_version,
        to_version=to_version if to_version is not None else check.local_version,
        from_commit=check.local_commit,
        to_commit=to_commit or check.local_commit,
        justification=justification,
    )
    append_log(_journal_entry(result, check), log_path)
    return result
