"""Tests de las heuristicas textuales de compresion (mixin aislado)."""

from __future__ import annotations

import pytest

from harness.memory_rag.compression_strategies.text_heuristics import (
    _TextHeuristicsMixin,
)
from harness.memory_rag.compression_types import PRESERVED_KEYWORDS


@pytest.fixture
def heuristica() -> _TextHeuristicsMixin:
    """Mixin sin estado (puro)."""
    return _TextHeuristicsMixin()


class TestHasVerb:
    """_has_verb: interseccion de palabras con el conjunto de verbos."""

    @pytest.mark.parametrize(
        "verbo",
        [
            "es",
            "son",
            "fue",
            "era",
            "ser",
            "estar",
            "tener",
            "hacer",
            "puede",
            "debe",
            "is",
            "are",
            "was",
            "crea",
            "genera",
            "devuelve",
            "ejecuta",
            "define",
        ],
    )
    def test_verbo_conocido(self, heuristica: _TextHeuristicsMixin, verbo: str) -> None:
        assert heuristica._has_verb(verbo) is True

    @pytest.mark.parametrize("texto", ["ES", "SON", "Crea", "Devuelve"])
    def test_normaliza_mayusculas(self, heuristica: _TextHeuristicsMixin, texto: str) -> None:
        """La comparacion es case-insensitive (texto en minusculas)."""
        assert heuristica._has_verb(texto) is True

    def test_frase_completa_con_verbo(self, heuristica: _TextHeuristicsMixin) -> None:
        assert heuristica._has_verb("el sistema crea reportes diarios") is True

    @pytest.mark.parametrize("texto", ["", "zzz qqq", "uno dos tres"])
    def test_sin_verbos(self, heuristica: _TextHeuristicsMixin, texto: str) -> None:
        assert heuristica._has_verb(texto) is False

    def test_no_es_subcadena_sino_palabra(self, heuristica: _TextHeuristicsMixin) -> None:
        """Las palabras se comparan completas (split), no por subcadena."""
        # "ess"/"aire" contienen partes de verbos pero no son verbos
        assert heuristica._has_verb("ess aire creaando") is False


class TestHasPreservedKeywords:
    """_has_preserved_keywords: cualquier palabra clave preservada activa."""

    @pytest.mark.parametrize(
        "keyword", list(PRESERVED_KEYWORDS)[:8]
    )
    def test_keyword_preservada(
        self, heuristica: _TextHeuristicsMixin, keyword: str
    ) -> None:
        assert heuristica._has_preserved_keywords(f"texto con {keyword} dentro") is True

    def test_sin_keywords(self, heuristica: _TextHeuristicsMixin) -> None:
        assert heuristica._has_preserved_keywords("nada relevante aqui") is False
