"""Contrato de ejecucion durable con Resume Contract (spec frontera 11.15).

WHAT: verifica las propiedades del Resume Contract (arXiv 2608.03836,
"Resume Means Resume", 2026-08) sobre ``DurableRunStore``: los frameworks
deployados (LangGraph, CrewAI, pydantic-graph) las INCUMPLEN medidas. SWARMIND
las exige por contrato:

1. **Prefix continuation**: ``resume_plan`` re-ejecuta SOLO pasos ``PENDING``;
   los ``COMPLETED`` jamas se re-ejecutan.
2. **Effect exactly-once**: un efecto se RECLAMA (``claim_step``) ANTES de
   ejecutarse; un crash entre claim y complete deja el paso RUNNING y resume
   NO lo re-ejecuta silenciosamente: lo expone como ``indeterminate`` (puede
   haber disparado). Re-ejecutar a ciegas duplicaria efectos (pagos, mensajes).
3. **Consume-once**: el segundo claim de un paso/efecto devuelve False ANTES
   de ejecutar (un solo racer gana; el paper midio saturacion 1.0 en 36/40
   celdas cuando el gate no reclamaba en el store compartido).
4. **Recovery determinism**: el plan es funcion SOLO del estado durable (sin
   reloj, sin azar): mismo store -> mismo plan.
5. **Checkpoint validity**: un journal corrupto se rechaza con error legible
   (WHAT+WHY+WHERE); nunca se opera sobre estado invalido en silencio.

WHY: sin este contrato, un crash o doble respuesta HITL duplica efectos
no-idempotentes en el orquestador multi-agente.

WHERE: ``harness/orchestrator/durable_run.py``.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from harness.orchestrator.durable_run import DurableRunStore, StepStatus

_STEPS = ("fetch", "charge", "notify")


def _store(tmp_path: Path) -> DurableRunStore:
    """Store durable apuntando a un journal en ``tmp_path``."""
    return DurableRunStore(tmp_path / "journal.json")


class TestPrefixContinuation:
    """Resume re-ejecuta solo pasos PENDING (nunca los COMPLETED)."""

    def test_reexecuta_solo_incompletos(self, tmp_path: Path) -> None:
        store = _store(tmp_path)
        store.start_run("run-1", _STEPS)
        assert store.claim_step("run-1", "fetch") is True
        store.complete_step("run-1", "fetch", result={"ok": True})
        assert store.claim_step("run-1", "charge") is True
        store.complete_step("run-1", "charge")
        # crash aqui: notify sigue PENDING

        fresh = _store(tmp_path)  # nueva instancia = tras crash
        plan = fresh.resume_plan("run-1")

        assert plan.reexecute == ("notify",), "solo el paso pendiente se re-ejecuta"
        assert plan.completed == ("fetch", "charge")
        assert plan.indeterminate == ()

    def test_run_completo_no_reexecuta_nada(self, tmp_path: Path) -> None:
        store = _store(tmp_path)
        store.start_run("run-1", _STEPS)
        for step in _STEPS:
            assert store.claim_step("run-1", step)
            store.complete_step("run-1", step)

        plan = _store(tmp_path).resume_plan("run-1")

        assert plan.reexecute == ()
        assert plan.completed == _STEPS


class TestEffectExactlyOnce:
    """Crash entre claim y complete: el efecto NO se re-ejecuta a ciegas."""

    def test_crash_tras_claim_queda_indeterminate(self, tmp_path: Path) -> None:
        store = _store(tmp_path)
        store.start_run("run-1", ("charge",))
        assert store.claim_step("run-1", "charge") is True
        # crash ANTES de complete_step: el cobro PUDO haberse disparado.

        fresh = _store(tmp_path)
        plan = fresh.resume_plan("run-1")

        assert plan.indeterminate == ("charge",), (
            "un paso RUNNING tras crash es indeterminado: re-ejecutarlo a ciegas "
            "duplicaria el efecto (pago/mensaje)"
        )
        assert plan.reexecute == (), "nada indeterminado entra en re-ejecucion automatica"

    def test_complete_sin_claim_es_error_legible(self, tmp_path: Path) -> None:
        store = _store(tmp_path)
        store.start_run("run-1", ("charge",))

        with pytest.raises(ValueError, match="claim"):
            store.complete_step("run-1", "charge")


class TestConsumeOnce:
    """El segundo claim de un paso reclamado es rechazado ANTES de ejecutar."""

    def test_segundo_claim_devuelve_false(self, tmp_path: Path) -> None:
        store = _store(tmp_path)
        store.start_run("run-1", ("charge",))

        first = store.claim_step("run-1", "charge")
        second = store.claim_step("run-1", "charge")

        assert first is True and second is False, "un solo racer gana el claim"

    def test_claim_rechazado_sobrevive_a_reinicio(self, tmp_path: Path) -> None:
        store = _store(tmp_path)
        store.start_run("run-1", ("charge",))
        assert store.claim_step("run-1", "charge") is True

        fresh = _store(tmp_path)  # otro proceso que reabre el mismo store

        assert fresh.claim_step("run-1", "charge") is False, (
            "consume-once debe valer CROSS-PROCESS: el gate vive en el store "
            "durable, no en memoria"
        )

    def test_evento_hitl_consume_una_sola_respuesta(self, tmp_path: Path) -> None:
        store = _store(tmp_path)
        store.start_run("run-1", ("publish",))

        first = store.consume_event("run-1", "approval-1", answer="approve")
        second = store.consume_event("run-1", "approval-1", answer="reject")

        assert first is True, "la primera respuesta gana"
        assert second is False, "la segunda respuesta debe ser rechazada (conflicto)"
        assert store.event_answer("run-1", "approval-1") == "approve", (
            "la respuesta persistida es la del primer racer"
        )


class TestRecoveryDeterminism:
    """El plan es funcion solo del estado durable (misma entrada -> mismo plan)."""

    def test_mismo_estado_mismo_plan(self, tmp_path: Path) -> None:
        store = _store(tmp_path)
        store.start_run("run-1", _STEPS)
        store.claim_step("run-1", "fetch")

        plan_a = _store(tmp_path).resume_plan("run-1")
        plan_b = _store(tmp_path).resume_plan("run-1")

        assert plan_a == plan_b, "sin reloj ni azar: determinismo puro"
        assert plan_a.reexecute == ("charge", "notify")
        assert plan_a.indeterminate == ("fetch",)


class TestCheckpointValidity:
    """Un journal corrupto se rechaza con error legible (nunca en silencio)."""

    def test_journal_corrupto_explicita_what_where(self, tmp_path: Path) -> None:
        journal = tmp_path / "journal.json"
        journal.write_text("{no-es-json", encoding="utf-8")

        with pytest.raises(ValueError, match="journal"):
            DurableRunStore(journal)

    def test_journal_con_forma_invalida_es_type_error(self, tmp_path: Path) -> None:
        """JSON valido pero estructura equivocada: error tipado, no silencio."""
        journal = tmp_path / "journal.json"
        journal.write_text("[1, 2, 3]", encoding="utf-8")

        with pytest.raises(TypeError, match="journal"):
            DurableRunStore(journal)

    def test_run_desconocido_explicita_error(self, tmp_path: Path) -> None:
        store = _store(tmp_path)

        with pytest.raises(ValueError, match="run-1"):
            store.resume_plan("run-1")

    def test_run_duplicado_explicita_error(self, tmp_path: Path) -> None:
        store = _store(tmp_path)
        store.start_run("run-1", ("a",))

        with pytest.raises(ValueError, match="run-1"):
            store.start_run("run-1", ("b",))

    def test_estado_en_disco_es_json_valido(self, tmp_path: Path) -> None:
        store = _store(tmp_path)
        store.start_run("run-1", ("a",))

        data = json.loads((tmp_path / "journal.json").read_text(encoding="utf-8"))

        steps = data["runs"]["run-1"]["steps"]
        assert steps["a"]["status"] == StepStatus.PENDING.value
