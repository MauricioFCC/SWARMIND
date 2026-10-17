"""Contrato del verificador formal inyectado (ciclo 11.17 - AlphaProof/AlphaEvolve).

WHAT: verifica ``harness/complex_problems/verifier.py`` contra la frontera:

- **AlphaProof** (Nature 2025-11): verificacion formal (Lean) como ground
  truth — el verificador es INYECTADO por DI, el loop nunca simula la prueba.
- **AlphaProof Nexus** (arXiv 2605.22763): test de lemmas anti-malformalizacion
  — antes de contar un problema como resuelto, el enunciado formal debe
  contener los marcadores requeridos del problema real (evita que el agente
  "resuelva" una version debilitada del statement).

WHY: sin verificador inyectado el loop auto-certifica sus propias
candidateS (epistemic closure); sin anti-malformalizacion, un LLM puede
reemplazar el teorema por algo trivial y reportar falso-éxito.

WHERE: ``harness/complex_problems/verifier.py``.
"""

from __future__ import annotations

import pytest

from harness.complex_problems.verifier import (
    VerificationResult,
    check_statement_integrity,
)


class _FakeVerifier:
    """Verifier de prueba que verifica segun su plantilla."""

    def __init__(self, ok_for: str) -> None:
        self._ok_for = ok_for

    def verify(self, candidate: str) -> VerificationResult:
        return VerificationResult(verified=candidate == self._ok_for, trace=(candidate,))


class TestVerificationResult:
    """Contrato del resultado (frozen, truthiness = verified)."""

    def test_bool_refleja_verified(self) -> None:
        assert bool(VerificationResult(verified=True)) is True
        assert bool(VerificationResult(verified=False)) is False

    def test_es_inmutable(self) -> None:
        from dataclasses import FrozenInstanceError

        result = VerificationResult(verified=True)

        with pytest.raises(FrozenInstanceError):
            result.verified = False  # type: ignore[misc]

    def test_trace_default_vacio(self) -> None:
        assert VerificationResult(verified=True).trace == ()


class TestVerifierProtocol:
    """El loop consume verificadores via Protocol (DI), no una clase concreta."""

    def test_protocol_acepta_implementacion_falsa(self) -> None:
        """Duck typing: basta con tener .verify(candidate) -> VerificationResult."""
        verifier: _FakeVerifier = _FakeVerifier("prueba")

        assert verifier.verify("prueba").verified is True
        assert verifier.verify("otra").verified is False


class TestAntiMalformalizacion:
    """Test de lemmas: marcadores faltantes del statement formal."""

    def test_marcadores_faltantes_se_reportan_en_orden(self) -> None:
        missing = check_statement_integrity(
            "theorem demo (n : Nat) : n + 0 = n := by", ["Nat", "commutative"]
        )

        assert missing == ("commutative",)

    def test_statement_vacio_falta_todo(self) -> None:
        assert check_statement_integrity("", ["a", "b"]) == ("a", "b")

    def test_todos_presentes_devuelve_vacio(self) -> None:
        statement = "lemma suma (a b : Nat) : a + b = b + a"
        assert check_statement_integrity(statement, ["suma", "Nat", "a + b"]) == ()

    def test_marcadores_duplicados_se_deduplican(self) -> None:
        missing = check_statement_integrity("x", ["a", "a", "b"])
        assert missing == ("a", "b")

    def test_sin_marcadores_requeridos_es_vacio(self) -> None:
        assert check_statement_integrity("cualquier cosa", []) == ()

    def test_marcador_vacio_se_rechaza(self) -> None:
        with pytest.raises(ValueError, match="vacio"):
            check_statement_integrity("x", ["ok", ""])
