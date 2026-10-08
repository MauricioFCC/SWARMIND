"""Tests para keyword_match — matching por frontera de palabra (anti falsos positivos).

Cubren normalizacion (acentos, guiones), no-match de substring (`api`⊄`capital`,
`doc`⊄`docker`, `go`⊄`good`, `pos`⊄`position`, `test`⊄`latest`), match positivo,
keywords multi-palabra, y las utilidades de conteo.
"""

from __future__ import annotations

from harness.orchestrator.keyword_match import (
    contains_word,
    match_keywords,
    normalize,
    score_keywords,
)


def test_normalize_strips_accents_and_hyphens() -> None:
    """normalize quita acentos, baja a minusculas y unifica guiones a espacio."""
    assert normalize("Diseña") == "disena"
    assert normalize("micro-servicio") == "micro servicio"
    assert normalize("  API_REST  ") == "api rest"
    assert normalize("") == ""


def test_contains_word_rejects_substring_false_positives() -> None:
    """`api`/`doc`/`go`/`pos`/`test` NO matchean palabras que los contienen."""
    assert contains_word("asignar capital del fondo", "api") is False
    assert contains_word("deploy con docker", "doc") is False
    assert contains_word("good practices", "go") is False
    assert contains_word("position sizing", "pos") is False
    assert contains_word("the latest build", "test") is False


def test_contains_word_accepts_real_words() -> None:
    """El match positivo funciona con palabra completa y variantes normalizadas."""
    assert contains_word("crear una API REST", "api") is True
    assert contains_word("diseña la arquitectura", "disena") is True
    assert contains_word("micro-servicio", "servicio") is True


def test_contains_word_multiword_phrase() -> None:
    """Keywords multi-palabra matchean como frase con frontera."""
    assert contains_word("position sizing para la cuenta", "position sizing") is True
    assert contains_word("position para sizing", "position sizing") is False


def test_contains_word_empty_keyword_is_false() -> None:
    """Una keyword vacia nunca matchea (evita match universal)."""
    assert contains_word("cualquier texto", "") is False


def test_match_and_score_keywords_preserve_order() -> None:
    """match_keywords conserva el orden de entrada; score cuenta los matches."""
    keywords = ("api", "capital", "docker", "doc")
    text = "crear una api con docker"
    assert match_keywords(text, keywords) == ("api", "docker")
    assert score_keywords(text, keywords) == 2
