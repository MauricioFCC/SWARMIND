"""
Tests para LazySkillLoader — Carga progresiva de skills en 3 niveles.

Cubre: descubrimiento, cache, carga tier 1/2/3, detección de dominio,
minificación, manejo de errores y edge cases.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from harness.memory_rag.skill_loader import (
    DOMAIN_KEYWORDS,
    SKILL_DOMAIN_MAP,
    LazySkillLoader,
    SkillInfo,
    create_loader,
)

# ===========================================================================
# Helpers para crear directorios de skills de prueba
# ===========================================================================


def _make_skill_dir(
    base: Path,
    name: str,
    description: str = "Test skill description",
    full_content: str = "",
    min_content: str = "",
    has_full: bool = True,
    has_min: bool = True,
) -> Path:
    """Crea un directorio de skill con SKILL.md y/o SKILL.min.md."""
    skill_dir = base / name
    skill_dir.mkdir(exist_ok=True)
    frontmatter = f'---\ndescription: "{description}"\n---\n\n'

    if has_full:
        content = frontmatter + (full_content or f"# {name}\n\nFull content of {name}.")
        (skill_dir / "SKILL.md").write_text(content, encoding="utf-8")

    if has_min:
        content = frontmatter + (min_content or f"# {name} (minified)\n\nKey points of {name}.")
        (skill_dir / "SKILL.min.md").write_text(content, encoding="utf-8")

    return skill_dir


@pytest.fixture
def skills_dir() -> Path:
    """Directorio temporal con skills de prueba."""
    tmp = Path(tempfile.mkdtemp(prefix="skills_test_"))
    _make_skill_dir(tmp, "hedgefund", "Hedge fund institutional doctrine", has_full=True, has_min=True)
    _make_skill_dir(tmp, "quant-trading", "Quantitative trading strategies", has_full=True, has_min=True)
    _make_skill_dir(tmp, "alpha-research", "Alpha research and analysis", has_full=True, has_min=True)
    _make_skill_dir(tmp, "evolve", "Meta-skill for continuous improvement", has_full=True, has_min=False)
    yield tmp
    # Cleanup
    import shutil
    shutil.rmtree(str(tmp), ignore_errors=True)


@pytest.fixture
def empty_skills_dir() -> Path:
    """Directorio temporal vacío."""
    tmp = Path(tempfile.mkdtemp(prefix="skills_empty_"))
    yield tmp
    import shutil
    shutil.rmtree(str(tmp), ignore_errors=True)


@pytest.fixture
def mixed_skills_dir() -> Path:
    """Directorio con skills que tienen solo un formato."""
    tmp = Path(tempfile.mkdtemp(prefix="skills_mixed_"))
    # Solo SKILL.md
    _make_skill_dir(tmp, "risk-execution", "Risk and execution management", has_full=True, has_min=False)
    # Solo SKILL.min.md
    _make_skill_dir(tmp, "healthtech", "Healthtech domain skills", has_full=False, has_min=True)
    # Ninguno
    skill_dir3 = tmp / "custom-skill"
    skill_dir3.mkdir(exist_ok=True)
    yield tmp
    import shutil
    shutil.rmtree(str(tmp), ignore_errors=True)


# ===========================================================================
# Tests: SkillInfo
# ===========================================================================


class TestSkillInfo:
    """Tests para SkillInfo dataclass."""

    def test_to_tier1(self) -> None:
        """to_tier1 retorna name + description acotado."""
        info = SkillInfo(name="test", description="A " * 150)  # >200 chars
        t1 = info.to_tier1()
        assert info.name in t1
        assert info.description[:200] in t1
        assert len(t1) < 250

    def test_to_tier2_uses_tier2_content(self) -> None:
        """to_tier2 prefiere content_tier2 sobre content_tier3."""
        info = SkillInfo(
            name="test", description="desc",
            content_tier2="minified", content_tier3="full",
        )
        assert info.to_tier2() == "minified"

    def test_to_tier2_fallback_to_tier3(self) -> None:
        """to_tier2 cae a content_tier3 si no hay tier2."""
        info = SkillInfo(
            name="test", description="desc",
            content_tier2="", content_tier3="full only",
        )
        assert info.to_tier2() == "full only"

    def test_to_tier3(self) -> None:
        """to_tier3 retorna content_tier3."""
        info = SkillInfo(name="test", description="desc", content_tier3="full content")
        assert info.to_tier3() == "full content"

    def test_default_tier_is_1(self) -> None:
        """SkillInfo default tier es 1."""
        info = SkillInfo(name="test", description="desc")
        assert info.tier == 1


# ===========================================================================
# Tests: Inicialización y Descubrimiento
# ===========================================================================


class TestDiscovery:
    """Tests para descubrimiento de skills."""

    def test_discover_skills(self, skills_dir: Path) -> None:
        """descubre skills del directorio."""
        loader = LazySkillLoader(skills_dir=str(skills_dir), auto_discover=True)
        assert len(loader._skills) == 4
        assert "hedgefund" in loader._skills
        assert "evolve" in loader._skills

    def test_discover_no_auto_discover(self, skills_dir: Path) -> None:
        """auto_discover=False no descubre skills."""
        loader = LazySkillLoader(skills_dir=str(skills_dir), auto_discover=False)
        assert len(loader._skills) == 0

    def test_discover_nonexistent_dir(self) -> None:
        """Directorio inexistente no causa error."""
        loader = LazySkillLoader(skills_dir="/nonexistent/path", auto_discover=True)
        assert len(loader._skills) == 0

    def test_discover_empty_dir(self, empty_skills_dir: Path) -> None:
        """Directorio vacío descubre 0 skills."""
        loader = LazySkillLoader(skills_dir=str(empty_skills_dir), auto_discover=True)
        assert len(loader._skills) == 0

    def test_discover_mixed_formats(self, mixed_skills_dir: Path) -> None:
        """Descubre skills con diferentes formatos de archivo."""
        loader = LazySkillLoader(skills_dir=str(mixed_skills_dir), auto_discover=True)
        assert "risk-execution" in loader._skills
        assert "healthtech" in loader._skills
        assert "custom-skill" in loader._skills
        # custom-skill no tiene archivos -> description por defecto
        custom = loader._skills["custom-skill"]
        assert custom.description == "Skill: custom-skill"

    def test_discover_reads_content(self, skills_dir: Path) -> None:
        """Descubre y cachea contenido de tiers."""
        loader = LazySkillLoader(skills_dir=str(skills_dir), auto_discover=True)
        hedge = loader._skills["hedgefund"]
        assert hedge.content_tier2 != ""  # minified
        assert hedge.content_tier3 != ""  # full

    def test_discover_evolve_no_min(self, skills_dir: Path) -> None:
        """Skill sin min.md usa full como tier2."""
        loader = LazySkillLoader(skills_dir=str(skills_dir), auto_discover=True)
        evolve = loader._skills["evolve"]
        assert evolve.content_tier2 == evolve.content_tier3
        assert evolve.content_tier3 != ""


# ===========================================================================
# Tests: SkillInfo domain mapping
# ===========================================================================


class TestDomainMapping:
    """Tests para mapeo de skills a dominios."""

    def test_skill_domain_map_exists(self) -> None:
        """SKILL_DOMAIN_MAP contiene las skills esperadas."""
        assert "hedgefund" in SKILL_DOMAIN_MAP
        assert "quant-trading" in SKILL_DOMAIN_MAP
        assert "evolve" in SKILL_DOMAIN_MAP

    def test_unknown_skill_maps_to_general(self, skills_dir: Path) -> None:
        """Skill no mapeada obtiene dominio ['general']."""
        _make_skill_dir(skills_dir, "unknown-skill", "Some skill")
        loader = LazySkillLoader(skills_dir=str(skills_dir), auto_discover=True)
        skill = loader._skills.get("unknown-skill")
        assert skill is not None
        assert skill.domain == ["general"]

    def test_domain_keywords(self) -> None:
        """DOMAIN_KEYWORDS contiene los dominios esperados."""
        assert "trading" in DOMAIN_KEYWORDS
        assert "general" in DOMAIN_KEYWORDS
        assert "quant" in DOMAIN_KEYWORDS["trading"]
        assert "health" in DOMAIN_KEYWORDS["healthtech"]


# ===========================================================================
# Tests: Tier 1 — Nombres siempre en prompt
# ===========================================================================


class TestTier1:
    """Tests para Tier 1: nombres + descripciones siempre en prompt."""

    def test_get_tier1_prompt_all(self, skills_dir: Path) -> None:
        """get_tier1_prompt lista todos los skills sin filtro."""
        loader = LazySkillLoader(skills_dir=str(skills_dir), auto_discover=True)
        prompt = loader.get_tier1_prompt()
        assert "## Available Skills" in prompt
        assert "hedgefund" in prompt
        assert "quant-trading" in prompt
        assert "evolve" in prompt

    def test_get_tier1_prompt_domain_filter(self, skills_dir: Path) -> None:
        """get_tier1_prompt con domain_filter solo incluye skills de ese dominio."""
        loader = LazySkillLoader(skills_dir=str(skills_dir), auto_discover=True)
        prompt = loader.get_tier1_prompt(domain_filter=["trading"])
        assert "quant-trading" in prompt
        # hedgefund es "general" -> no debería estar en filtro trading
        # (pero habilidades sin domain_filter solo se filtran por dominio)
        assert "hedgefund" not in prompt

    def test_get_tier1_prompt_empty_filter(self, skills_dir: Path) -> None:
        """domain_filter=['nonexistent'] retorna solo header."""
        loader = LazySkillLoader(skills_dir=str(skills_dir), auto_discover=True)
        prompt = loader.get_tier1_prompt(domain_filter=["nonexistent"])
        assert "## Available Skills" in prompt
        assert "hedgefund" not in prompt

    def test_get_tier1_prompt_lazy_marker(self, skills_dir: Path) -> None:
        """Skills domain-triggered aparecen con [lazy] sin domain_filter."""
        loader = LazySkillLoader(skills_dir=str(skills_dir), auto_discover=True)
        prompt = loader.get_tier1_prompt()  # sin filtro
        # quant-trading está en DOMAIN_TRIGGERED_SKILLS
        assert "[lazy]" in prompt

    def test_get_tier1_prompt_no_lazy_marker_with_filter(self, skills_dir: Path) -> None:
        """Con domain_filter, skills domain-triggered no muestran [lazy]."""
        loader = LazySkillLoader(skills_dir=str(skills_dir), auto_discover=True)
        prompt = loader.get_tier1_prompt(domain_filter=["trading"])
        assert "[lazy]" not in prompt

    def test_get_tier1_prompt_empty_skills(self) -> None:
        """get_tier1_prompt sin skills solo muestra header."""
        loader = LazySkillLoader(auto_discover=False)
        prompt = loader.get_tier1_prompt()
        assert "## Available Skills" in prompt


# ===========================================================================
# Tests: Tier 2 — Carga On-Demand
# ===========================================================================


class TestTier2:
    """Tests para Tier 2: carga on-demand de minified content."""

    def test_load_tier2_success(self, skills_dir: Path) -> None:
        """load_tier2 carga skill a tier 2."""
        loader = LazySkillLoader(skills_dir=str(skills_dir), auto_discover=True)
        results = loader.load_tier2(["hedgefund"])
        assert results["hedgefund"] is True
        skill = loader._skills["hedgefund"]
        assert skill.tier == 2
        assert skill.loaded is True
        assert "hedgefund" in loader._active_skills

    def test_load_tier2_unknown_skill(self, skills_dir: Path) -> None:
        """load_tier2 con skill desconocido retorna False."""
        loader = LazySkillLoader(skills_dir=str(skills_dir), auto_discover=True)
        results = loader.load_tier2(["nonexistent"])
        assert results["nonexistent"] is False

    def test_load_tier2_already_loaded(self, skills_dir: Path) -> None:
        """load_tier2 en skill ya cargado no incrementa loads."""
        loader = LazySkillLoader(skills_dir=str(skills_dir), auto_discover=True)
        loader.load_tier2(["hedgefund"])
        loads_before = loader._stats["loads_tier2"]
        loader.load_tier2(["hedgefund"])
        assert loader._stats["loads_tier2"] == loads_before

    def test_load_tier2_force_reload(self, skills_dir: Path) -> None:
        """force=True recarga incluso si ya está cargado."""
        loader = LazySkillLoader(skills_dir=str(skills_dir), auto_discover=True)
        loader.load_tier2(["hedgefund"])
        loads_before = loader._stats["loads_tier2"]
        loader.load_tier2(["hedgefund"], force=True)
        assert loader._stats["loads_tier2"] > loads_before

    def test_load_tier2_no_min_content_uses_full_fallback(self, mixed_skills_dir: Path) -> None:
        """Skill sin min.md usa full content como tier 2 (fallback en discover)."""
        loader = LazySkillLoader(skills_dir=str(mixed_skills_dir), auto_discover=True)
        results = loader.load_tier2(["risk-execution"])  # solo SKILL.md
        assert results["risk-execution"] is True
        skill = loader._skills["risk-execution"]
        # Nota: discover copia full content a tier2 como fallback
        assert skill.tier == 2  # tier 2 porque content_tier2 se pobló con full

    def test_load_tier2_no_content_at_all(self, mixed_skills_dir: Path) -> None:
        """Skill sin contenido alguno retorna False.

        Nota: custom-skill existe como directorio, se descubre con
        description="Skill: custom-skill", pero no tiene content_tier2
        porque no hay SKILL.md ni SKILL.min.md.
        """
        loader = LazySkillLoader(skills_dir=str(mixed_skills_dir), auto_discover=True)
        # custom-skill no tiene SKILL.md ni SKILL.min.md
        custom = loader._skills.get("custom-skill")
        assert custom is not None, "custom-skill debería descubrirse aunque sin archivos"
        assert custom.content_tier2 == "", "no debería tener content_tier2"
        results = loader.load_tier2(["custom-skill"])
        assert results["custom-skill"] is False


# ===========================================================================
# Tests: Tier 3 — Carga Full Content
# ===========================================================================


class TestTier3:
    """Tests para Tier 3: carga completa de skill."""

    def test_load_tier3_success(self, skills_dir: Path) -> None:
        """load_tier3 carga skill a tier 3."""
        loader = LazySkillLoader(skills_dir=str(skills_dir), auto_discover=True)
        results = loader.load_tier3(["quant-trading"])
        assert results["quant-trading"] is True
        skill = loader._skills["quant-trading"]
        assert skill.tier == 3
        assert skill.loaded is True

    def test_load_tier3_unknown_skill(self, skills_dir: Path) -> None:
        """load_tier3 con skill desconocido retorna False."""
        loader = LazySkillLoader(skills_dir=str(skills_dir), auto_discover=True)
        results = loader.load_tier3(["void"])
        assert results["void"] is False

    def test_load_tier3_no_content(self, empty_skills_dir: Path) -> None:
        """load_tier3 sin contenido retorna False."""
        loader = LazySkillLoader(skills_dir=str(empty_skills_dir), auto_discover=True)
        # Descubrió 0 skills así que no hay nada que cargar
        results = loader.load_tier3(["anything"])
        assert results["anything"] is False


# ===========================================================================
# Tests: load_for_domain
# ===========================================================================


class TestLoadForDomain:
    """Tests para load_for_domain — carga contextual."""

    def test_load_for_domain_trading(self, skills_dir: Path) -> None:
        """load_for_domain trading carga skills de trading."""
        loader = LazySkillLoader(skills_dir=str(skills_dir), auto_discover=True)
        results = loader.load_for_domain(["trading"])
        # quant-trading, alpha-research están en DOMAIN_TRIGGERED_SKILLS y dominio trading
        # hedgefund y evolve son ALWAYS_LOAD_SKILLS y también se cargan
        assert "quant-trading" in results
        assert "hedgefund" in results
        assert "evolve" in results

    def test_load_for_domain_unknown(self, skills_dir: Path) -> None:
        """load_for_domain con dominio desconocido solo carga always-on."""
        loader = LazySkillLoader(skills_dir=str(skills_dir), auto_discover=True)
        results = loader.load_for_domain(["nonexistent"])
        # Siempre carga ALWAYS_LOAD_SKILLS
        assert "hedgefund" in results
        assert "evolve" in results
        # No debe cargar domain-triggered skills
        assert "quant-trading" not in results

    def test_load_for_domain_multiple(self, skills_dir: Path) -> None:
        """load_for_domain con múltiples dominios."""
        loader = LazySkillLoader(skills_dir=str(skills_dir), auto_discover=True)
        results = loader.load_for_domain(["trading", "general"])
        assert len(results) >= 3

    def test_load_for_domain_tier_param(self, skills_dir: Path) -> None:
        """load_for_domain respeta el parámetro tier."""
        loader = LazySkillLoader(skills_dir=str(skills_dir), auto_discover=True)
        results_t2 = loader.load_for_domain(["trading"], tier=2)
        results_t3 = loader.load_for_domain(["general"], tier=3)
        # Ambos deben tener always-on
        assert "hedgefund" in results_t2
        assert "hedgefund" in results_t3

    def test_load_for_domain_idempotent(self, skills_dir: Path) -> None:
        """load_for_domain es idempotente (segunda llamada no duplica)."""
        loader = LazySkillLoader(skills_dir=str(skills_dir), auto_discover=True)
        loader.load_for_domain(["trading"])
        loads_before = loader._stats["loads_tier2"]
        loader.load_for_domain(["trading"])
        assert loader._stats["loads_tier2"] == loads_before


# ===========================================================================
# Tests: Context Building
# ===========================================================================


class TestContextBuilding:
    """Tests para construcción de contexto activo."""

    def test_get_active_skills_context_empty(self) -> None:
        """get_active_skills_context sin skills activos retorna vacío."""
        loader = LazySkillLoader(auto_discover=False)
        ctx = loader.get_active_skills_context()
        assert ctx == ""

    def test_get_active_skills_context_with_skills(self, skills_dir: Path) -> None:
        """get_active_skills_context retorna contenido formateado."""
        loader = LazySkillLoader(skills_dir=str(skills_dir), auto_discover=True)
        loader.load_tier2(["hedgefund"])
        ctx = loader.get_active_skills_context()
        assert "## Loaded Skills" in ctx
        assert "hedgefund" in ctx
        assert "(minified)" in ctx

    def test_get_active_skills_context_tier3(self, skills_dir: Path) -> None:
        """Skills en tier 3 muestran '(full)'."""
        loader = LazySkillLoader(skills_dir=str(skills_dir), auto_discover=True)
        loader.load_tier3(["quant-trading"])
        ctx = loader.get_active_skills_context()
        assert "(full)" in ctx
        assert "quant-trading" in ctx

    def test_get_loaded_skill_names(self, skills_dir: Path) -> None:
        """get_loaded_skill_names retorna nombres de skills cargados."""
        loader = LazySkillLoader(skills_dir=str(skills_dir), auto_discover=True)
        loader.load_tier2(["hedgefund"])
        names = loader.get_loaded_skill_names()
        assert "hedgefund" in names
        assert "quant-trading" not in names

    def test_get_loaded_skill_names_filtered(self, skills_dir: Path) -> None:
        """get_loaded_skill_names filtra por tier (tier >= N)."""
        loader = LazySkillLoader(skills_dir=str(skills_dir), auto_discover=True)
        loader.load_tier3(["quant-trading"])
        names_t1 = loader.get_loaded_skill_names(tier=1)
        names_t3 = loader.get_loaded_skill_names(tier=3)
        names_t4 = loader.get_loaded_skill_names(tier=4)
        assert "quant-trading" in names_t3
        # tier >= 1 incluye todos los cargados
        assert "quant-trading" in names_t1
        # tier >= 4 no incluye nada (max tier es 3)
        assert "quant-trading" not in names_t4


# ===========================================================================
# Tests: Detección de Dominio
# ===========================================================================


class TestDomainDetection:
    """Tests para detect_domains."""

    def test_detect_general(self, skills_dir: Path) -> None:
        """Mensaje genérico retorna ['general']."""
        loader = LazySkillLoader(skills_dir=str(skills_dir), auto_discover=True)
        domains = loader.detect_domains("configure the system please")
        assert "general" in domains

    def test_detect_trading(self, skills_dir: Path) -> None:
        """Mensaje con keywords de trading detecta dominio trading."""
        loader = LazySkillLoader(skills_dir=str(skills_dir), auto_discover=True)
        domains = loader.detect_domains("implement a trading strategy with alpha signals")
        assert "trading" in domains

    def test_detect_empty_message(self, skills_dir: Path) -> None:
        """Mensaje vacío retorna ['general']."""
        loader = LazySkillLoader(skills_dir=str(skills_dir), auto_discover=True)
        domains = loader.detect_domains("")
        assert domains == ["general"]

    def test_detect_general_always_present(self, skills_dir: Path) -> None:
        """'general' siempre está incluido al final."""
        loader = LazySkillLoader(skills_dir=str(skills_dir), auto_discover=True)
        domains = loader.detect_domains("buy 100 shares of AAPL market order")
        assert domains[-1] == "general"

    def test_detect_ranking_by_score(self, skills_dir: Path) -> None:
        """Dominios se ordenan por score descendente."""
        loader = LazySkillLoader(skills_dir=str(skills_dir), auto_discover=True)
        # healthtech tiene keywords que deberían puntuar
        domains = loader.detect_domains("patient diagnosis and clinical healthcare")
        # 'health' y 'clinical' y 'healthcare' deberían dar healthtech sobre general
        assert "healthtech" in domains

    def test_detect_caches_results(self, skills_dir: Path) -> None:
        """Resultados se cachean en _domain_cache.

        Solo se cachea si hay match de keywords (scores no vacío).
        """
        loader = LazySkillLoader(skills_dir=str(skills_dir), auto_discover=True)
        # "configure system deploy" contiene keywords de 'general'
        loader.detect_domains("configure system deploy the api")
        assert len(loader._domain_cache) >= 1


# ===========================================================================
# Tests: Hit Tracking y Auto-Promoción
# ===========================================================================


class TestHitTracking:
    """Tests para record_hit y auto-promoción."""

    def test_record_hit_increments(self, skills_dir: Path) -> None:
        """record_hit incrementa hit_count y stats."""
        loader = LazySkillLoader(skills_dir=str(skills_dir), auto_discover=True)
        loader.record_hit("hedgefund")
        skill = loader._skills["hedgefund"]
        assert skill.hit_count == 1
        assert loader._stats["hits"] == 1

    def test_record_hit_unknown_skill(self, skills_dir: Path) -> None:
        """record_hit con skill desconocido no falla."""
        loader = LazySkillLoader(skills_dir=str(skills_dir), auto_discover=True)
        loader.record_hit("void")  # no error

    def test_auto_promote_after_3_hits(self, skills_dir: Path) -> None:
        """3 hits promueven automáticamente a tier 2."""
        loader = LazySkillLoader(skills_dir=str(skills_dir), auto_discover=True)
        skill = loader._skills["hedgefund"]
        assert skill.tier == 1
        for _ in range(3):
            loader.record_hit("hedgefund")
        assert skill.tier >= 2
        assert skill.loaded is True

    def test_auto_promote_does_not_downgrade(self, skills_dir: Path) -> None:
        """Auto-promoción no baja tier si ya está en tier 3."""
        loader = LazySkillLoader(skills_dir=str(skills_dir), auto_discover=True)
        loader.load_tier3(["quant-trading"])
        skill = loader._skills["quant-trading"]
        assert skill.tier == 3
        for _ in range(5):
            loader.record_hit("quant-trading")
        assert skill.tier == 3  # no downgrade


# ===========================================================================
# Tests: get_skill
# ===========================================================================


class TestGetSkill:
    """Tests para get_skill."""

    def test_get_skill_exists(self, skills_dir: Path) -> None:
        """get_skill retorna SkillInfo si existe."""
        loader = LazySkillLoader(skills_dir=str(skills_dir), auto_discover=True)
        skill = loader.get_skill("hedgefund")
        assert skill is not None
        assert skill.name == "hedgefund"

    def test_get_skill_nonexistent(self, skills_dir: Path) -> None:
        """get_skill retorna None si no existe."""
        loader = LazySkillLoader(skills_dir=str(skills_dir), auto_discover=True)
        skill = loader.get_skill("void")
        assert skill is None


# ===========================================================================
# Tests: Estadísticas
# ===========================================================================


class TestStats:
    """Tests para get_stats."""

    def test_get_stats_initial(self) -> None:
        """get_stats inicial tiene valores en cero."""
        loader = LazySkillLoader(auto_discover=False)
        stats = loader.get_stats()
        assert stats["total_skills"] == 0
        assert stats["active_skills"] == 0
        assert stats["tokens_saved"] >= 0

    def test_get_stats_after_discovery(self, skills_dir: Path) -> None:
        """get_stats refleja skills descubiertos."""
        loader = LazySkillLoader(skills_dir=str(skills_dir), auto_discover=True)
        stats = loader.get_stats()
        assert stats["total_skills"] == 4
        assert stats["tier1_only"] == 4
        assert stats["tier2_loaded"] == 0

    def test_get_stats_after_loading(self, skills_dir: Path) -> None:
        """get_stats refleja skills cargados."""
        loader = LazySkillLoader(skills_dir=str(skills_dir), auto_discover=True)
        loader.load_tier2(["hedgefund"])
        stats = loader.get_stats()
        assert stats["active_skills"] == 1
        assert stats["tier2_loaded"] == 1

    def test_get_stats_tokens_saved(self, skills_dir: Path) -> None:
        """get_stats calcula tokens ahorrados vs carga completa."""
        loader = LazySkillLoader(skills_dir=str(skills_dir), auto_discover=True)
        stats = loader.get_stats()
        # Debe haber ahorro porque cargamos solo tier1
        assert stats["tokens_saved_pct"] >= 0


# ===========================================================================
# Tests: Extract Description
# ===========================================================================


class TestExtractDescription:
    """Tests para _extract_description (YAML frontmatter)."""

    def test_extract_double_quotes(self) -> None:
        """Extrae description entre comillas dobles."""
        content = '---\ndescription: "My awesome skill"\n---\n\nContent'
        result = LazySkillLoader._extract_description(content)
        assert result == "My awesome skill"

    def test_extract_single_quotes(self) -> None:
        """Extrae description entre comillas simples."""
        content = "---\ndescription: 'Single quoted desc'\n---\n\nContent"
        result = LazySkillLoader._extract_description(content)
        assert result == "Single quoted desc"

    def test_extract_unquoted(self) -> None:
        """Extrae description sin comillas."""
        content = "---\ndescription: Plain description here\n---\n\nContent"
        result = LazySkillLoader._extract_description(content)
        assert result == "Plain description here"

    def test_extract_no_description(self) -> None:
        """Sin description retorna string vacío."""
        content = "---\ntitle: My Skill\n---\n\nContent"
        result = LazySkillLoader._extract_description(content)
        assert result == ""

    def test_extract_empty_content(self) -> None:
        """Contenido vacío retorna string vacío."""
        result = LazySkillLoader._extract_description("")
        assert result == ""

    def test_extract_multiline_description(self) -> None:
        """Toma primera línea de description."""
        content = "---\ndescription: First line\nsecond line\n---\n\nContent"
        result = LazySkillLoader._extract_description(content)
        assert result == "First line"


# ===========================================================================
# Tests: Manejo de Errores
# ===========================================================================


class TestErrorHandling:
    """Tests para manejo de errores y edge cases."""

    def test_skills_dir_is_file_raises_error(self, tmp_path: Path) -> None:
        """Si skills_dir es un archivo, discover_skills lanza NotADirectoryError."""
        file_path = tmp_path / "notadir"
        file_path.write_text("", encoding="utf-8")
        with pytest.raises((NotADirectoryError, OSError)):
            LazySkillLoader(skills_dir=str(file_path), auto_discover=True)

    def test_skills_dir_with_subdirs_no_skill_files(self, tmp_path: Path) -> None:
        """Subdirectorios sin SKILL.md no rompen el descubrimiento."""
        sub = tmp_path / "subskill"
        sub.mkdir()
        # no SKILL.md dentro
        loader = LazySkillLoader(skills_dir=str(tmp_path), auto_discover=True)
        assert len(loader._skills) == 1  # subskill se descubre pero sin contenido
        skill = loader._skills["subskill"]
        assert skill.description == "Skill: subskill"

    def test_skill_file_with_bad_encoding_raises(self, tmp_path: Path) -> None:
        """Archivo con encoding inválido lanza UnicodeDecodeError."""
        sub = tmp_path / "badskill"
        sub.mkdir()
        (sub / "SKILL.md").write_bytes(b"---\ndescription: \xff\xfe bad\n---\n\ncontent")
        with pytest.raises(UnicodeDecodeError):
            LazySkillLoader(skills_dir=str(tmp_path), auto_discover=True)

    def test_load_tier2_skill_uses_full_fallback(self, mixed_skills_dir: Path) -> None:
        """load_tier2 para skill sin min.md usa content_tier3 como tier2 (fallback discover)."""
        loader = LazySkillLoader(skills_dir=str(mixed_skills_dir), auto_discover=True)
        # risk-execution solo tiene SKILL.md (content_tier3), sin min.md
        # Pero discover copia content_tier3 a content_tier2 como fallback
        result = loader.load_tier2(["risk-execution"])
        assert result["risk-execution"] is True
        skill = loader._skills["risk-execution"]
        # content_tier2 se pobló con fallback en discover -> tier 2
        assert skill.tier == 2

    def test_record_hit_before_discovery(self) -> None:
        """record_hit en loader vacío no falla."""
        loader = LazySkillLoader(auto_discover=False)
        loader.record_hit("anything")  # no error

    def test_dual_discovery_idempotent(self, skills_dir: Path) -> None:
        """Segundo discover_skills no duplica skills."""
        loader = LazySkillLoader(skills_dir=str(skills_dir), auto_discover=True)
        count1 = len(loader._skills)
        loader.discover_skills()
        assert len(loader._skills) == count1


# ===========================================================================
# Tests: Cache de Skills (Idempotencia)
# ===========================================================================


class TestSkillCache:
    """Tests para cache de skills — idempotencia y recarga."""

    def test_skill_cache_same_instance(self, skills_dir: Path) -> None:
        """Mismo objeto SkillInfo se reusa entre tier1 y tier2."""
        loader = LazySkillLoader(skills_dir=str(skills_dir), auto_discover=True)
        skill_before = loader._skills["hedgefund"]
        loader.load_tier2(["hedgefund"])
        skill_after = loader._skills["hedgefund"]
        assert skill_before is skill_after
        assert skill_after.tier == 2

    def test_active_skills_distinct_from_all(self, skills_dir: Path) -> None:
        """_active_skills es un subconjunto de _skills."""
        loader = LazySkillLoader(skills_dir=str(skills_dir), auto_discover=True)
        loader.load_tier2(["hedgefund"])
        for name in loader._active_skills:
            assert name in loader._skills

    def test_cache_clear_on_different_instance(self) -> None:
        """Diferentes instancias tienen caches independientes."""
        loader1 = LazySkillLoader(auto_discover=False)
        loader2 = LazySkillLoader(auto_discover=False)
        loader1._skills["test"] = SkillInfo(name="test", description="d")
        assert "test" not in loader2._skills


# ===========================================================================
# Tests: Convenience create_loader
# ===========================================================================


class TestCreateLoader:
    """Tests para create_loader factory."""

    def test_create_loader_returns_instance(self) -> None:
        """create_loader retorna LazySkillLoader."""
        loader = create_loader()
        assert isinstance(loader, LazySkillLoader)

    def test_create_loader_auto_discovers(self, skills_dir: Path) -> None:
        """create_loader auto-descubre skills."""
        loader = create_loader(skills_dir=str(skills_dir))
        assert len(loader._skills) > 0
