"""
sync_opencode_global.py — Sincroniza el CEREBRO y el MOTOR de Swarmind a la
config GLOBAL de opencode (estándar v2.5: opencode global = fuente de verdad).

Opción A (SSOT global): agentes, skills, core y registry viven UNA vez en
``~/.config/opencode/`` (config global de opencode) y opencode los toma para
TODOS los proyectos. Cada commit de SWARMIND invoca este script via
pre-commit hook, manteniendo el global siempre al dia sin duplicar archivos
por proyecto.

Estándar v2.5 (2026-08): EL MOTOR (harness/) TAMBIÉN vive en el global.
Los proyectos solo tienen .opencode/ + skills (sin copia de harness).
Esto elimina ~5.3 GB de duplicación (Hermes 3.3 GB, sugurityOs 1.7 GB).

Lo que NO se copia (queda en cada proyecto como config propia):
  - .opencode/config/           (project_config, routing_rules, token_budgets)
  - .opencode/federated/        (memoria federada por proyecto)
  - harness/db/                 (datos runtime LanceDB — en el global se copia db/schema, no datos)
  - .env                        (credenciales locales)

Seguridad (ADR-0035): rutas portables via env vars con fallback a
``Path.home()``. Nunca ``$HOME`` literal.

Uso:
    python scripts/sync_opencode_global.py              # Sync completo (cerebro + motor)
    python scripts/sync_opencode_global.py --dry-run    # Simular
    python scripts/sync_opencode_global.py --quiet      # Sin log (hook)
    python scripts/sync_opencode_global.py --cerebro    # Solo cerebro (agents/skills/core)
    python scripts/sync_opencode_global.py --motor      # Solo motor (harness)
"""

from __future__ import annotations

import argparse
import logging
import os
import shutil
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Rutas (portables, ADR-0035)
# ---------------------------------------------------------------------------

_HERE = Path(__file__).resolve().parent            # Swarmind/scripts/
_ROOT = _HERE.parent                               # Swarmind/
_SRC_OPENCODE = _ROOT / ".opencode"
_SRC_HARNESS = _ROOT / "harness"

# Config global de opencode: ~/.config/opencode (NO ~/.opencode)
_GLOBAL = Path(os.environ.get(
    "OPENCODE_GLOBAL_DIR",
    str(Path.home() / ".config" / "opencode"),
))

# Partes del cerebro que se sincronizan al global
_BRAIN_DIRS = ["agents", "skills", "core"]
_REGISTRY_FILE = "skills/skills_registry.yaml"

# Directorios del motor (harness) que se sincronizan al global.
# Se excluyen datos runtime (db/, tests locales, caches).
_HARNESS_INCLUDE = ["orchestrator", "memory_rag", "tools_sandbox", "model_router",
                    "evolve_loop", "qa", "security", "guardrails", "hooks",
                    "evals", "aifactory", "observability", "parallel", "plugins",
                    "gateway", "db", "benchmarks"]
_HARNESS_FILES = ["common.py", "delegate.py", "run.py", "run_commands.py",
                  "scheduler.py", "reset_state.py", "cli_common.py", "gpu_accel.py",
                  "gpu_optimize.py", "security_policy.py"]


# ---------------------------------------------------------------------------
# Sync
# ---------------------------------------------------------------------------


def _sync_dir(src: Path, dst: Path, dry_run: bool = False) -> int:
    """Copia un directorio del cerebro al destino global (merge preservador).

    Solo copia/sobreescribe; nunca borra archivos ajenos del global (ej.
    plugins, configs del usuario).

    Args:
        src: Directorio fuente (SWARMIND/.opencode/<parte>).
        dst: Directorio destino (~/.config/opencode/<parte>).
        dry_run: Si True, solo simula.

    Returns:
        Número de archivos sincronizados.
    """
    if not src.is_dir():
        logger.warning("  ⚠️  fuente no existe: %s", src)
        return 0
    dst.mkdir(parents=True, exist_ok=True)
    count = 0
    for item in src.iterdir():
        target = dst / item.name
        if item.is_dir():
            if not dry_run:
                shutil.copytree(item, target, dirs_exist_ok=True)
            count += sum(1 for _ in item.rglob("*") if _.is_file())
        else:
            if not dry_run:
                shutil.copy2(item, target)
            count += 1
    return count


def _sync_harness_to_global(dry_run: bool = False) -> int:
    """Sincroniza el motor (harness/) a ~/.config/opencode/harness.

    Estándar v2.5: el motor vive UNA vez en el global. Copia solo módulos
    de código (no datos runtime, no tests, no caches).

    Args:
        dry_run: Si True, solo simula.

    Returns:
        Número de archivos sincronizados.
    """
    if not _SRC_HARNESS.is_dir():
        logger.warning("  ⚠️  harness fuente no existe: %s", _SRC_HARNESS)
        return 0
    dst = _GLOBAL / "harness"
    dst.mkdir(parents=True, exist_ok=True)
    count = 0

    # Copiar directorios de módulos
    for subdir in _HARNESS_INCLUDE:
        src = _SRC_HARNESS / subdir
        if not src.is_dir():
            continue
        target = dst / subdir
        if not dry_run:
            shutil.copytree(src, target, dirs_exist_ok=True,
                            ignore=shutil.ignore_patterns("__pycache__", "*.pyc",
                                                           "*.so", "*.pyd", ".DS_Store"))
        count += sum(1 for _ in src.rglob("*.py") if _.is_file())

    # Copiar archivos raíz de harness
    for fname in _HARNESS_FILES:
        src = _SRC_HARNESS / fname
        if src.is_file():
            if not dry_run:
                shutil.copy2(src, dst / fname)
            count += 1

    return count


def sync_global(dry_run: bool = False, quiet: bool = False,
                cerebro: bool = False, motor: bool = False) -> dict:
    """Sincroniza el cerebro Swarmind a la config global de opencode.

    Args:
        dry_run: Si True, solo simula.
        quiet: Si True, suprime logs (para hooks).
        cerebro: Si True, solo sincroniza cerebro (agents/skills/core/registry).
        motor: Si True, solo sincroniza motor (harness/).

    Returns:
        Dict con estadísticas por parte del cerebro.
    """
    stats: dict[str, int] = {}
    if not quiet:
        logger.info("=" * 60)
        logger.info("🌐 SYNC OPENCODE GLOBAL (Opción A — SSOT, estándar v2.5)")
        logger.info("   Source: %s", _ROOT)
        logger.info("   Global: %s", _GLOBAL)
        logger.info("   Dry run: %s", dry_run)
        logger.info("=" * 60)

    # Por defecto sync completo (cerebro + motor) salvo flag explícito
    do_cerebro = cerebro or (not cerebro and not motor)
    do_motor = motor or (not cerebro and not motor)

    if do_cerebro:
        for part in _BRAIN_DIRS:
            src = _SRC_OPENCODE / part
            dst = _GLOBAL / part
            count = _sync_dir(src, dst, dry_run=dry_run)
            stats[part] = count
            if not quiet:
                logger.info("  ✅ %-10s %d archivos %s", part, count, "(simulado)" if dry_run else "")

        # skills_registry.yaml (referencia desde skills/)
        registry_src = _SRC_OPENCODE / _REGISTRY_FILE
        if registry_src.is_file():
            if not dry_run:
                registry_dst = _GLOBAL / "skills" / "skills_registry.yaml"
                registry_dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(registry_src, registry_dst)
            stats["skills_registry"] = 1
            if not quiet:
                logger.info("  ✅ skills_registry.yaml %s", "(simulado)" if dry_run else "actualizado")

    if do_motor:
        count = _sync_harness_to_global(dry_run=dry_run)
        stats["harness"] = count
        if not quiet:
            logger.info("  ✅ %-10s %d archivos %s", "harness", count, "(simulado)" if dry_run else "")

    total = sum(stats.values())
    if not quiet:
        logger.info("")
        logger.info("  📊 Total: %d archivos sincronizados al global", total)
        logger.info("")
        logger.info("  ℹ️  Reinicia opencode para que tome los cambios (config se carga al inicio).")
        logger.info("=" * 60)
    return stats


def main() -> None:
    """CLI principal del sync global."""
    parser = argparse.ArgumentParser(description="Sync cerebro+motor Swarmind -> opencode global")
    parser.add_argument("--dry-run", action="store_true", help="Solo simular")
    parser.add_argument("--quiet", action="store_true", help="Sin log (para hooks)")
    parser.add_argument("--cerebro", action="store_true", help="Solo cerebro (agents/skills/core)")
    parser.add_argument("--motor", action="store_true", help="Solo motor (harness)")
    args = parser.parse_args()

    sync_global(dry_run=args.dry_run, quiet=args.quiet, cerebro=args.cerebro, motor=args.motor)


if __name__ == "__main__":
    main()
