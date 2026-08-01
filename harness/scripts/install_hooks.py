"""
install_hooks.py â€” Git pre-commit hook installer for the Swarmind Harness.

Installs a **self-contained local** pre-commit hook that runs the
end-of-iteration pipeline. The hook is project-local and does NOT
depend on any external Swarmind template path or symlink.

Usage:
    python harness/scripts/install_hooks.py --install     # Install hook
    python harness/scripts/install_hooks.py --uninstall   # Uninstall hook
    python harness/scripts/install_hooks.py --status      # Show hook status
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import shutil
import stat
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

# â”€â”€ Paths (relative to this installer script) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
_HERE = Path(__file__).resolve().parent            # harness/scripts/
_HARNESS_ROOT = _HERE.parent                        # harness/
_PROJECT_ROOT = _HARNESS_ROOT.parent                # project root (where .git lives)

_HOOKS_DIR = _PROJECT_ROOT / ".git" / "hooks"
_HOOK_PATH = _HOOKS_DIR / "pre-commit"
_BACKUP_PATH = _HOOKS_DIR / "pre-commit.Swarmind.bak"
_STATUS_PATH = _HARNESS_ROOT / "db" / ".hook_status.json"

# â”€â”€ Self-contained hook template â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# This script is written into .git/hooks/pre-commit.
# It uses ONLY stdlib, resolves paths relative to __file__, and is
# fully autonomous â€” no external template dependency.
_LOCAL_HOOK_TEMPLATE = r'''#!/bin/sh
# PRE-COMMIT HOOK -- Auto-generado por Swarmind Harness (portable, ADR-0035)
# 1) QA rapido (pipeline end_of_iteration --pre-commit --quick)
# 2) Sync global opencode (Opción A: SSOT en ~/.config/opencode) -- best effort
# Usa uv si esta disponible; fallback a python3 / python.
_HOOK_DIR="$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)"
_PIPELINE="$_HOOK_DIR/harness/scripts/end_of_iteration.py"
_SYNC="$_HOOK_DIR/scripts/sync_opencode_global.py"

_run_python() {
    if command -v uv >/dev/null 2>&1; then
        uv run python "$@"
    elif command -v python3 >/dev/null 2>&1; then
        python3 "$@"
    else
        python "$@"
    fi
}

if [ -f "$_PIPELINE" ]; then
    _run_python "$_PIPELINE" --pre-commit --quick
    _rc=$?
    if [ "$_rc" -ne 0 ]; then
        exit "$_rc"
    fi
fi

# Sync global opencode: no bloquea el commit si falla (best effort)
if [ -f "$_SYNC" ]; then
    _run_python "$_SYNC" --quiet >/dev/null 2>&1 || echo "[pre-commit] aviso: sync opencode global fallo (commit continuo)"
fi

echo "[pre-commit] OK"
exit 0
'''


# â”€â”€ ANSI colours â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
_RED = "\033[91m"
_GREEN = "\033[92m"
_YELLOW = "\033[93m"
_CYAN = "\033[96m"
_BOLD = "\033[1m"
_RESET = "\033[0m"


def _ok(msg: str) -> str:
    return f"{_GREEN}{msg}{_RESET}"


def _warn(msg: str) -> str:
    return f"{_YELLOW}{msg}{_RESET}"


def _err(msg: str) -> str:
    return f"{_RED}{msg}{_RESET}"


def _bold(msg: str) -> str:
    return f"{_BOLD}{msg}{_RESET}"


def _cyan(msg: str) -> str:
    return f"{_CYAN}{msg}{_RESET}"


def _print(*args, **kwargs) -> None:
    """Print with Unicode fallback (replaces non-encodable chars)."""
    try:
        print(*args, **kwargs)
    except UnicodeEncodeError:
        safe_args = []
        for arg in args:
            if isinstance(arg, str):
                arg = (arg.replace("\u2014", "--")
                       .replace("\u2013", "-")
                       .replace("\u2500", "-")
                       .replace("\u2502", "|")
                       .replace("\u2514", "+")
                       .replace("\u250c", "+")
                       .replace("\u2510", "+")
                       .replace("\u2518", "+")
                       .replace("\u2018", "'")
                       .replace("\u2019", "'")
                       .replace("\u201c", '"')
                       .replace("\u201d", '"')
                       .replace("\u2026", "...")
                       .replace("\u00a0", " "))
            safe_args.append(arg)
        print(*safe_args, **kwargs)


# â”€â”€ Helpers â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def _is_git_repo() -> bool:
    """Check if PROJECT_ROOT is inside a git repository."""
    return (_PROJECT_ROOT / ".git").is_dir()


def _save_status(installed: bool, timestamp: str = "") -> None:
    """Persist hook installation metadata to JSON (informational only).

    Portabilidad (ADR-0035): hook_path se guarda RELATIVO al proyecto para
    no exponer rutas absolutas ni el nombre de usuario de la máquina.
    """
    status_dir = _STATUS_PATH.parent
    status_dir.mkdir(parents=True, exist_ok=True)
    status = {
        "installed": installed,
        "timestamp": timestamp or datetime.now(timezone.utc).isoformat(),
        "hook_path": os.path.relpath(_HOOK_PATH, _PROJECT_ROOT),
    }
    with open(_STATUS_PATH, "w", encoding="utf-8") as f:
        json.dump(status, f, indent=2)


def _load_status() -> dict:
    """Load hook installation metadata. Returns empty-safe dict."""
    if not _STATUS_PATH.exists():
        return {"installed": False, "timestamp": "", "hook_path": ""}
    try:
        with open(_STATUS_PATH, "r", encoding="utf-8") as f:
            status = json.load(f)
        status.setdefault("hook_path", "")
        return status
    except (json.JSONDecodeError, Exception):  # noqa: BLE001
        return {"installed": False, "timestamp": "", "hook_path": ""}


def _is_hook_ours(hook_path: Path = _HOOK_PATH) -> bool:
    """Return True if the existing hook was generated by this installer."""
    if not hook_path.exists():
        return False
    try:
        content = hook_path.read_text(encoding="utf-8", errors="ignore")
        return "PRE-COMMIT HOOK" in content
    except Exception:  # noqa: BLE001
        return False


def _is_legacy_hook(hook_path: Path = _HOOK_PATH) -> bool:
    """Return True if the existing hook is a legacy (template-bound) hook.

    Legacy hooks contain the *old* ``Swarmind Harness`` marker but do
    **not** contain the new ``PRE-COMMIT HOOK`` marker.
    """
    if not hook_path.exists():
        return False
    try:
        content = hook_path.read_text(encoding="utf-8", errors="ignore")
        return "Swarmind Harness" in content and "PRE-COMMIT HOOK" not in content
    except Exception:  # noqa: BLE001
        return False


def _prompt_yes_no(prompt: str, default: str = "Y") -> bool:
    """Prompt interactively for a yes/no answer."""
    suffix = " [Y/n]: " if default == "Y" else " [y/N]: "
    try:
        answer = input(prompt + suffix).strip().lower()
        if default == "Y":
            return answer in ("", "y", "yes")
        else:
            return answer in ("y", "yes")
    except (EOFError, KeyboardInterrupt):
        return default == "Y"


# â”€â”€ Public API â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def install_hook() -> bool:
    """Install the self-contained local pre-commit hook.

    Steps:
        1. Verifies the project is a git repository.
        2. Detects legacy hooks (pre-v2, template-bound) and offers migration.
        3. Backs up any existing hook.
        4. Writes the new autonomous hook script.
        5. Persists installation metadata to ``.hook_status.json``.
    """
    if not _is_git_repo():
        _print(f"  {_err('[ERROR]')} No es un repositorio Git: {_PROJECT_ROOT}")
        return False

    _HOOKS_DIR.mkdir(parents=True, exist_ok=True)

    # â”€â”€ Backup existing hook / legacy migration â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    if _HOOK_PATH.exists():
        if _is_legacy_hook():
            _print()
            _print(f"  {_warn('[!]')} Se detectÃ³ un hook legacy apuntando al template Swarmind.")
            _print(f"  {_warn('[!]')} Este hook deja de funcionar si el template se mueve o elimina.")
            _print()
            if _prompt_yes_no("  Â¿Migrar a hook local autocontenido?", default="Y"):
                _print(f"  {_ok('[OK]')} Migrando a hook local...")
                if not _BACKUP_PATH.exists():
                    shutil.copy2(str(_HOOK_PATH), str(_BACKUP_PATH))
                    _print(f"  {_ok('[OK]')} Hook legacy respaldado: {_BACKUP_PATH}")
            else:
                _print(f"  {_warn('[!]')} Cancelado por el usuario.")
                return False
        else:
            # Standard backup for non-legacy hooks
            if not _BACKUP_PATH.exists():
                shutil.copy2(str(_HOOK_PATH), str(_BACKUP_PATH))
                _print(f"  {_ok('[OK]')} Hook anterior respaldado: {_BACKUP_PATH}")
            else:
                _print(f"  {_warn('[WARN]')} Backup ya existe: {_BACKUP_PATH}")
    else:
        _print(f"  {_ok('[OK]')} No habÃ­a hook previo.")

    # â”€â”€ Write the new self-contained hook â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    try:
        with open(_HOOK_PATH, "w", encoding="utf-8", newline="\n") as f:
            f.write(_LOCAL_HOOK_TEMPLATE)
        if sys.platform != "win32":
            st = os.stat(_HOOK_PATH)
            os.chmod(_HOOK_PATH, st.st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)

        _save_status(True)
        _print()
        _print(f"  {_ok('[OK]')} Hook LOCAL instalado: {_HOOK_PATH}")
        _print()
        _print(f"  {_bold('Hook autocontenido â€” no depende de rutas externas.')}")
        _print(f"  {_bold('En cada commit ejecutarÃ¡ (modo rÃ¡pido):')}")
        _print("    harness/scripts/end_of_iteration.py --pre-commit --quick")
        _print()
        _print("  Para saltar el hook: git commit --no-verify")
        return True
    except Exception as exc:  # noqa: BLE001
        _print(f"  {_err('[ERROR]')} No se pudo escribir el hook: {exc}")
        return False


def uninstall_hook() -> bool:
    """Uninstall the pre-commit hook and restore backup if available."""
    if not _is_git_repo():
        _print(f"  {_err('[ERROR]')} No es un repositorio Git: {_PROJECT_ROOT}")
        return False

    if not _HOOK_PATH.exists() and not _BACKUP_PATH.exists():
        _print(f"  {_warn('[WARN]')} No hay hook instalado ni backup.")
        _save_status(False)
        return True

    is_ours = _is_hook_ours()

    # Restore backup if present
    if _BACKUP_PATH.exists():
        shutil.copy2(str(_BACKUP_PATH), str(_HOOK_PATH))
        _BACKUP_PATH.unlink()
        _print(f"  {_ok('[OK]')} Hook original restaurado desde backup.")
    elif is_ours:
        _HOOK_PATH.unlink()
        _print(f"  {_ok('[OK]')} Hook eliminado (no habÃ­a backup previo).")
    else:
        _print(f"  {_warn('[WARN]')} El hook actual no fue instalado por Swarmind Harness.")
        _print(f"  {_warn('[WARN]')} No se modificÃ³. Backup disponible: {_BACKUP_PATH}")
        return False

    _save_status(False)
    _print(f"  {_ok('[OK]')} Hook desinstalado exitosamente.")
    return True


def _get_last_run_info() -> str | None:
    """Try to obtain the last hook execution timestamp."""
    # 1. Check status file
    status = _load_status()
    if status.get("last_run"):
        return status["last_run"]

    # 2. Fallback: git reflog for hook file changes
    try:
        result = subprocess.run(
            ["git", "log", "--oneline", "-1", "--format=%ci", "--", ".git/hooks/pre-commit"],
            capture_output=True, text=True, timeout=10, cwd=str(_PROJECT_ROOT), check=False,
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
    except Exception as _exc:  # noqa: BLE001
        logger.warning("install_hooks: %s", _exc)
    return None


def _classify_hook() -> str:
    """Classify the current hook file: local | legacy | foreign | none."""
    if not _HOOK_PATH.exists():
        return "none"
    try:
        content = _HOOK_PATH.read_text(encoding="utf-8", errors="ignore")
        if "PRE-COMMIT HOOK" in content:
            return "local"
        if "Swarmind Harness" in content:
            return "legacy"
        return "foreign"
    except Exception:  # noqa: BLE001
        return "foreign"


def show_status() -> None:
    """Display the current hook installation status."""
    status = _load_status()
    installed = status.get("installed", False)
    hook_type = _classify_hook()
    backup_exists = _BACKUP_PATH.exists()
    is_git = _is_git_repo()

    _print()
    _print(f"  {_bold('Estado del Hook Pre-Commit')}")
    _print(f"  {'â”€' * 50}")

    if not is_git:
        _print(f"  {_err('[ERROR]')} No es un repositorio Git.")
        return

    if hook_type == "local":
        _print(f"  Estado:   {_ok('INSTALADO (LOCAL)')}")
    elif hook_type == "legacy":
        _print(f"  Estado:   {_warn('INSTALADO (LEGACY)')}")
        _print(f"  {_warn('  -> Migrar: python harness/scripts/install_hooks.py --install')}")
    elif hook_type == "foreign":
        _print(f"  Estado:   {_warn('OTRO HOOK')} (no de Swarmind Harness)")
    else:
        _print(f"  Estado:   {_cyan('NO INSTALADO')}")

    _print(f"  Ruta:     {_HOOK_PATH}")
    _print(f"  Backup:   {'SI' if backup_exists else 'NO'}")
    _print(f"  Git repo: {'SI' if is_git else 'NO'}")

    last_run = _get_last_run_info()
    if last_run:
        _print(f"  Ãšltimo:   {last_run}")
    elif installed:
        _print(f"  Ãšltimo:   {_warn('Sin ejecuciones registradas')}")

    last_status_update = status.get("timestamp", "")
    if last_status_update:
        try:
            dt = datetime.fromisoformat(last_status_update)
            _print(f"  Instalado: {dt.strftime('%Y-%m-%d %H:%M:%S')}")
        except (ValueError, TypeError):
            pass

    _print()
    _print("  Comandos:")
    _print("    python harness/scripts/install_hooks.py --install")
    _print("    python harness/scripts/install_hooks.py --uninstall")
    _print("    python harness/scripts/install_hooks.py --status")
    _print()


def main() -> None:
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Install/Uninstall/Check Git pre-commit hook for Swarmind Harness",
    )
    parser.add_argument("--install", action="store_true", help="Install the pre-commit hook")
    parser.add_argument("--uninstall", action="store_true", help="Uninstall the pre-commit hook")
    parser.add_argument("--status", action="store_true", help="Show hook installation status")
    args = parser.parse_args()

    if args.install:
        install_hook()
    elif args.uninstall:
        uninstall_hook()
    elif args.status:
        show_status()
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
