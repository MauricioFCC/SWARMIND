"""Tests TDD para hidden-body router — puntaje por cuerpo de skill (FR-C2).

RED primero (ADR-0103 / WS-C): el router puntua el CUERPO real del SKILL.md
(no solo metadata) por co-ocurrencia de palabras de la tarea, y lo combina
0.5/0.5 con la similitud existente. Frontera: hidden-body asymmetry
(SkillRouter, arXiv:2603.22455).

Criterios:
  (a) cuerpo con keywords -> body_score > 0 y sube la similitud combinada.
  (b) skill sin archivo -> solo metadata (no falla).
  (c) combinacion 0.5/0.5 exacta.
  (d) mutation: quitar la lectura del cuerpo rompe el test.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
import yaml

from harness.evolve_loop.skill_generator import SkillGenerator
from harness.orchestrator import skill_bundler
from harness.orchestrator.agent_dispatcher import AgentDispatcher
from harness.orchestrator.hidden_body import (
    _body_keyword_score,
    combine_hidden_body_score,
    read_skill_body,
    tokenize,
)
from harness.orchestrator.skill_bundler import SkillBundler

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

#: Cuerpo de skill que contiene todas las palabras de la tarea de prueba.
_BODY_WITH_KEYWORDS = (
    "---\nname: demo\n---\n"
    "# Demo Skill\n\n"
    "Implementar API REST con autenticacion JWT y seguridad OWASP.\n"
)

_TASK_WORDS = "api rest autenticacion jwt"


def _write_skill(directory: Path, body: str) -> Path:
    """Escribe un ``SKILL.md`` bajo ``directory`` y devuelve su ruta.

    Args:
        directory: Directorio destino (se crea si no existe).
        body: Contenido del skill.

    Returns:
        Ruta del ``SKILL.md`` creado.
    """
    directory.mkdir(parents=True, exist_ok=True)
    skill = directory / "SKILL.md"
    skill.write_text(body, encoding="utf-8")
    return skill


# ===========================================================================
# (a) cuerpo con keywords
# ===========================================================================


class TestBodyScore:
    """El cuerpo puntua por co-ocurrencia de palabras de la tarea."""

    def test_body_score_higher_with_keywords(self, tmp_path: Path) -> None:
        """Con cuerpo rico en keywords el body_score sube la similitud."""
        skill = _write_skill(tmp_path / "demo", _BODY_WITH_KEYWORDS)
        fake: dict[str, Any] = {"name": "demo", "path": str(skill)}

        with patch.object(SkillGenerator, "find_in_registry", return_value=fake):
            result = AgentDispatcher().find_skill_for_task(_TASK_WORDS)

        assert result is not None
        assert result["body_score"] > 0.0
        # metadata 0.80 + cuerpo 1.0 -> 0.90 (> 0.80 solo-metadata).
        assert result["similarity"] > 0.80

    def test_body_keyword_score_ratio(self) -> None:
        """El score es matches/task_words."""
        assert _body_keyword_score("api rest jwt", tokenize("api rest")) == pytest.approx(1.0)
        assert _body_keyword_score("api", tokenize("api rest")) == pytest.approx(0.5)
        assert _body_keyword_score("", tokenize("api")) == 0.0
        assert _body_keyword_score("api", set()) == 0.0


# ===========================================================================
# (b) skill sin archivo
# ===========================================================================


class TestMissingFile:
    """Sin archivo de cuerpo se usa solo la metadata."""

    def test_no_file_keeps_metadata_similarity(self) -> None:
        """Ruta inexistente -> body_score 0 y similitud de metadata intacta."""
        fake: dict[str, Any] = {"name": "ghost", "path": "/nonexistent/ghost.md"}

        with patch.object(SkillGenerator, "find_in_registry", return_value=fake):
            result = AgentDispatcher().find_skill_for_task("api rest")

        assert result is not None
        assert result["body_score"] == 0.0
        assert result["similarity"] == 0.80
        assert result["content"] == ""

    def test_read_skill_body_missing_is_empty(self) -> None:
        """``read_skill_body`` degrada a '' sin lanzar."""
        assert read_skill_body("") == ""
        assert read_skill_body("/nonexistent/nope.md") == ""


# ===========================================================================
# (c) combinacion 0.5/0.5
# ===========================================================================


class TestCombine:
    """La combinacion usa pesos exactos 0.5/0.5."""

    @pytest.mark.parametrize(
        "metadata,body,expected",
        [(0.80, 1.0, 0.90), (0.60, 0.20, 0.40), (0.0, 0.0, 0.0), (1.0, 1.0, 1.0)],
    )
    def test_combine_weights(
        self, metadata: float, body: float, expected: float
    ) -> None:
        """combine(meta, body) == 0.5*meta + 0.5*body."""
        assert combine_hidden_body_score(metadata, body) == pytest.approx(expected)

    def test_dispatcher_uses_half_half(self, tmp_path: Path) -> None:
        """En ``find_skill_for_task`` la similitud combinada es 0.5/0.5."""
        body = "api rest autenticacion jwt"
        skill = _write_skill(tmp_path / "half", body)
        fake: dict[str, Any] = {"name": "half", "path": str(skill)}

        with patch.object(SkillGenerator, "find_in_registry", return_value=fake):
            result = AgentDispatcher().find_skill_for_task(_TASK_WORDS)

        assert result is not None
        expected = combine_hidden_body_score(0.80, result["body_score"])
        assert result["similarity"] == pytest.approx(expected)


# ===========================================================================
# (d) mutation: el cableado del cuerpo es indispensable
# ===========================================================================


class TestBodyWiringMutation:
    """Si se elimina la lectura del cuerpo, estos asserts fallan.

    Mutation-style (ADR-0098 §7): el discriminante es la presencia de
    ``body_score`` NO nulo con archivo real + su efecto en ``similarity``.
    """

    def test_body_wiring_discriminant(self, tmp_path: Path) -> None:
        """El cuerpo real debe reflejarse en ``body_score`` (> 0)."""
        skill = _write_skill(tmp_path / "mut", _BODY_WITH_KEYWORDS)
        fake: dict[str, Any] = {"name": "mut", "path": str(skill)}

        with patch.object(SkillGenerator, "find_in_registry", return_value=fake):
            wired = AgentDispatcher().find_skill_for_task(_TASK_WORDS)

        assert wired is not None
        # Sin la lectura del cuerpo, body_score seria 0.0 y similarity 0.80.
        assert wired["body_score"] > 0.0
        assert wired["similarity"] != 0.80


# ===========================================================================
# SkillBundler: desempate de dominio ambiguo por cuerpo
# ===========================================================================


class TestSkillBundlerAmbiguity:
    """Dominios que empatan por keyword se desempatan por cuerpo."""

    def test_body_breaks_ambiguous_domain(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """El dominio cuyo cuerpo matchea mejor la tarea gana el empate."""
        skill_a = _write_skill(tmp_path / "a", "topic alpha")
        skill_b = _write_skill(tmp_path / "b", "topic alpha beta")

        monkeypatch.setitem(skill_bundler.DOMAIN_KEYWORDS, "domA", ["alpha", "beta"])
        monkeypatch.setitem(skill_bundler.DOMAIN_KEYWORDS, "domB", ["alpha", "beta"])
        monkeypatch.setitem(skill_bundler.DOMAIN_SKILLS, "domA", ["skillA"])
        monkeypatch.setitem(skill_bundler.DOMAIN_SKILLS, "domB", ["skillB"])

        registry = tmp_path / "skills_registry.yaml"
        registry.write_text(
            yaml.safe_dump(
                {
                    "skills": [
                        {"name": "skillA", "path": str(skill_a)},
                        {"name": "skillB", "path": str(skill_b)},
                    ]
                }
            ),
            encoding="utf-8",
        )
        bundler = SkillBundler(registry_path=registry)

        # ambOS dominios empatan por keyword; solo domB cubre "alpha beta".
        selected = bundler.select_skills("domA", task="alpha beta")

        assert selected == ["skillB"]

    def test_no_ambiguity_keeps_domain(self) -> None:
        """Sin ambiguedad, ``select_skills`` conserva el dominio pedido."""
        assert "security-audit" in SkillBundler().select_skills("security")
