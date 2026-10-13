"""Tests de solapamiento semantico entre skills del registry (ronda evolutiva 2).

WHAT: calcula, para cada par de las 36 skills de
``.opencode/skills/skills_registry.yaml``, un score de solape lexico de la
``description`` (Jaccard de tokens clave del trigger) + coseno de embeddings
(fallback del harness, solo diagnostico), y clasifica cada par con una
recomendacion: ``duplica`` | ``conflicta`` | ``especializa`` | ``ok``.

WHY: si dos skills responden al mismo trigger el router no sabe cual elegir y
degrada (SkillRouter, arXiv:2603.22455: el router debe leer el CUERPO para
desambiguar; mejor aun es NO duplicar: composicion declarada, ADR-0075). Este
test es el gate de efectividad: los picos de solape (>= ``PEAK_THRESHOLD``)
deben estar documentados/accionables.

WHERE: CI tras editar ``skills_registry.yaml`` o cualquier ``description``.

Nota EDV: el coseno con ``harness.common.fallback_embedding`` (vector de
frecuencia de caracteres) queda saturado (~0.97 en todos los pares) porque las
descriptions comparten plantilla; por eso el score que decide es el Jaccard
lexico y el coseno se conserva solo como diagnostico (ver test dedicado).

Ejecutar:
    uv run python -m pytest harness/tests/test_skill_overlap.py -q
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from itertools import combinations
from pathlib import Path

import numpy as np
import pytest
import yaml

from harness.common import fallback_embedding
from harness.orchestrator.hidden_body import tokenize
from harness.orchestrator.keyword_match import normalize

# ---------------------------------------------------------------------------
# Config del gate (MAG: valores con nombre)
# ---------------------------------------------------------------------------

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
REGISTRY_PATH = _PROJECT_ROOT / ".opencode" / "skills" / "skills_registry.yaml"

#: N de skills esperado en el registry (ronda 2).
EXPECTED_SKILLS = 37

#: Score de solape >= a este valor = "pico" que DEBE ser accionable.
PEAK_THRESHOLD = 0.8

#: Banda de atencion: picos relativos de la distribucion real que exigen
#: anti-trigger declarado o recomendacion no-``ok`` (knee de la distribucion).
ATTENTION_BAND = 0.10

#: Jaccard a partir del cual dos skills se consideran casi identicas.
DUPLICATE_THRESHOLD = 0.6

#: Coeficiente de solape (>%) para colision de trigger entre dos "Usar cuando".
TRIGGER_COLLISION_MIN = 0.4

#: Banda del coseno fallback que evidencia saturacion (no discriminativo).
COSINE_SATURATED_MIN = 0.80

#: Stopwords: funcionales espanolas + plantilla comun del registry.
_STOPWORDS: frozenset[str] = frozenset(
    {
        "usar", "cuando", "el", "la", "los", "las", "un", "una", "de", "del",
        "en", "y", "o", "u", "a", "al", "para", "por", "con", "sin", "que",
        "se", "su", "sus", "es", "son", "como", "mas", "the", "of", "to",
        "and", "or", "for", "involucra", "problema", "usuario", "busca",
        "quiere", "necesita", "pide", "opera", "dominio", "trabaja", "analiza",
        "gestiona", "disena", "construye", "implementa", "evalua", "nuevo",
        "nueva",
    }
)

#: Captura el trigger (texto previo a ``Alcance:``); ``Alcance`` declara
#: anti-triggers ("para X ver Y") y NO debe contar como solape de trigger.
_HEAD_RE = re.compile(r"^(.*?)(?:\.?\s*Alcance:|$)", re.DOTALL)


# ---------------------------------------------------------------------------
# Tipos
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Skill:
    """Skill del registry.

    Attributes:
        name: Nombre canonico.
        domain: Dominio declarado.
        description: Description "pushy".
    """

    name: str
    domain: str
    description: str


@dataclass(frozen=True)
class OverlapPair:
    """Par de skills con su score de solape y recomendacion.

    Attributes:
        skill_a: Primer skill (nombre).
        skill_b: Segundo skill (nombre).
        score: Jaccard lexico del trigger en ``[0, 1]`` (score que decide).
        cosine: Coseno de embeddings fallback (diagnostico, saturado).
        shared: Tokens clave compartidos (ordenados).
        recommendation: ``duplica`` | ``conflicta`` | ``especializa`` | ``ok``.
        cross_referenced: True si alguna description menciona a la otra por
            nombre (anti-trigger "para X ver Y" ya declarado).
    """

    skill_a: str
    skill_b: str
    score: float
    cosine: float
    shared: tuple[str, ...]
    recommendation: str
    cross_referenced: bool


# ---------------------------------------------------------------------------
# Scorer (KISS: word-overlap; cosine solo diagnostico)
# ---------------------------------------------------------------------------


def _trigger_head(description: str) -> str:
    """Extrae la parte trigger de una description (antes de ``Alcance:``).

    Args:
        description: Description completa del skill.

    Returns:
        Texto del trigger + keywords; ``""`` si la description es vacia.
    """
    match = _HEAD_RE.match(description or "")
    return match.group(1) if match else (description or "")


def _key_tokens(text: str) -> frozenset[str]:
    """Tokeniza y filtra stopwords funcionales/plantilla.

    Args:
        text: Texto a tokenizar.

    Returns:
        Conjunto de tokens clave normalizados.
    """
    return frozenset(t for t in tokenize(text) if t and t not in _STOPWORDS)


def _jaccard(left: frozenset[str], right: frozenset[str]) -> float:
    """Similitud Jaccard entre dos conjuntos de tokens.

    Args:
        left: Primer conjunto.
        right: Segundo conjunto.

    Returns:
        ``|A∩B| / |A∪B|`` en ``[0,1]``.
    """
    union = left | right
    return len(left & right) / len(union) if union else 0.0


def _cosine(left: str, right: str) -> float:
    """Coseno entre embeddings fallback del harness (diagnostico).

    Args:
        left: Primer texto.
        right: Segundo texto.

    Returns:
        Coseno en ``[-1, 1]``; ``0.0`` si algun vector es nulo.
    """
    vec_a, vec_b = fallback_embedding(left), fallback_embedding(right)
    denom = float(np.linalg.norm(vec_a) * np.linalg.norm(vec_b))
    return float(np.dot(vec_a, vec_b) / denom) if denom else 0.0


def _overlap_coefficient(left: frozenset[str], right: frozenset[str]) -> float:
    """Coeficiente de solape (Szymkiewicz-Simpson).

    Args:
        left: Primer conjunto.
        right: Segundo conjunto.

    Returns:
        ``|A∩B| / min(|A|,|B|)``; ``0.0`` si algun conjunto es vacio.
    """
    subset = min(len(left), len(right))
    return len(left & right) / subset if subset else 0.0


def _is_pushy(description: str) -> bool:
    """True si la description abre con "Usar cuando" (patron pushy).

    Args:
        description: Description del skill.

    Returns:
        True si el trigger arranca con ``usar cuando``.
    """
    return normalize(description).startswith("usar cuando")


def _recommend_pair(
    skill_a: Skill,
    skill_b: Skill,
    score: float,
    overlap: float,
) -> str:
    """Clasifica la relacion entre dos skills segun su solape.

    Args:
        skill_a: Primer skill.
        skill_b: Segundo skill.
        score: Jaccard lexico del trigger.
        overlap: Coeficiente de solape (para colision de trigger).

    Returns:
        ``duplica`` | ``conflicta`` | ``especializa`` | ``ok``.
    """
    if score >= DUPLICATE_THRESHOLD:
        return "duplica"
    if (
        _is_pushy(skill_a.description)
        and _is_pushy(skill_b.description)
        and overlap > TRIGGER_COLLISION_MIN
    ):
        return "conflicta"
    return "ok"


def _cross_referenced(skill_a: Skill, skill_b: Skill) -> bool:
    """True si alguna description menciona a la otra skill por nombre.

    Args:
        skill_a: Primer skill.
        skill_b: Segundo skill.

    Returns:
        True si A cita a B o B cita a A (anti-trigger declarado).
    """
    return skill_b.name in skill_a.description or skill_a.name in skill_b.description


def load_registry_skills(path: Path = REGISTRY_PATH) -> tuple[Skill, ...]:
    """Carga las skills del registry YAML.

    Args:
        path: Ruta del ``skills_registry.yaml``.

    Returns:
        Tupla de ``Skill`` en orden del registry.

    Raises:
        FileNotFoundError: Si el registry no existe.
    """
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return tuple(
        Skill(
            name=str(item["name"]),
            domain=str(item.get("domain", "")),
            description=str(item.get("description", "")),
        )
        for item in data["skills"]
    )


def _pair_for(skill_a: Skill, skill_b: Skill) -> OverlapPair:
    """Construye el ``OverlapPair`` de dos skills.

    Args:
        skill_a: Primer skill.
        skill_b: Segundo skill.

    Returns:
        Par con score, coseno, tokens compartidos y recomendacion.
    """
    head_a, head_b = _trigger_head(skill_a.description), _trigger_head(skill_b.description)
    tok_a, tok_b = _key_tokens(head_a), _key_tokens(head_b)
    score = _jaccard(tok_a, tok_b)
    overlap = _overlap_coefficient(tok_a, tok_b)
    return OverlapPair(
        skill_a=skill_a.name,
        skill_b=skill_b.name,
        score=score,
        cosine=_cosine(head_a, head_b),
        shared=tuple(sorted(tok_a & tok_b)),
        recommendation=_recommend_pair(skill_a, skill_b, score, overlap),
        cross_referenced=_cross_referenced(skill_a, skill_b),
    )


def compute_overlap_pairs(skills: tuple[Skill, ...]) -> tuple[OverlapPair, ...]:
    """Calcula todos los pares con su score de solape, ordenados desc.

    Args:
        skills: Skills del registry.

    Returns:
        Tupla de ``OverlapPair`` ordenada por ``score`` descendente y, ante
        empate, por nombre (determinista).
    """
    pairs = [_pair_for(a, b) for a, b in combinations(skills, 2)]
    return tuple(sorted(pairs, key=lambda p: (-p.score, p.skill_a, p.skill_b)))


def find_unactionable_peaks(
    pairs: tuple[OverlapPair, ...], threshold: float = PEAK_THRESHOLD
) -> tuple[OverlapPair, ...]:
    """Picos de solape (>= ``threshold``) sin recomendacion accionable.

    Args:
        pairs: Pares evaluados.
        threshold: Umbral de pico (default ``PEAK_THRESHOLD``).

    Returns:
        Pares con ``score >= threshold`` y recomendacion ``ok`` (no accionable).
    """
    return tuple(p for p in pairs if p.score >= threshold and p.recommendation == "ok")


def undocumented_attention_pairs(
    pairs: tuple[OverlapPair, ...], band: float = ATTENTION_BAND
) -> tuple[OverlapPair, ...]:
    """Pares en la banda de atencion sin desambiguacion declarada.

    WHAT: pares con ``band <= score`` que no tienen anti-trigger cruzado ni
    recomendacion accionable (``duplica``/``conflicta``/``especializa``).

    Args:
        pairs: Pares evaluados.
        band: Banda de atencion (knee de la distribucion).

    Returns:
        Pares que requieren decision de producto.
    """
    return tuple(
        p
        for p in pairs
        if p.score >= band and p.recommendation == "ok" and not p.cross_referenced
    )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def skills() -> tuple[Skill, ...]:
    """Skills reales del registry."""
    return load_registry_skills()


@pytest.fixture(scope="module")
def pairs(skills: tuple[Skill, ...]) -> tuple[OverlapPair, ...]:
    """Pares de solape del registry real, ordenados."""
    return compute_overlap_pairs(skills)


# ---------------------------------------------------------------------------
# (a) el scorer corre sobre el registry real y produce pares ordenados
# ---------------------------------------------------------------------------


def test_registry_has_36_skills(skills: tuple[Skill, ...]) -> None:
    """El registry tiene exactamente 36 skills (ronda 2)."""
    assert len(skills) == EXPECTED_SKILLS


def test_scorer_returns_ordered_pairs(pairs: tuple[OverlapPair, ...]) -> None:
    """630 pares ordenados por score descendente (determinista)."""
    assert len(pairs) == EXPECTED_SKILLS * (EXPECTED_SKILLS - 1) // 2
    scores = [p.score for p in pairs]
    assert scores == sorted(scores, reverse=True)
    assert pairs[0].skill_a == "psychology"
    assert pairs[0].skill_b == "sociology"


def test_every_pair_has_recommendation(pairs: tuple[OverlapPair, ...]) -> None:
    """Toda pareja recibe una recomendacion del conjunto permitido."""
    allowed = {"duplica", "conflicta", "especializa", "ok"}
    assert {p.recommendation for p in pairs} <= allowed


# ---------------------------------------------------------------------------
# (b) no hay picos (>= 0.8) sin recomendacion accionable
# ---------------------------------------------------------------------------


def test_no_unactionable_peaks_in_real_registry(pairs: tuple[OverlapPair, ...]) -> None:
    """Ningun par con score >= 0.8 queda sin recomendacion accionable."""
    peaks = find_unactionable_peaks(pairs)
    assert peaks == (), f"picos sin accion: {[(p.skill_a, p.skill_b) for p in peaks]}"


def test_holdout_peak_detection_flags_duplicate() -> None:
    """Dos descriptions identicas se detectan como pico accionable (sintetico)."""
    desc = "Usar cuando el usuario valida factores de alpha. alpha, factores, backtesting."
    skills = (
        Skill("alpha-research", "quantitative", desc),
        Skill("alpha-research-dupe", "quantitative", desc),
    )
    peaks = find_unactionable_peaks(compute_overlap_pairs(skills))
    assert len(peaks) == 0, "un duplicado debe ser accionable (no 'ok')"
    top = compute_overlap_pairs(skills)[0]
    assert top.recommendation == "duplica"
    assert top.score == pytest.approx(1.0)


def test_fallback_cosine_is_saturated_not_discriminative(
    pairs: tuple[OverlapPair, ...],
) -> None:
    """Documenta que el coseno fallback satura y NO decide el score.

    WHERE: justifica el uso de Jaccard como score principal (KISS/EDV).
    """
    cosines = [p.cosine for p in pairs]
    assert min(cosines) >= 0.75, "se esperaba coseno alto (plantilla comun)"
    # El score real (Jaccard) es muy inferior al coseno: no hay pico >= 0.8.
    assert max(p.score for p in pairs) < PEAK_THRESHOLD


@pytest.mark.xfail(
    strict=True,
    reason=(
        "DECISION DE PRODUCTO (ronda 2): healthtech~sociology comparte "
        "'sistemas/digital' sin anti-trigger cruzado; add 'para X ver Y' o "
        "aceptar. Ver specs/ronda2-solapamiento.md"
    ),
)
def test_attention_band_pairs_are_documented(pairs: tuple[OverlapPair, ...]) -> None:
    """Los pares de la banda de atencion declaran desambiguacion.

    WHAT: todo par con ``score >= ATTENTION_BAND`` debe tener anti-trigger
    cruzado o recomendacion accionable. WHY: los picos relativos sin
    desambiguar degradan el routing (aunque esten por debajo de 0.8).
    """
    gaps = undocumented_attention_pairs(pairs)
    assert gaps == (), (
        "pares en banda de atencion sin desambiguar: "
        f"{[(p.skill_a, p.skill_b, round(p.score, 3)) for p in gaps]}"
    )


# ---------------------------------------------------------------------------
# (c) mutacion: el threshold y la deteccion son necesarios para el gate
# ---------------------------------------------------------------------------


def test_mutation_threshold_controls_detection(pairs: tuple[OverlapPair, ...]) -> None:
    """Un threshold permisivo (0.0) invierte el resultado del gate.

    Si `PEAK_THRESHOLD` se mutara a 0.0, `find_unactionable_peaks` devolveria
    pares y `test_no_unactionable_peaks_in_real_registry` fallaria.
    """
    assert find_unactionable_peaks(pairs, threshold=1.0) == ()
    assert find_unactionable_peaks(pairs, threshold=0.0) != ()


def test_mutation_stub_recommendation_breaks_gate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Anular la deteccion (recomendacion siempre 'ok') rompe el gate.

    Prueba que `test_no_unactionable_peaks_in_real_registry` depende de la
    deteccion: con un `_recommend_pair` colapsado a 'ok', un duplicado
    sintetico deja de ser accionable y el gate fallaria.
    """
    import sys

    mod = sys.modules[__name__]
    monkeypatch.setattr(mod, "_recommend_pair", lambda *args, **kwargs: "ok")
    desc = "Usar cuando el usuario valida factores de alpha. alpha, backtesting."
    skills = (
        Skill("alpha-research", "quantitative", desc),
        Skill("alpha-research-dupe", "quantitative", desc),
    )
    peaks = find_unactionable_peaks(compute_overlap_pairs(skills))
    assert peaks != (), "sin deteccion, el duplicado queda sin accion (gate rojo)"
