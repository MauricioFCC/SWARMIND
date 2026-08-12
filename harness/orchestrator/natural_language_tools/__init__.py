"""NaturalLanguageTools — Tool calling en lenguaje natural (arXiv:2607.03953).

Antes: harness/orchestrator/natural_language_tools.py (771 lineas).
Ahora: paquete ``harness/orchestrator/natural_language_tools/``:

- ``core.py``: clase ``NaturalLanguageToolkit`` (estado + __init__).
- ``defaults.py``: mixin ``_DefaultsMixin`` (tools por defecto).
- ``registry.py``: mixin ``_RegistryMixin`` (gestion de herramientas).
- ``scoring.py``: mixin ``_ScoringMixin`` (scoring semantico).
- ``parameters.py``: mixin ``_ParametersMixin`` (extraccion de parametros).
- ``chaining.py``: mixin ``_ChainingMixin`` (encadenamiento de tools).
- ``parsing.py``: mixin ``_ParsingMixin`` (parse y parse_batch).
- ``utils.py``: mixin ``_UtilsMixin`` (sugerencias y busquedas).

Este ``__init__.py`` re-exporta TODOS los simbolos publicos (y los
constantes/tipos re-importados desde ``nlt_types``) del modulo original
para mantener backward-compat:

    from harness.orchestrator.natural_language_tools import NaturalLanguageToolkit

Regla AGR: cada archivo del paquete queda por debajo de 500 lineas.
"""

from __future__ import annotations

from harness.orchestrator.nlt_types import (
    _CHAIN_CONNECTORS,
    _PARAM_PATTERNS,
    _STOPWORDS,
    DEFAULT_CONFIDENCE_THRESHOLD,
    NLTool,
    NLTResult,
)

from .core import NaturalLanguageToolkit

__all__ = [
    "DEFAULT_CONFIDENCE_THRESHOLD",
    "_CHAIN_CONNECTORS",
    "_PARAM_PATTERNS",
    "_STOPWORDS",
    "NLTResult",
    "NLTool",
    "NaturalLanguageToolkit",
]
