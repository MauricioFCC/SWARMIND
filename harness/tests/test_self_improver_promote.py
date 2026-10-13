"""Tests TDD de ``SelfImprover.promote_best_snapshot`` (persistencia idempotente).

Contrato RED→GREEN del cierre determinista del give-loop de evolve:

  (d) ``promote_best_snapshot`` PERSISTE el mejor snapshot: el registro de
      promocion queda verificable en el cognition store temporal.
  (e) es IDEMPOTENTE: promover 2x deja el mismo estado (sin duplicados).
  (f) oracle de MUTACION: el id determinista del registro y sus metricos
      (``snapshot_id``, ``best_score``) coinciden exactamente -> mata mutantes de
      la logica de persistencia (id, metricos, tags).

Aislamiento: ``MockVectorStore`` en memoria (sin LanceDB); NUNCA se toca el
store real.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from harness.evolve_loop.cognition_sync import CognitionLesson, CognitionSync
from harness.evolve_loop.evaluator import CASEEvaluator
from harness.evolve_loop.self_improver import SelfImprover
from harness.tests.mock_vector_store import MockVectorStore

_SKILL = "promote-skill"
_COLLECTION = "asi_cognition_store"
_PROMOTION_TITLE = f"Snapshot promoted: {_SKILL}"


@pytest.fixture
def store() -> MockVectorStore:
    """MockVectorStore con la coleccion de cognition pre-creada."""
    vector_store = MockVectorStore()
    vector_store.create_collection(_COLLECTION)
    return vector_store


@pytest.fixture
def improver(store: MockVectorStore) -> SelfImprover:
    """SelfImprover con cognition sobre el store temporal."""
    return SelfImprover(
        evaluator=CASEEvaluator(), cognition=CognitionSync(vector_store=store)
    )


def _item_count(store: MockVectorStore) -> int:
    """Cuenta los items persistidos en la coleccion de cognition.

    Args:
        store: MockVectorStore usado por el ``CognitionSync``.

    Returns:
        Numero de items almacenados (privado del mock, solo para verificar).
    """
    return len(store._collections[_COLLECTION].items)


def _promotion_lessons(improver: SelfImprover) -> list[CognitionLesson]:
    """Recupera los registros de promocion persistidos.

    Args:
        improver: Instancia bajo prueba.

    Returns:
        Lista de lecciones cuyo titulo es el de promocion de ``_SKILL``.
    """
    return [
        lesson
        for lesson in improver.cognition.search_lessons("promoted", top_k=200)
        if lesson.title == _PROMOTION_TITLE
    ]


class TestPromotePersists:
    """(d) La promocion se persiste en el cognition store."""

    def test_promote_persiste_snapshot(self, improver: SelfImprover) -> None:
        """Tras una ronda, promover persiste 1 registro con el snapshot y score."""
        improver.run_round(_SKILL, rounds=1)

        snapshot_id = improver.promote_best_snapshot(_SKILL)

        assert snapshot_id is not None
        lessons = _promotion_lessons(improver)
        assert len(lessons) == 1
        assert lessons[0].metrics["snapshot_id"] == snapshot_id
        assert lessons[0].metrics["best_score"] == improver._best_scores[_SKILL]
        assert lessons[0].domain == "self_improvement.promotions"
        assert improver.has_been_promoted(_SKILL) is True

    def test_promote_sin_snapshot_devuelve_none(
        self, improver: SelfImprover
    ) -> None:
        """Sin rondas previas no hay snapshot: retorna None."""
        assert improver.promote_best_snapshot("nunca-corrio") is None


class TestPromoteIdempotent:
    """(e) Promover 2x no duplica el registro."""

    def test_promote_idempotente(
        self, improver: SelfImprover, store: MockVectorStore
    ) -> None:
        """Dos promociones dejan el mismo estado (mismo id, mismo conteo)."""
        improver.run_round(_SKILL, rounds=1)

        first = improver.promote_best_snapshot(_SKILL)
        count_after_first = _item_count(store)
        second = improver.promote_best_snapshot(_SKILL)
        count_after_second = _item_count(store)

        assert first == second
        assert count_after_first == count_after_second
        assert len(_promotion_lessons(improver)) == 1


class TestPromoteMutationOracle:
    """(f) Oracle de mutacion: valores exactos de la persistencia."""

    def test_promote_oraculo_mutacion(self, improver: SelfImprover) -> None:
        """El id determinista, metricos y tags coinciden exactamente."""
        improver.run_round(_SKILL, rounds=2)

        snapshot_id = improver.promote_best_snapshot(_SKILL)
        expected_id = f"promote_{_SKILL}_{snapshot_id}"

        lessons = _promotion_lessons(improver)
        assert len(lessons) == 1
        lesson = lessons[0]
        assert lesson.id == expected_id
        assert improver.cognition.has_lesson(expected_id) is True
        assert lesson.metrics == {
            "best_score": improver._best_scores[_SKILL],
            "snapshot_id": snapshot_id,
        }
        assert set(lesson.tags) == {"promotion", _SKILL, "snapshot"}


class TestPromoteBestEffort:
    """La persistencia es best-effort: un store caido no rompe el loop."""

    def test_promote_best_effort_store_falla(self) -> None:
        """Si ``add_lesson`` lanza, se loguea y se devuelve el snapshot."""
        cognition = MagicMock()
        cognition.has_lesson.return_value = False
        cognition.add_lesson.side_effect = RuntimeError("store caido")
        improver = SelfImprover(evaluator=CASEEvaluator(), cognition=cognition)
        improver._current_snapshots[_SKILL] = "snap_x"
        improver._best_scores[_SKILL] = 0.9

        result = improver.promote_best_snapshot(_SKILL)

        assert result == "snap_x"
        assert improver.has_been_promoted(_SKILL) is True
