"""Tests para el puente in-process de proyectos federados (mcp_project_bridge)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from harness.tools_sandbox.mcp_manager import MCPManager
from harness.tools_sandbox.mcp_project_bridge import (
    InProcessMCPClient,
    ProjectRegistry,
    register_project_bridge,
)


@pytest.fixture
def tmp_base(tmp_path: Path) -> Path:
    base = tmp_path / 'federated'
    base.mkdir()
    # seed two projects
    for name in ('proj_a', 'proj_b'):
        (base / f'knowledge_{name}.json').write_text(
            json.dumps({'project': name, 'updated_at': None, 'record_count': 0, 'records': []}),
            encoding='utf-8',
        )
    return base


def test_registry_list_projects(tmp_base: Path) -> None:
    reg = ProjectRegistry(tmp_base)
    assert sorted(reg.list_projects()) == ['proj_a', 'proj_b']


def test_registry_put_get_search(tmp_base: Path) -> None:
    reg = ProjectRegistry(tmp_base)
    rec = reg.put('proj_a', 'k1', 'hello world', tags=['demo'])
    assert rec['key'] == 'k1'
    assert reg.get('proj_a', 'k1') == 'hello world'
    # upsert
    reg.put('proj_a', 'k1', 'updated')
    assert reg.get('proj_a', 'k1') == 'updated'
    res = reg.search('hello', project='proj_a')
    assert res == []  # 'hello' no longer present after update
    res = reg.search('updated')
    assert len(res) == 1
    res = reg.search(tag='demo')
    assert len(res) == 1


def test_registry_status(tmp_base: Path) -> None:
    reg = ProjectRegistry(tmp_base)
    st = reg.status('proj_a')
    assert st['project'] == 'proj_a'
    assert st['record_count'] == 0


def test_registry_invalid_project_name(tmp_base: Path) -> None:
    reg = ProjectRegistry(tmp_base)
    with pytest.raises(ValueError):
        reg._path('bad/name')


def test_inprocess_client_tools_and_exec(tmp_base: Path) -> None:
    reg = ProjectRegistry(tmp_base)
    client = InProcessMCPClient(reg)
    assert client.is_connected() is True
    tools = client.list_tools()
    names = [t.name for t in tools]
    assert 'project_list' in names
    res = client.execute_tool('project_list', {})
    assert res.success is True
    assert 'proj_a' in (res.output or [])
    res = client.execute_tool('knowledge_put', {'project': 'proj_a', 'key': 'x', 'value': 42})
    assert res.success is True
    res = client.execute_tool('knowledge_get', {'project': 'proj_a', 'key': 'x'})
    assert res.success is True
    assert res.output == 42
    res = client.execute_tool('knowledge_search', {'query': '42'})
    assert res.success is True
    assert len(res.output) == 1
    res = client.execute_tool('project_status', {'project': 'proj_a'})
    assert res.success is True
    assert res.output['record_count'] == 1
    # unknown tool
    res = client.execute_tool('nope', {})
    assert res.success is False


def test_register_project_bridge(tmp_base: Path) -> None:
    m = MCPManager()
    name = register_project_bridge(m, base_dir=tmp_base)
    assert name == 'project_bridge'
    assert 'project_bridge' in m.get_connected_servers()
    tools = [t.name for t in m.list_all_tools()]
    assert 'knowledge_put' in tools
    r = m.execute('project_list', {})
    assert r.success is True
    assert 'proj_a' in (r.output or [])


def test_bridge_circuit_and_governance(tmp_base: Path) -> None:
    from harness.tools_sandbox.mcp_governance import MCPGovernor, ToolPolicy
    m = MCPManager()
    register_project_bridge(m, base_dir=tmp_base)
    gov = MCPGovernor(m)
    gov.register_policy(ToolPolicy(agent_id='agent1', allowed_tools=frozenset({'project_list'})))
    r = gov.execute('agent1', 'project_list', {})
    assert r.success is True
    with pytest.raises(PermissionError):
        gov.execute('agent1', 'knowledge_put', {'project': 'proj_a', 'key': 'k', 'value': 'v'})
