#!/usr/bin/env python3
"""
Agent Notes — Structured note-taking tool (Anthropic-style agentic memory).

Los agentes pueden escribir notas estructuradas que persisten entre sesiones.
Implementa el patron NOTES.md de Anthropic: el agente escribe notas regularmente
y las recupera cuando necesita contexto de sesiones anteriores.

Uso:
    python harness/scripts/agent_notes.py write "investigacion" "Transformers: atencion es O(n^2)"
    python harness/scripts/agent_notes.py list
    python harness/scripts/agent_notes.py search "transformers"
    python harness/scripts/agent_notes.py recent --limit 5
    python harness/scripts/agent_notes.py export --format markdown
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np

sys.path.insert(1, str(Path(__file__).resolve().parent.parent.parent))
from harness.common import fallback_embedding\nfrom harness.memory_rag.lance_vector_store import LanceVectorStore

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)

NOTES_COLLECTION = "agent_notes"
EMBEDDING_DIM = 384


def _ensure_collection(store: LanceVectorStore) -> None:
    """Ensure agent_notes collection exists."""
    if NOTES_COLLECTION not in store.list_collections():
        store.create_collection(NOTES_COLLECTION)


# _embed removed: use common.fallback_embedding directly


def cmd_write(args: argparse.Namespace) -> None:
    """Write a structured note."""
    store = LanceVectorStore()
    _ensure_collection(store)
    
    now = datetime.now(timezone.utc).isoformat()
    note_id = str(uuid.uuid4())
    
    metadata = {
        "id": note_id,
        "title": args.title,
        "category": args.category or "general",
        "content": args.content,
        "tags": args.tags.split(",") if args.tags else [],
        "source": args.source or "manual",
        "created_at": now,
        "updated_at": now,
    }
    
    vec = fallback_embedding("%s %s %s" % (args.title, args.category, args.content))
    store.insert(NOTES_COLLECTION, vec.reshape(1, -1), [metadata])
    logger.info("Note saved: [%s] %s", args.category, args.title)


def cmd_list(args: argparse.Namespace) -> None:
    """List all notes."""
    store = LanceVectorStore()
    
    try:
        dummy = np.zeros(EMBEDDING_DIM, dtype=np.float32)
        results = store.search(NOTES_COLLECTION, dummy, top_k=100)
    except Exception:
        logger.info("No notes found.")
        return
    
    if not results:
        logger.info("No notes found.")
        return
    
    # Group by category
    from collections import defaultdict
    groups: Dict[str, list] = defaultdict(list)
    
    for r in results:
        meta = r.get("metadata", {})
        if isinstance(meta, str):
            try:
                meta = json.loads(meta)
            except Exception:
                meta = {}
        cat = meta.get("category", "general")
        groups[cat].append(meta)
    
    for cat, notes in sorted(groups.items()):
        print("\n[%s]" % cat)
        for n in notes:
            title = n.get("title", "?")
            created = n.get("created_at", "?")[:10]
            print("  %s (%s)" % (title, created))


def cmd_search(args: argparse.Namespace) -> None:
    """Search notes by content."""
    store = LanceVectorStore()
    
    query_vec = fallback_embedding(args.query)
    try:
        results = store.search(NOTES_COLLECTION, query_vec, top_k=args.limit)
    except Exception:
        logger.info("No results.")
        return
    
    if not results:
        logger.info("No results for '%s'.", args.query)
        return
    
    print("Results for '%s':" % args.query)
    for r in results:
        meta = r.get("metadata", {})
        if isinstance(meta, str):
            try:
                meta = json.loads(meta)
            except Exception:
                meta = {}
        score = r.get("score", 0)
        title = meta.get("title", "?")
        content = (meta.get("content", "") or "")[:120]
        print("\n  [%.2f] %s" % (score, title))
        print("  %s" % content)


def cmd_recent(args: argparse.Namespace) -> None:
    """Show recent notes."""
    store = LanceVectorStore()
    
    try:
        dummy = np.zeros(EMBEDDING_DIM, dtype=np.float32)
        results = store.search(NOTES_COLLECTION, dummy, top_k=args.limit)
    except Exception:
        logger.info("No notes.")
        return
    
    for r in results:
        meta = r.get("metadata", {})
        if isinstance(meta, str):
            try:
                meta = json.loads(meta)
            except Exception:
                meta = {}
        title = meta.get("title", "?")
        cat = meta.get("category", "?")
        created = meta.get("created_at", "?")[:16]
        print("  [%s] %s - %s" % (created, cat, title))


def cmd_export(args: argparse.Namespace) -> None:
    """Export notes as markdown."""
    store = LanceVectorStore()
    
    try:
        dummy = np.zeros(EMBEDDING_DIM, dtype=np.float32)
        results = store.search(NOTES_COLLECTION, dummy, top_k=500)
    except Exception:
        print("# Agent Notes\n\nNo notes found.")
        return
    
    print("# Agent Notes\n")
    print("*Exported %s*\n" % datetime.now(timezone.utc).strftime("%Y-%m-%d"))
    
    from collections import defaultdict
    groups: Dict[str, list] = defaultdict(list)
    for r in results:
        meta = r.get("metadata", {})
        if isinstance(meta, str):
            try:
                meta = json.loads(meta)
            except Exception:
                meta = {}
        groups[meta.get("category", "general")].append(meta)
    
    for cat, notes in sorted(groups.items()):
        print("## %s\n" % cat)
        for n in notes:
            title = n.get("title", "?")
            content = n.get("content", "")
            tags = n.get("tags", [])
            created = n.get("created_at", "?")[:10]
            print("### %s" % title)
            print("*%s*" % created)
            if tags:
                print("*Tags: %s*" % ", ".join(tags))
            print()
            print(content)
            print()


def main():
    parser = argparse.ArgumentParser(description="Agent Notes — structured note-taking")
    sub = parser.add_subparsers(dest="command", help="Command")
    
    p_write = sub.add_parser("write", help="Write a note")
    p_write.add_argument("title", help="Note title")
    p_write.add_argument("content", help="Note content")
    p_write.add_argument("--category", "-c", default="general", help="Category")
    p_write.add_argument("--tags", "-t", default="", help="Comma-separated tags")
    p_write.add_argument("--source", "-s", default="manual", help="Source")
    
    sub.add_parser("list", help="List all notes")
    
    p_search = sub.add_parser("search", help="Search notes")
    p_search.add_argument("query", help="Search query")
    p_search.add_argument("--limit", "-n", type=int, default=5, help="Max results")
    
    p_recent = sub.add_parser("recent", help="Recent notes")
    p_recent.add_argument("--limit", "-n", type=int, default=10, help="Max results")
    
    p_export = sub.add_parser("export", help="Export as markdown")
    p_export.add_argument("--format", choices=["markdown"], default="markdown")
    
    args = parser.parse_args()
    
    commands = {
        "write": cmd_write,
        "list": cmd_list,
        "search": cmd_search,
        "recent": cmd_recent,
        "export": cmd_export,
    }
    
    if args.command in commands:
        commands[args.command](args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()

