"""render_local_models.py — regenera artefactos desde la SSOT de modelos locales.

WHAT: CLI idempotente que lee ``harness/model_router/local_models.yaml`` (SSOT)
y (1) escribe el YAML de config de llama-swap y (2) parchea los
``opencode.json``/``opencode.jsonc`` (provider ``llamacpp``, ``model``/
``small_model`` y ``agent.*.model``), preservando el resto de claves de esos
archivos. Las funciones de render viven en ``harness.model_router.local_models``
(fuente unica).
WHY: la config de modelos estaba duplicada en cinco archivos; actualizar un
modelo era un dolor y la deriva era silenciosa. Editar la SSOT + regenerar
mantiene todo en sincronia, y ``--check`` lo verifica como gate de CI.
WHERE: ``uv run python scripts/render_local_models.py [--dry-run|--check]``.

Uso:
    python scripts/render_local_models.py            # aplica (idempotente)
    python scripts/render_local_models.py --dry-run  # imprime sin escribir
    python scripts/render_local_models.py --check    # exit 1 si hay deriva
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

#: Raiz del repo en sys.path[1] (SEG: nunca index 0) para importar el harness.
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(1, str(_ROOT))

from harness.model_router.local_models import (
    build_targets,
    check_targets,
    load_config,
    write_targets,
)

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("render_local_models")

#: Ruta relativa del ``opencode.json`` versionado del repo.
REPO_OPENCODE_RELATIVE = Path(".opencode") / "opencode.json"
#: Ruta relativa del ``opencode.jsonc`` global del usuario (bajo su home).
GLOBAL_OPENCODE_RELATIVE = Path(".config") / "opencode" / "opencode.jsonc"


def _default_home() -> Path:
    """Home del usuario para el ``opencode.jsonc`` global.

    Returns:
        ``Path.home()`` (resuelto en runtime, nunca hardcodeado).
    """
    return Path.home()


def _render_all(args: argparse.Namespace) -> dict[Path, str]:
    """Resuelve los destinos y su contenido desde la SSOT y los argumentos.

    Args:
        args: Argumentos del CLI (ssot/repo_root/home).

    Returns:
        Mapa destino -> contenido esperado.

    Raises:
        ValueError: Si la SSOT es invalida o un destino no parsea.
    """
    config = load_config(args.ssot) if args.ssot is not None else load_config()
    swap_path = Path(config.backend.swap_config)
    repo_path = args.repo_root / REPO_OPENCODE_RELATIVE
    global_path = (args.home or _default_home()) / GLOBAL_OPENCODE_RELATIVE
    return build_targets(config, swap_path, repo_path, global_path)


def _print_targets(targets: dict[Path, str]) -> None:
    """Imprime cada destino y su contenido (modo ``--dry-run``)."""
    for path, content in targets.items():
        logger.info("")
        logger.info("=" * 72)
        logger.info("# DRY-RUN -> %s", path)
        logger.info("=" * 72)
        logger.info("%s", content)


def _report_mismatches(targets: dict[Path, str]) -> int:
    """Verifica ``render == disco``; imprime el estado y devuelve el exit code.

    Args:
        targets: Mapa destino -> contenido esperado.

    Returns:
        0 si todo esta sincronizado; 1 si hay destinos ausentes o desincronizados.
    """
    mismatches = check_targets(targets)
    if mismatches:
        for message in mismatches:
            logger.error("[DRIFT] %s", message)
        logger.error(
            "[FAIL] %s archivo(s) fuera de sync. "
            "WHY: la SSOT cambio y no se regenero. "
            "WHERE: scripts/render_local_models.py --check",
            len(mismatches),
        )
        return 1
    logger.info("[OK] Render == disco (%s destinos en sync).", len(targets))
    return 0


def main(argv: list[str] | None = None) -> int:
    """CLI entry point: aplica, simula o verifica la regeneracion.

    Args:
        argv: Argumentos (None = ``sys.argv[1:]``).

    Returns:
        Exit code: 0 exito; 1 si ``--check`` detecta deriva.
    """
    parser = argparse.ArgumentParser(
        description="Regenera llama-swap.yaml + opencode.json desde local_models.yaml"
    )
    parser.add_argument("--dry-run", action="store_true", help="imprime sin escribir")
    parser.add_argument("--check", action="store_true", help="exit 1 si hay deriva")
    parser.add_argument("--ssot", type=Path, default=None, help="ruta alternativa de la SSOT")
    parser.add_argument("--repo-root", type=Path, default=_ROOT, help="raiz del repo SWARMIND")
    parser.add_argument("--home", type=Path, default=None, help="home del usuario")
    args = parser.parse_args(argv)

    targets = _render_all(args)
    if args.dry_run:
        _print_targets(targets)
        return 0
    if args.check:
        return _report_mismatches(targets)
    written = write_targets(targets)
    for path in written:
        logger.info("[OK] Escrito: %s", path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
