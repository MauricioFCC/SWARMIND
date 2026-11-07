"""In-process MCP bridge for inter-project communication.

Exposes the federated knowledge store (.opencode/federated/*.json) as MCP
tools so that agents/projects can discover each other and share knowledge
through the standard MCPManager path (governance, audit, circuit breaker).

Tools exposed:
  - project_list: list registered projects
  - project_status: metadata of a project
  - knowledge_put: store a record (key/value/tags) in a project
  - knowledge_get: retrieve a record by key
  - knowledge_search: search records by query/tag across projects
"""

from __future__ import annotations

import json
import logging
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from harness.tools_sandbox.mcp_client import MCPResult, MCPTool

logger = logging.getLogger(__name__)

DEFAULT_BASE_DIR = Path('.opencode/federated')

_TOOL_DEFS: tuple[tuple[str, str], ...] = (
    ('project_list', 'List registered projects in the federated store.'),
    ('project_status', 'Return metadata (record count, updated_at) of a project.'),
    ('knowledge_put', 'Store a key/value record (with optional tags) in a project.'),
    ('knowledge_get', 'Retrieve a record by key from a project.'),
    ('knowledge_search', 'Search records by query substring and/or tag across projects.'),
)


class ProjectRegistry:
    '''Manages federated project knowledge files.'''

    def __init__(self, base_dir: str | Path | None = None) -> None:
        self.base_dir = Path(base_dir) if base_dir is not None else DEFAULT_BASE_DIR
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def _path(self, project: str) -> Path:
        if not project or not all(c.isalnum() or c in '-_' for c in project):
            raise ValueError('invalid project name')
        return self.base_dir / f'knowledge_{project}.json'

    def list_projects(self) -> list[str]:
        projects: list[str] = []
        for p in sorted(self.base_dir.glob('knowledge_*.json')):
            try:
                data = json.loads(p.read_text(encoding='utf-8'))
                projects.append(str(data.get('project', p.stem)))
            except (OSError, json.JSONDecodeError):
                projects.append(p.stem)
        return projects

    def _load(self, project: str) -> dict[str, Any]:
        path = self._path(project)
        if path.exists():
            try:
                return json.loads(path.read_text(encoding='utf-8'))
            except (OSError, json.JSONDecodeError):
                pass
        return {'project': project, 'updated_at': None, 'record_count': 0, 'records': []}

    def _save(self, project: str, data: dict[str, Any]) -> None:
        data['updated_at'] = datetime.now(UTC).isoformat()
        data['record_count'] = len(data.get('records', []))
        self._path(project).write_text(
            json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8'
        )

    def status(self, project: str) -> dict[str, Any]:
        data = self._load(project)
        return {
            'project': data.get('project', project),
            'record_count': data.get('record_count', len(data.get('records', []))),
            'updated_at': data.get('updated_at'),
        }

    def put(self, project: str, key: str, value: Any, tags: list[str] | None = None) -> dict[str, Any]:
        if not key:
            raise ValueError('key is required')
        data = self._load(project)
        records = data.setdefault('records', [])
        # upsert by key
        for rec in records:
            if rec.get('key') == key:
                rec['value'] = value
                rec['tags'] = list(tags or rec.get('tags', []))
                rec['ts'] = datetime.now(UTC).isoformat()
                self._save(project, data)
                return rec
        rec = {
            'key': key,
            'value': value,
            'tags': list(tags or []),
            'ts': datetime.now(UTC).isoformat(),
        }
        records.append(rec)
        self._save(project, data)
        return rec

    def get(self, project: str, key: str) -> Any:
        data = self._load(project)
        for rec in data.get('records', []):
            if rec.get('key') == key:
                return rec.get('value')
        return None

    def search(
        self,
        query: str = '',
        tag: str | None = None,
        project: str | None = None,
    ) -> list[dict[str, Any]]:
        projects = [project] if project else self.list_projects()
        results: list[dict[str, Any]] = []
        ql = (query or '').lower()
        for proj in projects:
            data = self._load(proj)
            for rec in data.get('records', []):
                if tag and tag not in (rec.get('tags') or []):
                    continue
                haystack = ' '.join([
                    str(rec.get('key', '')),
                    str(rec.get('value', '')),
                    ' '.join(rec.get('tags') or []),
                ]).lower()
                if ql and ql not in haystack:
                    continue
                results.append({'project': proj, **rec})
        return results


class InProcessMCPClient:
    '''MCPClient-compatible adapter wrapping a ProjectRegistry.'''

    def __init__(self, registry: ProjectRegistry) -> None:
        self._registry = registry
        self._connected = True

    def connect(self, url: str = '') -> bool:
        self._connected = True
        return True

    def connect_stdio(self, command: str = '', args: list[str] | None = None, env: dict[str, str] | None = None) -> bool:
        self._connected = True
        return True

    def is_connected(self) -> bool:
        return self._connected

    def disconnect(self) -> None:
        self._connected = False

    def list_tools(self) -> list[MCPTool]:
        return [MCPTool(name=n, description=d, server_name='project_bridge') for n, d in _TOOL_DEFS]

    def execute_tool(self, tool_name: str, params: dict[str, Any], timeout: int | None = None) -> MCPResult:
        start = time.perf_counter()
        try:
            out = self._dispatch(tool_name, params or {})
            success = True
            error = ''
        except Exception as exc:  # noqa: BLE001
            out = None
            success = False
            error = str(exc)
        elapsed = (time.perf_counter() - start) * 1000.0
        return MCPResult(
            success=success,
            output=out,
            tool_name=tool_name,
            server_name='project_bridge',
            duration_ms=round(elapsed, 2),
            error=error,
        )

    def _dispatch(self, tool_name: str, params: dict[str, Any]) -> Any:
        if tool_name == 'project_list':
            return self._registry.list_projects()
        if tool_name == 'project_status':
            return self._registry.status(str(params.get('project', '')))
        if tool_name == 'knowledge_put':
            return self._registry.put(
                str(params.get('project', '')),
                str(params.get('key', '')),
                params.get('value'),
                params.get('tags'),
            )
        if tool_name == 'knowledge_get':
            return self._registry.get(str(params.get('project', '')), str(params.get('key', '')))
        if tool_name == 'knowledge_search':
            return self._registry.search(
                query=str(params.get('query', '')),
                tag=params.get('tag'),
                project=params.get('project'),
            )
        raise ValueError(f'unknown tool: {tool_name}')


def register_project_bridge(
    manager: Any,
    base_dir: str | Path | None = None,
    enabled: bool = True,
) -> str:
    '''Register the in-process project bridge as an MCP server in a manager.'''
    name = 'project_bridge'
    registry = ProjectRegistry(base_dir)
    client = InProcessMCPClient(registry)
    if name in getattr(manager, '_servers', {}):
        manager.remove_server(name)
    manager.register_server(name, url='', tools=[n for n, _ in _TOOL_DEFS], enabled=enabled, description='In-process federated project bridge', transport='stdio', command='project_bridge')
    # override: mark as connected client directly
    manager._clients[name] = client
    if hasattr(manager, '_invalidate_index'):
        manager._invalidate_index()
    return name
