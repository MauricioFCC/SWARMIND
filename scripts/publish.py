"""Publica el repo: push de la rama + propagación verificada al global.

Cierra el ciclo que antes se hacía a mano (commit → `git push` →
`sync_opencode_global.py` → comprobar). Aborta si el árbol está sucio para no
publicar un estado no reproducible.

Pasos:

1. ``git status --porcelain`` debe estar vacío (si no, commit primero).
2. ``git push`` (con ``-u origin <branch>`` si no hay upstream).
3. ``scripts/sync_opencode_global.py`` (cerebro + motor).
4. ``scripts/verify_global_sync.py --quiet`` (falla si hay drift).

Uso:

    python scripts/publish.py --dry-run
    python scripts/publish.py
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PYTHON = sys.executable


def is_clean(porcelain: str) -> bool:
    """True si ``git status --porcelain`` no reporta cambios.

    Args:
        porcelain: Salida cruda de ``git status --porcelain``.

    Returns:
        True si no hay líneas (árbol limpio).
    """
    return not porcelain.strip()


def push_args(branch: str, has_upstream: bool) -> list[str]:
    """Argumentos de ``git push`` según exista upstream.

    Args:
        branch: Rama actual.
        has_upstream: True si la rama ya sigue a un remoto.

    Returns:
        Lista de argumentos para ``git``.
    """
    if has_upstream:
        return ["push"]
    return ["push", "-u", "origin", branch]


def _git(*args: str) -> subprocess.CompletedProcess[str]:
    """Ejecuta git en la raíz del repo (sin lanzar excepción)."""
    return subprocess.run(
        ["git", *args],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )


def _run(script: str, *args: str) -> subprocess.CompletedProcess[str]:
    """Ejecuta un script del repo con el Python actual."""
    return subprocess.run(
        [PYTHON, str(ROOT / "scripts" / script), *args],
        cwd=ROOT,
        text=True,
        check=False,
    )


def main(argv: list[str] | None = None) -> int:
    """Entrypoint de publicación.

    Args:
        argv: Argumentos CLI (``None`` usa ``sys.argv``).

    Returns:
        Exit code (0 = publicado y propagado, 1 = bloqueado/fallo).
    """
    parser = argparse.ArgumentParser(description="Push + sync global verificado")
    parser.add_argument("--dry-run", action="store_true", help="solo muestra el plan")
    parser.add_argument("--skip-verify", action="store_true", help="no verifica post-sync")
    parser.add_argument("--quiet", action="store_true", help="sin salida de scripts")
    args = parser.parse_args(argv)

    status = _git("status", "--porcelain")
    if status.returncode != 0:
        print(f"publish | WHAT=git status fallo | WHY={status.stderr.strip()}", file=sys.stderr)
        return 1
    if not is_clean(status.stdout):
        print(
            "publish | WHAT=arbol_sucio | WHY=hay cambios sin commitear | "
            "WHERE=publish | ACCION: commit antes de publicar",
            file=sys.stderr,
        )
        print(status.stdout.strip(), file=sys.stderr)
        return 1

    branch = _git("rev-parse", "--abbrev-ref", "HEAD").stdout.strip()
    has_upstream = (
        _git("rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}").returncode == 0
    )
    push = push_args(branch, has_upstream)
    print(f"publish: rama={branch} push={' '.join(push)}")

    if args.dry_run:
        print("publish: dry-run -> sync + verify (no se ejecutan)")
        return 0

    result = _git(*push)
    if result.returncode != 0:
        print(
            f"publish | WHAT=push_fallo | WHY={result.stderr.strip()[:500]} | "
            "WHERE=publish",
            file=sys.stderr,
        )
        return 1

    sync_result = _run("sync_opencode_global.py", "--quiet") if args.quiet else _run(
        "sync_opencode_global.py"
    )
    if sync_result.returncode != 0:
        print("publish | WHAT=sync_fallo | WHERE=sync_opencode_global", file=sys.stderr)
        return 1

    if not args.skip_verify:
        verify = _run("verify_global_sync.py", "--quiet")
        if verify.returncode != 0:
            print(
                "publish | WHAT=drift_post_sync | WHY=global != repo | "
                "WHERE=verify_global_sync",
                file=sys.stderr,
            )
            return 1

    print("publish OK: push + sync + verify. Reinicia opencode para recargar config.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
