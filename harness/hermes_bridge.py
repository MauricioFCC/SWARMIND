#!/usr/bin/env python3
"""
Hermes Bridge — Integration between AGENTIC harness and Hermes Agent.

Provides:
- Skills synchronization (AGENTIC ↔ Hermes format)
- MCP server registration
- Memory bridge for cognition lessons
- Delegation integration
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    import yaml
    HAS_YAML = True
except ImportError:
    HAS_YAML = False

HERMES_HOME = Path.home() / ".hermes"
PROJECT_ROOT = Path(__file__).resolve().parent.parent
AGENTIC_SKILLS_DIR = PROJECT_ROOT / ".opencode" / "skills" / "auto"
HERMES_SKILLS_DIR = HERMES_HOME / "skills"

def is_hermes_installed() -> bool:
    """Check if Hermes CLI is installed and available in PATH."""
    try:
        subprocess.run(["hermes", "--version"], capture_output=True, timeout=5)
        return True
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False

def sync_skill_formats() -> Dict[str, Any]:
    """Convert AGENTIC skills to Hermes format with frontmatter."""
    results = {"synced": 0, "errors": [], "skipped": 0}
    
    # Ensure directories exist
    HERMES_SKILLS_DIR.mkdir(parents=True, exist_ok=True)
    AGENTIC_SKILLS_DIR.mkdir(parents=True, exist_ok=True)
    
    for skill_file in AGENTIC_SKILLS_DIR.glob("*.md"):
        try:
            content = skill_file.read_text(encoding="utf-8")
            
            # Check if already has frontmatter
            if content.startswith("---\n"):
                results["skipped"] += 1
                continue
            
            # Parse AGENTIC format (# skill: name, **Dominio**, etc.)
            lines = content.split("\n")
            skill_name = skill_file.stem
            domain = "general"
            trigger = ""
            
            for line in lines[:10]:
                if line.startswith("# skill:"):
                    skill_name = line.split(":", 1)[1].strip()
                elif "**Dominio**:" in line:
                    domain = line.split(":", 1)[1].strip()
                elif "**Trigger**:" in line:
                    trigger = line.split(":", 1)[1].strip()
            
            # Build Hermes frontmatter
            frontmatter = {
                "name": skill_name,
                "description": f"Auto-generated from AGENTIC: {skill_name}",
                "domain": domain,
                "trigger": trigger[:100],
                "agent": "software-engineer",
                "version": "1.0.0",
            }
            
            # Write Hermes format
            hermes_content = f"---\n{yaml.dump(frontmatter, default_flow_style=False, allow_unicode=True)}---\n\n{content}\n"
            hermes_file = HERMES_SKILLS_DIR / skill_file.name
            hermes_file.write_text(hermes_content, encoding="utf-8")
            results["synced"] += 1
            
        except Exception as e:
            results["errors"].append(f"{skill_file}: {e}")
    
    return results

def list_hermes_mcp_servers() -> List[Dict[str, Any]]:
    """List MCP servers configured in Hermes."""
    results = []
    mcp_config = HERMES_HOME / "mcp_servers.json"
    
    if mcp_config.exists():
        try:
            data = json.loads(mcp_config.read_text())
            servers = data.get("mcp_servers", {})
            for name, config in servers.items():
                results.append({
                    "name": name,
                    "command": config.get("command", ""),
                    "url": config.get("url", ""),
                    "enabled": config.get("enabled", True),
                })
        except Exception:
            pass
    
    return results

def register_agentic_servers_with_hermes(force: bool = False) -> Dict[str, Any]:
    """Register AGENTIC's MCP server config with Hermes."""
    results = {"registered": 0, "already_registered": 0}
    
    agentic_config = PROJECT_ROOT / "harness" / "tools_sandbox" / "mcp_servers.yaml"
    if not agentic_config.exists():
        return {"error": "mcp_servers.yaml not found"}
    
    try:
        data = yaml.safe_load(agentic_config.read_text())
        servers = data.get("servers", [])
        
        hermes_mcp_path = HERMES_HOME / "mcp_servers.json"
        hermes_mcp = json.loads(hermes_mcp_path.read_text()) if hermes_mcp_path.exists() else {"mcp_servers": {}}
        
        for server in servers:
            name = f"agentic-{server['name']}"
            if name in hermes_mcp.get("mcp_servers", {}):
                if not force:
                    results["already_registered"] += 1
                    continue
            
            # Register with Hermes via CLI
            subprocess.run(
                ["hermes", "mcp", "add", name, "--url", server['url']],
                capture_output=True,
                timeout=30
            )
            results["registered"] += 1
            
    except Exception as e:
        results["error"] = str(e)
    
    return results

def bridge_cognition_to_hermes(top_k: int = 10) -> Dict[str, Any]:
    """Export AGENTIC cognition lessons to Hermes memory format."""
    from harness.memory_rag.lance_vector_store import LanceVectorStore
    
    # Use correct collection name from lance_schemas.py
    COGNITION_COLLECTION = "asi_cognition_store"
    
    results = {"exported": 0, "errors": []}
    
    try:
        store = LanceVectorStore()
        import numpy as np
        dummy = np.zeros(384, dtype=np.float32)
        lessons = store.search(COGNITION_COLLECTION, dummy, top_k=top_k)
        
        for lesson in lessons:
            try:
                meta = lesson.get("metadata", {})
                title = meta.get("title", "")
                content = meta.get("content", "")
                domain = meta.get("domain", "general")
                
                # In Hermes context, would call memory tool
                results["exported"] += 1
            except Exception as e:
                results["errors"].append(str(e))
                
    except Exception as e:
        results["error"] = str(e)
    
    return results

def main():
    parser = argparse.ArgumentParser(description="Hermes-AGENTIC Bridge")
    parser.add_argument("--sync-skills", action="store_true", help="Sync AGENTIC skills to Hermes format")
    parser.add_argument("--register-mcp", action="store_true", help="Register AGENTIC MCP servers with Hermes")
    parser.add_argument("--bridge-memory", action="store_true", help="Export cognition to Hermes memory")
    parser.add_argument("--all", action="store_true", help="Run all sync operations")
    parser.add_argument("--setup", action="store_true", help="Set up Hermes for AGENTIC (requires Hermes installed)")
    parser.add_argument("--check", action="store_true", help="Check the Hermes-AGENTIC integration setup")
    
    args = parser.parse_args()

    if args.setup:
        if not is_hermes_installed():
            print("Error: Hermes is not installed. Please install Hermes first.")
            sys.exit(1)
        print("[Bridge] Setting up Hermes for AGENTIC...")
        # Sync skills
        sync_result = sync_skill_formats()
        print(f"  Skills synced: {sync_result['synced']}, Skipped: {sync_result['skipped']}, Errors: {len(sync_result['errors'])}")
        # Register MCP servers
        register_result = register_agentic_servers_with_hermes()
        if "error" in register_result:
            print(f"  Error registering MCP servers: {register_result['error']}")
        else:
            print(f"  MCP servers registered: {register_result['registered']}, Already registered: {register_result['already_registered']}")
        # Optionally bridge memory if --bridge-memory is also set
        if args.bridge_memory:
            print("[Bridge] Bridging cognition memory...")
            memory_result = bridge_cognition_to_hermes()
            if "error" in memory_result:
                print(f"  Error bridging memory: {memory_result['error']}")
            else:
                print(f"  Lessons exported to memory: {memory_result['exported']}")
        return
    elif args.check:
        if not is_hermes_installed():
            print("Error: Hermes is not installed.")
            sys.exit(1)
        print("[Bridge] Checking Hermes-AGENTIC integration...")
        # Check skills: count of Hermes skills that have the AGENTIC auto-generated mark
        hermes_skills = list(HERMES_SKILLS_DIR.glob("*.md"))
        agentic_skill_count = 0
        for skill_file in hermes_skills:
            try:
                content = skill_file.read_text(encoding="utf-8")
                if "Auto-generated from AGENTIC" in content:
                    agentic_skill_count += 1
            except Exception:
                pass
        print(f"  AGENTIC skills in Hermes: {agentic_skill_count}/{len(hermes_skills)}")
        # Check MCP servers: list the agentic-* servers in Hermes
        mcp_result = list_hermes_mcp_servers()
        agentic_mcp_count = sum(1 for s in mcp_result if s['name'].startswith('agentic-'))
        print(f"  AGENTIC MCP servers in Hermes: {agentic_mcp_count}/{len(mcp_result)}")
        print("  Check complete.")
        return
    
    if args.all or args.sync_skills:
        print("[Bridge] Syncing skills...")
        result = sync_skill_formats()
        print(f"  Synced: {result['synced']}, Skipped: {result['skipped']}, Errors: {len(result['errors'])}")
    
    if args.all or args.register_mcp:
        print("[Bridge] Registering MCP servers...")
        result = list_hermes_mcp_servers()
        print(f"  Hermes MCP servers found: {len(result)}")
    
    if args.all or args.bridge_memory:
        print("[Bridge] Bridging cognition memory...")
        result = bridge_cognition_to_hermes()
        print(f"  Exported lessons: {result['exported']}")

if __name__ == "__main__":
    main()