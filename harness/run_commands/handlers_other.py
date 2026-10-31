"""run_commands handlers varios (rag/db/hooks/evolve/schedule/watch)."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import harness.run_commands as _rc
from harness.self_update import (
    Action,
    apply_update,
    audit_log,
    check_remote,
    fmt_version,
)


def _handle_rag_ingest(store, cmd: str) -> None:
    """Handle ``!rag ingest [--dir <path>] [--docs]``."""
    from harness.memory_rag.doc_ingester import ingest_project_directory

    parts = cmd.split()
    target_dir = None
    if "--dir" in parts:
        idx = parts.index("--dir")
        target_dir = parts[idx + 1] if idx + 1 < len(parts) else None
    include_docs = "--docs" in parts

    if target_dir:
        directory = Path(target_dir).resolve()
    else:
        # Default: project root (excluye harness/ y .opencode/ por RAG_EXCLUDE)
        directory = Path(__file__).resolve().parent.parent.parent

    if not directory.is_dir():
        _rc.logger.info("[RAG] Directorio no encontrado: %s", directory)
        return

    _rc.logger.info("[RAG] Ingestando desde: %s (docs=%s)", directory, include_docs)
    start = _rc.time.time()
    try:
        stats = ingest_project_directory(
            str(directory), show_progress=True, include_docs=include_docs
        )
        elapsed = _rc.time.time() - start
        _rc.logger.info(
            "[RAG] \u2705 Completado: %d archivos, %d chunks en %.1fs",
            stats.get("files_processed", 0),
            stats.get("chunks_inserted", 0),
            elapsed,
        )
        if stats.get("errors", 0):
            _rc.logger.warning("[RAG] \u26a0\ufe0f %d errores", stats["errors"])
    except Exception as e:  # noqa: BLE001
        _rc.logger.error("[RAG] \u274c Error: %s", e)


def _handle_rag_search(store, cmd: str) -> None:
    """Handle ``!rag search <consulta>`` — recuperacion dual-level (GraphRAG).

    Combina BM25 (nivel local) y expansion por grafo (nivel global) sobre
    RuscaDB; si la coleccion no tiene aristas, degrada a busqueda FTS.
    """
    from harness.memory_rag.graph_rag_retriever import GraphRAGRetriever

    query = cmd[len("!rag search") :].strip()
    if not query:
        _rc.logger.info("[RAG] Uso: !rag search <consulta>")
        return
    collections = store.list_collections()
    collection = "rag_chunks" if "rag_chunks" in collections else "memory"
    if collection not in collections:
        _rc.logger.info("[RAG] No hay colecciones con contenido. Ejecuta '!rag ingest'.")
        return
    retriever = GraphRAGRetriever(store, collection=collection, depth=2)
    results = retriever.retrieve(query, top_k=5)
    if not results:
        _rc.logger.info("[RAG] Sin resultados para: %s", query)
        return
    _rc.logger.info("[RAG] %d resultados en '%s':", len(results), collection)
    for rank, item in enumerate(results, start=1):
        text = (item.get("text") or "").replace("\n", " ")[:160]
        _rc.logger.info("  %d. [%.4f] %s", rank, item.get("score", 0.0), text)


def _handle_rag_stats(store) -> None:
    """Handle ``!rag stats`` — muestra estadisticas de la BD RAG."""
    colls = store.list_collections()
    _rc.logger.info("")
    _rc.logger.info("[RAG] Colecciones disponibles: %s", colls)
    if "rag_chunks" in colls:
        try:
            stats = store.get_collection_stats("rag_chunks")
            _rc.logger.info("[RAG] Coleccion 'rag_chunks':")
            _rc.logger.info("  Items: %d", stats.get("item_count", 0))
            _rc.logger.info("  Ultima actualizacion: %s", stats.get("last_updated", "N/A"))
        except Exception as exc:  # noqa: BLE001
            _rc.logger.info("[RAG] Coleccion 'rag_chunks' existe (error al obtener stats: %s)", exc)
            _rc.logger.info("  (Esto es normal si la BD esta vacia o es una version reciente de LanceDB)")
    else:
        _rc.logger.info("[RAG] Coleccion 'rag_chunks' no existe. Ejecuta '!rag ingest'.")
    _rc.logger.info("")


# ── DB Commands ──────────────────────────────────────────────────────

def _handle_db_migrate(store, cmd: str) -> None:
    """Handle ``!db migrate [--path <ruta>]``."""
    from harness.db.migrate_db import DBMigrator
    migrator = DBMigrator()
    parts = cmd.split()
    if "--path" in parts:
        idx = parts.index("--path")
        custom_path = parts[idx + 1] if idx + 1 < len(parts) else None
        if custom_path:
            result = migrator.migrate(custom_path)
        else:
            _rc.logger.info("[DB] Especifica una ruta: !db migrate --path <ruta>")
            return
    else:
        imports = migrator.scan_imports()
        if not imports:
            _rc.logger.info("[DB] No hay bases para migrar.")
            return
        for imp in imports:
            _rc.logger.info(f"[DB] Migrando '{imp['name']}'...")
            result = migrator.migrate(imp["path"])
    if result.get("migrated_collections"):
        _rc.logger.info("[DB] Migradas: {}".format(", ".join(result["migrated_collections"])))
    if result.get("created"):
        _rc.logger.info("[DB] Creadas: {}".format(", ".join(result["created"])))
    for s in result.get("skipped", []):
        _rc.logger.info(f"[DB] SKIP: {s}")
    for e in result.get("errors", []):
        _rc.logger.info(f"[DB] ERROR: {e}")
    if result.get("backup_path"):
        _rc.logger.info("[DB] Backup: {}".format(result["backup_path"]))


def _handle_db_list_imports() -> None:
    """Handle ``!db list-imports``."""
    from harness.db.migrate_db import DBMigrator
    migrator = DBMigrator()
    imports = migrator.scan_imports()
    if imports:
        _rc.logger.info(f"\n[DB] Bases detectadas ({len(imports)}):")
        for imp in imports:
            colls = ", ".join(imp["collections"])
            _rc.logger.info("  * {}: {} ({})".format(imp["name"], colls, imp["estimated_size_human"]))
    else:
        _rc.logger.info("[DB] No se detectaron bases de datos en import/")


def _handle_db_stats(store: Any) -> None:
    """Handle ``!db stats``."""
    from harness.db.migrate_db import DBMigrator
    migrator = DBMigrator()
    stats = migrator.get_stats()
    _rc.logger.info("\n[DB] Estadisticas de BD activa:")
    _rc.logger.info("  Path:   {}".format(stats.get("path", "N/A")))
    _rc.logger.info("  Chunks: {}".format(stats["total_chunks"]))
    _rc.logger.info("  Tamano: {}".format(stats.get("size_human", "N/A")))
    _rc.logger.info("  Ultima mod: {}".format(stats.get("last_modified", "N/A")))
    _rc.logger.info("  Colecciones:")
    for coll in stats["collections"]:
        count = coll["count"]
        if count >= 0:
            _rc.logger.info("  * {}: {} registros".format(coll["name"], count))
        else:
            _rc.logger.info("  * {}: ERROR {}".format(coll["name"], coll.get("error", "")))


def _handle_db_rollback(cmd: str) -> None:
    """Handle ``!db rollback <backup_path>``."""
    from harness.db.migrate_db import DBMigrator
    parts = cmd.split(maxsplit=2)
    if len(parts) < 2:
        _rc.logger.info("[DB] Uso: !db rollback <ruta_del_backup>")
        return
    backup_path = parts[2] if len(parts) > 2 else ""
    if not backup_path:
        _rc.logger.info("[DB] Uso: !db rollback <ruta_del_backup>")
        return
    migrator = DBMigrator()
    success = migrator.rollback(backup_path)
    if success:
        _rc.logger.info(f"[DB] Base restaurada desde: {backup_path}")
    else:
        _rc.logger.info(f"[DB] Error al restaurar desde: {backup_path}")


# ── Iteration End ───────────────────────────────────────────────────















# ── Hooks ────────────────────────────────────────────────────────────

def _handle_hooks_install() -> None:
    """Handle ``!hooks install`` — installs the pre-commit hook."""
    from harness.scripts.install_hooks import install_hook
    _rc.logger.info("[Harness] Instalando hook pre-commit...")
    install_hook()


def _handle_hooks_uninstall() -> None:
    """Handle ``!hooks uninstall`` — uninstalls the pre-commit hook."""
    from harness.scripts.install_hooks import uninstall_hook
    _rc.logger.info("[Harness] Desinstalando hook pre-commit...")
    uninstall_hook()

__all__ = [
    "_handle_db_list_imports",
    "_handle_db_migrate",
    "_handle_db_rollback",
    "_handle_db_stats",
    "_handle_hooks_install",
    "_handle_hooks_uninstall",
    "_handle_rag_ingest",
    "_handle_rag_stats",
]

# ---------------------------------------------------------------------------
# !update (self-update desde runtime; spec self-update-notice.md)
# ---------------------------------------------------------------------------


def _handle_update(cmd: str, harness_root: Path | None) -> None:
    """``!update check|apply|audit``: auto-actualizacion con guards.

    Rutea a las funciones puras de ``harness.self_update`` usando el journal
    default del repo (``.swarmind/update_log.jsonl``). El ``apply`` respeta los
    guards anti-reversion (ff-only, dirty worktree, max_seen); el downgrade
    forzado requiere ``--allow-downgrade`` y ``--justification=...``.
    """
    repo = Path(harness_root or Path.cwd()).resolve()
    log_path = repo / ".swarmind" / "update_log.jsonl"
    accion, allow_downgrade, justification = _parse_update_args(cmd)
    check = check_remote(repo) if accion in {"check", "apply"} else None
    if accion == "check":
        _log_update_check(check)
        return
    if accion == "audit":
        violations = audit_log(log_path)
        _rc.logger.info(
            "!update audit | violaciones=%d %s",
            len(violations),
            violations[:5],
        )
        return
    _apply_update_with_guards(repo, log_path, check, allow_downgrade, justification)


def _parse_update_args(cmd: str) -> tuple[str, bool, str]:
    """Parsea ``!update``: accion (default check), flag y justification."""
    tokens = cmd.split()[1:]
    accion = next((t for t in tokens if t in {"check", "apply", "audit"}), "check")
    allow = "--allow-downgrade" in tokens
    justification = ""
    for token in tokens:
        if token.startswith("--justification="):
            justification = token.split("=", 1)[1].strip()
    return accion, allow, justification


def _log_update_check(check) -> None:
    """Log del estado frente al remoto (sin mutar nada)."""
    remote_v = check.remote_version
    _rc.logger.info(
        "!update | estado=%s behind=%d ahead=%d local=%s remote=%s",
        check.state.value,
        check.behind,
        check.ahead,
        fmt_version(check.local_version),
        fmt_version(remote_v) if remote_v is not None else "?",
    )


def _apply_update_with_guards(
    repo: Path, log_path: Path, check, allow: bool, justification: str
) -> None:
    """Aplica con los guards anti-reversion y reporta el resultado."""
    result = apply_update(
        check,
        repo=repo,
        log_path=log_path,
        allow_downgrade=allow,
        downgrade_justification=justification,
    )
    _rc.logger.info(
        "!update | accion=%s changed=%s detail=%s from=%s to=%s",
        result.action.value,
        result.changed,
        result.detail,
        fmt_version(result.from_version),
        fmt_version(result.to_version),
    )
    if result.action is Action.FAILED:
        _rc.logger.error("!update | apply fallo: %s", result.detail)
