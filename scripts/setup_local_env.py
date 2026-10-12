#!/usr/bin/env python3
"""setup_local_env.py - persiste las env vars del harness local (multi-SO).

WHAT: escribe las variables que regulan el worker local (``SWARMIND_REQUIRE_LOCAL``)
y la raiz de modelos (``SWARMIND_LLAMA_DIR``) en el alcance persistente de cada SO,
para que el sistema sea configurable en Windows, macOS y Linux sin tocar codigo.
WHY: el harness lee ``os.environ`` (12-Factor); sin esto, cada maquina debia
recordar setear las vars a mano o quedaba el default solo en codigo. Politica
LOCAL SOLO TRIVIAL (default ``=0``): el local (mimo) atiende small_model
(tareas triviales); el oraculo cloud resuelve el trabajo real porque los LLM
locales carecen de calidad frontier. ``=1`` vuelve a exigir local SIEMPRE.
WHERE: ``scripts/setup_local_env.py`` (CLI); documentacion en
``harness/model_router/local_models.yaml`` (cabecera multi-SO).

Uso:
    python scripts/setup_local_env.py                     # setea default (idempotente)
    python scripts/setup_local_env.py --llama-dir /x/llama
    python scripts/setup_local_env.py --dry-run           # solo muestra acciones
    python scripts/setup_local_env.py --unset             # retira lo persistido

Alcance persistente por SO:
    Windows: ``setx VAR valor`` a nivel de usuario (procesos nuevos lo heredan).
    POSIX:   bloque con marcadores en ``~/.bashrc``, ``~/.zshrc`` y ``~/.zprofile``
             (los que existan); re-ejecutar no duplica; ``--unset`` lo retira.
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path

#: Variables que este script garantiza (el resto las lee el harness por default).
REQUIRE_LOCAL = "SWARMIND_REQUIRE_LOCAL"
LLAMA_DIR = "SWARMIND_LLAMA_DIR"

_BLOCK_START = "# >>> SWARMIND start >>>"
_BLOCK_END = "# <<< SWARMIND end <<<"
_BLOCK_RE = re.compile(
    rf"^{re.escape(_BLOCK_START)}.*?^{re.escape(_BLOCK_END)}\s*$",
    re.MULTILINE | re.DOTALL,
)


def _block(vars_dict: dict[str, str]) -> str:
    """Genera el bloque exportable POSIX con marcadores idempotentes.

    Args:
        vars_dict: Variables a persistir (nombre -> valor).

    Returns:
        Texto del bloque, terminado en salto de linea.
    """
    lines = [_BLOCK_START]
    lines.extend(f'export {name}="{value}"' for name, value in sorted(vars_dict.items()))
    lines.append(_BLOCK_END)
    return "\n".join(lines) + "\n"


def _rc_candidates(home: Path) -> list[Path]:
    """Devuelve los rc-files POSIX existentes (bash/zsh/profile).

    Args:
        home: Directorio HOME (inyectable para tests).

    Returns:
        Rutas de rc-files que ya existen en disco.
    """
    names = (".bashrc", ".zshrc", ".zprofile")
    return [home / name for name in names if (home / name).is_file()]


def _apply_rc(path: Path, block: str, dry_run: bool, unset: bool) -> str:
    """Inserta (o retira) el bloque SWARMIND en un rc-file, idempotente.

    Si el bloque ya existe se reemplaza en sitio (nunca se duplica); si no,
    se anade al final. ``unset`` lo elimina por completo.

    Args:
        path: Ruta del rc-file.
        block: Bloque exportable (ignorado si ``unset``).
        dry_run: Si True, no escribe; devuelve lo que se haria.
        unset: Si True, elimina el bloque existente.

    Returns:
        Descripcion de la accion tomada (o simulada).
    """
    text = path.read_text(encoding="utf-8") if path.exists() else ""
    if unset:
        if not _BLOCK_RE.search(text):
            return f"sin bloque en {path}: nada que retirar"
        verb = "retiraria" if dry_run else "retirado"
        return verb if dry_run else _write_rc(path, _BLOCK_RE.sub("", text), "retirado")
    if _BLOCK_RE.search(text):
        new_text = _BLOCK_RE.sub(block, text)
    else:
        new_text = text.rstrip() + ("\n\n" if text else "") + block.rstrip("\n") + "\n"
    return ("actualizaria bloque" if dry_run else _write_rc(path, new_text, "actualizado")) + f" en {path}"


def _write_rc(path: Path, content: str, verb: str) -> str:
    """Escribe el rc-file y reporta la accion (WHAT+WHY+WHERE).

    Args:
        path: Ruta del archivo.
        content: Contenido final.
        verb: Verbo de la accion (retirado/actualizado).

    Returns:
        Mensaje descriptivo.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return f"{verb} bloque en {path}"


def _apply_windows(vars_dict: dict[str, str], dry_run: bool, unset: bool) -> list[str]:
    """Persiste (o retira) las vars via ``setx`` a nivel de usuario (Windows).

    Args:
        vars_dict: Variables a setear (ignoradas si ``unset``).
        dry_run: Si True, solo reporta el comando.
        unset: Si True, borra las vars persistidas (valor vacio).

    Returns:
        Lista de acciones realizadas o simuladas.
    """
    actions: list[str] = []
    for name, value in sorted(vars_dict.items()):
        final = "" if unset else value
        cmd = f'setx {name} "{final}"'
        if dry_run:
            actions.append(f"simularia: {cmd}")
            continue
        subprocess.run(["setx", name, final], check=True, capture_output=True)
        actions.append(f"{name} persistido (setx)")
    return actions


def main() -> int:
    """CLI: persiste o retira la config local del harness (multi-SO)."""
    parser = argparse.ArgumentParser(description="Persiste env del harness local (multi-SO)")
    parser.add_argument("--llama-dir", default=os.getenv(LLAMA_DIR, ""),
                        help=f"Ruta raiz de llama (default: ${LLAMA_DIR} actual)")
    parser.add_argument("--dry-run", action="store_true", help="Solo mostrar acciones")
    parser.add_argument("--unset", action="store_true", help="Retirar lo persistido")
    args = parser.parse_args()

    vars_dict = {REQUIRE_LOCAL: "0"}
    if args.llama_dir and not args.unset:
        vars_dict[LLAMA_DIR] = args.llama_dir

    if sys.platform == "win32":
        for action in _apply_windows(vars_dict, args.dry_run, args.unset):
            print(f"  [win] {action}")
        return 0

    home = Path(os.path.expanduser("~"))
    block = _block(vars_dict)
    rc_files = _rc_candidates(home)
    if not rc_files and not args.dry_run:
        rc_files = [home / ".bashrc"]
    for path in rc_files:
        print(f"  [posix] {_apply_rc(path, block, args.dry_run, args.unset)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())