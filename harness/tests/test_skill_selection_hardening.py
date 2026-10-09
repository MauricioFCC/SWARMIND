"""Tests de endurecimiento de la seleccion/descarte de SKILLS del coordinator.

WHAT: fija el comportamiento correcto tras reemplazar el matching por substring
por `keyword_match` (frontera de palabra) en ``SkillBundler.detect_domain`` /
``select_skills`` y el matching por tokens en ``SkillGenerator.find_in_registry``.
WHY: la sonda adversarial documento falsos positivos ("api" en "capital", "pos"
en "position", "doc" en "docker") y falsos negativos (la query COMPLETA debia ser
substring de un campo). Estos tests son la version verde (VER).
WHERE: ``harness/tests``.
"""

from __future__ import annotations

from harness.evolve_loop.skill_generator import SkillGenerator
from harness.orchestrator.skill_bundler import SkillBundler


class TestDetectDomainWordBoundary:
    """``detect_domain`` no dispara por substrings colisionantes."""

    def test_capital_no_es_dominio_api(self) -> None:
        """'capital' contiene 'api' pero NO debe detectarse como dominio api."""
        assert SkillBundler().detect_domain("asignar capital del fondo") != "api"

    def test_position_no_es_dominio_retail(self) -> None:
        """'position' contiene 'pos' pero NO debe detectarse como retail."""
        assert SkillBundler().detect_domain("position sizing") != "retail"

    def test_docker_es_dominio_devops(self) -> None:
        """'deploy con docker' si detecta devops (keyword completa)."""
        assert SkillBundler().detect_domain("deploy con docker") == "devops"

    def test_api_real_sigue_detectandose(self) -> None:
        """Una API real sigue detectandose como api (no se rompio el positivo)."""
        assert SkillBundler().detect_domain("desarrollar una API REST") == "api"


class TestSelectSkillsWordBoundary:
    """``select_skills`` no inyecta documentacion por 'doc' dentro de 'docker'."""

    def test_docker_no_agrega_skills_de_documentacion(self) -> None:
        """Docker no debe arrastrar science-doc/legal-doc."""
        skills = SkillBundler().select_skills("devops", "deploy con docker")
        assert "science-doc" not in skills
        assert "legal-doc" not in skills

    def test_documentacion_explicita_si_agrega(self) -> None:
        """Mencionar 'documentacion' como palabra si agrega las skills."""
        skills = SkillBundler().select_skills("devops", "escribe la documentacion del deploy")
        assert {"science-doc", "legal-doc"} <= set(skills)

    def test_dominio_desconocido_abstiene(self) -> None:
        """Un dominio desconocido devuelve [] (no fabrica la lista general)."""
        assert SkillBundler().select_skills("dominio_inexistente") == []

    def test_sin_duplicados(self) -> None:
        """La seleccion no repite skills (INV-5)."""
        skills = SkillBundler().select_skills("devops", "deploy con docker")
        assert len(skills) == len(set(skills))


class TestFindInRegistryTokenMatch:
    """``find_in_registry`` matchea por tokens (name/trigger/description/domain)."""

    def test_frase_natural_seguridad(self) -> None:
        """'auditoria de seguridad' encuentra security-audit."""
        match = SkillGenerator.find_in_registry("auditoria de seguridad")
        assert match is not None
        assert match["name"] == "security-audit"

    def test_frase_natural_rust(self) -> None:
        """'necesito programar en rust' encuentra rust-lang."""
        match = SkillGenerator.find_in_registry("necesito programar en rust")
        assert match is not None
        assert match["name"] == "rust-lang"

    def test_keyword_exacta_sigue_funcionando(self) -> None:
        """El keyword exacto 'rust' sigue encontrando rust-lang."""
        match = SkillGenerator.find_in_registry("rust")
        assert match is not None
        assert match["name"] == "rust-lang"

    def test_ruido_abstiene(self) -> None:
        """Una query sin tokens reconocibles devuelve None."""
        assert SkillGenerator.find_in_registry("xyzzy plugh quux") is None


class TestDeterminismo:
    """Misma entrada -> misma salida entre llamadas (INV-1)."""

    def test_detect_domain_determinista(self) -> None:
        """``detect_domain`` es estable entre llamadas."""
        bundler = SkillBundler()
        task = "asignar capital del fondo"
        assert bundler.detect_domain(task) == bundler.detect_domain(task)

    def test_select_skills_determinista(self) -> None:
        """``select_skills`` es estable entre llamadas."""
        bundler = SkillBundler()
        first = bundler.select_skills("devops", "deploy con docker")
        second = bundler.select_skills("devops", "deploy con docker")
        assert first == second

    def test_find_in_registry_determinista(self) -> None:
        """``find_in_registry`` es estable entre llamadas."""
        first = SkillGenerator.find_in_registry("auditoria de seguridad")
        second = SkillGenerator.find_in_registry("auditoria de seguridad")
        assert first == second
