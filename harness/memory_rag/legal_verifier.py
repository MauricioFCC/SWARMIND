"""
LegalVerifier — Sistema de verificacion legal enterprise.

Implementa el framework SLM+RAG+Verification+Human Judgment.
Cada respuesta legal se verifica contra fuentes, jurisdiccion y confianza.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class LegalSource:
    """Fuente legal utilizada como respaldo de una respuesta.

    Attributes:
        title: Titulo descriptivo de la fuente.
        content: Contenido textual completo de la fuente.
        version: Version numerica del documento (default "1.0").
        jurisdiction: Jurisdiccion a la que pertenece la fuente (default "Colombia").
        is_latest: Indica si esta es la version mas reciente disponible.
    """
    title: str
    content: str
    version: str = "1.0"
    jurisdiction: str = "Colombia"
    is_latest: bool = True


@dataclass
class LegalAnswer:
    """Respuesta legal generada por el sistema con metadatos de verificacion.

    Attributes:
        question: Pregunta legal original del usuario.
        answer: Respuesta legal generada.
        sources: Lista de fuentes que respaldan la respuesta.
        confidence: Nivel de confianza calculado entre 0.0 y 1.0.
        jurisdiction: Jurisdiccion aplicable a la respuesta (default "Colombia").
        verified: Indica si la respuesta paso la verificacion (confidence >= 0.7).
        warnings: Lista de advertencias encontradas durante la verificacion.
    """
    question: str
    answer: str
    sources: list[LegalSource] = field(default_factory=list)
    confidence: float = 0.0
    jurisdiction: str = "Colombia"
    verified: bool = False
    warnings: list[str] = field(default_factory=list)


class LegalVerifier:
    """Verificador legal enterprise inspirado en el framework LuMay AI.

    Evalua respuestas legales contra fuentes, jurisdiccion, vigencia
    y genera reportes de explicabilidad para auditoria.

    Examples:
        >>> verifier = LegalVerifier()
        >>> source = LegalSource("Codigo Civil", "...", jurisdiction="Colombia")
        >>> verifier.add_source(source)
        >>> answer = LegalAnswer("Que dice el art 1?", "...", sources=[source])
        >>> result = verifier.verify(answer)
        >>> result.verified
        True
    """

    def __init__(self) -> None:
        """Inicializa el verificador con un repositorio de fuentes vacio."""
        self._sources: list[LegalSource] = []

    def add_source(self, source: LegalSource) -> None:
        """Agrega una fuente legal al repositorio interno del verificador.

        Args:
            source: Instancia de LegalSource con la fuente a registrar.
        """
        self._sources.append(source)

    def verify(self, answer: LegalAnswer) -> LegalAnswer:
        """Ejecuta el pipeline de verificacion legal sobre una respuesta.

        Evalua: existencia de fuentes, coincidencia de jurisdiccion,
        vigencia de las fuentes y calcula nivel de confianza.

        La penalizacion combina descuentos especificos por cada tipo de
        problema mas un descuento general por cada advertencia, reflejando
        el principio enterprise de que cualquier duda reduce drásticamente
        la confianza.

        Args:
            answer: Respuesta legal a verificar.

        Returns:
            LegalAnswer actualizada con confidence, verified y warnings.
        """
        warnings: list[str] = []
        confidence = 1.0

        # 1. Check if sources support the conclusion
        if not answer.sources:
            warnings.append("No hay fuentes que respalden esta respuesta")
            confidence -= 0.30

        # 2. Check jurisdiction match — TODAS las fuentes deben coincidir
        if answer.sources and not all(
            s.jurisdiction == answer.jurisdiction for s in answer.sources
        ):
            warnings.append(
                f"Jurisdiccion de la respuesta ({answer.jurisdiction}) "
                f"no coincide con fuentes"
            )
            confidence -= 0.30

        # 3. Check if sources are latest version
        outdated = [s for s in answer.sources if not s.is_latest]
        if outdated:
            warnings.append(f"Hay {len(outdated)} fuentes desactualizadas")
            confidence -= 0.25 * len(outdated)

        # 4. General penalty per warning (cubre cualquier problema adicional)
        confidence -= 0.10 * len(warnings)

        # 5. Cap and set final confidence
        answer.confidence = max(0.0, min(1.0, confidence))
        answer.verified = answer.confidence >= 0.7
        answer.warnings = warnings
        return answer

    def get_explainability_report(self, answer: LegalAnswer) -> str:
        """Genera un reporte de explicabilidad legible para auditoria.

        Incluye pregunta, nivel de confianza, estado de verificacion,
        advertencias y fuentes utilizadas.

        Args:
            answer: Respuesta legal verificada.

        Returns:
            Cadena de texto formateada como reporte de explicabilidad.
        """
        lines = ["## Reporte de Explicabilidad Legal", ""]
        lines.append(f"Pregunta: {answer.question}")
        lines.append(f"Confianza: {answer.confidence:.0%}")
        lines.append(f"Verificada: {'Si' if answer.verified else 'No'}")
        if answer.warnings:
            lines.append("Advertencias:")
            for w in answer.warnings:
                lines.append(f"- {w}")
        if answer.sources:
            lines.append("Fuentes:")
            for s in answer.sources:
                lines.append(
                    f"- {s.title} (v{s.version}, {s.jurisdiction})"
                )
        return "\n".join(lines)
