"""
Tests para Worktable — Mesa de Trabajo multi-agente.

Verifica:
  - Inicializacion correcta del Worktable
  - Debate con todos los agentes y subconjuntos
  - Estructura del Compendium
  - Dispatch simulado (modo offline)
  - Diferentes configuraciones de rondas (1, 2, 3)
  - Manejo de lista vacia de agentes
  - Completitud de perfiles de agente
  - Log del debate
"""

from __future__ import annotations

from typing import Any, Dict
from unittest.mock import MagicMock, patch

import pytest

from harness.orchestrator.worktable import (
    AGENT_PROFILES,
    AgentPosition,
    Compendium,
    DebateRound,
    Worktable,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def worktable() -> Worktable:
    """Worktable instance with default mock dispatch (modo offline)."""
    return Worktable()


@pytest.fixture
def custom_dispatch() -> Dict[str, Any]:
    """Factory for a deterministic dispatch function."""
    def _dispatch(
        agent: str,
        topic: str,
        round_type: DebateRound,
        profile: Dict[str, Any],
        **kwargs: Any,
    ) -> Dict[str, Any]:
        if round_type == DebateRound.OPENING:
            return {
                "stance": "a favor",
                "arguments": [
                    f"{profile['abbr']}: Argumento principal para {topic}",
                    f"Recomiendo: {profile['bias'][:80]}",
                ],
            }
        elif round_type == DebateRound.CRITIQUE:
            other_agents = kwargs.get("other_agents", [])
            concerns = [
                f"Preocupacion sobre {AGENT_PROFILES.get(o, {}).get('abbr', o)}"
                for o in other_agents[:2]
            ]
            return {"concerns": concerns}
        else:
            return {
                "arguments": [f"{profile['abbr']}: Propuesta refinada"],
                "vote": "aceptar",
            }
    return _dispatch


# ---------------------------------------------------------------------------
# Test: Init
# ---------------------------------------------------------------------------


class TestInit:
    """Worktable inicializa correctamente."""

    def test_init_default(self) -> None:
        """Worktable sin argumentos usa mock_dispatch."""
        wt = Worktable()
        assert wt._dispatch is not None
        assert wt._dispatch.__name__ == "_mock_dispatch"
        assert wt._positions == {}
        assert wt._round == 0
        assert wt._log == []

    def test_init_with_custom_dispatch(self, custom_dispatch: Any) -> None:
        """Worktable con dispatch personalizado."""
        wt = Worktable(dispatch_fn=custom_dispatch)
        assert wt._dispatch is not None
        assert wt._dispatch is custom_dispatch

    def test_init_positions_empty(self) -> None:
        """Posiciones inicialmente vacias."""
        wt = Worktable()
        assert wt.get_positions() == {}

    def test_init_log_empty(self) -> None:
        """Log inicialmente vacio."""
        wt = Worktable()
        assert wt.get_log() == []


# ---------------------------------------------------------------------------
# Test: Debate con todos los agentes
# ---------------------------------------------------------------------------


class TestDebateAllAgents:
    """Debate utilizando todos los agentes definidos."""

    def test_debate_all_agents_default(self, worktable: Worktable) -> None:
        """Debate con todos los agentes (default) y 3 rondas."""
        compendium = worktable.debate(
            topic="Disenar API REST para pagos",
        )
        assert isinstance(compendium, Compendium)
        assert len(compendium.participants) == len(AGENT_PROFILES)
        assert compendium.rounds == 3
        assert compendium.summary != ""

    def test_debate_all_agents_fields(self, worktable: Worktable) -> None:
        """Compendio con todos los agentes tiene campos poblados."""
        compendium = worktable.debate(
            topic="Arquitectura de microservicios",
        )
        # Todos los agentes participaron
        for agent_name in AGENT_PROFILES:
            assert agent_name in compendium.participants, (
                f"Agente {agent_name} no esta en participantes"
            )
        # Hay trade-offs identificados
        assert len(compendium.trade_offs) > 0
        # Hay agreement o recommendations
        has_content = (
            len(compendium.agreements) > 0
            or len(compendium.recommendations) > 0
        )
        assert has_content, "Debe haber agreements o recommendations"

    def test_debate_all_agents_positions(self, worktable: Worktable) -> None:
        """Despues del debate, todos los agentes tienen posiciones."""
        compendium = worktable.debate(
            topic="Sistema de notificaciones en tiempo real",
        )
        positions = worktable.get_positions()
        assert len(positions) == len(AGENT_PROFILES)
        for agent_name in AGENT_PROFILES:
            pos = positions.get(agent_name)
            assert pos is not None, f"Agente {agent_name} sin posicion"
            assert pos.agent_name == agent_name
            # Debe tener argumentos (ronda 1)
            assert len(pos.arguments) > 0, f"{agent_name} no tiene argumentos"
            # Debe tener vote (ronda 3)
            assert pos.vote in ("aceptar", "rechazar", "abstencion")


# ---------------------------------------------------------------------------
# Test: Debate con subconjunto de agentes
# ---------------------------------------------------------------------------


class TestDebateSubset:
    """Debate con solo algunos agentes."""

    def test_debate_three_agents(self, worktable: Worktable) -> None:
        """Debate con solo 3 agentes especificos."""
        selected = ["soc", "coupling", "cohesion"]
        compendium = worktable.debate(
            topic="Disenar modulo de autenticacion",
            agents=selected,
        )
        assert len(compendium.participants) == 3
        for a in selected:
            assert a in compendium.participants
        # Solo los seleccionados
        assert all(a in selected for a in compendium.participants)

    def test_debate_two_agents(self, worktable: Worktable) -> None:
        """Debate con solo 2 agentes."""
        selected = ["security", "scalability"]
        compendium = worktable.debate(
            topic="Arquitectura cloud-native",
            agents=selected,
        )
        assert len(compendium.participants) == 2
        assert "security" in compendium.participants
        assert "scalability" in compendium.participants

    def test_debate_single_agent(self, worktable: Worktable) -> None:
        """Debate con 1 solo agente (caso borde)."""
        compendium = worktable.debate(
            topic="Decicion simple",
            agents=["clean_code"],
        )
        assert len(compendium.participants) == 1
        assert compendium.participants[0] == "clean_code"
        assert compendium.rounds == 3

    def test_debate_subset_positions(self, worktable: Worktable) -> None:
        """Solo los agentes seleccionados tienen posiciones."""
        selected = ["resilience", "observability", "testability"]
        compendium = worktable.debate(
            topic="Sistema de monitoreo",
            agents=selected,
        )
        positions = worktable.get_positions()
        assert len(positions) == 3
        for a in selected:
            assert a in positions


# ---------------------------------------------------------------------------
# Test: Estructura del Compendium
# ---------------------------------------------------------------------------


class TestCompendiumStructure:
    """Compendio tiene los campos correctos."""

    def test_compendium_defaults(self) -> None:
        """Compendium con valores por defecto."""
        comp = Compendium()
        assert comp.summary == ""
        assert comp.agreements == []
        assert comp.trade_offs == []
        assert comp.rejected == []
        assert comp.recommendations == []
        assert comp.participants == []
        assert comp.rounds == 0

    def test_compendium_after_debate(self, worktable: Worktable) -> None:
        """Compendium post-debate tiene todos los campos poblados."""
        comp = worktable.debate(
            topic="Disenar gateway de pagos",
            agents=["soc", "security", "scalability"],
        )
        assert isinstance(comp.summary, str)
        assert len(comp.summary) > 0
        assert isinstance(comp.agreements, list)
        assert isinstance(comp.trade_offs, list)
        assert isinstance(comp.rejected, list)
        assert isinstance(comp.recommendations, list)
        assert isinstance(comp.participants, list)
        assert isinstance(comp.rounds, int)

    def test_compendium_summary_format(self, worktable: Worktable) -> None:
        """Summary comienza con COMPENDIO."""
        comp = worktable.debate(
            topic="Disenar API REST",
            agents=["soc", "coupling", "cohesion"],
        )
        assert comp.summary.startswith("COMPENDIO "), (
            f"Summary debe empezar con 'COMPENDIO': {comp.summary}"
        )

    def test_compendium_trade_offs_structure(self, worktable: Worktable) -> None:
        """Cada trade-off tiene from y concern."""
        comp = worktable.debate(
            topic="Base de datos distribuida",
            agents=["soc", "coupling", "scalability", "resilience"],
        )
        for to in comp.trade_offs:
            assert "from" in to, f"Trade-off sin 'from': {to}"
            assert "concern" in to, f"Trade-off sin 'concern': {to}"
            assert isinstance(to["from"], str)
            assert isinstance(to["concern"], str)

    def test_compendium_participants_unique(self, worktable: Worktable) -> None:
        """Participantes no tienen duplicados."""
        comp = worktable.debate(
            topic="Sistema de colas",
            agents=["soc", "coupling", "cohesion"],
        )
        assert len(comp.participants) == len(set(comp.participants))


# ---------------------------------------------------------------------------
# Test: Mock Dispatch
# ---------------------------------------------------------------------------


class TestMockDispatch:
    """Dispatch simulado funciona correctamente."""

    def test_mock_dispatch_opening(self) -> None:
        """Mock dispatch en ronda OPENING devuelve stance y arguments."""
        wt = Worktable()
        profile = AGENT_PROFILES["soc"]
        response = wt._mock_dispatch(
            agent="soc",
            topic="Disenar API REST",
            round_type=DebateRound.OPENING,
            profile=profile,
        )
        assert "stance" in response
        assert response["stance"] in ("a favor", "en contra")
        assert "arguments" in response
        assert len(response["arguments"]) >= 1
        # Stance basado en len(topic) % 2
        assert response["stance"] == "a favor"  # len("Disenar API REST") % 2 == 0

    def test_mock_dispatch_opening_odd_topic(self) -> None:
        """Topic con longitud impar -> stance 'en contra'."""
        wt = Worktable()
        profile = AGENT_PROFILES["coupling"]
        response = wt._mock_dispatch(
            agent="coupling",
            topic="ABC",  # len=3 -> impar
            round_type=DebateRound.OPENING,
            profile=profile,
        )
        assert response["stance"] == "en contra"

    def test_mock_dispatch_critique(self) -> None:
        """Mock dispatch en ronda CRITIQUE devuelve concerns."""
        wt = Worktable()
        profile = AGENT_PROFILES["security"]
        response = wt._mock_dispatch(
            agent="security",
            topic="Disenar API",
            round_type=DebateRound.CRITIQUE,
            profile=profile,
            other_agents=["soc", "coupling", "cohesion"],
        )
        assert "concerns" in response
        assert len(response["concerns"]) >= 1
        assert any("Preocupacion" in c for c in response["concerns"])

    def test_mock_dispatch_critique_no_others(self) -> None:
        """Critique sin other_agents devuelve lista vacia."""
        wt = Worktable()
        profile = AGENT_PROFILES["testability"]
        response = wt._mock_dispatch(
            agent="testability",
            topic="Disenar API",
            round_type=DebateRound.CRITIQUE,
            profile=profile,
        )
        assert response == {"concerns": []}

    def test_mock_dispatch_refinement(self) -> None:
        """Mock dispatch en ronda REFINEMENT devuelve arguments y vote."""
        wt = Worktable()
        profile = AGENT_PROFILES["clean_code"]
        response = wt._mock_dispatch(
            agent="clean_code",
            topic="Disenar API",
            round_type=DebateRound.REFINEMENT,
            profile=profile,
        )
        assert "arguments" in response
        assert "vote" in response
        assert response["vote"] in ("aceptar", "rechazar")
        # clean_code tiene len par (10) -> aceptar
        assert response["vote"] == "aceptar"

    def test_mock_dispatch_refinement_reject(self) -> None:
        """Agente con nombre impar -> voto rechazar."""
        wt = Worktable()
        profile = AGENT_PROFILES["soc"]  # len=3 -> impar
        response = wt._mock_dispatch(
            agent="soc",
            topic="Disenar API",
            round_type=DebateRound.REFINEMENT,
            profile=profile,
        )
        assert response["vote"] == "rechazar"

    def test_mock_dispatch_profile_fields(self) -> None:
        """Dispatch usa profile.bias y profile.questions correctamente."""
        wt = Worktable()
        profile = AGENT_PROFILES["resilience"]
        response = wt._mock_dispatch(
            agent="resilience",
            topic="Sistema critico",
            round_type=DebateRound.OPENING,
            profile=profile,
        )
        args = response["arguments"]
        assert any("Resilience" in a for a in args)
        assert any("redundancia" in a.lower() or "fallos" in a.lower() for a in args)


# ---------------------------------------------------------------------------
# Test: Debate con 1 ronda
# ---------------------------------------------------------------------------


class TestDebate1Round:
    """Debate con solo 1 ronda (solo postura inicial)."""

    def test_debate_1_round_basic(self, worktable: Worktable) -> None:
        """Debate con rounds=1 solo ejecuta ronda de apertura."""
        compendium = worktable.debate(
            topic="Disenar cache distribuido",
            agents=["soc", "coupling", "scalability"],
            rounds=1,
        )
        assert compendium.rounds == 1
        assert compendium.summary != ""

    def test_debate_1_round_no_critique(self) -> None:
        """Con 1 ronda, no hay concerns (critica no se ejecuta)."""
        wt = Worktable()
        compendium = wt.debate(
            topic="Sistema simple",
            agents=["soc", "coupling"],
            rounds=1,
        )
        positions = wt.get_positions()
        for agent_name, pos in positions.items():
            assert pos.concerns == [], (
                f"{agent_name} no deberia tener concerns con 1 ronda"
            )
            assert pos.vote == "abstencion", (
                f"{agent_name} no deberia tener voto con 1 ronda"
            )

    def test_debate_1_round_log_length(self, worktable: Worktable) -> None:
        """Log debe tener solo entradas de ronda 1."""
        compendium = worktable.debate(
            topic="Monolito vs microservicios",
            agents=["soc", "cohesion", "maintainability"],
            rounds=1,
        )
        log = worktable.get_log()
        assert all(entry["round"] == 1 for entry in log)
        assert all(entry["type"] == "opening" for entry in log)

    def test_debate_1_round_positions_have_arguments(self, worktable: Worktable) -> None:
        """Posiciones tras 1 ronda tienen argumentos pero no concerns."""
        compendium = worktable.debate(
            topic="Elegir base de datos",
            agents=["soc", "scalability"],
            rounds=1,
        )
        positions = worktable.get_positions()
        for agent_name, pos in positions.items():
            assert len(pos.arguments) > 0
            assert pos.concerns == []
            assert pos.vote == "abstencion"


# ---------------------------------------------------------------------------
# Test: Debate con 2 rondas
# ---------------------------------------------------------------------------


class TestDebate2Rounds:
    """Debate con 2 rondas (apertura + critica)."""

    def test_debate_2_rounds_basic(self, worktable: Worktable) -> None:
        """Debate con rounds=2 ejecuta apertura + critica."""
        compendium = worktable.debate(
            topic="Disenar API GraphQL",
            agents=["soc", "coupling", "interoperability"],
            rounds=2,
        )
        assert compendium.rounds == 2

    def test_debate_2_rounds_has_concerns(self) -> None:
        """Con 2 rondas, los agentes tienen concerns (critica)."""
        wt = Worktable()
        compendium = wt.debate(
            topic="Arquitectura hexagonal",
            agents=["soc", "coupling", "cohesion"],
            rounds=2,
        )
        positions = wt.get_positions()
        for agent_name, pos in positions.items():
            assert len(pos.concerns) > 0, (
                f"{agent_name} deberia tener concerns con 2 rondas"
            )

    def test_debate_2_rounds_no_vote(self) -> None:
        """Con 2 rondas, no hay voto (refinamiento no se ejecuta)."""
        wt = Worktable()
        compendium = wt.debate(
            topic="Patron CQRS",
            agents=["soc", "coupling"],
            rounds=2,
        )
        positions = wt.get_positions()
        for agent_name, pos in positions.items():
            assert pos.vote == "abstencion", (
                f"{agent_name} no deberia tener voto con 2 rondas"
            )

    def test_debate_2_rounds_log_types(self, worktable: Worktable) -> None:
        """Log debe tener entradas de tipo opening y critique."""
        compendium = worktable.debate(
            topic="Event sourcing",
            agents=["soc", "scalability", "resilience"],
            rounds=2,
        )
        log = worktable.get_log()
        types = [entry["type"] for entry in log]
        assert "opening" in types
        assert "critique" in types
        assert "refinement" not in types


# ---------------------------------------------------------------------------
# Test: Lista vacia de agentes
# ---------------------------------------------------------------------------


class TestDebateEmptyAgents:
    """Manejo de lista vacia de agentes."""

    def test_debate_empty_list(self, worktable: Worktable) -> None:
        """Lista vacia retorna Compendium vacio."""
        compendium = worktable.debate(
            topic="Cualquier tema",
            agents=[],
        )
        assert isinstance(compendium, Compendium)
        assert compendium.summary == ""
        assert compendium.participants == []
        assert compendium.rounds == 0

    def test_debate_none_agents(self, worktable: Worktable) -> None:
        """agents=None usa todos los agentes definidos."""
        compendium = worktable.debate(
            topic="Tema generico",
            agents=None,
        )
        assert len(compendium.participants) == len(AGENT_PROFILES)

    def test_debate_invalid_agents(self, worktable: Worktable) -> None:
        """Agentes invalidos son filtrados."""
        compendium = worktable.debate(
            topic="Tema",
            agents=["non_existent", "soc", "also_invalid"],
        )
        assert len(compendium.participants) == 1
        assert "soc" in compendium.participants

    def test_debate_all_invalid_agents(self, worktable: Worktable) -> None:
        """Todos los agentes invalidos -> Compendium vacio."""
        compendium = worktable.debate(
            topic="Tema",
            agents=["fake1", "fake2"],
        )
        assert compendium.summary == ""
        assert compendium.participants == []


# ---------------------------------------------------------------------------
# Test: Completitud de perfiles de agente
# ---------------------------------------------------------------------------


class TestAgentProfilesCompleteness:
    """Todos los perfiles tienen campos requeridos."""

    REQUIRED_FIELDS = ["name", "abbr", "description", "bias", "questions"]

    def test_all_profiles_have_required_fields(self) -> None:
        """Cada perfil en AGENT_PROFILES tiene todos los campos requeridos."""
        for agent_name, profile in AGENT_PROFILES.items():
            for field in self.REQUIRED_FIELDS:
                assert field in profile, (
                    f"Agente '{agent_name}' no tiene campo '{field}'"
                )

    def test_all_profiles_have_non_empty_name(self) -> None:
        """Campo 'name' no vacio."""
        for agent_name, profile in AGENT_PROFILES.items():
            assert profile["name"] != "", (
                f"Agente '{agent_name}' tiene name vacio"
            )

    def test_all_profiles_have_non_empty_abbr(self) -> None:
        """Campo 'abbr' no vacio."""
        for agent_name, profile in AGENT_PROFILES.items():
            assert profile["abbr"] != "", (
                f"Agente '{agent_name}' tiene abbr vacio"
            )

    def test_all_profiles_have_non_empty_description(self) -> None:
        """Campo 'description' no vacio."""
        for agent_name, profile in AGENT_PROFILES.items():
            assert profile["description"] != "", (
                f"Agente '{agent_name}' tiene description vacio"
            )

    def test_all_profiles_have_bias(self) -> None:
        """Campo 'bias' presente y no vacio."""
        for agent_name, profile in AGENT_PROFILES.items():
            assert profile["bias"] != "", (
                f"Agente '{agent_name}' tiene bias vacio"
            )

    def test_all_profiles_have_questions_list(self) -> None:
        """Campo 'questions' es una lista no vacia."""
        for agent_name, profile in AGENT_PROFILES.items():
            assert isinstance(profile["questions"], list), (
                f"Agente '{agent_name}' questions no es lista"
            )
            assert len(profile["questions"]) > 0, (
                f"Agente '{agent_name}' tiene questions vacia"
            )

    def test_profile_keys_are_strings(self) -> None:
        """Todas las claves de AGENT_PROFILES son strings."""
        for agent_name in AGENT_PROFILES:
            assert isinstance(agent_name, str)

    def test_profile_count(self) -> None:
        """Numero esperado de perfiles (13)."""
        assert len(AGENT_PROFILES) == 13, (
            f"Se esperaban 13 perfiles, hay {len(AGENT_PROFILES)}"
        )

    def test_known_agents_present(self) -> None:
        """Agentes clave estan presentes."""
        known = {
            "soc", "coupling", "cohesion", "resilience",
            "scalability", "observability", "clean_code",
            "maintainability", "testability", "interoperability",
            "security", "devops", "tradeoffs",
        }
        assert set(AGENT_PROFILES.keys()) == known, (
            f"Diferencia: {set(AGENT_PROFILES.keys()) ^ known}"
        )


# ---------------------------------------------------------------------------
# Test: Log del debate
# ---------------------------------------------------------------------------


class TestGetLog:
    """Log del debate."""

    def test_log_initial_empty(self, worktable: Worktable) -> None:
        """Log inicial vacio."""
        assert worktable.get_log() == []

    def test_log_after_debate(self, worktable: Worktable) -> None:
        """Log tiene entradas tras debate."""
        compendium = worktable.debate(
            topic="API REST",
            agents=["soc", "coupling", "security"],
        )
        log = worktable.get_log()
        assert len(log) > 0

    def test_log_entry_structure(self, worktable: Worktable) -> None:
        """Cada entrada de log tiene round, agent, type, content."""
        compendium = worktable.debate(
            topic="Sistema de pagos",
            agents=["soc", "coupling"],
        )
        log = worktable.get_log()
        for entry in log:
            assert "round" in entry
            assert "agent" in entry
            assert "type" in entry
            assert "content" in entry
            assert isinstance(entry["round"], int)
            assert isinstance(entry["agent"], str)
            assert isinstance(entry["type"], str)
            assert isinstance(entry["content"], dict)

    def test_log_round_types(self, worktable: Worktable) -> None:
        """Log contiene los tipos de ronda esperados."""
        compendium = worktable.debate(
            topic="Microservicios vs monolitos",
            agents=["soc", "coupling", "cohesion"],
        )
        log = worktable.get_log()
        types = {entry["type"] for entry in log}
        assert "opening" in types
        assert "critique" in types
        assert "refinement" in types

    def test_log_round_numbers(self, worktable: Worktable) -> None:
        """Rondas en el log son 1, 2, 3."""
        compendium = worktable.debate(
            topic="Arquitectura limpia",
            agents=["soc", "coupling"],
        )
        log = worktable.get_log()
        rounds = {entry["round"] for entry in log}
        assert rounds == {1, 2, 3}

    def test_log_agent_coverage(self, worktable: Worktable) -> None:
        """Todos los agentes aparecen en el log."""
        selected = ["soc", "resilience", "observability"]
        compendium = worktable.debate(
            topic="Sistema de tracing",
            agents=selected,
        )
        log = worktable.get_log()
        logged_agents = {entry["agent"] for entry in log}
        for a in selected:
            assert a in logged_agents, f"Agente {a} no aparece en log"

    def test_log_content_opening(self, worktable: Worktable) -> None:
        """Entradas de tipo opening tienen content con stance y arguments."""
        log = worktable.get_log()
        if not log:
            compendium = worktable.debate(
                topic="Test",
                agents=["soc"],
            )
            log = worktable.get_log()
        opening_entries = [e for e in log if e["type"] == "opening"]
        if opening_entries:
            content = opening_entries[0]["content"]
            assert "stance" in content
            assert "arguments" in content

    def test_log_immutable(self, worktable: Worktable) -> None:
        """get_log devuelve una copia (no la referencia interna)."""
        compendium = worktable.debate(
            topic="Tema",
            agents=["soc"],
        )
        log1 = worktable.get_log()
        log1.append({"extra": "data"})
        log2 = worktable.get_log()
        assert len(log1) != len(log2)  # log1 fue modificado, log2 no


# ---------------------------------------------------------------------------
# Test: Debate completo con 3 rondas (default)
# ---------------------------------------------------------------------------


class TestDebate3Rounds:
    """Debate completo con 3 rondas (comportamiento por defecto)."""

    def test_debate_3_rounds_default(self, worktable: Worktable) -> None:
        """Debate sin especificar rounds usa 3 rondas."""
        compendium = worktable.debate(
            topic="Disenar API REST",
            agents=["soc", "coupling"],
        )
        assert compendium.rounds == 3

    def test_debate_3_rounds_explicit(self, worktable: Worktable) -> None:
        """Debate con rounds=3 explicitamente."""
        compendium = worktable.debate(
            topic="Disenar API REST",
            agents=["soc", "coupling"],
            rounds=3,
        )
        assert compendium.rounds == 3

    def test_debate_3_rounds_full_positions(self) -> None:
        """Posiciones completas tras 3 rondas: arguments, concerns, vote."""
        wt = Worktable()
        compendium = wt.debate(
            topic="Arquitectura de software",
            agents=["soc", "coupling", "cohesion"],
            rounds=3,
        )
        positions = wt.get_positions()
        for agent_name, pos in positions.items():
            assert len(pos.arguments) > 0, f"{agent_name} sin arguments"
            assert len(pos.concerns) > 0, f"{agent_name} sin concerns"
            assert pos.vote != "abstencion", f"{agent_name} sin voto"

    def test_debate_3_rounds_log_complete(self, worktable: Worktable) -> None:
        """Log completo con opening, critique y refinement."""
        compendium = worktable.debate(
            topic="CQRS + Event Sourcing",
            agents=["soc", "cohesion", "scalability"],
            rounds=3,
        )
        log = worktable.get_log()
        types_by_round = {}
        for entry in log:
            types_by_round.setdefault(entry["round"], set()).add(entry["type"])
        assert 1 in types_by_round  # opening
        assert 2 in types_by_round  # critique
        assert 3 in types_by_round  # refinement


# ---------------------------------------------------------------------------
# Test: Custom dispatch
# ---------------------------------------------------------------------------


class TestCustomDispatch:
    """Worktable con funcion de dispatch personalizada."""

    def test_custom_dispatch_all_aceptar(self, custom_dispatch: Any) -> None:
        """Dispatch personalizado que siempre vota 'aceptar'."""
        wt = Worktable(dispatch_fn=custom_dispatch)
        compendium = wt.debate(
            topic="API REST",
            agents=["soc", "coupling", "cohesion"],
        )
        # Nuestro custom_dispatch siempre vota "aceptar"
        for agent_name in ["soc", "coupling", "cohesion"]:
            pos = wt.get_positions()[agent_name]
            assert pos.vote == "aceptar"
        # Summary debe ser COMPENDIO APROBADO
        assert "APROBADO" in compendium.summary

    def test_custom_dispatch_overrides_mock(self) -> None:
        """dispatch_fn personalizado reemplaza al mock."""
        call_log: list = []

        def tracking_dispatch(
            agent: str,
            topic: str,
            round_type: DebateRound,
            profile: Dict[str, Any],
            **kwargs: Any,
        ) -> Dict[str, Any]:
            call_log.append((agent, round_type.value))
            return {
                "stance": "a favor",
                "arguments": [f"{agent}: argumento"],
                "concerns": [f"{agent}: preocupacion"],
                "vote": "aceptar",
            }

        wt = Worktable(dispatch_fn=tracking_dispatch)
        compendium = wt.debate(
            topic="Test",
            agents=["soc", "coupling"],
            rounds=2,
        )
        # Verificar que se llamo a nuestro dispatch
        assert len(call_log) > 0
        assert call_log[0][0] == "soc"
        assert call_log[0][1] == "opening"
        assert call_log[1][0] == "coupling"
        assert call_log[1][1] == "opening"


# ---------------------------------------------------------------------------
# Test: Edge cases adicionales
# ---------------------------------------------------------------------------


class TestEdgeCases:
    """Casos borde adicionales."""

    def test_debate_with_empty_topic(self, worktable: Worktable) -> None:
        """Topic vacio no debe romper el debate."""
        compendium = worktable.debate(
            topic="",
            agents=["soc", "coupling"],
        )
        assert isinstance(compendium, Compendium)
        assert compendium.participants == ["soc", "coupling"]

    def test_debate_with_very_long_topic(self, worktable: Worktable) -> None:
        """Topic muy largo se maneja sin errores."""
        long_topic = "Disenar " + "muy " * 100 + "larga"
        compendium = worktable.debate(
            topic=long_topic,
            agents=["soc"],
        )
        assert isinstance(compendium, Compendium)
        assert len(compendium.participants) == 1

    def test_multiple_debates_independent(self) -> None:
        """Debates multiples no contaminan estados."""
        wt = Worktable()
        comp1 = wt.debate("Tema A", agents=["soc"])
        log1 = wt.get_log()
        comp2 = wt.debate("Tema B", agents=["coupling"])
        log2 = wt.get_log()
        # Cada debate tiene su propio log
        assert len(log1) > 0
        assert len(log2) > 0
        # El segundo debate reseteo el estado
        assert len(wt.get_positions()) == 1
        assert "coupling" in wt.get_positions()

    def test_agent_position_dataclass(self) -> None:
        """AgentPosition creado con valores por defecto."""
        pos = AgentPosition(agent_name="test_agent")
        assert pos.agent_name == "test_agent"
        assert pos.stance == "neutral"
        assert pos.arguments == []
        assert pos.concerns == []
        assert pos.vote == "abstencion"
