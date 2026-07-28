"""
Business Context — Glosario y contexto de negocio para agentes.

Resuelve ambiguedades terminologicas y provee contexto
especifico por industria/proyecto a los prompts de los agentes.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class BusinessTerm:
    """Termino de negocio con su definicion y contexto industrial.

    Args:
        term: Nombre del termino.
        definition: Definicion clara del termino.
        industry: Industria o dominio al que pertenece.
            Por defecto 'general'.
        aliases: Lista de sinonimos o alias del termino.
    """
    term: str
    definition: str
    industry: str = "general"
    aliases: List[str] = field(default_factory=list)


class BusinessContext:
    """Glosario de terminos de negocio para enriquecer prompts de agentes.

    Permite registrar terminos especificos de una industria o proyecto,
    resolver ambiguedades terminologicas y enriquecer prompts con
    definiciones contextuales.

    Raises:
        ValueError: Si se intenta registrar un termino vacio o sin definicion.
    """

    _DEFAULT_TERMS: list = [
        (
            "cliente activo",
            "Cliente que ha realizado una transaccion en los ultimos 30 dias",
            "general",
        ),
        (
            "churn",
            "Tasa de cancelacion de clientes en un periodo determinado",
            "general",
        ),
        (
            "ROAS",
            "Return on Ad Spend - ingresos generados por cada dolar invertido en publicidad",
            "marketing",
        ),
        (
            "CPA",
            "Cost per Acquisition - costo de adquirir un nuevo cliente",
            "marketing",
        ),
        (
            "LTV",
            "Lifetime Value - valor total que un cliente genera durante su relacion",
            "marketing",
        ),
    ]

    def __init__(self) -> None:
        """Inicializa el contexto de negocio con terminos por defecto."""
        self._terms: Dict[str, BusinessTerm] = {}
        self._industry: str = "general"
        self._load_defaults()

    def _load_defaults(self) -> None:
        """Carga los terminos por defecto en el glosario."""
        for term, definition, industry in self._DEFAULT_TERMS:
            self._terms[term.lower()] = BusinessTerm(
                term=term,
                definition=definition,
                industry=industry,
            )

    def set_industry(self, industry: str) -> None:
        """Establece la industria activa para el enriquecimiento de prompts.

        Args:
            industry: Nombre de la industria (ej: 'marketing', 'fintech').

        Raises:
            ValueError: Si industry es una cadena vacia.
        """
        if not industry:
            raise ValueError("La industria no puede ser una cadena vacia")
        self._industry = industry

    def get_industry(self) -> str:
        """Retorna la industria activa actual.

        Returns:
            Nombre de la industria configurada.
        """
        return self._industry

    def add_term(
        self,
        term: str,
        definition: str,
        industry: str = "general",
        aliases: Optional[List[str]] = None,
    ) -> None:
        """Agrega un nuevo termino al glosario.

        Args:
            term: Nombre del termino.
            definition: Definicion del termino.
            industry: Industria asociada. Por defecto 'general'.
            aliases: Lista opcional de alias.

        Raises:
            ValueError: Si term o definition estan vacios.
        """
        if not term or not term.strip():
            raise ValueError("El termino no puede estar vacio")
        if not definition or not definition.strip():
            raise ValueError("La definicion no puede estar vacia")
        self._terms[term.lower().strip()] = BusinessTerm(
            term=term.strip(),
            definition=definition.strip(),
            industry=industry,
            aliases=aliases or [],
        )

    def get_definition(self, term: str) -> Optional[str]:
        """Obtiene la definicion de un termino.

        Args:
            term: Termino a consultar.

        Returns:
            Definicion del termino si existe, None en caso contrario.
        """
        t = self._terms.get(term.lower().strip())
        return t.definition if t else None

    def get_term(self, term: str) -> Optional[BusinessTerm]:
        """Obtiene el objeto BusinessTerm completo.

        Args:
            term: Termino a consultar.

        Returns:
            BusinessTerm si existe, None en caso contrario.
        """
        return self._terms.get(term.lower().strip())

    def enrich_prompt(self, prompt: str) -> str:
        """Agrega definiciones de terminos encontrados en el prompt.

        Busca terminos del glosario dentro del prompt y anade
        definiciones contextuales al final del mismo. Solo incluye
        terminos de la industria activa o de industria 'general'.

        Args:
            prompt: Texto original del prompt.

        Returns:
            Prompt enriquecido con definiciones contextuales.
        """
        enriched = prompt
        for term, bt in self._terms.items():
            if term in prompt.lower():
                if bt.industry in (self._industry, "general"):
                    enriched += (
                        f"\n[Contexto: {bt.term} = {bt.definition}]"
                    )
        return enriched

    def list_terms(self, industry: str | None = None) -> List[BusinessTerm]:
        """Lista los terminos registrados, opcionalmente filtrados por industria.

        Args:
            industry: Si se especifica, filtra terminos de esa industria.
                Si es None, retorna todos los terminos.

        Returns:
            Lista de BusinessTerm que cumplen el filtro.
        """
        if industry is None:
            return list(self._terms.values())
        return [
            bt for bt in self._terms.values() if bt.industry == industry
        ]

    def remove_term(self, term: str) -> bool:
        """Elimina un termino del glosario.

        Args:
            term: Termino a eliminar.

        Returns:
            True si se elimino, False si no existia.
        """
        key = term.lower().strip()
        if key in self._terms:
            del self._terms[key]
            return True
        return False
