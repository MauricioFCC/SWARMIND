"""Sonda adversarial de la selección/descarte de SKILLS del coordinator (ADV/TDD).

WHAT: expone el comportamiento REAL (y sus debilidades) de la capa que decide
qué skill cargar o descartar: ``SkillBundler`` (``detect_domain``/
``select_skills``/``compose``), ``coordinator_dispatch.dispatch``,
``AgentDispatcher.find_skill_for_task`` y ``SkillGenerator.find_in_registry``.
WHY: un agente nunca afirma, verifica (VER). Antes de confiar en la selección
hay que probar falsos positivos/negativos, el umbral 0.70, el score YAML fijo
0.80, ``inherit`` vs selección, dedup, abstinencia, determinismo e inyección.
WHERE: ``harness/tests`` — sonda de solo lectura sobre producción (no la edita).

Convención: los tests marcados ``xfail(strict=True)`` documentan FALLOS
CONOCIDOS con el comportamiento DESEADO como aserción; si el fallo se corrige,
el test pasa a ``XPASS`` y rompe la suite (recordatorio de re-calibrar), nunca
se ablanda el test para "pintar verde".
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from harness.evolve_loop.skill_generator import SkillGenerator
from harness.orchestrator.agent_dispatcher import (
    SIMILARITY_THRESHOLD,
    AgentDispatcher,
)
from harness.orchestrator.coordinator_dispatch import dispatch
from harness.orchestrator.skill_bundler import DOMAIN_SKILLS, SkillBundler

# ---------------------------------------------------------------------------
# Constantes de la sonda (MAG: sin literales repetidos)
# ---------------------------------------------------------------------------

#: Tarea financiera que contiene "capital" (substring "api").
_TASK_CAPITAL = "asignar capital del fondo por mandato"

#: Tarea de riesgo que contiene "position" (substring "pos").
_TASK_POSITION = "position sizing para la cuenta"

#: Tarea DevOps que contiene "docker" (substring "doc").
_TASK_DOCKER = "deploy con docker"

#: Tarea Python/Flask (sin relación real con Rust).
_TASK_FLASK = "necesito un endpoint en Python con Flask"

#: Keywords y palabras que las contienen (evidencia del matching por substring).
_KW_API = "api"
_KW_POS = "pos"
_KW_DOC = "doc"
_WORD_CAPITAL = "capital"
_WORD_POSITION = "position"
_WORD_DOCKER = "docker"


def _empty_vector_store() -> object:
    """Devuelve un centinela no-None para habilitar el camino LanceDB.

    Returns:
        Objeto opaco; solo se usa como marcador de "hay vector store".
    """
    return object()


# ===========================================================================
# A. FALSOS POSITIVOS — matching por substring
# ===========================================================================


class TestFalsosPositivos:
    """El matcher por frontera de palabra evita colisiones de substring.

    Las colisiones existen en los strings crudos, pero el matcher
    (``keyword_match.contains_word``) ya no las usa: 'docker' no dispara 'doc',
    'capital' no dispara 'api', 'position' no dispara 'pos'.
    """

    def test_mecanismo_substring_colisiona(self) -> None:
        """Motiva la frontera: 'api'⊂'capital', 'pos'⊂'position', 'doc'⊂'docker'."""
        assert _KW_API in _WORD_CAPITAL
        assert _KW_POS in _WORD_POSITION
        assert _KW_DOC in _WORD_DOCKER

    def test_capital_no_deberia_ser_dominio_api(self) -> None:
        """Corregido: 'capital' ya no dispara 'api' (frontera de palabra)."""
        assert SkillBundler().detect_domain(_TASK_CAPITAL) != "api"

    def test_position_no_deberia_ser_dominio_retail(self) -> None:
        """Corregido: 'position' ya no dispara 'pos' (frontera de palabra)."""
        assert SkillBundler().detect_domain(_TASK_POSITION) != "retail"

    def test_docker_no_deberia_cargar_legal_doc(self) -> None:
        """Corregido: 'docker' ya no dispara 'doc'; no arrastra skills de documentación."""
        skills = SkillBundler().select_skills("devops", _TASK_DOCKER)
        assert "legal-doc" not in skills

    @pytest.mark.xfail(
        strict=True,
        reason="FALLO: dominio api incluye rust-lang fijo -> tarea Python carga Rust",
    )
    def test_api_python_no_deberia_cargar_rust(self) -> None:
        """Un endpoint REST en Python no debe cargar el skill de Rust."""
        skills = SkillBundler().select_skills("api", "endpoint REST en Python")
        assert "rust-lang" not in skills

    @pytest.mark.xfail(
        strict=True,
        reason="FALLO: coordinator hereda el orden fijo del dominio (rust-lang entra)",
    )
    def test_coordinator_flask_no_deberia_cargar_rust(self) -> None:
        """El plan del coordinator para Flask no debe declarar rust-lang."""
        assert "rust-lang" not in dispatch(_TASK_FLASK).skills


# ===========================================================================
# B. FALSOS NEGATIVOS — sin match exacto pero cubierto semánticamente
# ===========================================================================


class TestFalsosNegativos:
    """El registro matchea por tokens (frontera de palabra) contra sus campos."""

    def test_find_in_registry_match_exacto_funciona(self) -> None:
        """Un keyword exacto ('rust') sí encuentra la skill en el registro."""
        assert SkillGenerator.find_in_registry("rust") is not None

    def test_find_in_registry_frase_natural_matchea(self) -> None:
        """Corregido: una frase natural matchea por tokens (security-audit)."""
        match = SkillGenerator.find_in_registry("auditoria de seguridad")
        assert match is not None
        assert match["name"] == "security-audit"

    def test_frase_natural_deberia_matchear(self) -> None:
        """Una consulta natural sobre seguridad encuentra security-audit."""
        assert SkillGenerator.find_in_registry("auditoria de seguridad owasp") is not None

    def test_dispatcher_frase_natural_deberia_matchear(self) -> None:
        """El dispatcher encuentra rust-lang ante una frase natural (match por tokens)."""
        assert AgentDispatcher().find_skill_for_task("necesito programar en rust") is not None

    @pytest.mark.xfail(
        strict=True,
        reason="FALLO: el coordinator no carga evolve al elegir el agente evolve",
    )
    def test_coordinator_evolve_deberia_cargar_skill_evolve(self) -> None:
        """Si el agente elegido es 'evolve', su skill debe estar en el plan."""
        plan = dispatch("quiero mejorar mis skills del sistema")
        assert "evolve" in plan.skills


# ===========================================================================
# C. THRESHOLD y SCORE fijo
# ===========================================================================


class TestThresholdYScore:
    """Umbral 0.70 inclusivo y score YAML fijo 0.80 (no calibrado)."""

    def test_threshold_dispatch_borde_inclusivo(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """En el borde exacto 0.70 dispatch carga la skill (>=)."""
        dispatcher = AgentDispatcher()
        monkeypatch.setattr(
            dispatcher,
            "find_skill_for_task",
            lambda _task: {"name": "edge", "content": "x", "similarity": SIMILARITY_THRESHOLD},
        )
        assert dispatcher.dispatch("se", "tarea").get("skill_name") == "edge"

    def test_threshold_dispatch_justo_debajo_descarta(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Un pelo por debajo de 0.70 se descarta (from_scratch)."""
        dispatcher = AgentDispatcher()
        monkeypatch.setattr(
            dispatcher,
            "find_skill_for_task",
            lambda _task: {"name": "low", "content": "x", "similarity": SIMILARITY_THRESHOLD - 1e-9},
        )
        assert dispatcher.dispatch("se", "tarea")["used_skill"] is False

    def test_threshold_lancedb_borde(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """El camino LanceDB aplica el mismo borde inclusivo 0.70."""
        monkeypatch.setattr(
            "harness.orchestrator.agent_dispatcher.SkillGenerator.find_in_registry",
            lambda _query: None,
        )
        dispatcher = AgentDispatcher(vector_store=_empty_vector_store())
        monkeypatch.setattr(
            dispatcher,
            "_search_lancedb_skills",
            lambda _query: {"name": "edge", "similarity": SIMILARITY_THRESHOLD},
        )
        assert dispatcher.find_skill_for_task("tarea") is not None

    def test_threshold_lancedb_debajo_descarta(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """El camino LanceDB descarta por debajo de 0.70."""
        monkeypatch.setattr(
            "harness.orchestrator.agent_dispatcher.SkillGenerator.find_in_registry",
            lambda _query: None,
        )
        dispatcher = AgentDispatcher(vector_store=_empty_vector_store())
        monkeypatch.setattr(
            dispatcher,
            "_search_lancedb_skills",
            lambda _query: {"name": "low", "similarity": SIMILARITY_THRESHOLD - 1e-9},
        )
        assert dispatcher.find_skill_for_task("tarea") is None

    def test_score_yaml_fijo_080_y_contenido_resuelto(self) -> None:
        """Corregido: el name-match reporta 0.80 y ahora resuelve el ``content``.

        El score del matcher YAML sigue normalizado a 0.80 (keyword match
        fuerte); el ``path`` curado se resuelve por nombre y el contenido del
        skill deja de quedar vacío -> 'guided_by_skill' con texto real.
        """
        result = AgentDispatcher().find_skill_for_task("rust")
        assert result is not None
        assert result["similarity"] == 0.80
        assert result["content"] != ""

    def test_skill_matcheada_deberia_traer_contenido(self) -> None:
        """Corregido: una skill encontrada por el registry inyecta su contenido."""
        result = AgentDispatcher().find_skill_for_task("rust")
        assert result is not None
        assert result["content"].strip() != ""


# ===========================================================================
# D. INHERIT vs SELECCIÓN
# ===========================================================================


class TestInheritNoAfectaSeleccion:
    """``inherit`` solo afecta el contenido inyectado; jamás la selección."""

    def test_skill_con_inherit_roto_sigue_seleccionada(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """Una herencia rota reporta inherited_ok=False pero la skill se elige igual."""
        skill_md = tmp_path / "broken" / "SKILL.md"
        skill_md.parent.mkdir(parents=True)
        skill_md.write_text(
            "---\nname: broken\ninherit:\n  - core/missing-xyz.md\n---\n# Broken\n",
            encoding="utf-8",
        )
        entry: dict[str, Any] = {"name": "broken", "path": str(skill_md)}
        monkeypatch.setattr(
            "harness.orchestrator.agent_dispatcher.SkillGenerator.find_in_registry",
            lambda _query: dict(entry),
        )
        result = AgentDispatcher().find_skill_for_task("tarea")
        assert result is not None
        assert result["inherited_ok"] is False


# ===========================================================================
# E. DEDUP
# ===========================================================================


class TestDedup:
    """Dentro de una selección no hay duplicados y el registry deduplica
    near-duplicates por tokens del NOMBRE (Jaccard >= 0.9)."""

    def test_select_skills_sin_duplicados(self) -> None:
        """select_skills nunca debe repetir una skill en la misma lista."""
        bundler = SkillBundler()
        skills = bundler.select_skills("devops", _TASK_DOCKER)
        assert len(skills) == len(set(skills))

    def test_registry_deduplica_casi_identicas(self, tmp_path: Path) -> None:
        """Corregido: dos nombres con el mismo token normalizado colapsan a uno."""
        registry = tmp_path / "registry.yaml"
        registry.write_text(
            "skills:\n"
            "  - name: security-audit\n    domain: meta\n    description: \"mejora skills\"\n"
            "  - name: security_audit\n    domain: meta\n    description: \"mejora skills\"\n",
            encoding="utf-8",
        )
        assert len(SkillBundler(registry_path=registry).list_skills()) == 1


# ===========================================================================
# F. ABSTENTION
# ===========================================================================


class TestAbstencion:
    """Tanto el dispatcher como el bundler abstienen ante entrada sin señal."""

    def test_dispatcher_abstiene_ante_ruido(self) -> None:
        """Sin vector store ni match, el dispatcher devuelve None (abstiene)."""
        assert AgentDispatcher().find_skill_for_task("xyzzy plugh") is None

    def test_bundler_abstiene_ante_dominio_desconocido(self) -> None:
        """Corregido: un dominio desconocido devuelve [] (abstention, no 'general')."""
        assert SkillBundler().select_skills("dominio_inexistente") == []

    def test_coordinator_nunca_devuelve_skills_vacias(self) -> None:
        """El coordinator fabrica skills aunque la tarea no tenga relación."""
        assert len(dispatch("xyzzy plugh").skills) > 0


# ===========================================================================
# G. DETERMINISMO
# ===========================================================================


class TestDeterminismo:
    """Misma tarea -> misma selección (sin aleatoriedad sin semilla)."""

    def test_detect_domain_determinista(self) -> None:
        """detect_domain es estable entre llamadas."""
        bundler = SkillBundler()
        assert bundler.detect_domain(_TASK_FLASK) == bundler.detect_domain(_TASK_FLASK)

    def test_dispatch_determinista(self) -> None:
        """dispatch produce el mismo plan (agente, skills) entre llamadas."""
        first = dispatch(_TASK_FLASK)
        second = dispatch(_TASK_FLASK)
        assert (first.agent, first.skills) == (second.agent, second.skills)


# ===========================================================================
# H. DESCARTE TOTAL vía path determinista
# ===========================================================================


class TestDescarteTotal:
    """El guard financiero de is_closed_task evita el descarte total de skills."""

    def test_position_sizing_no_marca_tarea_cerrada(self) -> None:
        """Corregido: el contexto financiero desactiva la allowlist cerrada."""
        plan = dispatch(_TASK_POSITION)
        assert plan.deterministic is False
        assert plan.skills

    def test_position_sizing_no_deberia_descartar_skills(self) -> None:
        """Una tarea de riesgo substantiva no va por el path determinista."""
        assert dispatch(_TASK_POSITION).deterministic is False


# ===========================================================================
# I. INYECCIÓN / BLOAT
# ===========================================================================


class TestInyeccion:
    """La inyección por keyword respeta frontera de palabra; el coordinator topa."""

    def test_docker_no_inyecta_skills_de_documentacion(self) -> None:
        """Corregido: 'docker' no dispara 'doc'; no inyecta science-doc/legal-doc."""
        skills = SkillBundler().select_skills("devops", _TASK_DOCKER)
        assert "science-doc" not in skills
        assert "legal-doc" not in skills

    def test_coordinator_topa_skills_por_presupuesto(self) -> None:
        """El coordinator recorta a max_skills aunque la selección sea mayor."""
        assert len(dispatch(_TASK_DOCKER, max_skills=3).skills) <= 3

    def test_compose_no_topa_y_crece(self) -> None:
        """compose (sin tope) expande el bundle por encima del presupuesto del coordinator."""
        total = sum(len(c.bundled_skills) for c in SkillBundler().compose(_TASK_DOCKER))
        assert total > len(DOMAIN_SKILLS["general"])
