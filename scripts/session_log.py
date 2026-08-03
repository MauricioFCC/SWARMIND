#!/usr/bin/env python3
"""
session_log.py — Session Log con busqueda semantica en LanceDB.

Guarda decisiones de sesion en la cognition_store de LanceDB
para que el LLM pueda consultarlas por similitud semantica.
Mejor que un .md plano: permite busqueda por significado.

Uso:
    python scripts/session_log.py add "Titulo" --content "Detalle" --domain "dom" --tags "a,b,c"
    python scripts/session_log.py search "consulta semantica" --limit 5
    python scripts/session_log.py list --limit 10
    python scripts/session_log.py last
"""

from __future__ import annotations

import argparse
import logging
import sys
from typing import Any

logging.basicConfig(level=logging.ERROR)
logger = logging.getLogger(__name__)


def _get_cognition():
    """Inicializa CognitionSync."""
    try:
        from harness.evolve_loop.cognition_sync import CognitionSync
        from harness.memory_rag.lance_vector_store import LanceVectorStore
        store = LanceVectorStore()
        return CognitionSync(store)
    except ImportError as e:
        print(f"Error: No se pudo importar. Ejecuta desde la raiz del proyecto: {e}")
        sys.exit(1)
    except Exception as e:  # noqa: BLE001 - init defensivo
        print(f"Error al inicializar: {e}")
        sys.exit(1)


def _lesson_to_dict(lesson) -> dict[str, Any]:
    """Convierte CognitionLesson a dict."""
    return {
        "id": getattr(lesson, "id", "N/A"),
        "title": getattr(lesson, "title", "N/A"),
        "content": getattr(lesson, "content", ""),
        "domain": getattr(lesson, "domain", ""),
        "tags": getattr(lesson, "tags", []),
        "metrics": getattr(lesson, "metrics", {}),
        "created_at": getattr(lesson, "created_at", ""),
    }


def cmd_add(args: argparse.Namespace) -> None:
    """Agrega decision a cognition_store."""
    cog = _get_cognition()
    tags = [t.strip() for t in (args.tags or "").split(",") if t.strip()]

    leccion = cog.add_lesson(
        title=args.title,
        content=args.content,
        domain=args.domain or "session_log",
        tags=tags,
        metrics={},
    )
    d = _lesson_to_dict(leccion)
    print(f"Guardado: {d['id']}")
    print(f"  Titulo: {d['title']}")
    print(f"  Dominio: {d['domain']}")
    print(f"  Tags: {tags}")
    if args.metrics:
        print("  Nota: Las metricas deben pasarse como JSON valido: '{\"k\":\"v\"}'")


def cmd_search(args: argparse.Namespace) -> None:
    """Busqueda semantica en cognition_store."""
    cog = _get_cognition()
    resultados = cog.search_lessons(query=args.query, top_k=args.limit)
    _print_resultados(resultados, f"Busqueda: '{args.query}'")


def cmd_list(args: argparse.Namespace) -> None:
    """Lista lecciones recientes."""
    cog = _get_cognition()
    resultados = cog.search_lessons(query="session decision log", top_k=args.limit)
    _print_resultados(resultados, "Decisiones recientes")


def cmd_last(args: argparse.Namespace) -> None:
    """Muestra la ultima decision."""
    cog = _get_cognition()
    resultados = cog.search_lessons(query="session decision log", top_k=2)
    if not resultados:
        print("No hay sesiones registradas.")
        return
    r = resultados[0]
    d = _lesson_to_dict(r)
    print(f"\n{'=' * 60}")
    print("  Ultima decision")
    print(f"{'=' * 60}")
    print(f"  ID:       {d['id']}")
    print(f"  Titulo:   {d['title']}")
    print(f"  Dominio:  {d['domain']}")
    print(f"  Tags:     {d['tags']}")
    print(f"  Fecha:    {d['created_at']}")
    contenido = d['content'][:300] + "..." if len(d['content']) > 300 else d['content']
    print(f"\n  {contenido}")
    print(f"{'=' * 60}\n")


def _print_resultados(resultados, titulo: str) -> None:
    """Imprime resultados."""
    if not resultados:
        print(f"\n  Sin resultados: {titulo}")
        return
    print(f"\n{'=' * 60}")
    print(f"  {titulo} ({len(resultados)} resultados)")
    print(f"{'=' * 60}")
    for i, r in enumerate(resultados, 1):
        d = _lesson_to_dict(r)
        print(f"\n  [{i}] {d['title']}")
        print(f"      Dominio: {d['domain']}")
        print(f"      Tags: {d['tags']}")
        print(f"      Fecha: {d['created_at']}")
        c = d['content'][:180] + "..." if len(d['content']) > 180 else d['content']
        print(f"      {c}")
    print()


def main() -> None:
    parser = argparse.ArgumentParser(description="Session Log semantico en LanceDB")
    sub = parser.add_subparsers(dest="command")

    p = sub.add_parser("add", help="Agregar decision")
    p.add_argument("title", type=str)
    p.add_argument("--content", "-c", type=str, required=True)
    p.add_argument("--domain", "-d", type=str, default="session_log")
    p.add_argument("--tags", "-t", type=str, default="")
    p.add_argument("--metrics", "-m", type=str, default=None,
                   help='Metricas como JSON string: {"k":"v"}')

    p = sub.add_parser("search", help="Busqueda semantica")
    p.add_argument("query", type=str)
    p.add_argument("--limit", "-l", type=int, default=5)

    p = sub.add_parser("list", help="Listar recientes")
    p.add_argument("--limit", "-l", type=int, default=10)

    sub.add_parser("last", help="Ultima decision")

    args = parser.parse_args()

    if args.command == "add":
        cmd_add(args)
    elif args.command == "search":
        cmd_search(args)
    elif args.command == "list":
        cmd_list(args)
    elif args.command == "last":
        cmd_last(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
