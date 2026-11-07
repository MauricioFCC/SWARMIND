"""Guardrails de coste: el presupuesto se resuelve del SSOT, no se "pierde".

WHAT: sin `cost_budget`/`token_budget` explicito, `check_cost_budget` debe usar
`defaults.base_budget` de `.opencode/config/token_budgets.yaml` (INFO) en vez de
avisar "No se definio presupuesto". `check_cost_usage` compara cada metrica con
su eje (USD vs tokens) para no mezclar unidades.

WHY: el aviso de "sin presupuesto" aparecia en cada turno del agente aunque el
proyecto SI declara un presupuesto por defecto; y un limite de tokens se
comparaba contra el coste en USD.

WHERE: `harness/tests` — verifica `.opencode/core/guardrails_checks.py`.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(1, str(ROOT / ".opencode"))

import core.guardrails_checks as gc


@pytest.fixture
def ssot(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Apunta el guardrail a un token_budgets.yaml temporal con base_budget."""
    path = tmp_path / "token_budgets.yaml"
    path.write_text("defaults:\n  base_budget: 2048\n", encoding="utf-8")
    monkeypatch.setattr(gc, "_CONFIG_PATH", path)
    return path


def test_sin_budget_explicito_usa_el_default_del_ssot(ssot: Path) -> None:
    """Sin cost_budget, el resultado es INFO con el base_budget del proyecto."""
    result = gc.check_cost_budget({})
    assert result.passed is True
    assert result.severity is gc.GuardrailSeverity.INFO
    assert "2048" in result.message
    assert "No se definio" not in result.message


def test_sin_ssot_sigue_avisando(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Si no hay SSOT ni budget explicito, se mantiene el WARN honesto."""
    monkeypatch.setattr(gc, "_CONFIG_PATH", tmp_path / "missing.yaml")
    result = gc.check_cost_budget({})
    assert result.passed is False
    assert result.severity is gc.GuardrailSeverity.WARN


def test_budget_explicito_tiene_prioridad(ssot: Path) -> None:
    """Un token_budget explicito gana sobre el default del SSOT."""
    result = gc.check_cost_budget({"token_budget": 100})
    assert result.passed is True
    assert "100" in result.message


def test_uso_de_tokens_excede_el_default(ssot: Path) -> None:
    """token_usage > base_budget -> WARN (no se salta la verificacion)."""
    result = gc.check_cost_usage("token_usage: 3000", {})
    assert result.passed is False
    assert result.severity is gc.GuardrailSeverity.WARN


def test_uso_de_tokens_dentro_del_default(ssot: Path) -> None:
    """token_usage <= base_budget -> INFO dentro de presupuesto."""
    result = gc.check_cost_usage("token_usage: 100", {})
    assert result.passed is True
    assert "dentro de presupuesto" in result.message


def test_costo_no_se_compara_con_limite_de_tokens(ssot: Path) -> None:
    """max_tokens no limita el coste en USD (antes se mezclaban unidades)."""
    result = gc.check_cost_usage("cost: 5.0", {"token_budget": 10})
    assert result.passed is True


def test_costo_excede_limite_usd(ssot: Path) -> None:
    """max_cost_usd si limita el coste reportado."""
    result = gc.check_cost_usage("cost: 0.02", {"cost_budget": {"max_cost_usd": 0.01}})
    assert result.passed is False
    assert "excede presupuesto" in result.message
