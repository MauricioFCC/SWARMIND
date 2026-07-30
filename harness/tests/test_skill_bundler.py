"""
Tests para SkillBundler — composicion dinamica de agentes desde skills.
"""
from __future__ import annotations

import pytest

from harness.orchestrator.skill_bundler import SkillBundler


@pytest.fixture
def bundler() -> SkillBundler:
    """SkillBundler con registry real."""
    return SkillBundler()


class TestInit:
    """Inicializacion del SkillBundler."""

    def test_loads_registry(self, bundler: SkillBundler) -> None:
        """Debe cargar skills desde el registry."""
        skills = bundler.list_skills()
        assert len(skills) >= 15
        assert "rust-lang" in skills
        assert "frontend-uiux" in skills
        assert "security-audit" in skills

    def test_detects_all_domains(self, bundler: SkillBundler) -> None:
        """Debe listar todos los dominios soportados."""
        domains = bundler.list_domains()
        assert "web" in domains
        assert "data" in domains
        assert "security" in domains
        assert "general" in domains


class TestDetectDomain:
    """Deteccion de dominio por palabras clave."""

    @pytest.mark.parametrize("task,expected_domain", [
        ("Desarrollar una API REST en Rust", "api"),
        ("Crear un frontend web con React", "frontend"),
        ("Analisis de datos con pandas y sklearn", "data"),
        ("Auditoria de seguridad OWASP Top 10", "security"),
        ("Arquitectura hexagonal para microservicios", "architecture"),
        ("Estrategia de trading cuantitativo", "trading"),
        ("Investigacion de papers sobre transformers", "research"),
        ("Documento juridico contrato de arrendamiento", "legal"),
        ("Sistema de health-record electronica", "health"),
        ("Punto de venta para tienda minorista", "retail"),
        ("Hola mundo", "general"),
        ("", "general"),
    ])
    def test_detect_domain(
        self, bundler: SkillBundler, task: str, expected_domain: str
    ) -> None:
        """Debe detectar el dominio correcto."""
        assert bundler.detect_domain(task) == expected_domain


class TestSelectSkills:
    """Seleccion de skills por dominio."""

    def test_domain_skills(self, bundler: SkillBundler) -> None:
        """Dominio web debe incluir frontend-uiux y responsive-ui."""
        skills = bundler.select_skills("web")
        assert "frontend-uiux" in skills
        assert "responsive-ui" in skills

    def test_security_domain(self, bundler: SkillBundler) -> None:
        """Dominio security debe incluir security-audit."""
        skills = bundler.select_skills("security")
        assert "security-audit" in skills

    def test_general_fallback(self, bundler: SkillBundler) -> None:
        """Dominio desconocido debe usar general."""
        skills = bundler.select_skills("unknown_domain")
        assert len(skills) > 0

    def test_task_keywords_add_skills(self, bundler: SkillBundler) -> None:
        """Testing keywords deben agregar security-audit."""
        skills = bundler.select_skills("web", task="ejecutar tests de integracion")
        assert "security-audit" in skills


class TestCompose:
    """Composicion de agentes desde skills."""

    def test_compose_api_task(self, bundler: SkillBundler) -> None:
        """Tarea API debe componer builder con rust-lang y architecture."""
        agents = bundler.compose("Desarrollar API REST en Rust")
        assert len(agents) > 0
        # Buscar builder con rust-lang
        builder = next((a for a in agents if a.name == "builder"), None)
        assert builder is not None
        assert "rust-lang" in builder.bundled_skills

    def test_compose_frontend_task(self, bundler: SkillBundler) -> None:
        """Tarea frontend debe incluir frontend-uiux."""
        agents = bundler.compose("Crear landing page responsive con React")
        frontend = next((a for a in agents if a.name == "builder"), None)
        assert frontend is not None
        assert "frontend-uiux" in frontend.bundled_skills

    def test_compose_security_task(self, bundler: SkillBundler) -> None:
        """Tarea seguridad debe asignar security-audit a guardian."""
        agents = bundler.compose("Auditoria de seguridad OWASP")
        guardian = next((a for a in agents if a.name == "guardian"), None)
        assert guardian is not None
        assert "security-audit" in guardian.bundled_skills

    def test_compose_general_task(self, bundler: SkillBundler) -> None:
        """Tarea generica debe producir configuraciones."""
        agents = bundler.compose("Hola mundo")
        assert len(agents) >= 3  # builder, scientist, guardian

    def test_compose_empty_task(self, bundler: SkillBundler) -> None:
        """Tarea vacia debe manejar graceful."""
        agents = bundler.compose("")
        assert len(agents) >= 3

    def test_agent_config_has_lead_skill(self, bundler: SkillBundler) -> None:
        """Cada agente debe tener un lead_skill."""
        agents = bundler.compose("Desarrollar API REST en Rust")
        for agent in agents:
            if agent.bundled_skills:
                assert agent.lead_skill == agent.bundled_skills[0]


class TestSkillDescriptions:
    """Descripciones de skills desde el registry."""

    def test_get_description(self, bundler: SkillBundler) -> None:
        """Debe obtener descripcion de un skill existente."""
        desc = bundler.get_skill_description("rust-lang")
        assert len(desc) > 0
        assert "Rust" in desc

    def test_get_description_nonexistent(self, bundler: SkillBundler) -> None:
        """Skill inexistente debe retornar string vacio."""
        assert bundler.get_skill_description("nonexistent-skill") == ""


class TestAvailableAgents:
    """Filtro de agentes disponibles."""

    def test_custom_agents(self, bundler: SkillBundler) -> None:
        """Debe respetar la lista de agentes disponibles."""
        agents = bundler.compose(
            "Desarrollar API REST",
            available_agents=["builder", "guardian"],
        )
        names = [a.name for a in agents]
        assert "builder" in names
        assert "guardian" in names
        assert "scientist" not in names

    def test_single_agent(self, bundler: SkillBundler) -> None:
        """Un solo agente disponible debe funcionar."""
        agents = bundler.compose(
            "Tarea de seguridad",
            available_agents=["guardian"],
        )
        assert len(agents) == 1
        assert agents[0].name == "guardian"
