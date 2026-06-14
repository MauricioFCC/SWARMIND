"""
end_of_iteration.py — Pipeline de fin de iteracion (thin wrapper).

Este archivo ahora es un wrapper ligero que importa la implementacion
desde el paquete ``end_of_iteration/``.

La funcionalidad se ha dividido en fases separadas (<300 lineas cada una):

    end_of_iteration/
        __init__.py        — Pipeline principal, CLI, reportes
        config.py          — Constantes, tipos de datos, helpers
        phase1_bugs.py     — Bug hunting
        phase2_security.py — Security scan
        phase3_docs.py     — Docs update
        phase4_tokens.py   — Token report
        phase5_commit.py   — Commit preparation

Uso:
    python harness/scripts/end_of_iteration.py [--skip-bugs] [--skip-security]
                                               [--skip-docs] [--dry-run]
"""
from __future__ import annotations

from end_of_iteration import main

if __name__ == "__main__":
    main()
