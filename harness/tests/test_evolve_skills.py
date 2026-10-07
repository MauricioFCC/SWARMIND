"""Tests TDD del runner EVO de skills (``scripts/evolve_skills.py``).

Cubre el contrato del pase profundo GEPA + gate determinista:
  - ``score_skill``: cuerpo vacio = 0; secciones/checklist/PERSONA suman.
  - ``evaluate_variant``: perder una seccion del contrato penaliza.
  - ``_split_frontmatter``: con frontmatter, sin frontmatter y malformado.
  - ``run``: ``--dry-run`` NO escribe; una variante que no mejora NO se
    promueve; una que mejora pero pierde contrato tampoco.

La aleatoriedad de ``GEPAMutator`` se sustituye por un generador determinista
para que la suite no dependa de GEPA.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent
SCRIPTS_DIR = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import evolve_skills

#: Cuerpo baseline con las dos secciones del contrato, checklist y PERSONA.
_BASELINE_BODY = (
    "## Checklist\n"
    "## Anti-patrones\n"
    "- [ ] item\n"
    "PERSONA\n"
)
#: Cuerpo con frontmatter valido listo para promover.
_BASELINE_TEXT = f"---\nname: demo\n---\n{_BASELINE_BODY}"


def _write_skill(base: Path, text: str) -> Path:
    """Escribe un SKILL.md fixture dentro de ``base``.

    Args:
        base: Directorio raiz de skills (se crea ``demo/SKILL.md``).
        text: Contenido completo del SKILL.md.

    Returns:
        Ruta al SKILL.md creado.
    """
    skill_dir = base / "demo"
    skill_dir.mkdir()
    path = skill_dir / "SKILL.md"
    path.write_text(text, encoding="utf-8")
    return path


def _fake_propose(
    _name: str, _body: str, _count: int
) -> list[tuple[float, str, str]]:
    """Generador determinista de variantes (sustituye a GEPAMutator).

    Args:
        _name: Nombre de la skill (ignorado).
        _body: Cuerpo baseline (ignorado).
        _count: Numero de variantes (ignorado).

    Returns:
        Una unica variante con score 99.0 y estrategia "fake".
    """
    return [(99.0, "fake", "## Nuevo\nPERSONA\n")]


# ---------------------------------------------------------------------------
# score_skill
# ---------------------------------------------------------------------------


def test_score_skill_cuerpo_vacio_es_cero() -> None:
    """score_skill: cuerpo vacio o solo espacios puntua 0.0."""
    assert evolve_skills.score_skill("") == 0.0
    assert evolve_skills.score_skill("   \n\n\t") == 0.0


def test_score_skill_con_secciones_es_mayor_que_cero() -> None:
    """score_skill: secciones del contrato + checklist + PERSONA suman."""
    score = evolve_skills.score_skill(_BASELINE_BODY)
    assert score == pytest.approx(1.1)
    assert score > 0.0


# ---------------------------------------------------------------------------
# evaluate_variant
# ---------------------------------------------------------------------------


def test_evaluate_variant_penaliza_perdida_de_seccion() -> None:
    """evaluate_variant: perder '## Checklist' resta el peso de la seccion."""
    original = _BASELINE_BODY
    candidate = "## Anti-patrones\n- [ ] item\nPERSONA\n"
    penalty = evolve_skills.WEIGHT_MISSING_SECTION
    assert evolve_skills.evaluate_variant(original, candidate) == pytest.approx(
        evolve_skills.score_skill(candidate) - penalty
    )


def test_evaluate_variant_sin_perdida_igual_a_score() -> None:
    """evaluate_variant: variante integra puntua igual que score_skill."""
    assert evolve_skills.evaluate_variant(
        _BASELINE_BODY, _BASELINE_BODY
    ) == pytest.approx(evolve_skills.score_skill(_BASELINE_BODY))


# ---------------------------------------------------------------------------
# _split_frontmatter
# ---------------------------------------------------------------------------


def test_split_frontmatter_con_frontmatter() -> None:
    """_split_frontmatter: separa el bloque YAML del cuerpo."""
    front, body = evolve_skills._split_frontmatter("---\nname: demo\n---\ncuerpo\n")
    assert front == "---\nname: demo\n---"
    assert body == "\ncuerpo\n"


def test_split_frontmatter_sin_frontmatter() -> None:
    """_split_frontmatter: sin delimitador inicial devuelve ('', texto)."""
    front, body = evolve_skills._split_frontmatter("solo cuerpo")
    assert front == ""
    assert body == "solo cuerpo"


def test_split_frontmatter_malformado() -> None:
    """_split_frontmatter: delimitador sin cierre no se considera frontmatter."""
    text = "---\nsin cierre\n"
    front, body = evolve_skills._split_frontmatter(text)
    assert front == ""
    assert body == text


# ---------------------------------------------------------------------------
# run / _process
# ---------------------------------------------------------------------------


def test_run_dry_run_no_escribe(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """run(dry_run=True): propone una mejora pero NO modifica el archivo."""
    skill_file = _write_skill(tmp_path, _BASELINE_TEXT)
    monkeypatch.setattr(evolve_skills, "SKILLS_DIR", tmp_path)
    monkeypatch.setattr(evolve_skills, "_propose_variants", _fake_propose)

    code = evolve_skills.run(dry_run=True, limit=None, mutants=1)

    assert code == 0
    assert skill_file.read_text(encoding="utf-8") == _BASELINE_TEXT


def test_run_no_promueve_variante_que_no_mejora(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """run(dry_run=False): una variante con score <= baseline NO se promueve."""

    def _peor(_name: str, _body: str, _count: int) -> list[tuple[float, str, str]]:
        return [(0.0, "peor", "## Anti-patrones\n- [ ]\n")]

    skill_file = _write_skill(tmp_path, _BASELINE_TEXT)
    monkeypatch.setattr(evolve_skills, "SKILLS_DIR", tmp_path)
    monkeypatch.setattr(evolve_skills, "_propose_variants", _peor)

    code = evolve_skills.run(dry_run=False, limit=None, mutants=1)

    assert code == 0
    assert skill_file.read_text(encoding="utf-8") == _BASELINE_TEXT


def test_run_no_promueve_variante_que_pierde_contrato(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """run(dry_run=False): mejora de score pero pierde seccion -> no promueve."""

    def _sin_contrato(
        _name: str, _body: str, _count: int
    ) -> list[tuple[float, str, str]]:
        return [(99.0, "sin-contrato", "## Anti-patrones\n- [ ]\nPERSONA\n")]

    skill_file = _write_skill(tmp_path, _BASELINE_TEXT)
    monkeypatch.setattr(evolve_skills, "SKILLS_DIR", tmp_path)
    monkeypatch.setattr(evolve_skills, "_propose_variants", _sin_contrato)

    code = evolve_skills.run(dry_run=False, limit=None, mutants=1)

    assert code == 0
    assert skill_file.read_text(encoding="utf-8") == _BASELINE_TEXT


def test_run_sin_skills_devuelve_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """run: sin SKILL.md en el directorio devuelve exit code 1."""
    monkeypatch.setattr(evolve_skills, "SKILLS_DIR", tmp_path)
    assert evolve_skills.run(dry_run=True, limit=None, mutants=1) == 1
