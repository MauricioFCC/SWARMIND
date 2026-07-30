"""Split files > 900 lines into smaller modules."""
import os

def split_router():
    """Split router.py (2343) into router.py + multi_provider.py."""
    path = "harness/model_router/router.py"
    with open(path, "r", encoding="utf-8") as f:
        lines = f.readlines()

    # Find class boundaries
    model_router_start = None
    for i, line in enumerate(lines):
        if line.strip().startswith("class ModelRouter"):
            model_router_start = i
            break

    if model_router_start is None:
        print("  ERROR: ModelRouter class not found")
        return

    # multi_provider.py: everything before ModelRouter
    mp_lines = lines[:model_router_start]
    # Fix the module docstring
    mp_header = '"""MultiAPIProvider — Abstraccion multi-proveedor con fallover.\n\nGestiona multiples proveedores LLM (OpenAI, Anthropic, Google, Mistral, DeepSeek)\ncon registro dinamico, health checks, cost tracking y failover.\n"""\n'
    mp_content = mp_header + "".join(lines[25:model_router_start])

    # router.py: ModelRouter + imports from multi_provider
    r_header = '"""ModelRouter — Enrutamiento de tareas a modelos LLM."""\n'
    r_imports = "from harness.model_router.multi_provider import MultiAPIProvider, ProviderConfig, ProviderHealth, RoutingDecision, ExecutionResult, BudgetLimit\n"
    r_content = r_header + r_imports + "".join(lines[model_router_start:])

    with open("harness/model_router/multi_provider.py", "w", encoding="utf-8") as f:
        f.write(mp_content)

    with open("harness/model_router/router.py", "w", encoding="utf-8") as f:
        f.write(r_content)

    print(f"  router.py: {len(r_content.splitlines())} lines")
    print(f"  multi_provider.py: {len(mp_content.splitlines())} lines")
    print("  -> < 900 each" if len(r_content.splitlines()) < 900 and len(mp_content.splitlines()) < 900 else "  -> STILL > 900!")


def split_prompt_compressor():
    """Split prompt_compressor.py (1978) into prompt_compressor.py + separate budget manager."""
    path = "harness/memory_rag/prompt_compressor.py"
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()

    # Find TokenBudgetManager class
    marker = "class TokenBudgetManager"
    idx = content.find(marker)
    if idx == -1:
        print("  ERROR: TokenBudgetManager not found")
        return

    # Split: PromptCompressor core stays, TokenBudgetManager extracted
    core_content = content[:idx]
    tbm_content = content[idx:]

    # Fix imports in core
    core_fixed = core_content.strip()

    # Write budget manager
    tbm_header = '"""TokenBudgetManager — Gestion de presupuesto de tokens por sesion."""\nfrom __future__ import annotations\n\nimport threading\nimport time\nfrom dataclasses import dataclass, field\nfrom typing import Dict, Optional\n\n'
    tbm_final = tbm_header + tbm_content

    with open("harness/memory_rag/prompt_compressor.py", "w", encoding="utf-8") as f:
        f.write(core_fixed)

    with open("harness/memory_rag/token_budget_manager.py", "w", encoding="utf-8") as f:
        f.write(tbm_final)

    cc = len(core_fixed.splitlines())
    tc = len(tbm_final.splitlines())
    print(f"  prompt_compressor.py: {cc} lines")
    print(f"  token_budget_manager.py: {tc} lines")


def split_got_planner():
    """Split got_planner.py (1723) into got_planner.py + thought_graph.py."""
    path = "harness/orchestrator/got_planner.py"
    with open(path, "r", encoding="utf-8") as f:
        lines = f.readlines()

    # Find ThoughtGraph class
    thought_graph_start = None
    for i, line in enumerate(lines):
        if line.strip().startswith("class ThoughtGraph"):
            thought_graph_start = i
            break

    if thought_graph_start is None:
        print("  ERROR: ThoughtGraph not found")
        return

    # Find GoTPlanner class (where ThoughtGraph ends)
    got_planner_start = None
    for i in range(thought_graph_start + 1, len(lines)):
        if line.strip().startswith("class GoTPlanner"):
            got_planner_start = i
            break

    if got_planner_start is None:
        # If GoTPlanner not found, ThoughtGraph goes until end of file
        tg_lines = lines[thought_graph_start:]
        core_lines = lines[:thought_graph_start]
    else:
        tg_lines = lines[thought_graph_start:got_planner_start]
        core_lines = lines[:thought_graph_start] + lines[got_planner_start:]

    tg_header = '"""ThoughtGraph — Grafo de pensamientos para razonamiento multi-paso."""\nfrom __future__ import annotations\n\nfrom dataclasses import dataclass, field\nfrom typing import Any, Dict, List, Optional\n\n'
    tg_content = tg_header + "".join(tg_lines)

    with open("harness/orchestrator/got_planner.py", "w", encoding="utf-8") as f:
        f.write("".join(lines[:thought_graph_start]))

    with open("harness/orchestrator/thought_graph.py", "w", encoding="utf-8") as f:
        f.write(tg_content)

    cc = len("".join(lines[:thought_graph_start]).splitlines())
    tc = len(tg_content.splitlines())
    print(f"  got_planner.py: {cc} lines")
    print(f"  thought_graph.py: {tc} lines")


if __name__ == "__main__":
    print("Splitting router.py...")
    split_router()
    print("\nSplitting prompt_compressor.py...")
    split_prompt_compressor()
    print("\nSplitting got_planner.py...")
    split_got_planner()
    print("\nDone. Verifying...")
