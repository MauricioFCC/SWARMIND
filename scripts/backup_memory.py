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
  - RuscaDB es el backend nativo: los backups viven en
    <MEMORY_ROOT>/backups/ruscadb_<timestamp>/ruscadb/ (db + wal + manifest +
    blobs). Con instalaciones legadas que aun tienen LanceDB se respalda
    tambien <MEMORY_ROOT>/backups/lancedb_<timestamp>/lancedb/.
  - Rotación automática: conserva solo los `backup_keep` más recientes.
  - LanceDB (legado) = colecciones NO volatiles (excluye `semantic_cache` y
    `agent_workspace_logs`: cache/logs regenerables que sumaban ~9.8 GB).

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

# Timeout de comandos de programacion de tareas (schtasks/crontab).
_SCHED_CMD_TIMEOUT_SECONDS = 60

_MEMORY_ROOT = Path(os.environ.get(
    "MEMORY_ROOT",
    str(Path.home() / "Documents" / "Memory_Proyects"),
))
_CONFIG_FILE = _MEMORY_ROOT / ".swarmind_config.json"
_DB_DIR = _MEMORY_ROOT / "data" / "lancedb"
_RUSCA_DB = _MEMORY_ROOT / "data" / "ruscadb.db"
_BACKUP_ROOT = _MEMORY_ROOT / "backups"

#: Archivos/artefactos que componen el RuscaDB central (SSOT de la memoria).
_RUSCA_ARTIFACTS: tuple[str, ...] = (
    "ruscadb.db",
    "ruscadb.wal",
    "ruscadb.manifest.json",
    "ruscadb.manifest.json.bak",
    "ruscadb.blobs",
)

#: Colecciones VOLATILES excluidas del backup (cache/logs regenerables).
#: Dominan el tamano (semantic_cache ~5 GB + agent_workspace_logs ~4.6 GB) y no
#: aportan valor restaurable: copiarlas hacia el backup lento y gigante (~9.8 GB).
_BACKUP_EXCLUDE_COLLECTIONS: frozenset[str] = frozenset({
    "semantic_cache",
    "agent_workspace_logs",
})

#: Patron de exclusion derivado para ``shutil.ignore_patterns``.
_BACKUP_IGNORE_PATTERNS: tuple[str, ...] = tuple(
    f"{name}.lance" for name in sorted(_BACKUP_EXCLUDE_COLLECTIONS)
)

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


def _ruscadb_present() -> bool:
    """True si el RuscaDB central existe y tiene contenido.

    Returns:
        True cuando ``data/ruscadb.db`` existe con tamano > 0.
    """
    return _RUSCA_DB.is_file() and _RUSCA_DB.stat().st_size > 0


def _copy_ruscadb(dest: Path) -> int:
    """Copia los artefactos del RuscaDB central a ``dest``.

    Args:
        dest: Directorio destino (``<backup>/ruscadb``).

    Returns:
        Numero de artefactos copiados.
    """
    if not _ruscadb_present():
        return 0
    dest.mkdir(parents=True, exist_ok=True)
    copiados = 0
    for nombre in _RUSCA_ARTIFACTS:
        origen = _RUSCA_DB.parent / nombre
        if not origen.exists():
            continue
        if origen.is_dir():
            shutil.copytree(origen, dest / nombre, dirs_exist_ok=True)
        else:
            shutil.copy2(origen, dest / nombre)
        copiados += 1
    return copiados


def _count_lance_collections(db_dir: Path) -> int:
    if not db_dir.is_dir():
        return 0
    return sum(1 for d in db_dir.iterdir() if d.is_dir() and d.name.endswith(".lance"))


def _backup_timestamp(path: Path) -> datetime:
    """Extrae el timestamp de un backup (``<prefijo>_YYYYMMDD_HHMMSS``).

    Args:
        path: Directorio de backup.

    Returns:
        Fecha/hora UTC del backup; ``mtime`` como fallback defendible.
    """
    try:
        ts_str = path.name.split("_", 1)[1]
        return datetime.strptime(ts_str, "%Y%m%d_%H%M%S").replace(tzinfo=UTC)
    except (IndexError, ValueError):
        return datetime.fromtimestamp(path.stat().st_mtime, tz=UTC)


def _list_backups() -> list[Path]:
    """Lista backups (``ruscadb_*`` y ``lancedb_*``) del mas nuevo al mas viejo.

    Ordena por el timestamp del nombre, no alfabeticamente: con prefijos mixtos
    el orden alfabetico pondria todo ``ruscadb_*`` antes de ``lancedb_*`` y la
    rotacion borraria backups recientes.

    Returns:
        Directorios de backup ordenados descendentemente por fecha.
    """
    if not _BACKUP_ROOT.is_dir():
        return []
    return sorted(
        (
            d
            for d in _BACKUP_ROOT.iterdir()
            if d.is_dir() and d.name.startswith(("lancedb_", "ruscadb_"))
        ),
        key=_backup_timestamp,
        reverse=True,
    )


def _last_backup_age_hours() -> float | None:
    """Edad del backup más reciente en horas (None si no hay)."""
    backups = _list_backups()
    if not backups:
        return None
    return (datetime.now(UTC) - _backup_timestamp(backups[0])).total_seconds() / 3600


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

    WHAT: respalda el RuscaDB nativo (fuente de verdad de la memoria general) y,
    si existe, la LanceDB legada. WHY: sin RuscaDB en el backup, la memoria
    general quedaria sin respaldo restaurable. WHERE: pre-commit + tarea
    programada.

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

    hay_rusca = _ruscadb_present()
    lance_cols = _count_lance_collections(_DB_DIR)
    if not hay_rusca and lance_cols == 0:
        logger.warning(
            "  ⚠️  No hay db que respaldar (data/ruscadb.db vacía e "
            "data/lancedb sin colecciones)."
        )
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

    # Crear backup: directorio unico con subcarpetas por backend presente.
    ts = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    prefijo = "ruscadb" if hay_rusca else "lancedb"
    backup_dir = _BACKUP_ROOT / f"{prefijo}_{ts}"
    if not dry_run:
        backup_dir.mkdir(parents=True, exist_ok=True)
        if hay_rusca:
            copiados = _copy_ruscadb(backup_dir / "ruscadb")
            logger.info("      RuscaDB: %d artefacto(s) copiado(s).", copiados)
        if lance_cols:
            shutil.copytree(
                _DB_DIR, backup_dir / "lancedb", dirs_exist_ok=True,
                ignore=shutil.ignore_patterns(*_BACKUP_IGNORE_PATTERNS),
            )
    logger.info("  🛡️  Backup creado: %s %s", backup_dir, "(simulado)" if dry_run else "")
    if lance_cols:
        logger.info(
            "      Excluidas de LanceDB (volatiles): %s",
            ", ".join(sorted(_BACKUP_EXCLUDE_COLLECTIONS)),
        )

    # Rotación
    keep = config.get("backup_keep", 5)
    _rotate(keep, dry_run=dry_run)
    return True


def _restore(backup_dir: Path, dry_run: bool = False) -> bool:
    """Restaura la memoria desde un backup (RuscaDB nativo y/o LanceDB legado).

    Args:
        backup_dir: Directorio de backup (contiene ``ruscadb/`` y/o ``lancedb/``).
        dry_run: Si True, solo simula.

    Returns:
        True si se restauró al menos un backend.
    """
    src_rusca = backup_dir / "ruscadb"
    src_lance = backup_dir / "lancedb"
    hay_rusca = src_rusca.is_dir() and (src_rusca / "ruscadb.db").is_file()
    hay_lance = src_lance.is_dir() and _count_lance_collections(src_lance) > 0
    if not hay_rusca and not hay_lance:
        logger.error("  ❌ Backup inválido (sin RuscaDB ni colecciones LanceDB): %s", backup_dir)
        return False

    # Backup de la actual antes de restaurar (seguridad)
    if not dry_run:
        _do_backup(force=True, dry_run=False)

    if not dry_run:
        if hay_rusca:
            _RUSCA_DB.parent.mkdir(parents=True, exist_ok=True)
            for nombre in _RUSCA_ARTIFACTS:
                origen = src_rusca / nombre
                if not origen.exists():
                    continue
                destino = _RUSCA_DB.parent / nombre
                if origen.is_dir():
                    shutil.copytree(origen, destino, dirs_exist_ok=True)
                else:
                    shutil.copy2(origen, destino)
        if hay_lance:
            _DB_DIR.mkdir(parents=True, exist_ok=True)
            for d in src_lance.iterdir():
                if d.is_dir() and d.name.endswith(".lance"):
                    shutil.copytree(d, _DB_DIR / d.name, dirs_exist_ok=True)
    logger.info(
        "  ♻️  Restaurada memoria desde %s (ruscadb=%s, lancedb=%s) %s",
        backup_dir, hay_rusca, hay_lance, "(simulado)" if dry_run else "",
    )
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
    cmd = [
        "schtasks", "/Create", "/F", "/TN", task_name,
        *sc.split(),
        "/TR", f'"{python}" "{script}" --force',
    ]
    # Lista de args + shell=False: evita inyeccion de comandos (CWE-78).
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        check=False,
        timeout=_SCHED_CMD_TIMEOUT_SECONDS,
    )
    if result.returncode == 0:
        logger.info("  ✅ Tarea programada registrada: %s (cada %dh)", task_name, interval_hours)
        return True
    logger.warning("  ⚠️  No se pudo registrar tarea: %s", result.stderr.strip()[:200])
    return False


def _schedule_linux(interval_hours: int) -> bool:
    """Registra un cron job en Linux/macOS."""
    cron_line = f"0 */{max(interval_hours, 1)} * * * {sys.executable} {_HERE / 'backup_memory.py'} --force"
    try:
        current = subprocess.run(
            ["crontab", "-l"], capture_output=True, text=True, check=False,
            timeout=_SCHED_CMD_TIMEOUT_SECONDS,
        ).stdout
        if "SwarmindMemoryBackup" in current:
            logger.info("  ✅ Cron ya registrado (SwarmindMemoryBackup)")
            return True
        new_cron = current.rstrip() + "\n" + cron_line + "  # SwarmindMemoryBackup\n"
        result = subprocess.run(
            ["crontab", "-"], input=new_cron, capture_output=True, text=True,
            check=False, timeout=_SCHED_CMD_TIMEOUT_SECONDS,
        )
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
            capture_output=True, text=True, check=False,
            timeout=_SCHED_CMD_TIMEOUT_SECONDS,
        )
        if result.returncode == 0:
            logger.info("  ✅ Tarea programada eliminada")
            return True
        logger.warning("  ⚠️  No se pudo eliminar tarea (¿existe?).")
        return False
    # Linux: filtrar linea
    try:
        current = subprocess.run(
            ["crontab", "-l"], capture_output=True, text=True, check=False,
            timeout=_SCHED_CMD_TIMEOUT_SECONDS,
        ).stdout
        filtered = "\n".join(
            line for line in current.splitlines()
            if "SwarmindMemoryBackup" not in line
        ) + "\n"
        subprocess.run(
            ["crontab", "-"], input=filtered, capture_output=True, text=True,
            check=False, timeout=_SCHED_CMD_TIMEOUT_SECONDS,
        )
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
            partes: list[str] = []
            if (b / "ruscadb" / "ruscadb.db").is_file():
                partes.append("RuscaDB")
            cols = _count_lance_collections(b / "lancedb")
            if cols:
                partes.append(f"LanceDB {cols} colecciones")
            logger.info("  📦 %-30s (%s)", b.name, " + ".join(partes) or "vacío")
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
