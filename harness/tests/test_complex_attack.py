"""Contrato del loop de ataque a problemas complejos (ciclo 11.17 - Nexus).

WHAT: verifica ``harness/complex_problems/attack.py`` contra la frontera:

- **AlphaProof Nexus** (arXiv 2605.22763): orquesta los 5 mecanismos —
  escalera de presupuesto + verificador inyectado + anti-malformalizacion +
  ledger monotono + poblacion Elo — en un loop determinista: cada intento
  consume budget, el candidato pasa por integridad del statement y verificacion
  formal; si verifica, el problema queda resuelto para siempre (idempotente).

WHY: los mecanismos aislados no dan el sistema; el loop es el contrato
integrador (DI completa: verifier/hook/ledger inyectados, sin rng).

WHERE: ``harness/complex_problems/attack.py``.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest

from harness.complex_problems.attack import AttackLoop, AttackReport, AttemptRecord
from harness.complex_problems.budget import BudgetLadder
from harness.complex_problems.progress import ProgressLedger
from harness.complex_problems.verifier import VerificationResult, Verifier


class _ScriptedVerifier:
    """Verificador que verifica exactamente el candidato ``ok_for``."""

    def __init__(self, ok_for: str) -> None:
        self._ok_for = ok_for

    def verify(self, candidate: str) -> VerificationResult:
        return VerificationResult(verified=candidate == self._ok_for, trace=(candidate,))


class _NeverVerifier:
    """Verificador que nunca certifica (ataque fallido)."""

    def verify(self, candidate: str) -> VerificationResult:
        return VerificationResult(verified=False, trace=("sin prueba",))


def _loop(
    tmp_path: Path,
    *,
    hook: Callable[[int, str], str],
    verifier: Verifier,
    ledger: ProgressLedger | None = None,
    ladder: BudgetLadder | None = None,
    cost_per_attempt: int = 1,
    episode_cap: int = 100,
) -> AttackLoop:
    """Construye un AttackLoop con doubles puros (sin red ni disk)."""
    return AttackLoop(
        verifier=verifier,
        ledger=ledger or ProgressLedger(),
        candidate_hook=hook,
        ladder=ladder or BudgetLadder(rungs=(1, 2, 4)),
        cost_per_attempt=cost_per_attempt,
        episode_cap=episode_cap,
    )


class TestAttackLoop:
    """Contrato integrador (presupuesto x verificacion x monotonía)."""

    def test_resuelve_en_el_segundo_intento(self, tmp_path: Path) -> None:
        candidates = iter(("candidato-malo", "candidato-bueno"))
        loop = _loop(tmp_path, hook=lambda a, p: next(candidates), verifier=_ScriptedVerifier("candidato-bueno"))

        report = loop.attack("erdos-demo", "teorema demo", max_attempts=3)

        assert report.solved is True
        assert report.attempts == 2
        assert report.evidence == "candidato-bueno"
        assert [r.verified for r in report.history] == [False, True]
        assert [r.spent for r in report.history] == [1, 1], "costo por defecto: 1 episodio"
        assert report.history[0].granted == 1 and report.history[1].granted == 2

    def test_verificador_que_niega_todo_no_resuelve(self, tmp_path: Path) -> None:
        loop = _loop(tmp_path, hook=lambda a, p: f"c{a}", verifier=_NeverVerifier())

        report = loop.attack("p", "s", max_attempts=3)

        assert report.solved is False
        assert report.attempts == 3
        assert report.evidence is None
        assert all(r.verified is False for r in report.history)

    def test_reataque_de_problema_resuelto_es_idempotente(self, tmp_path: Path) -> None:
        ledger = ProgressLedger()
        loop = _loop(
            tmp_path,
            hook=lambda a, p: "ok",
            verifier=_ScriptedVerifier("ok"),
            ledger=ledger,
        )
        first = loop.attack("p", "s")

        second = loop.attack("p", "s")

        assert first.solved is True and first.attempts == 1
        assert second.solved is True
        assert second.attempts == 0, "ya resuelto: 0 episodios adicionales"
        assert second.spent == 0, "0 episodios gastados en re-ataque"
        assert second.history == ()
        assert second.evidence == "ok"

    def test_malformalizacion_bloquea_el_exito(self, tmp_path: Path) -> None:
        """Sin el marcador del problema real, verificar NO cuenta como resuelto."""
        loop = _loop(tmp_path, hook=lambda a, p: "ok", verifier=_ScriptedVerifier("ok"))

        report = loop.attack(
            "p",
            "teorema debilitado",
            required_markers=("teorema", "inexistente"),
            max_attempts=2,
        )

        assert report.solved is False
        assert all(r.verified is False for r in report.history)

    def test_presupuesto_agotado_corta_el_loop(self, tmp_path: Path) -> None:
        loop = _loop(
            tmp_path,
            hook=lambda a, p: f"c{a}",
            verifier=_NeverVerifier(),
            ladder=BudgetLadder(rungs=(1,)),
            episode_cap=1,
        )

        report = loop.attack("p", "s", max_attempts=5)

        assert report.attempts == 1, "episodios agotados: corta antes de max_attempts"
        assert report.spent == 1

    def test_tope_global_de_episodios_respeta_el_cap(self, tmp_path: Path) -> None:
        loop = _loop(
            tmp_path,
            hook=lambda a, p: f"c{a}",
            verifier=_NeverVerifier(),
            ladder=BudgetLadder(rungs=(5,)),
            cost_per_attempt=3,
            episode_cap=2,
        )

        report = loop.attack("p", "s", max_attempts=4)

        assert report.spent == 2, "el grant se acota al remanente del cap"
        assert report.attempts == 1

    def test_determinismo_del_reporte(self, tmp_path: Path) -> None:
        def run() -> AttackReport:
            loop = _loop(tmp_path, hook=lambda a, p: f"c{a}", verifier=_NeverVerifier())
            return loop.attack("p", "s", max_attempts=3)

        assert run() == run()

    def test_id_vacio_se_rechaza(self, tmp_path: Path) -> None:
        loop = _loop(tmp_path, hook=lambda a, p: "c", verifier=_NeverVerifier())

        with pytest.raises(ValueError, match="vacio"):
            loop.attack("", "s")

    def test_max_attempts_invalido_se_rechaza(self, tmp_path: Path) -> None:
        loop = _loop(tmp_path, hook=lambda a, p: "c", verifier=_NeverVerifier())

        with pytest.raises(ValueError, match="max_attempts"):
            loop.attack("p", "s", max_attempts=0)

    def test_cost_per_attempt_invalido_se_rechaza(self) -> None:
        with pytest.raises(ValueError, match="cost_per_attempt"):
            AttackLoop(
                verifier=_NeverVerifier(),
                ledger=ProgressLedger(),
                candidate_hook=lambda a, p: "c",
                ladder=BudgetLadder(rungs=(1,)),
                cost_per_attempt=0,
            )

    def test_default_de_costo_es_un_episodio_por_intento(self) -> None:
        """El default de cost_per_attempt (1) se ejercita sin pasarlo (sin costo explicito)."""
        loop = AttackLoop(
            verifier=_NeverVerifier(),
            ledger=ProgressLedger(),
            candidate_hook=lambda a, p: "c",
            ladder=BudgetLadder(rungs=(3,)),
            episode_cap=10,
        )

        report = loop.attack("p", "s", max_attempts=1)

        assert report.history[0].spent == 1, "default: 1 episodio por intento"


class TestFachada:
    """Tipos del dominio: Reporte frozen + stores accesibles por DI."""

    def test_reporte_es_inmutable(self) -> None:
        from dataclasses import FrozenInstanceError

        report = AttackReport(
            problem_id="p",
            solved=False,
            attempts=0,
            spent=0,
            evidence=None,
            history=(),
        )

        with pytest.raises(FrozenInstanceError):
            report.solved = True  # type: ignore[misc]

    def test_attempt_record_frozen(self) -> None:
        from dataclasses import FrozenInstanceError

        record = AttemptRecord(attempt=0, granted=1, spent=1, verified=False)

        with pytest.raises(FrozenInstanceError):
            record.spent = 2  # type: ignore[misc]
