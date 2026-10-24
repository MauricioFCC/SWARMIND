"""Bootstrap y migración de la memoria colectiva (ciclo 11.20 — spec memory-lifecycle).

WHAT: primer-paso de instalación cross-platform (win/linux/mac) de la
memoria colectiva ``~/Documents/Memory_Proyects`` (override ``MEMORY_ROOT``):

- ``bootstrap_memory``: crea ``data/lancedb`` + ``backups`` +
  ``.swarmind_config.json`` (idempotente, shape mergeable con
  ``scripts/backup_memory.py``).
- ``detect_project_local_memory``: identifica forks locales del proyecto
  (``harness/db/lancedb`` con tablas ``*.lance``).
- ``migrate_local_to_central``: fusiona por tablas — ausente en central
  => copia filas; no volátil más nueva => append; volátil o más vieja =>
  skip (doctrina: caches regenerables jamás se migran/respaldan).
- ``prune_volatile_collections``: elimina colecciones volátiles que
  exceden ``VOLATILE_MAX_BYTES`` (se regeneran; ahorra GB).

WHY: sin ``.swarmind_config.json`` el harness cae al fallback legacy
``harness/db/lancedb`` y creó un fork de 4.8 GB (arXiv:2607.21503:
memoria como ciclo de vida, no store; forgetting con política).

WHERE: ``harness/memory_rag/memory_bootstrap.py``; cableado en
``scripts/setup_swarmind.py`` (paso ``_bootstrap_memory``).
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from pathlib import Path

import lancedb

logger = logging.getLogger("harness.memory_rag.memory_bootstrap")

#: Colecciones VOLATILES (regenerables): jamás migrar ni respaldar.
#: Coinciden con backup_memory._BACKUP_EXCLUDE_COLLECTIONS (doctrina).
VOLATILE_COLLECTIONS: frozenset[str] = frozenset(
    {"semantic_cache", "agent_workspace_logs"}
)

#: Tope por colección volátil (1 GB). Excedido => se elimina y regenera.
#: Tope por coleccion volatil (256 MiB). Excedido => se elimina y regenera.
#: WHY cota efectiva (Item 3): la cache regenerable no debe dominar el SSOT.
#: En 2026-10 semantic_cache alcanzo 138 MB (5201 fragments) mientras las 13
#: colecciones de VALOR sumaban ~0.3 MB: 99.7% del almacenamiento era cache.
#: Bajar la cota de 1 GiB a 256 MiB acota ese dominio sin perder recall
#: (la cache se regenera; el valor es lo persiste).
VOLATILE_MAX_BYTES = 268_435_456

_BYTES_PER_MB = 1_048_576


@dataclass(frozen=True)
class BootstrapReport:
    """Resultado de ``bootstrap_memory``.

    Attributes:
        memory_root: Raiz de la memoria colectiva.
        data_dir: Directorio ``data/lancedb``.
        backups_dir: Directorio ``backups``.
        config_file: Ruta al ``.swarmind_config.json``.
        created: True si la config fue creada en esta ejecución.
    """

    memory_root: Path
    data_dir: Path
    backups_dir: Path
    config_file: Path
    created: bool


@dataclass(frozen=True)
class LocalFork:
    """Memoria local detectada en un proyecto.

    Attributes:
        db_dir: Directorio ``harness/db/lancedb``.
        tables: Nombres de tablas ``*.lance`` presentes.
    """

    db_dir: Path
    tables: tuple[str, ...]


@dataclass(frozen=True)
class MigrationReport:
    """Resultado de ``migrate_local_to_central``.

    Attributes:
        copied: Tablas copiadas completas (ausentes en central).
        appended: Tablas no volátiles con append de filas nuevas.
        skipped_volatile: Volátiles ignoradas (regenerables).
        skipped_stale: Tablas más viejas que el central (central gana).
    """

    copied: tuple[str, ...]
    appended: tuple[str, ...]
    skipped_volatile: tuple[str, ...]
    skipped_stale: tuple[str, ...]


def default_memory_root() -> Path:
    """Raiz de la memoria colectiva (cross-platform).

    Prioridad: env ``MEMORY_ROOT`` > ``~/Documents/Memory_Proyects``.

    Returns:
        Path de la raiz (aunque no exista aún).
    """
    env_root = os.environ.get("MEMORY_ROOT", "")
    if env_root:
        return Path(env_root)
    return Path.home() / "Documents" / "Memory_Proyects"


def bootstrap_memory(root: Path | None = None) -> BootstrapReport:
    """Crea la memoria colectiva si no existe (primera instalación).

    WHAT: ``<root>/{data/lancedb,backups}`` + ``.swarmind_config.json``
    con ``memory_root`` (shape mergeable con backup_memory._DEFAULTS).
    WHY: ``memory_config`` solo apunta al central si el config SSOT existe;
    sin él cae al fork legacy del proyecto.
    WHERE: primer paso de ``setup_swarmind.py``.

    Args:
        root: Raiz opcional (default ``default_memory_root()``).

    Returns:
        BootstrapReport con rutas y flag ``created``.
    """
    memory_root = root if root is not None else default_memory_root()
    data_dir = memory_root / "data" / "lancedb"
    backups_dir = memory_root / "backups"
    config_file = memory_root / ".swarmind_config.json"

    data_dir.mkdir(parents=True, exist_ok=True)
    backups_dir.mkdir(parents=True, exist_ok=True)

    created = not config_file.is_file()
    if created:
        config = {
            "memory_root": str(memory_root),
            "backup_enabled": True,
            "backup_interval_hours": 24,
            "backup_cadence": "daily",
            "backup_keep": 5,
            "cleanup_duplicates": True,
            "auto_import_db": False,
        }
        config_file.write_text(
            json.dumps(config, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        logger.info("bootstrap: config creada en %s", config_file)

    return BootstrapReport(
        memory_root=memory_root,
        data_dir=data_dir,
        backups_dir=backups_dir,
        config_file=config_file,
        created=created,
    )


def detect_project_local_memory(project_root: Path) -> LocalFork | None:
    """Detecta fork de memoria local del proyecto (cualquier SO).

    WHAT: busca ``<project>/harness/db/lancedb`` con tablas ``*.lance``.
    WHY: identificar memoria que debe fusionarse al central antes de que
    el runtime siga escribiendo en el fallback legacy.
    WHERE: paso de migración de ``setup_swarmind.py``.

    Args:
        project_root: Raiz del proyecto SWARMIND.

    Returns:
        LocalFork con tablas, o None si no hay fork local.
    """
    db_dir = project_root / "harness" / "db" / "lancedb"
    if not db_dir.is_dir():
        return None
    tables = tuple(
        sorted(
            p.name.removesuffix(".lance")
            for p in db_dir.iterdir()
            if p.is_dir() and p.name.endswith(".lance")
        )
    )
    if not tables:
        return None
    return LocalFork(db_dir=db_dir, tables=tables)


def _list_tables(db: object, db_dir: Path | None = None) -> set[str]:
    """Nombres de tablas via API + listing de directorio (robusto).

    WHAT: combina ``list_tables().tables`` con los dirs ``*.lance`` del
    filesystem (source of truth). Fusiona ambos porque la API de lancedb
    puede no reflejar tablas creadas en la misma sesión (cache interno).
    WHY: en migraciones que crean tablas y luego las reabren, la API
    devuelve stale; el directorio siempre está actualizado.
    WHERE: helper privado de ``migrate_local_to_central`` y
    ``prune_volatile_collections``.

    Args:
        db: Conexion ``lancedb.connect(...)``.
        db_dir: Directorio de la base (opcional, para listing directo).

    Returns:
        Conjunto de nombres de tabla (unión API + filesystem).
    """
    names = set(db.list_tables().tables)  # type: ignore[attr-defined]
    if db_dir is not None and db_dir.is_dir():
        names |= {
            p.name.removesuffix(".lance")
            for p in db_dir.iterdir()
            if p.is_dir() and p.name.endswith(".lance")
        }
    return names


def _table_mtime(db_dir: Path, table: str) -> float:
    """mtime máximo (epoch) de los archivos de una tabla .lance."""
    table_dir = db_dir / f"{table}.lance"
    return max(
        (p.stat().st_mtime for p in table_dir.rglob("*") if p.is_file()),
        default=0.0,
    )


def migrate_local_to_central(
    local_db: Path,
    central_db: Path,
    *,
    force_newer: bool | None = None,
) -> MigrationReport:
    """Fusiona la memoria local del proyecto hacia el central.

    WHAT: por tabla local: ausente en central => copia todas las filas;
    volátil => skip (regenerable); mtime local <= central => skip (stale);
    si no => append de filas (central += local). Determinista y auditable.
    WHY: el fork local nació de un fallback silencioso; el central es SSOT.
    WHERE: ``setup_swarmind.py`` tras ``bootstrap_memory``.

    Args:
        local_db: Directorio ``harness/db/lancedb`` local.
        central_db: Directorio ``data/lancedb`` del central.
        force_newer: Override de comparación de mtime en tests
            (None = comparar mtimes reales).

    Returns:
        MigrationReport con tablas copiadas/appended/skipped.
    """
    central_db.mkdir(parents=True, exist_ok=True)
    central_conn = lancedb.connect(str(central_db))
    central_names = _list_tables(central_conn, central_db)

    copied: list[str] = []
    appended: list[str] = []
    skipped_volatile: list[str] = []
    skipped_stale: list[str] = []

    for table in sorted(_list_tables(lancedb.connect(str(local_db)), local_db)):
        try:
            rows = lancedb.connect(str(local_db)).open_table(table).to_arrow()
        except Exception as e:  # noqa: BLE001 — tabla corrupta/ilegible, skip
            logger.warning(
                "Tabla '%s' corrupta/ilegible en local (%s) → skip",
                table, e
            )
            skipped_stale.append(table)
            continue
        if table in VOLATILE_COLLECTIONS:
            skipped_volatile.append(table)
            continue
        if table not in central_names:
            central_conn.create_table(table, data=rows)
            copied.append(table)
            continue
        is_newer = (
            force_newer
            if force_newer is not None
            else _table_mtime(local_db, table) > _table_mtime(central_db, table)
        )
        if is_newer:
            central_conn.open_table(table).add(rows)
            appended.append(table)
        else:
            skipped_stale.append(table)

    report = MigrationReport(
        copied=tuple(copied),
        appended=tuple(appended),
        skipped_volatile=tuple(skipped_volatile),
        skipped_stale=tuple(skipped_stale),
    )
    logger.info(
        "migracion local->central: copied=%d appended=%d "
        "skipped_volatile=%d skipped_stale=%d",
        len(report.copied), len(report.appended),
        len(report.skipped_volatile), len(report.skipped_stale),
    )
    return report


def _table_bytes(db_dir: Path, table: str) -> int:
    """Tamaño en bytes de una tabla .lance."""
    table_dir = db_dir / f"{table}.lance"
    return sum(p.stat().st_size for p in table_dir.rglob("*") if p.is_file())


def prune_volatile_collections(
    central_db: Path,
    max_bytes: int = VOLATILE_MAX_BYTES,
) -> list[str]:
    """Elimina colecciones volátiles que exceden el tope de tamaño.

    WHAT: ``semantic_cache``/``agent_workspace_logs`` son regenerables
    (doctrina backup_memory.py); si superan ``max_bytes`` se eliminan
    enteras para que el runtime las regenere limpias.
    WHY: una cache sin política TTL/tamaño es deuda — en producción las
    caches LLM requieren invalidación (frontera 2026); 5 GB de cache en
    el SSOT solo enlentece backups y búsqueda sin aportar recall.
    WHERE: rutina de mantenimiento (setup + !db).

    Args:
        central_db: Directorio ``data/lancedb`` del central.
        max_bytes: Tope por colección volátil.

    Returns:
        Lista ordenada de colecciones eliminadas.
    """
    db = lancedb.connect(str(central_db))
    removed: list[str] = []
    for table in sorted(_list_tables(db) & VOLATILE_COLLECTIONS):
        size = _table_bytes(central_db, table)
        if size > max_bytes:
            db.drop_table(table)
            removed.append(table)
            logger.info(
                "prune: volatil '%s' eliminada (%.1f MB > cap %.1f MB); "
                "se regenera en el proximo uso",
                table, size / _BYTES_PER_MB, max_bytes / _BYTES_PER_MB,
            )
    return removed
