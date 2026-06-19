#!/usr/bin/env python3
"""
Hermes-Aware Runner — Enhanced AGENTIC runner with Hermes integration.

This is a wrapper around run.py that:
1. Detects if Hermes is available
2. Uses Hermes delegate_task when possible
3. Falls back to SandboxLoop for compatibility
4. Maintains OpenCode/VSCode compatibility
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any, Dict, Optional

# Detect Hermes availability
HERMES_AVAILABLE = os.environ.get("HERMES_HOME") is not None or Path.home().joinpath(".hermes").exists()


def _hermes_delegate(task: str, target_agent: str, context: str = "") -> bool:
    """Try to delegate to Hermes if available."""
    try:
        # Only works inside Hermes session
        if "HERMES_SESSION_ID" in os.environ:
            from hermes_tools import delegate_task
            
            toolsets_map = {
                "software-engineer": ["terminal", "file", "todo"],
                "data-architect": ["terminal", "file"],
                "devops-sre": ["terminal", "file", "web"],
                "security-engineer": ["terminal", "file"],
                "ai-engineer": ["terminal", "file", "web"],
                "context-engineer": ["file", "memory"],
                "tool-mcp-engineer": ["terminal", "file"],
            }
            
            toolsets = toolsets_map.get(target_agent, ["terminal", "file"])
            
            # Delegate with full toolsets
            result = delegate_task(
                goal=f"@{target_agent}: {task}",
                context=context,
                toolsets=toolsets
            )
            return True
    except Exception as e:
        print(f"[Harness-Hermes] Delegation failed: {e}")
    
    return False


if __name__ == "__main__":
    # Main dispatcher - runs inside or outside Hermes
    if HERMES_AVAILABLE and _hermes_delegate(sys.argv[1] if len(sys.argv) > 1 else "", "project-manager"):
        print("[Harness] Task delegated to Hermes")
        sys.exit(0)
    
    # Fallback to original AGENTIC runner
    print("[Harness] Using AGENTIC native runner")
    import harness.run
    harness.run.main()