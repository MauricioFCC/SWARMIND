"""Contrato del loop de mineria (spec frontera 11.16 — NVIDIA + AlphaMCTS + QuantaAlpha).

WHAT: verifica ``harness/alpha_mining/mining_loop.py`` contra la frontera:

- **NVIDIA signal/code/eval** (blog NeMo Agent Toolkit, 2026-05): bucle
  cerrado signal(hipotesis) -> code(AST) -> eval(IC/RankIC + umbrales) con
  feedback de sugerencias a la siguiente iteracion; init diversificado.
- **AlphaMCTS** (arXiv 2505.11122): busqueda MCTS-UCT sobre formulas donde
  el reward cuantitativo del backtest guia la seleccion; determinista dadas
  las hooks y el estado (sin azar); el seed se evalua en la raiz.
- **QuantaAlpha** (arXiv 2602.07085): trayectorias de mineria con mutacion
  (reescribe SOLO el segmento fallido via reflexion) y crossover (recombina
  segmentos complementarios de padres de alta recompensa).
- **AlphaAgent/Hubble**: gates de generacion — complejidad (nodos), FSA
  (motifs prohibidos), originalidad (similitud vs zoo) y alineacion
  hipotesis-factor (score LLM inyectado via DI).

WHY: el harness no tenia NINGUNA capacidad alpha (gap verificado por IDP);
estos 5 sistemas miden IC 0.03-0.05 con estos mecanismos y sus bases estan
medidas fallando sin ellos.

WHERE: ``harness/alpha_mining/mining_loop.py``.
"""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from pathlib import Path

import numpy as np
import pytest

from harness.alpha_mining.alpha_zoo import AlphaZoo, FactorFamily, ZooEntry
from harness.alpha_mining.factor_dsl import (
    Expr,
    Field,
    Operator,
    abstract_gene,
    to_dict,
)
from harness.alpha_mining.mining_loop import (
    ALIGNMENT_MIN,
    LoopConfig,
    MiningContext,
    MiningLoop,
    Role,
    Trajectory,
    TrajectoryStep,
    crossover,
    mutate,
)
from harness.tests.fixtures_alpha import make_panel

_CLOSE = Expr.leaf(Field.CLOSE)
_OPEN = Expr.leaf(Field.OPEN)


def _corr_panel() -> dict[Field, np.ndarray]:
    """Panel con señal plantada: forward = 0.1 * cs_rank(open) (IC=1 con open)."""
    t, n = 6, 4
    open_ = np.tile(np.arange(1.0, n + 1.0) + np.arange(t)[:, None], (1, 1))
    close = np.zeros((t, n))
    close[0] = 100.0
    for step in range(t - 1):
        rank = open_[step].argsort().argsort() / (n - 1)
        close[step + 1] = close[step] * (1.0 + 0.1 * rank)
    return {
        Field.OPEN: open_,
        Field.CLOSE: close,
        Field.HIGH: close.copy(),
        Field.LOW: close.copy(),
        Field.VOLUME: np.ones((t, n)),
        Field.RETURNS: np.zeros((t, n)),
    }


def _big_expr() -> Expr:
    """Expr con 35 nodos (> MAX_NODES=32): viola el gate de complejidad."""
    expr = _CLOSE
    for _ in range(17):
        expr = Expr.apply(Operator.ADD, expr, Expr.leaf(Field.VOLUME))
    return expr


def _loop(
    tmp_path: Path,
    *,
    construct_hook,
    signal_hook=None,
    alignment_hook=None,
    config: LoopConfig | None = None,
    panel: dict[Field, np.ndarray] | None = None,
) -> MiningLoop:
    """MiningLoop de prueba sobre panel determinista."""
    return MiningLoop(
        panel if panel is not None else make_panel(),
        AlphaZoo(tmp_path / "zoo.jsonl"),
        config or LoopConfig(),
        signal_hook=signal_hook or (lambda round_index, variant: f"hyp-{variant}"),
        construct_hook=construct_hook,
        alignment_hook=alignment_hook,
    )


class TestGatesDeGeneracion:
    """Pipeline NVIDIA con gates AlphaAgent/Hubble antes del eval."""

    def test_acepta_y_puebla_el_zoo(self, tmp_path: Path) -> None:
        loop = _loop(
            tmp_path,
            construct_hook=lambda ctx, bp: to_dict(_OPEN),
            panel=_corr_panel(),
        )

        report = loop.run_round(1, ["momentum"])

        assert len(report.accepted) == 1
        assert report.accepted[0].formula == "open"
        assert len(loop.zoo.entries) == 1

    def test_gate_complejidad(self, tmp_path: Path) -> None:
        loop = _loop(tmp_path, construct_hook=lambda ctx, bp: to_dict(_big_expr()))

        report = loop.run_round(1, ["complejo"])

        assert report.accepted == ()
        assert any("complejidad" in reason for _, reason in report.rejected)

    def test_gate_fsa(self, tmp_path: Path) -> None:
        expr = Expr.apply(Operator.TS_MEAN, _CLOSE, window=20)
        config = LoopConfig(forbidden_genes=frozenset({abstract_gene(expr)}))
        loop = _loop(
            tmp_path, construct_hook=lambda ctx, bp: to_dict(expr), config=config
        )

        report = loop.run_round(1, ["crowded"])

        assert any("fsa" in reason for _, reason in report.rejected)

    def test_gate_originalidad(self, tmp_path: Path) -> None:
        expr = Expr.apply(Operator.DIV, _CLOSE, Expr.leaf(Field.VOLUME))
        zoo = AlphaZoo(tmp_path / "zoo.jsonl")
        zoo.add(
            ZooEntry(
                formula="div(close, volume)",
                tree=to_dict(expr),
                family=FactorFamily.OTHER,
                score=0.5,
                rank_ic=0.05,
                round_index=0,
            )
        )
        loop = MiningLoop(
            make_panel(),
            zoo,
            LoopConfig(),
            signal_hook=lambda r, v: "h",
            construct_hook=lambda ctx, bp: to_dict(expr),
        )

        report = loop.run_round(1, ["renombrado"])

        assert any("originalidad" in reason for _, reason in report.rejected)

    def test_gate_alineacion(self, tmp_path: Path) -> None:
        expr = Expr.apply(Operator.RANK, _CLOSE)
        loop = _loop(
            tmp_path,
            construct_hook=lambda ctx, bp: to_dict(expr),
            alignment_hook=lambda hyp, formula: 0.1,
        )

        report = loop.run_round(1, ["sin_relation"])

        assert any("alineacion" in reason for _, reason in report.rejected)
        assert ALIGNMENT_MIN == 0.5

    def test_feedback_llega_al_siguiente_ctx(self, tmp_path: Path) -> None:
        constante = Expr.apply(Operator.DIV, _CLOSE, _CLOSE)
        seen: list[MiningContext] = []

        def hook(ctx: MiningContext, blueprint: str) -> dict:
            seen.append(ctx)
            return to_dict(constante)

        loop = _loop(tmp_path, construct_hook=hook)

        loop.run_round(1, ["primero", "segundo"])

        assert seen[0].feedback == (), "el primer ctx arranca limpio"
        assert seen[1].feedback, "el segundo ctx hereda el feedback del primero"
        assert any("rank_ic" in item for item in seen[1].feedback)

    def test_metricas_rechazadas_alimentan_kb(self, tmp_path: Path) -> None:
        constante = Expr.apply(Operator.DIV, _CLOSE, _CLOSE)
        loop = _loop(tmp_path, construct_hook=lambda ctx, bp: to_dict(constante))

        loop.run_round(1, ["ruido"])

        assert dict(loop.zoo.failure_modes()) == {"metricas": 1}


class TestInicializacionDiversificada:
    """QuantaAlpha: Diversified Planning Initialization."""

    def test_hook_de_senal_recibe_variantes_distintas(self, tmp_path: Path) -> None:
        calls: list[tuple[int, int]] = []
        expr = Expr.apply(Operator.RANK, _CLOSE)

        def signal(round_index: int, variant: int) -> str:
            calls.append((round_index, variant))
            return f"hipotesis-{variant}"

        loop = _loop(
            tmp_path,
            construct_hook=lambda ctx, bp: to_dict(expr),
            signal_hook=signal,
            config=LoopConfig(pool_size=3),
        )

        hypotheses = loop.diversified_init(round_index=2)

        assert hypotheses == ("hipotesis-0", "hipotesis-1", "hipotesis-2")
        assert calls == [(2, 0), (2, 1), (2, 2)], "variantes distintas, sin repeticion"


class TestMCTSSearch:
    """AlphaMCTS: UCT guiado por reward del backtest, determinista."""

    def _mcts_loop(self, tmp_path: Path) -> MiningLoop:
        def hook(ctx: MiningContext, blueprint: str) -> dict:
            window = 3 + len(blueprint) % 10
            return to_dict(Expr.apply(Operator.TS_MEAN, _CLOSE, window=window))

        return _loop(tmp_path, construct_hook=hook)

    def test_determinismo_puro(self, tmp_path: Path) -> None:
        loop = self._mcts_loop(tmp_path)
        seed = Expr.apply(Operator.RANK, _CLOSE)

        first = loop.search_mcts(seed, iterations=5)
        second = loop.search_mcts(seed, iterations=5)

        assert first == second, "mismo estado + mismas hooks => mismo resultado"

    def test_visitas_iguales_a_iteraciones(self, tmp_path: Path) -> None:
        loop = self._mcts_loop(tmp_path)

        result = loop.search_mcts(_CLOSE, iterations=6)

        assert result.visited == 6, "una expansion/evaluacion por iteracion"

    def test_seed_perfecta_logra_score_maximo(self, tmp_path: Path) -> None:
        loop = _loop(
            tmp_path,
            construct_hook=lambda ctx, bp: to_dict(
                Expr.apply(Operator.TS_MEAN, _CLOSE, window=4)
            ),
            panel=_corr_panel(),
        )

        result = loop.search_mcts(_OPEN, iterations=3)

        assert result.best_score == pytest.approx(1.0)
        assert "open" in result.accepted, "el seed IC=1 se evalua en la raiz y entra al zoo"

    def test_uct_desciende_al_hermano_de_mayor_recompensa(self, tmp_path: Path) -> None:
        """Con branching>=2 la raiz acumula hermanos y UCT desciende al mejor.

        Hook con estado: hijo1 = sign(close) (score 0), hijo2 = open (score 1).
        Iteracion 3: nodo raiz lleno -> UCT debe elegir el hermano aceptado
        (blueprint del 3er hook call = "open"), no al primero por defecto.
        """
        blueprints: list[str] = []
        variants = [
            to_dict(Expr.apply(Operator.SIGN, _CLOSE)),  # score 0 (constante)
            to_dict(_OPEN),  # score 1 (senal plantada)
            to_dict(_OPEN),
        ]

        def hook(ctx: MiningContext, blueprint: str) -> dict:
            blueprints.append(blueprint)
            return variants[min(len(blueprints) - 1, len(variants) - 1)]

        loop = _loop(tmp_path, construct_hook=hook, panel=_corr_panel())

        result = loop.search_mcts(_OPEN, iterations=3)

        assert result.best_score == pytest.approx(1.0)
        assert len(blueprints) == 3, "una expansion por iteracion"
        assert blueprints[2] == "open", (
            "UCT desciende al hermano de mayor recompensa (score 1), no al primero"
        )


class TestEvolucionDeTrayectorias:
    """QuantaAlpha: mutacion segment-local + crossover de segmentos."""

    def _traj(self, hypothesis: str, formula: str, reward: float) -> Trajectory:
        return Trajectory(
            hypothesis=hypothesis,
            formula=formula,
            steps=(
                TrajectoryStep(role=Role.SIGNAL, payload=hypothesis),
                TrajectoryStep(role=Role.CODE, payload=formula),
                TrajectoryStep(role=Role.EVAL, payload=f"ic={reward}"),
            ),
            reward=reward,
        )

    def test_mutate_reescribe_solo_el_segmento_fallido(self) -> None:
        traj = self._traj("h", "f", 0.1)

        new = mutate(traj, lambda step: step.payload + " v2")

        assert new.steps[:2] == traj.steps[:2], "los segmentos sanos se preservan"
        assert new.steps[2].payload == "ic=0.1 v2"
        assert new.steps[2].role is Role.EVAL, "el rol del segmento se conserva"

    def test_crossover_recombina_segmentos_de_ambos_padres(self) -> None:
        better = self._traj("hip-A", "formula-A", 0.9)
        worse = self._traj("hip-B", "formula-B", 0.1)

        child = crossover(better, worse)

        assert child.hypothesis == "hip-A", "hipotesis del padre de mayor recompensa"
        assert child.formula == "formula-B", "formula re combinada del otro padre"
        assert child.steps == better.steps[:-1] + worse.steps[-1:]

    def test_evolve_pool_determinista(self) -> None:
        pool = tuple(
            self._traj(f"h{i}", f"f{i}", reward)
            for i, reward in enumerate((0.9, 0.7, 0.3, 0.1))
        )

        offspring = MiningLoop.evolve_pool(pool, lambda step: step.payload + " v2")

        assert len(offspring) == 3, "2 crossovers por pares + 1 mutacion del peor"
        assert offspring[-1].steps[-1].payload.endswith("v2"), "el peor fue mutado"
        assert offspring[-1].hypothesis == "h3"

    def test_evolve_pool_prioriza_recompensa_sobre_nombre(self) -> None:
        """El orden evolutivo es por REWARD (QuantaAlpha fitness), no por nombre."""
        pool = tuple(
            self._traj(name, f"f-{name}", reward)
            for name, reward in (("h0", 0.1), ("h1", 0.9), ("h2", 0.7), ("h3", 0.3))
        )

        offspring = MiningLoop.evolve_pool(pool, lambda step: step.payload + " v2")

        assert len(offspring) == 3
        assert offspring[0].hypothesis == "h1"
        assert offspring[0].formula == "f-h2", "crossover: formula del peor del par"
        assert offspring[1].hypothesis == "h3"
        assert offspring[1].formula == "f-h0"
        assert offspring[-1].hypothesis == "h0", "el peor por RECOMPENSA (0.1) se muta"

    def test_trajectory_es_inmutable(self) -> None:
        traj = self._traj("h", "f", 0.5)

        with pytest.raises(FrozenInstanceError):
            traj.reward = 1.0  # type: ignore[misc]

    def test_mutate_sin_pasos_es_noop(self) -> None:
        traj = Trajectory(hypothesis="h", formula="f", steps=(), reward=0.0)

        assert mutate(traj, lambda step: "x") == traj
