"""Tests TDD de Library Drift (retiro por outcome de skill libraries).

Contrato (arXiv 2605.19576, receta verificada):
  (a) ``record_outcome`` marca retrieval + helpful/hurt en el tracker (spy).
  (b) ``evaluate`` con ``trials < N_min`` → ``protect`` (aunque net sea
      negativo): NO retiro temprano (evita el dano de ``N_min=20``).
  (c) ``trials >= N_min`` y ``net < -tau`` → ``retire``.
  (d) ``trials >= N_min`` y ``net >= -tau`` → ``keep``.
  (e) ``sweep`` retira el ``.md`` de un skill con 120 trials y net -0.5, pero
      PROTEGE uno con 20 trials y net -0.5 (bajo N_min).
  (f) cap activo: mas de ``max_active`` skills → ``cap_exceeded`` en report.
  (g) oraculo de mutacion: ``min_trials``/comparador mal mutados rompen 2
      asserts discriminantes.
  (h) ``DriftPolicy.from_env()`` lee ``SWARMIND_DRIFT_*``.

Aislamiento: ``path`` y ``skills_dir`` temporales; NUNCA se toca el JSONL real
en ``harness/db`` ni ``.opencode/skills/auto``.
"""

from __future__ import annotations

import logging
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from harness.evolve_loop.library_drift import (
    DriftPolicy,
    LibraryDriftManager,
)
from harness.evolve_loop.skill_utility import SkillUtilityTracker
from harness.orchestrator.agent_dispatcher import AgentDispatcher


def _make_tracker(tmp_path: Path) -> SkillUtilityTracker:
    """Crea un tracker aislado en disco.

    Args:
        tmp_path: Directorio temporal de pytest.

    Returns:
        Tracker apuntando a un JSONL y skills_dir temporales.
    """
    return SkillUtilityTracker(
        path=tmp_path / "skill_utility.jsonl",
        skills_dir=tmp_path / "auto",
    )


def _make_manager(
    tmp_path: Path, policy: DriftPolicy | None = None
) -> LibraryDriftManager:
    """Crea un manager aislado sobre un tracker temporal.

    Args:
        tmp_path: Directorio temporal de pytest.
        policy: Politica opcional (default ``DriftPolicy()``).

    Returns:
        Manager con tracker/policy inyectados.
    """
    return LibraryDriftManager(tracker=_make_tracker(tmp_path), policy=policy)


def _seed(
    tracker: SkillUtilityTracker,
    name: str,
    *,
    retrievals: int,
    hurts: int = 0,
    helpfuls: int = 0,
) -> None:
    """Siembra un skill con recuperaciones y outcomes controlados.

    Args:
        tracker: Tracker a poblar.
        name: Nombre del skill.
        retrievals: Numero de recuperaciones (trials).
        hurts: Veces marcado como danino.
        helpfuls: Veces marcado como beneficioso.
    """
    for _ in range(retrievals):
        tracker.mark_retrieval(name)
    for _ in range(hurts):
        tracker.mark_hurt(name)
    for _ in range(helpfuls):
        tracker.mark_helpful(name)


def _write_skill_md(tmp_path: Path, name: str) -> Path:
    """Crea el ``.md`` de un skill en el ``skills_dir`` temporal.

    Args:
        tmp_path: Directorio temporal de pytest.
        name: Nombre del skill.

    Returns:
        Ruta del ``.md`` creado.
    """
    skills_dir = tmp_path / "auto"
    skills_dir.mkdir(parents=True, exist_ok=True)
    skill_file = skills_dir / f"{name}.md"
    skill_file.write_text(f"# {name}\n", encoding="utf-8")
    return skill_file


class TestRecordOutcome:
    """(a) el consumidor cablea el outcome real en el tracker."""

    def test_success_marca_retrieval_y_helpful(self) -> None:
        """used=True + success=True → mark_retrieval y mark_helpful."""
        tracker = MagicMock(spec=SkillUtilityTracker)
        manager = LibraryDriftManager(tracker=tracker)

        manager.record_outcome("sk", success=True)

        tracker.mark_retrieval.assert_called_once_with("sk")
        tracker.mark_helpful.assert_called_once_with("sk")
        tracker.mark_hurt.assert_not_called()

    def test_failure_marca_retrieval_y_hurt(self) -> None:
        """used=True + success=False → mark_retrieval y mark_hurt."""
        tracker = MagicMock(spec=SkillUtilityTracker)
        manager = LibraryDriftManager(tracker=tracker)

        manager.record_outcome("sk", success=False)

        tracker.mark_retrieval.assert_called_once_with("sk")
        tracker.mark_hurt.assert_called_once_with("sk")
        tracker.mark_helpful.assert_not_called()

    def test_used_false_no_marca_retrieval(self) -> None:
        """used=False → no marca recuperacion, pero si el outcome."""
        tracker = MagicMock(spec=SkillUtilityTracker)
        manager = LibraryDriftManager(tracker=tracker)

        manager.record_outcome("sk", success=True, used=False)

        tracker.mark_retrieval.assert_not_called()
        tracker.mark_helpful.assert_called_once_with("sk")

    def test_oserror_es_best_effort(self, caplog: pytest.LogCaptureFixture) -> None:
        """Un OSError del tracker NO propaga y loguea WHAT+WHY+WHERE."""
        tracker = MagicMock(spec=SkillUtilityTracker)
        tracker.mark_retrieval.side_effect = OSError("disco lleno")
        manager = LibraryDriftManager(tracker=tracker)

        with caplog.at_level(logging.WARNING):
            manager.record_outcome("sk", success=True)

        assert any(
            "WHAT" in record.message and "WHERE" in record.message
            for record in caplog.records
        )


class TestEvaluate:
    """(b)(c)(d) regla de frontera de retiro."""

    def test_bajo_n_min_protege_aunque_net_sea_negativo(self, tmp_path: Path) -> None:
        """(b) trials < N_min → protect (NO retiro temprano)."""
        manager = _make_manager(tmp_path)
        _seed(manager._tracker, "temprano", retrievals=99, hurts=50)

        verdict = manager.evaluate("temprano")

        assert verdict.decision == "protect"
        assert verdict.trials == 99
        assert verdict.net_utility < 0.0

    def test_evidencia_suficiente_y_net_negativo_retira(self, tmp_path: Path) -> None:
        """(c) trials >= N_min y net < -tau → retire."""
        manager = _make_manager(tmp_path)
        _seed(manager._tracker, "danino", retrievals=120, hurts=60)

        verdict = manager.evaluate("danino")

        assert verdict.decision == "retire"
        assert verdict.trials == 120
        assert verdict.net_utility == pytest.approx(-0.5)

    def test_evidencia_suficiente_y_net_dentro_del_margen_conserva(
        self, tmp_path: Path
    ) -> None:
        """(d) trials >= N_min y net >= -tau → keep."""
        manager = _make_manager(tmp_path)
        _seed(manager._tracker, "bueno", retrievals=120, hurts=6)

        verdict = manager.evaluate("bueno")

        assert verdict.decision == "keep"
        assert verdict.trials == 120
        assert verdict.net_utility == pytest.approx(-0.05)


class TestSweep:
    """(e) retiro fisico solo por encima de N_min."""

    def test_sweep_retira_con_evidencia_y_protege_temprano(self, tmp_path: Path) -> None:
        """120 trials net -0.5 → pruned; 20 trials net -0.5 → protegida."""
        manager = _make_manager(tmp_path)
        _seed(manager._tracker, "danino", retrievals=120, hurts=60)
        _seed(manager._tracker, "temprano", retrievals=20, hurts=10)

        danino_md = _write_skill_md(tmp_path, "danino")
        temprano_md = _write_skill_md(tmp_path, "temprano")

        verdicts = manager.sweep()
        by_name = {verdict.name: verdict for verdict in verdicts}

        assert by_name["danino"].decision == "retire"
        assert by_name["temprano"].decision == "protect"
        assert not danino_md.exists()  # retirada fisica
        assert temprano_md.exists()  # protegida: no se toca
        assert manager.report()["retired"] == 1


class TestCapActivo:
    """(f) cap activo de skills."""

    def test_cap_excedido_en_report(self, tmp_path: Path) -> None:
        """> max_active skills → cap_exceeded = exceso en el reporte."""
        manager = _make_manager(tmp_path, policy=DriftPolicy(max_active=50))
        for index in range(55):
            _seed(manager._tracker, f"sk-{index:02d}", retrievals=1)

        summary = manager.report()

        assert summary["total"] == 55
        assert summary["cap_exceeded"] == 5
        assert summary["protected"] == 55

    def test_sweep_no_borra_por_cap(self, tmp_path: Path) -> None:
        """El cap manda a revision pero NO borra el ``.md`` del skill seed."""
        manager = _make_manager(tmp_path, policy=DriftPolicy(max_active=2))
        for index in range(4):
            _seed(manager._tracker, f"seed-{index}", retrievals=1)
            _write_skill_md(tmp_path, f"seed-{index}")

        manager.sweep()

        for index in range(4):
            assert (tmp_path / "auto" / f"seed-{index}.md").exists()


class TestMutationOracle:
    """(g) oraculos de mutacion: 2 asserts discriminantes."""

    def test_min_trials_y_comparador_son_discriminantes(self, tmp_path: Path) -> None:
        """Mutantes de ``min_trials`` y del comparador rompen el veredicto."""
        manager = _make_manager(tmp_path, policy=DriftPolicy(min_trials=100, tau=0.10))

        # --- Assert 1: frontera de trials (mutante ``<`` → ``<=`` o N_min=3) ---
        _seed(manager._tracker, "borde", retrievals=100, hurts=50)
        _seed(manager._tracker, "debajo", retrievals=99, hurts=50)
        # Si el comparador fuera ``<=``, "borde" (100) seria protect; si N_min
        # fuera 3, "debajo" (99) no seria protect.
        assert manager.evaluate("borde").decision == "retire"
        assert manager.evaluate("debajo").decision == "protect"

        # --- Assert 2: estrictez del comparador (mutante ``<`` → ``<=``) ------
        _seed(manager._tracker, "justo", retrievals=100, hurts=10)
        # net == -tau exacto: con ``<`` es keep; con ``<=`` seria retire.
        assert manager.evaluate("justo").net_utility == pytest.approx(-0.10)
        assert manager.evaluate("justo").decision == "keep"


class TestFromEnv:
    """(h) overrides por entorno."""

    def test_from_env_lee_variables(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """from_env lee SWARMIND_DRIFT_MIN_TRIALS/TAU/MAX_ACTIVE."""
        monkeypatch.setenv("SWARMIND_DRIFT_MIN_TRIALS", "7")
        monkeypatch.setenv("SWARMIND_DRIFT_TAU", "0.25")
        monkeypatch.setenv("SWARMIND_DRIFT_MAX_ACTIVE", "9")

        policy = DriftPolicy.from_env()

        assert policy.min_trials == 7
        assert policy.tau == pytest.approx(0.25)
        assert policy.max_active == 9

    def test_from_env_defaults_sin_variables(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Sin variables, from_env devuelve los defaults de frontera."""
        monkeypatch.delenv("SWARMIND_DRIFT_MIN_TRIALS", raising=False)
        monkeypatch.delenv("SWARMIND_DRIFT_TAU", raising=False)
        monkeypatch.delenv("SWARMIND_DRIFT_MAX_ACTIVE", raising=False)

        policy = DriftPolicy.from_env()

        assert policy.min_trials == 100
        assert policy.tau == pytest.approx(0.10)
        assert policy.max_active == 50


class TestDispatcherWiring:
    """El dispatcher cablea el outcome real al manager (DI opcional)."""

    def test_record_skill_outcome_delega_en_manager(self) -> None:
        """record_skill_outcome delega en el manager inyectado."""
        manager = MagicMock(spec=LibraryDriftManager)
        dispatcher = AgentDispatcher(drift_manager=manager)

        dispatcher.record_skill_outcome("sk", success=True)

        manager.record_outcome.assert_called_once_with("sk", success=True, used=True)

    def test_sin_manager_es_noop(self) -> None:
        """Sin drift_manager, record_skill_outcome no lanza (backward-compatible)."""
        dispatcher = AgentDispatcher()

        dispatcher.record_skill_outcome("sk", success=False)  # no debe lanzar
