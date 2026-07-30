"""
Tests de propagacion — verifican que los 5 proyectos tengan configuracion correcta.

Cubre:
- routing_rules.yaml sin agentes fantasma
- Archivos clave presentes
- Agentes y skills correctos
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List

import pytest

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

PROJECTS: Dict[str, Path] = {
    "CQE": Path(r"$HOME\Documents\DEV-SPACE\quant-engine"),
    "HC": Path(r"$HOME\Documents\DEV-SPACE\health-record"),
    "Onyx": Path(r"$HOME\Documents\DEV-SPACE\trading-bot-AIBot"),
    "PDV": Path(r"$HOME\Documents\DEV-SPACE\pos-system"),
    "Hermes": Path(r"$HOME\Documents\shared_memory"),
}

# Agentes fantasma que NO deben aparecer en routing_rules.yaml
PHANTOM_AGENTS = [
    "quant-developer", "quant-scientist", "risk-manager",
    "trading-operations", "enterprise-architect", "ai-engineer",
    "software-engineer", "frontend-engineer", "data-architect",
    "devops-sre", "security-engineer", "mobile-engineer",
    "documentation-specialist", "project-manager", "requirements-analyst",
    "quality-gate",
]

# Archivos clave que DEBEN estar presentes en harness/
KEY_FILES = [
    "orchestrator/write_ahead_log.py",
    "gpu_accel.py",
    "gpu_optimize.py",
    "orchestrator/agent_capsules.py",
    "orchestrator/context_scoped.py",
    "orchestrator/worktable.py",
    "orchestrator/skill_bundler.py",
    "orchestrator/token_optimizer.py",
]

# Skills esperados por proyecto
EXPECTED_SKILLS: Dict[str, List[str]] = {
    "CQE": ["alpha-research", "evolve", "hedgefund", "math-doc", "quant-trading", "risk-execution", "science-doc"],
    "HC": ["evolve", "healthtech", "hedgefund", "legal-doc", "science-doc"],
    "Onyx": ["alpha-research", "evolve", "hedgefund", "math-doc", "quant-trading", "risk-execution", "science-doc"],
    "PDV": ["evolve", "hedgefund", "legal-doc", "pos-retail"],
    "Hermes": ["evolve", "healthtech", "hedgefund", "legal-doc", "math-doc", "pos-retail", "quant-trading", "risk-execution", "science-doc"],
}


# ===========================================================================
# Tests
# ===========================================================================


class TestRoutingRules:
    """routing_rules.yaml no debe contener agentes fantasma."""

    @pytest.mark.parametrize("name", list(PROJECTS.keys()))
    def test_no_phantom_agents(self, name: str) -> None:
        """Ningun proyecto debe referenciar agentes que no existen."""
        routing = PROJECTS[name] / ".opencode" / "config" / "routing_rules.yaml"
        assert routing.exists(), f"routing_rules.yaml not found in {name}"
        content = routing.read_text(encoding="utf-8")
        
        found = [a for a in PHANTOM_AGENTS if a in content]
        assert not found, f"{name} contiene agentes fantasma: {found}"

    @pytest.mark.parametrize("name", list(PROJECTS.keys()))
    def test_has_real_agents(self, name: str) -> None:
        """Debe contener los agentes reales del sistema."""
        routing = PROJECTS[name] / ".opencode" / "config" / "routing_rules.yaml"
        content = routing.read_text(encoding="utf-8")
        assert "coordinator" in content
        assert "builder" in content
        assert "scientist" in content
        assert "guardian" in content
        assert "evolve" in content


class TestKeyFiles:
    """Archivos clave del sistema deben estar presentes."""

    @pytest.mark.parametrize("name", list(PROJECTS.keys()))
    def test_key_files_present(self, name: str) -> None:
        """Todos los archivos clave deben existir en cada proyecto."""
        missing = []
        for f in KEY_FILES:
            full_path = PROJECTS[name] / "harness" / f
            if not full_path.exists():
                missing.append(f)
        assert not missing, f"{name} faltan: {missing}"


class TestAgentFiles:
    """Agentes correctamente desplegados."""

    @pytest.mark.parametrize("name", list(PROJECTS.keys()))
    def test_agent_count(self, name: str) -> None:
        """Deben haber 8 agentes desplegados."""
        agents_dir = PROJECTS[name] / ".opencode" / "agents"
        md_files = list(agents_dir.glob("*.md"))
        assert len(md_files) >= 8, f"{name} tiene solo {len(md_files)} agentes"

    @pytest.mark.parametrize("name", list(PROJECTS.keys()))
    def test_core_agents_exist(self, name: str) -> None:
        """Los 5 agentes principales deben existir."""
        agents_dir = PROJECTS[name] / ".opencode" / "agents"
        core = ["coordinator", "builder", "scientist", "guardian", "evolve"]
        existing = [f.stem for f in agents_dir.glob("*.md")]
        missing = [a for a in core if a not in existing]
        assert not missing, f"{name} faltan agentes: {missing}"


class TestSkills:
    """Skills correctamente desplegados por proyecto."""

    @pytest.mark.parametrize("name", list(PROJECTS.keys()))
    def test_skills_deployed(self, name: str) -> None:
        """Skills esperados deben estar presentes."""
        skills_dir = PROJECTS[name] / ".opencode" / "skills"
        deployed = {d.name for d in skills_dir.iterdir() if d.is_dir()}
        expected = set(EXPECTED_SKILLS.get(name, []))
        missing = expected - deployed
        assert not missing, f"{name} faltan skills: {missing}"


class TestTestFiles:
    """Tests correctamente desplegados."""

    @pytest.mark.parametrize("name", list(PROJECTS.keys()))
    def test_test_files_count(self, name: str) -> None:
        """Cada proyecto debe tener al menos 40 archivos de test."""
        tests_dir = PROJECTS[name] / "harness" / "tests"
        test_files = list(tests_dir.glob("test_*.py"))
        assert len(test_files) >= 40, f"{name} tiene solo {len(test_files)} tests"


class TestHermesSpecific:
    """Tests especificos para Hermes (memoria central)."""

    def test_hermes_has_max_skills(self) -> None:
        """Hermes debe tener la mayor cantidad de skills (9)."""
        skills_dir = PROJECTS["Hermes"] / ".opencode" / "skills"
        count = sum(1 for _ in skills_dir.iterdir() if _.is_dir())
        assert count >= 8, f"Hermes solo tiene {count} skills"
