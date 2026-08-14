"""NaturalLanguageTools defaults — herramientas por defecto del toolkit.

Extraccion mecanica del modulo original
``harness/orchestrator/natural_language_tools.py`` (sin cambios de logica
ni firmas): las 4 herramientas legales por defecto se definen en la
constante ``_DEFAULT_TOOLS`` y el mixin ``_DefaultsMixin`` las registra.
"""

from __future__ import annotations

from harness.orchestrator.nlt_types import NLTool

# ---------------------------------------------------------------------------
# Herramientas por defecto (4 tools legales)
# ---------------------------------------------------------------------------

_DEFAULT_TOOLS: list[NLTool] = [
    NLTool(
        name="buscar",
        description=(
            "Buscar documentos legales por contenido textual. "
            "Util para encontrar jurisprudencia, contratos, "
            "clausulas o cualquier texto dentro de documentos."
        ),
        parameters={
            "query": "texto o terminos a buscar",
            "max": "maximo de resultados a retornar (opcional)",
        },
        examples=[
            "buscar contratos de servicios 2024",
            "encuentra todas las clausulas de confidencialidad",
            "buscar jurisprudencia sobre debido proceso",
            "localizar demandas por incumplimiento",
        ],
    ),
    NLTool(
        name="analizar",
        description=(
            "Analizar un documento legal extrayendo entidades, "
            "partes, riesgos, clausulas relevantes y metadatos. "
            "Soporta analisis de riesgos, de partes y de entidades."
        ),
        parameters={
            "documento": "ruta o identificador del documento",
            "tipo": (
                "tipo de analisis: riesgos / partes / entidades "
                "(opcional, por defecto completo)"
            ),
        },
        examples=[
            "analizar contrato de arrendamiento",
            "analiza demanda por danos y perjuicios",
            "analizar el documento 1234 en modo riesgos",
            "analisis completo del expediente X-2024",
        ],
    ),
    NLTool(
        name="comparar",
        description=(
            "Comparar dos documentos legales y mostrar sus "
            "diferencias estructurales y de contenido. "
            "Identifica clausulas anadidas, eliminadas o modificadas."
        ),
        parameters={
            "doc1": "primer documento o version a comparar",
            "doc2": "segundo documento o version",
        },
        examples=[
            "comparar contratos de proveedor A y B",
            "compara version 1 y 2 del acuerdo de confidencialidad",
            "diferencias entre el documento X y el Y",
            "comparar clausulas de indemnizacion",
        ],
    ),
    NLTool(
        name="resumir",
        description=(
            "Resumir un documento legal en uno o mas parrafos "
            "con diferentes niveles de detalle. "
            "Genera resumenes ejecutivos, normales o detallados."
        ),
        parameters={
            "documento": "ruta o identificador del documento",
            "longitud": (
                "nivel de detalle del resumen: "
                "breve / normal / detallado (opcional)"
            ),
        },
        examples=[
            "resumir sentencia de la corte suprema",
            "resume el contrato en 3 parrafos",
            "resumen ejecutivo del dictamen legal",
            "detallado del caso Perez vs Empresa S.A.",
        ],
    ),
]


class _DefaultsMixin:
    """Mixin con el registro de las herramientas por defecto."""

    def _register_defaults(self) -> None:
        """Registra las herramientas legales por defecto (4 tools)."""
        for t in _DEFAULT_TOOLS:
            self._tools[t.name] = t
