"""Tests de agent_card — identidad y descubrimiento A2A local (ADR-0058)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from harness.federation.agent_card import (
    AGENT_CARD_FILENAME,
    AgentCard,
    AgentSkill,
    card_path,
    discover_cards,
    load_agent_card,
    write_agent_card,
)


def _card(name: str = "cqe", **overrides: object) -> AgentCard:
    """Card de prueba con defaults válidos."""
    defaults: dict[str, object] = {
        "description": "Librería cuantitativa",
        "version": "1.0.0",
        "project_root": Path("C:/DEV-SPACE/core-quant-engine"),
        "skills": (
            AgentSkill(
                id="quant-lib-extension",
                name="Extensión de librería",
                description="Implementa funciones en la librería",
                tags=("quant", "library"),
            ),
        ),
    }
    defaults.update(overrides)
    return AgentCard(name=name, **defaults)  # type: ignore[arg-type]


class TestAgentCard:
    """Contrato de la card."""

    def test_has_skill_true_and_false(self) -> None:
        card = _card()
        assert card.has_skill("quant-lib-extension")
        assert not card.has_skill("no-existe")

    def test_to_dict_roundtrip_fields(self) -> None:
        data = _card().to_dict()
        assert data["name"] == "cqe"
        assert data["skills"][0]["id"] == "quant-lib-extension"  # type: ignore[index]

    def test_card_is_frozen(self) -> None:
        with pytest.raises(AttributeError):
            _card().name = "otro"  # type: ignore[misc]


class TestWriteLoad:
    """Publicación y carga en la URI bien conocida."""

    def test_card_path_is_well_known(self, tmp_path: Path) -> None:
        path = card_path(tmp_path)
        assert path == tmp_path / ".opencode/.well-known" / AGENT_CARD_FILENAME

    def test_write_then_load_roundtrip(self, tmp_path: Path) -> None:
        write_agent_card(_card(), tmp_path)
        loaded = load_agent_card(tmp_path)
        assert loaded.name == "cqe"
        assert loaded.has_skill("quant-lib-extension")

    def test_load_missing_raises_file_not_found(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError, match="agent-card"):
            load_agent_card(tmp_path)

    def test_load_invalid_json_raises_value_error(self, tmp_path: Path) -> None:
        path = card_path(tmp_path)
        path.parent.mkdir(parents=True)
        path.write_text("{no-json", encoding="utf-8")
        with pytest.raises(ValueError, match="JSON inválido"):
            load_agent_card(tmp_path)

    def test_load_missing_required_field_raises(self, tmp_path: Path) -> None:
        path = card_path(tmp_path)
        path.parent.mkdir(parents=True)
        path.write_text(json.dumps({"name": "x"}), encoding="utf-8")
        with pytest.raises(ValueError, match="campos requeridos"):
            load_agent_card(tmp_path)


class TestDiscovery:
    """discover_cards sobre un root de proyectos."""

    def test_discovers_only_projects_with_cards(self, tmp_path: Path) -> None:
        write_agent_card(_card("alpha"), tmp_path / "alpha")
        write_agent_card(_card("beta"), tmp_path / "beta")
        (tmp_path / "gamma").mkdir()  # sin card
        names = [c.name for c in discover_cards(tmp_path)]
        assert names == ["alpha", "beta"]

    def test_invalid_card_skipped_with_warning(self, tmp_path: Path) -> None:
        bad = tmp_path / "bad"
        (card_path(bad)).parent.mkdir(parents=True)
        card_path(bad).write_text('{"name": "incompleta"}', encoding="utf-8")
        write_agent_card(_card("good"), tmp_path / "good")
        names = [c.name for c in discover_cards(tmp_path)]
        assert names == ["good"]

    def test_missing_root_returns_empty(self, tmp_path: Path) -> None:
        assert discover_cards(tmp_path / "nope") == []
