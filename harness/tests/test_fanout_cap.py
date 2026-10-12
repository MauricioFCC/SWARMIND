"""Tests TDD para fan-out cap — MAX_FANOUT_DEFAULT=5 (FR-C3, ADR-0103/WS-C).

RED primero: el escalado XLarge (11) debe quedar capado a 5 por defecto y solo
abrirse con ``SWARMIND_MAX_FANOUT``. Evidencia (RSV/EDV): Ringelmann (2 diversos
>= 16 homogeneos) + capability ceiling >45% (arXiv:2512.08296).

Criterios:
  (a) default max = 5.
  (b) ``SWARMIND_MAX_FANOUT=8`` sobreescribe.
  (c) el decider nunca devuelve > max.
  (d) env invalido -> default sin lanzar.
"""

from __future__ import annotations

import pytest

from harness.orchestrator.difficulty_router import (
    ENV_MAX_FANOUT,
    MAX_FANOUT_DEFAULT,
    MAX_FANOUT_XLARGE,
    ComplexityLevel,
    DifficultyRouter,
    ScaleDecider,
    resolve_max_fanout,
)

# ===========================================================================
# (a) default
# ===========================================================================


class TestDefaultCap:
    """Sin env, el cap es 5 y XLarge queda contenido."""

    def test_default_constant_is_five(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """``MAX_FANOUT_DEFAULT`` vale 5."""
        monkeypatch.delenv(ENV_MAX_FANOUT, raising=False)
        assert MAX_FANOUT_DEFAULT == 5

    def test_decider_default_max(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """``ScaleDecider`` sin env usa el cap por defecto."""
        monkeypatch.delenv(ENV_MAX_FANOUT, raising=False)
        assert ScaleDecider().max_fanout == MAX_FANOUT_DEFAULT

    def test_xlarge_capped_by_default(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """VERY_COMPLEX (11 deseado) se capa a 5 por defecto."""
        monkeypatch.delenv(ENV_MAX_FANOUT, raising=False)
        assert ScaleDecider().decide(ComplexityLevel.VERY_COMPLEX) == MAX_FANOUT_DEFAULT


# ===========================================================================
# (b) env override
# ===========================================================================


class TestEnvOverride:
    """``SWARMIND_MAX_FANOUT`` sobreescribe el cap."""

    def test_env_overrides_to_eight(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """env=8 -> cap 8 y VERY_COMPLEX usa 8."""
        monkeypatch.setenv(ENV_MAX_FANOUT, "8")
        decider = ScaleDecider()
        assert decider.max_fanout == 8
        assert decider.decide(ComplexityLevel.VERY_COMPLEX) == 8

    def test_env_allows_xlarge(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """env=11 abre el escalado XLarge completo."""
        monkeypatch.setenv(ENV_MAX_FANOUT, str(MAX_FANOUT_XLARGE))
        assert ScaleDecider().decide(ComplexityLevel.VERY_COMPLEX) == MAX_FANOUT_XLARGE

    def test_explicit_max_fanout_overrides_env(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Un cap explicito gana al env (DI)."""
        monkeypatch.setenv(ENV_MAX_FANOUT, "9")
        assert ScaleDecider(max_fanout=3).max_fanout == 3

    def test_route_decide_scale_respects_cap(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """``DifficultyRouter.decide_scale`` nunca supera el cap."""
        monkeypatch.delenv(ENV_MAX_FANOUT, raising=False)
        agents = DifficultyRouter().decide_scale(
            "implementar arquitectura distribuida con microservicios "
            "docker kubernetes ci/cd trading seguridad datos"
        )
        assert 1 <= agents <= MAX_FANOUT_DEFAULT


# ===========================================================================
# (c) nunca excede el max
# ===========================================================================


class TestNeverExceeds:
    """El decider jamas devuelve mas agentes que el cap."""

    @pytest.mark.parametrize("env", ["1", "5", "8", "11", "50"])
    @pytest.mark.parametrize("level", list(ComplexityLevel))
    def test_decide_bounded(
        self, monkeypatch: pytest.MonkeyPatch, env: str, level: ComplexityLevel
    ) -> None:
        """decide(level) <= min(env, cap)."""
        monkeypatch.setenv(ENV_MAX_FANOUT, env)
        decider = ScaleDecider()
        assert decider.decide(level) <= decider.max_fanout
        assert decider.decide(level) <= int(env)

    def test_decide_at_least_one(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Todo nivel pide al menos 1 agente (incluso TRIVIAL)."""
        monkeypatch.delenv(ENV_MAX_FANOUT, raising=False)
        decider = ScaleDecider()
        assert decider.decide(ComplexityLevel.TRIVIAL) >= 1


# ===========================================================================
# (d) env invalido
# ===========================================================================


class TestInvalidEnv:
    """Env malformado degrada al default sin lanzar."""

    @pytest.mark.parametrize("value", ["abc", "", "   ", "-3", "0", "5.5", "NaN"])
    def test_invalid_env_falls_back(
        self, monkeypatch: pytest.MonkeyPatch, value: str
    ) -> None:
        """Valor no-entero o < 1 -> cap por defecto."""
        monkeypatch.setenv(ENV_MAX_FANOUT, value)
        assert ScaleDecider().max_fanout == MAX_FANOUT_DEFAULT

    def test_resolve_max_fanout_never_raises(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """``resolve_max_fanout`` no lanza ante env invalido."""
        monkeypatch.setenv(ENV_MAX_FANOUT, "abc")
        assert resolve_max_fanout() == MAX_FANOUT_DEFAULT
