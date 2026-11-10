"""Auto-actualizacion de la instalacion GLOBAL de opencode (copia sin ``.git``).

WHAT: la instalacion que opencode carga (``~/.config/opencode``) es una COPIA
generada por ``publish.py`` -> ``sync_opencode_global.py``, no un clon. Sin
``.git`` el motor de ``core.py`` no puede hacer ``fetch`` ni ``merge``. Este
modulo añade el camino para esa instalacion: ``.swarmind/install.json`` sella
origen/rama/commit/version y ``check_install`` compara el sello contra el
remoto con ``git ls-remote``; ``apply_install`` clona la rama en un temporal y
re-sincroniza el global con el script oficial.

WHY: verificacion 2026-11-10 — ``self_update.py --check`` contra el global
terminaba en ``exit 2`` ("sin fuente de version"): el binario nativo y el
cerebro se instalaban pero nunca se actualizaban solos.

WHERE: ``scripts/sync_opencode_global.py`` (escribe el sello), ``scripts/
self_update.py`` y ``!update`` (consultan/aplican), ``run_support`` (aviso).

Invariantes: nunca lanza fuera de :func:`apply_install` (que degrada a un
resultado con ``action="failed"``); el sello es JSON versionado; jamas se
ejecuta un source/branch que no valide (sin inyeccion de flags ni shells).
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
import tempfile
import tomllib
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from harness.self_update.core import CheckState, GitResult, RunGit, default_run_git
from harness.self_update.versions import parse_semver

logger = logging.getLogger(__name__)

#: Nombre del sello dentro de ``<install_dir>/.swarmind/``.
STAMP_FILE = "install.json"
#: Version del formato del sello (invalida formatos viejos).
STAMP_VERSION = 1

_CLONE_TIMEOUT = 300
_SYNC_REL = Path("scripts") / "sync_opencode_global.py"
_SOURCE_PREFIXES = ("https://", "http://", "git@", "ssh://", "file://")
_BRANCH_CHARS = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._/-")


@dataclass(frozen=True)
class InstallStamp:
    """Sello de la copia instalada: de donde vino y en que commit esta.

    Args:
        source: URL del repositorio de origen (validada antes de usar).
        branch: Rama instalada.
        commit: SHA del commit sincronizado.
        version: Version de ``pyproject.toml`` en ese commit (puede ser "").
        synced_at: ISO-8601 UTC de la sincronizacion.
    """

    source: str
    branch: str
    commit: str
    version: str = ""
    synced_at: str = ""

    def to_dict(self) -> dict[str, str | int]:
        """Serializa el sello al formato JSON versionado."""
        return {
            "stamp_version": STAMP_VERSION,
            "source": self.source,
            "branch": self.branch,
            "commit": self.commit,
            "version": self.version,
            "synced_at": self.synced_at,
        }


@dataclass(frozen=True)
class InstallCheck:
    """Estado de la copia instalada frente al remoto (sin mutar nada)."""

    state: CheckState
    local_commit: str = ""
    remote_commit: str = ""
    source: str = ""
    branch: str = ""
    version: str = ""
    detail: str = ""


@dataclass(frozen=True)
class InstallResult:
    """Resultado de ``apply_install`` (nunca lanza)."""

    action: str
    changed: bool = False
    detail: str = ""
    from_commit: str = ""
    to_commit: str = ""
    from_version: str = ""
    to_version: str = ""


def stamp_path(install_dir: Path) -> Path:
    """Ruta del sello de instalacion (``.swarmind/install.json``).

    Args:
        install_dir: Directorio de la instalacion global.

    Returns:
        Ruta del JSON del sello.
    """
    return Path(install_dir) / ".swarmind" / STAMP_FILE


def read_stamp(install_dir: Path) -> InstallStamp | None:
    """Lee el sello (``None`` si falta, esta corrupto o es de otro formato).

    Args:
        install_dir: Directorio de la instalacion global.

    Returns:
        Sello valido o ``None`` (nunca lanza).
    """
    try:
        data = json.loads(stamp_path(install_dir).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict) or data.get("stamp_version") != STAMP_VERSION:
        return None
    source, branch, commit = data.get("source"), data.get("branch"), data.get("commit")
    if not (isinstance(source, str) and isinstance(branch, str) and isinstance(commit, str)):
        return None
    return InstallStamp(
        source=source,
        branch=branch,
        commit=commit,
        version=str(data.get("version") or ""),
        synced_at=str(data.get("synced_at") or ""),
    )


def write_stamp(install_dir: Path, stamp: InstallStamp) -> Path:
    """Escribe el sello en ``<install_dir>/.swarmind/install.json``.

    Args:
        install_dir: Directorio de la instalacion global.
        stamp: Sello a persistir.

    Returns:
        Ruta del sello escrito.

    Raises:
        OSError: Si no se puede crear el directorio o escribir el archivo.
    """
    destino = stamp_path(install_dir)
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(
        json.dumps(stamp.to_dict(), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return destino


def _version_at(repo: Path) -> str:
    """Version de ``pyproject.toml`` en ``repo`` ('' si falta o esta roto)."""
    try:
        data = tomllib.loads((repo / "pyproject.toml").read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError):
        return ""
    version = data.get("project", {}).get("version")
    return str(version) if version else ""


def stamp_from_repo(repo: Path, run_git: RunGit | None = None) -> InstallStamp | None:
    """Construye el sello leyendo origen/rama/commit del clon fuente.

    Args:
        repo: Raiz del clon SWARMIND (con ``.git``).
        run_git: Runner DI (default: git real).

    Returns:
        Sello listo para escribir, o ``None`` si no hay origin/commit/rama.
    """
    runner = run_git or default_run_git
    url = runner(["remote", "get-url", "origin"], cwd=repo)
    head = runner(["rev-parse", "HEAD"], cwd=repo)
    branch = runner(["rev-parse", "--abbrev-ref", "HEAD"], cwd=repo)
    if url.code != 0 or head.code != 0 or not url.out or not head.out:
        return None
    rama = branch.out if branch.code == 0 and branch.out else "main"
    return InstallStamp(
        source=url.out.strip(),
        branch=rama,
        commit=head.out.strip(),
        version=_version_at(repo),
        synced_at=datetime.now(UTC).isoformat(),
    )


def _valid_source(source: str) -> bool:
    """True si el origen es una URL git conocida y no parece un flag.

    Args:
        source: URL candidata del remoto.

    Returns:
        True si empieza por un prefijo permitido y no contiene espacios.
    """
    limpio = source.strip()
    if not limpio or limpio.startswith("-") or any(c.isspace() for c in limpio):
        return False
    return limpio.startswith(_SOURCE_PREFIXES)


def _valid_branch(branch: str) -> bool:
    """True si la rama solo usa caracteres seguros de refname."""
    return bool(branch) and not branch.startswith("-") and set(branch) <= _BRANCH_CHARS


def _degraded(state: CheckState, stamp: InstallStamp | None, detail: str) -> InstallCheck:
    """``InstallCheck`` degradado (offline/no_git/sin sello)."""
    return InstallCheck(
        state=state,
        local_commit=stamp.commit if stamp else "",
        source=stamp.source if stamp else "",
        branch=stamp.branch if stamp else "",
        version=stamp.version if stamp else "",
        detail=detail,
    )


def _remote_head(runner: RunGit, install_dir: Path, stamp: InstallStamp) -> GitResult:
    """SHA del tip remoto via ``git ls-remote`` (sin clonar)."""
    return runner(
        ["ls-remote", "--heads", stamp.source, f"refs/heads/{stamp.branch}"],
        cwd=install_dir,
    )


def check_install(install_dir: Path, run_git: RunGit | None = None) -> InstallCheck:
    """Compara el sello de la copia instalada contra el tip remoto.

    Args:
        install_dir: Directorio de la instalacion global.
        run_git: Runner DI (default: git real).

    Returns:
        ``InstallCheck`` con estado (nunca lanza).
    """
    stamp = read_stamp(install_dir)
    if stamp is None:
        return _degraded(CheckState.NO_GIT, None, "sin .swarmind/install.json")
    if not _valid_source(stamp.source) or not _valid_branch(stamp.branch):
        return _degraded(CheckState.NO_REMOTE, stamp, "sello con origen/rama invalido")
    runner = run_git or default_run_git
    res = _remote_head(runner, install_dir, stamp)
    if res.code == 127:
        return _degraded(CheckState.NO_GIT, stamp, res.err)
    if res.code != 0:
        return _degraded(CheckState.OFFLINE, stamp, res.err or "ls-remote fallo")
    sha = res.out.split()[0] if res.out.split() else ""
    if not sha:
        return _degraded(CheckState.NO_REMOTE, stamp, "rama no encontrada en el remoto")
    estado = CheckState.UP_TO_DATE if sha == stamp.commit else CheckState.BEHIND
    detalle = "sello al dia con el remoto" if estado is CheckState.UP_TO_DATE else "remoto avanzó"
    return InstallCheck(
        state=estado,
        local_commit=stamp.commit,
        remote_commit=sha,
        source=stamp.source,
        branch=stamp.branch,
        version=stamp.version,
        detail=detalle,
    )


def _failed(detail: str, stamp: InstallStamp | None = None) -> InstallResult:
    """``InstallResult`` de fallo con contexto del sello previo."""
    return InstallResult(
        action="failed",
        detail=detail,
        from_commit=stamp.commit if stamp else "",
        from_version=stamp.version if stamp else "",
    )


def _clone(runner: RunGit, stamp: InstallStamp, workspace: Path) -> Path | None:
    """Clona la rama en ``workspace/repo``; ``None`` si git falla."""
    destino = workspace / "repo"
    res = runner(
        ["clone", "--depth", "1", "--branch", stamp.branch, stamp.source, str(destino)],
        cwd=workspace,
        timeout=_CLONE_TIMEOUT,
    )
    if res.code != 0 or not destino.is_dir():
        logger.warning("apply_install: clone fallo (%s): %s", res.code, res.err[:300])
        return None
    return destino


def _run_sync(repo: Path, install_dir: Path, python: str) -> bool:
    """Ejecuta el sync oficial del clon hacia ``install_dir`` (sin shells)."""
    script = repo / _SYNC_REL
    if not script.is_file():
        logger.warning("apply_install: el clon no trae %s", _SYNC_REL)
        return False
    entorno = {**os.environ, "OPENCODE_GLOBAL_DIR": str(install_dir)}
    proc = subprocess.run(
        [python, str(script), "--quiet"],
        cwd=repo,
        env=entorno,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
        timeout=_CLONE_TIMEOUT,
    )
    if proc.returncode != 0:
        logger.warning("apply_install: sync fallo (%s): %s", proc.returncode, proc.stderr[:300])
        return False
    return True


def apply_install(
    install_dir: Path,
    *,
    run_git: RunGit | None = None,
    python: str | None = None,
) -> InstallResult:
    """Aplica el update de la copia instalada clonando el remoto.

    Args:
        install_dir: Directorio de la instalacion global.
        run_git: Runner DI (default: git real).
        python: Interprete para el sync (default: ``sys.executable``).

    Returns:
        ``InstallResult`` con ``action`` en
        ``updated|up_to_date|no_stamp|offline|no_git|failed`` (nunca lanza).
    """
    stamp = read_stamp(install_dir)
    if stamp is None:
        return _failed("sin sello .swarmind/install.json; ejecuta publish.py")
    if not _valid_source(stamp.source) or not _valid_branch(stamp.branch):
        return _failed("sello con origen/rama invalido", stamp)
    runner = run_git or default_run_git
    check = check_install(install_dir, run_git=runner)
    if check.state is CheckState.UP_TO_DATE:
        return InstallResult(action="up_to_date", detail=check.detail, from_commit=stamp.commit)
    if check.state is CheckState.NO_GIT:
        return _failed(f"git no disponible: {check.detail}", stamp)
    if check.state is CheckState.OFFLINE:
        return _failed(f"remoto inaccesible: {check.detail}", stamp)
    return _apply_clone(install_dir, stamp, check, runner, python or sys.executable)


def _apply_clone(
    install_dir: Path,
    stamp: InstallStamp,
    check: InstallCheck,
    runner: RunGit,
    python: str,
) -> InstallResult:
    """Clona, sincroniza y re-sella; limpia el temporal siempre."""
    with tempfile.TemporaryDirectory(prefix="swarmind-update-") as tmp:
        repo = _clone(runner, stamp, Path(tmp))
        if repo is None:
            return _failed("clone fallo", stamp)
        if not _run_sync(repo, Path(install_dir), python):
            return _failed("sync del clon fallo", stamp)
        head = runner(["rev-parse", "HEAD"], cwd=repo)
        nuevo = InstallStamp(
            source=stamp.source,
            branch=stamp.branch,
            commit=head.out.strip() if head.code == 0 else check.remote_commit,
            version=_version_at(repo) or stamp.version,
            synced_at=datetime.now(UTC).isoformat(),
        )
        write_stamp(install_dir, nuevo)
    return InstallResult(
        action="updated",
        changed=True,
        detail="clone + sync completados",
        from_commit=stamp.commit,
        to_commit=nuevo.commit,
        from_version=stamp.version,
        to_version=nuevo.version,
    )


def _notice_state_path(install_dir: Path) -> Path:
    """Ruta del state de cooldown del aviso (junto al sello)."""
    return Path(install_dir) / ".swarmind" / "update_notice.json"


def install_notice(
    install_dir: Path,
    *,
    cooldown_hours: float = 24.0,
    run_git: RunGit | None = None,
) -> str | None:
    """Aviso de update con cooldown para la copia instalada.

    Args:
        install_dir: Directorio de la instalacion global.
        cooldown_hours: Horas entre comprobaciones (``0`` anula el rate-limit).
        run_git: Runner DI (default: git real).

    Returns:
        Mensaje a mostrar o ``None`` (al dia, degradado, sin sello o cooldown).
    """
    try:
        return _next_notice(Path(install_dir), cooldown_hours, run_git)
    except Exception:
        logger.debug("install_notice degradado", exc_info=True)
        return None


def _next_notice(install_dir: Path, cooldown_hours: float, run_git: RunGit | None) -> str | None:
    """Flujo: cooldown -> check -> guardar state -> mensaje."""
    state_path = _notice_state_path(install_dir)
    try:
        state = json.loads(state_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        state = {}
    ahora = datetime.now(UTC).timestamp()
    ultimo = float(state.get("checked_epoch", 0.0)) if isinstance(state, dict) else 0.0
    if cooldown_hours > 0 and state and ahora - ultimo < cooldown_hours * 3600.0:
        return None
    check = check_install(install_dir, run_git=run_git)
    if check.state in (CheckState.NO_GIT, CheckState.OFFLINE, CheckState.NO_REMOTE):
        return None  # no se cachea el fallo: reintento pronto
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(
        json.dumps({"checked_epoch": ahora, "last_state": check.state.value}) + "\n",
        encoding="utf-8",
    )
    if check.state is not CheckState.BEHIND:
        return None
    local = parse_semver(check.version) if check.version else None
    version = f" (instalada {local})" if local else ""
    return (
        f"update disponible en {check.branch}: origin avanzo a "
        f"{check.remote_commit[:7]}{version}. Ejecuta: python scripts/self_update.py "
        f"--apply --repo {install_dir}"
    )
