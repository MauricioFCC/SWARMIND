"""Tests TDD del veto duro de anti-triggers en el router (Codex #34712).

WHAT: los anti-triggers en prosa de la ``description`` ("No usar para X") los
ignora el routing implicito; el veto NEGATIVO debe vivir en el ROUTER (veto
duro) y excluir al candidato ANTES del rank.

WHY: la description "pushy" convive con clausulas de alcance ("para X ver Y")
y anti-triggers ("No usar", "Evitar", "Cuando NO usar", "anti-trigger"). El
matching por tokens puede cargar una skill que explicitamente NO aplica. El veto
duro (Codex #34712 + ThakiCloud Description Budget) cierra ese falso positivo.

WHERE: ``harness/tests/test_hard_veto_router.py`` — sonda sobre produccion
(``AgentDispatcher``, ``hard_veto_score``, ``apply_hard_veto``).

Cubre:
  (a) veto cuando la clausula anti-trigger menciona la tarea;
  (b) NO veto cuando menciona otra cosa (tokens distintos);
  (c) description sin anti-trigger -> no veta;
  (d) ``veto_context_chars=0`` -> comportamiento definido y sin excepcion;
  (e) mutation-style: borrar la clausula de veto rompe el oraculo (2 asserts).
"""

from __future__ import annotations

from harness.orchestrator.agent_dispatcher import (
    NEGATIVE_TRIGGER_RE,
    VETO_CONTEXT_CHARS,
    VETO_TOKEN_MATCH,
    AgentDispatcher,
    apply_hard_veto,
    hard_veto_score,
)

# ---------------------------------------------------------------------------
# Fixtures de texto (MAG: sin literales repetidos)
# ---------------------------------------------------------------------------

#: Description con anti-trigger explicito sobre "kubernetes".
_VETO_DESC = "Usar cuando el usuario despliega contenedores. No usar para kubernetes."

#: Tarea que SI menciona el dominio vetado (kubernetes).
_TASK_VETO = "quiero desplegar kubernetes en produccion"

#: Tarea que NO menciona el dominio vetado.
_TASK_OK = "quiero analizar finanzas del trimestre"

#: Description limpia (sin ningun anti-trigger).
_CLEAN_DESC = "Usar cuando el usuario analiza series de datos y metricas."

_VETO_TOKEN = "kubernetes"


def _vetoed_skill() -> dict[str, str]:
    """Candidato de skill con anti-trigger sobre kubernetes."""
    return {"name": "devops-infra", "description": _VETO_DESC}


# ===========================================================================
# Constantes del contrato
# ===========================================================================


def test_constantes_del_contrato() -> None:
    """Las constantes del veto respetan el contrato (60 chars, 1 token)."""
    assert VETO_CONTEXT_CHARS == 60
    assert VETO_TOKEN_MATCH == 1
    assert NEGATIVE_TRIGGER_RE.search("No usar para X") is not None
    assert NEGATIVE_TRIGGER_RE.search("Cuando NO usar: ver Alcance") is not None


# ===========================================================================
# (a) veto cuando la clausula menciona la tarea
# ===========================================================================


def test_a_hard_veto_score_veta_cuando_clausula_menciona_tarea() -> None:
    """(a) La clausula anti-trigger menciona la tarea -> score 0.0 (veta)."""
    assert hard_veto_score(_VETO_DESC, _TASK_VETO) == 0.0


def test_a_apply_hard_veto_excluye_candidato() -> None:
    """(a) El candidato vetado desaparece de la lista filtrada."""
    assert apply_hard_veto([_vetoed_skill()], _TASK_VETO) == []


# ===========================================================================
# (b) NO veto cuando la clausula menciona otra cosa
# ===========================================================================


def test_b_hard_veto_score_no_veta_si_tokens_distintos() -> None:
    """(b) La clausula anti-trigger no menciona la tarea -> score 1.0."""
    assert hard_veto_score(_VETO_DESC, _TASK_OK) == 1.0


def test_b_apply_hard_veto_conserva_candidato() -> None:
    """(b) El candidato no vetado permanece en la lista filtrada."""
    skill = _vetoed_skill()
    assert apply_hard_veto([skill], _TASK_OK) == [skill]


# ===========================================================================
# (c) description sin anti-trigger -> no veta
# ===========================================================================


def test_c_sin_anti_trigger_no_veta() -> None:
    """(c) Sin anti-trigger en la description -> score 1.0 y candidato conservado."""
    assert hard_veto_score(_CLEAN_DESC, _TASK_VETO) == 1.0
    skill = {"name": "data-science", "description": _CLEAN_DESC}
    assert apply_hard_veto([skill], _TASK_VETO) == [skill]


# ===========================================================================
# (d) veto_context_chars=0 -> definido y sin excepcion
# ===========================================================================


def test_d_contexto_cero_definido_sin_excepcion() -> None:
    """(d) Con 0 chars de contexto no hay clausula -> score 1.0, sin excepcion."""
    score = hard_veto_score(_VETO_DESC, _TASK_VETO, veto_context_chars=0)
    assert score in (0.0, 1.0)
    assert score == 1.0


# ===========================================================================
# (e) mutation-style: borrar la clausula de veto rompe el oraculo
# ===========================================================================


def test_e_mutation_borrar_clausula_rompe_oraculo() -> None:
    """(e) Con la clausula -> veta; al borrarla -> deja de vetar (2 asserts).

    Si la implementacion ignorara la clausula y vetara por la sola presencia del
    trigger, el mutante (sin clausula) seguiria vetando y este test fallaria.
    """
    # 1) Description con clausula anti-trigger -> veta la tarea que la menciona.
    assert hard_veto_score(_VETO_DESC, _TASK_VETO) == 0.0

    # 2) Mutante: se BORRA la clausula de veto -> ya no veta.
    mutated = _VETO_DESC.split("No usar")[0].strip()
    assert "No usar" not in mutated
    assert hard_veto_score(mutated, _TASK_VETO) == 1.0


def test_e_mutante_token_match_alto_no_veta() -> None:
    """(e) Si se exige mas interseccion de la disponible, el veto no se confirma.

    Discrimina un mutante que ignorase ``veto_token_match``.
    """
    assert hard_veto_score(
        _VETO_DESC, _TASK_VETO, veto_token_match=VETO_TOKEN_MATCH + 5
    ) == 1.0


# ===========================================================================
# Integracion: el dispatcher aplica el veto ANTES de devolver el candidato
# ===========================================================================


def test_dispatcher_veta_candidato_del_registry(monkeypatch) -> None:
    """El dispatcher devuelve None si el unico match del registry esta vetado."""
    monkeypatch.setattr(
        "harness.orchestrator.agent_dispatcher.SkillGenerator.find_in_registry",
        lambda _query: {"name": "devops-infra", "description": _VETO_DESC, "path": ""},
    )
    dispatcher = AgentDispatcher()
    assert dispatcher.find_skill_for_task(_TASK_VETO) is None


def test_dispatcher_conserva_candidato_no_vetado(monkeypatch) -> None:
    """El dispatcher conserva el candidato si la tarea no activa el anti-trigger."""
    monkeypatch.setattr(
        "harness.orchestrator.agent_dispatcher.SkillGenerator.find_in_registry",
        lambda _query: {"name": "data-science", "description": _CLEAN_DESC, "path": ""},
    )
    dispatcher = AgentDispatcher()
    result = dispatcher.find_skill_for_task(_TASK_VETO)
    assert result is not None
    assert result["name"] == "data-science"
