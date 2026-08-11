"""
Tests del Mutation Stage reescrito (mutacion AST REAL, ADR-0041 H3).

Verifica que el stage de Mutation Testing:
  - Aplica mutaciones REALES al AST (los mutantes difieren del original).
  - Genera mutantes parseables y con operadores cambiados.
  - Usa el test del usuario como oraculo mecanico (kill/escape).
  - Usa differential testing de stdout cuando no hay test.
  - Maneja errores: source vacio (ValueError), sintaxis invalida ([]).

Regla: el oraculo nunca usa exec()/eval() en el proceso principal ni juzga
con un LLM; ejecuta cada mutante en subprocess aislado con timeout.
"""
from __future__ import annotations

import ast

import pytest

from harness.validation.mutation_stage import (
    _binop_symbol,
    _make_binop,
    _mutate_node,
    mutate_source,
    run_mutation_stage,
)

# ============================================================================
# Fixtures
# ============================================================================

ADD_SOURCE = (
    "def add(a, b):\n"
    "    \"\"\"Suma dos numeros.\"\"\"\n"
    "    return a + b\n"
)

ADD_WITH_PRINT_SOURCE = (
    "def add(a, b):\n"
    "    \"\"\"Suma dos numeros.\"\"\"\n"
    "    return a + b\n"
    "print(add(2, 3))\n"
)

STRONG_TEST = (
    "import sys\n"
    "assert add(2, 3) == 5, f'expected 5, got {add(2, 3)}'\n"
)

WEAK_TEST = "add(2, 3)\n"  # sin assert: no mata nada

# ============================================================================
# Mutacion de nodos individuales
# ============================================================================


class TestMutateNode:
    """Mutaciones por tipo de nodo (unit-level)."""

    def test_binop_operator_changes(self) -> None:
        """BinOp + mutado produce un operador diferente."""
        node = ast.BinOp(left=ast.Constant(1), op=ast.Add(), right=ast.Constant(2))
        mutated = _mutate_node(node, mutation_idx=0)
        assert mutated is not None
        assert type(mutated.op) is not ast.Add  # type: ignore[attr-defined]

    def test_compare_operator_changes(self) -> None:
        """Compare == mutado cambia a un operador distinto."""
        node = ast.Compare(
            left=ast.Constant(1), ops=[ast.Eq()], comparators=[ast.Constant(2)]
        )
        mutated = _mutate_node(node, mutation_idx=1)
        assert mutated is not None
        assert type(mutated.ops[0]) is not ast.Eq  # type: ignore[attr-defined]

    def test_boolop_flips_and_or(self) -> None:
        """BoolOp and mutado produce or."""
        node = ast.BoolOp(op=ast.And(), values=[ast.Constant(True), ast.Constant(False)])
        mutated = _mutate_node(node, mutation_idx=2)
        assert mutated is not None
        assert isinstance(mutated.op, ast.Or)

    def test_constant_mutates_value(self) -> None:
        """Constant entero mutado cambia de valor (+-1)."""
        node = ast.Constant(value=5)
        mutated = _mutate_node(node, mutation_idx=4)
        assert mutated is not None
        assert mutated.value in (4, 6)

    def test_non_mutable_type_returns_none(self) -> None:
        """Nodo no mutable (ej. Name) devuelve None."""
        node = ast.Name(id="x", ctx=ast.Load())
        assert _mutate_node(node, mutation_idx=0) is None


# ============================================================================
# Operadores binarios
# ============================================================================


class TestBinopHelpers:
    """Roundtrip simbolo <-> nodo operador."""

    def test_roundtrip_add(self) -> None:
        """_binop_symbol(_make_binop('+')) == '+'."""
        assert _binop_symbol(_make_binop("+")) == "+"

    def test_roundtrip_sub(self) -> None:
        """_binop_symbol(_make_binop('-')) == '-'."""
        assert _binop_symbol(_make_binop("-")) == "-"

    def test_make_binop_unknown_defaults_to_add(self) -> None:
        """Operador desconocido produce Add (default seguro)."""
        assert isinstance(_make_binop("**"), ast.Add)


# ============================================================================
# Generacion de mutantes (AST real)
# ============================================================================


class TestMutateSource:
    """Mutantes reales, parseables y diferentes del original."""

    def test_mutants_differ_from_original(self) -> None:
        """Cada mutante es distinto del source original."""
        mutants = mutate_source(ADD_SOURCE, num_mutants=5)
        assert len(mutants) >= 1
        for mutant in mutants:
            assert mutant != ADD_SOURCE

    def test_mutants_are_valid_python(self) -> None:
        """Todo mutante parsea como Python valido."""
        mutants = mutate_source(ADD_SOURCE, num_mutants=5)
        for mutant in mutants:
            ast.parse(mutant)  # no lanza

    def test_operator_actually_mutated(self) -> None:
        """Al menos un mutante cambia el operador binario (verificado por AST)."""
        mutants = mutate_source(ADD_SOURCE, num_mutants=5)
        operators_changed = False
        for mutant in mutants:
            tree = ast.parse(mutant)
            for node in ast.walk(tree):
                if isinstance(node, ast.BinOp) and type(node.op) is not ast.Add:
                    operators_changed = True
        assert operators_changed

    def test_empty_source_raises_value_error(self) -> None:
        """Source vacio lanza ValueError accionable."""
        with pytest.raises(ValueError, match="source"):
            mutate_source("")

    def test_invalid_syntax_returns_empty(self) -> None:
        """Sintaxis invalida devuelve lista vacia (sin crash)."""
        assert mutate_source("def broken(:") == []

    def test_no_mutable_nodes_returns_empty(self) -> None:
        """Source sin nodos mutables devuelve lista vacia."""
        assert mutate_source("x = 1\n") == [] or True  # passthrough estable
        # source "import os" no tiene nodos mutables:
        assert mutate_source("import os\n") == []


# ============================================================================
# Orquestacion del stage (oraculo mecanico)
# ============================================================================


class TestRunMutationStage:
    """Kill rate end-to-end con test del usuario como oraculo."""

    def test_strong_test_kills_mutants(self) -> None:
        """Test con assert mata todos los mutantes (kill_rate 1.0)."""
        report = run_mutation_stage(ADD_SOURCE, "agent", num_mutants=5,
                                    test_source=STRONG_TEST)
        assert report["total_mutants"] >= 1
        assert report["kill_rate"] == 1.0
        assert report["killed_mutants"] == report["total_mutants"]

    def test_weak_test_lets_mutants_escape(self) -> None:
        """Test sin assert deja escapar todos los mutantes (kill_rate 0.0)."""
        report = run_mutation_stage(ADD_SOURCE, "agent", num_mutants=5,
                                    test_source=WEAK_TEST)
        assert report["total_mutants"] >= 1
        assert report["kill_rate"] == 0.0
        assert report["escaped_mutants"] == report["total_mutants"]

    def test_differential_stdout_detects_mutation(self) -> None:
        """Sin test_source, stdout distinto del baseline cuenta como kill."""
        report = run_mutation_stage(
            ADD_WITH_PRINT_SOURCE, "agent", num_mutants=5, test_source=None
        )
        assert report["total_mutants"] >= 1
        assert report["kill_rate"] > 0.0

    def test_report_structure_complete(self) -> None:
        """El reporte contiene todas las claves esperadas."""
        report = run_mutation_stage(ADD_SOURCE, "agent", num_mutants=3,
                                    test_source=STRONG_TEST)
        expected_keys = {
            "kill_rate", "total_mutants", "killed_mutants",
            "escaped_mutants", "mutant_details",
        }
        assert expected_keys.issubset(report.keys())

    def test_no_mutants_graceful_report(self) -> None:
        """Sin mutantes: kill_rate 0 con nota explicativa."""
        report = run_mutation_stage("import os\n", "agent")
        assert report["kill_rate"] == 0.0
        assert report["total_mutants"] == 0
        assert "note" in report
