"""On-Demand Agent Factory (refactorizado a paquete).

Antes: harness/aifactory/agent_factory.py (692 lineas).
Ahora: paquete ``harness/aifactory/agent_factory/`` con submódulos cohesivos:

- ``models.py``: constantes nombradas + dataclasses inmutables
  (``AgentTemplate``, ``SpawnConfig``, ``GeneratedAgent``).
- ``registry.py``: ``AgentTemplateRegistry`` (catalogo YAML).
- ``recommender.py``: ``AgentRecommender`` (capa QueryAnalysis).
- ``render_mixin.py``: mixin ``_MarkdownRenderMixin`` (composicion Markdown).
- ``factory.py``: ``OnDemandAgentFactory`` (core del pipeline).

Este ``__init__.py`` re-exporta TODOS los simbolos publicos del modulo
original para mantener backward-compat:

    from harness.aifactory.agent_factory import OnDemandAgentFactory

Regla AGR: cada archivo del paquete queda por debajo de 500 lineas.
"""

from __future__ import annotations

from .factory import OnDemandAgentFactory
from .models import (
    BUDGET_DEFAULT,
    FALLBACK_TEMPLATE_ID,
    MAX_ITERATIONS_DEFAULT,
    AgentTemplate,
    GeneratedAgent,
    SpawnConfig,
)
from .models import (
    DEFAULT_COST_ESTIMATE as DEFAULT_COST_ESTIMATE,
)
from .models import (
    DEFAULT_PERMISSIONS as DEFAULT_PERMISSIONS,
)
from .models import (
    DESCRIPTION_MAX_LEN as DESCRIPTION_MAX_LEN,
)
from .models import (
    UUID_SUFFIX_LEN as UUID_SUFFIX_LEN,
)
from .recommender import AgentRecommender
from .registry import AgentTemplateRegistry

__all__ = [
    "BUDGET_DEFAULT",
    "FALLBACK_TEMPLATE_ID",
    "MAX_ITERATIONS_DEFAULT",
    "AgentRecommender",
    "AgentTemplate",
    "AgentTemplateRegistry",
    "GeneratedAgent",
    "OnDemandAgentFactory",
    "SpawnConfig",
]
