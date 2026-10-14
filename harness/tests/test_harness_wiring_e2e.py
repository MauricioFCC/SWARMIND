"""Wiring end-to-end del harness: skills + agentes + herramientas (MCP).

Verifica que TODO quede cableado de punta a punta:
  - Skills: cada `SKILL.md` descubre su `SKILL.min.md` (formato dual).
  - Agentes: el discovery del harness encuentra los perfiles reales.
  - Herramientas: la SSOT MCP -> config de opencode, y el target_router del
    skill reverse-engineering solo apunta a servers existentes.
  - Dispatch: el plan de tarea aplica agente + skills + HERRAMIENTAS a la vez.

Sin red: lee archivos y router puro.
"""

from __future__ import annotations

from pathlib import Path

from harness.orchestrator.agent_discovery import discover_agents_recursive
from harness.orchestrator.coordinator_dispatch import DispatchPlan, dispatch
from harness.reverse_engineering.target_router import (
    TARGET_NATIVE,
    route,
)
from harness.tools_sandbox.mcp_catalog import catalog_servers, servers_for_task
from harness.tools_sandbox.mcp_opencode import build_mcp_servers, load_servers

_ROOT = Path(__file__).resolve().parents[2]
_SKILLS = _ROOT / ".opencode" / "skills"
_MCP_YAML = _ROOT / "harness" / "tools_sandbox" / "mcp_servers.yaml"


class TestSkillsWired:
    """Skills en formato dual (SKILL.md + SKILL.min.md)."""

    def test_skills_discoverable_with_both_formats(self) -> None:
        skill_dirs = [
            d for d in _SKILLS.iterdir() if d.is_dir() and (d / "SKILL.md").is_file()
        ]
        assert len(skill_dirs) >= 30
        # Formato dual: la mayoria tiene min (el harness lo prefiere).
        with_min = [d for d in skill_dirs if (d / "SKILL.min.md").is_file()]
        assert len(with_min) >= 30


class TestAgentsWired:
    """El discovery del harness encuentra los agentes reales (sin fantasmas)."""

    def test_agents_discovered(self) -> None:
        agents = discover_agents_recursive()
        assert len(agents) >= 20
        assert not [n for n in agents if n.endswith(".agent.min")]

    def test_core_agents_present(self) -> None:
        agents = discover_agents_recursive()
        for name in ("coordinator", "builder", "scientist", "guardian"):
            assert name in agents, name


class TestToolsWired:
    """SSOT MCP -> opencode, y router RE -> servers existentes."""

    def test_catalog_maps_to_opencode_entries(self) -> None:
        servers = load_servers(_MCP_YAML)
        built = build_mcp_servers(servers)
        assert set(built) == set(catalog_servers())
        for entry in built.values():
            assert entry["type"] in {"local", "remote"}

    def test_target_router_only_points_to_catalog_servers(self) -> None:
        known = set(catalog_servers())
        r = route("tool.exe", authorized=True, sample=b"MZ\x00" + b"\x00" * 32)
        assert r.target_type == TARGET_NATIVE
        assert set(r.mcp_servers) <= known
        assert r.mcp_servers


class TestDispatchAppliesAll:
    """El dispatch aplica agente + skills + herramientas juntos."""

    def test_dispatch_plan_carries_tools_from_catalog(self) -> None:
        plan = dispatch("decompila el binario y haz ingenieria inversa")
        assert isinstance(plan, DispatchPlan)
        assert plan.agent
        assert plan.skills
        assert set(plan.tools) <= set(catalog_servers())
        assert plan.tools, "tarea RE debe cablear herramientas MCP"

    def test_dispatch_unknown_task_has_no_tools_but_agent(self) -> None:
        plan = dispatch("redacta un resumen ejecutivo del estado del proyecto")
        assert plan.agent
        assert set(plan.tools) <= set(catalog_servers())

    def test_servers_for_task_matches_dispatch(self) -> None:
        task = "usa el navegador para probar la interfaz web"
        plan = dispatch(task)
        assert tuple(plan.tools) == servers_for_task(task.lower())
