"""Verifica que el global de OpenCode quedó idéntico a la SSOT del repo.

`sync_opencode_global.py` copia cerebro + motor, pero hasta ahora no había una
comprobación post-sync: un fallo silencioso (archivo nuevo no incluido, copia
parcial, digest distinto) solo se descubría al importar el global. Este script
compara por hash:

- motor: ``harness/`` (archivos raíz + paquetes de ``_HARNESS_INCLUDE``).
- cerebro: ``agents/``, ``skills/``, ``core/``, ``commands/`` y el registry.
- doctrina: ``AGENTS.md``.

Solo reporta **faltantes o divergentes** (los extras curados del global, como
agents/skills propios, son válidos y se ignoran).

Uso:

    python scripts/verify_global_sync.py
    python scripts/verify_global_sync.py --json
    python scripts/verify_global_sync.py --quiet   # solo exit code
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(1, str(Path(__file__).resolve().parent))

import sync_opencode_global as sync


def _is_comparable(path: Path) -> bool:
    """True si el archivo debe entrar en la comparación (misma política que sync)."""
    return (
        not sync._IGNORED_DIR_NAMES.intersection(path.parts)
        and not path.name.endswith(sync._IGNORED_SUFFIXES)
        and path.name not in sync._IGNORED_FILE_NAMES
    )


def _digest(path: Path) -> str:
    """sha256 de un archivo (integridad, no criptografía)."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def compare_tree(
    source: Path, target: Path, *, prefix: str = ""
) -> tuple[list[str], list[str]]:
    """Compara un árbol fuente contra su copia global.

    Args:
        source: Directorio de la SSOT.
        target: Directorio global equivalente.
        prefix: Prefijo para los mensajes (p. ej. ``harness/``).

    Returns:
        ``(faltantes, divergentes)`` con rutas relativas legibles.
    """
    missing: list[str] = []
    diverged: list[str] = []
    for path in sorted(source.rglob("*")):
        if not path.is_file() or not _is_comparable(path):
            continue
        relative = path.relative_to(source)
        label = f"{prefix}{relative.as_posix()}"
        destination = target / relative
        if not destination.is_file():
            missing.append(label)
        elif _digest(path) != _digest(destination):
            diverged.append(label)
    return missing, diverged


def verify() -> dict[str, list[str]]:
    """Ejecuta la comparación completa.

    Returns:
        ``{"missing": [...], "diverged": [...]}`` (vacío = propagación sana).
    """
    missing: list[str] = []
    diverged: list[str] = []

    # Archivos raíz del paquete harness (se comparan uno a uno).
    for filename in sync._HARNESS_FILES:
        source = sync._SRC_HARNESS / filename
        if not source.is_file():
            continue
        destination = sync._GLOBAL / "harness" / filename
        if not destination.is_file():
            missing.append(f"harness/{filename}")
        elif _digest(source) != _digest(destination):
            diverged.append(f"harness/{filename}")

    for package in sync._HARNESS_INCLUDE:
        package_missing, package_diverged = compare_tree(
            sync._SRC_HARNESS / package,
            sync._GLOBAL / "harness" / package,
            prefix=f"harness/{package}/",
        )
        missing.extend(package_missing)
        diverged.extend(package_diverged)

    for directory in sync._BRAIN_DIRS:
        dir_missing, dir_diverged = compare_tree(
            sync._ROOT / ".opencode" / directory,
            sync._GLOBAL / directory,
            prefix=f"{directory}/",
        )
        missing.extend(dir_missing)
        diverged.extend(dir_diverged)

    registry_source = sync._ROOT / ".opencode" / "skills" / "skills_registry.yaml"
    registry_target = sync._GLOBAL / "skills" / "skills_registry.yaml"
    if not registry_target.is_file():
        missing.append("skills/skills_registry.yaml")
    elif _digest(registry_source) != _digest(registry_target):
        diverged.append("skills/skills_registry.yaml")

    if not (sync._GLOBAL / "AGENTS.md").is_file():
        missing.append("AGENTS.md")
    elif _digest(sync._SRC_AGENTS_MD) != _digest(sync._GLOBAL / "AGENTS.md"):
        diverged.append("AGENTS.md")

    return {"missing": sorted(missing), "diverged": sorted(diverged)}


def main(argv: list[str] | None = None) -> int:
    """Entrypoint de la verificación.

    Args:
        argv: Argumentos CLI (``None`` usa ``sys.argv``).

    Returns:
        Exit code (0 = global sincronizado, 1 = drift).
    """
    parser = argparse.ArgumentParser(description="Verifica sync global OpenCode")
    parser.add_argument("--json", action="store_true", help="salida JSON")
    parser.add_argument("--quiet", action="store_true", help="sin detalle")
    args = parser.parse_args(argv)

    result = verify()
    ok = not result["missing"] and not result["diverged"]
    if args.json:
        print(json.dumps({**result, "ok": ok}, indent=2, sort_keys=True))
    elif not args.quiet:
        print(f"global: {sync._GLOBAL}")
        print(f"faltantes: {len(result['missing'])} | divergentes: {len(result['diverged'])}")
        for label in result["missing"]:
            print(f"  FALTA  {label}")
        for label in result["diverged"]:
            print(f"  DRIFT  {label}")
        print("GLOBAL SINCRONIZADO" if ok else "GLOBAL CON DRIFT")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
