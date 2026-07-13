#!/usr/bin/env python3
"""CLI para gestion de plugins."""
from __future__ import annotations
import argparse
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from harness.plugins.registry import registry


def main():
    p = argparse.ArgumentParser(description="Tools CLI")
    sub = p.add_subparsers(dest="command")
    sub.add_parser("list", help="List tools")
    pi = sub.add_parser("info", help="Tool info")
    pi.add_argument("name")
    pr = sub.add_parser("run", help="Run tool")
    pr.add_argument("name")
    pr.add_argument("args", nargs="*")
    sub.add_parser("discover", help="Rediscover")
    args = p.parse_args()
    
    if args.command == "list":
        for t in registry.list_tools():
            print(f"  {t['name']:<20} {t['description'][:60]}")
    elif args.command == "info":
        t = registry.get(args.name)
        if t:
            print(f"Name: {t.name}\nDesc: {t.description}\nVersion: {t.version}")
        else:
            print(f"Not found: {args.name}")
    elif args.command == "run":
        t = registry.get(args.name)
        if not t:
            print(f"Not found: {args.name}")
            return
        kwargs = {}
        for a in args.args:
            if "=" in a:
                k, v = a.split("=", 1)
                kwargs[k] = v
        print(t.execute(**kwargs))
    elif args.command == "discover":
        print(f"Discovered {registry.discover_all()} tools")
    else:
        p.print_help()


if __name__ == "__main__":
    main()
