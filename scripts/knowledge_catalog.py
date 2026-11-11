#!/usr/bin/env python3
"""knowledge_catalog.py — catálogo de conocimiento de la memoria central.

Uso:
    python scripts/knowledge_catalog.py ingest docs/knowledge/catalog.seed.json
    python scripts/knowledge_catalog.py search "graph rag multi-hop" --top 5
    python scripts/knowledge_catalog.py search "cache" --kind technique --json
    python scripts/knowledge_catalog.py stats
    python scripts/knowledge_catalog.py graph paper:arxiv-2404.16130
    python scripts/knowledge_catalog.py export docs/knowledge/catalog.export.json
    python scripts/knowledge_catalog.py verify docs/knowledge/catalog.seed.json
    python scripts/knowledge_catalog.py feedback "graph rag" --ids paper:arxiv-2404.16130 --outcome useful
    python scripts/knowledge_catalog.py gaps

Exit: 0 = ok; 1 = error de datos/entorno; 2 = uso inválido.
Spec: docs/specs/knowledge-catalog.md.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(1, str(Path(__file__).resolve().parents[1]))  # SEG: raiz repo

from harness.memory_rag.knowledge_catalog import (
    EntryKind,
    KnowledgeCatalog,
)
from harness.memory_rag.knowledge_catalog_types import entry_from_json


def _paths(store: object) -> tuple[Path, Path]:
    """Deriva índice y grafo junto al archivo de la base de memoria.

    Args:
        store: Store con ``db_path``.

    Returns:
        ``(index_path, graph_path)`` dentro de ``<data>/``.
    """
    base = Path(str(getattr(store, "db_path", "ruscadb.db"))).parent
    return (
        base / "knowledge_catalog.index.json",
        base / "knowledge_catalog_graph.json",
    )


def _open_catalog() -> KnowledgeCatalog:
    """Abre el store central y construye el catálogo persistente."""
    from harness.memory_rag.ruscadb_store import RuscaDBStore

    store = RuscaDBStore()
    index_path, graph_path = _paths(store)
    return KnowledgeCatalog(
        store, index_path=index_path, graph_path=graph_path
    )


def _cmd_ingest(args: argparse.Namespace) -> int:
    """Indexa un seed JSON en la memoria central."""
    catalog = _open_catalog()
    report = catalog.ingest(Path(args.path))
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if not report["errors"] else 1


def _cmd_search(args: argparse.Namespace) -> int:
    """Busca en el catálogo (híbrido + grafo)."""
    catalog = _open_catalog()
    kind = EntryKind(args.kind) if args.kind else None
    hits = catalog.search(
        args.query, top_k=args.top, kind=kind, expand=not args.no_expand
    )
    if args.json:
        print(json.dumps(hits, indent=2, ensure_ascii=False))
        return 0
    if not hits:
        print("sin resultados")
        return 0
    for hit in hits:
        print(f"[{hit['score']:.4f}] {hit['kind']:<12} {hit['catalog_id']}")
        print(f"         {hit['title']}")
        print(f"         {hit['url']}  ({', '.join(hit['sources'])})")
    return 0


def _cmd_stats(args: argparse.Namespace) -> int:
    """Muestra el resumen del catálogo y su uso (salud del conocimiento)."""
    catalog = _open_catalog()
    stats = catalog.stats()
    stats["usage"] = catalog.usage_stats()
    print(json.dumps(stats, indent=2, ensure_ascii=False))
    return 0


def _cmd_graph(args: argparse.Namespace) -> int:
    """Lista vecinos de una entrada en el grafo tipado."""
    catalog = _open_catalog()
    vecinos = catalog.graph.query(f"catalog:{args.catalog_id}", max_depth=1)
    if args.reverse:
        vecinos += catalog.graph.query(
            f"catalog:{args.catalog_id}", max_depth=1, reverse=True
        )
    for vecino in vecinos:
        print(f"{vecino['relation']:<12} {vecino['node']}")
    return 0 if vecinos else 1


def _cmd_export(args: argparse.Namespace) -> int:
    """Exporta el catálogo a JSON canónico."""
    destino = _open_catalog().export(Path(args.path))
    print(f"exportado: {destino}")
    return 0


def _cmd_feedback(args: argparse.Namespace) -> int:
    """Registra el resultado de una consulta (ciclo de vida del catálogo)."""
    catalog = _open_catalog()
    ids = tuple(x for x in args.ids.split(",") if x) if args.ids else ()
    record = catalog.record_usage(
        args.query, ids, outcome=args.outcome, note=args.note
    )
    print(json.dumps(record.to_dict() if record else {}, ensure_ascii=False))
    if args.outcome == "missing":
        print(
            "GAP: añade la fuente al seed local y reingiere para no perder efectividad.",
            file=sys.stderr,
        )
    return 0


def _cmd_gaps(args: argparse.Namespace) -> int:
    """Lista los gaps abiertos (consultas con outcome ``missing``)."""
    resumen = _open_catalog().usage_stats(top=args.top)
    print(json.dumps(resumen.get("gaps", []), indent=2, ensure_ascii=False))
    return 0


def _cmd_verify(args: argparse.Namespace) -> int:
    """Valida un seed sin escribir en la memoria (no abre el store)."""
    payload = json.loads(Path(args.path).read_text(encoding="utf-8"))
    crudas = payload.get("entries", payload) if isinstance(payload, dict) else payload
    errores: list[str] = []
    for item in crudas:
        try:
            entry_from_json(item)
        except (KeyError, ValueError) as exc:
            errores.append(f"{item.get('url', '?')}: {exc}")
    if errores:
        for error in errores:
            print(f"INVALIDO: {error}", file=sys.stderr)
        return 1
    print(f"OK: {len(crudas)} entradas válidas")
    return 0


def _add_query_parsers(sub: argparse._SubParsersAction) -> None:
    """Registra los subcomandos de consulta (search/graph)."""
    p_search = sub.add_parser("search", help="búsqueda híbrida + grafo")
    p_search.add_argument("query")
    p_search.add_argument("--top", type=int, default=5)
    p_search.add_argument("--kind", choices=[k.value for k in EntryKind], default=None)
    p_search.add_argument("--no-expand", action="store_true")
    p_search.add_argument("--json", action="store_true")
    p_search.set_defaults(func=_cmd_search)

    p_graph = sub.add_parser("graph", help="vecinos de una entrada")
    p_graph.add_argument("catalog_id")
    p_graph.add_argument("--reverse", action="store_true")
    p_graph.set_defaults(func=_cmd_graph)


def _add_data_parsers(sub: argparse._SubParsersAction) -> None:
    """Registra los subcomandos de datos y ciclo de vida."""
    p_ingest = sub.add_parser("ingest", help="indexa un seed JSON")
    p_ingest.add_argument("path")
    p_ingest.set_defaults(func=_cmd_ingest)

    p_stats = sub.add_parser("stats", help="resumen del catálogo")
    p_stats.set_defaults(func=_cmd_stats)

    p_export = sub.add_parser("export", help="exporta a JSON")
    p_export.add_argument("path")
    p_export.set_defaults(func=_cmd_export)

    p_feedback = sub.add_parser("feedback", help="registra el uso de una consulta")
    p_feedback.add_argument("query")
    p_feedback.add_argument("--ids", default="", help="catalog_ids separados por coma")
    p_feedback.add_argument(
        "--outcome", choices=["useful", "stale", "missing"], default="useful"
    )
    p_feedback.add_argument("--note", default="")
    p_feedback.set_defaults(func=_cmd_feedback)

    p_gaps = sub.add_parser("gaps", help="lista los gaps abiertos (missing)")
    p_gaps.add_argument("--top", type=int, default=10)
    p_gaps.set_defaults(func=_cmd_gaps)

    p_verify = sub.add_parser("verify", help="valida un seed (sin store)")
    p_verify.add_argument("path")
    p_verify.set_defaults(func=_cmd_verify)


def _build_parser() -> argparse.ArgumentParser:
    """Parser CLI con subcomandos (consulta + datos/ciclo de vida)."""
    parser = argparse.ArgumentParser(description="Catálogo de conocimiento SWARMIND")
    sub = parser.add_subparsers(dest="cmd", required=True)
    _add_query_parsers(sub)
    _add_data_parsers(sub)
    return parser


def main(argv: list[str] | None = None) -> int:
    """Entrada CLI: despacha al subcomando y devuelve su exit code."""
    args = _build_parser().parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
