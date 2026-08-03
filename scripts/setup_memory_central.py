"""
setup_memory_central.py — Configura la MEMORIA CENTRAL de Swarmind.

Estándar v3.0 (2026-08): la memoria vive UNA vez en
``<Documents>/Memory_Proyects`` (portable via ``MEMORY_ROOT``).

DIFERENCIAS vs modelo anterior:
  - Antes: memoria local en CADA proyecto (duplicada).
  - Ahora: UNA memoria central portable en Documents, usada por TODOS.

SEGURIDAD DE DATOS (v3.1, ADR-0038):
  - NUNCA borra la db sin hacer backup previo.
  - Backup automático de data/lancedb antes de cualquier operación destructiva.
  - La copia de backup vive en <MEMORY_ROOT>/backups/ con timestamp.
  - Es idempotente: si la db ya existe y es válida, no la toca.

QUÉ HACE:
  1. Determina MEMORY_ROOT (portable): ``$MEMORY_ROOT`` o
     ``<home>/Documents/Memory_Proyects`` (cualquier SO).
  2. Construye la estructura de memoria desde cero (idempotente).
  3. SI data/lancedb tiene colecciones válidas → NO hace nada con la db.
  4. SI data/lancedb NO existe o está vacía → avisa al usuario (no inventa
     fuentes hardcodeadas; el usuario decide importar o empezar de cero).
  5. Limpia duplicados de motor (harness/, scripts/, etc.) SOLO después de
     confirmar que la db está segura en data/lancedb.
  6. Crea backup de seguridad de la db antes de cualquier borrado.

ESTRUCTURA RESULTANTE (Memory_Proyects/):
  Memory_Proyects/
  ├── knowledge/          # conocimiento por dominio
  ├── syntheses/          # sintesis de sesiones
  ├── 99_Hermes_Brain/    # cerebro central
  ├── personal/           # notas personales
  ├── projects/           # memoria por proyecto
  ├── sessions/           # registros de sesiones
  ├── inbox/              # entradas entrantes
  ├── exports/            # exportaciones
  ├── data/
  │   └── lancedb/        # db central (SE PRESERVA con backup)
  ├── backups/            # copias de seguridad (timestamp)
  └── README.md

Uso:
    python scripts/setup_memory_central.py --dry-run          # Ver plan
    python scripts/setup_memory_central.py                    # Construir/limpiar
    python scripts/setup_memory_central.py --preserve-all     # No borrar nada
    python scripts/setup_memory_central.py --backup           # Solo backup de db
    python scripts/setup_memory_central.py --restore <dir>    # Restaurar backup
"""

from __future__ import annotations

import argparse
import logging
import os
import shutil
from datetime import UTC, datetime
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)

_HERE = Path(__file__).resolve().parent        # Swarmind/scripts/
_ROOT = _HERE.parent                           # Swarmind/

# Ruta central portable (cualquier SO): $MEMORY_ROOT o <home>/Documents/Memory_Proyects
_MEMORY_ROOT = Path(os.environ.get(
    "MEMORY_ROOT",
    str(Path.home() / "Documents" / "Memory_Proyects"),
))

# Directorios de memoria (se construyen siempre, preservando contenido)
_MEMORY_DIRS = [
    "knowledge", "syntheses", "99_Hermes_Brain", "personal",
    "projects", "sessions", "inbox", "exports", "data",
    "data/lancedb", "backups",
]

# Directorios que NO corresponden en una carpeta de memoria pura
# (el motor y el cerebro viven en opencode global / repo Swarmind).
# Se borran SOLO con backup previo y SI la db central está segura.
_CLEANUP_DIRS = [
    "harness", "scripts", "memory_rag", "core", "infra",
    "quality", "skills", ".opencode", ".pytest_cache",
    "__pycache__",
]


def _count_lance_collections(db_dir: Path) -> int:
    """Cuenta colecciones .lance válidas en un directorio de db.

    Args:
        db_dir: Directorio de la db LanceDB.

    Returns:
        Número de colecciones (dirs .lance).
    """
    if not db_dir.is_dir():
        return 0
    return sum(1 for d in db_dir.iterdir() if d.is_dir() and d.name.endswith(".lance"))


def _backup_db(dry_run: bool = False) -> Path | None:
    """Crea un backup de la db central con timestamp.

    Args:
        dry_run: Si True, solo simula.

    Returns:
        Ruta del backup creado, o None si no había db.
    """
    db = _MEMORY_ROOT / "data" / "lancedb"
    if _count_lance_collections(db) == 0:
        logger.info("  ℹ️  No hay db para backup (data/lancedb vacía o inexistente).")
        return None

    ts = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    backup_dir = _MEMORY_ROOT / "backups" / f"lancedb_{ts}"
    if not dry_run:
        backup_dir.mkdir(parents=True, exist_ok=True)
        shutil.copytree(db, backup_dir / "lancedb", dirs_exist_ok=True)
    logger.info("  🛡️  Backup creado: %s %s", backup_dir, "(simulado)" if dry_run else "")
    return backup_dir


def _restore_db(backup_dir: Path, dry_run: bool = False) -> bool:
    """Restaura una db desde un backup.

    Args:
        backup_dir: Directorio de backup (contiene lancedb/).
        dry_run: Si True, solo simula.

    Returns:
        True si se restauró.
    """
    src = backup_dir / "lancedb"
    if not src.is_dir() or _count_lance_collections(src) == 0:
        logger.error("  ❌ Backup inválido (sin colecciones .lance): %s", backup_dir)
        return False
    dst = _MEMORY_ROOT / "data" / "lancedb"
    if not dry_run:
        # Hacer backup de la actual antes de restaurar (seguridad)
        _backup_db(dry_run=False)
        dst.mkdir(parents=True, exist_ok=True)
        for d in src.iterdir():
            if d.is_dir() and d.name.endswith(".lance"):
                shutil.copytree(d, dst / d.name, dirs_exist_ok=True)
    logger.info("  ♻️  Restaurada db desde %s %s", backup_dir, "(simulado)" if dry_run else "")
    return True


def _build_structure(dry_run: bool) -> None:
    """Crea la estructura de memoria (idempotente)."""
    logger.info("")
    logger.info("📁 Construyendo estructura de memoria central...")
    for rel in _MEMORY_DIRS:
        path = _MEMORY_ROOT / rel
        if path.exists():
            logger.info("  ✅ existe: %s", rel)
        else:
            if not dry_run:
                path.mkdir(parents=True, exist_ok=True)
                (path / ".gitkeep").write_text("", encoding="utf-8")
            logger.info("  ➕ creado: %s %s", rel, "(simulado)" if dry_run else "")


def _verify_db_safe(dry_run: bool) -> bool:
    """Verifica que la db central está segura antes de limpiar duplicados.

    Returns:
        True si la db central tiene colecciones (o no hay db que proteger).
    """
    db = _MEMORY_ROOT / "data" / "lancedb"
    cols = _count_lance_collections(db)
    if cols > 0:
        logger.info("  🗄️  DB central OK: %d colecciones en data/lancedb", cols)
        return True

    # Buscar si hay db en duplicados (harness/) que no se haya migrado
    for dup in _CLEANUP_DIRS:
        dup_db = _MEMORY_ROOT / dup / "db" / "lancedb"
        dup_cols = _count_lance_collections(dup_db)
        if dup_cols > 0:
            logger.warning(
                "  ⚠️  Se encontró db en %s (%d colecciones) pero NO en data/lancedb. "
                "La db NO se migra automáticamente (el usuario decide el origen). "
                "data/lancedb queda vacía; los duplicados NO se limpian.",
                dup_db, dup_cols,
            )
            return False
    return True  # No hay db que proteger → seguro limpiar duplicados de motor


def _cleanup(dry_run: bool) -> None:
    """Limpia duplicados de motor SOLO si la db central está segura."""
    logger.info("")
    logger.info("🧹 Limpiando duplicados (motor/cerebro no son memoria)...")
    removed = 0
    for name in _CLEANUP_DIRS:
        path = _MEMORY_ROOT / name
        if not path.exists():
            continue
        if not dry_run:
            shutil.rmtree(path, ignore_errors=True)
        removed += 1
        logger.info("  🗑️  %s %s", name, "(simulado)" if dry_run else "")
    if removed == 0:
        logger.info("  (nada que limpiar)")


def _verify(dry_run: bool) -> bool:
    """Verifica la estructura resultante."""
    logger.info("")
    logger.info("=" * 60)
    logger.info("🧠 MEMORIA CENTRAL: %s", _MEMORY_ROOT)
    logger.info("=" * 60)
    ok = True
    for rel in _MEMORY_DIRS:
        path = _MEMORY_ROOT / rel
        if path.is_dir():
            n = sum(1 for _ in path.rglob("*") if _.is_file()) if path.exists() else 0
            logger.info("  ✅ %-20s (%d archivos)", rel, n)
        else:
            if not dry_run:
                ok = False
                logger.info("  ❌ %-20s (NO existe)", rel)
    db = _MEMORY_ROOT / "data" / "lancedb"
    cols = _count_lance_collections(db)
    logger.info("  🗄️  DB LanceDB: %d colecciones", cols)
    return ok


def main() -> None:
    """CLI principal."""
    parser = argparse.ArgumentParser(description="Configura la memoria central de Swarmind")
    parser.add_argument("--dry-run", action="store_true", help="Solo simular (no escribe)")
    parser.add_argument("--preserve-all", action="store_true", help="No limpiar duplicados")
    parser.add_argument("--backup", action="store_true", help="Solo crear backup de la db")
    parser.add_argument("--restore", type=str, metavar="DIR", help="Restaurar db desde backup")
    args = parser.parse_args()

    logger.info("=" * 60)
    logger.info("🚀 SWARMIND MEMORY CENTRAL SETUP (estándar v3.1)")
    logger.info("   Raíz:  %s", _MEMORY_ROOT)
    logger.info("   Dry:   %s", args.dry_run)
    logger.info("=" * 60)

    # Modo backup-only
    if args.backup:
        _backup_db(dry_run=args.dry_run)
        return

    # Modo restore
    if args.restore:
        _restore_db(Path(args.restore), dry_run=args.dry_run)
        return

    if not _MEMORY_ROOT.exists():
        logger.info("  ➕ Creando carpeta raíz: %s", _MEMORY_ROOT)
        if not args.dry_run:
            _MEMORY_ROOT.mkdir(parents=True, exist_ok=True)

    # 1. Backup de seguridad ANTES de tocar nada destructivo
    _backup_db(dry_run=args.dry_run)

    # 2. Construir estructura (idempotente)
    _build_structure(dry_run=args.dry_run)

    # 3. Verificar db segura antes de limpiar
    db_safe = _verify_db_safe(dry_run=args.dry_run)

    # 4. Limpiar duplicados solo si db segura y no --preserve-all
    if not args.preserve_all and db_safe:
        _cleanup(dry_run=args.dry_run)
    elif not args.preserve_all:
        logger.info("  ⏭️  Cleanup omitido: db central no confirmada. El usuario decide.")

    ok = _verify(dry_run=args.dry_run)
    if ok:
        logger.info("")
        logger.info("🎉 MEMORIA CENTRAL LISTA. Ruta portable via MEMORY_ROOT.")
        logger.info("   Configurar: $env:MEMORY_ROOT = '<tu>/Documents/Memory_Proyects'")
        sys_exit = 0
    else:
        logger.error("  ❌ Hay directorios faltantes (ejecuta sin --dry-run).")
        sys_exit = 1
    raise SystemExit(sys_exit)


if __name__ == "__main__":
    main()
