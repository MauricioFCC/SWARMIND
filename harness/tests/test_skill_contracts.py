"""Contratos SDD de TODOS los skills (ADR-0048) — gate de cobertura y drift.

WHAT: cada skill de ``.opencode/skills`` debe tener ``SKILL.spec.json`` valido
(pre/postcondiciones, invariantes, failing_test) y su ``source_sha256`` debe
coincidir con el ``SKILL.md`` vigente (anti content-drift). El spec se genera
con ``python scripts/generate_skill_specs.py --write``.

WHY: solo 1 de 44 skills tenia contrato formal; sin contrato el orquestador no
puede rechazar invocaciones fuera de precondiciones y el body puede divergir
del spec sin que nadie lo note (gate VER).

WHERE: ``harness/tests`` — verificacion de solo lectura sobre ``.opencode``.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from harness.context.skill_contract import load_skill_contract, validate_contract

ROOT = Path(__file__).resolve().parents[2]
SKILLS_DIR = ROOT / ".opencode" / "skills"
SHARED_TEST = ROOT / "harness" / "tests" / "test_skill_contracts.py"

#: Minimo de keywords de body (mejora de routing body-aware, SkillRouter 2026).
MIN_BODY_KEYWORDS = 5


def _skill_dirs() -> list[Path]:
    """Directorios de skill reales (con SKILL.md), ordenados por nombre."""
    return sorted(
        path
        for path in SKILLS_DIR.iterdir()
        if path.is_dir() and (path / "SKILL.md").is_file()
    )


def _source_digest(skill_dir: Path) -> str:
    """sha256 del SKILL.md (oraculo independiente del generador)."""
    return hashlib.sha256((skill_dir / "SKILL.md").read_bytes()).hexdigest()


def _spec(skill_dir: Path) -> dict[str, object]:
    """Carga el JSON del spec tal cual (para claves extra del generador)."""
    return json.loads((skill_dir / "SKILL.spec.json").read_text(encoding="utf-8"))


class TestSpecCoverage:
    """Cobertura: todo skill del repositorio tiene contrato formal."""

    def test_every_skill_has_spec(self) -> None:
        """No queda ninguna skill sin SKILL.spec.json."""
        missing = [
            skill_dir.name
            for skill_dir in _skill_dirs()
            if not (skill_dir / "SKILL.spec.json").is_file()
        ]
        assert not missing, f"skills sin contrato SDD: {missing}"

    def test_shared_contract_test_exists(self) -> None:
        """El failing_test compartido existe (Ley de Hierro ADR-0047)."""
        assert SHARED_TEST.is_file()


class TestSpecValidity:
    """Cada contrato cumple el esquema y la semantica minima."""

    @pytest.mark.parametrize("skill_dir", _skill_dirs(), ids=lambda p: p.name)
    def test_contract_has_no_errors(self, skill_dir: Path) -> None:
        """load + validate_contract no reportan errores para el skill."""
        contract = load_skill_contract(skill_dir)
        assert contract is not None
        assert contract.name == skill_dir.name
        assert validate_contract(contract, skill_dir) == []
        assert len(contract.postconditions) >= 2
        assert contract.invariants

    @pytest.mark.parametrize("skill_dir", _skill_dirs(), ids=lambda p: p.name)
    def test_spec_matches_skill_md_digest(self, skill_dir: Path) -> None:
        """source_sha256 coincide con el SKILL.md actual (specs generados)."""
        spec = _spec(skill_dir)
        if "source_sha256" not in spec:
            pytest.skip("contrato manual curado (sin digest de origen)")
        assert spec["source_sha256"] == _source_digest(skill_dir), (
            f"{skill_dir.name}: SKILL.md cambio; regenerar con "
            "python scripts/generate_skill_specs.py --write"
        )

    @pytest.mark.parametrize("skill_dir", _skill_dirs(), ids=lambda p: p.name)
    def test_routing_keywords_are_distinctive(self, skill_dir: Path) -> None:
        """routing.body_keywords (specs generados): >=5, minusculas, sin duplicados."""
        spec = _spec(skill_dir)
        if not spec.get("provenance", {}).get("generator"):
            pytest.skip("contrato manual curado (sin routing generado)")
        keywords = spec.get("routing", {}).get("body_keywords", [])
        assert len(keywords) >= MIN_BODY_KEYWORDS, f"{skill_dir.name}: {keywords}"
        assert len(set(keywords)) == len(keywords)
        assert all(word == word.lower() and word.isalpha() for word in keywords)

    def test_specs_are_reproducible(self) -> None:
        """Regenerar el spec desde SKILL.md produce exactamente el fichero."""
        from scripts.generate_skill_specs import _serialize, build_specs

        expected = build_specs()
        drift = [
            name
            for name, spec in expected.items()
            if _spec(SKILLS_DIR / name).get("provenance", {}).get("generator")
            and (SKILLS_DIR / name / "SKILL.spec.json").read_text(encoding="utf-8")
            != _serialize(spec)
        ]
        assert not drift, f"specs no reproducibles: {drift}"
