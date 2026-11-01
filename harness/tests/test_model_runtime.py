"""Tests del SSOT escalera frugal (spec model-free-edits.md, N9 gratis>barata).

Adversarial: precedence de env, ids invalidos, mirror de agenda, routing off.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from harness.model_router import edit_runtime as er
from harness.model_router.edit_constants import (
    DEFAULT_EDITS_MODEL,
    RUNTIME_YAML_RELPATH,
    YAML_KEY_FREE,
    YAML_KEY_PAID,
)

_REPO = Path(er.ROOT)


class TestLadderOrder:
    """Gratis primero, de pago despues (N9)."""

    def test_default_ladder_free_first(self):
        """El primero es beam-free y el resto conserva el orden yaml."""
        ladder = er.resolve_edit_ladder()
        assert ladder.primary == DEFAULT_EDITS_MODEL
        assert ladder.candidates == (
            DEFAULT_EDITS_MODEL,
            "opencode/beam-free",
            "opencode-go/deepseek-v4.1-flash",
        )

    def test_ssot_yaml_has_free_and_paid_sections(self):
        """El SSOT real del repo declara free+paid (sin drift de agenda)."""
        text = (_REPO / RUNTIME_YAML_RELPATH).read_text(encoding="utf-8")
        ladder = yaml.safe_load(text)["frugal_ladder"]
        assert ladder[YAML_KEY_FREE][0] == DEFAULT_EDITS_MODEL
        assert ladder[YAML_KEY_PAID][0].endswith("deepseek-v4.1-flash")


class TestEnvOverride:
    """Env override del tier (N5) y pin del primary conservando el resto."""

    def test_env_id_pins_primary_and_keeps_others(self):
        """Un override de env queda primero y conserva la escalera."""
        ladder = er.resolve_edit_ladder(
            env={"SWARMIND_EDITS_MODEL": "opencode/beam-free"},
            yaml_path="missing.yaml",
        )
        assert ladder.primary == "opencode/beam-free"
        assert DEFAULT_EDITS_MODEL in ladder.candidates

    def test_invalid_env_id_is_ignored_not_error(self):
        """Un id invalido en env se ignora: la escalera por defecto aplica."""
        ladder = er.resolve_edit_ladder(
            env={"SWARMIND_EDITS_MODEL": "no-espacio x"},
            yaml_path="missing.yaml",
        )
        assert ladder.primary == DEFAULT_EDITS_MODEL

    def test_yaml_free_list_from_tmp_override(self, tmp_path):
        """El yaml SSOT provee la agenda; el fallback barato va detras."""
        target = tmp_path / "model_runtime.yaml"
        target.write_text(
            "defaults:\n  fallback_model: provider/paid-1\n"
            "frugal_ladder:\n  free:\n    - provider/free-1\n"
            "  paid:\n    - provider/paid-2\n",
            encoding="utf-8",
        )
        ladder = er.resolve_edit_ladder(yaml_path=str(target))
        assert ladder.primary == "provider/free-1"
        assert ladder.candidates == (
            "provider/free-1",
            "provider/paid-2",
            "provider/paid-1",
        )


class TestFrugalRouting:
    """Flag de routing frugal (env > yaml > default True = ahorro GANADO)."""

    def test_default_enabled(self):
        """Por defecto el routing esta activo (presentar el plan frugal)."""
        assert er.frugal_enabled(yaml_path="missing.yaml") is True

    def test_env_zero_disables(self):
        """`SWARMIND_FRUGAL_ROUTING=0` apaga el routing puede yaml true."""
        assert er.frugal_enabled(env={"SWARMIND_FRUGAL_ROUTING": "0"}) is False

    def test_env_one_forces_on(self):
        """Env 1 fuerza el encendido (SSOT de operacion)."""
        assert er.frugal_enabled(env={"SWARMIND_FRUGAL_ROUTING": "1"}) is True

    def test_dispatch_model_deep_returns_empty(self):
        """Tarea profunda (razonamiento) NUNCA va al tier frugal."""
        assert er.frugal_dispatch_model("disena la arquitectura", is_deep_task=True) == ""

    def test_dispatch_model_empty_task(self):
        """Texto vacio no aplicable (cadena vacia)."""
        assert er.frugal_dispatch_model("", is_deep_task=False) == ""

    def test_dispatch_model_disabled(self):
        """Routing apagado: sin modelo frugal aunque la tarea sea small."""
        assert (
            er.frugal_dispatch_model(
                "renombrar variable",
                is_deep_task=False,
                env={"SWARMIND_FRUGAL_ROUTING": "0"},
            )
            == ""
        )

    def test_dispatch_model_default_task_gives_free(self):
        """Tarea small con routing activo devuelve el id gratis (beam)."""
        assert (
            er.frugal_dispatch_model("renombrar variable", is_deep_task=False)
            == DEFAULT_EDITS_MODEL
        )


class TestValidation:
    """model_id_is_valid (fail-soft, no lanza)."""

    @pytest.mark.parametrize(
        ("model_id", "expected"),
        [
            ("opencode-go/beam-free", True),
            ("opencode/beam-free", True),
            ("a/b", True),
            ("", False),
            ("a b/c", False),
            ("a/", False),
            ("/b", False),
            (" a/b", False),
            ("a/b/c", False),
        ],
    )
    def test_model_id_validity(self, model_id, expected):
        """Ids provider/model validos; los demas no."""
        assert er.model_id_is_valid(model_id) is expected


class TestMirror:
    """N6: el agente .md y el SSOT yaml comparten el default (signal drift)."""

    def test_yaml_default_matches_agent_frontmatter(self):
        """El id yaml == el model del frontmatter de beam-patcher."""
        ssot = yaml.safe_load((_REPO / RUNTIME_YAML_RELPATH).read_text(encoding="utf-8"))
        agent_md = (_REPO / ".opencode" / "agents" / "beam-patcher.md").read_text(
            encoding="utf-8"
        )
        front = yaml.safe_load(agent_md.split("---", 2)[1])
        assert front["model"] == ssot["defaults"]["edits_model"]
        assert front["mode"] == "subagent"
        assert front["description"]
        assert any(
            p["action"] == "edit" and p["effect"] == "allow"
            for p in front["permissions"]
        )
        assert any(
            p["action"] == "shell" and p["effect"] == "deny"
            for p in front["permissions"]
        )

    def test_command_is_wired_to_agent(self):
        """`/patch-free` referencia al subagente (cable de un solo archivo)."""
        command = (
            _REPO / ".opencode" / "commands" / "patch-free.md"
        ).read_text(encoding="utf-8")
        front = yaml.safe_load(command.split("---", 2)[1])
        assert front["agent"] == "beam-patcher"
