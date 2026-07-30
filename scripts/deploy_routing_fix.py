"""
Fix routing_rules.yaml for all projects.

Reemplaza routing_rules.yaml en cada proyecto con la version actualizada
de Swarmind, eliminando las referencias a agentes fantasma.

Los proyectos preservaban routing_rules.yaml antiguos via backup/restore
en deploy_all.py, nunca recibiendo las actualizaciones de agentes.

Usage:
    python scripts/deploy_routing_fix.py
"""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_ROOT = _HERE.parent
_SOURCE_ROUTING = _ROOT / ".opencode" / "config" / "routing_rules.yaml"

# Same project configs as deploy_all.py
_DEV_SPACE = Path(os.environ.get("DEV_SPACE_ROOT", Path.home() / "Documents" / "DEV-SPACE"))
_HERMES_PATH = Path(os.environ.get("HERMES_PATH", _DEV_SPACE / "shared_memory"))

PROJECTS = [
    ("quant-engine", _DEV_SPACE / "quant-engine"),
    ("health-record", _DEV_SPACE / "health-record"),
    ("trading-bot-AIBot", _DEV_SPACE / "trading-bot-AIBot"),
    ("pos-system", _DEV_SPACE / "pos-system"),
    ("shared_memory", _HERMES_PATH),
]


def main():
    if not _SOURCE_ROUTING.exists():
        print(f"❌ Source routing_rules.yaml not found: {_SOURCE_ROUTING}")
        sys.exit(1)

    fixed = 0
    for name, path in PROJECTS:
        target = path / ".opencode" / "config" / "routing_rules.yaml"
        if not target.exists():
            print(f"  ⏭️  {name}: routing_rules.yaml not found")
            continue
        
        # Read current content
        content = target.read_text(encoding="utf-8")
        
        # Check if it has old non-existent agents
        old_agents = [
            "quant-developer", "quant-scientist", "risk-manager", 
            "trading-operations", "enterprise-architect", "ai-engineer",
            "software-engineer", "frontend-engineer", "data-architect",
            "devops-sre", "security-engineer", "mobile-engineer",
            "documentation-specialist", "project-manager", "requirements-analyst",
            "quality-gate",
        ]
        
        has_old = any(agent in content for agent in old_agents)
        
        if has_old:
            # Backup old version
            backup = target.with_suffix(".yaml.bak")
            shutil.copy2(str(target), str(backup))
            
            # Replace with source version
            shutil.copy2(str(_SOURCE_ROUTING), str(target))
            print(f"  ✅ {name}: routing_rules.yaml UPDATED (backup at {backup.name})")
            fixed += 1
        else:
            print(f"  ✅ {name}: already up to date")
    
    print(f"\n📊 Total: {fixed} projects fixed, {len(PROJECTS) - fixed} already up to date")


if __name__ == "__main__":
    main()
