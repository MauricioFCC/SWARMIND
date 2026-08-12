"""Motor de recomendacion de plantillas del On-Demand Agent Factory.

Submodulo interno del paquete :mod:`harness.aifactory.agent_factory`.

Extraido de forma mecanica desde ``agent_factory.py`` (regla AGR: archivos
< 500 lineas). Define ``AgentRecommender`` (capa QueryAnalysis del pipeline
del paper). Los cuerpos son identicos al original; solo cambia la ubicacion
fisica del codigo.
"""

from __future__ import annotations

from .models import FALLBACK_TEMPLATE_ID, AgentTemplate
from .registry import AgentTemplateRegistry


class AgentRecommender:
    """Motor de recomendacion de plantillas por keywords (QueryAnalysis).

    Tokeniza la tarea en minusculas y puntua cada template contando los
    tokens de la tarea presentes en sus keywords (domain_tags + nombre +
    descripcion). Gana el de mayor score; en empate, el primero en orden
    de registro. Sin coincidencias, usa el template de fallback
    (research-synthesis) o, si no existe, el primero del catalogo.
    """

    def __init__(self, fallback_template_id: str = FALLBACK_TEMPLATE_ID) -> None:
        """Inicializa el recommender con template de fallback.

        Args:
            fallback_template_id: Template usado sin coincidencias.
                Default: 'research-synthesis' (sintesis generalista).
        """
        self._fallback_template_id = fallback_template_id

    def recommend(
        self, task: str, registry: AgentTemplateRegistry
    ) -> AgentTemplate:
        """Recomienda el template mas similar a la tarea.

        Args:
            task: Descripcion de la tarea del usuario.
            registry: Catalogo de plantillas a consultar.

        Returns:
            AgentTemplate recomendado (o fallback si no hay coincidencias).
        """
        tokens = self._tokenize(task)
        best_template: AgentTemplate | None = None
        best_score = 0
        for template in registry.templates():
            score = self._score(tokens, template)
            if score > best_score:
                best_template = template
                best_score = score
        if best_template is not None:
            return best_template
        fallback = registry.get(self._fallback_template_id)
        if fallback is not None:
            return fallback
        return registry.templates()[0]

    @staticmethod
    def _tokenize(task: str) -> set[str]:
        """Tokeniza la tarea en palabras en minusculas.

        Args:
            task: Texto de la tarea.

        Returns:
            Conjunto de tokens sin vacios.
        """
        return {token for token in task.lower().split() if token}

    @staticmethod
    def _template_keywords(template: AgentTemplate) -> set[str]:
        """Construye el set de keywords de un template.

        Args:
            template: Plantilla a analizar.

        Returns:
            Conjunto de keywords (domain_tags + nombre + descripcion).
        """
        keywords: set[str] = set(template.domain_tags)
        keywords.update(template.name.lower().split())
        keywords.update(template.description.lower().split())
        return keywords

    def _score(self, task_tokens: set[str], template: AgentTemplate) -> int:
        """Puntua un template contra los tokens de la tarea.

        Args:
            task_tokens: Tokens normalizados de la tarea.
            template: Plantilla a puntuar.

        Returns:
            Numero de tokens de la tarea presentes en las keywords.
        """
        keywords = self._template_keywords(template)
        return sum(1 for token in task_tokens if token in keywords)
