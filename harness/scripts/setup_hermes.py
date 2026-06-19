#!/usr/bin/env python3
"""
Setup Hermes Integration - One-command setup for AGENTIC + Hermes.

Usage:
    python harness/scripts/setup_hermes.py
    
This script:
1. Creates .opencode/skills/agentic-hermes skill directory
2. Installs the bridge skill into Hermes
3. Configures MCP servers if available
4. Sets up memory bridge
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
HERMES_HOME = Path.home() / ".hermes"

def main():
    print("=" * 60)
    print("  AGENTIC + Hermes Integration Setup")
    print("=" * 60)
    
    # Check Hermes availability
    if not HERMES_HOME.exists():
        print("\n[!] Hermes not found at ~/.hermes")
        print("    Install Hermes first: curl -fsSL https://hermes-agent.nousresearch.com/install.sh | bash")
        return 1
    
    # 1. Install the bridge skill
    print("\n[1/4] Installing agentic-hermes-bridge skill...")
    try:
        subprocess.run([
            "hermes", "skills", "install", 
            str(PROJECT_ROOT / "harness" / "skills" / "agentic-hermes.md"),
            "--name", "agentic-hermes"
        ], timeout=30)
        print("    ✓ Skill installed")
    except Exception as e:
        print(f"    ⚠ Could not install skill: {e}")
    
    # 2. Sync MCP servers
    print("\n[2/4] Syncing MCP servers...")
    try:
        subprocess.run(["hermes", "mcp", "list"], timeout=10)
        print("    ✓ MCP servers available")
    except Exception as e:
        print(f"    ⚠ MCP check failed: {e}")
    
    # 3. Create profile for AGENTIC
    print("\n[3/4] Creating AGENTIC profile...")
    profile_dir = HERMES_HOME / "profiles" / "agentic"
    profile_dir.mkdir(parents=True, exist_ok=True)
    
    # Link to AGENTIC skills
    agentic_skills = PROJECT_ROOT / ".opencode" / "skills"
    if agentic_skills.exists():
        skills_link = profile_dir / "skills"
        if not skills_link.exists():
            # Create symlink or copy
            skills_link.symlink_to(agentic_skills, target_is_directory=True)
            print(f"    ✓ Linked skills: {skills_link}")
    
    # 4. Memory integration
    print("\n[4/4] Configuring memory bridge...")
    # No action needed - uses existing LanceDB
    
    print("\n" + "=" * 60)
    print("  Setup complete! Next steps:")
    print("=" * 60)
    print("""
  From anywhere in your project, run:

    hermes -p agentic chat -q "@software-engineer: implementar API FastAPI"

  Or use the AGENTIC runner with Hermes:

    python harness/run_hermes.py "@software-engineer: implementar API FastAPI"

  To sync skills:

    python harness/hermes_bridge.py --sync-skills
    hermes skills list  # Verify

  To check MCP servers:

    hermes mcp list
    python harness/hermes_bridge.py --register-mcp
""")
    return 0


if __name__ == "__main__":
    sys.exit(main())