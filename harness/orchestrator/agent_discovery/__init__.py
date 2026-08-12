"""Agent Discovery — Recursive agent profile parser.

Antes: harness/orchestrator/agent_discovery.py (559 lineas).
Ahora: paquete ``harness/orchestrator/agent_discovery/``:

- ``keywords.py``: mapas ``_DOMAIN_KEYWORDS`` y ``_CAPABILITY_KEYWORDS``.
- ``parsing.py``: helpers de parseo (frontmatter + inferencia).
- ``discovery.py``: ``discover_agents_recursive``.
- ``helpers.py``: alias map, resolucion, capabilities y domain helpers.

Este ``__init__.py`` re-exporta TODOS los simbolos publicos del modulo
original para mantener backward-compat:

    from harness.orchestrator.agent_discovery import discover_agents_recursive

Regla AGR: cada archivo del paquete queda por debajo de 500 lineas.
"""
from __future__ import annotations

from .discovery import discover_agents_recursive
from .helpers import (
    build_alias_map,
    build_intent_map,
    get_agent_for_domain,
    get_all_capabilities,
    list_agents,
    resolve_agent_name,
)
from .keywords import (
    _CAPABILITY_KEYWORDS as _CAPABILITY_KEYWORDS,
)
from .keywords import (
    _DOMAIN_KEYWORDS as _DOMAIN_KEYWORDS,
)
from .parsing import (
    _get_agents_dir as _get_agents_dir,
)
from .parsing import (
    _infer_from_content as _infer_from_content,
)
from .parsing import (
    _parse_frontmatter as _parse_frontmatter,
)
from .parsing import (
    _try_import_yaml as _try_import_yaml,
)
from .parsing import parse_agent_profile

__all__ = [
    "build_alias_map",
    "build_intent_map",
    "discover_agents_recursive",
    "get_agent_for_domain",
    "get_all_capabilities",
    "list_agents",
    "parse_agent_profile",
    "resolve_agent_name",
]
