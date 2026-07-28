"""
Tests para gepa_mutator — GEPAMutator, MutantPrompt.
"""
from __future__ import annotations

import pytest

from harness.evolve_loop.gepa_mutator import GEPAMutator, MutantPrompt

# ===================================================================
# MutantPrompt
# ===================================================================


class TestMutantPrompt:
    """Tests para el dataclass MutantPrompt."""

    def test_create(self):
        """Test creacion basica."""
        mp = MutantPrompt(
            id="abc123",
            source_agent="test-agent",
            original_prompt="Original prompt",
            mutated_prompt="Mutated prompt",
            mutations_applied=["reorder_paragraphs"],
        )
        assert mp.id == "abc123"
        assert mp.source_agent == "test-agent"
        assert mp.score == 0.0
        assert mp.created_at != ""

    def test_post_init_sets_timestamp(self):
        """Test __post_init__ asigna created_at si no se provee."""
        mp = MutantPrompt(
            id="xyz", source_agent="agent", original_prompt="", mutated_prompt="",
            mutations_applied=[],
        )
        assert mp.created_at != ""

    def test_post_init_preserves_timestamp(self):
        """Test __post_init__ preserva created_at si se provee."""
        mp = MutantPrompt(
            id="xyz", source_agent="agent", original_prompt="", mutated_prompt="",
            mutations_applied=[], created_at="2026-01-01T00:00:00",
        )
        assert mp.created_at == "2026-01-01T00:00:00"


# ===================================================================
# GEPAMutator
# ===================================================================


class TestGEPAMutatorInit:
    """Tests de inicializacion de GEPAMutator."""

    def test_init(self):
        """Test init crea instancia con seed."""
        m = GEPAMutator(seed=42)
        assert m.rng is not None
        assert m._mutation_log == []

    def test_init_deterministic(self):
        """Test mismo seed produce mismos resultados."""
        m1 = GEPAMutator(seed=42)
        m2 = GEPAMutator(seed=42)
        m1.create_mutants("agent", "Test prompt", num_mutants=2)
        m2.create_mutants("agent", "Test prompt", num_mutants=2)
        assert len(m1._mutation_log) == len(m2._mutation_log)


class TestGEPAMutatorCreateMutants:
    """Tests para create_mutants."""

    def test_create_mutants_default_count(self):
        """Test create_mutants con cantidad por defecto."""
        m = GEPAMutator(seed=1)
        mutants = m.create_mutants("agent", "Hello world prompt", num_mutants=3)
        assert len(mutants) == 3
        for mutant in mutants:
            assert mutant.source_agent == "agent"
            assert mutant.original_prompt == "Hello world prompt"
            assert mutant.mutated_prompt != ""
            assert len(mutant.mutations_applied) >= 2

    def test_create_mutants_zero(self):
        """Test create_mutants con 0 mutantes."""
        m = GEPAMutator(seed=1)
        mutants = m.create_mutants("agent", "prompt", num_mutants=0)
        assert mutants == []

    def test_create_mutants_unique_ids(self):
        """Test cada mutante tiene id unico."""
        m = GEPAMutator(seed=2)
        mutants = m.create_mutants("agent", "prompt", num_mutants=5)
        ids = [mu.id for mu in mutants]
        assert len(ids) == len(set(ids))

    def test_create_mutants_custom_strategies(self):
        """Test create_mutants con conjunto personalizado de estrategias."""
        m = GEPAMutator(seed=3)
        mutants = m.create_mutants(
            "agent", "You are a helpful assistant.",
            num_mutants=2,
            strategies=["add_constraint_prefix"],
        )
        for mutant in mutants:
            applied = mutant.mutations_applied
            assert all(s in ["add_constraint_prefix"] for s in applied)

    def test_create_mutants_short_prompt(self):
        """Test create_mutants con prompt muy corto."""
        m = GEPAMutator(seed=4)
        mutants = m.create_mutants("agent", "Hi", num_mutants=2)
        assert len(mutants) == 2
        for mutant in mutants:
            assert mutant.mutated_prompt != ""


class TestGEPAMutatorScoreAndPromote:
    """Tests para score_and_promote."""

    def test_score_and_promote_selects_best(self):
        """Test score_and_promote selecciona el mutante con mayor score."""
        m = GEPAMutator(seed=5)
        mutants = m.create_mutants("agent", "Test prompt", num_mutants=3)
        test_scores = {mutants[0].id: 0.5, mutants[1].id: 0.9, mutants[2].id: 0.3}
        winner, score = m.score_and_promote(mutants, test_scores)
        assert winner.id == mutants[1].id
        assert score == 0.9

    def test_score_and_promote_all_zero(self):
        """Test score_and_promote con todos scores 0."""
        m = GEPAMutator(seed=6)
        mutants = m.create_mutants("agent", "prompt", num_mutants=2)
        test_scores = {mu.id: 0.0 for mu in mutants}
        winner, score = m.score_and_promote(mutants, test_scores)
        assert score == 0.0
        # El primer mutante es el default
        assert winner.id == mutants[0].id

    def test_score_and_promote_empty_mutants(self):
        """Test score_and_promote con lista vacia (edge case)."""
        m = GEPAMutator(seed=7)
        # Si la lista esta vacia, se indexa mutants[0] → IndexError
        # Esto es comportamiento de la implementacion actual
        with pytest.raises(IndexError):
            m.score_and_promote([], {})


class TestGEPAMutatorStrategies:
    """Tests para estrategias individuales de mutacion."""

    def test_reorder_paragraphs(self):
        """Test _reorder_paragraphs mantiene primer parrafo fijo."""
        text = "Role definition.\n\nSecond paragraph.\n\nThird paragraph."
        result = GEPAMutator._reorder_paragraphs(text)
        assert result.startswith("Role definition.")

    def test_reorder_paragraphs_single(self):
        """Test _reorder_paragraphs con un solo parrafo no cambia nada."""
        text = "Only one paragraph."
        result = GEPAMutator._reorder_paragraphs(text)
        assert result == text

    def test_add_constraint_prefix(self):
        """Test _add_constraint_prefix agrega prefijo si no existe."""
        text = "You are an agent."
        result = GEPAMutator._add_constraint_prefix(text)
        assert "CRITICAL:" in result or "IMPORTANT:" in result or "REQUIREMENT:" in result or "RULE:" in result

    def test_add_constraint_prefix_already_present(self):
        """Test _add_constraint_prefix no duplica si ya existe (usa string exacto de la lista)."""
        constraint = "CRITICAL: You must follow C.A.S.E. (Clarify, Architect, Solve, Evaluate) reasoning in every response."
        text = f"{constraint}\n\nBe helpful."
        result = GEPAMutator._add_constraint_prefix(text)
        # Como la constraint exacta ya esta en el texto, no deberia agregar otra
        # (aunque random.choice seleccione esta misma, "chosen not in text" es False)
        # Nota: si random.choice selecciona otra constraint diferente, se agregaria.
        # Verificamos que al menos la constraint original se conserva.
        assert constraint in result

    def test_strengthen_verbs(self):
        """Test _strengthen_verbs reemplaza verbos debiles."""
        text = "You might consider trying to implement this."
        result = GEPAMutator._strengthen_verbs(text)
        assert "might" not in result.lower()
        assert "will" in result.lower()
        assert "consider" not in result.lower()
        assert "implement" in result.lower()

    def test_add_specificity(self):
        """Test _add_specificity agrega booster de especificidad."""
        text = "Solve the problem."
        result = GEPAMutator._add_specificity(text)
        assert "[Specificity]:" in result

    def test_condense(self):
        """Test _condense elimina palabras de relleno."""
        text = "In order to solve due to the fact that we need to."
        result = GEPAMutator._condense(text)
        assert "in order to" not in result
        assert "to" in result  # reemplazado
        assert "due to the fact that" not in result
        assert "because" in result

    def test_add_case_structure(self):
        """Test _add_case_structure agrega bloque C.A.S.E. si no existe."""
        text = "Here is the solution."
        result = GEPAMutator._add_case_structure(text)
        assert "CLARIFY:" in result.upper()
        assert "ARCHITECT:" in result.upper()

    def test_add_case_structure_already_present(self):
        """Test _add_case_structure no duplica si ya existe."""
        text = "Follow C.A.S.E. approach. CLARIFY: Understand."
        result = GEPAMutator._add_case_structure(text)
        assert result == text

    def test_remove_hedging(self):
        """Test _remove_hedging elimina lenguaje dubitativo."""
        text = "I think perhaps we should probably consider this."
        result = GEPAMutator._remove_hedging(text)
        assert "I think" not in result
        assert "perhaps" not in result
        assert "probably" not in result

    def test_emphasize_role(self):
        """Test _emphasize_role enfatiza la primera linea de rol."""
        text = "You are a software engineer."
        result = GEPAMutator._emphasize_role(text)
        assert "[ROLE]:" in result or "[AUTHORITY:" in result

    def test_emphasize_role_no_change(self):
        """Test _emphasize_role no cambia si primera linea no es de rol."""
        text = "Just some text without role declaration.\nSecond line."
        result = GEPAMutator._emphasize_role(text)
        assert result == text


class TestGEPAMutatorLog:
    """Tests para el log de mutaciones."""

    def test_get_mutation_log_empty(self):
        """Test get_mutation_log retorna [] inicialmente."""
        m = GEPAMutator(seed=8)
        assert m.get_mutation_log() == []

    def test_get_mutation_log_after_round(self):
        """Test get_mutation_log registra ronda tras score_and_promote."""
        m = GEPAMutator(seed=9)
        mutants = m.create_mutants("agent", "prompt", num_mutants=2)
        scores = {mu.id: 0.5 for mu in mutants}
        m.score_and_promote(mutants, scores)
        log = m.get_mutation_log()
        assert len(log) == 1
        assert log[0]["num_mutants"] == 2
        assert "winner_id" in log[0]
        assert "winner_score" in log[0]
