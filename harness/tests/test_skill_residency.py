"""Tests de skill_residency — presupuesto de residencia y tiering (ADR-0053)."""
from __future__ import annotations

from pathlib import Path

import pytest

from harness.context.skill_residency import (
    DESC_TOKEN_RANGE,
    RESIDENT_SLOT_BUDGET,
    TARGET_RESIDENT_MAX,
    SkillTier,
    audit_residency,
    estimate_tokens,
    recommend_tiers,
)


def _make_skill(skills_dir: Path, name: str, description: str) -> None:
    """Crea una skill de prueba con frontmatter valido."""
    skill_dir = skills_dir / name
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: {description}\n---\n\n# {name}\n",
        encoding="utf-8",
    )


class TestEstimateTokens:
    """estimate_tokens: heuristica ~4 chars/token."""

    def test_empty_text_returns_zero(self) -> None:
        assert estimate_tokens("") == 0

    def test_four_chars_per_token(self) -> None:
        assert estimate_tokens("a" * 40) == 10

    def test_short_text_floors_to_zero(self) -> None:
        assert estimate_tokens("abc") == 0


class TestAuditResidency:
    """audit_residency sobre librerias temporales."""

    def test_missing_dir_raises_value_error(self, tmp_path: Path) -> None:
        with pytest.raises(ValueError, match="no existe"):
            audit_residency(tmp_path / "nope")

    def test_counts_skills_and_tokens(self, tmp_path: Path) -> None:
        _make_skill(tmp_path, "alpha", "x" * 400)
        _make_skill(tmp_path, "beta", "y" * 200)
        report = audit_residency(tmp_path)
        assert report.total_skills == 2
        # frontmatter de alpha ~ 428 chars -> 107 tokens
        assert report.resident_if_all_tokens > 0
        names = [s.name for s in report.skills]
        assert names == ["alpha", "beta"]

    def test_skill_without_frontmatter_costs_zero(self, tmp_path: Path) -> None:
        skill_dir = tmp_path / "plain"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text("# sin frontmatter\n", encoding="utf-8")
        report = audit_residency(tmp_path)
        assert report.skills[0].description_tokens == 0

    def test_warning_when_over_target_resident(self, tmp_path: Path) -> None:
        for i in range(TARGET_RESIDENT_MAX + 1):
            _make_skill(tmp_path, f"skill-{i:02d}", "d" * 100)
        report = audit_residency(tmp_path)
        assert any("clasificar en tiers" in w for w in report.warnings)

    def test_no_warning_for_small_library(self, tmp_path: Path) -> None:
        _make_skill(tmp_path, "solo", "desc corta")
        report = audit_residency(tmp_path)
        assert report.warnings == ()

    def test_budget_constant_matches_paper(self) -> None:
        assert RESIDENT_SLOT_BUDGET == 100
        low, high = DESC_TOKEN_RANGE
        assert low < high and low >= 50


class TestRecommendTiers:
    """recommend_tiers: esenciales INSTALLED, resto REFERENCE."""

    def test_essential_installed_rest_reference(self, tmp_path: Path) -> None:
        _make_skill(tmp_path, "core", "a")
        _make_skill(tmp_path, "extra", "b")
        report = audit_residency(tmp_path)
        tiers = recommend_tiers(report, essential={"core"})
        assert tiers["core"] is SkillTier.INSTALLED
        assert tiers["extra"] is SkillTier.REFERENCE

    def test_too_many_essential_raises(self, tmp_path: Path) -> None:
        _make_skill(tmp_path, "only", "a")
        report = audit_residency(tmp_path)
        essential = {f"ghost-{i}" for i in range(TARGET_RESIDENT_MAX + 1)}
        with pytest.raises(ValueError, match="TARGET_RESIDENT_MAX"):
            recommend_tiers(report, essential=essential)

    def test_unknown_essential_raises(self, tmp_path: Path) -> None:
        _make_skill(tmp_path, "real", "a")
        report = audit_residency(tmp_path)
        with pytest.raises(ValueError, match="inexistentes"):
            recommend_tiers(report, essential={"fantasma"})
