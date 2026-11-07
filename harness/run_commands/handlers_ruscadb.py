"""Comandos ``!db`` nativos de RuscaDB: capacidades, salud, backup y GC.

Aprovechan las APIs que el store ya implementa (integridad, LSN, cache de
consultas, búsqueda binaria, grafo, backup online y GC de blobs) en lugar de
mirar solo el tamaño del archivo. Todos son de solo lectura salvo ``backup``,
``gc`` y ``reconcile`` (explícitos).
"""

from __future__ import annotations

from typing import Any

import harness.run_commands as _rc
from harness.memory_rag.ruscadb_capabilities import probe, recommendations


def _call(store: Any, name: str, default: Any = None) -> Any:
    """Invoca ``store.name()`` si existe; devuelve ``default`` si no."""
    method = getattr(store, name, None)
    if not callable(method):
        return default
    try:
        return method()
    except Exception as exc:  # el comando reporta, no rompe
        return f"error: {type(exc).__name__}: {exc}"


def _call1(store: Any, name: str, arg: Any, default: Any = None) -> Any:
    """Invoca ``store.name(arg)`` si existe; devuelve ``default`` si no."""
    method = getattr(store, name, None)
    if not callable(method):
        return default
    try:
        return method(arg)
    except Exception as exc:
        return f"error: {type(exc).__name__}: {exc}"


def _handle_db_capabilities() -> None:
    """Handle ``!db capabilities``: qué expone la DLL y qué falta."""
    report = probe()
    _rc.logger.info("\n[DB] Capacidades RuscaDB (DLL cargada):")
    for name, item in sorted(report.features.items()):
        mark = "OK " if item.available else "NO "
        detail = "" if item.available else f" (falta: {', '.join(item.missing)})"
        _rc.logger.info("  [%s] %-18s%s", mark, name, detail)
    for line in recommendations(report):
        _rc.logger.info("  %s", line)


def _handle_db_health(store: Any) -> None:
    """Handle ``!db health``: integridad, LSN, caches y grafo."""
    _rc.logger.info("\n[DB] Salud RuscaDB:")
    _rc.logger.info("  integridad: %s", _call(store, "integrity", "no disponible"))
    _rc.logger.info("  lsn:        %s", _call(store, "current_lsn", "no disponible"))
    _rc.logger.info("  query cache: %s", _call(store, "query_cache_stats", "no disponible"))
    _rc.logger.info("  binario:     %s", _call(store, "binary_search_stats", "no disponible"))
    for collection in _call(store, "list_collections", []) or []:
        stats = _call1(store, "graph_stats", collection, "no disponible")
        _rc.logger.info("  grafo[%s]: %s", collection, stats)


def _handle_db_stats(store: Any) -> None:
    """Handle ``!db stats``: colecciones y métricas del store activo."""
    collections = _call(store, "list_collections", []) or []
    _rc.logger.info("\n[DB] Estado RuscaDB: %d colecciones", len(collections))
    for name in collections:
        stats = _call1(store, "get_collection_stats", name, "sin stats")
        _rc.logger.info("  * %s: %s", name, stats)
    _rc.logger.info("  lsn: %s", _call(store, "current_lsn", "no disponible"))
    _rc.logger.info("  query cache: %s", _call(store, "query_cache_stats", "no disponible"))


def _handle_db_backup(store: Any, cmd: str) -> None:
    """Handle ``!db backup <destino>``: backup online del motor."""
    parts = cmd.split(maxsplit=2)
    if len(parts) < 3 or not parts[2].strip():
        _rc.logger.info("[DB] Uso: !db backup <ruta_destino>")
        return
    destination = parts[2].strip()
    try:
        written = store.backup(destination)
    except Exception as exc:
        _rc.logger.info("[DB] Backup falló: %s", exc)
        return
    _rc.logger.info("[DB] Backup creado en %s (%s bytes)", destination, written)


def _handle_db_gc(store: Any) -> None:
    """Handle ``!db gc``: recolecta blobs no referenciados."""
    _rc.logger.info("[DB] Blobs recolectados: %s", _call(store, "gc_blobs", 0))


def _handle_db_reconcile(store: Any) -> None:
    """Handle ``!db reconcile``: reconcilia colecciones con el motor."""
    _rc.logger.info("[DB] Reconciliación: %s", _call(store, "reconcile", {}))
