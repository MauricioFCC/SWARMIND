"""
backup_memory.py — Copia de seguridad automática de la memoria central.

Lee la configuración de `<MEMORY_ROOT>/.swarmind_config.json` (creada por
`config_swarmind.py`) y ejecuta el backup según el intervalo configurado.

CONFIGURACIÓN (ver config_swarmind.py):
  - backup_enabled:      True/False — activa o desactiva el backup
  - backup_interval_hours: N horas entre backups (0 = solo manual/pre-commit)
  - backup_cadence:      manual | daily | weekly | commit (legacy, si no hay
                         backup_interval_hours explícito)
  - backup_keep:         N backups a conservar (rotación automática)

MECANISMO AUTOMÁTICO:
  1. Pre-commit hook (cada commit): corre este script (cadence=commit).
  2. Tarea programada (opcional): Windows Task Scheduler o Linux cron
     (registrada por config_swarmind.py --schedule) ejecuta el backup
     periódicamente según backup_interval_hours.
  3. El script es idempotente: si el último backup es más reciente que el
     intervalo, no hace nada (evita backups duplicados).

SEGURIDAD:
  - Nunca borra la db de producción.
  - Los backups viven en <MEMORY_ROOT>/backups/lancedb_<timestamp>.
  - Rotación automática: conserva solo los `backup_keep` más recientes.
  - Backup es copia completa (no incremental) — simple y confiable.

Uso:
    python scripts/backup_memory.py                 # Backup (respeta intervalo)
    python scripts/backup_memory.py --force         # Backup forzado (ignora intervalo)
    python scripts/backup_memory.py --list          # Listar backups disponibles
    python scripts/backup_memory.py --restore <dir> # Restaurar desde backup
    python scripts/backup_memory.py --schedule      # Registrar tarea programada
    python scripts/backup_memory.py --uninstall     # Quitar tarea programada
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import shutil
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)

_HERE = Path(__file__).resolve().parent
_ROOT = _HERE.parent

_MEMORY_ROOT = Path(os.environ.get(
    "MEMORY_ROOT",
    str(Path.home() / "Documents" / "Memory_Proyects"),
))
_CONFIG_FILE = _MEMORY_ROOT / ".swarmind_config.json"
_DB_DIR = _MEMORY_ROOT / "data" / "lancedb"
_BACKUP_ROOT = _MEMORY_ROOT / "backups"

_DEFAULTS = {
    "memory_root": str(_MEMORY_ROOT),
    "backup_enabled": True,
    "backup_interval_hours": 24,     # 24h = daily por defecto
    "backup_cadence": "daily",       # manual | daily | weekly | commit
    "backup_keep": 5,
    "cleanup_duplicates": True,
    "auto_import_db": False,
}


def _load_config() -> dict:
    if _CONFIG_FILE.exists():
        try:
            data = json.loads(_CONFIG_FILE.read_text(encoding="utf-8"))
            merged = dict(_DEFAULTS)
            merged.update(data)
            return merged
        except Exception:  # noqa: BLE001 - config defensiva
            return dict(_DEFAULTS)
    return dict(_DEFAULTS)


def _count_lance_collections(db_dir: Path) -> int:
    if not db_dir.is_dir():
        return 0
    return sum(1 for d in db_dir.iterdir() if d.is_dir() and d.name.endswith(".lance"))


def _list_backups() -> list[Path]:
    if not _BACKUP_ROOT.is_dir():
        return []
    return sorted(
        (d for d in _BACKUP_ROOT.iterdir() if d.is_dir() and d.name.startswith("lancedb_")),
        reverse=True,
    )


def _last_backup_age_hours() -> float | None:
    """Edad del backup más reciente en horas (None si no hay)."""
    backups = _list_backups()
    if not backups:
        return None
    # El timestamp esta en el nombre: lancedb_YYYYMMDD_HHMMSS
    try:
        ts_str = backups[0].name.replace("lancedb_", "")
        ts = datetime.strptime(ts_str, "%Y%m%d_%H%M%S").replace(tzinfo=UTC)
        return (datetime.now(UTC) - ts).total_seconds() / 3600
    except ValueError:
        return None


def _rotate(keep: int, dry_run: bool = False) -> int:
    """Rotación: borra backups viejos, conserva los `keep` más recientes.

    Args:
        keep: Número de backups a conservar.
        dry_run: Si True, solo simula.

    Returns:
        Número de backups eliminados.
    """
    backups = _list_backups()
    to_delete = backups[keep:]
    removed = 0
    for b in to_delete:
        if not dry_run:
            shutil.rmtree(b, ignore_errors=True)
        removed += 1
    if removed and not dry_run:
        logger.info("  🧹 Rotación: %d backup(s) viejo(s) eliminado(s) (keep=%d)", removed, keep)
    return removed


def _do_backup(force: bool = False, dry_run: bool = False) -> bool:
    """Ejecuta el backup respetando la config (intervalo + rotación).

    Args:
        force: Si True, ignora el intervalo.
        dry_run: Si True, solo simula.

    Returns:
        True si se creó un backup.
    """
    config = _load_config()
    if not config.get("backup_enabled", True):
        logger.info("  ⏸️  Backup desactivado en config (backup_enabled=false).")
        return False

    if _count_lance_collections(_DB_DIR) == 0:
        logger.warning("  ⚠️  No hay db que respaldar (data/lancedb vacía o inexistente).")
        return False

    # Respetar intervalo (si no es force)
    interval = config.get("backup_interval_hours", 0)
    cadence = config.get("backup_cadence", "manual")
    if cadence == "daily" and not interval:
        interval = 24
    elif cadence == "weekly" and not interval:
        interval = 168

    if not force and interval and interval > 0:
        age = _last_backup_age_hours()
        if age is not None and age < interval:
            logger.info(
                "  ⏭️  Último backup hace %.1fh (intervalo %dh). Omitido.",
                age, interval,
            )
            return False

    # Crear backup
    ts = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    backup_dir = _BACKUP_ROOT / f"lancedb_{ts}"
    if not dry_run:
        backup_dir.mkdir(parents=True, exist_ok=True)
        shutil.copytree(_DB_DIR, backup_dir / "lancedb", dirs_exist_ok=True)
    logger.info("  🛡️  Backup creado: %s %s", backup_dir, "(simulado)" if dry_run else "")

    # Rotación
    keep = config.get("backup_keep", 5)
    _rotate(keep, dry_run=dry_run)
    return True


def _restore(backup_dir: Path, dry_run: bool = False) -> bool:
    """Restaura una db desde un backup."""
    src = backup_dir / "lancedb"
    if not src.is_dir() or _count_lance_collections(src) == 0:
        logger.error("  ❌ Backup inválido (sin colecciones): %s", backup_dir)
        return False
    # Backup de la actual antes de restaurar (seguridad)
    if not dry_run and _count_lance_collections(_DB_DIR) > 0:
        _do_backup(force=True, dry_run=False)
    if not dry_run:
        _DB_DIR.mkdir(parents=True, exist_ok=True)
        for d in src.iterdir():
            if d.is_dir() and d.name.endswith(".lance"):
                shutil.copytree(d, _DB_DIR / d.name, dirs_exist_ok=True)
    logger.info("  ♻️  Restaurada db desde %s %s", backup_dir, "(simulado)" if dry_run else "")
    return True


def _schedule_windows(interval_hours: int) -> bool:
    """Registra una tarea programada en Windows Task Scheduler.

    Args:
        interval_hours: Intervalo en horas.

    Returns:
        True si se registró.
    """
    python = sys.executable
    script = str(_HERE / "backup_memory.py")
    task_name = "SwarmindMemoryBackup"
    # Sintaxis schtasks: /SC DAILY solo con /ST (sin /D para diario)
    if interval_hours % 24 == 0:
        days = interval_hours // 24
        if days == 1:
            sc = "/SC DAILY /ST 02:00"
        else:
            sc = f"/SC DAILY /MO {days} /ST 02:00"
    else:
        sc = f"/SC HOURLY /MO {max(interval_hours, 1)}"
    cmd = (
        f'schtasks /Create /F /TN "{task_name}" {sc} '
        f'/TR "\\"{python}\\" \\"{script}\\" --force"'
    )
    result = subprocess.run(cmd, capture_output=True, text=True, shell=True, check=False)
    if result.returncode == 0:
        logger.info("  ✅ Tarea programada registrada: %s (cada %dh)", task_name, interval_hours)
        return True
    logger.warning("  ⚠️  No se pudo registrar tarea: %s", result.stderr.strip()[:200])
    return False


def _schedule_linux(interval_hours: int) -> bool:
    """Registra un cron job en Linux/macOS."""
    cron_line = f"0 */{max(interval_hours, 1)} * * * {sys.executable} {_HERE / 'backup_memory.py'} --force"
    try:
        current = subprocess.run(["crontab", "-l"], capture_output=True, text=True, check=False).stdout
        if "SwarmindMemoryBackup" in current:
            logger.info("  ✅ Cron ya registrado (SwarmindMemoryBackup)")
            return True
        new_cron = current.rstrip() + "\n" + cron_line + "  # SwarmindMemoryBackup\n"
        result = subprocess.run(["crontab", "-"], input=new_cron, capture_output=True, text=True, check=False)
        if result.returncode == 0:
            logger.info("  ✅ Cron registrado: %s", cron_line)
            return True
        logger.warning("  ⚠️  No se pudo registrar cron: %s", result.stderr.strip()[:200])
        return False
    except FileNotFoundError:
        logger.warning("  ⚠️  crontab no disponible (Linux/macOS requerido).")
        return False


def _schedule(interval_hours: int) -> bool:
    """Registra la tarea programada según el SO."""
    if os.name == "nt":
        return _schedule_windows(interval_hours)
    return _schedule_linux(interval_hours)


def _uninstall_schedule() -> bool:
    """Quita la tarea programada."""
    if os.name == "nt":
        result = subprocess.run(
            ['schtasks', '/Delete', '/F', '/TN', 'SwarmindMemoryBackup'],
            capture_output=True, text=True, shell=True,
            check=False,
        )
        if result.returncode == 0:
            logger.info("  ✅ Tarea programada eliminada")
            return True
        logger.warning("  ⚠️  No se pudo eliminar tarea (¿existe?).")
        return False
    # Linux: filtrar linea
    try:
        current = subprocess.run(["crontab", "-l"], capture_output=True, text=True, check=False).stdout
        filtered = "\n".join(
            line for line in current.splitlines()
            if "SwarmindMemoryBackup" not in line
        ) + "\n"
        subprocess.run(["crontab", "-"], input=filtered, capture_output=True, text=True, check=False)
        logger.info("  ✅ Cron eliminado")
        return True
    except FileNotFoundError:
        return False


def main() -> None:
    """CLI principal."""
    parser = argparse.ArgumentParser(description="Backup automático de la memoria central")
    parser.add_argument("--force", action="store_true", help="Backup forzado (ignora intervalo)")
    parser.add_argument("--dry-run", action="store_true", help="Solo simular")
    parser.add_argument("--list", action="store_true", help="Listar backups")
    parser.add_argument("--restore", type=str, metavar="DIR", help="Restaurar desde backup")
    parser.add_argument("--schedule", action="store_true", help="Registrar tarea programada")
    parser.add_argument("--uninstall", action="store_true", help="Quitar tarea programada")
    args = parser.parse_args()

    config = _load_config()

    if args.list:
        backups = _list_backups()
        if not backups:
            logger.info("  (sin backups)")
        for b in backups:
            cols = _count_lance_collections(b / "lancedb")
            logger.info("  📦 %-30s (%d colecciones)", b.name, cols)
        return

    if args.restore:
        _restore(Path(args.restore), dry_run=args.dry_run)
        return

    if args.schedule:
        interval = config.get("backup_interval_hours", 24)
        _schedule(interval)
        return

    if args.uninstall:
        _uninstall_schedule()
        return

    # Backup normal (respeta intervalo)
    _do_backup(force=args.force, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
