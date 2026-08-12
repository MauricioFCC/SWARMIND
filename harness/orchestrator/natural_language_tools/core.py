"""NaturalLanguageTools core — clase principal ``NaturalLanguageToolkit``.

Extraccion mecanica del modulo original
``harness/orchestrator/natural_language_tools.py`` (sin cambios de logica
ni firmas). La clase compone los mixins por responsabilidad:

- ``_DefaultsMixin`` (defaults.py): registro de tools por defecto.
- ``_RegistryMixin`` (registry.py): gestion de herramientas.
- ``_ScoringMixin`` (scoring.py): scoring semantico.
- ``_ParametersMixin`` (parameters.py): extraccion de parametros.
- ``_ChainingMixin`` (chaining.py): encadenamiento de tools.
- ``_ParsingMixin`` (parsing.py): parse y parse_batch.
- ``_UtilsMixin`` (utils.py): sugerencias y busquedas.
"""

from __future__ import annotations

import logging

from harness.orchestrator.nlt_types import DEFAULT_CONFIDENCE_THRESHOLD, NLTool

from .chaining import _ChainingMixin
from .defaults import _DefaultsMixin
from .parameters import _ParametersMixin
from .parsing import _ParsingMixin
from .registry import _RegistryMixin
from .scoring import _ScoringMixin
from .utils import _UtilsMixin

logger = logging.getLogger(__name__)


class NaturalLanguageToolkit(
    _DefaultsMixin,
    _RegistryMixin,
    _ParsingMixin,
    _ScoringMixin,
    _ParametersMixin,
    _ChainingMixin,
    _UtilsMixin,
):
    """Convierte lenguaje natural en llamadas estructuradas a herramientas.

    Implementa el pipeline de Natural Language Tool Calling (arXiv:2607.03953):
      1. Semantic overlap scoring entre texto de entrada y cada tool.
      2. Seleccion de mejor candidato sobre umbral de confianza.
      3. Extraccion de parametros mediante patrones lingueisticos.
      4. Encadenamiento de herramientas para intenciones compuestas.

    Examples:
        >>> nlt = NaturalLanguageToolkit()
        >>> result = nlt.parse("buscar contratos de servicios")
        >>> result.tool
        'buscar'
        >>> result.confidence > 0.3
        True
        >>> result.structured_output["action"]
        'buscar'
    """

    def __init__(
        self,
        confidence_threshold: float = DEFAULT_CONFIDENCE_THRESHOLD,
    ) -> None:
        """Inicializa el toolkit con herramientas por defecto.

        Args:
            confidence_threshold: Umbral minimo de confianza (0-1) para
                considerar un match como valido. Por defecto 0.35.
        """
        self._tools: dict[str, NLTool] = {}
        self._threshold = confidence_threshold
        self._register_defaults()
        logger.info(
            "NaturalLanguageToolkit inicializado con %d tools, "
            "threshold=%.2f",
            len(self._tools), self._threshold,
        )
